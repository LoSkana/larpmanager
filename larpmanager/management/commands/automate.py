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
from larpmanager.cache.feature import get_assoc_features, get_event_features
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
from larpmanager.models.member import Badge, Membership, MembershipStatus, get_user_membership
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

    def go(self):
        """Execute all automated processes.

        Performs database cleanup, accounting updates, reminder checks,
        badge processing, and payment validation across all associations.
        """
        self.clean_db()

        # update accounting on all registrations
        reg_que = get_regs_paying_incomplete()
        for reg in reg_que.select_related("run"):
            reg.save()

        # perform checks on assocs
        for assoc in Association.objects.all():
            features = get_assoc_features(assoc.id)
            if "remind" in features:
                self.check_remind(assoc)
            if "badge" in features:
                self.check_achievements(assoc)
            if "record_acc" in features:
                check_accounting(assoc.id)

        # perform standard checks
        self.check_password_reset()
        self.check_payment_not_approved()
        self.check_old_payments()

        # perform check on runs
        for run in Run.objects.exclude(development__in=[DevelopStatus.DONE, DevelopStatus.CANC]):
            ev_features = get_event_features(run.event_id)
            if "deadlines" in ev_features:
                self.check_deadline(run)
            if "record_acc" in ev_features:
                check_run_accounting(run)
            if "print_pdf" in ev_features:
                print_run_bkg(run.event.assoc.slug, run.get_slug())

    @staticmethod
    def check_old_payments():
        """Delete payment invoices older than 60 days with CREATED status.

        Cleans up abandoned payment attempts to prevent database bloat.
        """
        # delete old payment invoice
        ref = datetime.now() - timedelta(days=60)
        que = PaymentInvoice.objects.filter(status=PaymentStatus.CREATED)
        for pi in que.filter(created__lte=ref.date()):
            pi.delete()

    @staticmethod
    def check_payment_not_approved():
        """Notify admins about payment invoices awaiting approval.

        Sends notifications for submitted payment invoices and cleans up
        orphaned invoices that reference non-existent objects.
        """
        # Notify payment invoices not approved
        for p in PaymentInvoice.objects.filter(status=PaymentStatus.SUBMITTED):
            try:
                notify_invoice_check(p)
            except ObjectDoesNotExist:
                p.delete()
            except Exception as e:
                notify_admins("notify_invoice_check fail", p.idx, e)

    @staticmethod
    def check_password_reset():
        """Send password reset reminders and clear processed requests.

        Processes pending password reset requests by sending reminder emails
        and clearing the reset flags from membership records.
        """
        # check password reset
        que = Membership.objects.exclude(password_reset__exact="")
        for mb in que.exclude(password_reset__isnull=True):
            send_password_reset_remainder(mb)
            mb.password_reset = ""
            mb.save()

    @staticmethod
    def clean_db():
        """Execute configured database cleanup operations.

        Runs SQL cleanup commands defined in CLEAN_DB setting to maintain
        database performance and remove stale data.
        """
        # PaymentInvoice.objects.filter(txn_id__isnull=True).delete()
        with connection.cursor() as cursor:
            for sql in conf_settings.CLEAN_DB:
                cursor.execute(sql)

    def check_achievements(self, assoc):
        """Process badge achievements for association members.

        Analyzes past and future event registrations to award badges
        based on participation and friend referral patterns.

        Args:
            assoc: Association instance to process badges for
        """
        cache = {"badges": {}, "players": {}}
        ev = {}
        # past events
        for run in Run.objects.filter(end__lt=datetime.today(), event__assoc=assoc):
            que = Registration.objects.filter(run=run, cancellation_date__isnull=True)
            for reg in que.exclude(ticket__tier__in=[TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC]):
                self.check_ach_player(reg, cache)
            ev[run.event.id] = run.event

        # future events
        for run in Run.objects.filter(end__gt=datetime.today()):
            for reg in Registration.objects.filter(run=run, cancellation_date__isnull=True).exclude(
                ticket__tier=TicketTier.WAITING
            ):
                self.check_friends_player(reg, cache)

    def add_member_badge(self, cod, member, cache):
        """Award a badge to a member if not already possessed.

        Args:
            cod (str): Badge code to award
            member: Member instance to award badge to
            cache (dict): Badge and player cache for performance
        """
        # check if it has already
        if cod in self.get_cache_badges_player(cache, member):
            return
        # get badge
        badge = self.get_cache_badge(cache, cod)
        if not badge:
            return
        # print(reg.member)
        # print(k)
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
    def get_cache_badges_player(cache, member):
        """Get cached list of badge codes for a member.

        Args:
            cache (dict): Player badge cache
            member: Member instance to get badges for

        Returns:
            list: Badge codes already possessed by member
        """
        if member.id not in cache["players"]:
            ch = []
            for b in member.badges.all():
                ch.append(b.cod)
            cache["players"][member.id] = ch
        return cache["players"][member.id]

    @staticmethod
    def get_cache_badge(cache, cod):
        """Get badge instance from cache or database.

        Args:
            cache (dict): Badge cache
            cod (str): Badge code to retrieve

        Returns:
            Badge or None: Badge instance if found, None otherwise
        """
        try:
            if cod not in cache["badges"]:
                cache["badges"][cod] = Badge.objects.get(cod=cod)
            return cache["badges"][cod]
        except Exception:
            return None

    @staticmethod
    def get_count(nm, cache, m, v=1):
        """Track and increment member activity counters.

        Args:
            nm (str): Counter name (e.g., 'play', 'staff', 'orga')
            cache (dict): Activity cache
            m: Member instance
            v (int): Value to add to counter

        Returns:
            int: Updated counter value
        """
        if nm not in cache:
            cache[nm] = {}
        if m.id not in cache[nm]:
            cache[nm][m.id] = 0
        cache[nm][m.id] += v
        return cache[nm][m.id]

    def check_friends_player(self, reg, cache):
        """Check and award friend referral badges.

        Args:
            reg: Registration instance
            cache (dict): Activity cache for tracking friend counts
        """
        # count how many friends you got
        c = AccountingItemDiscount.objects.filter(detail=reg.id, disc__typ=Discount.FRIEND).count()
        count = self.get_count("friend", cache, reg.member, c)
        tp = ["bronze", "silver", "gold", "platinum"]
        lm = [1, 4, 8, 12]
        for i in range(0, len(tp)):
            if count < lm[i]:
                continue
            k = f"friends-{tp[i]}"
            self.add_member_badge(k, reg.member, cache)

    def check_ach_player(self, reg, cache):
        """Check and award player participation badges.

        Args:
            reg: Registration instance
            cache (dict): Activity cache for tracking play counts
        """
        # count how many registrations
        count = self.get_count("play", cache, reg.member)
        tp = ["bronze", "silver", "gold", "platinum"]
        lm = [1, 5, 10, 15]
        for i in range(0, len(tp)):
            if count < lm[i]:
                continue
            k = f"player-{tp[i]}"
            self.add_member_badge(k, reg.member, cache)

    def check_badge_help(self, m, cache):
        """Check and award help/support badges.

        Args:
            m: Member instance
            cache (dict): Activity cache for tracking help counts
        """
        # count how many registration
        count = self.get_count("help", cache, m)
        tp = ["bronze"]
        lm = [1]
        for i in range(0, len(tp)):
            if count < lm[i]:
                continue
            k = f"help-{tp[i]}"
            self.add_member_badge(k, m, cache)

    def check_badge_trad(self, m, cache):
        """Check and award translation/localization badges.

        Args:
            m: Member instance
            cache (dict): Activity cache for tracking translation counts
        """
        # count how many registrations
        count = self.get_count("trad", cache, m)
        tp = ["bronze"]
        lm = [1]
        for i in range(0, len(tp)):
            if count < lm[i]:
                continue
            k = f"trad-{tp[i]}"
            self.add_member_badge(k, m, cache)

    def check_badge_staff(self, m, cache):
        """Check and award staff participation badges.

        Args:
            m: Member instance
            cache (dict): Activity cache for tracking staff counts
        """
        # count how many registrations
        count = self.get_count("staff", cache, m)
        tp = ["bronze", "silver", "gold", "platinum"]
        lm = [1, 4, 7, 10]
        for i in range(0, len(tp)):
            if count < lm[i]:
                continue
            k = f"staff-{tp[i]}"
            self.add_member_badge(k, m, cache)

    def check_badge_orga(self, m, cache):
        """Check and award organizer badges.

        Args:
            m: Member instance
            cache (dict): Activity cache for tracking organizer counts
        """
        # count how many registrations
        count = self.get_count("orga", cache, m)
        tp = ["bronze", "silver", "gold", "platinum"]
        lm = [1, 3, 5, 7]
        for i in range(0, len(tp)):
            if count < lm[i]:
                continue
            k = f"organizzatore-{tp[i]}"
            self.add_member_badge(k, m, cache)

    def check_remind(self, assoc):
        """Check and send reminder emails for association registrations.

        Args:
            assoc: Association instance to process reminders for
        """
        holidays = assoc.get_config("remind_holidays", True)

        if not holidays and check_holiday():
            return

        remind_days = int(assoc.get_config("remind_days", 5))

        reg_que = get_regs(assoc)
        ref = datetime.now() + timedelta(days=3)
        reg_que = reg_que.exclude(run__start__isnull=True).exclude(run__start__lte=ref.date())
        for reg in reg_que.select_related("run", "ticket"):
            self.remind_reg(reg, assoc, remind_days)

    def remind_reg(self, reg, assoc, remind_days):
        """Process reminder logic for a specific registration.

        Args:
            reg: Registration instance to check reminders for
            assoc: Association instance
            remind_days (int): Interval for sending reminders
        """
        ev_features = get_event_features(reg.run.event_id)

        get_user_membership(reg.member, assoc.id)

        # check today is the day to send emails
        if get_time_diff_today(reg.created) % remind_days != 1:
            return

        # if the player is not waiting
        if reg.ticket and reg.ticket.tier != TicketTier.WAITING:
            m = reg.member.membership
            handled = False

            if "membership" in ev_features:
                # check if player is a member
                if m.status in (MembershipStatus.EMPTY, MembershipStatus.JOINED):
                    remember_membership(reg)
                    handled = True
                # check if players has not payed yet it's membership fee
                elif "laog" not in ev_features and m.status == MembershipStatus.ACCEPTED:
                    self.check_membership_fee(reg)
                    handled = True

            if not handled and not m.compiled:
                remember_profile(reg)

        if reg.alert:
            self.check_payment(reg)

    @staticmethod
    def check_membership_fee(reg):
        """Check if membership fee reminder should be sent.

        Args:
            reg: Registration instance to check membership fee for
        """
        year = datetime.today().year
        if year != reg.run.end.year:
            return

        membership_payed = AccountingItemMembership.objects.filter(year=reg.run.end.year, member=reg.member).count()
        if membership_payed > 0:
            return

        membership_pending = PaymentInvoice.objects.filter(
            member=reg.member,
            status=PaymentStatus.SUBMITTED,
            typ=PaymentType.REGISTRATION,
        ).count()
        if membership_pending > 0:
            return

        remember_membership_fee(reg)

    @staticmethod
    def check_payment(reg):
        """Check if payment reminder should be sent for registration.

        Args:
            reg: Registration instance to check payment alerts for
        """
        # check there is an alert
        if not reg.alert:
            return

        if not reg.quota:
            return

        # check if there is a submitted payment
        pending_que = PaymentInvoice.objects.filter(
            member_id=reg.member_id,
            status=PaymentStatus.SUBMITTED,
            typ=PaymentType.REGISTRATION,
            idx=reg.id,
        )
        if pending_que.count() > 0:
            return

        remember_pay(reg)

    def check_deadline(self, run):
        """Check and send deadline notifications for run.

        Args:
            run: Run instance to check deadlines for
        """
        if check_holiday():
            return

        ref = datetime.now() - timedelta(days=7)
        if not run.start or run.start < ref.date():
            return

        deadline_days = int(run.event.assoc.get_config("deadline_days", 0))
        if not deadline_days:
            return
        if get_time_diff_today(run.start) % deadline_days != 1:
            return

        notify_deadlines(run)
