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

from datetime import datetime

from dateutil.relativedelta import relativedelta

from larpmanager.cache.config import get_assoc_config
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemMembership,
    AccountingItemOther,
    Collection,
    OtherChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
    RefundStatus,
)
from larpmanager.models.event import DevelopStatus
from larpmanager.models.form import RegistrationChoice
from larpmanager.models.member import get_user_membership
from larpmanager.models.registration import Registration


def info_accounting(request, ctx):
    """Gather comprehensive accounting information for a member.

    Collects registration history, payment status, membership fees, donations,
    collections, refunds, and token/credit balances for display in member dashboard.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary with member and association ID

    Side effects:
        Populates ctx with accounting data including reg_list, payments_todo,
        payments_pending, refunds, and various balance information
    """
    member = ctx["member"]
    get_user_membership(member, ctx["a_id"])
    ctx["reg_list"] = []

    _info_membership(ctx, member, request)

    _info_donations(ctx, member, request)

    _info_collections(ctx, member, request)

    ctx["reg_years"] = {}

    pending = _init_pending(member)

    choices = _init_choices(member)

    # get all registrations in the future, or not completed
    for s in ["payments_todo", "payments_pending"]:
        ctx[s] = []

    reg_que = Registration.objects.filter(member=member, run__event__assoc_id=ctx["a_id"])
    reg_que = reg_que.exclude(run__development__in=[DevelopStatus.CANC])
    for reg in reg_que.select_related("run", "run__event", "ticket"):
        _init_regs(choices, ctx, pending, reg)

    # check open refund requests
    ctx["refunds"] = ctx["member"].refund_requests.filter(status=RefundStatus.REQUEST, assoc_id=ctx["a_id"])

    _info_token_credit(ctx, member)


def _init_regs(choices, ctx, pending, reg):
    """Initialize registration options and payment status tracking.

    Args:
        choices: Dictionary mapping registration IDs to their selected options
        ctx: Context dictionary to update with payment status
        pending: Dictionary of pending payment invoices
        reg: Registration instance to process

    Side effects:
        Updates ctx with payments_pending and payments_todo lists
        Sets reg.opts and reg.pending attributes
    """
    if reg.id not in choices:
        choices[reg.id] = {}
    reg.opts = choices[reg.id]
    ctx["reg_list"].append(reg)

    # check if there is a pending payment
    if reg.id in pending:
        reg.pending = True
        ctx["payments_pending"].append(reg)
    elif reg.quota > 0:
        ctx["payments_todo"].append(reg)
    if reg.run.start:
        if reg.run.start < datetime.now().date():
            return
        ctx["reg_years"][reg.run.start.year] = 1


def _init_pending(member):
    """Initialize pending payment tracking for a member.

    Args:
        member: Member instance to check for pending payments

    Returns:
        dict: Mapping of registration IDs to lists of pending payment invoices
    """
    pending = {}
    pending_que = PaymentInvoice.objects.filter(
        member_id=member.id,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.REGISTRATION,
    )
    for el in pending_que:
        if el.idx not in pending:
            pending[el.idx] = []
        pending[el.idx].append(el)
    return pending


def _init_choices(member):
    """Initialize registration choice tracking for a member.

    Args:
        member: Member instance to get registration choices for

    Returns:
        dict: Nested mapping of registration and question IDs to selected options
    """
    choices = {}
    choice_que = RegistrationChoice.objects.filter(reg__member_id=member.id)
    choice_que = choice_que.select_related("option", "question")
    for el in choice_que:
        if el.reg_id not in choices:
            choices[el.reg_id] = {}
        if el.question_id not in choices[el.reg_id]:
            choices[el.reg_id][el.question_id] = {"q": el.question, "l": []}
        choices[el.reg_id][el.question_id]["l"].append(el.option)
    return choices


def _info_token_credit(ctx, member):
    """Get token and credit balance information for a member.

    Args:
        ctx: Context dictionary with association ID to update
        member: Member instance to check balances for

    Side effects:
        Updates ctx with acc_tokens and acc_credits counts
    """
    # check if it had any token
    que = AccountingItemOther.objects.filter(
        member=member,
        oth=OtherChoices.TOKEN,
        assoc_id=ctx["a_id"],
    )
    ctx["acc_tokens"] = que.count()

    # check if it had any credits
    que_exp = AccountingItemExpense.objects.filter(member=member, is_approved=True, assoc_id=ctx["a_id"])
    que_cre = AccountingItemOther.objects.filter(
        member=member,
        oth=OtherChoices.CREDIT,
        assoc_id=ctx["a_id"],
    )
    ctx["acc_credits"] = que_exp.count() + que_cre.count()


def _info_collections(ctx, member, request):
    """Get collection information if collections feature is enabled.

    Args:
        ctx: Context dictionary with association ID to update
        member: Member instance to get collections for
        request: Django request with association features

    Side effects:
        Updates ctx with collections and collection_gifts if feature enabled
    """
    if "collection" not in request.assoc["features"]:
        return

    ctx["collections"] = Collection.objects.filter(organizer=member, assoc_id=ctx["a_id"])
    ctx["collection_gifts"] = AccountingItemCollection.objects.filter(member=member, collection__assoc_id=ctx["a_id"])


def _info_donations(ctx, member, request):
    """Get donation history if donations feature is enabled.

    Args:
        ctx: Context dictionary with association ID to update
        member: Member instance to get donations for
        request: Django request with association features

    Side effects:
        Updates ctx with donations list if feature enabled
    """
    if "donate" not in request.assoc["features"]:
        return

    que = AccountingItemDonation.objects.filter(member=member, assoc_id=ctx["a_id"])
    ctx["donations"] = que.order_by("-created")


def _info_membership(ctx, member, request):
    """Get membership fee information if membership feature is enabled.

    Args:
        ctx: Context dictionary with association ID to update
        member: Member instance to get membership info for
        request: Django request with association features

    Side effects:
        Updates ctx with membership fee history, current year status,
        pending status, and grace period information if feature enabled
    """
    if "membership" not in request.assoc["features"]:
        return

    year = datetime.now().year
    ctx["membership_fee"] = []
    for el in AccountingItemMembership.objects.filter(member=member, assoc_id=ctx["a_id"]).order_by("year"):
        ctx["membership_fee"].append(el.year)
    ctx["year_membership_fee"] = year in ctx["membership_fee"]
    pending_que = PaymentInvoice.objects.filter(
        member=member,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.MEMBERSHIP,
    )
    if pending_que.count() > 0:
        ctx["year_membership_pending"] = True

    ctx["year"] = year
    m_day = get_assoc_config(ctx["a_id"], "membership_day", "01-01")
    if m_day:
        m_grazing = int(get_assoc_config(ctx["a_id"], "membership_grazing", "0"))
        m_day += f"-{year}"
        dt = datetime.strptime(m_day, "%d-%m-%Y")
        dt += relativedelta(months=m_grazing)
        ctx["grazing"] = datetime.now() < dt
