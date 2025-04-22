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

from larpmanager.models.accounting import AccountingItemMembership
from larpmanager.models.casting import Casting
from larpmanager.models.member import Member, Membership
from larpmanager.models.registration import Registration, RegistrationTicket
from larpmanager.cache.feature import get_assoc_features, get_event_features


def get_users_data(ids):
    return [
        (str(mb), mb.email)
        for mb in Member.objects.filter(pk__in=ids).order_by("surname").only("name", "surname", "email", "nickname")
    ]


def get_membership_fee_year(assoc_id, year=None):
    if not year:
        year = datetime.now().year
    return set(
        AccountingItemMembership.objects.filter(assoc_id=assoc_id, year=year).values_list("member_id", flat=True)
    )


def check_run_deadlines(runs):
    if not runs:
        return []

    run_ids = [run.id for run in runs]
    regs_id = []
    members_id = []
    members_map = {}
    all_regs = {}
    for run in runs:
        all_regs[run.id] = []
        members_map[run.id] = []

    reg_que = Registration.objects.filter(run_id__in=run_ids, cancellation_date__isnull=True)
    reg_que = reg_que.exclude(ticket__tier=RegistrationTicket.WAITING)
    for reg in reg_que:
        regs_id.append(reg.id)
        members_id.append(reg.member_id)
        all_regs[reg.run_id].append(reg)

    tolerance = int(runs[0].event.assoc.get_config("deadlines_tolerance", "30"))

    assoc_id = runs[0].event.assoc_id
    now = datetime.now()
    uses_membership = "membership" in get_assoc_features(assoc_id)

    memberships = {}
    fees = {}
    if uses_membership:
        memberships = {
            el.member_id: el for el in Membership.objects.filter(assoc_id=assoc_id, member_id__in=members_id)
        }
        fees = get_membership_fee_year(assoc_id)

    all_res = []

    for run in runs:
        if not run.start:
            continue

        collect = {k: [] for k in ["pay", "pay_del", "casting", "memb", "memb_del", "fee", "fee_del"]}
        features = get_event_features(run.event.id)
        player_ids = []

        for reg in all_regs[run.id]:
            if reg.ticket and reg.ticket.tier != RegistrationTicket.STAFF:
                player_ids.append(reg.member_id)

            if uses_membership:
                membership = memberships.get(reg.member_id)
                if not membership:
                    continue

                if membership.status in [Membership.EMPTY, Membership.JOINED, Membership.UPLOADED]:
                    elapsed = now.date() - reg.created.date()
                    key = "memb_del" if elapsed.days > tolerance else "memb"
                    collect[key].append(reg.member_id)
                    continue

                if membership.status in [Membership.SUBMITTED]:
                    continue

                check_fee = "laog" not in features and run.start.year == now.year
                if check_fee and reg.member_id not in fees:
                    # if we are now *tolerance* days away from the larp start
                    if now.date() + timedelta(days=tolerance) > run.start:
                        collect["fee_del"].append(reg.member_id)
                    else:
                        collect["fee"].append(reg.member_id)

            deadlines_payment(collect, features, reg, tolerance)

        deadlines_casting(collect, features, player_ids, run)
        result = {k: get_users_data(v) for k, v in collect.items()}
        result["run"] = run
        all_res.append(result)

    return all_res


def deadlines_payment(collect, features, reg, tolerance):
    # check payments
    if "payment" not in features:
        return

    if reg.deadline < -tolerance:
        collect["pay_del"].append(reg.member_id)
    elif reg.deadline < 0:
        collect["pay"].append(reg.member_id)


def deadlines_casting(collect, features, player_ids, run):
    # check casting
    if "casting" not in features:
        return

    casting_chars = run.event.get_config("casting_characters", 1)
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
