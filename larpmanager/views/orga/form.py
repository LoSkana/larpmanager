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

import json

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.button import clear_event_button_cache
from larpmanager.cache.character import reset_event_cache_all
from larpmanager.cache.config import get_event_config
from larpmanager.cache.experience import clear_event_exp_cache, clear_event_exp_systems_cache
from larpmanager.cache.registration_lookup import (
    clear_registration_tickets_cache,
    get_active_registrations,
    get_registration_tickets,
)
from larpmanager.cache.writing import clear_relationship_tags_cache
from larpmanager.forms.base import DEFAULT_LIKERT_MAX
from larpmanager.forms.registration import OrgaRegistrationTicketForm
from larpmanager.models.form import (
    REGISTRATION_APPLICABLE_TO_TYPE,
    BaseQuestionType,
    RegistrationOption,
    RegistrationQuestionApplicable,
    RegistrationQuestionType,
)
from larpmanager.models.registration import (
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSection,
    RegistrationSurcharge,
)
from larpmanager.models.writing import Faction, get_event_class_parent, get_event_elements
from larpmanager.utils.core.checks import check_event_context
from larpmanager.utils.edit.backend import (
    backend_order,
    backend_set_order,
)
from larpmanager.utils.edit.options_inline import (
    options_inline_delete,
    options_inline_reorder,
    options_inline_save,
)
from larpmanager.utils.edit.orga import (
    OrgaAction,
    check_registration_form_type,
    form_edit_handler,
    options_edit_handler,
    orga_delete,
    orga_edit,
    orga_new,
)
from larpmanager.utils.io.download import orga_registration_form_download, orga_tickets_download
from larpmanager.utils.registrations.questions import (
    get_ordered_registration_questions,
    get_registration_answers_by_question,
    get_registration_choices_by_question,
)


@login_required
def orga_registration_tickets(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle organization registration tickets management.

    Manages the display and download of registration tickets for an event.
    Supports both GET requests for displaying the tickets page and POST
    requests for downloading tickets.

    Args:
        request: The HTTP request object containing user data and method info
        event_slug: Event identifier string for permission checking and context

    Returns:
        HttpResponse: Rendered tickets template or download response

    """
    # Check user permissions for accessing registration tickets management
    context = check_event_context(request, event_slug, "orga_registration_tickets")

    # Handle POST request for ticket download functionality
    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_tickets_download(context)

    # Set up context variables for template rendering
    context["upload"] = "registration_tickets"
    context["download"] = 1

    # Fetch registration tickets ordered by their sequence number
    context["list"] = get_registration_tickets(context["event"].id)
    # Get available ticket tiers for the current event
    context["tiers"] = OrgaRegistrationTicketForm.get_tier_available(context["event"], context)
    # Show the sold count column only if the event displays sold tickets
    context["show_ticket_sold"] = get_event_config(context["event"].id, "ticket_sold", context=context)

    return render(request, "larpmanager/orga/registration/tickets.html", context)


@login_required
def orga_registration_tickets_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration ticket."""
    return orga_new(request, event_slug, OrgaAction.REGISTRATION_TICKETS)


@login_required
def orga_registration_tickets_edit(request: HttpRequest, event_slug: str, ticket_uuid: str) -> HttpResponse:
    """Edit a specific registration ticket."""
    return orga_edit(request, event_slug, OrgaAction.REGISTRATION_TICKETS, ticket_uuid)


@login_required
def orga_registration_tickets_delete(request: HttpRequest, event_slug: str, ticket_uuid: str) -> HttpResponse:
    """Delete ticket for event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_TICKETS, ticket_uuid)


@login_required
def orga_registration_sections(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display registration sections for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_registration_sections")

    # Retrieve and order registration sections
    context["list"] = RegistrationSection.objects.filter(event=context["event"]).order_by("order")

    return render(request, "larpmanager/orga/registration/sections.html", context)


@login_required
def orga_registration_sections_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration section for an event."""
    return orga_new(request, event_slug, OrgaAction.REGISTRATION_SECTIONS)


@login_required
def orga_registration_sections_edit(request: HttpRequest, event_slug: str, section_uuid: str) -> HttpResponse:
    """Edit a specific registration section for an event."""
    return orga_edit(request, event_slug, OrgaAction.REGISTRATION_SECTIONS, section_uuid)


@login_required
def orga_registration_sections_delete(request: HttpRequest, event_slug: str, section_uuid: str) -> HttpResponse:
    """Delete section for event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_SECTIONS, section_uuid)


@login_required
def orga_registration_form(request: HttpRequest, event_slug: str, registration_type: str | None = None) -> HttpResponse:
    """Handle the organization registration form view.

    Displays the registration form configuration page for event organizers,
    allowing them to view and download the current registration questions.

    Args:
        request: The HTTP request object containing user and POST data
        event_slug: Event identifier string for permission checking
        registration_type: Form type to display; defaults to "registration"

    Returns:
        HttpResponse: Rendered registration form page or download response

    """
    if registration_type is None:
        return redirect("orga_registration_form", event_slug=event_slug, registration_type="registration")

    # Check if user has permission to access the registration form management
    context = check_event_context(request, event_slug, "orga_registration_form")

    # Validate the registration form type parameter and add to context
    check_registration_form_type(context, registration_type)

    # Handle download request for registration form data
    if request.method == "POST" and request.POST.get("download") == "1":
        return orga_registration_form_download(context)

    # Configure context for template rendering
    context["upload"] = f"{context['typ']}_form"
    context["download"] = 1

    # Fetch ordered registration questions with their options, scoped to the current form type
    context["list"] = get_ordered_registration_questions(
        context, applicable=context["registration_typ"]
    ).prefetch_related(Prefetch("options", queryset=RegistrationOption.objects.order_by("order")))

    return render(request, "larpmanager/orga/registration/form.html", context)


@login_required
def orga_registration_form_new(
    request: HttpRequest, event_slug: str, registration_type: str | None = None
) -> HttpResponse:
    """Create a new registration form question."""
    return form_edit_handler(
        request,
        event_slug,
        "orga_registration_form",
        None,
        extra_context=_registration_form_extra_context(registration_type),
    )


@login_required
def orga_registration_form_edit(
    request: HttpRequest, event_slug: str, question_uuid: str, registration_type: str | None = None
) -> HttpResponse:
    """Edit registration form question for organizers."""
    return form_edit_handler(
        request,
        event_slug,
        "orga_registration_form",
        question_uuid,
        extra_context=_registration_form_extra_context(registration_type),
    )


def _registration_form_extra_context(registration_type: str | None) -> dict:
    """Build extra_context for form_edit_handler, defaulting to the "registration" type."""
    return {"registration_type": registration_type or "registration"}


@login_required
def orga_registration_form_delete(
    request: HttpRequest,
    event_slug: str,
    question_uuid: str,
    registration_type: str | None = None,  # noqa: ARG001
) -> HttpResponse:
    """Delete question for event."""
    return orga_delete(
        request,
        event_slug,
        OrgaAction.REGISTRATION_FORM,
        question_uuid,
    )


@login_required
def orga_registration_options_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration option."""
    return options_edit_handler(request, event_slug, "orga_registration_form", None)


@login_required
def orga_registration_options_edit(request: HttpRequest, event_slug: str, option_uuid: str) -> HttpResponse:
    """Edit registration options for an event."""
    return options_edit_handler(request, event_slug, "orga_registration_form", option_uuid)


@login_required
def orga_registration_options_order(
    request: HttpRequest,
    event_slug: str,
    option_uuid: str,
    order: int,
) -> HttpResponse:
    """Reorder registration options within a form question.

    Args:
        request: The HTTP request object
        event_slug: Event/run slug identifier
        option_uuid: Option UUID to reorder
        order: Direction to move the option (1 or 0)

    Returns:
        Redirect to the registration form edit page

    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_registration_form")

    # Exchange the order of registration options
    backend_order(context, RegistrationOption, option_uuid, order)

    # Redirect back to the form edit page
    url = reverse(
        "orga_registration_form_edit",
        kwargs={
            "event_slug": context["run"].get_slug(),
            "registration_type": REGISTRATION_APPLICABLE_TO_TYPE[context["current"].question.applicable],
            "question_uuid": context["current"].question.uuid,
        },
    )
    return HttpResponseRedirect(url)


@login_required
def orga_registration_options_delete(request: HttpRequest, event_slug: str, option_uuid: str) -> HttpResponse:
    """Delete registration option for an event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_FORM_OPTION, option_uuid)


@login_required
def orga_registration_options_inline_save(
    request: HttpRequest, event_slug: str, option_uuid: str | None = None
) -> HttpResponse:
    """Create or update a registration option from the inline editor (AJAX)."""
    return options_inline_save(request, event_slug, "orga_registration_form", option_uuid)


@login_required
def orga_registration_options_inline_reorder(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Persist the full ordering of a question's options (AJAX)."""
    return options_inline_reorder(request, event_slug, "orga_registration_form")


@login_required
def orga_registration_options_inline_delete(request: HttpRequest, event_slug: str, option_uuid: str) -> HttpResponse:
    """Delete a registration option from the inline editor (AJAX)."""
    return options_inline_delete(request, event_slug, "orga_registration_form", option_uuid)


@login_required
def orga_registration_quotas(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage registration quotas for an event."""
    # Check event permissions and build context
    context = check_event_context(request, event_slug, "orga_registration_quotas")

    # Retrieve and order quotas by number
    context["list"] = RegistrationQuota.objects.filter(event=context["event"]).order_by("number")

    return render(request, "larpmanager/orga/registration/quotas.html", context)


@login_required
def orga_registration_quotas_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration quota for an event."""
    return orga_new(request, event_slug, OrgaAction.REGISTRATION_QUOTAS)


@login_required
def orga_registration_quotas_edit(request: HttpRequest, event_slug: str, quota_uuid: str) -> HttpResponse:
    """Edit a specific registration quota for an event."""
    return orga_edit(request, event_slug, OrgaAction.REGISTRATION_QUOTAS, quota_uuid)


@login_required
def orga_registration_quotas_delete(request: HttpRequest, event_slug: str, quota_uuid: str) -> HttpResponse:
    """Delete quota for event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_QUOTAS, quota_uuid)


@login_required
def orga_registration_installments(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage registration installments for an event."""
    # Verify user has permission to access registration installment management
    context = check_event_context(request, event_slug, "orga_registration_installments")

    # Retrieve all installments for this event, ordered by sequence and amount
    context["list"] = RegistrationInstallment.objects.filter(event=context["event"]).order_by("order", "amount")

    return render(request, "larpmanager/orga/registration/installments.html", context)


@login_required
def orga_registration_installments_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration installment for an event."""
    return orga_new(request, event_slug, OrgaAction.REGISTRATION_INSTALLMENTS)


@login_required
def orga_registration_installments_edit(request: HttpRequest, event_slug: str, installment_uuid: str) -> HttpResponse:
    """Edit a specific registration installment for an event."""
    return orga_edit(request, event_slug, OrgaAction.REGISTRATION_INSTALLMENTS, installment_uuid)


@login_required
def orga_registration_installments_delete(request: HttpRequest, event_slug: str, installment_uuid: str) -> HttpResponse:
    """Delete installment for event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_INSTALLMENTS, installment_uuid)


@login_required
def orga_registration_surcharges(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display registration surcharges for an event."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_registration_surcharges")

    # Fetch and order surcharges by number
    context["list"] = RegistrationSurcharge.objects.filter(event=context["event"]).order_by("number")

    return render(request, "larpmanager/orga/registration/surcharges.html", context)


@login_required
def orga_registration_surcharges_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration surcharge for an event."""
    return orga_new(request, event_slug, OrgaAction.REGISTRATION_SURCHARGES)


@login_required
def orga_registration_surcharges_edit(request: HttpRequest, event_slug: str, surcharge_uuid: str) -> HttpResponse:
    """Edit a registration surcharge for an event."""
    return orga_edit(request, event_slug, OrgaAction.REGISTRATION_SURCHARGES, surcharge_uuid)


@login_required
def orga_registration_surcharges_delete(request: HttpRequest, event_slug: str, surcharge_uuid: str) -> HttpResponse:
    """Delete surcharge for event."""
    return orga_delete(request, event_slug, OrgaAction.REGISTRATION_SURCHARGES, surcharge_uuid)


@login_required
def orga_reorder_items(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Unified drag-and-drop reorder endpoint. POST JSON {model, uuids}."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    model_key = data.get("model", "")
    uuids = data.get("uuids", [])
    if not isinstance(uuids, list):
        return JsonResponse({"error": "uuids must be a list"}, status=400)
    action = OrgaAction.from_string(model_key)
    if action is None or not action.config.get("form"):
        return JsonResponse({"error": "Invalid model"}, status=400)
    context = check_event_context(request, event_slug, model_key)
    model_class = action.config["form"].Meta.model
    backend_set_order(context, model_class, uuids)
    if action.config.get("writing"):
        reset_event_cache_all(context["run"].id)
    if action.config.get("exp"):
        event_id = context["event"].id
        clear_event_exp_cache(event_id)
        clear_event_exp_systems_cache(event_id)
    if action.config.get("button"):
        clear_event_button_cache(context["event"].id)
    if action.config.get("tickets"):
        clear_registration_tickets_cache(context["event"].id)
    if action.config.get("relationship_tags"):
        clear_relationship_tags_cache(get_event_class_parent(context["event"].id, model_class, context=context))
    return JsonResponse({"ok": True})


def _orga_single_applicable_answers(
    request: HttpRequest,
    event_slug: str,
    permission_slug: str,
    applicable: RegistrationQuestionApplicable,
    page_info: str,
    template: str,
) -> HttpResponse:
    """Show, per participant, the answers to the questions of a single applicable form.

    Shared by matchmaker/debrief (and any future single-applicable-question orga review
    page): matchmaker additionally resolves RegistrationQuestionType.FACTION_PREFERENCE
    answers (raw comma-separated faction uuids) into ranked faction names.
    """
    context = check_event_context(request, event_slug, permission_slug)
    context["page_info"] = page_info

    questions = list(
        get_ordered_registration_questions(context, applicable=applicable).prefetch_related(
            Prefetch("options", queryset=RegistrationOption.objects.order_by("order"))
        )
    )
    context["questions"] = questions

    registrations = (
        get_active_registrations(context["run"].id).select_related("member").order_by("member__name", "member__surname")
    )

    question_ids = [question.id for question in questions]

    answers_by_registration = get_registration_answers_by_question(question_ids, registration__run=context["run"])
    choices_by_registration = get_registration_choices_by_question(question_ids, registration__run=context["run"])

    faction_names_by_uuid = {}
    if applicable == RegistrationQuestionApplicable.MATCHMAKER:
        faction_names_by_uuid = {
            str(uuid): name
            for uuid, name in get_event_elements(context["event"].id, Faction, context=context).values_list(
                "uuid", "name"
            )
        }

    rows = []
    for registration in registrations:
        cells = []
        has_answer = False
        for question in questions:
            if question.typ in (BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE):
                value = ", ".join(choices_by_registration.get(registration.id, {}).get(question.id, []))
            elif question.typ == RegistrationQuestionType.FACTION_PREFERENCE:
                raw = answers_by_registration.get(registration.id, {}).get(question.id, "")
                names = [faction_names_by_uuid[uuid] for uuid in raw.split(",") if uuid in faction_names_by_uuid]
                value = ", ".join(f"{i}. {name}" for i, name in enumerate(names, start=1))
            else:
                value = answers_by_registration.get(registration.id, {}).get(question.id, "")
            if value:
                has_answer = True
            cells.append(value)
        if has_answer:
            rows.append({"registration": registration, "cells": cells})

    context["rows"] = rows
    context["likert_charts"] = _get_likert_charts(questions, rows)

    return render(request, template, context)


def _get_likert_charts(questions: list, rows: list) -> list:
    """Build per-question answer distributions for likert questions, for bar charts."""
    likert_charts = []
    for idx, question in enumerate(questions):
        if question.typ != RegistrationQuestionType.LIKERT:
            continue
        scale_max = question.max_length or DEFAULT_LIKERT_MAX
        counts = [0] * scale_max
        for row in rows:
            value = row["cells"][idx]
            if value.isdigit() and 1 <= int(value) <= scale_max:
                counts[int(value) - 1] += 1
        likert_charts.append({"question": question, "scale_max": scale_max, "counts": counts})
    return likert_charts


@login_required
def orga_matchmaker_answers(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Show, per participant, the answers to the matchmaker questions."""
    return _orga_single_applicable_answers(
        request,
        event_slug,
        "orga_matchmaker_answers",
        RegistrationQuestionApplicable.MATCHMAKER,
        _("Review participant answers to the matchmaker questions"),
        "larpmanager/orga/matchmaker.html",
    )


@login_required
def orga_debrief_answers(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Show, per participant, the answers to the debrief questions."""
    return _orga_single_applicable_answers(
        request,
        event_slug,
        "orga_debrief_answers",
        RegistrationQuestionApplicable.DEBRIEF,
        _("Review participant answers to the debrief questions"),
        "larpmanager/orga/debrief.html",
    )
