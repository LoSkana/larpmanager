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
from typing import Any

from django.conf import settings as conf_settings
from django.db.models import Count
from django.utils import timezone

from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.feature import get_association_features, get_event_features
from larpmanager.models.accounting import AccountingItemMembership
from larpmanager.models.casting import Casting
from larpmanager.models.event import Run
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration, TicketTier


def get_users_data(member_ids: Any) -> Any:
    """Get user display names and emails for deadline notifications.

    Args:
        member_ids (list): List of member IDs

    Returns:
        list: List of (display_name, email) tuples

    """
    return [
        (str(member), member.email)
        for member in Member.objects.filter(pk__in=member_ids)
        .order_by("surname")
        .only("name", "surname", "email", "nickname")
    ]


def get_membership_fee_year(association_id: int, year: Any = None) -> set:
    """Get set of member IDs who paid membership fee for given year.

    Args:
        association_id (int): Association ID
        year (int, optional): Year to check, defaults to current year

    Returns:
        set: Set of member IDs who paid fee for the year

    """
    if not year:
        year = timezone.now().year
    return set(
        AccountingItemMembership.objects.filter(association_id=association_id, year=year).values_list(
            "member_id",
            flat=True,
        ),
    )


def check_run_deadlines(runs: list[Run]) -> list:
    """Check deadline compliance for registrations.

    Args:
        runs: Run instances to check

    Returns:
        List of dicts with deadline violations per run

    """
    if not runs:
        return []

    # Collect all run and member IDs
    run_ids = [run.id for run in runs]
    registration_ids = []
    member_ids = []
    members_by_run = {}
    registrations_by_run = {}
    for run in runs:
        registrations_by_run[run.id] = []
        members_by_run[run.id] = []

    # Query active registrations
    registration_query = Registration.objects.filter(run_id__in=run_ids, cancellation_date__isnull=True)
    registration_query = registration_query.exclude(ticket__tier=TicketTier.WAITING)
    for registration in registration_query:
        registration_ids.append(registration.id)
        member_ids.append(registration.member_id)
        registrations_by_run[registration.run_id].append(registration)

    # Get tolerance setting
    tolerance = int(get_association_config(runs[0].event.association_id, "deadlines_tolerance", default_value="30"))

    # Check membership feature
    association_id = runs[0].event.association_id
    now = timezone.now()
    uses_membership = "membership" in get_association_features(association_id)

    # Load memberships and fees
    memberships = {
        membership.member_id: membership
        for membership in Membership.objects.filter(association_id=association_id, member_id__in=member_ids)
    }
    fees = {}
    if uses_membership:
        fees = get_membership_fee_year(association_id)

    all_results = []

    # Check each run
    for run in runs:
        if not run.start:
            continue

        # Initialize collectors for different deadline types
        deadline_violations = {
            category: []
            for category in [
                "pay",
                "pay_del",
                "casting",
                "memb",
                "memb_del",
                "fee",
                "fee_del",
                "profile",
                "profile_del",
            ]
        }
        features = get_event_features(run.event_id)
        player_ids = []

        # Check each registration
        for registration in registrations_by_run[run.id]:
            if registration.ticket and registration.ticket.tier not in [TicketTier.STAFF, TicketTier.NPC]:
                player_ids.append(registration.member_id)

            # Check membership or profile deadlines
            if uses_membership:
                deadlines_membership(
                    deadline_violations,
                    features,
                    fees,
                    memberships,
                    now,
                    registration,
                    run,
                    tolerance,
                )
            else:
                deadlines_profile(deadline_violations, memberships, now, registration, run, tolerance)

            # Check payment deadlines
            deadlines_payment(deadline_violations, features, registration, tolerance)

        # Check casting deadlines
        deadlines_casting(deadline_violations, features, player_ids, run)
        result = {category: get_users_data(violations) for category, violations in deadline_violations.items()}
        result["run"] = run
        all_results.append(result)

    return all_results


def deadlines_profile(
    deadline_violations: Any,
    memberships: Any,
    current_datetime: Any,
    registration: Any,
    event_run: Any,
    tolerance_days: Any,
) -> None:
    """Check profile completion deadlines for registration.

    Args:
        deadline_violations (dict): Dictionary to collect deadline violations
        memberships (dict): Member ID to membership mapping
        current_datetime (datetime): Current datetime
        registration: Registration instance
        event_run: Run instance
        tolerance_days (int): Tolerance days for deadlines

    Side effects:
        Updates deadline_violations with profile deadline violations

    """
    membership = memberships.get(registration.member_id)
    if not membership:
        return

    if membership.compiled:
        return

    if current_datetime.date() + timedelta(days=tolerance_days) > event_run.start:
        deadline_violations["profile_del"].append(registration.member_id)
    else:
        deadline_violations["profile"].append(registration.member_id)


def deadlines_membership(
    violations_by_type: dict[str, list[int]],
    event_features: dict[str, any],
    members_with_paid_fees: set[int],
    memberships_by_member_id: dict[int, any],
    current_datetime: datetime,
    registration: any,
    event_run: any,
    tolerance_days: int,
) -> None:
    """Check membership and fee deadlines for registration.

    Evaluates membership status and fee payment deadlines for a given registration,
    updating the collect dictionary with any violations found based on tolerance periods.

    Args:
        violations_by_type: Dictionary to collect deadline violations, organized by violation type
        event_features: Event features configuration dictionary
        members_with_paid_fees: Set of member IDs who have paid their membership fee
        memberships_by_member_id: Mapping from member ID to membership instance
        current_datetime: Current datetime for deadline calculations
        registration: Registration instance being evaluated
        event_run: Run instance containing event start date
        tolerance_days: Number of days tolerance allowed for deadlines

    Side Effects:
        Updates violations_by_type dictionary with membership and fee deadline violations
        under keys: 'memb', 'memb_del', 'fee', 'fee_del'

    """
    # Get membership for the registered member
    membership = memberships_by_member_id.get(registration.member_id)
    if not membership:
        return

    # Check if membership is in incomplete states (empty, joined, uploaded)
    if membership.status in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
        # Calculate days elapsed since registration creation
        days_elapsed = current_datetime.date() - registration.created.date()
        # Classify as delayed if beyond tolerance, otherwise normal violation
        violation_type = "memb_del" if days_elapsed.days > tolerance_days else "memb"
        violations_by_type[violation_type].append(registration.member_id)
        return

    # Skip further checks if membership is submitted (in review)
    if membership.status in [MembershipStatus.SUBMITTED]:
        return

    # Determine if fee checking is required (not LAOG event and current year)
    should_check_fee = "laog" not in event_features and event_run.start.year == current_datetime.year
    if should_check_fee and registration.member_id not in members_with_paid_fees:
        # Check if we're within tolerance days of the event start
        if current_datetime.date() + timedelta(days=tolerance_days) > event_run.start:
            # Event is imminent - mark as delayed fee violation
            violations_by_type["fee_del"].append(registration.member_id)
        else:
            # Event is still far enough - mark as regular fee violation
            violations_by_type["fee"].append(registration.member_id)


def deadlines_payment(deadline_violations: Any, event_features: Any, registration: Any, tolerance_days: Any) -> None:
    """Check payment deadlines for registration.

    Args:
        deadline_violations (dict): Dictionary to collect deadline violations
        event_features (dict): Event features
        registration: Registration instance with deadline attribute
        tolerance_days (int): Tolerance days for deadlines

    Side effects:
        Updates deadline_violations with payment deadline violations

    """
    # check payments
    if "payment" not in event_features:
        return

    # Skip alert setting if quota is negligible
    if registration.quota <= conf_settings.MAX_ROUNDING_TOLERANCE:
        return

    if registration.deadline < -tolerance_days:
        deadline_violations["pay_del"].append(registration.member_id)
    elif registration.deadline <= 0:
        deadline_violations["pay"].append(registration.member_id)


def deadlines_casting(collect: Any, features: Any, player_ids: Any, run: Any) -> None:
    """Check casting preference submission for players.

    Args:
        collect (dict): Dictionary to collect deadline violations
        features (dict): Event features
        player_ids (list): List of player member IDs
        run: Run instance

    Side effects:
        Updates collect with casting preference violations

    """
    # check casting
    if "casting" not in features:
        return

    casting_characters_required = get_event_config(run.event_id, "casting_characters", default_value=1)
    # members that already have a character
    members_with_characters = (
        Registration.objects.filter(run=run)
        .annotate(character_count=Count("rcrs"))
        .filter(character_count__gte=casting_characters_required)
        .values_list("member_id", flat=True)
    )

    # members that sent casting preferences
    members_with_preferences = Casting.objects.filter(run=run).values_list("member_id", flat=True)

    collect["cast"] = set(player_ids) - (set(members_with_characters) | set(members_with_preferences))
