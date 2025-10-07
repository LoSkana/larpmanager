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

"""Tests for experience point calculation functions"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from larpmanager.utils.experience import (
    _apply_modifier_cost,
    check_available_ability_px,
    get_free_abilities,
    set_free_abilities,
)
from larpmanager.tests.unit.base import BaseTestCase


class TestExperienceUtilityFunctions(BaseTestCase):
    """Test cases for experience utility functions"""

    def test_get_free_abilities_empty(self):
        """Test get_free_abilities with no free abilities"""
        character = MagicMock()
        character.get_config.return_value = "[]"

        result = get_free_abilities(character)

        self.assertEqual(result, [])

    def test_get_free_abilities_with_list(self):
        """Test get_free_abilities with abilities"""
        character = MagicMock()
        character.get_config.return_value = "[1, 2, 3]"

        result = get_free_abilities(character)

        self.assertEqual(result, [1, 2, 3])

    def test_set_free_abilities_basic(self):
        """Test set_free_abilities stores list"""
        from unittest.mock import call

        character = MagicMock()

        with patch("larpmanager.utils.experience.save_single_config") as mock_save:
            set_free_abilities(character, [1, 2, 3])

            mock_save.assert_called_once()
            args = mock_save.call_args[0]
            self.assertEqual(args[0], character)
            self.assertEqual(args[1], "free_abilities")
            self.assertEqual(args[2], "[1, 2, 3]")

    def test_check_available_ability_px_no_prereq(self):
        """Test check_available_ability_px with no prerequisites"""
        ability = MagicMock()
        ability.prerequisites.all.return_value = []
        ability.requirements.all.return_value = []

        result = check_available_ability_px(ability, set(), set())

        self.assertTrue(result)

    def test_check_available_ability_px_prereq_met(self):
        """Test check_available_ability_px with prerequisites met"""
        prereq1 = MagicMock()
        prereq1.id = 1
        prereq2 = MagicMock()
        prereq2.id = 2

        ability = MagicMock()
        ability.prerequisites.all.return_value = [prereq1, prereq2]
        ability.requirements.all.return_value = []

        current_abilities = {1, 2, 3}
        result = check_available_ability_px(ability, current_abilities, set())

        self.assertTrue(result)

    def test_check_available_ability_px_prereq_not_met(self):
        """Test check_available_ability_px with prerequisites not met"""
        prereq1 = MagicMock()
        prereq1.id = 1
        prereq2 = MagicMock()
        prereq2.id = 5

        ability = MagicMock()
        ability.prerequisites.all.return_value = [prereq1, prereq2]
        ability.requirements.all.return_value = []

        current_abilities = {1, 2, 3}
        result = check_available_ability_px(ability, current_abilities, set())

        # Missing prerequisite 5
        self.assertFalse(result)

    def test_check_available_ability_px_requirements_met(self):
        """Test check_available_ability_px with requirements met"""
        req1 = MagicMock()
        req1.id = 10
        req2 = MagicMock()
        req2.id = 20

        ability = MagicMock()
        ability.prerequisites.all.return_value = []
        ability.requirements.all.return_value = [req1, req2]

        current_choices = {10, 20, 30}
        result = check_available_ability_px(ability, set(), current_choices)

        self.assertTrue(result)

    def test_check_available_ability_px_requirements_not_met(self):
        """Test check_available_ability_px with requirements not met"""
        req1 = MagicMock()
        req1.id = 10
        req2 = MagicMock()
        req2.id = 25

        ability = MagicMock()
        ability.prerequisites.all.return_value = []
        ability.requirements.all.return_value = [req1, req2]

        current_choices = {10, 20, 30}
        result = check_available_ability_px(ability, set(), current_choices)

        # Missing requirement 25
        self.assertFalse(result)

    def test_apply_modifier_cost_no_modifiers(self):
        """Test apply_modifier_cost with no modifiers"""
        ability = MagicMock()
        ability.id = 1
        ability.cost = 100

        mods_by_ability = {}
        _apply_modifier_cost(ability, mods_by_ability, set(), set())

        # Cost should remain unchanged
        self.assertEqual(ability.cost, 100)

    def test_apply_modifier_cost_basic(self):
        """Test apply_modifier_cost with basic modifier"""
        ability = MagicMock()
        ability.id = 1
        ability.cost = 100

        # Modifier: cost 50, no prereqs, no reqs
        mods_by_ability = {1: [(50, set(), set())]}

        _apply_modifier_cost(ability, mods_by_ability, set(), set())

        # Cost should be modified to 50
        self.assertEqual(ability.cost, 50)

    def test_apply_modifier_cost_prereq_not_met(self):
        """Test apply_modifier_cost with prerequisite not met"""
        ability = MagicMock()
        ability.id = 1
        ability.cost = 100

        # Modifier requires prerequisite ability 5
        mods_by_ability = {1: [(50, {5}, set())]}
        current_abilities = {1, 2, 3}

        _apply_modifier_cost(ability, mods_by_ability, current_abilities, set())

        # Cost should remain unchanged (prereq not met)
        self.assertEqual(ability.cost, 100)

    def test_apply_modifier_cost_prereq_met(self):
        """Test apply_modifier_cost with prerequisite met"""
        ability = MagicMock()
        ability.id = 1
        ability.cost = 100

        # Modifier requires prerequisite ability 5
        mods_by_ability = {1: [(50, {5}, set())]}
        current_abilities = {1, 2, 3, 5}

        _apply_modifier_cost(ability, mods_by_ability, current_abilities, set())

        # Cost should be modified (prereq met)
        self.assertEqual(ability.cost, 50)

    def test_apply_modifier_cost_requirement_not_met(self):
        """Test apply_modifier_cost with requirement not met"""
        ability = MagicMock()
        ability.id = 1
        ability.cost = 100

        # Modifier requires choice option 10
        mods_by_ability = {1: [(50, set(), {10})]}
        current_choices = {5, 6, 7}

        _apply_modifier_cost(ability, mods_by_ability, set(), current_choices)

        # Cost should remain unchanged (req not met)
        self.assertEqual(ability.cost, 100)

    def test_apply_modifier_cost_requirement_met(self):
        """Test apply_modifier_cost with requirement met"""
        ability = MagicMock()
        ability.id = 1
        ability.cost = 100

        # Modifier requires choice option 10
        mods_by_ability = {1: [(50, set(), {10})]}
        current_choices = {5, 6, 7, 10}

        _apply_modifier_cost(ability, mods_by_ability, set(), current_choices)

        # Cost should be modified (req met)
        self.assertEqual(ability.cost, 50)

    def test_apply_modifier_cost_first_valid_wins(self):
        """Test apply_modifier_cost uses first valid modifier"""
        ability = MagicMock()
        ability.id = 1
        ability.cost = 100

        # Multiple modifiers, first one is valid
        mods_by_ability = {1: [(30, set(), set()), (50, set(), set()), (70, set(), set())]}

        _apply_modifier_cost(ability, mods_by_ability, set(), set())

        # Should use first valid modifier (30)
        self.assertEqual(ability.cost, 30)

    def test_apply_modifier_cost_skip_invalid_use_valid(self):
        """Test apply_modifier_cost skips invalid and uses first valid"""
        ability = MagicMock()
        ability.id = 1
        ability.cost = 100

        # First modifier has unmet prereq, second is valid
        mods_by_ability = {1: [(30, {99}, set()), (50, set(), set()), (70, set(), set())]}
        current_abilities = {1, 2, 3}

        _apply_modifier_cost(ability, mods_by_ability, current_abilities, set())

        # Should skip first (prereq 99 not met) and use second (50)
        self.assertEqual(ability.cost, 50)

    def test_apply_modifier_cost_multiple_prereqs_and_reqs(self):
        """Test apply_modifier_cost with both prerequisites and requirements"""
        ability = MagicMock()
        ability.id = 1
        ability.cost = 100

        # Modifier requires both prereqs and reqs
        mods_by_ability = {1: [(50, {2, 3}, {10, 20})]}
        current_abilities = {1, 2, 3, 4}
        current_choices = {10, 20, 30}

        _apply_modifier_cost(ability, mods_by_ability, current_abilities, current_choices)

        # Both prereqs and reqs met
        self.assertEqual(ability.cost, 50)
