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
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt

from larpmanager.accounting.gateway import (
    redsys_webhook,
    satispay_check,
    satispay_webhook,
    stripe_webhook,
    sumup_webhook,
)
from larpmanager.accounting.invoice import invoice_received_money
from larpmanager.accounting.member import info_accounting
from larpmanager.accounting.payment import get_payment_form
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
from larpmanager.forms.member import (
    MembershipForm,
)
from larpmanager.mail.accounting import notify_invoice_check, notify_refund_request
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemExpense,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemPayment,
    Collection,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.association import Association
from larpmanager.models.member import Member, MembershipStatus, get_user_membership
from larpmanager.models.registration import (
    Registration,
)
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.common import (
    get_assoc,
    get_collection_partecipate,
    get_collection_redeem,
)
from larpmanager.utils.event import check_event_permission, get_event_run
from larpmanager.utils.exceptions import (
    check_assoc_feature,
)
from larpmanager.utils.fiscal_code import calculate_fiscal_code


@login_required
def accounting(request):
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

    return render(request, "larpmanager/member/accounting.html", ctx)


@login_required
def accounting_tokens(request):
    ctx = def_user_ctx(request)
    ctx.update(
        {
            "given": AccountingItemOther.objects.filter(
                member=ctx["member"],
                hide=False,
                oth=AccountingItemOther.TOKEN,
                assoc_id=ctx["a_id"],
            ),
            "used": AccountingItemPayment.objects.filter(
                member=ctx["member"],
                hide=False,
                pay=AccountingItemPayment.TOKEN,
                assoc_id=ctx["a_id"],
            ),
        }
    )
    return render(request, "larpmanager/member/acc_tokens.html", ctx)


@login_required
def accounting_credits(request):
    ctx = def_user_ctx(request)
    ctx.update(
        {
            "exp": AccountingItemExpense.objects.filter(
                member=ctx["member"], hide=False, is_approved=True, assoc_id=ctx["a_id"]
            ),
            "given": AccountingItemOther.objects.filter(
                member=ctx["member"],
                hide=False,
                oth=AccountingItemOther.CREDIT,
                assoc_id=ctx["a_id"],
            ),
            "used": AccountingItemPayment.objects.filter(
                member=ctx["member"],
                hide=False,
                pay=AccountingItemPayment.CREDIT,
                assoc_id=ctx["a_id"],
            ),
            "ref": AccountingItemOther.objects.filter(
                member=ctx["member"],
                hide=False,
                oth=AccountingItemOther.REFUND,
                assoc_id=ctx["a_id"],
            ),
        }
    )
    return render(request, "larpmanager/member/acc_credits.html", ctx)


@login_required
def acc_refund(request):
    check_assoc_feature(request, "refund")
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    ctx.update({"member": request.user.member, "a_id": request.assoc["id"]})
    get_user_membership(request.user.member, ctx["a_id"])
    if request.method == "POST":
        form = RefundRequestForm(request.POST, member=ctx["member"])
        if form.is_valid():
            p = form.save(commit=False)
            p.member = ctx["member"]
            p.assoc_id = ctx["a_id"]
            p.save()
            notify_refund_request(p)
            messages.success(
                request, _("Request for reimbursement entered! You will receive notice when it is disbursed.")
            )
            return redirect("accounting")
    else:
        form = RefundRequestForm(member=ctx["member"])
    ctx["form"] = form
    return render(request, "larpmanager/member/acc_refund.html", ctx)


@login_required
def acc_pay(request, s, n, method=None):
    check_assoc_feature(request, "payment")
    ctx = get_event_run(request, s, n, signup=True, status=True)

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
def acc_reg(request, reg_id, method=None):
    check_assoc_feature(request, "payment")

    try:
        reg = Registration.objects.select_related("run", "run__event").get(
            id=reg_id,
            member=request.user.member,
            cancellation_date__isnull=True,
            run__event__assoc_id=request.assoc["id"],
        )
    except Exception as err:
        raise Http404(f"registration not found {err}") from err

    ctx = get_event_run(request, reg.run.event.slug, reg.run.number)
    ctx["show_accounting"] = True

    reg.membership = get_user_membership(reg.member, request.assoc["id"])

    if reg.tot_iscr == reg.tot_payed:
        messages.success(request, _("Everything is in order about the payment of this event") + "!")
        return redirect("gallery", s=reg.run.event.slug, n=reg.run.number)

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
        return redirect("gallery", s=reg.run.event.slug, n=reg.run.number)

    if "membership" in ctx["features"] and not reg.membership.date:
        mes = _("To be able to pay, your membership application must be approved.")
        messages.warning(request, mes)
        return redirect("gallery", s=reg.run.event.slug, n=reg.run.number)

    ctx["reg"] = reg

    if reg.quota:
        ctx["quota"] = reg.quota
    else:
        ctx["quota"] = reg.tot_iscr - reg.tot_payed

    key = f"{reg.id}_{reg.num_payments}"

    ctx["association"] = Association.objects.get(pk=ctx["a_id"])
    ctx["hide_amount"] = ctx["association"].get_config("payment_hide_amount", False)

    if method:
        ctx["def_method"] = method

    if request.method == "POST":
        form = PaymentForm(request.POST, reg=reg, ctx=ctx)
        if form.is_valid():
            get_payment_form(request, form, PaymentType.REGISTRATION, ctx, key)
    else:
        form = PaymentForm(reg=reg, ctx=ctx)
    ctx["form"] = form

    return render(request, "larpmanager/member/acc_reg.html", ctx)


@login_required
def acc_membership(request, method=None):
    check_assoc_feature(request, "membership")
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    memb = get_user_membership(request.user.member, request.assoc["id"])
    if memb.status != MembershipStatus.ACCEPTED:
        messages.success(request, _("It is not possible for you to pay dues at this time."))
        return redirect("accounting")

    year = datetime.now().year
    try:
        AccountingItemMembership.objects.get(year=year, member=request.user.member, assoc_id=request.assoc["id"])
        messages.success(request, _("You have already paid this year's membership fee"))
        return redirect("accounting")
    except Exception:
        pass

    ctx["year"] = year

    key = f"{request.user.member.id}_{year}"

    if method:
        ctx["def_method"] = method

    if request.method == "POST":
        form = MembershipForm(request.POST, ctx=ctx)
        if form.is_valid():
            get_payment_form(request, form, PaymentType.MEMBERSHIP, ctx, key)
    else:
        form = MembershipForm(ctx=ctx)
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
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    if request.method == "POST":
        form = CollectionNewForm(request.POST)
        if form.is_valid():
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
    if c.status != Collection.OPEN:
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
    if c.status != Collection.OPEN:
        raise Http404("Collection not open")

    c.status = Collection.DONE
    c.save()

    messages.success(request, _("Collection closed"))
    return redirect("acc_collection_manage", s=s)


@login_required
def acc_collection_redeem(request, s):
    c = get_collection_redeem(request, s)
    ctx = def_user_ctx(request)
    ctx["show_accounting"] = True
    ctx["coll"] = c
    if c.status != Collection.DONE:
        raise Http404("Collection not found")

    if request.method == "POST":
        c.member = request.user.member
        c.status = Collection.PAYED
        c.save()
        messages.success(request, _("The collection has been delivered!"))
        return redirect("home")

    ctx["list"] = AccountingItemCollection.objects.filter(collection=c, collection__assoc_id=request.assoc["id"])
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
    mes = _("The payment was not completed. Please contact us to find out why.")
    messages.warning(request, mes)
    return redirect("accounting")


def acc_profile_check(request, mes, inv):
    # check if profile is compiled
    member = request.user.member
    mb = get_user_membership(member, request.assoc["id"])

    if not mb.compiled:
        mes += " " + _("As a final step, we ask you to complete your profile.")
        messages.success(request, mes)
        return redirect("profile")

    messages.success(request, mes)

    return acc_redirect(inv)


def acc_redirect(inv):
    if inv.typ == PaymentType.REGISTRATION:
        reg = Registration.objects.get(id=inv.idx)
        return redirect("gallery", s=reg.run.event.slug, n=reg.run.number)
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

    ctx = def_user_ctx(request)
    satispay_check(request, ctx)
    mes = _("You have completed the payment!")
    return acc_profile_check(request, mes, inv)


@login_required
def acc_submit(request, s, p):
    if not request.method == "POST":
        messages.error(request, _("You can't access this way!"))
        return redirect("accounting")

    if s in {"wire", "paypal_nf"}:
        form = WireInvoiceSubmitForm(request.POST, request.FILES)
    elif s == "any":
        form = AnyInvoiceSubmitForm(request.POST, request.FILES)
    else:
        raise Http404("unknown value: " + s)

    if not form.is_valid():
        # print(form.errors)
        mes = _("Error loading. Invalid file format (we accept only pdf or images).")
        messages.error(request, mes)
        return redirect("/" + p)

    try:
        inv = PaymentInvoice.objects.get(cod=form.cleaned_data["cod"], assoc_id=request.assoc["id"])
    except ObjectDoesNotExist:
        messages.error(request, _("Error processing payment, contact us"))
        return redirect("/" + p)

    if s in {"wire", "paypal_nf"}:
        inv.invoice = form.cleaned_data["invoice"]
    elif s == "any":
        inv.text = form.cleaned_data["text"]

    inv.status = PaymentStatus.SUBMITTED

    inv.txn_id = datetime.now().timestamp()
    inv.save()

    notify_invoice_check(inv)

    mes = _("Payment received! As soon as it is approved, your accounts will be updated.")
    return acc_profile_check(request, mes, inv)


@login_required
def acc_confirm(request, c):
    try:
        inv = PaymentInvoice.objects.get(cod=c, assoc_id=request.assoc["id"])
    except ObjectDoesNotExist:
        messages.error(request, _("Invoice not found"))
        return redirect("home")

    if inv.status != PaymentStatus.SUBMITTED:
        messages.error(request, _("Invoice already confirmed"))
        return redirect("home")

    # check authorization
    found = False
    assoc = Association.objects.get(pk=request.assoc["id"])
    if "treasurer" in get_assoc_features(assoc.id):
        for mb in assoc.get_config("treasurer_appointees", "").split(", "):
            if not mb:
                continue
            if request.user.member.id == int(mb):
                found = True

    if not found:
        if inv.typ == PaymentType.REGISTRATION:
            reg = Registration.objects.get(pk=inv.idx)
            check_event_permission(request, reg.run.event.slug, reg.run.number)

    inv.status = PaymentStatus.CONFIRMED
    inv.save()

    messages.success(request, _("Payment confirmed"))
    return redirect("home")


def add_runs(ls, lis, future=True):
    for e in lis:
        for r in e.runs.all():
            if future and r.end < date.today():
                continue
            ls[r.id] = r
