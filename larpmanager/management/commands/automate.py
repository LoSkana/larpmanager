# LarpManager - https://larpmanager.com
# Copyright (C) 2025 Scanagatta Mauro
#
# This file is part of LarpManager and is dual-licensed:
#
# 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
#    as published by the Free Software Foundation. You may use, modify, and
#    distribute this file under those terms.
#
# 2. Under a commercial license, allowing use in closed-source or proprietary
#    environments without the obligations of the AGPL.
#
# If you have obtained this file under the AGPL, and you make it available over
# a network, you must also make the complete source code available under the same license.
#
# For more information or to purchase a commercial license, contact:
# commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary

from datetime import datetime, timedelta

from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand
from django.db import connection

from larpmanager.accounting.balance import check_accounting, check_run_accounting
from larpmanager.accounting.token_credit import get_regs, get_regs_paying_incomplete
from larpmanager.cache.config import get_association_config
from larpmanager.cache.feature import get_association_features, get_event_features
from larpmanager.mail.accounting import notify_invoice_check
from larpmanager.mail.base import check_holiday
from larpmanager.mail.member import send_password_reset_remainder
from larpmanager.mail.remind import (
    notify_deadlines,
    remember_membership,
    remember_membership_fee,
    remember_pay,
    remember_profile,
)
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemMembership,
    Discount,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.association import Association
from larpmanager.models.event import DevelopStatus, Run
from larpmanager.models.member import Badge, Member, Membership, MembershipStatus, get_user_membership
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.utils.common import get_time_diff_today
from larpmanager.utils.pdf import print_run_bkg
from larpmanager.utils.tasks import notify_admins


class Command(BaseCommand):
    """Django management command for automated background processes.

    Handles periodic tasks including:
    - Registration accounting updates
    - Reminder email sending
    - Badge achievement processing
    - Payment invoice cleanup
    - Database maintenance
    """

    help = "Automate processes "

    def handle(self, *args, **options):
        """Main command entry point with exception handling.

        Args:
            *args: Command arguments
            **options: Command options
        """
        try:
            self.go()
        except Exception as e:
            notify_admins("Automate", "", e)

    def go(self) -> None:
        """Execute all automated processes.

        Performs comprehensive automation tasks including database cleanup,
        accounting updates, reminder checks, badge processing, and payment
        validation across all associations and runs.

        This method orchestrates the daily automation workflow by:
        1. Cleaning up the database
        2. Updating accounting for incomplete registrations
        3. Running feature-specific checks for each association
        4. Performing standard system-wide checks
        5. Processing run-specific automation tasks

        Note:
            This method should be scheduled to run daily via cron job or
            similar scheduling mechanism.
        """
        # Clean up database records and perform initial maintenance
        self.clean_db()

        # Update accounting for all registrations with incomplete payments
        # Process each registration to recalculate totals and payment status
        registrations_with_incomplete_payments = get_regs_paying_incomplete()
        for registration in registrations_with_incomplete_payments.select_related("run"):
            registration.save()

        # Process feature-specific checks for each association
        # Only run checks if the association has the required features enabled
        for association in Association.objects.all():
            enabled_features = get_association_features(association.id)

            # Check if reminder notifications need to be sent
            if "remind" in enabled_features:
                self.check_remind(association)

            # Process achievement/badge updates for members
            if "badge" in enabled_features:
                self.check_achievements(association)

            # Validate and update accounting records
            if "record_acc" in enabled_features:
                check_accounting(association.id)

        # Perform standard system-wide maintenance checks
        # These checks run regardless of feature flags
        self.check_password_reset()
        self.check_payment_not_approved()
        self.check_old_payments()

        # Process automation tasks for active runs only
        # Skip completed or cancelled runs to avoid unnecessary processing
        for run in Run.objects.exclude(development__in=[DevelopStatus.DONE, DevelopStatus.CANC]):
            event_features = get_event_features(run.event_id)

            # Check and process deadline notifications
            if "deadlines" in event_features:
                self.check_deadline(run)

            # Update run-specific accounting records
            if "record_acc" in event_features:
                check_run_accounting(run)

            # Generate background PDF documents for the run
            if "print_pdf" in event_features:
                print_run_bkg(run.event.association.slug, run.get_slug())

    @staticmethod
    def check_old_payments():
        """Delete payment invoices older than 60 days with CREATED status.

        Cleans up abandoned payment attempts to prevent database bloat.
        """
        # delete old payment invoice
        reference_date = datetime.now() - timedelta(days=60)
        payment_invoices_query = PaymentInvoice.objects.filter(status=PaymentStatus.CREATED)
        for payment_invoice in payment_invoices_query.filter(created__lte=reference_date.date()):
            payment_invoice.delete()

    @staticmethod
    def check_payment_not_approved():
        """Notify admins about payment invoices awaiting approval.

        Sends notifications for submitted payment invoices and cleans up
        orphaned invoices that reference non-existent objects.
        """
        # Notify payment invoices not approved
        for payment_invoice in PaymentInvoice.objects.filter(status=PaymentStatus.SUBMITTED):
            try:
                notify_invoice_check(payment_invoice)
            except ObjectDoesNotExist:
                payment_invoice.delete()
            except Exception as exception:
                notify_admins("notify_invoice_check fail", payment_invoice.idx, exception)

    @staticmethod
    def check_password_reset():
        """Send password reset reminders and clear processed requests.

        Processes pending password reset requests by sending reminder emails
        and clearing the reset flags from membership records.
        """
        # check password reset
        pending_reset_memberships = Membership.objects.exclude(password_reset__exact="")
        for membership in pending_reset_memberships.exclude(password_reset__isnull=True):
            send_password_reset_remainder(membership)
            membership.password_reset = ""
            membership.save()

    @staticmethod
    def clean_db():
        """Execute configured database cleanup operations.

        Runs SQL cleanup commands defined in CLEAN_DB setting to maintain
        database performance and remove stale data.
        """
        # PaymentInvoice.objects.filter(txn_id__isnull=True).delete()
        with connection.cursor() as database_cursor:
            for cleanup_sql_query in conf_settings.CLEAN_DB:
                database_cursor.execute(cleanup_sql_query)

    def check_achievements(self, association: Association) -> None:
        """Process badge achievements for association members.

        Analyzes past and future event registrations to award badges
        based on participation and friend referral patterns. Processes
        all completed events for participation badges and future events
        for friend referral tracking.

        Args:
            association: Association instance to process badges for

        Returns:
            None: Function performs side effects by updating badge cache
        """
        # Initialize cache for badges and player data
        cache = {"badges": {}, "players": {}}
        events_by_id = {}

        # Process past events for participation badges
        for run in Run.objects.filter(end__lt=datetime.today(), event__association=association):
            # Get all non-cancelled registrations
            registrations = Registration.objects.filter(run=run, cancellation_date__isnull=True)

            # Process registrations excluding waiting list, staff, and NPCs
            for registration in registrations.exclude(
                ticket__tier__in=[TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC]
            ):
                self.check_ach_player(registration, cache)

            # Cache event data for reference
            events_by_id[run.event_id] = run.event

        # Process future events for friend referral tracking
        for run in Run.objects.filter(end__gt=datetime.today()):
            # Get confirmed registrations (excluding waiting list)
            for registration in Registration.objects.filter(run=run, cancellation_date__isnull=True).exclude(
                ticket__tier=TicketTier.WAITING
            ):
                # Check friend referral achievements
                self.check_friends_player(registration, cache)

    def add_member_badge(self, badge_code: str, member: Member, badge_cache: dict) -> None:
        """Award a badge to a member if not already possessed.

        This method checks if a member already has a specific badge and awards it
        if they don't. It uses a cache for performance optimization to avoid
        repeated database queries.

        Args:
            badge_code: Badge code identifier to award
            member: Member instance to award the badge to
            badge_cache: Badge and player cache dictionary for performance optimization

        Returns:
            None
        """
        # Check if member already possesses this badge
        if badge_code in self.get_cache_badges_player(badge_cache, member):
            return

        # Retrieve badge object from cache
        badge = self.get_cache_badge(badge_cache, badge_code)
        if not badge:
            return

        # Award badge to member by adding to many-to-many relationship
        badge.members.add(member)

    def check_event_badge(self, event, m, cache):
        """Award event-specific badge to member.

        Args:
            event: Event instance to derive badge from
            m: Member instance to award badge to
            cache (dict): Badge cache for performance
        """
        self.add_member_badge(event.slug, m, cache)

    @staticmethod
    def get_cache_badges_player(cache: dict, member: Member) -> list:
        """Get cached list of badge codes for a member.

        Retrieves badge codes from cache if available, otherwise queries the database
        to build the cache entry for the member's badges.

        Args:
            cache (dict): Player badge cache containing 'players' key with member IDs
            member: Member instance to get badges for

        Returns:
            list: Badge codes already possessed by member

        Note:
            Modifies the cache dictionary by adding member badge data if not present.
        """
        # Check if member's badges are already cached
        if member.id not in cache["players"]:
            # Build list of badge codes from member's badges
            badge_codes = []
            for badge in member.badges.all():
                badge_codes.append(badge.cod)

            # Cache the badge codes for this member
            cache["players"][member.id] = badge_codes

        # Return cached badge codes
        return cache["players"][member.id]

    @staticmethod
    def get_cache_badge(badge_cache: dict, badge_code: str) -> Badge | None:
        """Get badge instance from cache or database.

        Retrieves a badge by code from the provided cache dictionary. If the badge
        is not found in cache, attempts to fetch it from the database and stores
        it in the cache for future use.

        Args:
            badge_cache: Dictionary containing cached badge instances under 'badges' key
            badge_code: Badge code string used to identify and retrieve the badge

        Returns:
            Badge instance if found in cache or database, None if not found or on error

        Note:
            Modifies the cache dictionary by adding newly fetched badges
        """
        try:
            # Check if badge code is not already cached
            if badge_code not in badge_cache["badges"]:
                # Fetch badge from database and store in cache
                badge_cache["badges"][badge_code] = Badge.objects.get(cod=badge_code)

            # Return cached badge instance
            return badge_cache["badges"][badge_code]
        except Exception:
            # Return None on any error (badge not found, cache issues, etc.)
            return None

    @staticmethod
    def get_count(
        counter_name: str, activity_cache: dict[str, dict[int, int]], member, increment_value: int = 1
    ) -> int:
        """Track and increment member activity counters.

        Args:
            counter_name: Counter name (e.g., 'play', 'staff', 'orga')
            activity_cache: Activity cache mapping counter names to member ID counters
            member: Member instance
            increment_value: Value to add to counter (default: 1)

        Returns:
            Updated counter value for the member
        """
        # Initialize counter type if not exists
        if counter_name not in activity_cache:
            activity_cache[counter_name] = {}

        # Initialize member counter if not exists
        if member.id not in activity_cache[counter_name]:
            activity_cache[counter_name][member.id] = 0

        # Increment counter and return new value
        activity_cache[counter_name][member.id] += increment_value
        return activity_cache[counter_name][member.id]

    def check_friends_player(self, reg: Registration, cache: dict) -> None:
        """Check and award friend referral badges based on friend count.

        This method counts how many friends a player has referred and awards
        appropriate tier badges (bronze, silver, gold, platinum) based on
        predefined thresholds.

        Args:
            reg: Registration instance to check friend count for
            cache: Activity cache dictionary for tracking friend counts
                  and preventing duplicate badge awards

        Returns:
            None
        """
        # Count total friend referral discounts associated with this registration
        friend_discount_count = AccountingItemDiscount.objects.filter(detail=reg.id, disc__typ=Discount.FRIEND).count()

        # Get current friend count from cache or calculate if not cached
        current_friend_count = self.get_count("friend", cache, reg.member, friend_discount_count)

        # Define badge tiers and their corresponding friend count thresholds
        badge_tiers = ["bronze", "silver", "gold", "platinum"]
        tier_thresholds = [1, 4, 8, 12]  # Minimum friends required for each tier

        # Iterate through each tier and award badges if threshold is met
        for tier_index in range(0, len(badge_tiers)):
            # Skip tier if friend count doesn't meet minimum requirement
            if current_friend_count < tier_thresholds[tier_index]:
                continue

            # Generate badge key and award to member
            badge_key = f"friends-{badge_tiers[tier_index]}"
            self.add_member_badge(badge_key, reg.member, cache)

    def check_ach_player(self, reg: Registration, cache: dict) -> None:
        """Check and award player participation badges based on play count.

        Awards bronze, silver, gold, and platinum badges to players based on
        their number of registrations/participation events.

        Args:
            reg: Registration instance for the current player
            cache: Activity cache dictionary for tracking play counts across members

        Returns:
            None
        """
        # Count total registrations/plays for this member
        play_count = self.get_count("play", cache, reg.member)

        # Define badge tiers and their required play count thresholds
        badge_types = ["bronze", "silver", "gold", "platinum"]
        play_count_limits = [1, 5, 10, 15]

        # Iterate through each badge tier and award if threshold is met
        for badge_index in range(0, len(badge_types)):
            if play_count < play_count_limits[badge_index]:
                continue

            # Generate badge key and award to member
            badge_key = f"player-{badge_types[badge_index]}"
            self.add_member_badge(badge_key, reg.member, cache)

    def check_badge_help(self, m: Member, cache: dict) -> None:
        """Check and award help/support badges based on member activity.

        Evaluates a member's help activity count and awards bronze-level badges
        when specific thresholds are met. Currently supports bronze tier badges
        for members who have provided help at least once.

        Args:
            m: Member instance to check for badge eligibility
            cache: Activity cache dictionary for tracking help counts and badges

        Returns:
            None: Function modifies cache in-place by adding badges
        """
        # Retrieve the current help activity count for this member
        count = self.get_count("help", cache, m)

        # Define badge tiers and their corresponding thresholds
        tp = ["bronze"]  # Available badge tiers
        lm = [1]  # Minimum help count required for each tier

        # Iterate through each badge tier and check eligibility
        for i in range(0, len(tp)):
            # Skip if member hasn't reached the threshold for this tier
            if count < lm[i]:
                continue

            # Generate badge key and award it to the member
            k = f"help-{tp[i]}"
            self.add_member_badge(k, m, cache)

    def check_badge_trad(self, m: Member, cache: dict) -> None:
        """Check and award translation/localization badges based on member activity.

        Evaluates a member's translation contributions and awards appropriate badges
        based on predefined thresholds. Currently supports bronze badge for 1+ translations.

        Args:
            m: Member instance to check for badge eligibility
            cache: Activity cache dictionary for tracking translation counts and badge state

        Returns:
            None: Function modifies cache in-place by adding eligible badges
        """
        # Retrieve translation count from cache for the member
        count = self.get_count("trad", cache, m)

        # Define badge types and their minimum requirements
        tp = ["bronze"]
        lm = [1]

        # Iterate through each badge type and check eligibility
        for i in range(0, len(tp)):
            # Skip if member hasn't met minimum requirement for this badge
            if count < lm[i]:
                continue

            # Award badge if requirements are met
            k = f"trad-{tp[i]}"
            self.add_member_badge(k, m, cache)

    def check_badge_staff(self, m: Member, cache: dict) -> None:
        """Check and award staff participation badges based on staff registration count.

        Evaluates a member's staff participation history and awards bronze, silver,
        gold, or platinum badges based on the number of staff registrations. Badges
        are awarded cumulatively (e.g., a member with 7 registrations gets bronze,
        silver, and gold badges).

        Args:
            m: Member instance to check for badge eligibility
            cache: Activity cache dictionary for tracking staff participation counts
                  and preventing duplicate badge awards

        Returns:
            None: Function modifies cache state and awards badges as side effects
        """
        # Get total count of staff registrations for this member
        count = self.get_count("staff", cache, m)

        # Define badge types and their minimum requirements
        tp = ["bronze", "silver", "gold", "platinum"]
        lm = [1, 4, 7, 10]

        # Iterate through each badge tier and award if requirements are met
        for i in range(0, len(tp)):
            # Skip if member hasn't reached the minimum count for this badge
            if count < lm[i]:
                continue

            # Generate badge key and award the badge to the member
            k = f"staff-{tp[i]}"
            self.add_member_badge(k, m, cache)

    def check_badge_orga(self, m: Member, cache: dict) -> None:
        """Check and award organizer badges based on event organization count.

        Evaluates a member's organizing activity and awards bronze, silver, gold,
        or platinum organizer badges based on predefined thresholds.

        Args:
            m: Member instance to check for organizer badges
            cache: Activity cache dictionary for tracking organizer counts
                  and preventing duplicate badge awards

        Returns:
            None: Badges are awarded as side effects through add_member_badge
        """
        # Get the total count of events organized by this member
        count = self.get_count("orga", cache, m)

        # Define badge types and their corresponding thresholds
        tp = ["bronze", "silver", "gold", "platinum"]
        lm = [1, 3, 5, 7]

        # Iterate through each badge tier and award if threshold is met
        for i in range(0, len(tp)):
            # Skip if member hasn't reached this threshold yet
            if count < lm[i]:
                continue

            # Construct badge key and award the badge
            k = f"organizzatore-{tp[i]}"
            self.add_member_badge(k, m, cache)

    def check_remind(self, association: Association) -> None:
        """Check and send reminder emails for association registrations.

        This function processes reminders for upcoming event registrations based on
        association configuration. It respects holiday settings and reminder day
        preferences while filtering for future events.

        Args:
            association (Association): Association instance to process reminders for.
                Must have get_config method for accessing configuration values.

        Returns:
            None: This function performs side effects (sending emails) but returns nothing.

        Note:
            The function filters out registrations for events that start within 3 days
            or have already started, and only processes events with valid start dates.
        """
        # Check if reminders should be sent during holidays
        send_reminders_during_holidays = association.get_config("remind_holidays", True)

        # Skip processing if it's a holiday and holiday reminders are disabled
        if not send_reminders_during_holidays and check_holiday():
            return

        # Get the number of days before event to send reminders
        reminder_days_before_event = int(association.get_config("remind_days", 5))

        # Get all registrations for this association
        registrations_queryset = get_regs(association)

        # Calculate reference date (3 days from now) to filter out immediate events
        minimum_start_date = datetime.now() + timedelta(days=3)

        # Filter registrations to exclude events without start dates or starting too soon
        registrations_queryset = registrations_queryset.exclude(run__start__isnull=True).exclude(
            run__start__lte=minimum_start_date.date()
        )

        # Process each qualifying registration for reminder emails
        for registration in registrations_queryset.select_related("run", "ticket"):
            self.remind_reg(registration, association, reminder_days_before_event)

    def remind_reg(self, reg: Registration, association: Association, remind_days: int) -> None:
        """Process reminder logic for a specific registration.

        Handles various reminder scenarios based on registration status, membership state,
        and event features. Sends appropriate reminder emails based on the registration's
        current state and membership requirements.

        Args:
            reg: Registration instance to check reminders for
            association: Association instance containing the registration
            remind_days: Interval in days for sending reminders

        Returns:
            None
        """
        # Get event features and user membership for this registration
        event_features = get_event_features(reg.run.event_id)
        get_user_membership(reg.member, association.id)

        # Check if today is the scheduled day to send reminder emails
        # Only send reminders on specific intervals based on registration creation date
        if get_time_diff_today(reg.created) % remind_days != 1:
            return

        # Process reminders only for non-waiting registrations
        if reg.ticket and reg.ticket.tier != TicketTier.WAITING:
            membership = reg.member.membership
            reminder_sent = False

            # Handle membership-related reminders if membership feature is enabled
            if "membership" in event_features:
                # Send membership reminder for empty or joined members
                if membership.status in (MembershipStatus.EMPTY, MembershipStatus.JOINED):
                    remember_membership(reg)
                    reminder_sent = True
                # Check membership fee payment for accepted members (except LAOG events)
                elif "laog" not in event_features and membership.status == MembershipStatus.ACCEPTED:
                    self.check_membership_fee(reg)
                    reminder_sent = True

            # Send profile completion reminder if membership wasn't handled and profile incomplete
            if not reminder_sent and not membership.compiled:
                remember_profile(reg)

        # Check payment status and send payment reminders if registration has alerts
        if reg.alert:
            self.check_payment(reg)

    @staticmethod
    def check_membership_fee(registration: Registration) -> None:
        """Check if membership fee reminder should be sent.

        This function determines whether a membership fee reminder should be sent
        to a member based on their registration status, payment history, and
        pending invoices for the current year.

        Args:
            registration: Registration instance to check membership fee for

        Returns:
            None: Function performs side effects (sending reminders) but returns nothing

        Note:
            Only processes registrations for the current year and sends reminders
            only if no membership fee has been paid and no payment is pending.
        """
        # Get current year for membership fee validation
        current_year = datetime.today().year

        # Skip if registration is not for current year
        if current_year != registration.run.end.year:
            return

        # Check if membership fee has already been paid for this year
        membership_fee_already_paid = AccountingItemMembership.objects.filter(
            year=registration.run.end.year, member=registration.member
        ).count()
        if membership_fee_already_paid > 0:
            return

        # Check if there are pending membership payments
        membership_payment_pending = PaymentInvoice.objects.filter(
            member=registration.member,
            status=PaymentStatus.SUBMITTED,
            typ=PaymentType.REGISTRATION,
        ).count()
        if membership_payment_pending > 0:
            return

        # Send membership fee reminder if no payment exists and none pending
        remember_membership_fee(registration)

    @staticmethod
    def check_payment(reg: Registration) -> None:
        """Check if payment reminder should be sent for registration.

        This function determines whether a payment reminder should be sent to a member
        for their registration by checking various conditions including alert status,
        quota availability, and existing pending payments.

        Args:
            reg: Registration instance to check payment alerts for

        Returns:
            None: This function performs actions but does not return a value
        """
        # Check if alerts are enabled for this registration
        if not reg.alert:
            return

        # Verify that the registration has an associated quota
        if not reg.quota:
            return

        # Query for any existing submitted payment invoices for this registration
        # to avoid sending duplicate payment reminders
        pending_payment_invoices = PaymentInvoice.objects.filter(
            member_id=reg.member_id,
            status=PaymentStatus.SUBMITTED,
            typ=PaymentType.REGISTRATION,
            idx=reg.id,
        )

        # If there are pending payments, skip sending reminder
        if pending_payment_invoices.count() > 0:
            return

        # Send payment reminder if all conditions are met
        remember_pay(reg)

    def check_deadline(self, run: Run) -> None:
        """Check and send deadline notifications for run.

        This function performs deadline checking for a specific run, considering holidays,
        run timing constraints, and configured deadline intervals. It will send notifications
        when appropriate based on the deadline_days configuration.

        Args:
            run: Run instance to check deadlines for. Must have start date and associated event.

        Returns:
            None
        """
        # Skip processing if today is a holiday
        if check_holiday():
            return

        # Calculate reference date (7 days ago) and skip if run is too old or has no start date
        reference_date = datetime.now() - timedelta(days=7)
        if not run.start or run.start < reference_date.date():
            return

        # Get deadline interval configuration for the association
        deadline_interval_days = int(get_association_config(run.event.association_id, "deadline_days", 0))
        if not deadline_interval_days:
            return

        # Check if today matches the deadline notification schedule
        # Only notify when days until run start modulo deadline_days equals 1
        if get_time_diff_today(run.start) % deadline_interval_days != 1:
            return

        # Send deadline notifications for this run
        notify_deadlines(run)
