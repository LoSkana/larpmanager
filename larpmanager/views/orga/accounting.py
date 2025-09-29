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
from django.urls import reverse
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
from larpmanager.templatetags.show_tags import format_decimal
from larpmanager.utils.edit import backend_get, orga_edit
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.paginate import orga_paginate


@login_required
def orga_discounts(request, s):
    ctx = check_event_permission(request, s, "orga_discounts")
    ctx["list"] = Discount.objects.filter(event=ctx["event"]).order_by("number")
    return render(request, "larpmanager/orga/accounting/discounts.html", ctx)


@login_required
def orga_discounts_edit(request, s, num):
    return orga_edit(request, s, "orga_discounts", OrgaDiscountForm, num)


@login_required
def orga_expenses_my(request, s):
    ctx = check_event_permission(request, s, "orga_expenses_my")
    ctx["list"] = AccountingItemExpense.objects.filter(run=ctx["run"], member=request.user.member).order_by("-created")
    return render(request, "larpmanager/orga/accounting/expenses_my.html", ctx)


@login_required
def orga_expenses_my_new(request, s):
    ctx = check_event_permission(request, s, "orga_expenses_my")
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
                return redirect("orga_expenses_my_new", s=ctx["run"].get_slug())
            return redirect("orga_expenses_my", s=ctx["run"].get_slug())
    else:
        form = OrgaPersonalExpenseForm(ctx=ctx)

    ctx["form"] = form
    return render(request, "larpmanager/orga/accounting/expenses_my_new.html", ctx)


@login_required
def orga_invoices(request, s):
    ctx = check_event_permission(request, s, "orga_invoices")
    que = PaymentInvoice.objects.filter(reg__run=ctx["run"], status=PaymentStatus.SUBMITTED)
    ctx["list"] = que.select_related("member", "method")
    return render(request, "larpmanager/orga/accounting/invoices.html", ctx)


@login_required
def orga_invoices_confirm(request, s, num):
    ctx = check_event_permission(request, s, "orga_invoices")
    backend_get(ctx, PaymentInvoice, num)

    if ctx["el"].reg.run != ctx["run"]:
        raise Http404("i'm sorry, what?")

    if ctx["el"].status == PaymentStatus.CREATED or ctx["el"].status == PaymentStatus.SUBMITTED:
        ctx["el"].status = PaymentStatus.CONFIRMED
    else:
        messages.warning(request, _("Receipt already confirmed") + ".")
        return redirect("orga_invoices", s=ctx["run"].get_slug())

    ctx["el"].save()
    messages.success(request, _("Element approved") + "!")
    return redirect("orga_invoices", s=ctx["run"].get_slug())


@login_required
def orga_accounting(request, s):
    ctx = check_event_permission(request, s, "orga_accounting")
    ctx["dc"] = get_run_accounting(ctx["run"], ctx)
    return render(request, "larpmanager/orga/accounting/accounting.html", ctx)


@login_required
def orga_tokens(request, s):
    ctx = check_event_permission(request, s, "orga_tokens")
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
    return orga_paginate(
        request, ctx, AccountingItemOther, "larpmanager/orga/accounting/tokens.html", "orga_tokens_edit"
    )


@login_required
def orga_tokens_edit(request, s, num):
    return orga_edit(request, s, "orga_tokens", OrgaTokenForm, num)


@login_required
def orga_credits(request, s):
    ctx = check_event_permission(request, s, "orga_credits")
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
    return orga_paginate(
        request, ctx, AccountingItemOther, "larpmanager/orga/accounting/credits.html", "orga_credits_edit"
    )


@login_required
def orga_credits_edit(request, s, num):
    return orga_edit(request, s, "orga_credits", OrgaCreditForm, num)


@login_required
def orga_payments(request, s):
    ctx = check_event_permission(request, s, "orga_payments")
    fields = [
        ("member", _("Member")),
        ("method", _("Method")),
        ("type", _("Type")),
        ("status", _("Status")),
        ("net", _("Net")),
        ("trans", _("Fee")),
        ("created", _("Date")),
    ]
    if "vat" in ctx.get("features", []):
        fields.append(("vat", _("VAT")))

    ctx.update(
        {
            "selrel": ("reg__member", "reg__run", "inv", "inv__method"),
            "afield": "reg",
            "fields": fields,
            "callbacks": {
                "member": lambda row: str(row.reg.member) if row.reg and row.reg.member else "",
                "method": lambda el: str(el.inv.method) if el.inv else "",
                "type": lambda el: el.get_pay_display(),
                "status": lambda el: el.inv.get_status_display() if el.inv else "",
                "net": lambda el: format_decimal(el.net),
                "trans": lambda el: format_decimal(el.trans) if el.trans else "",
                "vat": lambda el: format_decimal(el.vat) if el.vat else "",
            },
        }
    )
    return orga_paginate(
        request, ctx, AccountingItemPayment, "larpmanager/orga/accounting/payments.html", "orga_payments_edit"
    )


@login_required
def orga_payments_edit(request, s, num):
    return orga_edit(request, s, "orga_payments", OrgaPaymentForm, num)


@login_required
def orga_outflows(request, s):
    ctx = check_event_permission(request, s, "orga_outflows")
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
    return orga_paginate(
        request, ctx, AccountingItemOutflow, "larpmanager/orga/accounting/outflows.html", "orga_outflows_edit"
    )


@login_required
def orga_outflows_edit(request, s, num):
    return orga_edit(request, s, "orga_outflows", OrgaOutflowForm, num)


@login_required
def orga_inflows(request, s):
    ctx = check_event_permission(request, s, "orga_inflows")
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
    return orga_paginate(
        request, ctx, AccountingItemInflow, "larpmanager/orga/accounting/inflows.html", "orga_inflows_edit"
    )


@login_required
def orga_inflows_edit(request, s, num):
    return orga_edit(request, s, "orga_inflows", OrgaInflowForm, num)


@login_required
def orga_expenses(request, s):
    ctx = check_event_permission(request, s, "orga_expenses")
    ctx["disable_approval"] = ctx["event"].assoc.get_config("expense_disable_orga", False)
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
                "action": lambda el: f"<a href='{reverse('orga_expenses_approve', args=[ctx['run'].get_slug(), el.id])}'>{approve}</a>"
                if not el.is_approved and not ctx["disable_approval"]
                else "",
                "type": lambda el: el.get_exp_display(),
            },
        }
    )
    return orga_paginate(
        request, ctx, AccountingItemExpense, "larpmanager/orga/accounting/expenses.html", "orga_expenses_edit"
    )


@login_required
def orga_expenses_edit(request, s, num):
    return orga_edit(request, s, "orga_expenses", OrgaExpenseForm, num)


@login_required
def orga_expenses_approve(request, s, num):
    ctx = check_event_permission(request, s, "orga_expenses")
    if ctx["event"].assoc.get_config("expense_disable_orga", False):
        raise Http404("eh no caro mio")

    try:
        exp = AccountingItemExpense.objects.get(pk=num)
    except Exception as err:
        raise Http404("no id expense") from err

    if exp.run.event != ctx["event"]:
        raise Http404("not your orga")

    exp.is_approved = True
    exp.save()
    messages.success(request, _("Request approved"))
    return redirect("orga_expenses", s=ctx["run"].get_slug())
