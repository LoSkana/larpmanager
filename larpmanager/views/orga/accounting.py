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
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.balance import get_run_accounting
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
from larpmanager.utils.edit import backend_get, orga_edit
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.paginate import orga_paginate


@login_required
def orga_discounts(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_discounts")
    ctx["list"] = Discount.objects.filter(event=ctx["event"]).order_by("number")
    return render(request, "larpmanager/orga/accounting/discounts.html", ctx)


@login_required
def orga_discounts_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_discounts", OrgaDiscountForm, num)


@login_required
def orga_expenses_my(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_expenses_my")
    ctx["list"] = AccountingItemExpense.objects.filter(run=ctx["run"], member=request.user.member).order_by("-created")
    return render(request, "larpmanager/orga/accounting/expenses_my.html", ctx)


@login_required
def orga_expenses_my_new(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_expenses_my")
    if request.method == "POST":
        form = OrgaPersonalExpenseForm(request.POST, request.FILES, ctx=ctx)
        if form.is_valid():
            exp = form.save(commit=False)
            exp.run = ctx["run"]
            exp.member = request.user.member
            exp.assoc_id = request.assoc["id"]
            exp.save()
            messages.success(request, _("Reimbursement request item added"))

            if "continue" in request.POST:
                return redirect("orga_expenses_my_new", s=ctx["event"].slug, n=ctx["run"].number)
            return redirect("orga_expenses_my", s=ctx["event"].slug, n=ctx["run"].number)
    else:
        form = OrgaPersonalExpenseForm(ctx=ctx)

    ctx["form"] = form
    return render(request, "larpmanager/orga/accounting/expenses_my_new.html", ctx)


@login_required
def orga_invoices(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_invoices")
    que = PaymentInvoice.objects.filter(reg__run=ctx["run"], status=PaymentStatus.SUBMITTED)
    ctx["list"] = que.select_related("member", "method")
    return render(request, "larpmanager/orga/accounting/invoices.html", ctx)


@login_required
def orga_invoices_confirm(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_invoices")
    backend_get(ctx, PaymentInvoice, num)

    if ctx["el"].reg.run != ctx["run"]:
        raise Http404("i'm sorry, what?")

    if ctx["el"].status == PaymentStatus.CREATED or ctx["el"].status == PaymentStatus.SUBMITTED:
        ctx["el"].status = PaymentStatus.CONFIRMED
    else:
        messages.warning(request, _("Receipt already confirmed") + ".")
        return redirect("orga_invoices", s=ctx["event"].slug, n=ctx["run"].number)

    ctx["el"].save()
    messages.success(request, _("Element approved") + "!")
    return redirect("orga_invoices", s=ctx["event"].slug, n=ctx["run"].number)


@login_required
def orga_accounting(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_accounting")
    ctx["dc"] = get_run_accounting(ctx["run"], ctx)
    return render(request, "larpmanager/orga/accounting/accounting.html", ctx)


@login_required
def orga_tokens(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_tokens")
    orga_paginate(request, ctx, AccountingItemOther, selrel=("run", "run__event"), subtype="tokens")
    return render(request, "larpmanager/orga/accounting/tokens.html", ctx)


@login_required
def orga_tokens_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_tokens", OrgaTokenForm, num)


@login_required
def orga_credits(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_credits")
    orga_paginate(request, ctx, AccountingItemOther, selrel=("run", "run__event"), subtype="credits")
    return render(request, "larpmanager/orga/accounting/credits.html", ctx)


@login_required
def orga_credits_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_credits", OrgaCreditForm, num)


@login_required
def orga_payments(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_payments")
    sr = ("reg__member", "reg__run", "inv", "inv__method")
    orga_paginate(request, ctx, AccountingItemPayment, selrel=sr, afield="reg")
    return render(request, "larpmanager/orga/accounting/payments.html", ctx)


@login_required
def orga_payments_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_payments", OrgaPaymentForm, num)


@login_required
def orga_outflows(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_outflows")
    orga_paginate(request, ctx, AccountingItemOutflow, selrel=("run", "run__event"))
    return render(request, "larpmanager/orga/accounting/outflows.html", ctx)


@login_required
def orga_outflows_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_outflows", OrgaOutflowForm, num)


@login_required
def orga_inflows(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_inflows")
    orga_paginate(request, ctx, AccountingItemInflow, selrel=("run", "run__event"))
    return render(request, "larpmanager/orga/accounting/inflows.html", ctx)


@login_required
def orga_inflows_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_inflows", OrgaInflowForm, num)


@login_required
def orga_expenses(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_expenses")
    orga_paginate(request, ctx, AccountingItemExpense, selrel=("run", "run__event"))
    return render(request, "larpmanager/orga/accounting/expenses.html", ctx)


@login_required
def orga_expenses_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_expenses", OrgaExpenseForm, num)


@login_required
def orga_expenses_approve(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_expenses")
    try:
        exp = AccountingItemExpense.objects.get(pk=num)
    except Exception as err:
        raise Http404("no id expense") from err

    if exp.run.event != ctx["event"]:
        raise Http404("not your orga")

    exp.is_approved = True
    exp.save()
    messages.success(request, _("Request approved"))
    return redirect("orga_expenses", s=ctx["event"].slug, n=ctx["run"].number)
