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
"""Registration question ordering and per-registration answer/choice lookups.

get_ordered_registration_questions was split out of larpmanager.views.orga.form:
larpmanager.views.orga.registration needs this function, but importing
larpmanager.views.orga.form from there pulls in a long chain (options_inline ->
forms.character -> forms.writing -> services.character -> services.event ->
cache.wwyltd) that circles back to larpmanager.views.orga.registration itself. This
module has none of those dependencies, so both view modules can import it at the top
of the file.
"""

from __future__ import annotations

from typing import Any

from django.db.models import F, QuerySet

from larpmanager.models.form import RegistrationAnswer, RegistrationChoice, RegistrationQuestion
from larpmanager.models.writing import get_event_elements


def get_ordered_registration_questions(context: dict, applicable: str | None = None) -> QuerySet[RegistrationQuestion]:
    """Get registration questions ordered by section and question order.

    Args:
        context: View context (must contain "event")
        applicable: Optional RegistrationQuestionApplicable value to filter by. Unfiltered when None.

    """
    questions = get_event_elements(context["event"].id, RegistrationQuestion, context=context)
    if applicable is not None:
        questions = questions.filter(applicable=applicable)
    return questions.order_by(F("section__order").asc(nulls_first=True), "order")


def get_registration_answers_by_question(
    question_ids: list[int], **registration_filter: Any
) -> dict[int, dict[int, str]]:
    """Map registration id -> question id -> answer text, for the given questions.

    Args:
        question_ids: Ids of the registration questions to collect answers for
        registration_filter: Extra filter kwargs scoping which registrations are considered
            (e.g. registration_id__in=[...] or registration__run=run)

    """
    answers_by_registration: dict[int, dict[int, str]] = {}
    for answer in RegistrationAnswer.objects.filter(question_id__in=question_ids, **registration_filter):
        answers_by_registration.setdefault(answer.registration_id, {})[answer.question_id] = answer.text
    return answers_by_registration


def get_registration_choices_by_question(
    question_ids: list[int], **registration_filter: Any
) -> dict[int, dict[int, list[str]]]:
    """Map registration id -> question id -> selected choice option names, for the given questions.

    Args:
        question_ids: Ids of the registration questions to collect choices for
        registration_filter: Extra filter kwargs scoping which registrations are considered
            (e.g. registration_id__in=[...] or registration__run=run)

    """
    choices_by_registration: dict[int, dict[int, list[str]]] = {}
    for choice in RegistrationChoice.objects.filter(question_id__in=question_ids, **registration_filter).select_related(
        "option"
    ):
        choices_by_registration.setdefault(choice.registration_id, {}).setdefault(choice.question_id, []).append(
            choice.option.name
        )
    return choices_by_registration
