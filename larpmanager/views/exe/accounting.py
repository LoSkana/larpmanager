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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.balance import assoc_accounting, assoc_accounting_data, check_accounting, get_run_accounting
from larpmanager.accounting.invoice import invoice_verify
from larpmanager.cache.role import check_assoc_permission
from larpmanager.forms.accounting import (
    ExeCollectionForm,
    ExeCreditForm,
    ExeDonationForm,
    ExeExpenseForm,
    ExeInflowForm,
    ExeInvoiceForm,
    ExeOutflowForm,
    ExePaymentForm,
    ExeRefundRequestForm,
    ExeTokenForm,
)
from larpmanager.forms.writing import UploadElementsForm
from larpmanager.models.accounting import (
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemInflow,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemOutflow,
    AccountingItemPayment,
    AccountingItemTransaction,
    BalanceChoices,
    Collection,
    OtherChoices,
    PaymentChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
    RecordAccounting,
    RefundRequest,
    RefundStatus,
)
from larpmanager.models.association import Association
from larpmanager.models.event import Run
from larpmanager.models.registration import Registration
from larpmanager.models.utils import get_sum
from larpmanager.templatetags.show_tags import format_decimal
from larpmanager.utils.edit import backend_get, exe_edit
from larpmanager.utils.paginate import exe_paginate


@login_required
def exe_outflows(request: HttpRequest) -> HttpResponse:
    """Display paginated list of accounting outflows for association.

    This view function retrieves and displays a paginated list of accounting outflows
    for the current association. It requires proper association permissions and
    configures field display with custom callbacks for formatting.

    Parameters
    ----------
    request : HttpRequest
        Django HTTP request object containing user authentication and session data.
        Must be from an authenticated user with appropriate association permissions.

    Returns
    -------
    HttpResponse
        Rendered HTTP response containing the outflows list template with pagination
        and configured field display options.

    Notes
    -----
    The function uses exe_paginate for consistent pagination behavior and applies
    custom formatting callbacks for statement downloads and expense type display.
    """
    # Check user permissions and get base context for association
    context = check_assoc_permission(request, "exe_outflows")

    # Configure context with field definitions and display options
    context.update(
        {
            # Define related fields for efficient database queries
            "selrel": ("run", "run__event"),
            # Configure visible fields with localized headers
            "fields": [
                ("run", _("Event")),
                ("type", _("Type")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("payment_date", _("Date")),
                ("statement", _("Statement")),
            ],
            # Define custom display callbacks for specific fields
            "callbacks": {
                "statement": lambda el: f"<a href='{el.download()}'>Download</a>",
                "type": lambda el: el.get_exp_display(),
            },
        }
    )

    # Return paginated view with configured context and template
    return exe_paginate(
        request, context, AccountingItemOutflow, "larpmanager/exe/accounting/outflows.html", "exe_outflows_edit"
    )


@login_required
def exe_outflows_edit(request: HttpRequest, num: int) -> HttpResponse:
    """Edit accounting outflow record.

    Args:
        request: Django HTTP request object containing user authentication
                and form data for editing the outflow record
        num: Primary key identifier of the outflow record to edit

    Returns:
        HttpResponse: Rendered edit form on GET request or redirect
                     to outflows list on successful POST save

    Raises:
        Http404: If outflow record with given ID does not exist
        PermissionDenied: If user lacks permission to edit outflows
    """
    # Delegate to generic edit handler with outflow-specific form and redirect
    return exe_edit(request, ExeOutflowForm, num, "exe_outflows")


@login_required
def exe_inflows(request: HttpRequest) -> HttpResponse:
    """Display paginated list of accounting inflows for association.

    Args:
        request: Django HTTP request object. Must be authenticated and have
            appropriate association permissions for viewing accounting inflows.

    Returns:
        HttpResponse: Rendered template response containing paginated list of
            accounting inflows with download links for statements.

    Raises:
        PermissionDenied: If user lacks required association permissions.
    """
    # Check user permissions for association accounting inflows access
    context = check_assoc_permission(request, "exe_inflows")

    # Configure pagination context with related field optimization
    # and display field definitions for inflow data
    context.update(
        {
            # Optimize database queries by selecting related event data
            "selrel": ("run", "run__event"),
            # Define display fields with localized headers
            "fields": [
                ("run", _("Event")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("payment_date", _("Date")),
                ("statement", _("Statement")),
            ],
            # Configure custom rendering callbacks for special fields
            "callbacks": {
                "statement": lambda el: f"<a href='{el.download()}'>Download</a>",
            },
        }
    )

    # Render paginated inflows list with edit functionality
    return exe_paginate(
        request, context, AccountingItemInflow, "larpmanager/exe/accounting/inflows.html", "exe_inflows_edit"
    )


@login_required
def exe_inflows_edit(request, num):
    return exe_edit(request, ExeInflowForm, num, "exe_inflows")


@login_required
def exe_donations(request: HttpRequest) -> HttpResponse:
    """Display paginated list of donations for association.

    Renders a paginated table showing all donations made to the association,
    including member information, description, value, and creation date.

    Args:
        request (HttpRequest): Django HTTP request object. Must be from an
            authenticated user with appropriate association permissions.

    Returns:
        HttpResponse: Rendered template displaying the donations list with
            pagination controls and table headers for member, description,
            value, and date columns.

    Raises:
        PermissionDenied: If user lacks required association permissions.
    """
    # Check user has permission to view donations for this association
    context = check_assoc_permission(request, "exe_donations")

    # Define table column headers and their corresponding field names
    # These will be displayed in the donations list template
    context.update(
        {
            "fields": [
                ("member", _("Member")),  # Donation maker
                ("descr", _("Description")),  # Donation description/purpose
                ("value", _("Value")),  # Monetary amount
                ("created", _("Date")),  # When donation was created
            ],
        }
    )

    # Render paginated donations list using the accounting template
    return exe_paginate(
        request, context, AccountingItemDonation, "larpmanager/exe/accounting/donations.html", "exe_donations_edit"
    )


@login_required
def exe_donations_edit(request, num):
    return exe_edit(request, ExeDonationForm, num, "exe_donations")


@login_required
def exe_credits(request: HttpRequest) -> dict:
    """
    Display and manage credits for an association.

    This view function handles the display of accounting credits for an organization,
    providing a paginated list with filtering and editing capabilities.

    Args:
        request: The HTTP request object containing user session and parameters.

    Returns:
        dict: A dictionary containing the rendered HTML response with credits data
              and pagination controls.
    """
    # Check user permissions for credits management
    context = check_assoc_permission(request, "exe_credits")

    # Configure display context with relationship selections and field definitions
    context.update(
        {
            # Define related model fields for efficient database queries
            "selrel": ("run", "run__event"),
            "subtype": "credits",
            # Define table columns for credits display
            "fields": [
                ("member", _("Member")),
                ("run", _("Event")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("created", _("Date")),
            ],
        }
    )

    # Render paginated credits list with editing capabilities
    return exe_paginate(
        request, context, AccountingItemOther, "larpmanager/exe/accounting/credits.html", "exe_credits_edit"
    )


@login_required
def exe_credits_edit(request, num):
    return exe_edit(request, ExeCreditForm, num, "exe_credits")


@login_required
def exe_tokens(request: HttpRequest) -> HttpResponse:
    """
    Display paginated list of accounting tokens for organization executives.

    This view handles the display of token-based accounting items with filtering
    and pagination capabilities for organization-level administrators.

    Args:
        request: The HTTP request object containing user and session data.

    Returns:
        HttpResponse: Rendered template with paginated token data and context.

    Raises:
        PermissionDenied: If user lacks 'exe_tokens' permission for the association.
    """
    # Check user permissions for token management at organization level
    context = check_assoc_permission(request, "exe_tokens")

    # Configure context with table display settings and field definitions
    context.update(
        {
            # Define related field selections for optimized database queries
            "selrel": ("run", "run__event"),
            # Set subtype identifier for template rendering
            "subtype": "tokens",
            # Define table columns with localized headers
            "fields": [
                ("member", _("Member")),
                ("run", _("Event")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("created", _("Date")),
            ],
        }
    )
    # Render paginated view with AccountingItemOther model data
    return exe_paginate(
        request, context, AccountingItemOther, "larpmanager/exe/accounting/tokens.html", "exe_tokens_edit"
    )


@login_required
def exe_tokens_edit(request, num):
    return exe_edit(request, ExeTokenForm, num, "exe_tokens")


@login_required
def exe_expenses(request: HttpRequest) -> HttpResponse:
    """
    Handle expense management for organization executives.

    Displays a paginated list of accounting expense items with approval functionality.
    Only users with 'exe_expenses' permission can access this view.

    Args:
        request: HTTP request object containing user and session data

    Returns:
        HttpResponse: Rendered expenses page with paginated expense items
    """
    # Check user permissions for expense management
    context = check_assoc_permission(request, "exe_expenses")
    approve = _("Approve")

    # Configure table display settings and field definitions
    context.update(
        {
            # Define related field selection for optimization
            "selrel": ("run", "run__event"),
            # Define table columns with display names
            "fields": [
                ("member", _("Member")),
                ("type", _("Type")),
                ("run", _("Event")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("created", _("Date")),
                ("statement", _("Statement")),
                ("action", _("Action")),
            ],
            # Define custom rendering callbacks for specific fields
            "callbacks": {
                # Render statement as downloadable link
                "statement": lambda el: f"<a href='{el.download()}'>Download</a>",
                # Show approve button only for non-approved expenses
                "action": lambda el: f"<a href='{reverse('exe_expenses_approve', args=[el.id])}'>{approve}</a>"
                if not el.is_approved
                else "",
                # Display human-readable expense type
                "type": lambda el: el.get_exp_display(),
            },
        }
    )

    # Return paginated expense list with edit functionality
    return exe_paginate(
        request, context, AccountingItemExpense, "larpmanager/exe/accounting/expenses.html", "exe_expenses_edit"
    )


@login_required
def exe_expenses_edit(request, num):
    return exe_edit(request, ExeExpenseForm, num, "exe_expenses")


@login_required
def exe_expenses_approve(request: HttpRequest, num: str) -> HttpResponse:
    """Approve an expense request for the current organization.

    Args:
        request: The HTTP request object containing user and organization context
        num: The primary key identifier of the expense to approve

    Returns:
        HttpResponse: Redirect to the expenses list page

    Raises:
        Http404: If expense doesn't exist or doesn't belong to current organization
    """
    # Check user has permission to manage expenses
    context = check_assoc_permission(request, "exe_expenses")

    # Retrieve the expense object, raise 404 if not found
    try:
        exp = AccountingItemExpense.objects.get(pk=num)
    except Exception as err:
        raise Http404("no id expense") from err

    # Verify expense belongs to current organization
    if exp.assoc_id != context["association_id"]:
        raise Http404("not your orga")

    # Mark expense as approved and save changes
    exp.is_approved = True
    exp.save()

    # Show success message and redirect to expenses list
    messages.success(request, _("Request approved"))
    return redirect("exe_expenses")


@login_required
def exe_payments(request: HttpRequest) -> HttpResponse:
    """Display paginated list of accounting payments for organization executives.

    Shows payment records with configurable fields including member info, payment method,
    type, status, event details, amounts, and VAT information (if VAT feature enabled).

    Args:
        request: Django HTTP request object containing user session and parameters

    Returns:
        HttpResponse: Rendered template with paginated payment data and context
    """
    # Check user permissions for accessing payments section
    context = check_assoc_permission(request, "exe_payments")

    # Define base fields to display in payments table
    fields = [
        ("member", _("Member")),
        ("method", _("Method")),
        ("type", _("Type")),
        ("status", _("Status")),
        ("run", _("Event")),
        ("net", _("Net")),
        ("trans", _("Fee")),
        ("created", _("Date")),
        ("info", _("Info")),
    ]

    # Add VAT-related fields if VAT feature is enabled for this organization
    if "vat" in context["features"]:
        fields.append(("vat_ticket", _("VAT (Ticket)")))
        fields.append(("vat_options", _("VAT (Options)")))

    # Configure pagination context with field definitions and data callbacks
    context.update(
        {
            "selrel": ("reg__member", "reg__run", "inv", "inv__method"),  # Related fields to select
            "afield": "reg",  # Main field for filtering
            "fields": fields,  # Table column definitions
            # Callbacks for formatting display values in each column
            "callbacks": {
                "run": lambda row: str(row.reg.run) if row.reg and row.reg.run else "",
                "method": lambda el: str(el.inv.method) if el.inv else "",
                "type": lambda el: el.get_pay_display(),
                "status": lambda el: el.inv.get_status_display() if el.inv else "",
                "net": lambda el: format_decimal(el.net),
                "trans": lambda el: format_decimal(el.trans) if el.trans else "",
            },
        }
    )

    # Return paginated view of AccountingItemPayment records
    return exe_paginate(
        request, context, AccountingItemPayment, "larpmanager/exe/accounting/payments.html", "exe_payments_edit"
    )


@login_required
def exe_payments_edit(request, num):
    return exe_edit(request, ExePaymentForm, num, "exe_payments")


@login_required
def exe_invoices(request) -> HttpResponse:
    """Display and manage payment invoices for the organization.

    This view provides a paginated list of payment invoices with filtering
    and confirmation capabilities for submitted invoices.

    Args:
        request: HTTP request object containing user and session data

    Returns:
        HttpResponse: Rendered template with invoice list and pagination
    """
    # Check user permissions for invoice management
    context = check_assoc_permission(request, "exe_invoices")
    confirm = _("Confirm")

    # Update context with table configuration
    context.update(
        {
            # Define selectable relationships for filtering
            "selrel": ("method", "member"),
            # Define table columns and headers
            "fields": [
                ("member", _("Member")),
                ("method", _("Method")),
                ("type", _("Type")),
                ("status", _("Status")),
                ("gross", _("Gross")),
                ("trans", _("Transaction")),
                ("causal", _("Causal")),
                ("details", _("Details")),
                ("created", _("Date")),
                ("action", _("Action")),
            ],
            # Define data formatting callbacks for each column
            "callbacks": {
                # Display payment method as string
                "method": lambda el: str(el.method),
                # Show human-readable type and status labels
                "type": lambda el: el.get_typ_display(),
                "status": lambda el: el.get_status_display(),
                # Format monetary values with proper decimal formatting
                "gross": lambda el: format_decimal(el.mc_gross),
                "trans": lambda el: format_decimal(el.mc_fee) if el.mc_fee else "",
                # Display causal and details information
                "causal": lambda el: el.causal,
                "details": lambda el: el.get_details(),
                # Show confirm action only for submitted invoices
                "action": lambda el: f"<a href='{reverse('exe_invoices_confirm', args=[el.id])}'>{confirm}</a>"
                if el.status == PaymentStatus.SUBMITTED
                else "",
            },
        }
    )

    # Return paginated invoice list with edit functionality
    return exe_paginate(
        request, context, PaymentInvoice, "larpmanager/exe/accounting/invoices.html", "exe_invoices_edit"
    )


@login_required
def exe_invoices_edit(request, num):
    return exe_edit(request, ExeInvoiceForm, num, "exe_invoices")


@login_required
def exe_invoices_confirm(request: HttpRequest, num: int) -> HttpResponse:
    """Confirm a payment invoice by updating its status.

    Changes invoice status from CREATED or SUBMITTED to CONFIRMED.
    Only invoices in CREATED or SUBMITTED status can be confirmed.

    Args:
        request: The HTTP request object containing user and session data
        num: The invoice number/ID to confirm

    Returns:
        HttpResponse: Redirect to the invoices list page

    Raises:
        Http404: If invoice is already confirmed or in invalid status
    """
    # Check user permissions for invoice management
    context = check_assoc_permission(request, "exe_invoices")

    # Retrieve the specific invoice by number
    backend_get(context, PaymentInvoice, num)

    # Validate current status allows confirmation
    if context["el"].status == PaymentStatus.CREATED or context["el"].status == PaymentStatus.SUBMITTED:
        # Update status to confirmed
        context["el"].status = PaymentStatus.CONFIRMED
    else:
        # Reject if invoice already processed
        raise Http404("already done")

    # Persist changes to database
    context["el"].save()

    # Show success message and redirect to invoice list
    messages.success(request, _("Element approved") + "!")
    return redirect("exe_invoices")


@login_required
def exe_collections(request: HttpRequest) -> HttpResponse:
    """Display collections list for association executives."""
    # Check user permissions and get association context
    context = check_assoc_permission(request, "exe_collections")

    # Fetch collections with related data, ordered by creation date
    context["list"] = (
        Collection.objects.filter(assoc_id=context["association_id"])
        .select_related("member", "organizer")
        .order_by("-created")
    )

    return render(request, "larpmanager/exe/accounting/collections.html", context)


@login_required
def exe_collections_edit(request, num):
    return exe_edit(request, ExeCollectionForm, num, "exe_collections")


@login_required
def exe_refunds(request: HttpRequest) -> dict:
    """Handle refund requests management for organization executives.

    This view displays a paginated list of refund requests with status information
    and action buttons for processing pending refunds.

    Args:
        request: HttpRequest object containing the user's request data

    Returns:
        dict: Context dictionary for rendering the refunds template with pagination

    Raises:
        PermissionDenied: If user lacks exe_refunds permission
    """
    # Check user permissions for refund management
    context = check_assoc_permission(request, "exe_refunds")
    done = _("Done")

    # Define table column headers and their display names
    context.update(
        {
            "fields": [
                ("details", _("Informations")),
                ("member", _("Member")),
                ("value", _("Total required")),
                ("credits", _("Remaining credits")),
                ("status", _("Status")),
                ("action", _("Action")),
            ],
            # Configure column data transformation callbacks
            "callbacks": {
                # Display human-readable status text
                "status": lambda el: el.get_status_display(),
                # Show action button only for unpaid refunds
                "action": lambda el: f"<a href='{reverse('exe_refunds_confirm', args=[el.id])}'>{done}</a>"
                if el.status != RefundStatus.PAYED
                else "",
            },
        }
    )

    # Return paginated refund requests with template context
    return exe_paginate(request, context, RefundRequest, "larpmanager/exe/accounting/refunds.html", "exe_refunds_edit")


@login_required
def exe_refunds_edit(request, num):
    return exe_edit(request, ExeRefundRequestForm, num, "exe_refunds")


@login_required
def exe_refunds_confirm(request: HttpRequest, num: int) -> HttpResponse:
    """Confirm a refund request by changing its status to PAYED.

    This view handles the confirmation of refund requests by updating their status
    from REQUEST to PAYED. Only requests in REQUEST status can be confirmed.

    Args:
        request: The HTTP request object containing user authentication and permissions
        num: The unique identifier number of the refund request to confirm

    Returns:
        HttpResponse: Redirect to the refunds list page after successful confirmation

    Raises:
        Http404: If the refund request is not in REQUEST status (already processed)
    """
    # Check user permissions for accessing refund management
    context = check_assoc_permission(request, "exe_refunds")

    # Retrieve the specific refund request by number
    backend_get(context, RefundRequest, num)

    # Verify the refund request is in the correct status for confirmation
    if context["el"].status == RefundStatus.REQUEST:
        # Update status to indicate the refund has been paid
        context["el"].status = RefundStatus.PAYED
    else:
        # Prevent duplicate processing of already confirmed requests
        raise Http404("already done")

    # Persist the status change to the database
    context["el"].save()

    # Show success message to the user and redirect to refunds list
    messages.success(request, _("Element approved") + "!")
    return redirect("exe_refunds")


@login_required
def exe_accounting(request: HttpRequest) -> HttpResponse:
    """Render organization-wide accounting dashboard."""
    # Check user permissions for accounting access
    context = check_assoc_permission(request, "exe_accounting")

    # Populate context with accounting data
    assoc_accounting(context)

    return render(request, "larpmanager/exe/accounting/accounting.html", context)


@login_required
def exe_year_accounting(request: HttpRequest) -> JsonResponse:
    """Get accounting data for a specific year."""
    # Check association permissions for accounting access
    context = check_assoc_permission(request, "exe_accounting")

    # Parse and validate year parameter from POST data
    try:
        year = int(request.POST.get("year"))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid year parameter"}, status=400)

    # Build response with association ID and accounting data
    res = {"association_id": context["association_id"]}
    assoc_accounting_data(res, year)
    return JsonResponse({"res": res})


@login_required
def exe_run_accounting(request: HttpRequest, num: int) -> HttpResponse:
    """Display accounting information for a specific run.

    Args:
        request: The HTTP request object
        num: Primary key of the run to display accounting for

    Returns:
        Rendered accounting template with run and accounting data

    Raises:
        Http404: If run doesn't belong to user's association
    """
    # Check user has accounting permissions for this association
    context = check_assoc_permission(request, "exe_accounting")

    # Get the run and verify ownership
    context["run"] = Run.objects.get(pk=num)
    if context["run"].event.assoc_id != context["association_id"]:
        raise Http404("not your run")

    # Get accounting data for this run
    context["dc"] = get_run_accounting(context["run"], context)
    return render(request, "larpmanager/orga/accounting/accounting.html", context)


@login_required
def exe_accounting_rec(request: HttpRequest) -> HttpResponse:
    """Display accounting records for the organization."""
    context = check_assoc_permission(request, "exe_accounting_rec")

    # Get accounting records for the organization (not tied to specific runs)
    context["list"] = RecordAccounting.objects.filter(assoc_id=context["association_id"], run__isnull=True).order_by(
        "created"
    )

    # If no records exist, create them and redirect
    if len(context["list"]) == 0:
        check_accounting(context["association_id"])
        return redirect("exe_accounting_rec")

    # Set date range based on first and last records
    context["start"] = context["list"][0].created
    context["end"] = context["list"].reverse()[0].created

    return render(request, "larpmanager/exe/accounting/accounting_rec.html", context)


def check_year(request: HttpRequest, context: dict) -> int:
    """Check and validate the year parameter from request data.

    Retrieves the association from context, generates a list of valid years
    from the association's creation year to the current year, and validates
    the year parameter from POST data if present.

    Args:
        request: The HTTP request object containing POST data
        context: Context dictionary containing association ID and other data

    Returns:
        int: The validated year value, defaults to current year if invalid

    Raises:
        Association.DoesNotExist: If association with given ID doesn't exist
    """
    # Get association and generate valid years range
    association = Association.objects.get(pk=context["association_id"])
    context["years"] = list(range(datetime.today().year, association.created.year - 1, -1))

    # Process POST data if present
    if request.POST:
        try:
            # Attempt to parse year from POST data
            context["year"] = int(request.POST.get("year"))
        except (ValueError, TypeError):
            # Fall back to current year if parsing fails
            context["year"] = context["years"][0]
    else:
        # Default to current year if no POST data
        context["year"] = context["years"][0]

    return context["year"]


@login_required
def exe_balance(request: HttpRequest) -> HttpResponse:
    """Executive view for displaying association balance sheet for a specific year.

    Calculates totals for memberships, donations, tickets, and expenses from
    various accounting models to generate comprehensive financial reporting.
    Proportionally distributes reimbursements across expense categories.

    Args:
        request: Django HTTP request object with user authentication and year parameter

    Returns:
        HttpResponse: Rendered balance sheet template with financial data including:
            - memberships: Total membership fees
            - donations: Total donations
            - tickets: Net ticket revenue (payments - transaction fees)
            - inflows: Total inflows
            - expenditure: Dict of expenses by category
            - in: Total incoming funds
            - out: Total outgoing funds
            - bal: Balance (in - out)

    Raises:
        PermissionDenied: If user lacks exe_balance permission
    """
    # Verify user has executive balance permission
    context = check_assoc_permission(request, "exe_balance")
    year = check_year(request, context)

    # Define date range for the selected year
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)

    # Calculate total membership fees for the year
    context["memberships"] = get_sum(
        AccountingItemMembership.objects.filter(assoc_id=context["association_id"], year=year)
    )

    # Calculate total donations received in the year
    context["donations"] = get_sum(
        AccountingItemDonation.objects.filter(assoc_id=context["association_id"], created__gte=start, created__lt=end)
    )

    # Calculate net ticket revenue (cash payments minus transaction fees)
    context["tickets"] = get_sum(
        AccountingItemPayment.objects.filter(
            assoc_id=context["association_id"],
            pay=PaymentChoices.MONEY,
            created__gte=start,
            created__lt=end,
        )
    ) - get_sum(
        AccountingItemTransaction.objects.filter(
            assoc_id=context["association_id"], created__gte=start, created__lt=end
        )
    )

    # Calculate total inflows for the year
    context["inflows"] = get_sum(
        AccountingItemInflow.objects.filter(
            assoc_id=context["association_id"], payment_date__gte=start, payment_date__lt=end
        )
    )

    # Sum all incoming funds
    context["in"] = context["memberships"] + context["donations"] + context["tickets"] + context["inflows"]

    # Initialize expenditure tracking
    context["expenditure"] = {}
    context["out"] = 0

    # Calculate total refunds/reimbursements for proportional distribution
    context["rimb"] = get_sum(
        AccountingItemOther.objects.filter(
            assoc_id=context["association_id"],
            created__gte=start,
            created__lt=end,
            oth=OtherChoices.REFUND,
        )
    )

    # Initialize expenditure categories with zero values
    for value, label in BalanceChoices.choices:
        context["expenditure"][value] = {"name": label, "value": 0}

    # Aggregate approved personal expenses by balance category
    for el in (
        AccountingItemExpense.objects.filter(
            assoc_id=context["association_id"], created__gte=start, created__lt=end, is_approved=True
        )
        .values("balance")
        .annotate(Sum("value"))
    ):
        value = el["value__sum"]
        bl = el["balance"]
        context["expenditure"][bl]["value"] = value
        context["out"] += value

    # Proportionally distribute reimbursements across expense categories
    tot = context["out"]
    context["out"] = 0
    if tot:
        # Recalculate each category's value based on proportion of total reimbursed
        for bl, _descr in BalanceChoices.choices:
            v = context["expenditure"][bl]["value"]
            # Resample value based on actual reimbursements issued
            v = (v / tot) * context["rimb"]
            context["out"] += v
            context["expenditure"][bl]["value"] = v

    # Add association-level outflows to expenditure categories
    for el in (
        AccountingItemOutflow.objects.filter(
            assoc_id=context["association_id"], payment_date__gte=start, payment_date__lt=end
        )
        .values("balance")
        .annotate(Sum("value"))
    ):
        value = el["value__sum"]
        bl = el["balance"]
        context["expenditure"][bl]["value"] += value
        context["out"] += value

    # Calculate final balance
    context["bal"] = context["in"] - context["out"]

    return render(request, "larpmanager/exe/accounting/balance.html", context)


@login_required
def exe_verification(request: HttpRequest) -> HttpResponse:
    """Handle payment verification process with invoice upload and processing.

    This function manages the verification of payment invoices by allowing users to
    view pending payments and upload verification documents. It excludes automated
    payment methods and processes manual verification uploads.

    Args:
        request: HTTP request object containing user data and potentially uploaded files
            for payment verification processing

    Returns:
        HttpResponse: Rendered verification template containing pending payments list
            and file upload form for verification documents

    Raises:
        PermissionError: If user lacks required association permissions for verification
    """
    # Check user permissions and get association context
    context = check_assoc_permission(request, "exe_verification")

    # Query pending payment invoices excluding automated payment methods
    # Filter out created status and electronic payment methods that auto-verify
    context["todo"] = (
        PaymentInvoice.objects.filter(assoc_id=context["association_id"], verified=False)
        .exclude(status=PaymentStatus.CREATED)
        .exclude(method__slug__in=["redsys", "satispay", "paypal", "stripe", "sumup"])
        .select_related("method")
    )

    # Extract registration payment IDs for further processing
    check = [el.id for el in context["todo"] if el.typ == PaymentType.REGISTRATION]

    # Get accounting payment records for registration payments
    payments = AccountingItemPayment.objects.filter(inv_id__in=check)

    # Create mapping from invoice ID to run-member identifier
    # Build sets of unique run and member IDs for efficient querying
    aux = {acc.inv_id: f"{acc.reg.run_id}-{acc.member_id}" for acc in payments}
    run_ids = {acc.reg.run_id for acc in payments}
    member_ids = {acc.member_id for acc in payments}

    # Cache registration special codes using run-member composite key
    # This avoids N+1 queries when displaying registration codes
    cache = {
        f"{reg.run_id}-{reg.member_id}": reg.special_cod
        for reg in Registration.objects.filter(run_id__in=run_ids, member_id__in=member_ids)
    }

    # Attach registration codes to payment invoice objects
    for el in context["todo"]:
        el.reg_cod = cache.get(aux.get(el.id))

    # Handle file upload for payment verification
    if request.method == "POST":
        form = UploadElementsForm(request.POST, request.FILES, only_one=True)
        if form.is_valid():
            # Process uploaded verification file and count verified payments
            counter = invoice_verify(context, request.FILES["first"])
            messages.success(request, _("Verified payments") + "!" + " " + str(counter))
            return redirect("exe_verification")

    else:
        # Initialize empty form for GET requests
        form = UploadElementsForm(only_one=True)

    context["form"] = form

    return render(request, "larpmanager/exe/verification.html", context)


@login_required
def exe_verification_manual(request: HttpRequest, num: int) -> HttpResponse:
    """Manually verify a payment invoice for an organization.

    This view allows organization executives to manually confirm payment invoices
    that belong to their organization. It checks permissions, validates ownership,
    and prevents duplicate verification.

    Args:
        request: The HTTP request object containing user and session data
        num: The primary key of the PaymentInvoice to verify

    Returns:
        HttpResponse: Redirect to the verification list page

    Raises:
        Http404: If the invoice doesn't belong to the user's organization
    """
    # Check user has permission to access manual verification
    context = check_assoc_permission(request, "exe_verification")

    # Retrieve the invoice to verify
    invoice = PaymentInvoice.objects.get(pk=num)

    # Ensure invoice belongs to user's organization
    if invoice.assoc_id != context["association_id"]:
        raise Http404("not your assoc!")

    # Check if payment is already verified to prevent duplicates
    if invoice.verified:
        messages.warning(request, _("Payment already confirmed"))
        return redirect("exe_verification")

    # Mark invoice as verified and save changes
    invoice.verified = True
    invoice.save()

    # Notify user of successful verification
    messages.success(request, _("Payment confirmed"))
    return redirect("exe_verification")
