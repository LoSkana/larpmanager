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
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from larpmanager.accounting.registration import registration_payments_status
from larpmanager.cache.registration_lookup import get_active_registrations
from larpmanager.cache.writing import get_character_element_fields
from larpmanager.models.form import BaseQuestionType
from larpmanager.models.registration import CheckIn, Registration
from larpmanager.models.writing import FactionType
from larpmanager.utils.core.checks import check_event_context
from larpmanager.utils.registrations.questions import (
    get_ordered_registration_questions,
    get_registration_answers_by_question,
    get_registration_choices_by_question,
)


def _resolve_registration(run_id: int, registration_uuid: str) -> Registration:
    """Return the registration for the run matching a scanned QR code's uuid."""
    return Registration.objects.get(
        uuid=registration_uuid, run_id=run_id, cancellation_date__isnull=True, pending=False
    )


def _registration_row(registration: Registration) -> dict:
    """Build the JSON-serializable row used by the check-in list and chart."""
    registration_payments_status(registration)
    characters = ", ".join(rel.character.name for rel in registration.rcrs.select_related("character"))
    check_in = getattr(registration, "check_in", None)
    # select_related bypasses the safedelete manager's filtering, so a soft-deleted
    # CheckIn (e.g. removed from the admin) would otherwise still read as present.
    if check_in and check_in.deleted:
        check_in = None
    return {
        "uuid": registration.uuid,
        "member": registration.display_member(),
        "character": characters,
        "paid": registration.payment_status == "c",
        "checked_in_at": check_in.checked_in_at.isoformat() if check_in and check_in.checked_in_at else None,
    }


@login_required
def orga_checkin(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render the check-in dashboard: registration list, chart and scan control.

    Ships the full registration list for the run inline, so the page keeps working
    (lookup + local list/chart update) even without connectivity; a scan is synced
    to the server in the background, or queued in localStorage until it succeeds.
    """
    context = check_event_context(request, event_slug, "orga_checkin")

    registrations = (
        get_active_registrations(context["run"].id)
        .select_related("member", "check_in")
        .prefetch_related("rcrs__character")
    )
    rows = [_registration_row(registration) for registration in registrations]

    context["checkin_data"] = json.dumps(rows)
    return render(request, "larpmanager/orga/checkin.html", context)


@login_required
def orga_checkin_detail(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Return ticket, addons, faction and full character sheet fields for one registration.

    Fetched on demand when a check-in row is expanded, rather than shipped with the
    initial list, since it requires per-registration writing-question queries.
    """
    context = check_event_context(request, event_slug, "orga_checkin")
    context["show_all"] = "1"

    registration_uuid = request.GET.get("uuid", "")
    try:
        registration = _resolve_registration(context["run"].id, registration_uuid)
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko", "error": "invalid_uuid"}, status=404)

    questions = list(get_ordered_registration_questions(context))
    question_ids = [question.id for question in questions]
    answers = get_registration_answers_by_question(question_ids, registration_id=registration.id)
    choices = get_registration_choices_by_question(question_ids, registration_id=registration.id)

    addons = []
    for question in questions:
        if question.typ in (BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE):
            value = ", ".join(choices.get(registration.id, {}).get(question.id, []))
        else:
            value = answers.get(registration.id, {}).get(question.id, "")
        if value:
            addons.append({"name": question.name, "value": value})

    first_character = next((rel.character for rel in registration.rcrs.select_related("character")), None)

    faction_name = ""
    character_fields = []
    if first_character:
        faction_name = ", ".join(
            first_character.factions_list.exclude(typ=FactionType.SECRET).values_list("name", flat=True)
        )
        fields_data = get_character_element_fields(context, first_character.id, only_visible=False)
        for question_uuid, question in fields_data["questions"].items():
            value = fields_data["fields"].get(question_uuid)
            if not value:
                continue
            if isinstance(value, str):
                display_value = value
            else:
                display_value = ", ".join(
                    fields_data["options"][option_uuid]["name"]
                    for option_uuid in value
                    if option_uuid in fields_data["options"]
                )
            character_fields.append({"name": question["name"], "value": display_value})

    return JsonResponse(
        {
            "res": "ok",
            "ticket": registration.ticket.name if registration.ticket_id else None,
            "addons": addons,
            "faction": faction_name,
            "character_fields": character_fields,
        }
    )


@login_required
def orga_checkin_scan(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Validate a scanned QR token and mark the matching registration present.

    Accepts an optional client-supplied `scanned_at` timestamp so scans buffered
    offline keep their real scan time once synced.
    """
    context = check_event_context(request, event_slug, "orga_checkin")

    registration_uuid = request.POST.get("uuid", "")
    try:
        registration = _resolve_registration(context["run"].id, registration_uuid)
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko", "error": "invalid_uuid"}, status=400)

    scanned_at = parse_datetime(request.POST.get("scanned_at", "")) or timezone.now()

    with transaction.atomic():
        # all_objects includes soft-deleted rows, so re-scanning after the check-in
        # was removed (e.g. from the admin) revives it instead of colliding on the
        # unique registration_id constraint.
        check_in, _created = CheckIn.all_objects.select_for_update().get_or_create(registration=registration)
        if check_in.deleted or not check_in.checked_in_at:
            check_in.deleted = None
            check_in.checked_in_at = scanned_at
            check_in.checked_in_by = request.user.member
            check_in.save()

    return JsonResponse({"res": "ok", "row": _registration_row(registration)})
