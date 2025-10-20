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

from django.db.models import Count

from larpmanager.cache.config import get_assoc_config
from larpmanager.cache.feature import get_assoc_features, get_event_features
from larpmanager.models.accounting import AccountingItemMembership
from larpmanager.models.casting import Casting
from larpmanager.models.event import Run
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration, TicketTier


def get_users_data(ids: list[int]) -> list[tuple[str, str]]:
    """Get user display names and emails for deadline notifications.

    Retrieves member information including display names and email addresses
    for a given list of member IDs, ordered by surname for consistent output.

    Args:
        ids: List of member primary key IDs to fetch data for.

    Returns:
        List of tuples containing (display_name, email) pairs for each member.
        Display names are string representations of Member objects.

    Example:
        >>> get_users_data([1, 2, 3])
        [('John Doe', 'john@example.com'), ('Jane Smith', 'jane@example.com')]
    """
    # Query members by primary key, ordered by surname for consistent results
    members = Member.objects.filter(pk__in=ids).order_by("surname")

    # Only fetch required fields to optimize database query performance
    members = members.only("name", "surname", "email", "nickname")

    # Build list of (display_name, email) tuples using string representation
    return [(str(mb), mb.email) for mb in members]


def get_membership_fee_year(assoc_id: int, year: int | None = None) -> set[int]:
    """Get set of member IDs who paid membership fee for given year.

    Args:
        assoc_id: Association ID to filter by.
        year: Year to check for membership payments. If None, defaults to current year.

    Returns:
        Set of member IDs who paid membership fee for the specified year.

    Example:
        >>> get_membership_fee_year(1, 2023)
        {123, 456, 789}
    """
    # Use current year if no specific year provided
    if not year:
        year = datetime.now().year

    # Query membership payments for the association and year
    # Return as set of member IDs for efficient membership testing
    return set(
        AccountingItemMembership.objects.filter(assoc_id=assoc_id, year=year).values_list("member_id", flat=True)
    )


def check_run_deadlines(runs: list) -> list:
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
    regs_id = []
    members_id = []
    members_map = {}
    all_regs = {}
    for run in runs:
        all_regs[run.id] = []
        members_map[run.id] = []

    # Query active registrations
    reg_que = Registration.objects.filter(run_id__in=run_ids, cancellation_date__isnull=True)
    reg_que = reg_que.exclude(ticket__tier=TicketTier.WAITING)
    for reg in reg_que:
        regs_id.append(reg.id)
        members_id.append(reg.member_id)
        all_regs[reg.run_id].append(reg)

    # Get tolerance setting
    tolerance = int(get_assoc_config(runs[0].event.assoc_id, "deadlines_tolerance", "30"))

    # Check membership feature
    assoc_id = runs[0].event.assoc_id
    now = datetime.now()
    uses_membership = "membership" in get_assoc_features(assoc_id)

    # Load memberships and fees
    memberships = {el.member_id: el for el in Membership.objects.filter(assoc_id=assoc_id, member_id__in=members_id)}
    fees = {}
    if uses_membership:
        fees = get_membership_fee_year(assoc_id)

    all_res = []

    # Check each run
    for run in runs:
        if not run.start:
            continue

        # Initialize collectors for different deadline types
        collect = {
            k: [] for k in ["pay", "pay_del", "casting", "memb", "memb_del", "fee", "fee_del", "profile", "profile_del"]
        }
        features = get_event_features(run.event.id)
        player_ids = []

        # Check each registration
        for reg in all_regs[run.id]:
            if reg.ticket and reg.ticket.tier not in [TicketTier.STAFF, TicketTier.NPC]:
                player_ids.append(reg.member_id)

            # Check membership or profile deadlines
            if uses_membership:
                deadlines_membership(collect, features, fees, memberships, now, reg, run, tolerance)
            else:
                deadlines_profile(collect, features, memberships, now, reg, run, tolerance)

            # Check payment deadlines
            deadlines_payment(collect, features, reg, tolerance)

        # Check casting deadlines
        deadlines_casting(collect, features, player_ids, run)
        result = {k: get_users_data(v) for k, v in collect.items()}
        result["run"] = run
        all_res.append(result)

    return all_res


def deadlines_profile(
    collect: dict[str, list[int]],
    features: dict,
    memberships: dict[int, object],
    now: datetime,
    reg: object,
    run: object,
    tolerance: int,
) -> None:
    """Check profile completion deadlines for registration.

    Determines if a member's profile completion deadline has been violated
    based on the run start date and tolerance period. Updates the collect
    dictionary with appropriate deadline violations.

    Args:
        collect: Dictionary to collect deadline violations with keys 'profile_del'
                and 'profile' containing lists of member IDs
        features: Event features configuration dictionary
        memberships: Mapping of member ID to membership objects
        now: Current datetime for deadline comparison
        reg: Registration instance containing member_id
        run: Run instance containing start date
        tolerance: Number of tolerance days before deadline enforcement

    Side effects:
        Updates collect dict by appending member IDs to 'profile_del' or
        'profile' lists based on deadline status
    """
    # Get membership object for the registration's member
    membership = memberships.get(reg.member_id)
    if not membership:
        return

    # Skip check if member profile is already compiled
    if membership.compiled:
        return

    # Check if deadline has passed considering tolerance period
    # If current date plus tolerance exceeds run start, it's a deletion case
    if now.date() + timedelta(days=tolerance) > run.start:
        collect["profile_del"].append(reg.member_id)
    else:
        # Otherwise, it's a regular profile deadline warning
        collect["profile"].append(reg.member_id)


def deadlines_membership(
    collect: dict[str, list[int]],
    features: dict[str, Any],
    fees: set[int],
    memberships: dict[int, Any],
    now: datetime,
    reg: Registration,
    run: Run,
    tolerance: int,
) -> None:
    """Check membership and fee deadlines for registration.

    Examines registration membership status and fee payment deadlines,
    updating the collect dictionary with any violations found.

    Args:
        collect: Dictionary to collect deadline violations by type
        features: Event features configuration
        fees: Set of member IDs who paid membership fee
        memberships: Mapping from member ID to membership object
        now: Current datetime for deadline calculations
        reg: Registration instance being checked
        run: Run instance containing event details
        tolerance: Number of tolerance days for deadlines

    Returns:
        None: Function updates collect dictionary in place

    Side Effects:
        Updates collect with membership and fee deadline violations
    """
    # Get membership for this registration's member
    membership = memberships.get(reg.member_id)
    if not membership:
        return

    # Check for incomplete membership statuses
    # These require membership completion within tolerance period
    if membership.status in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
        elapsed = now.date() - reg.created.date()
        # Use delayed key if tolerance exceeded, otherwise normal key
        key = "memb_del" if elapsed.days > tolerance else "memb"
        collect[key].append(reg.member_id)
        return

    # Skip fee checks for submitted memberships (already processed)
    if membership.status in [MembershipStatus.SUBMITTED]:
        return

    # Check membership fee requirements
    # Skip fee check if "laog" feature enabled or event not in current year
    check_fee = "laog" not in features and run.start.year == now.year
    if check_fee and reg.member_id not in fees:
        # Check if we're within tolerance days of event start
        # Use delayed collection if deadline is imminent
        if now.date() + timedelta(days=tolerance) > run.start:
            collect["fee_del"].append(reg.member_id)
        else:
            collect["fee"].append(reg.member_id)


def deadlines_payment(
    collect: dict[str, list[int]], features: dict[str, any], reg: Registration, tolerance: int
) -> None:
    """Check payment deadlines for registration and update violation collections.

    Examines registration payment deadlines against tolerance thresholds and
    categorizes violations into immediate and grace period collections.

    Args:
        collect: Dictionary containing lists of member IDs for different violation types.
                Must have 'pay_del' and 'pay' keys for deadline violations.
        features: Event feature configuration dictionary. Function returns early
                 if 'payment' feature is not enabled.
        reg: Registration instance containing deadline attribute (negative values
             indicate days past deadline).
        tolerance: Maximum allowed days past deadline before escalating violation
                  category (positive integer).

    Returns:
        None: Function modifies collect dictionary in-place.

    Side Effects:
        - Appends member_id to collect['pay_del'] for severe deadline violations
        - Appends member_id to collect['pay'] for minor deadline violations
    """
    # Early return if payment feature is not enabled for this event
    if "payment" not in features:
        return

    # Check deadline violation severity and categorize appropriately
    # Severe violation: past deadline beyond tolerance threshold
    if reg.deadline < -tolerance:
        collect["pay_del"].append(reg.member_id)
    # Minor violation: past deadline but within tolerance period
    elif reg.deadline < 0:
        collect["pay"].append(reg.member_id)


def deadlines_casting(collect: dict[str, set[int]], features: dict[str, bool], player_ids: list[int], run: Run) -> None:
    """Check casting preference submission for players.

    Identifies players who need to submit casting preferences by comparing
    registered players against those who already have characters or have
    submitted preferences.

    Args:
        collect: Dictionary to collect deadline violations, updated with 'cast' key
        features: Event features configuration mapping feature names to enabled status
        player_ids: List of player member IDs to check for casting requirements
        run: Run instance containing event and registration data

    Side Effects:
        Updates collect dictionary with 'cast' key containing set of member IDs
        who haven't submitted casting preferences and don't have enough characters.
    """
    # Skip casting checks if feature is not enabled
    if "casting" not in features:
        return

    # Get minimum required characters per player from event configuration
    casting_chars = run.event.get_config("casting_characters", 1)

    # Find members who already have sufficient characters assigned
    # Query registrations and count related character assignments (rcrs)
    casted = (
        Registration.objects.filter(run=run)
        .annotate(chars=Count("rcrs"))
        .filter(chars__gte=casting_chars)
        .values_list("member_id", flat=True)
    )

    # Find members who have submitted casting preferences
    prefs = Casting.objects.filter(run=run).values_list("member_id", flat=True)

    # Calculate players missing casting preferences
    # Exclude those with enough characters or existing preferences
    collect["cast"] = set(player_ids) - (set(casted) | set(prefs))
