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
    name: str,
    run,
    description: str,
    model_class,
    choices,
    type_field: str | None,
    filters: dict | None = None,
    filter_by_registration: bool = False,
) -> dict:
    """Get detailed accounting breakdown for a specific accounting item type.

    This function calculates totals, counts, and detailed breakdowns by type
    for accounting items associated with a specific run or registration.

    Args:
        name: Display name for the accounting category
        run: Run instance to filter accounting items
        description: Description of the accounting category
        model_class: Model class for accounting items (e.g., AccountingItemPayment)
        choices: Choices enumeration for display names
        type_field: Field name to group items by (e.g., 'pay', 'exp'). If None,
             no detailed breakdown is generated
        filters: Optional additional filters to apply to the queryset
        filter_by_registration: If True, filter by reg__run instead of run directly

    Returns:
        dict: Accounting breakdown containing:
            - tot: Total value sum
            - num: Total item count
            - detail: Dictionary with breakdown by type (if type_field provided)
            - name: Display name
            - descr: Description
    """
    # Initialize result dictionary with base structure
    result = {"tot": 0, "num": 0, "detail": {}, "name": name, "descr": description}

    # Filter accounting items by run or registration run
    if filter_by_registration:
        queryset = model_class.objects.filter(reg__run=run)
    else:
        queryset = model_class.objects.filter(run=run)

    # Apply additional filters if provided
    if filters:
        queryset = queryset.filter(**filters)

    # Process each accounting item
    for accounting_item in queryset:
        # Update global counters
        result["num"] += 1
        result["tot"] += accounting_item.value

        # Skip detailed breakdown if no type field specified
        if type_field is None:
            continue

        # Get type value and create detail entry if needed
        item_type = getattr(accounting_item, type_field)
        if item_type not in result["detail"]:
            result["detail"][item_type] = {
                "tot": 0,
                "num": 0,
                "name": get_display_choice(choices, item_type),
            }

        # Update type-specific counters
        result["detail"][item_type]["num"] += 1
        result["detail"][item_type]["tot"] += accounting_item.value

    return result


def get_acc_reg_type(registration) -> tuple[str, str]:
    """Determine registration type for accounting categorization.

    Analyzes a registration instance to categorize it for accounting purposes.
    Returns appropriate type codes and display names based on cancellation status
    and ticket tier information.

    Args:
        registration: Registration instance to categorize. Must have cancellation_date
            and ticket attributes.

    Returns:
        tuple[str, str]: A tuple containing:
            - type_code: Short code identifying the registration type
            - display_name: Human-readable name for the registration type
    """
    # Check if registration has been cancelled
    if registration.cancellation_date:
        return "can", "Disdetta"

    # Return empty values if no ticket is associated
    if not registration.ticket:
        return "", ""

    # Extract tier information from ticket and get display name
    return (
        registration.ticket.tier,
        get_display_choice(TicketTier.choices, registration.ticket.tier),
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
    accounting_data = {"tot": 0, "num": 0, "detail": {}, "name": nm, "descr": descr}

    # Query all non-cancelled registrations for the run with ticket data
    registrations = Registration.objects.filter(run=run).select_related("ticket").filter(cancellation_date__isnull=True)

    # Process each registration to build breakdown by ticket type
    for registration in registrations:
        # Get ticket type and description for this registration
        (ticket_type, ticket_description) = get_acc_reg_type(registration)

        # Initialize ticket type entry if not exists
        if ticket_type not in accounting_data["detail"]:
            accounting_data["detail"][ticket_type] = {"tot": 0, "num": 0, "name": ticket_description}

        # Update ticket type counters
        accounting_data["detail"][ticket_type]["num"] += 1
        accounting_data["detail"][ticket_type]["tot"] += registration.tot_iscr

        # Update overall counters
        accounting_data["num"] += 1
        accounting_data["tot"] += registration.tot_iscr

    return accounting_data


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


def get_run_accounting(run: Run, context: dict, perform_update: bool = True) -> dict:
    """Generate comprehensive accounting report for a run.

    Calculates revenue, costs, and balance for a run based on enabled features.
    Includes payments, expenses, inflows, outflows, refunds, tokens, and credits.
    The function aggregates various accounting items and updates the run's financial fields.

    Args:
        run: Run instance to generate accounting for
        context: Context dictionary with optional token/credit names (e.g., 'token_name', 'credit_name')
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
    details_by_category = {}
    # Fetch feature flags to determine which accounting categories are enabled for this event
    features = get_event_features(run.event_id)

    # Process expenses: accumulate all approved expenses submitted by collaborators
    sum_expenses = 0
    if "expense" in features:
        details_by_category["exp"] = get_acc_detail(
            _("Expenses"),
            run,
            _("Total of expenses submitted by collaborators and approved"),
            AccountingItemExpense,
            ExpenseChoices.choices,
            "exp",
        )
        sum_expenses = details_by_category["exp"]["tot"]

    # Process outflows: accumulate all recorded money outflows
    sum_outflows = 0
    if "outflow" in features:
        details_by_category["out"] = get_acc_detail(
            _("Outflows"),
            run,
            _("Total of recorded money outflows"),
            AccountingItemOutflow,
            ExpenseChoices.choices,
            "exp",
        )
        sum_outflows = details_by_category["out"]["tot"]

    # Process inflows: accumulate all recorded money inflows
    sum_inflows = 0
    if "inflow" in features:
        details_by_category["in"] = get_acc_detail(
            _("Inflows"), run, _("Total of recorded money inflows"), AccountingItemInflow, None, None
        )
        sum_inflows = details_by_category["in"]["tot"]

    # Process payments: accumulate all participation fees received from registrations
    sum_payments = 0
    if "payment" in features:
        details_by_category["pay"] = get_acc_detail(
            _("Income"),
            run,
            _("Total participation fees received"),
            AccountingItemPayment,
            PaymentChoices.choices,
            "pay",
            filter_by_registration=True,
        )
        sum_payments = details_by_category["pay"]["tot"]

    # Process transaction fees: accumulate all transfer commissions withheld
    details_by_category["trs"] = get_acc_detail(
        _("Transactions"),
        run,
        _("Total amount withheld for transfer commissions"),
        AccountingItemTransaction,
        None,
        None,
        filter_by_registration=True,
    )
    sum_fees = details_by_category["trs"]["tot"]

    # Process refunds: accumulate all amounts refunded to participants for cancellations
    sum_refund = 0
    if "refund" in features:
        details_by_category["ref"] = get_acc_detail(
            _("Refunds"),
            run,
            _("Total amount refunded to participants"),
            AccountingItemOther,
            OtherChoices.choices,
            "oth",
            filters={"cancellation__exact": True},
        )
        sum_refund = details_by_category["ref"]["tot"]

    # Process tokens and credits: accumulate all issued tokens and credits
    sum_credits = 0
    sum_tokens = 0
    if "token_credit" in features:
        # Tokens are virtual currency issued to members
        details_by_category["tok"] = get_acc_detail(
            context.get("token_name", _("Tokens")),
            run,
            _("Total issued"),
            AccountingItemOther,
            OtherChoices.choices,
            "oth",
            filters={"cancellation__exact": False, "oth__exact": OtherChoices.TOKEN},
        )
        sum_tokens = details_by_category["tok"]["tot"]

        # Credits are similar to tokens but distinct in accounting
        details_by_category["cre"] = get_acc_detail(
            context.get("credit_name", _("Credits")),
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
        sum_credits = details_by_category["cre"]["tot"]

    # Process discounts: accumulate all participation fee reductions
    if "discount" in features:
        details_by_category["dis"] = get_acc_detail(
            _("Discount"),
            run,
            _("Total participation fees reduced through discounts"),
            AccountingItemDiscount,
            None,
            None,
        )

    # Process registrations: get theoretical total based on selected ticket tiers
    details_by_category["reg"] = get_acc_reg_detail(
        _("Registrations"), run, _("Theoretical total of income due to participation fees selected by the participants")
    )

    # Calculate final financial figures
    # Revenue = payments received + inflows - (transaction fees + refunds)
    run.revenue = sum_payments + sum_inflows - (sum_fees + sum_refund)
    # Costs = outflows + expenses + virtual currency issued (tokens + credits)
    run.costs = sum_outflows + sum_expenses + sum_tokens + sum_credits
    # Balance = net profit or loss
    run.balance = run.revenue - run.costs

    # Apply organization tax if enabled
    if "organization_tax" in features:
        tax_percentage = int(get_assoc_config(run.event.assoc_id, "organization_tax_perc", "10"))
        run.tax = run.revenue * tax_percentage / 100

    # Persist the calculated financial data
    if perform_update:
        run.save()

    return details_by_category


def check_accounting(association_id: int) -> None:
    """Perform association-wide accounting check and record results.

    This function executes an accounting verification for the specified association
    and persists the calculated financial totals to the database.

    Args:
        association_id (int): The unique identifier of the association to check accounting for.

    Returns:
        None

    Side Effects:
        Creates a new RecordAccounting entry in the database containing the
        calculated global_sum and bank_sum values for the association.
    """
    # Initialize context dictionary with association ID for accounting calculation
    context = {"association_id": association_id}

    # Execute association accounting calculation, populating context with financial sums
    assoc_accounting(context)

    # Persist accounting results to database via RecordAccounting model
    RecordAccounting.objects.create(
        assoc_id=association_id, global_sum=context["global_sum"], bank_sum=context["bank_sum"]
    )


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


def assoc_accounting_data(context: dict, year: int | None = None) -> None:
    """Gather association accounting data for a specific year or all time.

    Aggregates all monetary flows (inflows, outflows, memberships, donations, etc.)
    for an association and populates the context dictionary with the sums.

    Args:
        context: Context dictionary with 'a_id' (association ID) key. Will be updated
             with sum fields for various accounting categories
        year: Optional year to filter data. If None, uses all years (1990-2990)

    Side effects:
        Updates context with the following keys:
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
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
    else:
        # Use a very wide range to capture all records
        start_date = date(1990, 1, 1)
        end_date = date(2990, 1, 1)

    # Calculate executive-level outflows (not associated with any specific run)
    context["outflow_exec_sum"] = get_sum(
        AccountingItemOutflow.objects.filter(
            run=None, assoc_id=context["association_id"], payment_date__gte=start_date, payment_date__lte=end_date
        )
    )
    # Calculate executive-level inflows (not associated with any specific run)
    context["inflow_exec_sum"] = get_sum(
        AccountingItemInflow.objects.filter(
            run=None, assoc_id=context["association_id"], payment_date__gte=start_date, payment_date__lte=end_date
        )
    )

    # Calculate membership fees collected
    context["membership_sum"] = get_sum(
        AccountingItemMembership.objects.filter(
            assoc_id=context["association_id"], created__gte=start_date, created__lte=end_date
        )
    )
    # Calculate donations received
    context["donations_sum"] = get_sum(
        AccountingItemDonation.objects.filter(
            assoc_id=context["association_id"], created__gte=start_date, created__lte=end_date
        )
    )
    # Calculate collections (gifts/prepaid credits) received
    context["collections_sum"] = get_sum(
        AccountingItemCollection.objects.filter(
            assoc_id=context["association_id"], created__gte=start_date, created__lte=end_date
        )
    )

    # Calculate all inflows for the association
    context["inflow_sum"] = get_sum(
        AccountingItemInflow.objects.filter(
            assoc_id=context["association_id"], payment_date__gte=start_date, payment_date__lte=end_date
        )
    )
    # Calculate all outflows for the association
    context["outflow_sum"] = get_sum(
        AccountingItemOutflow.objects.filter(
            assoc_id=context["association_id"], payment_date__gte=start_date, payment_date__lte=end_date
        )
    )

    # Calculate cash payments received (excluding online/bank transfers)
    context["pay_money_sum"] = get_sum(
        AccountingItemPayment.objects.filter(
            pay=PaymentChoices.MONEY,
            assoc_id=context["association_id"],
            created__gte=start_date,
            created__lte=end_date,
        )
    )
    # Calculate transaction fees charged by payment processors
    context["transactions_sum"] = get_sum(
        AccountingItemTransaction.objects.filter(
            assoc_id=context["association_id"], created__gte=start_date, created__lte=end_date
        )
    )
    # Calculate total refunds issued
    context["refund_sum"] = get_sum(
        AccountingItemOther.objects.filter(
            oth=OtherChoices.REFUND,
            assoc_id=context["association_id"],
            created__gte=start_date,
            created__lte=end_date,
        )
    )

    # Calculate net incoming and outgoing sums
    context["in_sum"] = (
        context["inflow_sum"]
        + context["membership_sum"]
        + context["donations_sum"]
        + context["collections_sum"]
        + context["pay_money_sum"]
        - context["transactions_sum"]
    )
    context["out_sum"] = context["outflow_sum"] + context["refund_sum"]


def assoc_accounting(context: dict) -> None:
    """Generate comprehensive association accounting summary.

    Calculates member balances, run balances, and overall financial position
    for an association across all years. Aggregates tokens, credits, and monetary
    flows to provide a complete financial overview.

    Args:
        context: Context dictionary with 'a_id' (association ID) key

    Side effects:
        Updates context with the following keys:
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
    context.update({"list": [], "tokens_sum": 0, "credits_sum": 0, "balance_sum": 0})

    # Gather all members with non-zero tokens or credits
    for membership in (
        Membership.objects.filter(assoc_id=context["association_id"])
        .filter(~Q(tokens=Decimal(0)) | ~Q(credit=Decimal(0)))
        .select_related("member")
        .order_by("-credit", "-tokens")
    ):
        # Attach credit and token balance to member object for display
        member = membership.member
        member.credit = membership.credit
        member.tokens = membership.tokens
        context["list"].append(member)

        # Accumulate total tokens and credits outstanding
        context["tokens_sum"] += membership.tokens
        context["credits_sum"] += membership.credit

    # Fetch all non-draft, non-cancelled runs for the association
    context["runs"] = (
        Run.objects.filter(event__assoc_id=context["association_id"])
        .exclude(development=DevelopStatus.START)
        .exclude(development=DevelopStatus.CANC)
        .select_related("event")
        .order_by("-end")
    )

    # Accumulate balance from all completed runs
    for run in context["runs"]:
        if run.development == DevelopStatus.DONE:
            context["balance_sum"] += run.balance

    # Fetch detailed accounting data (inflows, outflows, memberships, etc.)
    assoc_accounting_data(context)

    # Calculate global financial position
    # Global sum = (run balances + memberships + donations + exec inflows) - (exec outflows + tokens issued)
    context["global_sum"] = (
        context["balance_sum"] + context["membership_sum"] + context["donations_sum"] + context["inflow_exec_sum"]
    ) - (context["outflow_exec_sum"] + context["tokens_sum"])

    # Calculate bank balance based on actual money movements
    # Bank sum = (cash payments + memberships + donations + inflows) - (outflows + fees + refunds)
    context["bank_sum"] = (
        context["pay_money_sum"] + context["membership_sum"] + context["donations_sum"] + context["inflow_sum"]
    ) - (context["outflow_sum"] + context["transactions_sum"] + context["refund_sum"])

    # Build year range dictionary from association creation to current year
    association = Association.objects.only("created").get(pk=context["association_id"])
    start_year = int(association.created.year)
    end_year = int(datetime.now().date().year)
    context["sum_year"] = {}
    while start_year <= end_year:
        context["sum_year"][start_year] = 1
        start_year += 1
