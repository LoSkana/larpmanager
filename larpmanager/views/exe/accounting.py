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
from django.urls import reverse
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
from larpmanager.utils.base import check_assoc_permission
from larpmanager.utils.edit import backend_get, exe_edit
from larpmanager.utils.paginate import exe_paginate


@login_required
def exe_outflows(request):
    """Display paginated list of accounting outflows for association.

    Args:
        request: Django HTTP request object (must be authenticated)

    Returns:
        HttpResponse: Rendered outflows list template
    """
    ctx = check_assoc_permission(request, "exe_outflows")
    ctx.update(
        {
            "selrel": ("run", "run__event"),
            "fields": [
                ("run", _("Event")),
                ("type", _("Type")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("payment_date", _("Date")),
                ("statement", _("Statement")),
            ],
            "callbacks": {
                "statement": lambda el: f"<a href='{el.download()}'>Download</a>",
                "type": lambda el: el.get_exp_display(),
            },
        }
    )
    return exe_paginate(
        request, ctx, AccountingItemOutflow, "larpmanager/exe/accounting/outflows.html", "exe_outflows_edit"
    )


@login_required
def exe_outflows_edit(request, num):
    """Edit accounting outflow record.

    Args:
        request: Django HTTP request object (must be authenticated)
        num (int): Outflow record ID

    Returns:
        HttpResponse: Edit form or redirect after save
    """
    return exe_edit(request, ExeOutflowForm, num, "exe_outflows")


@login_required
def exe_inflows(request):
    """Display paginated list of accounting inflows for association.

    Args:
        request: Django HTTP request object (must be authenticated)

    Returns:
        HttpResponse: Rendered inflows list template
    """
    ctx = check_assoc_permission(request, "exe_inflows")
    ctx.update(
        {
            "selrel": ("run", "run__event"),
            "fields": [
                ("run", _("Event")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("payment_date", _("Date")),
                ("statement", _("Statement")),
            ],
            "callbacks": {
                "statement": lambda el: f"<a href='{el.download()}'>Download</a>",
            },
        }
    )
    return exe_paginate(
        request, ctx, AccountingItemInflow, "larpmanager/exe/accounting/inflows.html", "exe_inflows_edit"
    )


@login_required
def exe_inflows_edit(request, num):
    return exe_edit(request, ExeInflowForm, num, "exe_inflows")


@login_required
def exe_donations(request):
    """Display paginated list of donations for association.

    Args:
        request: Django HTTP request object (must be authenticated)

    Returns:
        HttpResponse: Rendered donations list template
    """
    ctx = check_assoc_permission(request, "exe_donations")
    ctx.update(
        {
            "fields": [
                ("member", _("Member")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("date", _("Date")),
            ],
        }
    )
    return exe_paginate(
        request, ctx, AccountingItemDonation, "larpmanager/exe/accounting/donations.html", "exe_donations_edit"
    )


@login_required
def exe_donations_edit(request, num):
    return exe_edit(request, ExeDonationForm, num, "exe_donations")


@login_required
def exe_credits(request):
    ctx = check_assoc_permission(request, "exe_credits")
    ctx.update(
        {
            "selrel": ("run", "run__event"),
            "subtype": "credits",
            "fields": [
                ("member", _("Member")),
                ("run", _("Event")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("created", _("Date")),
            ],
        }
    )
    return exe_paginate(
        request, ctx, AccountingItemOther, "larpmanager/exe/accounting/credits.html", "exe_credits_edit"
    )


@login_required
def exe_credits_edit(request, num):
    return exe_edit(request, ExeCreditForm, num, "exe_credits")


@login_required
def exe_tokens(request):
    ctx = check_assoc_permission(request, "exe_tokens")

    ctx.update(
        {
            "selrel": ("run", "run__event"),
            "subtype": "tokens",
            "fields": [
                ("member", _("Member")),
                ("run", _("Event")),
                ("descr", _("Description")),
                ("value", _("Value")),
                ("created", _("Date")),
            ],
        }
    )
    return exe_paginate(request, ctx, AccountingItemOther, "larpmanager/exe/accounting/tokens.html", "exe_tokens_edit")


@login_required
def exe_tokens_edit(request, num):
    return exe_edit(request, ExeTokenForm, num, "exe_tokens")


@login_required
def exe_expenses(request):
    ctx = check_assoc_permission(request, "exe_expenses")
    approve = _("Approve")
    ctx.update(
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
            "callbacks": {
                "statement": lambda el: f"<a href='{el.download()}'>Download</a>",
                "action": lambda el: f"<a href='{reverse('exe_expenses_approve', args=[el.id])}'>{approve}</a>"
                if not el.is_approved
                else "",
                "type": lambda el: el.get_exp_display(),
            },
        }
    )
    return exe_paginate(
        request, ctx, AccountingItemExpense, "larpmanager/exe/accounting/expenses.html", "exe_expenses_edit"
    )


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
    fields = [
        ("member", _("Member")),
        ("method", _("Method")),
        ("type", _("Type")),
        ("status", _("Status")),
        ("run", _("Event")),
        ("net", _("Net")),
        ("trans", _("Fee")),
        ("created", _("Date")),
    ]
    if "vat" in ctx["features"]:
        fields.append(("vat", _("VAT")))

    ctx.update(
        {
            "selrel": ("reg__member", "reg__run", "inv", "inv__method"),
            "afield": "reg",
            "fields": fields,
            "callbacks": {
                "run": lambda row: str(row.reg.run) if row.reg and row.reg.run else "",
                "method": lambda el: str(el.inv.method) if el.inv else "",
                "type": lambda el: el.get_pay_display(),
                "status": lambda el: el.inv.get_status_display() if el.inv else "",
                "net": lambda el: format_decimal(el.net),
                "trans": lambda el: format_decimal(el.trans) if el.trans else "",
                "vat": lambda el: format_decimal(el.vat) if el.vat else "",
            },
        }
    )
    return exe_paginate(
        request, ctx, AccountingItemPayment, "larpmanager/exe/accounting/payments.html", "exe_payments_edit"
    )


@login_required
def exe_payments_edit(request, num):
    return exe_edit(request, ExePaymentForm, num, "exe_payments")


@login_required
def exe_invoices(request):
    ctx = check_assoc_permission(request, "exe_invoices")
    confirm = _("Confirm")
    ctx.update(
        {
            "selrel": ("method", "member"),
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
            "callbacks": {
                "method": lambda el: str(el.method),
                "type": lambda el: el.get_typ_display(),
                "status": lambda el: el.get_status_display(),
                "gross": lambda el: format_decimal(el.mc_gross),
                "trans": lambda el: format_decimal(el.mc_fee) if el.mc_fee else "",
                "causal": lambda el: el.causal,
                "details": lambda el: el.get_details(),
                "action": lambda el: f"<a href='{reverse('exe_invoices_confirm', args=[el.id])}'>{confirm}</a>"
                if el.status == PaymentStatus.SUBMITTED
                else "",
            },
        }
    )
    return exe_paginate(request, ctx, PaymentInvoice, "larpmanager/exe/accounting/invoices.html", "exe_invoices_edit")


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
    try:
        year = int(request.POST.get("year"))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid year parameter"}, status=400)
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
        try:
            ctx["year"] = int(request.POST.get("year"))
        except (ValueError, TypeError):
            ctx["year"] = ctx["years"][0]
    else:
        ctx["year"] = ctx["years"][0]

    return ctx["year"]


@login_required
def exe_balance(request):
    """Executive view for displaying association balance sheet for a specific year.

    Calculates totals for memberships, donations, tickets, and expenses from
    various accounting models to generate comprehensive financial reporting.

    Args:
        request: Django HTTP request object with user authentication and year parameter

    Returns:
        HttpResponse: Rendered balance sheet template with financial data
    """
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
            pay=PaymentChoices.MONEY,
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
            oth=OtherChoices.REFUND,
        )
    )

    # add personal expenses
    for value, label in BalanceChoices.choices:
        ctx["expenditure"][value] = {"name": label, "value": 0}

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
        for bl, _descr in BalanceChoices.choices:
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
    """Handle payment verification process with invoice upload and processing.

    Args:
        request: HTTP request object with file upload capability

    Returns:
        Rendered verification template with pending payments and upload form
    """
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
