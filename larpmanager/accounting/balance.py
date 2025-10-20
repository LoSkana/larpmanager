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

import logging
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.registration import get_display_choice
from larpmanager.cache.config import get_assoc_config
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

logger = logging.getLogger(__name__)


def get_acc_detail(
    nm: str, run: Run, descr: str, cls, cho, typ: str | None, filters: dict | None = None, reg: bool = False
) -> dict:
    """Get detailed accounting breakdown for a specific accounting item type.

    Analyzes accounting items for a given run and provides aggregated statistics
    including totals, counts, and detailed breakdowns by specified type field.

    Args:
        nm: Display name for the accounting category
        run: Run instance to filter accounting items
        descr: Description of the accounting category
        cls: Model class for accounting items (e.g., AccountingItemPayment)
        cho: Choices enumeration for display names
        typ: Field name to group items by (e.g., 'pay', 'exp'). None to skip grouping
        filters: Optional additional filters to apply to queryset
        reg: If True, filter by reg__run instead of run

    Returns:
        Dictionary containing:
            - tot: Total value sum across all items
            - num: Total count of items
            - detail: Breakdown by type with individual totals and counts
            - name: Display name for the category
            - descr: Category description
    """
    # Initialize result dictionary with base structure
    dc = {"tot": 0, "num": 0, "detail": {}, "name": nm, "descr": descr}

    # Build queryset based on reg parameter
    if reg:
        lst = cls.objects.filter(reg__run=run)
    else:
        lst = cls.objects.filter(run=run)

    # Apply additional filters if provided
    if filters:
        lst = lst.filter(**filters)

    # Process each accounting item
    for a in lst:
        # Update overall totals
        dc["num"] += 1
        dc["tot"] += a.value

        # Skip type-based grouping if typ is None
        if typ is None:
            continue

        # Get type value and initialize detail entry if needed
        tp = getattr(a, typ)
        if tp not in dc["detail"]:
            dc["detail"][tp] = {"tot": 0, "num": 0, "name": get_display_choice(cho, tp)}

        # Update type-specific totals
        dc["detail"][tp]["num"] += 1
        dc["detail"][tp]["tot"] += a.value

    return dc


def get_acc_reg_type(el) -> tuple[str, str]:
    """Determine registration type for accounting categorization.

    Analyzes a registration instance to categorize it for accounting purposes.
    Returns appropriate type codes and display names based on cancellation status
    and ticket tier information.

    Args:
        el: Registration instance to categorize. Must have cancellation_date
            and ticket attributes.

    Returns:
        tuple[str, str]: A tuple containing:
            - type_code: Short code identifying the registration type
            - display_name: Human-readable name for the registration type
    """
    # Check if registration has been cancelled
    if el.cancellation_date:
        return "can", "Disdetta"

    # Return empty values if no ticket is associated
    if not el.ticket:
        return "", ""

    # Extract tier information from ticket and get display name
    return (
        el.ticket.tier,
        get_display_choice(TicketTier.choices, el.ticket.tier),
    )


def get_acc_reg_detail(nm: str, run, descr: str) -> dict:
    """Get detailed registration accounting breakdown by ticket tier.

    Analyzes all non-cancelled registrations for a given run and provides
    a comprehensive breakdown by ticket type, including totals and counts.

    Args:
        nm: Display name for the accounting category
        run: Run instance to get registrations for
        descr: Description of the accounting category

    Returns:
        Dictionary containing:
            - tot: Total amount across all registrations
            - num: Total number of registrations
            - detail: Breakdown by ticket type with individual totals/counts
            - name: Display name passed as parameter
            - descr: Description passed as parameter
    """
    # Initialize result dictionary with base structure
    dc = {"tot": 0, "num": 0, "detail": {}, "name": nm, "descr": descr}

    # Query all non-cancelled registrations for the run with ticket data
    registrations = Registration.objects.filter(run=run).select_related("ticket").filter(cancellation_date__isnull=True)

    # Process each registration to build breakdown by ticket type
    for reg in registrations:
        # Get ticket type and description for this registration
        (tp, descr) = get_acc_reg_type(reg)

        # Initialize ticket type entry if not exists
        if tp not in dc["detail"]:
            dc["detail"][tp] = {"tot": 0, "num": 0, "name": descr}

        # Update ticket type counters
        dc["detail"][tp]["num"] += 1
        dc["detail"][tp]["tot"] += reg.tot_iscr

        # Update overall counters
        dc["num"] += 1
        dc["tot"] += reg.tot_iscr

    return dc


def get_token_details(nm: str, run) -> dict:
    """Get token accounting details for a run.

    Calculates the total value and count of accounting items for a specific run,
    returning a summary dictionary with totals, counts, and metadata.

    Args:
        nm (str): Display name for the token category
        run: Run instance to get token details for

    Returns:
        dict: Dictionary containing:
            - tot (int): Total value of all accounting items
            - num (int): Number of accounting items
            - detail (dict): Empty detail dictionary for future use
            - name (str): Display name for the category
    """
    # Initialize result dictionary with default values
    dc = {"tot": 0, "num": 0, "detail": {}, "name": nm}

    # Iterate through all accounting items for the given run
    for a in AccountingItemOther.objects.filter(run=run):
        # Increment item count
        dc["num"] += 1
        # Add item value to total
        dc["tot"] += a.value

    return dc


def get_run_accounting(run: Run, ctx: dict, perform_update: bool = True) -> dict:
    """Generate comprehensive accounting report for a run.

    Calculates revenue, costs, and balance for a run based on enabled features.
    Includes payments, expenses, inflows, outflows, refunds, tokens, and credits.
    The function aggregates various accounting items and updates the run's financial fields.

    Args:
        run: Run instance to generate accounting for
        ctx: Context dictionary with optional token/credit names (e.g., 'token_name', 'credit_name')
        perform_update: Whether to update the run with new financial data

    Returns:
        dict: Complete accounting breakdown by category. Keys may include:
            - 'exp': Expenses breakdown
            - 'out': Outflows breakdown
            - 'in': Inflows breakdown
            - 'pay': Payments breakdown
            - 'trs': Transactions breakdown
            - 'ref': Refunds breakdown
            - 'tok': Tokens breakdown
            - 'cre': Credits breakdown
            - 'dis': Discounts breakdown
            - 'reg': Registrations breakdown

    Side effects:
        Updates run.revenue, run.costs, run.balance, and run.tax fields and saves the run
    """
    dc = {}
    # Fetch feature flags to determine which accounting categories are enabled for this event
    features = get_event_features(run.event_id)

    # Process expenses: accumulate all approved expenses submitted by collaborators
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

    # Process outflows: accumulate all recorded money outflows
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

    # Process inflows: accumulate all recorded money inflows
    s_inflows = 0
    if "inflow" in features:
        dc["in"] = get_acc_detail(
            _("Inflows"), run, _("Total of recorded money inflows"), AccountingItemInflow, None, None
        )
        s_inflows = dc["in"]["tot"]

    # Process payments: accumulate all participation fees received from registrations
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

    # Process transaction fees: accumulate all transfer commissions withheld
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

    # Process refunds: accumulate all amounts refunded to participants for cancellations
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

    # Process tokens and credits: accumulate all issued tokens and credits
    s_credits = 0
    s_tokens = 0
    if "token_credit" in features:
        # Tokens are virtual currency issued to members
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

        # Credits are similar to tokens but distinct in accounting
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

    # Process discounts: accumulate all participation fee reductions
    if "discount" in features:
        dc["dis"] = get_acc_detail(
            _("Discount"),
            run,
            _("Total participation fees reduced through discounts"),
            AccountingItemDiscount,
            None,
            None,
        )

    # Process registrations: get theoretical total based on selected ticket tiers
    dc["reg"] = get_acc_reg_detail(
        _("Registrations"), run, _("Theoretical total of income due to participation fees selected by the participants")
    )

    # Calculate final financial figures
    # Revenue = payments received + inflows - (transaction fees + refunds)
    run.revenue = s_payments + s_inflows - (s_fees + s_refund)
    # Costs = outflows + expenses + virtual currency issued (tokens + credits)
    run.costs = s_outflows + s_expenses + s_tokens + s_credits
    # Balance = net profit or loss
    run.balance = run.revenue - run.costs

    # Apply organization tax if enabled
    if "organization_tax" in features:
        tax = int(get_assoc_config(run.event.assoc_id, "organization_tax_perc", "10"))
        run.tax = run.revenue * tax / 100

    # Persist the calculated financial data
    if perform_update:
        run.save()

    return dc


def check_accounting(assoc_id: int) -> None:
    """Perform association-wide accounting check and record results.

    This function executes an accounting verification for the specified association
    and persists the calculated financial totals to the database.

    Args:
        assoc_id (int): The unique identifier of the association to check accounting for.

    Returns:
        None

    Side Effects:
        Creates a new RecordAccounting entry in the database containing the
        calculated global_sum and bank_sum values for the association.
    """
    # Initialize context dictionary with association ID for accounting calculation
    ctx = {"a_id": assoc_id}

    # Execute association accounting calculation, populating ctx with financial sums
    assoc_accounting(ctx)

    # Persist accounting results to database via RecordAccounting model
    RecordAccounting.objects.create(assoc_id=assoc_id, global_sum=ctx["global_sum"], bank_sum=ctx["bank_sum"])


def check_run_accounting(run: Run) -> None:
    """Perform run-specific accounting check and record results.

    This function performs accounting calculations for a specific run and records
    the results in the database for audit purposes.

    Args:
        run: Run instance to check accounting for. Must have an associated event
             with an organization (assoc).

    Returns:
        None

    Side Effects:
        - Updates run accounting calculations via get_run_accounting
        - Creates a new RecordAccounting entry in the database
    """
    # Perform accounting calculations and update run balance
    get_run_accounting(run, {})

    # Log the accounting operation for debugging
    logger.debug(f"Recording accounting for run: {run}")

    # Create audit record with current balance (bank_sum set to 0 as default)
    RecordAccounting.objects.create(assoc=run.event.assoc, run=run, global_sum=run.balance, bank_sum=0)


def assoc_accounting_data(ctx: dict, year: int | None = None) -> None:
    """Gather association accounting data for a specific year or all time.

    Aggregates all monetary flows (inflows, outflows, memberships, donations, etc.)
    for an association and populates the context dictionary with the sums.

    Args:
        ctx: Context dictionary with 'a_id' (association ID) key. Will be updated
             with sum fields for various accounting categories
        year: Optional year to filter data. If None, uses all years (1990-2990)

    Side effects:
        Updates ctx with the following keys:
        - outflow_exec_sum: Executive outflows sum
        - inflow_exec_sum: Executive inflows sum
        - membership_sum: Total membership fees
        - donations_sum: Total donations
        - collections_sum: Total collections
        - inflow_sum: Total inflows
        - outflow_sum: Total outflows
        - pay_money_sum: Total cash payments
        - transactions_sum: Total transaction fees
        - refund_sum: Total refunds
        - in_sum: Total incoming money
        - out_sum: Total outgoing money
    """
    # Determine the date range for filtering accounting records
    if year:
        s = date(year, 1, 1)
        e = date(year, 12, 31)
    else:
        # Use a very wide range to capture all records
        s = date(1990, 1, 1)
        e = date(2990, 1, 1)

    # Calculate executive-level outflows (not associated with any specific run)
    ctx["outflow_exec_sum"] = get_sum(
        AccountingItemOutflow.objects.filter(run=None, assoc_id=ctx["a_id"], payment_date__gte=s, payment_date__lte=e)
    )
    # Calculate executive-level inflows (not associated with any specific run)
    ctx["inflow_exec_sum"] = get_sum(
        AccountingItemInflow.objects.filter(run=None, assoc_id=ctx["a_id"], payment_date__gte=s, payment_date__lte=e)
    )

    # Calculate membership fees collected
    ctx["membership_sum"] = get_sum(
        AccountingItemMembership.objects.filter(assoc_id=ctx["a_id"], created__gte=s, created__lte=e)
    )
    # Calculate donations received
    ctx["donations_sum"] = get_sum(
        AccountingItemDonation.objects.filter(assoc_id=ctx["a_id"], created__gte=s, created__lte=e)
    )
    # Calculate collections (gifts/prepaid credits) received
    ctx["collections_sum"] = get_sum(
        AccountingItemCollection.objects.filter(assoc_id=ctx["a_id"], created__gte=s, created__lte=e)
    )

    # Calculate all inflows for the association
    ctx["inflow_sum"] = get_sum(
        AccountingItemInflow.objects.filter(assoc_id=ctx["a_id"], payment_date__gte=s, payment_date__lte=e)
    )
    # Calculate all outflows for the association
    ctx["outflow_sum"] = get_sum(
        AccountingItemOutflow.objects.filter(assoc_id=ctx["a_id"], payment_date__gte=s, payment_date__lte=e)
    )

    # Calculate cash payments received (excluding online/bank transfers)
    ctx["pay_money_sum"] = get_sum(
        AccountingItemPayment.objects.filter(
            pay=PaymentChoices.MONEY,
            assoc_id=ctx["a_id"],
            created__gte=s,
            created__lte=e,
        )
    )
    # Calculate transaction fees charged by payment processors
    ctx["transactions_sum"] = get_sum(
        AccountingItemTransaction.objects.filter(assoc_id=ctx["a_id"], created__gte=s, created__lte=e)
    )
    # Calculate total refunds issued
    ctx["refund_sum"] = get_sum(
        AccountingItemOther.objects.filter(
            oth=OtherChoices.REFUND,
            assoc_id=ctx["a_id"],
            created__gte=s,
            created__lte=e,
        )
    )

    # Calculate net incoming and outgoing sums
    ctx["in_sum"] = (
        ctx["inflow_sum"]
        + ctx["membership_sum"]
        + ctx["donations_sum"]
        + ctx["collections_sum"]
        + ctx["pay_money_sum"]
        - ctx["transactions_sum"]
    )
    ctx["out_sum"] = ctx["outflow_sum"] + ctx["refund_sum"]


def assoc_accounting(ctx: dict) -> None:
    """Generate comprehensive association accounting summary.

    Calculates member balances, run balances, and overall financial position
    for an association across all years. Aggregates tokens, credits, and monetary
    flows to provide a complete financial overview.

    Args:
        ctx: Context dictionary with 'a_id' (association ID) key

    Side effects:
        Updates ctx with the following keys:
        - list: List of members with non-zero tokens or credits
        - tokens_sum: Total tokens issued across all members
        - credits_sum: Total credits issued across all members
        - balance_sum: Sum of balances from all completed runs
        - runs: QuerySet of runs for the association
        - global_sum: Overall financial position
        - bank_sum: Bank account balance based on recorded transactions
        - sum_year: Dictionary mapping years to 1 (for year range)
        Plus all fields from assoc_accounting_data()
    """
    # Initialize member balance tracking
    ctx.update({"list": [], "tokens_sum": 0, "credits_sum": 0, "balance_sum": 0})

    # Gather all members with non-zero tokens or credits
    for el in (
        Membership.objects.filter(assoc_id=ctx["a_id"])
        .filter(~Q(tokens=Decimal(0)) | ~Q(credit=Decimal(0)))
        .select_related("member")
        .order_by("-credit", "-tokens")
    ):
        # Attach credit and token balance to member object for display
        mb = el.member
        mb.credit = el.credit
        mb.tokens = el.tokens
        ctx["list"].append(mb)

        # Accumulate total tokens and credits outstanding
        ctx["tokens_sum"] += el.tokens
        ctx["credits_sum"] += el.credit

    # Fetch all non-draft, non-cancelled runs for the association
    ctx["runs"] = (
        Run.objects.filter(event__assoc_id=ctx["a_id"])
        .exclude(development=DevelopStatus.START)
        .exclude(development=DevelopStatus.CANC)
        .select_related("event")
        .order_by("-end")
    )

    # Accumulate balance from all completed runs
    for el in ctx["runs"]:
        if el.development == DevelopStatus.DONE:
            ctx["balance_sum"] += el.balance

    # Fetch detailed accounting data (inflows, outflows, memberships, etc.)
    assoc_accounting_data(ctx)

    # Calculate global financial position
    # Global sum = (run balances + memberships + donations + exec inflows) - (exec outflows + tokens issued)
    ctx["global_sum"] = (ctx["balance_sum"] + ctx["membership_sum"] + ctx["donations_sum"] + ctx["inflow_exec_sum"]) - (
        ctx["outflow_exec_sum"] + ctx["tokens_sum"]
    )

    # Calculate bank balance based on actual money movements
    # Bank sum = (cash payments + memberships + donations + inflows) - (outflows + fees + refunds)
    ctx["bank_sum"] = (ctx["pay_money_sum"] + ctx["membership_sum"] + ctx["donations_sum"] + ctx["inflow_sum"]) - (
        ctx["outflow_sum"] + ctx["transactions_sum"] + ctx["refund_sum"]
    )

    # Build year range dictionary from association creation to current year
    assoc = Association.objects.only("created").get(pk=ctx["a_id"])
    s_year = int(assoc.created.year)
    e_year = int(datetime.now().date().year)
    ctx["sum_year"] = {}
    while s_year <= e_year:
        ctx["sum_year"][s_year] = 1
        s_year += 1
