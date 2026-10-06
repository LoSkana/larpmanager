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


"""Tests for experience calls: CSV export/import and the per-character calls summary"""

import pytest

from larpmanager.models.event import EventConfig
from larpmanager.models.experience import AbilityExp, AbilityTypeExp, CallExp, ModifierExp, RuleExp
from larpmanager.models.form import QuestionApplicable, QuestionStatus, WritingQuestion, WritingQuestionType
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.io.download import (
    export_abilities,
    export_ability_types,
    export_calls,
    export_modifiers,
    export_rules,
    zip_exports,
)
from larpmanager.utils.io.restore import _FakeFile, _FakeForm, execute_restore, preview_restore
from larpmanager.utils.io.upload import calls_load
from larpmanager.utils.services.experience import add_calls_tooltips, get_character_calls


@pytest.mark.django_db(transaction=True)
class TestExperienceCalls(BaseTestCase):
    """Test cases for calls CSV export/import and the calls summary filter"""

    def setUp(self) -> None:
        self.event = self.get_event()
        self.system = self.get_system_exp(self.event)
        self.context = {
            "event": self.event,
            "run": self.get_run(),
            "features": set(),
            "association_id": self.event.association_id,
            "member": self.get_member(),
            "typ": "exp_call",
        }

    def _ability(self, number: int, descr: str) -> AbilityExp:
        return AbilityExp.objects.create(
            event=self.event, name=f"ab{number}", number=number, system=self.system, descr=descr
        )

    def test_upload_creates_and_updates_by_name(self) -> None:
        """Uploaded calls are created, then updated when the name matches ignoring case"""
        logs = calls_load(self.context, _FakeForm(first=_FakeFile(b"name,descr\nSTUN,Fall down\nBLEED,Lose blood\n")))
        self.assertTrue(all(log.startswith("OK - Created") for log in logs), logs)
        self.assertEqual(CallExp.objects.filter(event=self.event).count(), 2)

        logs = calls_load(self.context, _FakeForm(first=_FakeFile(b"name,descr\nstun,Kneel\n")))
        self.assertTrue(logs[0].startswith("OK - Updated"), logs)
        self.assertEqual(CallExp.objects.filter(event=self.event).count(), 2)
        self.assertEqual(CallExp.objects.get(event=self.event, name="STUN").descr, "Kneel")

    def test_export_round_trip(self) -> None:
        """Exported calls list name and description in display order"""
        CallExp.objects.create(event=self.event, name="STUN", descr="Fall down", order=2)
        CallExp.objects.create(event=self.event, name="BLEED", descr="Lose blood", order=1)
        name, headers, rows = export_calls(self.context)[0]
        self.assertEqual(name, "calls")
        self.assertEqual(headers, ["name", "descr"])
        self.assertEqual(rows, [["BLEED", "Lose blood"], ["STUN", "Fall down"]])

    def test_character_calls_filter(self) -> None:
        """Only calls written as standalone uppercase words in the abilities descriptions are returned"""
        CallExp.objects.create(event=self.event, name="Stun", descr="Fall down", order=1)
        CallExp.objects.create(event=self.event, name="BLEED", order=2)
        CallExp.objects.create(event=self.event, name="FIRE", order=3)
        CallExp.objects.create(event=self.event, name="KNOCK", order=4)
        abilities = [
            self._ability(1, "<p>Call <strong>STUN</strong> on a hit.</p>"),
            self._ability(2, "<p>You may bleed, or call FIREBALL, or knock.</p>"),
        ]

        self.assertEqual(get_character_calls(self.event.id, abilities), [])

        EventConfig.objects.create(event=self.event, name="exp_calls", value="True")
        self.assertEqual(get_character_calls(self.event.id, abilities), [{"name": "STUN", "descr": "Fall down"}])

        # Saving a call refreshes the cached calls
        CallExp.objects.create(event=self.event, name="KNOCK DOWN", order=5)
        abilities.append(self._ability(3, "<p>Call KNOCK DOWN.</p>"))
        self.assertEqual(
            [call["name"] for call in get_character_calls(self.event.id, abilities)], ["STUN", "KNOCK DOWN"]
        )

    def test_calls_tooltips(self) -> None:
        """Calls in the description text get a tooltip, while tag attributes and other words are untouched"""
        calls = [
            {"name": "STUN", "descr": "<p>Fall down</p>"},
            {"name": "MASS STUN", "descr": "<p>Everyone falls</p>"},
            {"name": "BLEED", "descr": ""},
        ]
        text = '<p title="STUN">Call STUN or MASS STUN, not STUNNING or BLEED</p>'

        result = add_calls_tooltips(text, calls)

        self.assertEqual(
            result,
            '<p title="STUN">Call '
            "<span class='exp-call' data-call-descr='&lt;p&gt;Fall down&lt;/p&gt;'>STUN</span> or "
            "<span class='exp-call' data-call-descr='&lt;p&gt;Everyone falls&lt;/p&gt;'>MASS STUN</span>"
            ", not STUNNING or BLEED</p>",
        )
        self.assertEqual(add_calls_tooltips(text, []), text)

    def test_backup_restore_round_trip(self) -> None:
        """Ability types, rules, modifiers and calls are restored from a backup zip"""
        ability_type = AbilityTypeExp.objects.create(event=self.event, name="Combat")
        ability = AbilityExp.objects.create(
            event=self.event, name="sword", number=1, system=self.system, typ=ability_type, cost=2
        )
        field = WritingQuestion.objects.create(
            event=self.event,
            name="strength",
            description="Strength",
            typ=WritingQuestionType.COMPUTED,
            status=QuestionStatus.OPTIONAL,
            applicable=QuestionApplicable.CHARACTER,
        )
        rule = RuleExp.objects.create(event=self.event, number=1, field=field, amount=2)
        rule.abilities.add(ability)
        modifier = ModifierExp.objects.create(event=self.event, number=1, cost=3)
        modifier.abilities.add(ability)
        CallExp.objects.create(event=self.event, name="STUN", descr="Fall down")

        exports = []
        for export in (export_ability_types, export_abilities, export_rules, export_modifiers, export_calls):
            exports.extend(export(self.context))
        zip_bytes = zip_exports(self.context, exports, "backup").content

        # Remove the elements, so that the restore must recreate them
        for model in (CallExp, ModifierExp, RuleExp):
            model.objects.filter(event=self.event).delete()

        sections, unknown = preview_restore(self.context, zip_bytes)
        assert unknown == []
        labels = [section["label"] for section in sections]
        assert labels == ["Ability types", "Abilities", "Rules", "Modifiers", "Calls"]

        logs = execute_restore(self.context, zip_bytes)
        assert not [log for log in logs if log.startswith("ERR")], logs

        restored_rule = RuleExp.objects.get(event=self.event, number=1)
        assert restored_rule.field_id == field.id
        assert list(restored_rule.abilities.all()) == [ability]
        assert list(ModifierExp.objects.get(event=self.event, number=1).abilities.all()) == [ability]
        assert CallExp.objects.get(event=self.event, name="STUN").descr == "Fall down"
