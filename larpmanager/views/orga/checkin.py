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

from html import unescape

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.html import strip_tags
from django.utils.text import Truncator

from larpmanager.accounting.registration import registration_payments_status
from larpmanager.cache.config import get_event_config
from larpmanager.cache.registration_lookup import get_active_registrations
from larpmanager.cache.writing import get_writing_element_fields_batch
from larpmanager.models.form import BaseQuestionType, QuestionApplicable, RegistrationQuestionType
from larpmanager.models.registration import CheckIn, Registration
from larpmanager.models.writing import Faction, FactionType
from larpmanager.utils.core.checks import check_event_context
from larpmanager.utils.registrations.questions import (
    get_ordered_registration_questions,
    get_ranking_names,
    get_registration_answers_by_question,
    get_registration_choices_by_question,
)


def _resolve_registration(run_id: int, registration_uuid: str) -> Registration:
    """Return the registration for the run matching a scanned QR code's uuid."""
    return Registration.objects.prefetch_related("rcrs__character").get(
        uuid=registration_uuid, run_id=run_id, cancellation_date__isnull=True, pending=False
    )


def _registration_row(registration: Registration, *, writing_number: bool) -> dict:
    """Build the JSON-serializable row used by the check-in list and chart."""
    registration_payments_status(registration)
    character_labels = []
    for rel in registration.rcrs.all():
        label = rel.character.name
        if writing_number:
            label = f"#{rel.character.number} {label}"
        character_labels.append(label)
    characters = ", ".join(character_labels)
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


# Max characters of a single detail value shipped with the check-in page.
DETAIL_VALUE_MAX_LENGTH = 200


def _truncate_detail(value: str) -> str:
    """Shorten a detail value to keep the inline check-in payload small."""
    return Truncator(value).chars(DETAIL_VALUE_MAX_LENGTH, truncate="...")


def _registration_addons(
    questions: list, answers: dict[int, str], choices: dict[int, list[str]], ranking_names: dict[int, dict]
) -> list[dict]:
    """Return the non-empty registration answers of one registration as name/value pairs."""
    addons = []
    for question in questions:
        if question.typ in (BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE):
            value = ", ".join(choices.get(question.id, []))
        elif question.typ == RegistrationQuestionType.RANKING:
            value = ", ".join(get_ranking_names(answers.get(question.id, ""), ranking_names[question.id]))
        else:
            value = answers.get(question.id, "")
        if value:
            addons.append({"name": question.name, "value": _truncate_detail(value)})
    return addons


def _character_fields(fields_data: dict) -> list[dict]:
    """Return the non-empty character sheet fields as name/value pairs."""
    character_fields = []
    for question_uuid, question in fields_data.get("questions", {}).items():
        value = fields_data.get("fields", {}).get(question_uuid)
        if not value:
            continue
        if isinstance(value, str):
            display_value = unescape(strip_tags(value))
        else:
            display_value = ", ".join(
                fields_data["options"][option_uuid]["name"]
                for option_uuid in value
                if option_uuid in fields_data["options"]
            )
        character_fields.append({"name": question["name"], "value": _truncate_detail(display_value)})
    return character_fields


def _registration_details(context: dict, registrations: list[Registration]) -> dict[int, dict]:
    """Map registration id -> ticket, addons, faction and character sheet fields.

    Built in bulk for the whole run, so details are available offline right after a scan.
    """
    context["show_all"] = "1"
    registration_ids = [registration.id for registration in registrations]

    questions = list(get_ordered_registration_questions(context).prefetch_related("options"))
    question_ids = [question.id for question in questions]
    answers = get_registration_answers_by_question(question_ids, registration_id__in=registration_ids)
    choices = get_registration_choices_by_question(question_ids, registration_id__in=registration_ids)
    ranking_names = {
        question.id: {str(option.uuid): option.name for option in question.options.all()}
        for question in questions
        if question.typ == RegistrationQuestionType.RANKING
    }

    first_characters = {}
    for registration in registrations:
        rels = list(registration.rcrs.all())
        if rels:
            first_characters[registration.id] = rels[0].character
    character_fields_by_id = get_writing_element_fields_batch(
        context,
        "character",
        QuestionApplicable.CHARACTER,
        [character.id for character in first_characters.values()],
        only_visible=False,
    )

    details = {}
    for registration in registrations:
        addons = _registration_addons(
            questions, answers.get(registration.id, {}), choices.get(registration.id, {}), ranking_names
        )

        faction_name = ""
        character_fields = []
        character = first_characters.get(registration.id)
        if character:
            faction_name = ", ".join(faction.name for faction in character.factions_list.all())
            character_fields = _character_fields(character_fields_by_id.get(character.id, {}))

        details[registration.id] = {
            "ticket": registration.ticket.name if registration.ticket_id else None,
            "addons": addons,
            "faction": faction_name,
            "character_fields": character_fields,
        }
    return details


@login_required
def orga_checkin(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render the check-in dashboard: registration list, chart and scan control.

    Ships the full registration list with each registration's details inline, so the
    page keeps working (lookup, details, local list/chart update) even without
    connectivity; a scan is synced to the server in the background, or queued in
    localStorage until it succeeds.
    """
    context = check_event_context(request, event_slug, "orga_checkin")

    registrations = list(
        get_active_registrations(context["run"].id)
        .select_related("member", "check_in", "ticket")
        .prefetch_related(
            "rcrs__character",
            Prefetch(
                "rcrs__character__factions_list",
                queryset=Faction.objects.exclude(typ=FactionType.SECRET).order_by("order"),
            ),
        )
    )
    writing_number = get_event_config(context["event"].id, "writing_number", context=context)
    details = _registration_details(context, registrations)
    context["checkin_data"] = [
        {**_registration_row(registration, writing_number=writing_number), "detail": details[registration.id]}
        for registration in registrations
    ]
    return render(request, "larpmanager/orga/checkin.html", context)


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

    writing_number = get_event_config(context["event"].id, "writing_number", context=context)
    return JsonResponse({"res": "ok", "row": _registration_row(registration, writing_number=writing_number)})
