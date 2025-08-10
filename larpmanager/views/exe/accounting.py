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
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.balance import assoc_accounting, assoc_accounting_data, check_accounting, get_run_accounting
from larpmanager.accounting.invoice import invoice_verify
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
from larpmanager.forms.writing import (
    UploadElementsForm,
)
from larpmanager.models.accounting import (
    AccountingItem,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemInflow,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemOutflow,
    AccountingItemPayment,
    AccountingItemTransaction,
    Collection,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
    RecordAccounting,
    RefundRequest,
    RefundStatus,
)
from larpmanager.models.association import Association
from larpmanager.models.event import (
    Run,
)
from larpmanager.models.registration import (
    Registration,
)
from larpmanager.models.utils import get_sum
from larpmanager.utils.base import check_assoc_permission
from larpmanager.utils.edit import backend_get, exe_edit
from larpmanager.utils.paginate import exe_paginate
from larpmanager.views.orga.accounting import assign_payment_fee


@login_required
def exe_outflows(request):
    ctx = check_assoc_permission(request, "exe_outflows")
    exe_paginate(request, ctx, AccountingItemOutflow, selrel=("run", "run__event"))
    return render(request, "larpmanager/exe/accounting/outflows.html", ctx)


@login_required
def exe_outflows_edit(request, num):
    return exe_edit(request, ExeOutflowForm, num, "exe_outflows")


@login_required
def exe_inflows(request):
    ctx = check_assoc_permission(request, "exe_inflows")
    exe_paginate(request, ctx, AccountingItemInflow, selrel=("run", "run__event"))
    return render(request, "larpmanager/exe/accounting/inflows.html", ctx)


@login_required
def exe_inflows_edit(request, num):
    return exe_edit(request, ExeInflowForm, num, "exe_inflows")


@login_required
def exe_donations(request):
    ctx = check_assoc_permission(request, "exe_donations")
    exe_paginate(request, ctx, AccountingItemDonation, show_runs=False)
    return render(request, "larpmanager/exe/accounting/donations.html", ctx)


@login_required
def exe_donations_edit(request, num):
    return exe_edit(request, ExeDonationForm, num, "exe_donations")


@login_required
def exe_credits(request):
    ctx = check_assoc_permission(request, "exe_credits")
    exe_paginate(request, ctx, AccountingItemOther, selrel=("run", "run__event"), subtype="credits")
    return render(request, "larpmanager/exe/accounting/credits.html", ctx)


@login_required
def exe_credits_edit(request, num):
    return exe_edit(request, ExeCreditForm, num, "exe_credits")


@login_required
def exe_tokens(request):
    ctx = check_assoc_permission(request, "exe_tokens")
    exe_paginate(request, ctx, AccountingItemOther, selrel=("run", "run__event"), subtype="tokens")
    return render(request, "larpmanager/exe/accounting/tokens.html", ctx)


@login_required
def exe_tokens_edit(request, num):
    return exe_edit(request, ExeTokenForm, num, "exe_tokens")


@login_required
def exe_expenses(request):
    ctx = check_assoc_permission(request, "exe_expenses")
    exe_paginate(request, ctx, AccountingItemExpense, selrel=("run", "run__event"))
    return render(request, "larpmanager/exe/accounting/expenses.html", ctx)


@login_required
def exe_expenses_edit(request, num):
    return exe_edit(request, ExeExpenseForm, num, "exe_expenses")


@login_required
def exe_expenses_approve(request, num):
    check_assoc_permission(request, "exe_expenses")
    try:
        exp = AccountingItemExpense.objects.get(pk=num)
    except Exception as err:
        raise Http404("no id expense") from err

    if exp.assoc_id != request.assoc["id"]:
        raise Http404("not your orga")

    exp.is_approved = True
    exp.save()
    messages.success(request, _("Request approved"))
    return redirect("exe_expenses")


@login_required
def exe_payments(request):
    ctx = check_assoc_permission(request, "exe_payments")
    sr = ("reg__member", "reg__run", "inv", "inv__method")
    exe_paginate(request, ctx, AccountingItemPayment, selrel=sr, afield="reg")
    assign_payment_fee(ctx)
    return render(request, "larpmanager/exe/accounting/payments.html", ctx)


@login_required
def exe_payments_edit(request, num):
    return exe_edit(request, ExePaymentForm, num, "exe_payments")


@login_required
def exe_invoices(request):
    ctx = check_assoc_permission(request, "exe_invoices")
    sr = ("method", "member")
    exe_paginate(request, ctx, PaymentInvoice, show_runs=False, selrel=sr)
    return render(request, "larpmanager/exe/accounting/invoices.html", ctx)


@login_required
def exe_invoices_edit(request, num):
    return exe_edit(request, ExeInvoiceForm, num, "exe_invoices")


@login_required
def exe_invoices_confirm(request, num):
    ctx = check_assoc_permission(request, "exe_invoices")
    backend_get(ctx, PaymentInvoice, num)

    if ctx["el"].status == PaymentStatus.CREATED or ctx["el"].status == PaymentStatus.SUBMITTED:
        ctx["el"].status = PaymentStatus.CONFIRMED
    else:
        raise Http404("already done")

    ctx["el"].save()
    messages.success(request, _("Element approved") + "!")
    return redirect("exe_invoices")


@login_required
def exe_collections(request):
    ctx = check_assoc_permission(request, "exe_collections")
    ctx["list"] = (
        Collection.objects.filter(assoc_id=ctx["a_id"]).select_related("member", "organizer").order_by("-created")
    )
    return render(request, "larpmanager/exe/accounting/collections.html", ctx)


@login_required
def exe_collections_edit(request, num):
    return exe_edit(request, ExeCollectionForm, num, "exe_collections")


@login_required
def exe_refunds(request):
    ctx = check_assoc_permission(request, "exe_refunds")
    exe_paginate(
        request,
        ctx,
        RefundRequest,
        show_runs=False,
    )
    return render(request, "larpmanager/exe/accounting/refunds.html", ctx)


@login_required
def exe_refunds_edit(request, num):
    return exe_edit(request, ExeRefundRequestForm, num, "exe_refunds")


@login_required
def exe_refunds_confirm(request, num):
    ctx = check_assoc_permission(request, "exe_refunds")
    backend_get(ctx, RefundRequest, num)

    if ctx["el"].status == RefundStatus.REQUEST:
        ctx["el"].status = RefundStatus.PAYED
    else:
        raise Http404("already done")

    ctx["el"].save()
    messages.success(request, _("Element approved") + "!")
    return redirect("exe_refunds")


@login_required
def exe_accounting(request):
    ctx = check_assoc_permission(request, "exe_accounting")
    assoc_accounting(ctx)
    return render(request, "larpmanager/exe/accounting/accounting.html", ctx)


@login_required
def exe_year_accounting(request):
    ctx = check_assoc_permission(request, "exe_accounting")
    year = int(request.POST.get("year"))
    res = {"a_id": ctx["a_id"]}
    assoc_accounting_data(res, year)
    return JsonResponse({"res": res})


@login_required
def exe_run_accounting(request, num):
    ctx = check_assoc_permission(request, "exe_accounting")
    ctx["run"] = Run.objects.get(pk=num)
    if ctx["run"].event.assoc_id != ctx["a_id"]:
        raise Http404("not your run")
    ctx["dc"] = get_run_accounting(ctx["run"], ctx)
    return render(request, "larpmanager/orga/accounting/accounting.html", ctx)


@login_required
def exe_accounting_rec(request):
    ctx = check_assoc_permission(request, "exe_accounting_rec")
    ctx["list"] = RecordAccounting.objects.filter(assoc_id=ctx["a_id"], run__isnull=True).order_by("created")
    if len(ctx["list"]) == 0:
        check_accounting(ctx["a_id"])
        return redirect("exe_accounting_rec")
    ctx["start"] = ctx["list"][0].created
    ctx["end"] = ctx["list"].reverse()[0].created
    return render(request, "larpmanager/exe/accounting/accounting_rec.html", ctx)


def check_year(request, ctx):
    assoc = Association.objects.get(pk=ctx["a_id"])
    ctx["years"] = list(range(datetime.today().year, assoc.created.year - 1, -1))

    if request.POST:
        ctx["year"] = int(request.POST.get("year"))
    else:
        ctx["year"] = ctx["years"][0]

    return ctx["year"]


@login_required
def exe_balance(request):
    ctx = check_assoc_permission(request, "exe_balance")
    year = check_year(request, ctx)

    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    # get total membership for that year
    ctx["memberships"] = get_sum(AccountingItemMembership.objects.filter(assoc_id=ctx["a_id"], year=year))
    ctx["donations"] = get_sum(
        AccountingItemDonation.objects.filter(assoc_id=ctx["a_id"], created__gte=start, created__lt=end)
    )
    ctx["tickets"] = get_sum(
        AccountingItemPayment.objects.filter(
            assoc_id=ctx["a_id"],
            pay=AccountingItemPayment.MONEY,
            created__gte=start,
            created__lt=end,
        )
    ) - get_sum(AccountingItemTransaction.objects.filter(assoc_id=ctx["a_id"], created__gte=start, created__lt=end))
    ctx["inflows"] = get_sum(
        AccountingItemInflow.objects.filter(assoc_id=ctx["a_id"], payment_date__gte=start, payment_date__lt=end)
    )

    ctx["in"] = ctx["memberships"] + ctx["donations"] + ctx["tickets"] + ctx["inflows"]

    ctx["expenditure"] = {}
    ctx["out"] = 0

    ctx["rimb"] = get_sum(
        AccountingItemOther.objects.filter(
            assoc_id=ctx["a_id"],
            created__gte=start,
            created__lt=end,
            oth=AccountingItemOther.REFUND,
        )
    )

    # add personal expenses
    for el in AccountingItem.BALANCE_CHOICES:
        (bl, descr) = el
        ctx["expenditure"][bl] = {"name": descr, "value": 0}

    for el in (
        AccountingItemExpense.objects.filter(
            assoc_id=ctx["a_id"], created__gte=start, created__lt=end, is_approved=True
        )
        .values("balance")
        .annotate(Sum("value"))
    ):
        value = el["value__sum"]
        bl = el["balance"]
        ctx["expenditure"][bl]["value"] = value
        ctx["out"] += value

    tot = ctx["out"]
    ctx["out"] = 0
    if tot:
        # round for actual reimbursed
        for el in AccountingItem.BALANCE_CHOICES:
            (bl, descr) = el
            v = ctx["expenditure"][bl]["value"]
            # resample value on given out credits
            v = (v / tot) * ctx["rimb"]
            ctx["out"] += v
            ctx["expenditure"][bl]["value"] = v

    # add normaly association outflows
    for el in (
        AccountingItemOutflow.objects.filter(assoc_id=ctx["a_id"], payment_date__gte=start, payment_date__lt=end)
        .values("balance")
        .annotate(Sum("value"))
    ):
        value = el["value__sum"]
        bl = el["balance"]
        ctx["expenditure"][bl]["value"] += value
        ctx["out"] += value

    ctx["bal"] = ctx["in"] - ctx["out"]

    return render(request, "larpmanager/exe/accounting/balance.html", ctx)


@login_required
def exe_verification(request):
    ctx = check_assoc_permission(request, "exe_verification")

    ctx["todo"] = (
        PaymentInvoice.objects.filter(assoc_id=ctx["a_id"], verified=False)
        .exclude(status=PaymentStatus.CREATED)
        .exclude(method__slug__in=["redsys", "satispay", "paypal", "stripe", "sumup"])
        .select_related("method")
    )

    check = [el.id for el in ctx["todo"] if el.typ == PaymentType.REGISTRATION]

    payments = AccountingItemPayment.objects.filter(inv_id__in=check)

    aux = {acc.inv_id: f"{acc.reg.run_id}-{acc.member_id}" for acc in payments}
    run_ids = {acc.reg.run_id for acc in payments}
    member_ids = {acc.member_id for acc in payments}

    cache = {
        f"{reg.run_id}-{reg.member_id}": reg.special_cod
        for reg in Registration.objects.filter(run_id__in=run_ids, member_id__in=member_ids)
    }

    for el in ctx["todo"]:
        el.reg_cod = cache.get(aux.get(el.id))

    if request.method == "POST":
        form = UploadElementsForm(request.POST, request.FILES, only_one=True)
        if form.is_valid():
            counter = invoice_verify(request, ctx, request.FILES["first"])
            messages.success(request, _("Verified payments") + "!" + " " + str(counter))
            return redirect("exe_verification")

    else:
        form = UploadElementsForm(only_one=True)

    ctx["form"] = form

    return render(request, "larpmanager/exe/verification.html", ctx)


@login_required
def exe_verification_manual(request, num):
    ctx = check_assoc_permission(request, "exe_verification")
    invoice = PaymentInvoice.objects.get(pk=num)

    if invoice.assoc_id != ctx["a_id"]:
        raise Http404("not your assoc!")

    if invoice.verified:
        messages.warning(request, _("Payment already confirmed"))
        return redirect("exe_verification")

    invoice.verified = True
    invoice.save()
    messages.success(request, _("Payment confirmed"))
    return redirect("exe_verification")
