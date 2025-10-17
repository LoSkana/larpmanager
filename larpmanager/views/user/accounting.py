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
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
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
def accounting(request):
    """Display user accounting information including balances and payment status.

    Args:
        request: HTTP request object from authenticated user

    Returns:
        HttpResponse: Rendered accounting page with balance, payments, and delegated member info
    """
    ctx = def_user_ctx(request)
    if ctx["a_id"] == 0:
        return redirect("home")
    info_accounting(request, ctx)

    ctx["delegated_todo"] = False
    if "delegated_members" in request.assoc["features"]:
        ctx["delegated"] = Member.objects.filter(parent=request.user.member)
        for el in ctx["delegated"]:
            del_ctx = {"member": el, "a_id": ctx["a_id"]}
            info_accounting(request, del_ctx)
            el.ctx = del_ctx
            ctx["delegated_todo"] = ctx["delegated_todo"] or del_ctx["payments_todo"]

    ctx["assoc_terms_conditions"] = get_assoc_text(ctx["a_id"], AssocTextType.TOC)

    return render(request, "larpmanager/member/accounting.html", ctx)


@login_required
def accounting_tokens(request):
    """Display user's token accounting information including given and used tokens.

    Args:
        request: HTTP request object from authenticated user

    Returns:
        HttpResponse: Rendered token accounting page with given/used token lists
    """
    ctx = def_user_ctx(request)
    ctx.update(
        {
            "given": AccountingItemOther.objects.filter(
                member=ctx["member"],
                hide=False,
                oth=OtherChoices.TOKEN,
                assoc_id=ctx["a_id"],
            ),
            "used": AccountingItemPayment.objects.filter(
                member=ctx["member"],
                hide=False,
                pay=PaymentChoices.TOKEN,
                assoc_id=ctx["a_id"],
            ),
        }
    )
    return render(request, "larpmanager/member/acc_tokens.html", ctx)


@login_required
def accounting_credits(request):
    """
    Display user's accounting credits including expenses, credits given/used, and refunds.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered accounting credits template
    """
    ctx = def_user_ctx(request)
    ctx.update(
        {
            "exp": AccountingItemExpense.objects.filter(
                member=ctx["member"], hide=False, is_approved=True, assoc_id=ctx["a_id"]
            ),
            "given": AccountingItemOther.objects.filter(
                member=ctx["member"],
                hide=False,
                oth=OtherChoices.CREDIT,
                assoc_id=ctx["a_id"],
            ),
            "used": AccountingItemPayment.objects.filter(
                member=ctx["member"],
                hide=False,
                pay=PaymentChoices.CREDIT,
                assoc_id=ctx["a_id"],
            ),
            "ref": AccountingItemOther.objects.filter(
                member=ctx["member"],
                hide=False,
                oth=OtherChoices.REFUND,
                assoc_id=ctx["a_id"],
            ),
        }
    )
    return render(request, "larpmanager/member/acc_credits.html", ctx)


@login_required
def acc_refund(request):
    """Handle refund request form processing and notifications.

    Args:
        request: HTTP request with user data

    Returns:
        HttpResponse: Refund form template or redirect after successful submission
    """
    check_assoc_feature(request, "refund")
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    ctx.update({"member": request.user.member, "a_id": request.assoc["id"]})
    get_user_membership(request.user.member, ctx["a_id"])
    if request.method == "POST":
        form = RefundRequestForm(request.POST, member=ctx["member"])
        if form.is_valid():
            with transaction.atomic():
                p = form.save(commit=False)
                p.member = ctx["member"]
                p.assoc_id = ctx["a_id"]
                p.save()
            notify_refund_request(p)
            messages.success(
                request, _("Request for reimbursement entered! You will receive notice when it is processed.") + "."
            )
            return redirect("accounting")
    else:
        form = RefundRequestForm(member=ctx["member"])
    ctx["form"] = form
    return render(request, "larpmanager/member/acc_refund.html", ctx)


@login_required
def acc_pay(request, s, method=None):
    """Handle payment redirection for event registration.

    Args:
        request: HTTP request object
        s: Event slug string
        method: Optional payment method

    Returns:
        Redirect to appropriate payment page
    """
    check_assoc_feature(request, "payment")
    ctx = get_event_run(request, s, signup=True, status=True)

    if not ctx["run"].reg:
        messages.warning(
            request, _("We cannot find your registration for this event. Are you logged in as the correct user") + "?"
        )
        return redirect("accounting")
    else:
        reg = ctx["run"].reg

    if "fiscal_code_check" in ctx["features"]:
        result = calculate_fiscal_code(ctx["member"])
        if "error_cf" in result:
            messages.warning(
                request, _("Your tax code has a problem that we ask you to correct") + ": " + result["error_cf"]
            )
            return redirect("profile")

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
def acc_donate(request):
    check_assoc_feature(request, "donate")
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    if request.method == "POST":
        form = DonateForm(request.POST, ctx=ctx)
        if form.is_valid():
            get_payment_form(request, form, PaymentType.DONATE, ctx)
    else:
        form = DonateForm(ctx=ctx)
    ctx["form"] = form
    ctx["donate"] = 1
    return render(request, "larpmanager/member/acc_donate.html", ctx)


@login_required
def acc_collection(request):
    """Handle member collection creation and payment processing.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered collection form template
    """
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    if request.method == "POST":
        form = CollectionNewForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                p = form.save(commit=False)
                p.organizer = request.user.member
                p.assoc_id = request.assoc["id"]
                p.save()
            messages.success(request, _("The collection has been activated!"))
            return redirect("acc_collection_manage", s=p.contribute_code)
    else:
        form = CollectionNewForm()
    ctx["form"] = form
    return render(request, "larpmanager/member/acc_collection.html", ctx)


@login_required
def acc_collection_manage(request, s):
    c = get_collection_partecipate(request, s)
    if request.user.member != c.organizer:
        raise Http404("Collection not yours")
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    ctx.update(
        {
            "coll": c,
            "list": AccountingItemCollection.objects.filter(collection=c, collection__assoc_id=request.assoc["id"]),
        }
    )
    return render(request, "larpmanager/member/acc_collection_manage.html", ctx)


@login_required
def acc_collection_participate(request, s):
    c = get_collection_partecipate(request, s)
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    ctx["coll"] = c
    if c.status != CollectionStatus.OPEN:
        raise Http404("Collection not open")

    if request.method == "POST":
        form = CollectionForm(request.POST, ctx=ctx)
        if form.is_valid():
            get_payment_form(request, form, PaymentType.COLLECTION, ctx)
    else:
        form = CollectionForm(ctx=ctx)
    ctx["form"] = form
    return render(request, "larpmanager/member/acc_collection_participate.html", ctx)


@login_required
def acc_collection_close(request, s):
    c = get_collection_partecipate(request, s)
    if request.user.member != c.organizer:
        raise Http404("Collection not yours")
    if c.status != CollectionStatus.OPEN:
        raise Http404("Collection not open")

    with transaction.atomic():
        c.status = CollectionStatus.DONE
        c.save()

    messages.success(request, _("Collection closed"))
    return redirect("acc_collection_manage", s=s)


@login_required
def acc_collection_redeem(request, s):
    """Handle redemption of completed accounting collections.

    Args:
        request: HTTP request object
        s: Collection slug identifier

    Returns:
        Redirect to home on POST success or rendered redemption template
    """
    c = get_collection_redeem(request, s)
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    ctx["coll"] = c
    if c.status != CollectionStatus.DONE:
        raise Http404("Collection not found")

    if request.method == "POST":
        with transaction.atomic():
            c.member = request.user.member
            c.status = CollectionStatus.PAYED
            c.save()
        messages.success(request, _("The collection has been delivered!"))
        return redirect("home")

    ctx["list"] = AccountingItemCollection.objects.filter(
        collection=c, collection__assoc_id=request.assoc["id"]
    ).select_related("member", "collection")
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
def acc_redsys_ko(request):
    # printpretty_request(request))
    # err_paypal(pretty_request(request))
    messages.error(request, _("The payment has not been completed"))
    return redirect("accounting")


@login_required
def acc_wait(request):
    return render(request, "larpmanager/member/acc_wait.html")


@login_required
def acc_cancelled(request):
    mes = _("The payment was not completed. Please contact us to find out why") + "."
    messages.warning(request, mes)
    return redirect("accounting")


def acc_profile_check(request, mes, inv):
    # check if profile is compiled
    member = request.user.member
    mb = get_user_membership(member, request.assoc["id"])

    if not mb.compiled:
        mes += " " + _("As a final step, we ask you to complete your profile") + "."
        messages.success(request, mes)
        return redirect("profile")

    messages.success(request, mes)

    return acc_redirect(inv)


def acc_redirect(inv):
    if inv.typ == PaymentType.REGISTRATION:
        reg = Registration.objects.get(id=inv.idx)
        return redirect("gallery", s=reg.run.get_slug())
    return redirect("accounting")


@login_required
def acc_payed(request, p=0):
    if p:
        try:
            inv = PaymentInvoice.objects.get(pk=p, member=request.user.member, assoc_id=request.assoc["id"])
        except Exception as err:
            raise Http404("eeeehm") from err
    else:
        inv = None

    mes = _("You have completed the payment!")
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
