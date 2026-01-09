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

from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
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
from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.config import get_association_config
from larpmanager.cache.feature import get_association_features
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
    Collection,
    CollectionStatus,
    OtherChoices,
    PaymentChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.association import Association, AssociationTextType
from larpmanager.models.member import Member, MembershipStatus, get_user_membership
from larpmanager.models.registration import Registration
from larpmanager.utils.core.base import check_event_context, get_context, get_event_context
from larpmanager.utils.core.common import (
    get_collection_partecipate,
    get_collection_redeem,
)
from larpmanager.utils.core.exceptions import check_association_feature
from larpmanager.utils.users.fiscal_code import calculate_fiscal_code

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
    context = get_context(request)
    if context["association_id"] == 0:
        return redirect("home")

    # Populate main user's accounting information
    info_accounting(context)

    # Initialize delegated members tracking
    context["delegated_todo"] = False

    # Process delegated members if feature is enabled
    if "delegated_members" in context["features"]:
        # Get all members delegated to current user
        context["delegated"] = Member.objects.filter(parent=context["member"])

        # Process accounting info for each delegated member
        for el in context["delegated"]:
            del_ctx = {
                "member": el,
                "association_id": context["association_id"],
                "features": context["features"],
            }
            info_accounting(del_ctx)

            # Attach context to member object for template access
            el.context = del_ctx
            # Track if any delegated member has pending payments
            context["delegated_todo"] = context["delegated_todo"] or del_ctx["payments_todo"]

    # Load organization terms and conditions for display
    context["association_terms_conditions"] = get_association_text(context["association_id"], AssociationTextType.TOC)

    return render(request, "larpmanager/member/accounting.html", context)


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
    context = get_context(request)

    # Query for tokens given to the user (non-hidden, within current association)
    given_tokens = AccountingItemOther.objects.filter(
        member=context["member"],
        hide=False,
        oth=OtherChoices.TOKEN,
        association_id=context["association_id"],
    )

    # Query for tokens used by the user (non-hidden, within current association)
    used_tokens = AccountingItemPayment.objects.filter(
        member=context["member"],
        hide=False,
        pay=PaymentChoices.TOKEN,
        association_id=context["association_id"],
    )

    # Update context with token data
    context.update(
        {
            "given": given_tokens,
            "used": used_tokens,
        },
    )

    # Render and return the token accounting template
    return render(request, "larpmanager/member/acc_tokens.html", context)


@login_required
def accounting_credits(request: HttpRequest) -> HttpResponse:
    """Display user's accounting credits including expenses, credits given/used, and refunds.

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
    context = get_context(request)

    # Add accounting data to context with filtered queries for current user/association
    context.update(
        {
            # Approved expenses for the user in current association
            "exp": AccountingItemExpense.objects.filter(
                member=context["member"],
                hide=False,
                is_approved=True,
                association_id=context["association_id"],
            ),
            # Credits given to the user in current association
            "given": AccountingItemOther.objects.filter(
                member=context["member"],
                hide=False,
                oth=OtherChoices.CREDIT,
                association_id=context["association_id"],
            ),
            # Payments made using credits by the user in current association
            "used": AccountingItemPayment.objects.filter(
                member=context["member"],
                hide=False,
                pay=PaymentChoices.CREDIT,
                association_id=context["association_id"],
            ),
            # Refunds issued to the user in current association
            "ref": AccountingItemOther.objects.filter(
                member=context["member"],
                hide=False,
                oth=OtherChoices.REFUND,
                association_id=context["association_id"],
            ),
        },
    )

    # Render the accounting credits template with populated context
    return render(request, "larpmanager/member/acc_credits.html", context)


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
    context = get_context(request)
    check_association_feature(request, context, "refund")
    context["show_accounting"] = True

    # Verify user membership in current association
    get_user_membership(context["member"], context["association_id"])

    if request.method == "POST":
        # Process refund request form submission
        form = RefundRequestForm(request.POST, context=context)

        if form.is_valid():
            # Save refund request with transaction safety
            with transaction.atomic():
                p: PaymentInvoice = form.save(commit=False)
                p.member = context["member"]
                p.association_id = context["association_id"]
                p.save()

            # Send notification to administrators about new refund request
            notify_refund_request(p)

            # Show success message and redirect to accounting dashboard
            messages.success(
                request,
                _("Request for reimbursement entered! You will receive notice when it is processed.") + ".",
            )
            return redirect("accounting")
    else:
        # Display empty form for GET request
        form = RefundRequestForm(context=context)

    # Add form to context and render template
    context["form"] = form
    return render(request, "larpmanager/member/acc_refund.html", context)


@login_required
def accounting_payment(request: HttpRequest, event_slug: str, method: str | None = None) -> HttpResponse:
    """Handle payment redirection for event registration.

    Validates user permissions and registration status before redirecting to
    the appropriate payment processing page. Performs fiscal code validation
    if the feature is enabled for the association.

    Args:
        request: Django HTTP request object containing user session and data
        event_slug: Event slug string identifier for the specific event
        method: Optional payment method identifier (e.g., 'paypal', 'stripe')

    Returns:
        HttpResponse: Redirect response to payment page or error page

    Raises:
        PermissionDenied: If user lacks payment feature access
        Http404: If event or registration not found

    """
    # Get event context and validate user registration status
    context = get_event_context(request, event_slug, signup=True, include_status=True)

    # Check if user has permission to access payment features
    check_association_feature(request, context, "payment")

    # Verify user has valid registration for this event
    if not context["registration"]:
        messages.warning(
            request,
            _("We cannot find your registration for this event. Are you logged in as the correct user") + "?",
        )
        return redirect("accounting")
    reg = context["registration"]

    # Validate fiscal code if feature is enabled for this association
    if "fiscal_code_check" in context["features"]:
        result = calculate_fiscal_code(context["member"])
        # Redirect to profile if fiscal code has validation errors
        if "error_cf" in result:
            # Redirect to profile page if fiscal code has errors
            messages.warning(
                request,
                _("Your tax code has a problem that we ask you to correct") + ": " + result["error_cf"],
            )
            return redirect("profile")

    # Redirect to payment processing with or without specific method
    if method:
        return redirect("accounting_registration", registration_uuid=reg.uuid, method=method)
    return redirect("accounting_registration", registration_uuid=reg.uuid)


@login_required
def accounting_registration(request: HttpRequest, registration_uuid: str, method: str | None = None) -> HttpResponse:
    """Handle registration payment processing for event registrations.

    Manages payment flows, fee calculations, and transaction recording
    across different payment methods. Validates registration status,
    membership requirements, and outstanding payment amounts.

    Args:
        request: HTTP request object with authenticated user
        registration_uuid: Registration UUID
        method: Optional payment method slug to pre-select

    Returns:
        HttpResponse: Rendered payment form or redirect on validation failure/success

    Raises:
        Http404: If registration not found or invalid parameters

    """
    # Ensure payment feature is enabled for this association
    context = get_context(request)
    check_association_feature(request, context, "payment")

    # Get event context and mark as accounting page
    registration = get_accounting_registration(context, registration_uuid)
    context = get_event_context(request, registration.run.get_slug())
    context["show_accounting"] = True
    context["registration"] = registration

    # Load membership status for permission checks
    registration.membership = get_user_membership(registration.member, context["association_id"])

    # Check if registration is already fully paid
    if registration.tot_iscr == registration.tot_payed:
        messages.success(request, _("Everything is in order about the payment of this event") + "!")
        return redirect("gallery", event_slug=registration.run.get_slug())

    # Check for pending payment verification
    pending = (
        PaymentInvoice.objects.filter(
            idx=registration.id,
            member_id=registration.member_id,
            status=PaymentStatus.SUBMITTED,
            typ=PaymentType.REGISTRATION,
        ).count()
        > 0
    )
    if pending:
        messages.success(request, _("You have already sent a payment pending verification"))
        return redirect("gallery", event_slug=registration.run.get_slug())

    # Verify membership approval if membership feature is enabled
    if "membership" in context["features"] and not registration.membership.date:
        mes = _("To be able to pay, your membership application must be approved") + "."
        messages.warning(request, mes)
        return redirect("gallery", event_slug=registration.run.get_slug())

    # Calculate payment quota - use installment quota if set, otherwise full balance
    if registration.quota:
        context["quota"] = registration.quota
    else:
        context["quota"] = registration.tot_iscr - registration.tot_payed

    # Generate unique key for payment tracking
    key = f"{registration.id}_{registration.num_payments}"

    # Load association configuration for payment display
    context["association"] = Association.objects.get(pk=context["association_id"])
    context["hide_amount"] = context["association"].get_config("payment_hide_amount", default_value=False)

    # Pre-select payment method if specified
    if method:
        context["def_method"] = method

    # Handle payment form submission
    if request.method == "POST":
        form = PaymentForm(request.POST, registration=registration, context=context)
        if form.is_valid():
            # Process payment through selected gateway
            get_payment_form(request, form, PaymentType.REGISTRATION, context, key)
    else:
        form = PaymentForm(registration=registration, context=context)
    context["form"] = form

    return render(request, "larpmanager/member/accounting_registration.html", context)


def get_accounting_registration(context: dict, registration_uuid: str) -> Registration:
    """Get registration by UUID with member and association validation.

    Args:
        context: Context dictionary containing member and association_id
        registration_uuid: Registration UUID or ID (numeric fallback)

    Returns:
        Registration object with related run and event data

    Raises:
        Http404: If registration not found or access denied
    """
    # Build base queryset with related data
    queryset = Registration.objects.select_related("run", "run__event")
    filters = {
        "member": context["member"],
        "cancellation_date__isnull": True,
        "run__event__association_id": context["association_id"],
    }

    # Try UUID lookup first
    try:
        return queryset.get(uuid=registration_uuid, **filters)
    except (ObjectDoesNotExist, ValueError, AttributeError) as err:
        # Fallback to pk lookup if identifier is numeric
        if str(registration_uuid).isdigit():
            try:
                return queryset.get(pk=registration_uuid, **filters)
            except ObjectDoesNotExist:
                msg = f"registration not found {err}"
                raise Http404(msg) from err
        msg = f"registration not found {err}"
        raise Http404(msg) from err


@login_required
def acc_membership(request: HttpRequest, method: str | None = None) -> HttpResponse:
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
    context = get_context(request)
    check_association_feature(request, context, "membership")
    context["show_accounting"] = True

    # Validate user membership status - must be accepted to pay dues
    memb = get_user_membership(context["member"], context["association_id"])
    if memb.status != MembershipStatus.ACCEPTED:
        messages.success(request, _("It is not possible for you to pay dues at this time") + ".")
        return redirect("accounting")

    # Check if membership fee already paid for current year
    year = timezone.now().year
    try:
        AccountingItemMembership.objects.get(
            year=year,
            member=context["member"],
            association_id=context["association_id"],
        )
        messages.success(request, _("You have already paid this year's membership fee"))
        return redirect("accounting")
    except AccountingItemMembership.DoesNotExist as e:
        logger.debug("Membership fee not found for member=%s, year=%s: %s", context["member"].id, year, e)

    # Set up context variables for template rendering
    context["year"] = year
    key = f"{context['member'].id}_{year}"

    # Set default payment method if provided
    if method:
        context["def_method"] = method

    # Process form submission or render initial form
    if request.method == "POST":
        form = MembershipForm(request.POST, context=context)
        if form.is_valid():
            # Generate payment form for valid membership submission
            get_payment_form(request, form, PaymentType.MEMBERSHIP, context, key)
    else:
        form = MembershipForm(context=context)

    # Add form and membership fee to context for template
    context["form"] = form
    context["membership_fee"] = get_association_config(context["association_id"], "membership_fee", default_value=0)

    return render(request, "larpmanager/member/acc_membership.html", context)


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
    context = get_context(request)
    check_association_feature(request, context, "donate")
    context["show_accounting"] = True

    # Process form submission for donation payment
    if request.method == "POST":
        form = DonateForm(request.POST, context=context)
        if form.is_valid():
            # Generate payment form for valid donation request
            get_payment_form(request, form, PaymentType.DONATE, context)
    else:
        # Display empty donation form for GET requests
        form = DonateForm(context=context)

    # Add form and donation flag to template context
    context["form"] = form
    context["donate"] = 1

    return render(request, "larpmanager/member/acc_donate.html", context)


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
    context = get_context(request)
    context["show_accounting"] = True

    if request.method == "POST":
        # Process form submission for new collection
        form = CollectionNewForm(request.POST)

        if form.is_valid():
            # Create collection within atomic transaction to ensure data consistency
            with transaction.atomic():
                p: Collection = form.save(commit=False)
                p.organizer = context["member"]
                p.association_id = context["association_id"]
                p.save()

            # Show success message and redirect to collection management
            messages.success(request, _("The collection has been activated!"))
            return redirect("acc_collection_manage", collection_code=p.contribute_code)
    else:
        # Initialize empty form for GET request
        form = CollectionNewForm()

    # Add form to context and render template
    context["form"] = form
    return render(request, "larpmanager/member/acc_collection.html", context)


@login_required
def acc_collection_manage(request: HttpRequest, collection_code: str) -> HttpResponse:
    """Manage accounting collection for the authenticated user.

    Args:
        request: HTTP request object containing user and association data
        collection_code: Code collection identifier

    Returns:
        HttpResponse: Rendered template with collection management interface

    Raises:
        Http404: If the collection doesn't belong to the requesting user

    """
    # Initialize base user context and enable accounting display
    context = get_context(request)
    context["show_accounting"] = True

    # Retrieve the collection the user participates in
    c = get_collection_partecipate(context, collection_code)

    # Verify user ownership of the collection
    if context["member"] != c.organizer:
        msg = "Collection not yours"
        raise Http404(msg)

    # Add collection data and filtered accounting items to context
    context.update(
        {
            "coll": c,
            "list": AccountingItemCollection.objects.filter(
                collection=c,
                collection__association_id=context["association_id"],
            ),
        },
    )

    # Render and return the collection management template
    return render(request, "larpmanager/member/acc_collection_manage.html", context)


@login_required
def acc_collection_participate(request: HttpRequest, collection_code: str) -> HttpResponse:
    """Handle user participation in a collection payment process.

    Args:
        request: The HTTP request object containing user session and POST data
        collection_code: Code collection identifier

    Returns:
        HttpResponse: Rendered template with collection participation form

    Raises:
        Http404: When the collection is not in OPEN status

    """
    # Initialize base context with user data and accounting flag
    context = get_context(request)
    context["show_accounting"] = True

    # Get the collection object and verify user permissions
    c = get_collection_partecipate(context, collection_code)
    context["coll"] = c

    # Validate collection is open for participation
    if c.status != CollectionStatus.OPEN:
        msg = "Collection not open"
        raise Http404(msg)

    # Handle form submission for collection participation
    if request.method == "POST":
        form = CollectionForm(request.POST, context=context)
        # Process valid form and setup payment gateway
        if form.is_valid():
            get_payment_form(request, form, PaymentType.COLLECTION, context)
    else:
        # Initialize empty form for GET requests
        form = CollectionForm(context=context)

    # Add form to context and render participation template
    context["form"] = form
    return render(request, "larpmanager/member/acc_collection_participate.html", context)


@login_required
def acc_collection_close(request: HttpRequest, collection_code: str) -> HttpResponse:
    """Close an open collection by changing its status to DONE.

    Args:
        request: The HTTP request object containing user information
        collection_code: Code collection identifier

    Returns:
        HttpResponse: Redirect to the collection management page

    Raises:
        Http404: If collection doesn't belong to user or isn't open

    """
    # Get the collection the user participates in
    context = get_context(request)
    c = get_collection_partecipate(context, collection_code)

    # Verify the current user is the organizer of this collection
    if context["member"] != c.organizer:
        msg = "Collection not yours"
        raise Http404(msg)

    # Ensure the collection is in an open state before closing
    if c.status != CollectionStatus.OPEN:
        msg = "Collection not open"
        raise Http404(msg)

    # Atomically update the collection status to prevent race conditions
    with transaction.atomic():
        c.status = CollectionStatus.DONE
        c.save()

    # Notify user of successful closure and redirect to management page
    messages.success(request, _("Collection closed"))
    return redirect("acc_collection_manage", collection_code=collection_code)


@login_required
def acc_collection_redeem(request: HttpRequest, collection_code: str) -> HttpResponseRedirect | HttpResponse:
    """Handle redemption of completed accounting collections.

    This function allows users to redeem completed accounting collections by changing
    their status from DONE to PAYED and assigning them to the requesting user.

    Args:
        request: The HTTP request object containing user and method information
        collection_code: Code collection identifier

    Returns:
        HttpResponseRedirect: Redirects to home page after successful POST redemption
        HttpResponse: Rendered template with collection details for GET requests

    Raises:
        Http404: If the collection is not found or status is not DONE

    """
    # Initialize the context with default user context and accounting flag
    context = get_context(request)
    context["show_accounting"] = True

    # Get the collection using the provided slug and validate access
    c = get_collection_redeem(context, collection_code)
    context["coll"] = c

    # Verify collection is in the correct status for redemption
    if c.status != CollectionStatus.DONE:
        msg = "Collection not found"
        raise Http404(msg)

    # Handle POST request for collection redemption
    if request.method == "POST":
        # Use atomic transaction to ensure data consistency
        with transaction.atomic():
            c.member = context["member"]
            c.status = CollectionStatus.PAYED
            c.save()

        # Display success message and redirect to home
        messages.success(request, _("The collection has been delivered!"))
        return redirect("home")

    # For GET requests, prepare collection items list for display
    context["list"] = AccountingItemCollection.objects.filter(
        collection=c,
        collection__association_id=context["association_id"],
    ).select_related("member", "collection")

    # Render the redemption template with collection data
    return render(request, "larpmanager/member/acc_collection_redeem.html", context)


def acc_webhook_paypal(request: HttpRequest, s: str) -> JsonResponse | None:  # noqa: ARG001
    """Handle PayPal webhook for invoice payment confirmation."""
    # Temporary fix until PayPal fees are better understood
    if invoice_received_money(s):
        return JsonResponse({"res": "ok"})
    return None


@csrf_exempt
def acc_webhook_satispay(request: HttpRequest) -> JsonResponse:
    """Handle Satispay webhook callbacks and return success response."""
    # Process incoming Satispay webhook
    satispay_webhook(request)

    # Return success confirmation
    return JsonResponse({"res": "ok"})


@csrf_exempt
def acc_webhook_stripe(request: HttpRequest) -> JsonResponse:
    """Handle Stripe webhook notifications."""
    # Process Stripe webhook event
    stripe_webhook(request)
    return JsonResponse({"res": "ok"})


@csrf_exempt
def acc_webhook_sumup(request: HttpRequest) -> JsonResponse:
    """Process SumUp webhook and return success response."""
    sumup_webhook(request)
    return JsonResponse({"res": "ok"})


@csrf_exempt
def acc_webhook_redsys(request: HttpRequest) -> JsonResponse:
    """Process Redsys payment gateway webhook and return confirmation response."""
    redsys_webhook(request)
    return JsonResponse({"res": "ok"})


@csrf_exempt
def acc_redsys_ko(request: HttpRequest) -> HttpResponseRedirect:
    """Handle failed Redsys payment callback."""
    # Notify user about payment failure
    messages.error(request, _("The payment has not been completed"))
    return redirect("accounting")


@login_required
def acc_wait(request: HttpRequest) -> HttpResponse:
    """Render the account waiting page."""
    return render(request, "larpmanager/member/acc_wait.html")


@login_required
def acc_cancelled(request: HttpRequest) -> HttpResponse:
    """Handle cancelled payment redirecting to accounting page."""
    mes = _("The payment was not completed. Please contact us to find out why") + "."
    messages.warning(request, mes)
    return redirect("accounting")


def acc_profile_check(request: HttpRequest, success_message: str, invoice: Any) -> HttpResponse:
    """Check if user profile is compiled and redirect appropriately.

    Validates that the user's membership profile is complete. If not compiled,
    adds a message prompting profile completion and redirects to profile page.
    Otherwise, displays success message and redirects to accounting page.

    Args:
        request: Django HTTP request object containing user information
        success_message: Success message string to display to user
        invoice: Invoice object for accounting redirect

    Returns:
        HttpResponse: Redirect to either profile page or accounting page

    """
    # Get current user's membership for this association
    context = get_context(request)
    membership = context["membership"]

    # Check if membership profile has been completed
    if not membership.compiled:
        # Add profile completion prompt to message and redirect to profile
        success_message += " " + _("As a final step, we ask you to complete your profile") + "."
        messages.success(request, success_message)
        return redirect("profile")

    # Profile is complete - show success message and proceed to accounting
    messages.success(request, success_message)
    return acc_redirect(invoice)


def acc_redirect(invoice: PaymentInvoice) -> HttpResponseRedirect:
    """Redirect to appropriate page after payment based on invoice type."""
    # Redirect to run gallery if invoice is for registration
    if invoice.typ == PaymentType.REGISTRATION:
        registration = Registration.objects.get(id=invoice.idx)
        return redirect("gallery", event_slug=registration.run.get_slug())

    # Default redirect to accounting page
    return redirect("accounting")


@login_required
def acc_payed(request: HttpRequest, registration_uuid: str = "0") -> HttpResponse:
    """Handle payment completion and redirect to profile check.

    Args:
        request: The HTTP request object containing user and association data
        registration_uuid: Payment uuid. If 0, no specific invoice is processed

    Returns:
        HttpResponse from acc_profile_check with success message and invoice

    Raises:
        Http404: If payment invoice with given pk doesn't exist or doesn't belong to user

    """
    # Check if a specific payment invoice ID was provided
    context = get_context(request)
    if registration_uuid != "0":
        try:
            # Retrieve the payment invoice for the current user and association
            inv = PaymentInvoice.objects.get(
                uuid=registration_uuid,
                member=context["member"],
                association_id=context["association_id"],
            )
        except Exception as err:
            # Raise 404 if invoice not found or access denied
            msg = "eeeehm"
            raise Http404(msg) from err
    else:
        # No specific invoice to process
        inv = None

    # Set success message for payment completion
    mes = _("You have completed the payment!")

    # Redirect to profile check with success message and invoice
    return acc_profile_check(request, mes, inv)


@login_required
def acc_submit(request: HttpRequest, payment_method: str, redirect_path: str) -> HttpResponse:
    """Handle payment submission and invoice upload for user accounts.

    Processes different payment types (wire transfer, PayPal, any) and handles
    file uploads with validation and status updates.

    Args:
        request: The HTTP request object containing POST data and files
        payment_method: Payment submission type ('wire', 'paypal_nf', or 'any')
        redirect_path: Redirect path for error cases

    Returns:
        HttpResponse: Redirect response to accounting page or profile check

    Raises:
        Http404: If payment submission type is unknown

    """
    context = get_context(request)
    # Only allow POST requests for security
    if request.method != "POST":
        messages.error(request, _("You can't access this way!"))
        return redirect("accounting")

    # Check if receipt is required for manual payments
    require_receipt = get_association_config(context["association_id"], "payment_require_receipt", default_value=False)

    # Select appropriate form based on payment type
    if payment_method in {"wire", "paypal_nf"}:
        form = WireInvoiceSubmitForm(request.POST, request.FILES, require_receipt=require_receipt)
    elif payment_method == "any":
        form = AnyInvoiceSubmitForm(request.POST, request.FILES)
    else:
        msg = "unknown value: " + payment_method
        raise Http404(msg)

    # Validate form data and uploaded files
    if not form.is_valid():
        mes = _("Error loading. Invalid file format (we accept only pdf or images)") + "."
        messages.error(request, mes)
        return redirect("/" + redirect_path)

    # Retrieve the payment invoice using form data
    try:
        inv = PaymentInvoice.objects.get(cod=form.cleaned_data["cod"], association_id=context["association_id"])
    except ObjectDoesNotExist:
        messages.error(request, _("Error processing payment, contact us"))
        return redirect("/" + redirect_path)

    # Update invoice with submitted data atomically
    with transaction.atomic():
        if payment_method in {"wire", "paypal_nf"}:
            # Only set invoice if one was provided
            if form.cleaned_data.get("invoice"):
                inv.invoice = form.cleaned_data["invoice"]
        elif payment_method == "any":
            inv.text = form.cleaned_data["text"]

        # Mark as submitted and generate transaction ID
        inv.status = PaymentStatus.SUBMITTED
        inv.txn_id = timezone.now().timestamp()
        inv.save()

    # Send notification for invoice review
    notify_invoice_check(inv)

    # Display success message and redirect to profile check
    mes = _("Payment received") + "! " + _("As soon as it is approved, your accounting will be updated") + "."
    return acc_profile_check(request, mes, inv)


@login_required
def acc_confirm(request: HttpRequest, invoice_cod: str) -> HttpResponse:
    """Confirm accounting payment invoice with authorization checks.

    Args:
        request: HTTP request object with user authentication
        invoice_cod: Invoice confirmation code

    Returns:
        HttpResponse: Redirect to home page with success/error message

    Raises:
        ObjectDoesNotExist: When invoice with given code is not found
        PermissionDenied: When user lacks authorization to confirm invoice

    """
    # Retrieve invoice by confirmation code and association ID
    context = get_context(request)
    try:
        inv = PaymentInvoice.objects.get(cod=invoice_cod, association_id=context["association_id"])
    except ObjectDoesNotExist:
        messages.error(request, _("Invoice not found"))
        return redirect("home")

    # Check if invoice is in submittable status
    if inv.status != PaymentStatus.SUBMITTED:
        messages.error(request, _("Invoice already confirmed"))
        return redirect("home")

    # Authorization check: verify user permissions
    found = False
    association_id = context["association_id"]

    # Check if user is appointed treasurer
    if "treasurer" in get_association_features(association_id):
        for mb in get_association_config(association_id, "treasurer_appointees", default_value="").split(", "):
            if not mb:
                continue
            if context["member"].id == int(mb):
                found = True

    # For registration payments, check event permissions
    if not found and inv.typ == PaymentType.REGISTRATION:
        reg = Registration.objects.get(pk=inv.idx)
        check_event_context(request, reg.run.get_slug())

    # Atomically update invoice status to confirmed
    with transaction.atomic():
        inv.status = PaymentStatus.CONFIRMED
        inv.save()

    # Return success response
    messages.success(request, _("Payment confirmed"))
    return redirect("home")


def add_runs(ls: dict, lis: list, *, future: bool = True) -> None:
    """Add runs from events to dictionary, optionally filtering past runs."""
    for e in lis:
        # Filter and add runs to dictionary by ID
        for r in e.runs.all():
            if future and r.end < timezone.now().date():
                continue
            ls[r.id] = r
