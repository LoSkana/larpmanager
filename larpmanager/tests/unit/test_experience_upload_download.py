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

"""Tests for experience CSV export/import, including the experience system column"""

from typing import Any
from unittest import mock

import pandas as pd
import pytest

from larpmanager.cache.experience import clear_event_exp_systems_cache
from larpmanager.models.experience import AbilityExp, CriterionExp, DeliveryExp, SystemExp
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    WritingOption,
    WritingQuestion,
)
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.common import get_class_parent
from larpmanager.utils.io.download import (
    _get_column_names,
    export_abilities,
    export_criterions,
    export_deliveries,
)
from larpmanager.utils.io.restore import _FakeFile, _FakeForm, _preview_abilities, _preview_deliveries
from larpmanager.utils.io.upload import (
    _ability_load,
    _assign_requirements,
    _criterion_load,
    _delivery_load,
    abilities_load,
    criterions_load,
    deliveries_load,
)


@pytest.mark.django_db(transaction=True)
class TestExperienceUploadDownload(BaseTestCase):
    """Test cases for ability, criterion and delivery CSV export/import"""

    def setUp(self) -> None:
        self.event = self.get_event()
        self.run = self.get_run()
        self.system = self.get_system_exp(self.event)
        self.context = {
            "event": self.event,
            "run": self.run,
            "features": set(),
            "association_id": self.event.association_id,
            "member": self.get_member(),
        }
        clear_event_exp_systems_cache(self.event.id)

    def _add_second_system(self) -> Any:
        system, _created = SystemExp.objects.get_or_create(event=self.event, number=2, defaults={"name": "Karma"})
        clear_event_exp_systems_cache(self.event.id)
        return system

    def _load_csv(self, typ: str, csv_text: str) -> list[str]:
        """Run a real CSV through the loader of the given upload type, as an upload would"""
        context = {**self.context, "typ": typ}
        form = _FakeForm(first=_FakeFile(csv_text.encode()))
        loaders = {
            "exp_abilitie": abilities_load,
            "exp_criterion": criterions_load,
            "exp_deliverie": deliveries_load,
        }
        return loaders[typ](context, form)

    def _writing_options(self) -> tuple[Any, Any]:
        """Create a writing question with two options, usable as criterion requirements"""
        question = WritingQuestion.objects.create(
            event=self.event,
            name="origin",
            description="Where do you come from?",
            typ=BaseQuestionType.SINGLE,
            status=QuestionStatus.OPTIONAL,
            applicable=QuestionApplicable.CHARACTER,
            order=1,
        )
        first = WritingOption.objects.create(event=self.event, question=question, name="North", order=1)
        second = WritingOption.objects.create(event=self.event, question=question, name="South", order=2)
        return first, second

    def _columns(self, typ: str) -> dict:
        context = {**self.context, "typ": typ}
        _get_column_names(context)
        return context["columns"][0]

    def test_system_column_hidden_with_single_system(self) -> None:
        """The system column is not offered when only one experience system exists"""
        for typ in ("exp_abilitie", "exp_criterion", "exp_deliverie"):
            self.assertNotIn("system", self._columns(typ))

        AbilityExp.objects.create(event=self.event, name="sword", number=1, system=self.system, cost=2)
        _name, headers, _rows = export_abilities(self.context)[0]
        self.assertNotIn("system", headers)

    def test_system_column_shown_with_multiple_systems(self) -> None:
        """The system column is offered and exported when multiple systems exist"""
        second = self._add_second_system()

        for typ in ("exp_abilitie", "exp_criterion", "exp_deliverie"):
            self.assertIn("system", self._columns(typ))

        AbilityExp.objects.create(event=self.event, name="sword", number=1, system=second, cost=2)
        _name, headers, rows = export_abilities(self.context)[0]
        self.assertEqual(headers[-1], "system")
        self.assertEqual(rows[0][-1], second.name)

    def test_ability_load_assigns_system(self) -> None:
        """Uploading an ability row assigns the experience system by name"""
        second = self._add_second_system()

        result = _ability_load(self.context, {"name": "sword", "cost": "3", "system": "Karma"})

        self.assertTrue(result.startswith("OK"))
        ability = AbilityExp.objects.get(event=self.event, name="sword")
        self.assertEqual(ability.system_id, second.id)
        self.assertEqual(ability.cost, 3)

    def test_ability_is_matched_ignoring_case(self) -> None:
        """An ability is updated even when the uploaded name differs only by case"""
        _ability_load(self.context, {"name": "sword", "cost": "3"})

        result = _ability_load(self.context, {"name": "Sword", "cost": "5"})

        self.assertTrue(result.startswith("OK - Updated"))
        self.assertEqual(AbilityExp.objects.get(event=self.event, name="sword").cost, 5)
        self.assertEqual(AbilityExp.objects.filter(event=self.event).count(), 1)

    def test_ability_relations_are_kept_when_the_cell_is_empty(self) -> None:
        """An empty ability relation cell keeps the stored relation instead of clearing it"""
        first, _second = self._writing_options()
        AbilityExp.objects.create(event=self.event, name="shield", number=2, system=self.system, cost=2)

        _ability_load(self.context, {"name": "sword", "prerequisites": "shield", "requirements": first.name})
        self._load_csv("exp_abilitie", "name,cost,prerequisites,requirements\nsword,4,,\n")

        ability = AbilityExp.objects.get(event=self.event, name="sword")
        self.assertEqual(ability.cost, 4)
        self.assertEqual(list(ability.prerequisites.values_list("name", flat=True)), ["shield"])
        self.assertEqual(list(ability.requirements.values_list("name", flat=True)), [first.name])

    def test_ability_preview_matches_the_execution_ignoring_case(self) -> None:
        """The restore preview reports an update when only the case of the ability name differs"""
        _ability_load(self.context, {"name": "sword", "cost": "3"})

        section = _preview_abilities(self.context, pd.DataFrame([{"name": "Sword", "cost": 5}]))

        self.assertEqual(section["updates"], ["Sword"])
        self.assertEqual(section["creates"], [])

    def test_ability_relations_are_replaced_when_the_cell_has_data(self) -> None:
        """A filled ability relation cell replaces the stored relation instead of adding to it"""
        first, second = self._writing_options()
        ability = AbilityExp.objects.create(event=self.event, name="sword", number=1, system=self.system, cost=2)
        ability.requirements.add(first)

        _ability_load(self.context, {"name": "sword", "requirements": second.name})

        self.assertEqual(list(ability.requirements.values_list("name", flat=True)), [second.name])

    def test_ability_visible_round_trip(self) -> None:
        """The visible flag is exported as text, and read back by an upload of the same file"""
        AbilityExp.objects.create(event=self.event, name="sword", number=1, system=self.system, cost=2, visible=False)

        self.assertIn("visible", self._columns("exp_abilitie"))
        _name, headers, rows = export_abilities(self.context)[0]
        row = dict(zip(headers, rows[0], strict=True))
        self.assertEqual(row["visible"], "false")

        self._load_csv("exp_abilitie", "name,visible\nsword,true\n")
        self.assertTrue(AbilityExp.objects.get(event=self.event, name="sword").visible)

    def test_ability_visible_is_kept_when_the_cell_is_empty(self) -> None:
        """A blank visible cell keeps the stored flag instead of hiding the ability"""
        AbilityExp.objects.create(event=self.event, name="sword", number=1, system=self.system, cost=2)

        self._load_csv("exp_abilitie", "name,cost,visible\nsword,4,\n")

        ability = AbilityExp.objects.get(event=self.event, name="sword")
        self.assertEqual(ability.cost, 4)
        self.assertTrue(ability.visible)

    def test_criterion_round_trip(self) -> None:
        """Criterion rows are imported and exported back with the same values"""
        second = self._add_second_system()

        result = _criterion_load(
            self.context,
            {"number": "1", "name": "bonus", "operation": "ADD", "amount": "5", "order": "1", "system": "Karma"},
        )

        self.assertTrue(result.startswith("OK"))
        criterion = CriterionExp.objects.get(event=self.event, number=1)
        self.assertEqual(criterion.system_id, second.id)

        _name, headers, rows = export_criterions(self.context)[0]
        row = dict(zip(headers, rows[0], strict=True))
        self.assertEqual(row["name"], "bonus")
        self.assertEqual(row["operation"], "ADD")
        self.assertEqual(str(row["amount"]), "5.00")
        self.assertEqual(row["system"], second.name)

    def test_delivery_round_trip(self) -> None:
        """Delivery rows are imported and exported back with the same values"""
        character = self.character(self.event, name="Awarded Char")
        result = _delivery_load(
            self.context,
            {"number": "7", "name": "first award", "amount": "10", "characters": character.name, "order": "1"},
        )

        self.assertTrue(result.startswith("OK"))
        delivery = DeliveryExp.objects.get(event=self.event, name="first award")
        self.assertEqual(delivery.amount, 10)
        self.assertEqual(delivery.system_id, self.system.id)
        self.assertEqual(list(delivery.characters.values_list("id", flat=True)), [character.id])

        _name, headers, rows = export_deliveries(self.context)[0]
        row = dict(zip(headers, rows[0], strict=True))
        self.assertEqual(row["number"], 7)
        self.assertEqual(row["name"], "first award")
        self.assertEqual(row["amount"], 10)
        self.assertEqual(row["characters"], character.name)
        self.assertNotIn("system", headers)

    def test_delivery_is_matched_ignoring_case(self) -> None:
        """A delivery is updated even when the uploaded name differs only by case"""
        _delivery_load(self.context, {"name": "first award", "amount": "10"})

        result = _delivery_load(self.context, {"name": "First Award", "amount": "20"})

        self.assertTrue(result.startswith("OK - Updated"))
        self.assertEqual(DeliveryExp.objects.get(event=self.event, name="first award").amount, 20)
        self.assertEqual(DeliveryExp.objects.filter(event=self.event).count(), 1)

    def test_delivery_number_is_not_reassigned_on_update(self) -> None:
        """The number of an existing delivery is kept, and the uploaded one is reported"""
        _delivery_load(self.context, {"number": "7", "name": "first award", "amount": "10"})

        result = _delivery_load(self.context, {"number": "9", "name": "first award", "amount": "20"})

        self.assertIn("WARN - number kept as 7, ignoring the uploaded one: 9", result)
        delivery = DeliveryExp.objects.get(event=self.event, name="first award")
        self.assertEqual(delivery.number, 7)
        self.assertEqual(delivery.amount, 20)

    def test_unknown_column_is_reported_once_for_the_whole_file(self) -> None:
        """An unrecognized column is dropped when the file is read, so it is reported only once"""
        csv_text = "number,name,amount,event_id\n1,bonus,5,999\n2,malus,3,999\n"

        logs = self._load_csv("exp_criterion", csv_text)

        self.assertEqual(len([log for log in logs if "event_id" in log]), 1)
        self.assertIn("WARN - columns ignored: event_id", logs[0])
        parent_id = get_class_parent(self.event.id, CriterionExp)
        self.assertEqual(CriterionExp.objects.get(event=self.event, number=1).event_id, parent_id)

    def test_criterion_row_is_rolled_back_on_failure(self) -> None:
        """A row that fails midway leaves no half written criterion behind"""
        first, second = self._writing_options()
        criterion = CriterionExp.objects.create(event=self.event, number=1, name="bonus", system=self.system)
        criterion.requirements.add(first, second)

        row = {"number": "1", "name": "bonus", "amount": "5", "requirements": first.name}
        with (
            mock.patch("larpmanager.utils.io.upload.save_log", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            _criterion_load(self.context, row)

        criterion.refresh_from_db()
        self.assertEqual(criterion.amount, 0)
        self.assertEqual(
            sorted(criterion.requirements.values_list("name", flat=True)), sorted([first.name, second.name])
        )

    def test_delivery_preview_matches_the_execution_ignoring_case(self) -> None:
        """The restore preview reports an update when only the case of the name differs"""
        _delivery_load(self.context, {"name": "first award", "amount": "10"})

        section = _preview_deliveries(self.context, pd.DataFrame([{"name": "First Award", "amount": 20}]))

        self.assertEqual(section["updates"], ["First Award"])
        self.assertEqual(section["creates"], [])

    def test_criterion_relations_are_replaced_on_reupload(self) -> None:
        """Re-uploading a criterion replaces its relations instead of accumulating them"""
        AbilityExp.objects.create(event=self.event, name="sword", number=1, system=self.system, cost=2)
        AbilityExp.objects.create(event=self.event, name="shield", number=2, system=self.system, cost=2)

        row = {"number": "1", "name": "bonus", "operation": "ADD", "amount": "5", "prerequisites": "sword, shield"}
        _criterion_load(self.context, row)
        _criterion_load(self.context, {**row, "prerequisites": "sword"})

        criterion = CriterionExp.objects.get(event=self.event, number=1)
        self.assertEqual(list(criterion.prerequisites.values_list("name", flat=True)), ["sword"])

    def test_delivery_characters_are_replaced_on_reupload(self) -> None:
        """Re-uploading a delivery replaces its characters instead of accumulating them"""
        first = self.character(self.event, name="First Char")
        second = self.character(self.event, name="Second Char")

        row = {"name": "award", "amount": "10", "characters": f"{first.name}, {second.name}"}
        _delivery_load(self.context, row)
        _delivery_load(self.context, {**row, "characters": second.name})

        delivery = DeliveryExp.objects.get(event=self.event, name="award")
        self.assertEqual(list(delivery.characters.values_list("id", flat=True)), [second.id])

    def test_empty_relation_column_clears_relations(self) -> None:
        """An empty relation cell clears the relation instead of being ignored"""
        AbilityExp.objects.create(event=self.event, name="sword", number=1, system=self.system, cost=2)

        row = {"number": "1", "name": "bonus", "amount": "5", "prerequisites": "sword"}
        _criterion_load(self.context, row)
        _criterion_load(self.context, {**row, "prerequisites": ""})

        criterion = CriterionExp.objects.get(event=self.event, number=1)
        self.assertEqual(list(criterion.prerequisites.all()), [])

    def test_zero_amount_is_applied_on_update(self) -> None:
        """A zero value overwrites the previous one instead of being treated as empty"""
        _criterion_load(self.context, {"number": "1", "name": "bonus", "amount": "5"})
        _criterion_load(self.context, {"number": "1", "name": "bonus", "amount": "0"})

        criterion = CriterionExp.objects.get(event=self.event, number=1)
        self.assertEqual(criterion.amount, 0)

    def test_blank_scalar_column_is_ignored(self) -> None:
        """A blank scalar cell keeps the stored value and reports no error"""
        _criterion_load(self.context, {"number": "1", "name": "bonus", "amount": "5", "operation": "SUB"})

        result = _criterion_load(self.context, {"number": "1", "name": "bonus", "amount": "", "operation": ""})

        self.assertEqual(result, "OK - Updated bonus")
        criterion = CriterionExp.objects.get(event=self.event, number=1)
        self.assertEqual(criterion.amount, 5)
        self.assertEqual(criterion.operation, "SUB")

    def test_unknown_column_is_ignored_and_reported(self) -> None:
        """An unrecognized column is never written on the model, and is reported"""
        result = _criterion_load(self.context, {"number": "1", "name": "bonus", "event_id": "999"})

        self.assertIn("WARN - unknown column ignored: event_id", result)
        criterion = CriterionExp.objects.get(event=self.event, number=1)
        self.assertEqual(criterion.event_id, get_class_parent(self.event.id, CriterionExp))

    def test_invalid_amount_is_reported(self) -> None:
        """An unparsable numeric value is reported without aborting the row"""
        result = _criterion_load(self.context, {"number": "1", "name": "bonus", "amount": "abc"})

        self.assertIn("ERR - invalid amount value: abc", result)
        self.assertTrue(CriterionExp.objects.filter(event=self.event, number=1).exists())

    def test_delivery_number_already_taken_is_reported(self) -> None:
        """A delivery keeps an uploaded number only when free, and reports when it is not"""
        _delivery_load(self.context, {"number": "7", "name": "first award", "amount": "10"})

        result = _delivery_load(self.context, {"number": "7", "name": "second award", "amount": "5"})

        self.assertIn("WARN - number already taken, assigned automatically: 7", result)
        self.assertNotEqual(DeliveryExp.objects.get(event=self.event, name="second award").number, 7)

    def test_delivery_reupload_does_not_warn_on_its_own_number(self) -> None:
        """Updating an existing delivery does not report its own number as taken"""
        row = {"number": "7", "name": "first award", "amount": "10"}
        _delivery_load(self.context, row)

        result = _delivery_load(self.context, row)

        self.assertEqual(result, "OK - Updated first award")

    def test_ability_errors_are_reported(self) -> None:
        """Field errors collected while loading an ability reach the upload logs"""
        self._add_second_system()

        result = _ability_load(self.context, {"name": "sword", "cost": "3", "system": "Missing"})

        self.assertIn("ERR - system not found: Missing", result)

    def test_unknown_system_is_reported(self) -> None:
        """A row referencing a missing system keeps the default and logs an error"""
        self._add_second_system()

        result = _delivery_load(self.context, {"name": "second award", "amount": "5", "system": "Missing"})

        self.assertIn("ERR - system not found: Missing", result)
        delivery = DeliveryExp.objects.get(event=self.event, name="second award")
        self.assertEqual(delivery.system_id, self.system.id)

    def test_empty_relation_cell_clears_relations_through_the_uploaded_file(self) -> None:
        """An empty relation cell of a real CSV clears the relation, instead of reading as missing"""
        AbilityExp.objects.create(event=self.event, name="sword", number=1, system=self.system, cost=2)
        self._load_csv("exp_criterion", "number,name,amount,prerequisites\n1,bonus,5,sword\n")

        self._load_csv("exp_criterion", "number,name,amount,prerequisites\n1,bonus,5,\n")

        criterion = CriterionExp.objects.get(event=self.event, number=1)
        self.assertEqual(list(criterion.prerequisites.all()), [])

    def test_missing_relation_column_keeps_relations_through_the_uploaded_file(self) -> None:
        """A relation column absent from the uploaded file leaves the stored relation untouched"""
        AbilityExp.objects.create(event=self.event, name="sword", number=1, system=self.system, cost=2)
        self._load_csv("exp_criterion", "number,name,amount,prerequisites\n1,bonus,5,sword\n")

        self._load_csv("exp_criterion", "number,name,amount\n1,bonus,5\n")

        criterion = CriterionExp.objects.get(event=self.event, number=1)
        self.assertEqual(list(criterion.prerequisites.values_list("name", flat=True)), ["sword"])

    def test_blank_scalar_cell_of_uploaded_file_is_ignored(self) -> None:
        """A blank scalar cell of a real CSV keeps the stored value"""
        self._load_csv("exp_criterion", "number,name,operation,amount\n1,bonus,SUB,5\n")

        self._load_csv("exp_criterion", "number,name,operation,amount\n1,bonus,,\n")

        criterion = CriterionExp.objects.get(event=self.event, number=1)
        self.assertEqual(criterion.amount, 5)
        self.assertEqual(criterion.operation, "SUB")

    def test_criterion_without_name_is_skipped_on_creation(self) -> None:
        """A criterion cannot be created without a name, while an existing one may omit it"""
        result = _criterion_load(self.context, {"number": "1", "name": "", "amount": "5"})

        self.assertEqual(result, "ERR - Empty name, row skipped")
        self.assertFalse(CriterionExp.objects.filter(event=self.event, number=1).exists())

        _criterion_load(self.context, {"number": "1", "name": "bonus", "amount": "5"})
        _criterion_load(self.context, {"number": "1", "amount": "8"})

        criterion = CriterionExp.objects.get(event=self.event, number=1)
        self.assertEqual(criterion.name, "bonus")
        self.assertEqual(criterion.amount, 8)

    def test_duplicate_delivery_names_are_disambiguated_by_number(self) -> None:
        """Deliveries sharing a name are updated by number, instead of aborting the upload"""
        DeliveryExp.objects.create(event=self.event, name="award", number=1, system=self.system, amount=1)
        DeliveryExp.objects.create(event=self.event, name="award", number=2, system=self.system, amount=2)

        result = _delivery_load(self.context, {"number": "2", "name": "award", "amount": "50"})

        self.assertIn("WARN - several deliveries named award, updated the one with number 2", result)
        self.assertEqual(DeliveryExp.objects.get(event=self.event, number=2).amount, 50)
        self.assertEqual(DeliveryExp.objects.get(event=self.event, number=1).amount, 1)

    def test_duplicate_delivery_names_fall_back_to_the_first(self) -> None:
        """Without a matching number, the lowest numbered of the duplicates is updated"""
        DeliveryExp.objects.create(event=self.event, name="award", number=1, system=self.system, amount=1)
        DeliveryExp.objects.create(event=self.event, name="award", number=2, system=self.system, amount=2)

        _delivery_load(self.context, {"name": "award", "amount": "50"})

        self.assertEqual(DeliveryExp.objects.get(event=self.event, number=1).amount, 50)
        self.assertEqual(DeliveryExp.objects.get(event=self.event, number=2).amount, 2)

    def test_requirements_are_added_without_replacing_when_asked(self) -> None:
        """The additive mode used by the writing option import keeps the stored requirements"""
        first, second = self._writing_options()
        criterion = CriterionExp.objects.create(event=self.event, number=1, name="bonus", system=self.system)
        criterion.requirements.add(first)

        _assign_requirements(self.context, criterion, [], second.name, replace=False)

        self.assertEqual(
            sorted(criterion.requirements.values_list("name", flat=True)), sorted([first.name, second.name])
        )

    def test_requirements_replace_the_stored_ones_by_default(self) -> None:
        """The default mode makes the upload idempotent, replacing the stored requirements"""
        first, second = self._writing_options()
        criterion = CriterionExp.objects.create(event=self.event, number=1, name="bonus", system=self.system)
        criterion.requirements.add(first)

        _assign_requirements(self.context, criterion, [], second.name)

        self.assertEqual(list(criterion.requirements.values_list("name", flat=True)), [second.name])
