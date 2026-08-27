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

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.registration_lookup import get_active_registrations
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationOption,
    RegistrationQuestionApplicable,
    RegistrationQuestionType,
)
from larpmanager.models.writing import Faction, get_event_elements
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.registrations.questions import (
    get_ordered_registration_questions,
    get_registration_answers_by_question,
    get_registration_choices_by_question,
)

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


@login_required
def orga_matchmaker_answers(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Show, per participant, the answers to the matchmaker questions."""
    context = check_event_context(request, event_slug, "orga_matchmaker_answers")
    context["page_info"] = _("Review participant answers to the matchmaker questions")

    questions = list(
        get_ordered_registration_questions(
            context, applicable=RegistrationQuestionApplicable.MATCHMAKER
        ).prefetch_related(Prefetch("options", queryset=RegistrationOption.objects.order_by("order")))
    )
    context["questions"] = questions

    registrations = (
        get_active_registrations(context["run"].id).select_related("member").order_by("member__name", "member__surname")
    )

    question_ids = [question.id for question in questions]

    answers_by_registration = get_registration_answers_by_question(question_ids, registration__run=context["run"])
    choices_by_registration = get_registration_choices_by_question(question_ids, registration__run=context["run"])

    faction_names_by_uuid = {
        str(uuid): name
        for uuid, name in get_event_elements(context["event"].id, Faction, context=context).values_list("uuid", "name")
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

    return render(request, "larpmanager/orga/matchmaker/answers.html", context)
