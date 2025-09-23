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

from datetime import date, datetime
from decimal import Decimal

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.registration import get_display_choice
from larpmanager.cache.feature import get_event_features
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemDiscount,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemInflow,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemOutflow,
    AccountingItemPayment,
    AccountingItemTransaction,
    ExpenseChoices,
    OtherChoices,
    PaymentChoices,
    RecordAccounting,
)
from larpmanager.models.association import Association
from larpmanager.models.event import DevelopStatus, Run
from larpmanager.models.member import Membership
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.models.utils import get_sum


def get_acc_detail(nm, run, descr, cls, cho, typ, filters=None, reg=False):
    """Get detailed accounting breakdown for a specific accounting item type.

    Args:
        nm: Display name for the accounting category
        run: Run instance to filter accounting items
        descr: Description of the accounting category
        cls: Model class for accounting items (e.g., AccountingItemPayment)
        cho: Choices enumeration for display names
        typ: Field name to group items by (e.g., 'pay', 'exp')
        filters: Optional additional filters to apply
        reg: If True, filter by reg__run instead of run

    Returns:
        dict: Breakdown with totals, counts, and details by type
    """
    dc = {"tot": 0, "num": 0, "detail": {}, "name": nm, "descr": descr}
    if reg:
        lst = cls.objects.filter(reg__run=run)
    else:
        lst = cls.objects.filter(run=run)
    if filters:
        lst = lst.filter(**filters)
    for a in lst:
        dc["num"] += 1
        dc["tot"] += a.value
        if typ is None:
            continue
        tp = getattr(a, typ)
        if tp not in dc["detail"]:
            dc["detail"][tp] = {"tot": 0, "num": 0, "name": get_display_choice(cho, tp)}
        dc["detail"][tp]["num"] += 1
        dc["detail"][tp]["tot"] += a.value
    return dc


def get_acc_reg_type(el):
    """Determine registration type for accounting categorization.

    Args:
        el: Registration instance to categorize

    Returns:
        tuple: (type_code, display_name) for the registration type
    """
    if el.cancellation_date:
        return "can", "Disdetta"
    if not el.ticket:
        return "", ""
    return (
        el.ticket.tier,
        get_display_choice(TicketTier.choices, el.ticket.tier),
    )


def get_acc_reg_detail(nm, run, descr):
    """Get detailed registration accounting breakdown by ticket tier.

    Args:
        nm: Display name for the accounting category
        run: Run instance to get registrations for
        descr: Description of the accounting category

    Returns:
        dict: Breakdown of registrations by ticket tier with totals and counts
    """
    dc = {"tot": 0, "num": 0, "detail": {}, "name": nm, "descr": descr}
    for reg in Registration.objects.filter(run=run).select_related("ticket").filter(cancellation_date__isnull=True):
        (tp, descr) = get_acc_reg_type(reg)
        if tp not in dc["detail"]:
            dc["detail"][tp] = {"tot": 0, "num": 0, "name": descr}
        dc["detail"][tp]["num"] += 1
        dc["detail"][tp]["tot"] += reg.tot_iscr

        dc["num"] += 1
        dc["tot"] += reg.tot_iscr
    return dc


def get_token_details(nm, run):
    """Get token accounting details for a run.

    Args:
        nm: Display name for the token category
        run: Run instance to get token details for

    Returns:
        dict: Token totals and counts
    """
    dc = {"tot": 0, "num": 0, "detail": {}, "name": nm}
    for a in AccountingItemOther.objects.filter(run=run):
        dc["num"] += 1
        dc["tot"] += a.value
    return dc


def get_run_accounting(run, ctx):
    """Generate comprehensive accounting report for a run.

    Calculates revenue, costs, and balance for a run based on enabled features.
    Includes payments, expenses, inflows, outflows, refunds, tokens, and credits.

    Args:
        run: Run instance to generate accounting for
        ctx: Context dictionary with optional token/credit names

    Returns:
        dict: Complete accounting breakdown by category

    Side effects:
        Updates run.revenue, run.costs, run.balance, and run.tax fields
    """
    dc = {}
    features = get_event_features(run.event_id)

    s_expenses = 0
    if "expense" in features:
        dc["exp"] = get_acc_detail(
            _("Expenses"),
            run,
            _("Total of expenses submitted by collaborators and approved"),
            AccountingItemExpense,
            ExpenseChoices.choices,
            "exp",
        )
        s_expenses = dc["exp"]["tot"]

    s_outflows = 0
    if "outflow" in features:
        dc["out"] = get_acc_detail(
            _("Outflows"),
            run,
            _("Total of recorded money outflows"),
            AccountingItemOutflow,
            ExpenseChoices.choices,
            "exp",
        )
        s_outflows = dc["out"]["tot"]

    s_inflows = 0
    if "inflow" in features:
        dc["in"] = get_acc_detail(
            _("Inflows"), run, _("Total of recorded money inflows"), AccountingItemInflow, None, None
        )
        s_inflows = dc["in"]["tot"]

    s_payments = 0
    if "payment" in features:
        dc["pay"] = get_acc_detail(
            _("Income"),
            run,
            _("Total participation fees received"),
            AccountingItemPayment,
            PaymentChoices.choices,
            "pay",
            reg=True,
        )
        s_payments = dc["pay"]["tot"]

    dc["trs"] = get_acc_detail(
        _("Transactions"),
        run,
        _("Total amount withheld for transfer commissions"),
        AccountingItemTransaction,
        None,
        None,
        reg=True,
    )
    s_fees = dc["trs"]["tot"]

    s_refund = 0
    if "refund" in features:
        dc["ref"] = get_acc_detail(
            _("Refunds"),
            run,
            _("Total amount refunded to participants"),
            AccountingItemOther,
            OtherChoices.choices,
            "oth",
            filters={"cancellation__exact": True},
        )
        s_refund = dc["ref"]["tot"]

    s_credits = 0
    s_tokens = 0
    if "token_credit" in features:
        dc["tok"] = get_acc_detail(
            ctx.get("token_name", _("Tokens")),
            run,
            _("Total issued"),
            AccountingItemOther,
            OtherChoices.choices,
            "oth",
            filters={"cancellation__exact": False, "oth__exact": OtherChoices.TOKEN},
        )
        s_tokens = dc["tok"]["tot"]
        dc["cre"] = get_acc_detail(
            ctx.get("credit_name", _("Credits")),
            run,
            _("Total issued"),
            AccountingItemOther,
            OtherChoices.choices,
            "oth",
            filters={
                "cancellation__exact": False,
                "oth__exact": OtherChoices.CREDIT,
            },
        )
        s_credits = dc["cre"]["tot"]

    if "discount" in features:
        dc["dis"] = get_acc_detail(
            _("Discount"),
            run,
            _("Total participation fees reduced through discounts"),
            AccountingItemDiscount,
            None,
            None,
        )

    dc["reg"] = get_acc_reg_detail(
        _("Registrations"), run, _("Theoretical total of income due to participation fees selected by the participants")
    )

    run.revenue = s_payments + s_inflows - (s_fees + s_refund)
    run.costs = s_outflows + s_expenses + s_tokens + s_credits
    run.balance = run.revenue - run.costs

    if "organization_tax" in features:
        tax = int(run.event.assoc.get_config("organization_tax_perc", "10"))
        run.tax = run.revenue * tax / 100

    run.save()

    return dc


def check_accounting(assoc_id):
    """Perform association-wide accounting check and record results.

    Args:
        assoc_id: Association ID to check accounting for

    Side effects:
        Creates RecordAccounting entry with global and bank sums
    """
    ctx = {"a_id": assoc_id}
    assoc_accounting(ctx)
    RecordAccounting.objects.create(assoc_id=assoc_id, global_sum=ctx["global_sum"], bank_sum=ctx["bank_sum"])


def check_run_accounting(run):
    """Perform run-specific accounting check and record results.

    Args:
        run: Run instance to check accounting for

    Side effects:
        Updates run accounting and creates RecordAccounting entry
    """
    get_run_accounting(run, {})
    # print(run)
    RecordAccounting.objects.create(assoc=run.event.assoc, run=run, global_sum=run.balance, bank_sum=0)


def assoc_accounting_data(ctx, year=None):
    """Gather association accounting data for a specific year or all time.

    Args:
        ctx: Context dictionary with association ID to update
        year: Optional year to filter data, if None uses all years

    Side effects:
        Updates ctx with various sum fields for inflows, outflows, payments, etc.
    """
    if year:
        s = date(year, 1, 1)
        e = date(year, 12, 31)
    else:
        s = date(1990, 1, 1)
        e = date(2990, 1, 1)

    ctx["outflow_exec_sum"] = get_sum(
        AccountingItemOutflow.objects.filter(run=None, assoc_id=ctx["a_id"], payment_date__gte=s, payment_date__lte=e)
    )
    ctx["inflow_exec_sum"] = get_sum(
        AccountingItemInflow.objects.filter(run=None, assoc_id=ctx["a_id"], payment_date__gte=s, payment_date__lte=e)
    )
    ctx["membership_sum"] = get_sum(
        AccountingItemMembership.objects.filter(assoc_id=ctx["a_id"], created__gte=s, created__lte=e)
    )
    ctx["donations_sum"] = get_sum(
        AccountingItemDonation.objects.filter(assoc_id=ctx["a_id"], created__gte=s, created__lte=e)
    )
    ctx["collections_sum"] = get_sum(
        AccountingItemCollection.objects.filter(assoc_id=ctx["a_id"], created__gte=s, created__lte=e)
    )

    ctx["inflow_sum"] = get_sum(
        AccountingItemInflow.objects.filter(assoc_id=ctx["a_id"], payment_date__gte=s, payment_date__lte=e)
    )
    ctx["outflow_sum"] = get_sum(
        AccountingItemOutflow.objects.filter(assoc_id=ctx["a_id"], payment_date__gte=s, payment_date__lte=e)
    )
    ctx["pay_money_sum"] = get_sum(
        AccountingItemPayment.objects.filter(
            pay=PaymentChoices.MONEY,
            assoc_id=ctx["a_id"],
            created__gte=s,
            created__lte=e,
        )
    )
    ctx["transactions_sum"] = get_sum(
        AccountingItemTransaction.objects.filter(assoc_id=ctx["a_id"], created__gte=s, created__lte=e)
    )
    ctx["refund_sum"] = get_sum(
        AccountingItemOther.objects.filter(
            oth=OtherChoices.REFUND,
            assoc_id=ctx["a_id"],
            created__gte=s,
            created__lte=e,
        )
    )

    ctx["in_sum"] = (
        ctx["inflow_sum"]
        + ctx["membership_sum"]
        + ctx["donations_sum"]
        + ctx["collections_sum"]
        + ctx["pay_money_sum"]
        - ctx["transactions_sum"]
    )
    ctx["out_sum"] = ctx["outflow_sum"] + ctx["refund_sum"]


def assoc_accounting(ctx):
    """Generate comprehensive association accounting summary.

    Calculates member balances, run balances, and overall financial position
    for an association across all years.

    Args:
        ctx: Context dictionary with association ID to update

    Side effects:
        Updates ctx with member lists, run lists, balance sums, and yearly data
        Sets global_sum and bank_sum for overall financial position
    """
    ctx.update({"list": [], "tokens_sum": 0, "credits_sum": 0, "balance_sum": 0})
    for el in (
        Membership.objects.filter(assoc_id=ctx["a_id"])
        .filter(~Q(tokens=Decimal(0)) | ~Q(credit=Decimal(0)))
        .select_related("member")
        .order_by("-credit", "-tokens")
    ):
        mb = el.member
        mb.credit = el.credit
        mb.tokens = el.tokens
        ctx["list"].append(mb)
        ctx["tokens_sum"] += el.tokens
        ctx["credits_sum"] += el.credit
    ctx["runs"] = (
        Run.objects.filter(event__assoc_id=ctx["a_id"])
        .exclude(development=DevelopStatus.START)
        .exclude(development=DevelopStatus.CANC)
        .select_related("event")
        .order_by("-end")
    )
    for el in ctx["runs"]:
        if el.development == DevelopStatus.DONE:
            ctx["balance_sum"] += el.balance

    assoc_accounting_data(ctx)

    ctx["global_sum"] = (ctx["balance_sum"] + ctx["membership_sum"] + ctx["donations_sum"] + ctx["inflow_exec_sum"]) - (
        ctx["outflow_exec_sum"] + ctx["tokens_sum"]
    )
    ctx["bank_sum"] = (ctx["pay_money_sum"] + ctx["membership_sum"] + ctx["donations_sum"] + ctx["inflow_sum"]) - (
        ctx["outflow_sum"] + ctx["transactions_sum"] + ctx["refund_sum"]
    )

    # for every year, from the start
    assoc = Association.objects.get(pk=ctx["a_id"])
    s_year = int(assoc.created.year)
    e_year = int(datetime.now().date().year)
    ctx["sum_year"] = {}
    while s_year <= e_year:
        ctx["sum_year"][s_year] = 1
        s_year += 1
