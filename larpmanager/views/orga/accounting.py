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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.balance import get_run_accounting
from larpmanager.cache.config import get_assoc_config
from larpmanager.forms.accounting import (
    OrgaCreditForm,
    OrgaDiscountForm,
    OrgaExpenseForm,
    OrgaInflowForm,
    OrgaOutflowForm,
    OrgaPaymentForm,
    OrgaPersonalExpenseForm,
    OrgaTokenForm,
)
from larpmanager.models.accounting import (
    AccountingItemExpense,
    AccountingItemInflow,
    AccountingItemOther,
    AccountingItemOutflow,
    AccountingItemPayment,
    Discount,
    PaymentInvoice,
    PaymentStatus,
)
from larpmanager.templatetags.show_tags import format_decimal
from larpmanager.utils.base import check_event_context
from larpmanager.utils.edit import backend_get, orga_edit
from larpmanager.utils.paginate import orga_paginate


@login_required
def orga_discounts(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage discounts for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_discounts")

    # Get all discounts for the event ordered by number
    context["list"] = Discount.objects.filter(event=context["event"]).order_by("number")

    return render(request, "larpmanager/orga/accounting/discounts.html", context)


@login_required
def orga_discounts_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_discounts", OrgaDiscountForm, num)


@login_required
def orga_expenses_my(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display user's personal expenses for an event run."""
    context = check_event_context(request, event_slug, "orga_expenses_my")
    context["list"] = AccountingItemExpense.objects.filter(run=context["run"], member=request.user.member).order_by(
        "-created"
    )
    return render(request, "larpmanager/orga/accounting/expenses_my.html", context)


@login_required
def orga_expenses_my_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new personal expense reimbursement request.

    This view handles both GET and POST requests for creating new personal
    expense reimbursement items. On GET, it displays an empty form. On POST,
    it validates and saves the expense, then redirects appropriately.

    Args:
        request: Django HTTP request object containing user data and form submission
        event_slug: Event slug identifier used to identify the specific event/run

    Returns:
        HttpResponse: Rendered form template for GET requests or redirect response
        for successful POST requests. Returns form with validation errors on
        invalid POST submissions.

    Raises:
        PermissionDenied: If user lacks required permissions for the event
    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_expenses_my")

    if request.method == "POST":
        # Process form submission with uploaded files
        form = OrgaPersonalExpenseForm(request.POST, request.FILES, context=context)

        if form.is_valid():
            # Save expense without committing to add additional fields
            exp = form.save(commit=False)

            # Set required relationship fields from context and user
            exp.run = context["run"]
            exp.member = request.user.member
            exp.assoc_id = context["association_id"]
            exp.save()

            # Show success message to user
            messages.success(request, _("Reimbursement request item added"))

            # Redirect based on user's choice to continue or finish
            if "continue" in request.POST:
                return redirect("orga_expenses_my_new", event_slug=context["run"].get_slug())
            return redirect("orga_expenses_my", event_slug=context["run"].get_slug())
    else:
        # Create empty form for GET request
        form = OrgaPersonalExpenseForm(context=context)

    # Add form to context and render template
    context["form"] = form
    return render(request, "larpmanager/orga/accounting/expenses_my_new.html", context)


@login_required
def orga_invoices(request: HttpRequest, event_slug: str) -> HttpResponse:
    """
    Display payment invoices awaiting confirmation for event organizers.

    This view shows submitted payment invoices for the current event run with
    optimized database queries to prevent N+1 query problems. Results are
    filtered to show only invoices with SUBMITTED status.

    Args:
        request: Django HTTP request object containing user session and data
        event_slug: Event slug identifier used to determine the current event context

    Returns:
        HttpResponse: Rendered template with paginated invoice list and context data

    Raises:
        PermissionDenied: If user lacks 'orga_invoices' permission for the event
        Http404: If event with given slug does not exist
    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_invoices")

    # Build optimized query with select_related to prevent N+1 queries
    que = (
        PaymentInvoice.objects.filter(reg__run=context["run"], status=PaymentStatus.SUBMITTED)
        .select_related(
            "member",  # For {{ el.member }} in template
            "method",  # For {{ el.method }} in template
            "reg",  # For confirmation URL generation
            "reg__run",  # For run.get_slug() in confirmation URL
        )
        .order_by("-created")  # Show newest invoices first
    )

    # Add invoice list to template context
    context["list"] = que

    # Render template with invoice data
    return render(request, "larpmanager/orga/accounting/invoices.html", context)


@login_required
def orga_invoices_confirm(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Confirm a payment invoice for an organization event.

    This function allows organizers to confirm payment invoices that are in
    CREATED or SUBMITTED status. Once confirmed, the invoice status is updated
    to CONFIRMED and the user is redirected back to the invoices list.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event identifier string for URL routing
        num: The invoice number/ID to confirm

    Returns:
        HttpResponse: Redirect to the invoices list page with success/warning message

    Raises:
        Http404: If the invoice doesn't belong to the current event
        PermissionDenied: If user lacks orga_invoices permission (via check_event_context)
    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_invoices")

    # Retrieve the payment invoice by number
    backend_get(context, PaymentInvoice, num)

    # Verify invoice belongs to the current event run
    if context["el"].reg.run != context["run"]:
        raise Http404("i'm sorry, what?")

    # Check if invoice can be confirmed (must be CREATED or SUBMITTED)
    if context["el"].status == PaymentStatus.CREATED or context["el"].status == PaymentStatus.SUBMITTED:
        # Update status to confirmed and save
        context["el"].status = PaymentStatus.CONFIRMED
    else:
        # Invoice already processed - show warning and redirect
        messages.warning(request, _("Receipt already confirmed") + ".")
        return redirect("orga_invoices", event_slug=context["run"].get_slug())

    # Save the updated invoice status
    context["el"].save()

    # Show success message and redirect to invoices list
    messages.success(request, _("Element approved") + "!")
    return redirect("orga_invoices", event_slug=context["run"].get_slug())


@login_required
def orga_accounting(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display accounting overview for an event run."""
    # Check permissions and retrieve event context
    context = check_event_context(request, event_slug, "orga_accounting")

    # Get accounting data for the run
    context["dc"] = get_run_accounting(context["run"], context)

    return render(request, "larpmanager/orga/accounting/accounting.html", context)


@login_required
def orga_tokens(request: HttpRequest, event_slug) -> dict:
    """
    Display and manage accounting tokens for an organization's events.

    This view handles the display of accounting tokens (credits/debits) for events
    within an organization, providing a paginated interface for token management.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: The event slug identifier for context resolution

    Returns:
        dict: Rendered response containing the tokens page with pagination

    Raises:
        PermissionDenied: If user lacks 'orga_tokens' permission for the event
    """
    # Check user permissions for token management in the specified event
    context = check_event_context(request, event_slug, "orga_tokens")

    # Configure context with relationship selectors and display metadata
    # 'selrel' defines the database relationships to follow for data retrieval
    # 'subtype' categorizes this view as a token management interface
    context.update(
        {
            "selrel": ("run", "run__event"),  # Follow run -> event relationships
            "subtype": "tokens",  # Mark as token management subtype
            # Define table columns with localized headers for the token list
            "fields": [
                ("member", _("Member")),  # Token holder/user
                ("run", _("Event")),  # Associated event run
                ("descr", _("Description")),  # Token description/purpose
                ("value", _("Value")),  # Token monetary value
                ("created", _("Date")),  # Token creation timestamp
            ],
        }
    )

    # Return paginated view of AccountingItemOther objects (tokens)
    # Uses the organization accounting tokens template and edit route
    return orga_paginate(
        request, context, AccountingItemOther, "larpmanager/orga/accounting/tokens.html", "orga_tokens_edit"
    )


@login_required
def orga_tokens_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_tokens", OrgaTokenForm, num)


@login_required
def orga_credits(request: HttpRequest, event_slug: str) -> HttpResponse:
    """View for displaying and managing organization credits.

    Args:
        request: The HTTP request object containing user information and parameters
        event_slug: The event slug identifier for permission checking

    Returns:
        HttpResponse: Rendered paginated credits page with accounting items
    """
    # Check user permissions for accessing organization credits functionality
    context = check_event_context(request, event_slug, "orga_credits")

    # Configure context with relationship selectors and field definitions
    context.update(
        {
            "selrel": ("run", "run__event"),  # Database relationship path for filtering
            "subtype": "credits",  # Accounting item subtype identifier
            # Define display fields with their localized labels
            "fields": [
                ("member", _("Member")),
                ("run", _("Event")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("created", _("Date")),
            ],
        }
    )

    # Return paginated view of accounting items using the configured context
    return orga_paginate(
        request, context, AccountingItemOther, "larpmanager/orga/accounting/credits.html", "orga_credits_edit"
    )


@login_required
def orga_credits_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_credits", OrgaCreditForm, num)


@login_required
def orga_payments(request: HttpRequest, event_slug: str) -> HttpResponse:
    """
    Display organization payments page with filterable payment data.

    Args:
        request: HTTP request object containing user session and form data
        event_slug: Event slug identifier for permission checking and context

    Returns:
        HttpResponse: Rendered payments page with paginated payment data
    """
    # Check user permissions for accessing organization payments
    context = check_event_context(request, event_slug, "orga_payments")

    # Define base table fields for payment display
    fields = [
        ("member", _("Member")),
        ("method", _("Method")),
        ("type", _("Type")),
        ("status", _("Status")),
        ("net", _("Net")),
        ("trans", _("Fee")),
        ("created", _("Date")),
    ]

    # Add VAT fields if VAT feature is enabled
    if "vat" in context["features"]:
        fields.append(("vat_ticket", _("VAT (Ticket)")))
        fields.append(("vat_options", _("VAT (Options)")))

    # Configure context with database relations and field callbacks
    context.update(
        {
            # Define select_related fields for efficient database queries
            "selrel": ("reg__member", "reg__run", "inv", "inv__method"),
            "afield": "reg",
            "fields": fields,
            # Define callback functions for data formatting
            "callbacks": {
                "member": lambda row: str(row.reg.member) if row.reg and row.reg.member else "",
                "method": lambda el: str(el.inv.method) if el.inv else "",
                "type": lambda el: el.get_pay_display(),
                "status": lambda el: el.inv.get_status_display() if el.inv else "",
                "net": lambda el: format_decimal(el.net),
                "trans": lambda el: format_decimal(el.trans) if el.trans else "",
            },
        }
    )

    # Return paginated payment data with configured template
    return orga_paginate(
        request, context, AccountingItemPayment, "larpmanager/orga/accounting/payments.html", "orga_payments_edit"
    )


@login_required
def orga_payments_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_payments", OrgaPaymentForm, num)


@login_required
def orga_outflows(request: HttpRequest, event_slug: str) -> HttpResponse:
    """
    Display paginated outflow accounting items for event organizers.

    Args:
        request: HTTP request object containing user authentication and parameters
        event_slug: Event slug identifier for permission checking and data filtering

    Returns:
        HTTP response with rendered outflows template and pagination context

    Raises:
        PermissionDenied: If user lacks 'orga_outflows' permission for the event
    """
    # Check user permissions for accessing outflow data in the specified event
    context = check_event_context(request, event_slug, "orga_outflows")

    # Configure context with table display settings and field definitions
    context.update(
        {
            # Define related fields for database query optimization
            "selrel": ("run", "run__event"),
            # Configure table columns with localized headers
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
                # Create download link for statement documents
                "statement": lambda el: f"<a href='{el.download()}'>Download</a>",
                # Display human-readable type labels
                "type": lambda el: el.get_exp_display(),
            },
        }
    )

    # Render paginated table with outflow data and edit functionality
    return orga_paginate(
        request, context, AccountingItemOutflow, "larpmanager/orga/accounting/outflows.html", "orga_outflows_edit"
    )


@login_required
def orga_outflows_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_outflows", OrgaOutflowForm, num)


@login_required
def orga_inflows(request: HttpRequest, event_slug: str) -> dict:
    """Display paginated list of accounting inflows for organization event management.

    This function handles the organization view for accounting inflows, providing
    a paginated table with download links for statements and proper permission checking.

    Args:
        request: Django HTTP request object containing user session and data
        event_slug: event slug identifier used for permission checking

    Returns:
        dict: Rendered HTTP response with paginated inflows table and context data
    """
    # Check user permissions for accessing organization inflow data
    context = check_event_context(request, event_slug, "orga_inflows")

    # Configure context with table display settings and field definitions
    context.update(
        {
            # Define related model relationships for efficient database queries
            "selrel": ("run", "run__event"),
            # Configure table columns with localized headers for display
            "fields": [
                ("run", _("Event")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("payment_date", _("Date")),
                ("statement", _("Statement")),
            ],
            # Define custom callback functions for rendering specific table cells
            "callbacks": {
                "statement": lambda el: f"<a href='{el.download()}'>Download</a>",
            },
        }
    )

    # Return paginated view with configured context and template rendering
    return orga_paginate(
        request, context, AccountingItemInflow, "larpmanager/orga/accounting/inflows.html", "orga_inflows_edit"
    )


@login_required
def orga_inflows_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_inflows", OrgaInflowForm, num)


@login_required
def orga_expenses(request: HttpRequest, event_slug: str) -> HttpResponse:
    """
    Display and manage organization expenses for a specific event.

    This view provides paginated expense management functionality for event organizers,
    including approval actions and statement downloads when permissions allow.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event identifier string used for URL routing and permission checks

    Returns:
        HttpResponse: Rendered template with expense data and pagination controls
    """
    # Check user permissions for expense management and initialize context
    context = check_event_context(request, event_slug, "orga_expenses")

    # Determine if approval functionality should be disabled for this organization
    context["disable_approval"] = get_assoc_config(context["event"].assoc_id, "expense_disable_orga", False, context)

    # Cache the translated approval text for callback usage
    approve = _("Approve")

    # Configure table display settings including related field prefetching
    # and column definitions with their respective labels
    context.update(
        {
            "selrel": ("run", "run__event"),
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
            # Define callback functions for custom column rendering
            "callbacks": {
                # Generate download link for expense statement documents
                "statement": lambda el: f"<a href='{el.download()}'>Download</a>",
                # Show approval link only for unapproved items when approval is enabled
                "action": lambda el: f"<a href='{reverse('orga_expenses_approve', args=[context['run'].get_slug(), el.id])}'>{approve}</a>"
                if not el.is_approved and not context["disable_approval"]
                else "",
                # Display human-readable expense type from model choices
                "type": lambda el: el.get_exp_display(),
            },
        }
    )

    # Render paginated expense list using the organization template
    return orga_paginate(
        request, context, AccountingItemExpense, "larpmanager/orga/accounting/expenses.html", "orga_expenses_edit"
    )


@login_required
def orga_expenses_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_expenses", OrgaExpenseForm, num)


@login_required
def orga_expenses_approve(request: HttpRequest, event_slug: str, num: int) -> HttpResponseRedirect:
    """Approve an expense request for an event.

    This function handles the approval of expense requests by organization
    administrators. It validates permissions, checks if expenses are enabled,
    and updates the expense approval status.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event identifier string used for URL routing
        num: The primary key ID of the expense to be approved

    Returns:
        HttpResponseRedirect: Redirect response to the expenses list page

    Raises:
        Http404: If expenses are disabled, expense doesn't exist, or user
                lacks permission for the event
    """
    # Check user permissions for expense management on this event
    context = check_event_context(request, event_slug, "orga_expenses")

    # Verify that expense functionality is enabled for this association
    if get_assoc_config(context["event"].assoc_id, "expense_disable_orga", False):
        raise Http404("eh no caro mio")

    # Retrieve the expense object or raise 404 if not found
    try:
        exp = AccountingItemExpense.objects.get(pk=num)
    except Exception as err:
        raise Http404("no id expense") from err

    # Ensure the expense belongs to the current event
    if exp.run.event != context["event"]:
        raise Http404("not your orga")

    # Update expense approval status and save to database
    exp.is_approved = True
    exp.save()

    # Display success message and redirect to expenses list
    messages.success(request, _("Request approved"))
    return redirect("orga_expenses", event_slug=context["run"].get_slug())
