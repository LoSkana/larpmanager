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
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.registration import (
    OrgaRegistrationInstallmentForm,
    OrgaRegistrationOptionForm,
    OrgaRegistrationQuestionForm,
    OrgaRegistrationQuotaForm,
    OrgaRegistrationSectionForm,
    OrgaRegistrationSurchargeForm,
    OrgaRegistrationTicketForm,
)
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationOption,
    RegistrationQuestion,
    get_ordered_registration_questions,
)
from larpmanager.models.registration import (
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSection,
    RegistrationSurcharge,
    RegistrationTicket,
)
from larpmanager.utils.common import (
    exchange_order,
)
from larpmanager.utils.download import orga_registration_form_download, orga_tickets_download
from larpmanager.utils.edit import backend_edit, orga_edit, set_suggestion
from larpmanager.utils.event import check_event_permission


@login_required
def orga_registration_tickets(request, s):
    ctx = check_event_permission(request, s, "orga_registration_tickets")

    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_tickets_download(ctx)

    ctx["upload"] = "registration_tickets"
    ctx["download"] = 1

    ctx["list"] = RegistrationTicket.objects.filter(event=ctx["event"]).order_by("order")
    ctx["tiers"] = OrgaRegistrationTicketForm.get_tier_available(ctx["event"])

    return render(request, "larpmanager/orga/registration/tickets.html", ctx)


@login_required
def orga_registration_tickets_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_tickets", OrgaRegistrationTicketForm, num)


@login_required
def orga_registration_tickets_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_registration_tickets")
    exchange_order(ctx, RegistrationTicket, num, order)
    return redirect("orga_registration_tickets", s=ctx["run"].get_slug())


@login_required
def orga_registration_sections(request, s):
    ctx = check_event_permission(request, s, "orga_registration_sections")
    ctx["list"] = RegistrationSection.objects.filter(event=ctx["event"]).order_by("order")
    return render(request, "larpmanager/orga/registration/sections.html", ctx)


@login_required
def orga_registration_sections_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_sections", OrgaRegistrationSectionForm, num)


@login_required
def orga_registration_sections_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_registration_sections")
    exchange_order(ctx, RegistrationSection, num, order)
    return redirect("orga_registration_sections", s=ctx["run"].get_slug())


@login_required
def orga_registration_form(request, s):
    ctx = check_event_permission(request, s, "orga_registration_form")

    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_registration_form_download(ctx)

    ctx["upload"] = "registration_form"
    ctx["download"] = 1

    ctx["list"] = get_ordered_registration_questions(ctx).prefetch_related("options")
    for el in ctx["list"]:
        el.options_list = el.options.order_by("order")

    return render(request, "larpmanager/orga/registration/form.html", ctx)


@login_required
def orga_registration_form_edit(request, s, num):
    perm = "orga_registration_form"
    ctx = check_event_permission(request, s, perm)
    if backend_edit(request, ctx, OrgaRegistrationQuestionForm, num, assoc=False):
        set_suggestion(ctx, perm)
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, s=ctx["run"].get_slug(), num=0)

        edit_option = False
        if str(request.POST.get("new_option", "")) == "1":
            edit_option = True
        elif ctx["saved"].typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
            if not RegistrationOption.objects.filter(question_id=ctx["saved"].id).exists():
                edit_option = True
                messages.warning(
                    request,
                    _("You must define at least one option before saving a single-choice or multiple-choice question"),
                )
        if edit_option:
            return redirect(orga_registration_options_new, s=ctx["run"].get_slug(), num=ctx["saved"].id)
        return redirect(perm, s=ctx["run"].get_slug())

    ctx["list"] = RegistrationOption.objects.filter(question=ctx["el"]).order_by("order")
    return render(request, "larpmanager/orga/registration/form_edit.html", ctx)


@login_required
def orga_registration_form_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_registration_form")
    exchange_order(ctx, RegistrationQuestion, num, order)
    return redirect("orga_registration_form", s=ctx["run"].get_slug())


@login_required
def orga_registration_options_edit(request, s, num):
    ctx = check_event_permission(request, s, "orga_registration_form")

    # Check if registration questions exist
    if not ctx["event"].get_elements(RegistrationQuestion).exists():
        # Add warning message and redirect to registration questions adding page
        messages.warning(
            request, _("You must create at least one registration question before you can create registration options")
        )
        return redirect("orga_registration_form_edit", s=s, num=0)

    return registration_option_edit(ctx, num, request)


@login_required
def orga_registration_options_new(request, s, num):
    ctx = check_event_permission(request, s, "orga_registration_form")
    ctx["question_id"] = num
    return registration_option_edit(ctx, 0, request)


def registration_option_edit(ctx, num, request):
    if backend_edit(request, ctx, OrgaRegistrationOptionForm, num, assoc=False):
        redirect_target = "orga_registration_form_edit"
        if "continue" in request.POST:
            redirect_target = "orga_registration_options_new"
        return redirect(redirect_target, s=ctx["run"].get_slug(), num=ctx["saved"].question_id)

    return render(request, "larpmanager/orga/edit.html", ctx)


@login_required
def orga_registration_options_order(request, s, num, order):
    ctx = check_event_permission(request, s, "orga_registration_form")
    exchange_order(ctx, RegistrationOption, num, order)
    return redirect("orga_registration_form_edit", s=ctx["run"].get_slug(), num=ctx["current"].question_id)


@login_required
def orga_registration_quotas(request, s):
    ctx = check_event_permission(request, s, "orga_registration_quotas")
    ctx["list"] = RegistrationQuota.objects.filter(event=ctx["event"]).order_by("number")
    return render(request, "larpmanager/orga/registration/quotas.html", ctx)


@login_required
def orga_registration_quotas_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_quotas", OrgaRegistrationQuotaForm, num)


@login_required
def orga_registration_installments(request, s):
    ctx = check_event_permission(request, s, "orga_registration_installments")
    ctx["list"] = RegistrationInstallment.objects.filter(event=ctx["event"]).order_by("order", "amount")
    return render(request, "larpmanager/orga/registration/installments.html", ctx)


@login_required
def orga_registration_installments_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_installments", OrgaRegistrationInstallmentForm, num)


@login_required
def orga_registration_surcharges(request, s):
    ctx = check_event_permission(request, s, "orga_registration_surcharges")
    ctx["list"] = RegistrationSurcharge.objects.filter(event=ctx["event"]).order_by("number")
    return render(request, "larpmanager/orga/registration/surcharges.html", ctx)


@login_required
def orga_registration_surcharges_edit(request, s, num):
    return orga_edit(request, s, "orga_registration_surcharges", OrgaRegistrationSurchargeForm, num)
