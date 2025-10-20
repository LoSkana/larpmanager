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

from django.db.models import Count

from larpmanager.cache.config import get_assoc_config, get_event_config
from larpmanager.cache.feature import get_assoc_features, get_event_features
from larpmanager.models.accounting import AccountingItemMembership
from larpmanager.models.casting import Casting
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration, TicketTier


def get_users_data(ids):
    """Get user display names and emails for deadline notifications.

    Args:
        ids (list): List of member IDs

    Returns:
        list: List of (display_name, email) tuples
    """
    return [
        (str(mb), mb.email)
        for mb in Member.objects.filter(pk__in=ids).order_by("surname").only("name", "surname", "email", "nickname")
    ]


def get_membership_fee_year(assoc_id, year=None):
    """Get set of member IDs who paid membership fee for given year.

    Args:
        assoc_id (int): Association ID
        year (int, optional): Year to check, defaults to current year

    Returns:
        set: Set of member IDs who paid fee for the year
    """
    if not year:
        year = datetime.now().year
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
        features = get_event_features(run.event_id)
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


def deadlines_profile(collect, features, memberships, now, reg, run, tolerance):
    """Check profile completion deadlines for registration.

    Args:
        collect (dict): Dictionary to collect deadline violations
        features (dict): Event features
        memberships (dict): Member ID to membership mapping
        now (datetime): Current datetime
        reg: Registration instance
        run: Run instance
        tolerance (int): Tolerance days for deadlines

    Side effects:
        Updates collect with profile deadline violations
    """
    membership = memberships.get(reg.member_id)
    if not membership:
        return

    if membership.compiled:
        return

    if now.date() + timedelta(days=tolerance) > run.start:
        collect["profile_del"].append(reg.member_id)
    else:
        collect["profile"].append(reg.member_id)


def deadlines_membership(
    collect: dict[str, list[int]],
    features: dict[str, any],
    fees: set[int],
    memberships: dict[int, any],
    now: datetime,
    reg: any,
    run: any,
    tolerance: int,
) -> None:
    """Check membership and fee deadlines for registration.

    Evaluates membership status and fee payment deadlines for a given registration,
    updating the collect dictionary with any violations found based on tolerance periods.

    Args:
        collect: Dictionary to collect deadline violations, organized by violation type
        features: Event features configuration dictionary
        fees: Set of member IDs who have paid their membership fee
        memberships: Mapping from member ID to membership instance
        now: Current datetime for deadline calculations
        reg: Registration instance being evaluated
        run: Run instance containing event start date
        tolerance: Number of days tolerance allowed for deadlines

    Side Effects:
        Updates collect dictionary with membership and fee deadline violations
        under keys: 'memb', 'memb_del', 'fee', 'fee_del'
    """
    # Get membership for the registered member
    membership = memberships.get(reg.member_id)
    if not membership:
        return

    # Check if membership is in incomplete states (empty, joined, uploaded)
    if membership.status in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
        # Calculate days elapsed since registration creation
        elapsed = now.date() - reg.created.date()
        # Classify as delayed if beyond tolerance, otherwise normal violation
        key = "memb_del" if elapsed.days > tolerance else "memb"
        collect[key].append(reg.member_id)
        return

    # Skip further checks if membership is submitted (in review)
    if membership.status in [MembershipStatus.SUBMITTED]:
        return

    # Determine if fee checking is required (not LAOG event and current year)
    check_fee = "laog" not in features and run.start.year == now.year
    if check_fee and reg.member_id not in fees:
        # Check if we're within tolerance days of the event start
        if now.date() + timedelta(days=tolerance) > run.start:
            # Event is imminent - mark as delayed fee violation
            collect["fee_del"].append(reg.member_id)
        else:
            # Event is still far enough - mark as regular fee violation
            collect["fee"].append(reg.member_id)


def deadlines_payment(collect, features, reg, tolerance):
    """Check payment deadlines for registration.

    Args:
        collect (dict): Dictionary to collect deadline violations
        features (dict): Event features
        reg: Registration instance with deadline attribute
        tolerance (int): Tolerance days for deadlines

    Side effects:
        Updates collect with payment deadline violations
    """
    # check payments
    if "payment" not in features:
        return

    if reg.deadline < -tolerance:
        collect["pay_del"].append(reg.member_id)
    elif reg.deadline < 0:
        collect["pay"].append(reg.member_id)


def deadlines_casting(collect, features, player_ids, run):
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

    casting_chars = get_event_config(run.event_id, "casting_characters", 1)
    # members that already have a character
    casted = (
        Registration.objects.filter(run=run)
        .annotate(chars=Count("rcrs"))
        .filter(chars__gte=casting_chars)
        .values_list("member_id", flat=True)
    )

    # members that sent casting preferences
    prefs = Casting.objects.filter(run=run).values_list("member_id", flat=True)

    collect["cast"] = set(player_ids) - (set(casted) | set(prefs))
