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

"""Unit tests for the inline (no-modal) options editor endpoints."""

import json
from typing import Any
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from larpmanager.models.form import RegistrationOption, RegistrationQuestion
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.edit import options_inline
from larpmanager.utils.edit.options_inline import (
    options_inline_delete,
    options_inline_reorder,
    options_inline_save,
)


@pytest.mark.django_db
class TestInlineOptionsEndpoints(BaseTestCase):
    """Exercise save / reorder / delete of the inline options editor."""

    def _context(self) -> dict:
        run = self.get_run()
        return {
            "event": run.event,
            "run": run,
            "member": self.get_member(),
            "features": {},
            "association_id": run.event.association_id,
        }

    def _question(self) -> RegistrationQuestion:
        return RegistrationQuestion.objects.create(
            event=self.get_event(),
            typ="s",
            name="Alloggio",
            order=1,
        )

    def _call(self, view: Any, post_data: dict, **kwargs: Any) -> Any:
        request = RequestFactory().post("/", post_data)
        request.user = self.get_user()
        context = self._context()
        with patch.object(options_inline, "check_event_context", return_value=context):
            return view(request, "test", "orga_registration_form", **kwargs)

    def test_inline_save_creates_option(self) -> None:
        question = self._question()

        response = self._call(
            options_inline_save,
            {"question_uuid": str(question.uuid), "name": "Tenda", "price": "10", "description": ""},
        )

        payload = json.loads(response.content)
        assert payload["success"] is True, payload
        option = RegistrationOption.objects.get(uuid=payload["option"]["uuid"])
        assert option.name == "Tenda"
        assert option.price == 10
        assert option.question_id == question.id

    def test_inline_save_partial_update_keeps_other_fields(self) -> None:
        question = self._question()
        option = RegistrationOption.objects.create(
            event=self.get_event(), question=question, name="Tenda", price=10, description="In giardino"
        )

        # Autosave of the name field only must not wipe price or description
        response = self._call(options_inline_save, {"name": "Tendone"}, option_uuid=str(option.uuid))

        payload = json.loads(response.content)
        assert payload["success"] is True
        option.refresh_from_db()
        assert option.name == "Tendone"
        assert option.price == 10
        assert option.description == "In giardino"

    def test_inline_save_validation_error(self) -> None:
        question = self._question()

        response = self._call(options_inline_save, {"question_uuid": str(question.uuid), "name": ""})

        assert response.status_code == 400
        payload = json.loads(response.content)
        assert payload["success"] is False
        assert "name" in payload["errors"]

    def test_inline_save_blank_price_and_max_treated_as_zero(self) -> None:
        question = self._question()

        response = self._call(
            options_inline_save,
            {"question_uuid": str(question.uuid), "name": "Tenda", "price": "", "max_available": ""},
        )

        payload = json.loads(response.content)
        assert payload["success"] is True, payload
        option = RegistrationOption.objects.get(uuid=payload["option"]["uuid"])
        assert option.price == 0
        assert option.max_available == 0

    def test_inline_reorder(self) -> None:
        question = self._question()
        first = RegistrationOption.objects.create(event=self.get_event(), question=question, name="A", price=0, order=1)
        second = RegistrationOption.objects.create(
            event=self.get_event(), question=question, name="B", price=0, order=2
        )

        response = self._call(options_inline_reorder, {"uuids[]": [str(second.uuid), str(first.uuid)]})

        payload = json.loads(response.content)
        assert payload["success"] is True
        first.refresh_from_db()
        second.refresh_from_db()
        assert (second.order, first.order) == (1, 2)

    def test_inline_reorder_rejects_foreign_options(self) -> None:
        question = self._question()
        other_question = RegistrationQuestion.objects.create(event=self.get_event(), typ="s", name="Pasti", order=2)
        mine = RegistrationOption.objects.create(event=self.get_event(), question=question, name="A", price=0)
        other = RegistrationOption.objects.create(event=self.get_event(), question=other_question, name="B", price=0)

        response = self._call(options_inline_reorder, {"uuids[]": [str(mine.uuid), str(other.uuid)]})

        assert response.status_code == 400

    def test_inline_delete(self) -> None:
        question = self._question()
        option = RegistrationOption.objects.create(event=self.get_event(), question=question, name="A", price=0)

        response = self._call(options_inline_delete, {}, option_uuid=str(option.uuid))

        payload = json.loads(response.content)
        assert payload["success"] is True
        assert not RegistrationOption.objects.filter(pk=option.pk).exists()
