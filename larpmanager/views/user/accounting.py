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
from typing import Optional, Union

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt

from larpmanager.accounting.gateway import (
    redsys_webhook,
    satispay_webhook,
    stripe_webhook,
    sumup_webhook,
)
from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.accounting.member import info_accounting
from larpmanager.accounting.payment import get_payment_form
from larpmanager.cache.config import get_assoc_config
from larpmanager.cache.feature import get_assoc_features
from larpmanager.forms.accounting import (
    AnyInvoiceSubmitForm,
    CollectionForm,
    CollectionNewForm,
    DonateForm,
    PaymentForm,
    RefundRequestForm,
    WireInvoiceSubmitForm,
)
from larpmanager.forms.member import MembershipForm
from larpmanager.mail.accounting import notify_invoice_check, notify_refund_request
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemExpense,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemPayment,
    CollectionStatus,
    OtherChoices,
    PaymentChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.association import Association, AssocTextType
from larpmanager.models.member import Member, MembershipStatus, get_user_membership
from larpmanager.models.registration import Registration
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.common import (
    get_assoc,
    get_collection_partecipate,
    get_collection_redeem,
)
from larpmanager.utils.event import check_event_permission, get_event_run
from larpmanager.utils.exceptions import check_assoc_feature
from larpmanager.utils.fiscal_code import calculate_fiscal_code
from larpmanager.utils.text import get_assoc_text

logger = logging.getLogger(__name__)


@login_required
def accounting(request: HttpRequest) -> HttpResponse:
    """Display user accounting information including balances and payment status.

    This view renders the user's accounting page showing their balance, payment history,
    and status. If delegated members feature is enabled, it also displays accounting
    information for all delegated members.

    Args:
        request: HTTP request object from authenticated user. Must contain an
                authenticated user with associated member and organization.

    Returns:
        HttpResponse: Rendered accounting page template with context containing:
            - User balance and payment information
            - Delegated members' accounting data (if feature enabled)
            - Organization terms and conditions
            - Payment todo status flags

    Note:
        Redirects to home page if user has no associated organization (a_id == 0).
    """
    # Initialize base context and check for valid association
    ctx = def_user_ctx(request)
    if ctx["a_id"] == 0:
        return redirect("home")

    # Populate main user's accounting information
    info_accounting(request, ctx)

    # Initialize delegated members tracking
    ctx["delegated_todo"] = False

    # Process delegated members if feature is enabled
    if "delegated_members" in request.assoc["features"]:
        # Get all members delegated to current user
        ctx["delegated"] = Member.objects.filter(parent=request.user.member)

        # Process accounting info for each delegated member
        for el in ctx["delegated"]:
            del_ctx = {"member": el, "a_id": ctx["a_id"]}
            info_accounting(request, del_ctx)

            # Attach context to member object for template access
            el.ctx = del_ctx
            # Track if any delegated member has pending payments
            ctx["delegated_todo"] = ctx["delegated_todo"] or del_ctx["payments_todo"]

    # Load organization terms and conditions for display
    ctx["assoc_terms_conditions"] = get_assoc_text(ctx["a_id"], AssocTextType.TOC)

    return render(request, "larpmanager/member/accounting.html", ctx)


@login_required
def accounting_tokens(request: HttpRequest) -> HttpResponse:
    """Display user's token accounting information including given and used tokens.

    This view renders a page showing the authenticated user's token accounting
    information, including tokens they have been given and tokens they have used
    within their associated organization.

    Args:
        request (HttpRequest): HTTP request object from authenticated user

    Returns:
        HttpResponse: Rendered token accounting page with given/used token lists

    Note:
        Only shows non-hidden accounting items for the user's current association.
    """
    # Initialize context with default user data
    ctx = def_user_ctx(request)

    # Query for tokens given to the user (non-hidden, within current association)
    given_tokens = AccountingItemOther.objects.filter(
        member=ctx["member"],
        hide=False,
        oth=OtherChoices.TOKEN,
        assoc_id=ctx["a_id"],
    )

    # Query for tokens used by the user (non-hidden, within current association)
    used_tokens = AccountingItemPayment.objects.filter(
        member=ctx["member"],
        hide=False,
        pay=PaymentChoices.TOKEN,
        assoc_id=ctx["a_id"],
    )

    # Update context with token data
    ctx.update(
        {
            "given": given_tokens,
            "used": used_tokens,
        }
    )

    # Render and return the token accounting template
    return render(request, "larpmanager/member/acc_tokens.html", ctx)


@login_required
def accounting_credits(request: HttpRequest) -> HttpResponse:
    """
    Display user's accounting credits including expenses, credits given/used, and refunds.

    This view retrieves all accounting-related items for the current user within their
    associated organization, including approved expenses, credit transactions, payment
    records using credits, and refunds.

    Args:
        request (HttpRequest): The HTTP request object containing user session data
            and request metadata.

    Returns:
        HttpResponse: Rendered template displaying the user's accounting credits
            summary with expenses, given credits, used credits, and refunds.
    """
    # Get base user context with member and association info
    ctx = def_user_ctx(request)

    # Add accounting data to context with filtered queries for current user/association
    ctx.update(
        {
            # Approved expenses for the user in current association
            "exp": AccountingItemExpense.objects.filter(
                member=ctx["member"], hide=False, is_approved=True, assoc_id=ctx["a_id"]
            ),
            # Credits given to the user in current association
            "given": AccountingItemOther.objects.filter(
                member=ctx["member"],
                hide=False,
                oth=OtherChoices.CREDIT,
                assoc_id=ctx["a_id"],
            ),
            # Payments made using credits by the user in current association
            "used": AccountingItemPayment.objects.filter(
                member=ctx["member"],
                hide=False,
                pay=PaymentChoices.CREDIT,
                assoc_id=ctx["a_id"],
            ),
            # Refunds issued to the user in current association
            "ref": AccountingItemOther.objects.filter(
                member=ctx["member"],
                hide=False,
                oth=OtherChoices.REFUND,
                assoc_id=ctx["a_id"],
            ),
        }
    )

    # Render the accounting credits template with populated context
    return render(request, "larpmanager/member/acc_credits.html", ctx)


@login_required
def acc_refund(request: HttpRequest) -> HttpResponse:
    """Handle refund request form processing and notifications.

    Processes user refund requests by displaying a form for GET requests and
    handling form submission for POST requests. Creates refund records and
    sends notifications to administrators.

    Args:
        request: HTTP request object containing user data and form submission

    Returns:
        HttpResponse: Rendered refund form template for GET requests or
                     redirect to accounting page after successful POST submission

    Raises:
        PermissionDenied: If user lacks refund feature access
    """
    # Check user has permission to access refund functionality
    check_assoc_feature(request, "refund")

    # Initialize base context with user and association data
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    ctx.update({"member": request.user.member, "a_id": request.assoc["id"]})

    # Verify user membership in current association
    get_user_membership(request.user.member, ctx["a_id"])

    if request.method == "POST":
        # Process refund request form submission
        form = RefundRequestForm(request.POST, member=ctx["member"])

        if form.is_valid():
            # Save refund request with transaction safety
            with transaction.atomic():
                p = form.save(commit=False)
                p.member = ctx["member"]
                p.assoc_id = ctx["a_id"]
                p.save()

            # Send notification to administrators about new refund request
            notify_refund_request(p)

            # Show success message and redirect to accounting dashboard
            messages.success(
                request, _("Request for reimbursement entered! You will receive notice when it is processed.") + "."
            )
            return redirect("accounting")
    else:
        # Display empty form for GET request
        form = RefundRequestForm(member=ctx["member"])

    # Add form to context and render template
    ctx["form"] = form
    return render(request, "larpmanager/member/acc_refund.html", ctx)


@login_required
def acc_pay(request: HttpRequest, s: str, method: Optional[str] = None) -> HttpResponse:
    """Handle payment redirection for event registration.

    Validates user permissions and registration status before redirecting to
    the appropriate payment processing page. Performs fiscal code validation
    if the feature is enabled for the association.

    Args:
        request: Django HTTP request object containing user session and data
        s: Event slug string identifier for the specific event
        method: Optional payment method identifier (e.g., 'paypal', 'stripe')

    Returns:
        HttpResponse: Redirect response to payment page or error page

    Raises:
        PermissionDenied: If user lacks payment feature access
        Http404: If event or registration not found
    """
    # Check if user has permission to access payment features
    check_assoc_feature(request, "payment")

    # Get event context and validate user registration status
    ctx = get_event_run(request, s, signup=True, status=True)

    # Verify user has valid registration for this event
    if not ctx["run"].reg:
        messages.warning(
            request, _("We cannot find your registration for this event. Are you logged in as the correct user") + "?"
        )
        return redirect("accounting")
    else:
        reg = ctx["run"].reg

    # Validate fiscal code if feature is enabled for this association
    if "fiscal_code_check" in ctx["features"]:
        result = calculate_fiscal_code(ctx["member"])
        # Redirect to profile if fiscal code has validation errors
        if "error_cf" in result:
            # Redirect to profile page if fiscal code has errors
            messages.warning(
                request, _("Your tax code has a problem that we ask you to correct") + ": " + result["error_cf"]
            )
            return redirect("profile")

    # Redirect to payment processing with or without specific method
    if method:
        return redirect("acc_reg", reg_id=reg.id, method=method)
    else:
        return redirect("acc_reg", reg_id=reg.id)


@login_required
def acc_reg(request: HttpRequest, reg_id: int, method: str | None = None) -> HttpResponse:
    """Handle registration payment processing for event registrations.

    Manages payment flows, fee calculations, and transaction recording
    across different payment methods. Validates registration status,
    membership requirements, and outstanding payment amounts.

    Args:
        request: HTTP request object with authenticated user
        reg_id: Registration ID to process payment for
        method: Optional payment method slug to pre-select

    Returns:
        HttpResponse: Rendered payment form or redirect on validation failure/success

    Raises:
        Http404: If registration not found or invalid parameters
    """
    # Ensure payment feature is enabled for this association
    check_assoc_feature(request, "payment")

    # Retrieve registration with related run and event data
    try:
        reg = Registration.objects.select_related("run", "run__event").get(
            id=reg_id,
            member=request.user.member,
            cancellation_date__isnull=True,
            run__event__assoc_id=request.assoc["id"],
        )
    except Exception as err:
        raise Http404(f"registration not found {err}") from err

    # Get event context and mark as accounting page
    ctx = get_event_run(request, reg.run.get_slug())
    ctx["show_accounting"] = True

    # Load membership status for permission checks
    reg.membership = get_user_membership(reg.member, request.assoc["id"])

    # Check if registration is already fully paid
    if reg.tot_iscr == reg.tot_payed:
        messages.success(request, _("Everything is in order about the payment of this event") + "!")
        return redirect("gallery", s=reg.run.get_slug())

    # Check for pending payment verification
    pending = (
        PaymentInvoice.objects.filter(
            idx=reg.id,
            member_id=reg.member_id,
            status=PaymentStatus.SUBMITTED,
            typ=PaymentType.REGISTRATION,
        ).count()
        > 0
    )
    if pending:
        messages.success(request, _("You have already sent a payment pending verification"))
        return redirect("gallery", s=reg.run.get_slug())

    # Verify membership approval if membership feature is enabled
    if "membership" in ctx["features"] and not reg.membership.date:
        mes = _("To be able to pay, your membership application must be approved") + "."
        messages.warning(request, mes)
        return redirect("gallery", s=reg.run.get_slug())

    # Add registration to context
    ctx["reg"] = reg

    # Calculate payment quota - use installment quota if set, otherwise full balance
    if reg.quota:
        ctx["quota"] = reg.quota
    else:
        ctx["quota"] = reg.tot_iscr - reg.tot_payed

    # Generate unique key for payment tracking
    key = f"{reg.id}_{reg.num_payments}"

    # Load association configuration for payment display
    ctx["association"] = Association.objects.get(pk=ctx["a_id"])
    ctx["hide_amount"] = ctx["association"].get_config("payment_hide_amount", False)

    # Pre-select payment method if specified
    if method:
        ctx["def_method"] = method

    # Handle payment form submission
    if request.method == "POST":
        form = PaymentForm(request.POST, reg=reg, ctx=ctx)
        if form.is_valid():
            # Process payment through selected gateway
            get_payment_form(request, form, PaymentType.REGISTRATION, ctx, key)
    else:
        form = PaymentForm(reg=reg, ctx=ctx)
    ctx["form"] = form

    return render(request, "larpmanager/member/acc_reg.html", ctx)


@login_required
def acc_membership(request: HttpRequest, method: Optional[str] = None) -> HttpResponse:
    """Process membership fee payment for the current year.

    This function handles the membership fee payment workflow, including validation
    of membership status, checking for existing payments, and processing payment forms.

    Args:
        request: HTTP request object containing user data and session information
        method: Optional payment method to use as default in the payment form

    Returns:
        HttpResponse: Rendered membership payment form template or redirect response

    Raises:
        PermissionDenied: If user lacks required association feature access
    """
    # Check if user has access to membership feature
    check_assoc_feature(request, "membership")
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True

    # Validate user membership status - must be accepted to pay dues
    memb = get_user_membership(request.user.member, request.assoc["id"])
    if memb.status != MembershipStatus.ACCEPTED:
        messages.success(request, _("It is not possible for you to pay dues at this time") + ".")
        return redirect("accounting")

    # Check if membership fee already paid for current year
    year = datetime.now().year
    try:
        AccountingItemMembership.objects.get(year=year, member=request.user.member, assoc_id=request.assoc["id"])
        messages.success(request, _("You have already paid this year's membership fee"))
        return redirect("accounting")
    except Exception:
        pass

    # Set up context variables for template rendering
    ctx["year"] = year
    key = f"{request.user.member.id}_{year}"

    # Set default payment method if provided
    if method:
        ctx["def_method"] = method

    # Process form submission or render initial form
    if request.method == "POST":
        form = MembershipForm(request.POST, ctx=ctx)
        if form.is_valid():
            # Generate payment form for valid membership submission
            get_payment_form(request, form, PaymentType.MEMBERSHIP, ctx, key)
    else:
        form = MembershipForm(ctx=ctx)

    # Add form and membership fee to context for template
    ctx["form"] = form
    ctx["membership_fee"] = get_assoc(request).get_config("membership_fee")

    return render(request, "larpmanager/member/acc_membership.html", ctx)


@login_required
def acc_donate(request: HttpRequest) -> HttpResponse:
    """Handle donation form display and processing for authenticated users.

    This view manages the donation workflow by displaying a donation form
    and processing payment requests when the form is submitted.

    Args:
        request: The HTTP request object containing user data and form submission

    Returns:
        HttpResponse: Rendered donation page with form and context data

    Raises:
        PermissionDenied: If user lacks 'donate' feature access
    """
    # Check if user has permission to access donation feature
    check_assoc_feature(request, "donate")

    # Initialize base context with user data and accounting visibility
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True

    # Process form submission for donation payment
    if request.method == "POST":
        form = DonateForm(request.POST, ctx=ctx)
        if form.is_valid():
            # Generate payment form for valid donation request
            get_payment_form(request, form, PaymentType.DONATE, ctx)
    else:
        # Display empty donation form for GET requests
        form = DonateForm(ctx=ctx)

    # Add form and donation flag to template context
    ctx["form"] = form
    ctx["donate"] = 1

    return render(request, "larpmanager/member/acc_donate.html", ctx)


@login_required
def acc_collection(request: HttpRequest) -> HttpResponse:
    """Handle member collection creation and payment processing.

    This view function processes both GET and POST requests for creating
    new collections. On GET, it displays an empty form. On POST, it validates
    the form data and creates a new collection with the current user as organizer.

    Args:
        request (HttpRequest): The HTTP request object containing method,
            POST data, user information, and association context.

    Returns:
        HttpResponse: For GET requests, renders the collection form template.
            For successful POST requests, redirects to collection management page.
            For invalid POST requests, re-renders form with validation errors.

    Raises:
        DatabaseError: If the atomic transaction fails during collection creation.
    """
    # Initialize context with user defaults and enable accounting display
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True

    if request.method == "POST":
        # Process form submission for new collection
        form = CollectionNewForm(request.POST)

        if form.is_valid():
            # Create collection within atomic transaction to ensure data consistency
            with transaction.atomic():
                p = form.save(commit=False)
                p.organizer = request.user.member
                p.assoc_id = request.assoc["id"]
                p.save()

            # Show success message and redirect to collection management
            messages.success(request, _("The collection has been activated!"))
            return redirect("acc_collection_manage", s=p.contribute_code)
    else:
        # Initialize empty form for GET request
        form = CollectionNewForm()

    # Add form to context and render template
    ctx["form"] = form
    return render(request, "larpmanager/member/acc_collection.html", ctx)


@login_required
def acc_collection_manage(request: HttpRequest, s: str) -> HttpResponse:
    """
    Manage accounting collection for the authenticated user.

    Args:
        request: HTTP request object containing user and association data
        s: Collection identifier string

    Returns:
        HttpResponse: Rendered template with collection management interface

    Raises:
        Http404: If the collection doesn't belong to the requesting user
    """
    # Retrieve the collection the user participates in
    c = get_collection_partecipate(request, s)

    # Verify user ownership of the collection
    if request.user.member != c.organizer:
        raise Http404("Collection not yours")

    # Initialize base user context and enable accounting display
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True

    # Add collection data and filtered accounting items to context
    ctx.update(
        {
            "coll": c,
            "list": AccountingItemCollection.objects.filter(collection=c, collection__assoc_id=request.assoc["id"]),
        }
    )

    # Render and return the collection management template
    return render(request, "larpmanager/member/acc_collection_manage.html", ctx)


@login_required
def acc_collection_participate(request: HttpRequest, s: str) -> HttpResponse:
    """Handle user participation in a collection payment process.

    Args:
        request: The HTTP request object containing user session and POST data
        s: String identifier for the collection to participate in

    Returns:
        HttpResponse: Rendered template with collection participation form

    Raises:
        Http404: When the collection is not in OPEN status
    """
    # Get the collection object and verify user permissions
    c = get_collection_partecipate(request, s)

    # Initialize base context with user data and accounting flag
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    ctx["coll"] = c

    # Validate collection is open for participation
    if c.status != CollectionStatus.OPEN:
        raise Http404("Collection not open")

    # Handle form submission for collection participation
    if request.method == "POST":
        form = CollectionForm(request.POST, ctx=ctx)
        # Process valid form and setup payment gateway
        if form.is_valid():
            get_payment_form(request, form, PaymentType.COLLECTION, ctx)
    else:
        # Initialize empty form for GET requests
        form = CollectionForm(ctx=ctx)

    # Add form to context and render participation template
    ctx["form"] = form
    return render(request, "larpmanager/member/acc_collection_participate.html", ctx)


@login_required
def acc_collection_close(request: HttpRequest, s: str) -> HttpResponse:
    """Close an open collection by changing its status to DONE.

    Args:
        request: The HTTP request object containing user information
        s: The collection identifier/slug

    Returns:
        HttpResponse: Redirect to the collection management page

    Raises:
        Http404: If collection doesn't belong to user or isn't open
    """
    # Get the collection the user participates in
    c = get_collection_partecipate(request, s)

    # Verify the current user is the organizer of this collection
    if request.user.member != c.organizer:
        raise Http404("Collection not yours")

    # Ensure the collection is in an open state before closing
    if c.status != CollectionStatus.OPEN:
        raise Http404("Collection not open")

    # Atomically update the collection status to prevent race conditions
    with transaction.atomic():
        c.status = CollectionStatus.DONE
        c.save()

    # Notify user of successful closure and redirect to management page
    messages.success(request, _("Collection closed"))
    return redirect("acc_collection_manage", s=s)


@login_required
def acc_collection_redeem(request: HttpRequest, s: str) -> Union[HttpResponseRedirect, HttpResponse]:
    """Handle redemption of completed accounting collections.

    This function allows users to redeem completed accounting collections by changing
    their status from DONE to PAYED and assigning them to the requesting user.

    Args:
        request: The HTTP request object containing user and method information
        s: The collection slug identifier used to retrieve the specific collection

    Returns:
        HttpResponseRedirect: Redirects to home page after successful POST redemption
        HttpResponse: Rendered template with collection details for GET requests

    Raises:
        Http404: If the collection is not found or status is not DONE
    """
    # Get the collection using the provided slug and validate access
    c = get_collection_redeem(request, s)

    # Initialize the context with default user context and accounting flag
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    ctx["coll"] = c

    # Verify collection is in the correct status for redemption
    if c.status != CollectionStatus.DONE:
        raise Http404("Collection not found")

    # Handle POST request for collection redemption
    if request.method == "POST":
        # Use atomic transaction to ensure data consistency
        with transaction.atomic():
            c.member = request.user.member
            c.status = CollectionStatus.PAYED
            c.save()

        # Display success message and redirect to home
        messages.success(request, _("The collection has been delivered!"))
        return redirect("home")

    # For GET requests, prepare collection items list for display
    ctx["list"] = AccountingItemCollection.objects.filter(
        collection=c, collection__assoc_id=request.assoc["id"]
    ).select_related("member", "collection")

    # Render the redemption template with collection data
    return render(request, "larpmanager/member/acc_collection_redeem.html", ctx)


def acc_webhook_paypal(request, s):
    # temp fix until we understand better the paypal fees
    if invoice_received_money(s):
        return JsonResponse({"res": "ok"})


@csrf_exempt
def acc_webhook_satispay(request):
    satispay_webhook(request)
    return JsonResponse({"res": "ok"})


@csrf_exempt
def acc_webhook_stripe(request):
    stripe_webhook(request)
    return JsonResponse({"res": "ok"})


@csrf_exempt
def acc_webhook_sumup(request):
    sumup_webhook(request)
    return JsonResponse({"res": "ok"})


@csrf_exempt
def acc_webhook_redsys(request):
    redsys_webhook(request)
    return JsonResponse({"res": "ok"})


@csrf_exempt
def acc_redsys_ko(request: HttpRequest) -> HttpResponseRedirect:
    """Handle failed Redsys payment callback."""
    # printpretty_request(request))
    # err_paypal(pretty_request(request))

    # Notify user about payment failure
    messages.error(request, _("The payment has not been completed"))
    return redirect("accounting")


@login_required
def acc_wait(request):
    return render(request, "larpmanager/member/acc_wait.html")


@login_required
def acc_cancelled(request: HttpRequest) -> HttpResponse:
    """Handle cancelled payment redirecting to accounting page."""
    mes = _("The payment was not completed. Please contact us to find out why") + "."
    messages.warning(request, mes)
    return redirect("accounting")


def acc_profile_check(request: HttpRequest, mes: str, inv) -> HttpResponse:
    """Check if user profile is compiled and redirect appropriately.

    Validates that the user's membership profile is complete. If not compiled,
    adds a message prompting profile completion and redirects to profile page.
    Otherwise, displays success message and redirects to accounting page.

    Args:
        request: Django HTTP request object containing user information
        mes: Success message string to display to user
        inv: Invoice object for accounting redirect

    Returns:
        HttpResponse: Redirect to either profile page or accounting page
    """
    # Get current user's member object and membership for this association
    member = request.user.member
    mb = get_user_membership(member, request.assoc["id"])

    # Check if membership profile has been completed
    if not mb.compiled:
        # Add profile completion prompt to message and redirect to profile
        mes += " " + _("As a final step, we ask you to complete your profile") + "."
        messages.success(request, mes)
        return redirect("profile")

    # Profile is complete - show success message and proceed to accounting
    messages.success(request, mes)
    return acc_redirect(inv)


def acc_redirect(inv: PaymentInvoice) -> HttpResponseRedirect:
    """Redirect to appropriate page after payment based on invoice type."""
    # Redirect to run gallery if invoice is for registration
    if inv.typ == PaymentType.REGISTRATION:
        reg = Registration.objects.get(id=inv.idx)
        return redirect("gallery", s=reg.run.get_slug())

    # Default redirect to accounting page
    return redirect("accounting")


@login_required
def acc_payed(request: HttpRequest, p: int = 0) -> HttpResponse:
    """Handle payment completion and redirect to profile check.

    Args:
        request: The HTTP request object containing user and association data
        p: Payment invoice primary key. If 0, no specific invoice is processed

    Returns:
        HttpResponse from acc_profile_check with success message and invoice

    Raises:
        Http404: If payment invoice with given pk doesn't exist or doesn't belong to user
    """
    # Check if a specific payment invoice ID was provided
    if p:
        try:
            # Retrieve the payment invoice for the current user and association
            inv = PaymentInvoice.objects.get(pk=p, member=request.user.member, assoc_id=request.assoc["id"])
        except Exception as err:
            # Raise 404 if invoice not found or access denied
            raise Http404("eeeehm") from err
    else:
        # No specific invoice to process
        inv = None

    # Set success message for payment completion
    mes = _("You have completed the payment!")

    # Redirect to profile check with success message and invoice
    return acc_profile_check(request, mes, inv)


@login_required
def acc_submit(request: HttpRequest, s: str, p: str) -> HttpResponse:
    """Handle payment submission and invoice upload for user accounts.

    Processes different payment types (wire transfer, PayPal, any) and handles
    file uploads with validation and status updates.

    Args:
        request: The HTTP request object containing POST data and files
        s: Payment submission type ('wire', 'paypal_nf', or 'any')
        p: Redirect path for error cases

    Returns:
        HttpResponse: Redirect response to accounting page or profile check

    Raises:
        Http404: If payment submission type is unknown
    """
    # Only allow POST requests for security
    if not request.method == "POST":
        messages.error(request, _("You can't access this way!"))
        return redirect("accounting")

    # Check if receipt is required for manual payments
    require_receipt = get_assoc_config(request.assoc["id"], "payment_require_receipt", False)

    # Select appropriate form based on payment type
    if s in {"wire", "paypal_nf"}:
        form = WireInvoiceSubmitForm(request.POST, request.FILES, require_receipt=require_receipt)
    elif s == "any":
        form = AnyInvoiceSubmitForm(request.POST, request.FILES)
    else:
        raise Http404("unknown value: " + s)

    # Validate form data and uploaded files
    if not form.is_valid():
        # logger.debug(f"Form errors: {form.errors}")
        mes = _("Error loading. Invalid file format (we accept only pdf or images)") + "."
        messages.error(request, mes)
        return redirect("/" + p)

    # Retrieve the payment invoice using form data
    try:
        inv = PaymentInvoice.objects.get(cod=form.cleaned_data["cod"], assoc_id=request.assoc["id"])
    except ObjectDoesNotExist:
        messages.error(request, _("Error processing payment, contact us"))
        return redirect("/" + p)

    # Update invoice with submitted data atomically
    with transaction.atomic():
        if s in {"wire", "paypal_nf"}:
            # Only set invoice if one was provided
            if form.cleaned_data.get("invoice"):
                inv.invoice = form.cleaned_data["invoice"]
        elif s == "any":
            inv.text = form.cleaned_data["text"]

        # Mark as submitted and generate transaction ID
        inv.status = PaymentStatus.SUBMITTED
        inv.txn_id = datetime.now().timestamp()
        inv.save()

    # Send notification for invoice review
    notify_invoice_check(inv)

    # Display success message and redirect to profile check
    mes = _("Payment received") + "!" + _("As soon as it is approved, your accounting will be updated") + "."
    return acc_profile_check(request, mes, inv)


@login_required
def acc_confirm(request: HttpRequest, c: str) -> HttpResponse:
    """
    Confirm accounting payment invoice with authorization checks.

    Args:
        request: HTTP request object with user authentication
        c: Invoice confirmation code

    Returns:
        HttpResponse: Redirect to home page with success/error message

    Raises:
        ObjectDoesNotExist: When invoice with given code is not found
        PermissionDenied: When user lacks authorization to confirm invoice
    """
    # Retrieve invoice by confirmation code and association ID
    try:
        inv = PaymentInvoice.objects.get(cod=c, assoc_id=request.assoc["id"])
    except ObjectDoesNotExist:
        messages.error(request, _("Invoice not found"))
        return redirect("home")

    # Check if invoice is in submittable status
    if inv.status != PaymentStatus.SUBMITTED:
        messages.error(request, _("Invoice already confirmed"))
        return redirect("home")

    # Authorization check: verify user permissions
    found = False
    assoc_id = request.assoc["id"]

    # Check if user is appointed treasurer
    if "treasurer" in get_assoc_features(assoc_id):
        for mb in get_assoc_config(assoc_id, "treasurer_appointees", "").split(", "):
            if not mb:
                continue
            if request.user.member.id == int(mb):
                found = True

    # For registration payments, check event permissions
    if not found:
        if inv.typ == PaymentType.REGISTRATION:
            reg = Registration.objects.get(pk=inv.idx)
            check_event_permission(request, reg.run.get_slug())

    # Atomically update invoice status to confirmed
    with transaction.atomic():
        inv.status = PaymentStatus.CONFIRMED
        inv.save()

    # Return success response
    messages.success(request, _("Payment confirmed"))
    return redirect("home")


def add_runs(ls, lis, future=True):
    for e in lis:
        for r in e.runs.all():
            if future and r.end < date.today():
                continue
            ls[r.id] = r
