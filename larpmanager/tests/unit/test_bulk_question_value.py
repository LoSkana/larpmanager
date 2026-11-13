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

"""Unit tests for the bulk operations setting the value of single choice questions."""

import json
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingChoice,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.registration import RegistrationTicket
from larpmanager.models.writing import Character
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.exceptions import ReturnNowError
from larpmanager.utils.services.bulk import Operations, handle_bulk_characters, handle_bulk_registrations


@pytest.mark.django_db
class TestBulkQuestionValue(BaseTestCase):
    """Check the "set value" bulk operations on characters and registrations."""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.run = self.get_run()
        self.event = self.run.event
        self.factory = RequestFactory()

    def _context(self) -> dict:
        return {
            "event": self.event,
            "run": self.run,
            "association_id": self.event.association_id,
            "features": {},
            "member": self.get_member(),
        }

    def _post(self, handler: callable, operation: str, target: str, uuids: list[str]) -> dict:
        request = self.factory.post("/", {"operation": operation, "target": target, "uuids[]": uuids})
        request.user = self.get_user()
        with pytest.raises(ReturnNowError) as exc:
            handler(request, self._context())
        return json.loads(exc.value.value.content)

    def test_character_single_choice(self) -> None:
        question = WritingQuestion.objects.create(
            event=self.event, applicable=QuestionApplicable.CHARACTER, typ=BaseQuestionType.SINGLE, name="Origin"
        )
        opt_a = WritingOption.objects.create(event=self.event, question=question, name="North")
        opt_b = WritingOption.objects.create(event=self.event, question=question, name="South")
        skills = WritingQuestion.objects.create(
            event=self.event, applicable=QuestionApplicable.CHARACTER, typ=BaseQuestionType.MULTIPLE, name="Skills"
        )
        char_1 = Character.objects.create(event=self.event, name="One")
        char_2 = Character.objects.create(event=self.event, name="Two")
        WritingChoice.objects.create(element_id=char_1.id, question=question, option=opt_a)

        # Listing offers one operation for the single choice question only
        request = self.factory.get("/")
        request.user = self.get_user()
        context = self._context()
        handle_bulk_characters(request, context)
        idx = f"{int(Operations.SET_CHAR_QUESTION)}_{question.uuid}"
        ops = [op for op in context["bulk"] if op["idx"] == idx]
        assert len(ops) == 1
        assert ops[0]["label"] == "Set 'Origin'"
        assert [str(obj["uuid"]) for obj in ops[0]["objs"]] == [str(opt_a.uuid), str(opt_b.uuid)]
        skills_idx = f"{int(Operations.SET_CHAR_QUESTION)}_{skills.uuid}"
        assert not [op for op in context["bulk"] if op["idx"] == skills_idx]

        res = self._post(handle_bulk_characters, ops[0]["idx"], str(opt_b.uuid), [str(char_1.uuid), str(char_2.uuid)])
        assert res == {"res": "ok"}
        for char in (char_1, char_2):
            choices = WritingChoice.objects.filter(element_id=char.id, question=question)
            assert list(choices.values_list("option_id", flat=True)) == [opt_b.id]

        # Re-applying the same value keeps the existing choices untouched
        choice_ids = set(WritingChoice.objects.filter(question=question).values_list("id", flat=True))
        res = self._post(handle_bulk_characters, ops[0]["idx"], str(opt_b.uuid), [str(char_1.uuid), str(char_2.uuid)])
        assert res == {"res": "ok"}
        assert set(WritingChoice.objects.filter(question=question).values_list("id", flat=True)) == choice_ids

    def test_character_invalid_option(self) -> None:
        question = WritingQuestion.objects.create(
            event=self.event, applicable=QuestionApplicable.CHARACTER, typ=BaseQuestionType.MULTIPLE, name="Skills"
        )
        option = WritingOption.objects.create(event=self.event, question=question, name="Fight")
        char = Character.objects.create(event=self.event, name="One")

        res = self._post(
            handle_bulk_characters,
            f"{int(Operations.SET_CHAR_QUESTION)}_{question.uuid}",
            str(option.uuid),
            [str(char.uuid)],
        )
        assert "error" in res
        assert not WritingChoice.objects.filter(element_id=char.id).exists()

    def test_registration_single_choice(self) -> None:
        question = RegistrationQuestion.objects.create(event=self.event, typ=BaseQuestionType.SINGLE, name="Meal")
        RegistrationOption.objects.create(event=self.event, question=question, name="Standard")
        option = RegistrationOption.objects.create(
            event=self.event, question=question, name="Vegan", price=Decimal("10.00")
        )
        registration = self.create_registration(run=self.run)

        request = self.factory.get("/")
        request.user = self.get_user()
        context = self._context()
        handle_bulk_registrations(request, context)
        assert [op["idx"] for op in context["bulk"]] == [
            Operations.SET_REG_TICKET,
            f"{int(Operations.SET_REG_QUESTION)}_{question.uuid}",
        ]

        res = self._post(
            handle_bulk_registrations, context["bulk"][1]["idx"], str(option.uuid), [str(registration.uuid)]
        )
        assert res == {"res": "ok"}
        choices = RegistrationChoice.objects.filter(registration=registration, question=question)
        assert list(choices.values_list("option_id", flat=True)) == [option.id]

    def test_registration_set_ticket(self) -> None:
        """Bulk set ticket assigns the chosen ticket."""
        registration = self.create_registration(run=self.run)
        ticket = RegistrationTicket.objects.create(event=self.event, name="Bulk ticket", number=99)
        res = self._post(
            handle_bulk_registrations, str(int(Operations.SET_REG_TICKET)), str(ticket.uuid), [str(registration.uuid)]
        )
        assert res == {"res": "ok"}
        registration.refresh_from_db()
        assert registration.ticket_id == ticket.id

    def test_label_truncated(self) -> None:
        """Operation label uses at most 30 chars of the question name."""
        question = RegistrationQuestion.objects.create(event=self.event, typ=BaseQuestionType.SINGLE, name="A" * 40)
        RegistrationOption.objects.create(event=self.event, question=question, name="Yes")
        request = self.factory.get("/")
        request.user = self.get_user()
        context = self._context()
        handle_bulk_registrations(request, context)
        labels = [
            op["label"] for op in context["bulk"] if op["idx"] == f"{int(Operations.SET_REG_QUESTION)}_{question.uuid}"
        ]
        assert labels == ["Set '" + "A" * 30 + "'"]
