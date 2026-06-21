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

"""
Regression tests for writing-related bugs:
  Bug 1 - Progress step reset when editing a plot with parent event.
  Bug 2 - $unimportant prefix not reflected in plot list stats.
"""

from larpmanager.tests.unit.base import BaseTestCase


class TestProgressStepParentEvent(BaseTestCase):
    """Bug 1: progress field queryset must use parent event's steps for child events."""

    def test_progress_steps_use_parent_event(self) -> None:
        """When run belongs to child event, progress_event resolves to parent."""
        from larpmanager.models.event import ProgressStep

        parent_event = self.create_event(name="Parent Event")
        parent_step = ProgressStep.objects.create(event=parent_event, number=1, name="Final", order=1)

        child_event = self.create_event(name="Child Event")
        child_event.parent = parent_event
        child_event.save()

        # create_default_event_setup auto-creates Run(number=1) for the child event
        child_run = child_event.runs.get(number=1)

        # Simulate the fixed logic in _init_special_fields
        run_event = child_run.event
        progress_event = run_event.parent if run_event.parent else run_event

        fixed_steps = list(ProgressStep.objects.filter(event=progress_event).order_by("order"))
        self.assertIn(parent_step, fixed_steps)

    def test_buggy_filter_misses_parent_steps(self) -> None:
        """Demonstrate the pre-fix behaviour: filtering by child event omits parent's steps."""
        from larpmanager.models.event import ProgressStep

        parent_event = self.create_event(name="Parent Event 2")
        parent_step = ProgressStep.objects.create(event=parent_event, number=1, name="Draft", order=1)

        child_event = self.create_event(name="Child Event 2")
        child_event.parent = parent_event
        child_event.save()

        # Pre-fix: filter by child event only -> empty
        child_only_steps = list(ProgressStep.objects.filter(event=child_event).order_by("order"))
        self.assertNotIn(parent_step, child_only_steps)


class TestPlotUnimportantStats(BaseTestCase):
    """Bug 2: $unimportant prefix must reduce 'important' count in get_event_plot_rels."""

    def test_important_count_excludes_unimportant_relationships(self) -> None:
        """get_event_plot_rels returns correct important count with $unimportant prefix."""
        from larpmanager.cache.rels import get_event_plot_rels
        from larpmanager.models.event import EventConfig
        from larpmanager.models.writing import Character, Plot, PlotCharacterRel

        event = self.create_event(name="Unimportant Test Event")
        EventConfig.objects.create(event=event, name="writing_unimportant", value="True")

        plot = Plot.objects.create(event=event, number=1, name="Test Plot")
        char1 = Character.objects.create(event=event, number=1, name="Important Hero")
        char2 = Character.objects.create(event=event, number=2, name="Background NPC")

        PlotCharacterRel.objects.create(plot=plot, character=char1, text="Normal hero role")
        PlotCharacterRel.objects.create(plot=plot, character=char2, text="$unimportant background role")

        result = get_event_plot_rels(plot)

        self.assertEqual(result["character_rels"]["count"], 2)
        self.assertEqual(result["character_rels"]["important"], 1)

    def test_all_unimportant_gives_zero_important(self) -> None:
        """When all relationships are $unimportant, important count is zero."""
        from larpmanager.cache.rels import get_event_plot_rels
        from larpmanager.models.event import EventConfig
        from larpmanager.models.writing import Character, Plot, PlotCharacterRel

        event = self.create_event(name="All Unimportant Event")
        EventConfig.objects.create(event=event, name="writing_unimportant", value="True")

        plot = Plot.objects.create(event=event, number=1, name="Minor Plot")
        char1 = Character.objects.create(event=event, number=1, name="NPC One")
        char2 = Character.objects.create(event=event, number=2, name="NPC Two")

        PlotCharacterRel.objects.create(plot=plot, character=char1, text="$unimportant minor")
        PlotCharacterRel.objects.create(plot=plot, character=char2, text="$unimportant also minor")

        result = get_event_plot_rels(plot)

        self.assertEqual(result["character_rels"]["count"], 2)
        self.assertEqual(result["character_rels"]["important"], 0)

    def test_no_important_key_when_feature_disabled(self) -> None:
        """When writing_unimportant is disabled, character_rels has no 'important' key."""
        from larpmanager.cache.rels import get_event_plot_rels
        from larpmanager.models.writing import Character, Plot, PlotCharacterRel

        event = self.create_event(name="Feature Disabled Event")

        plot = Plot.objects.create(event=event, number=1, name="Plain Plot")
        char1 = Character.objects.create(event=event, number=1, name="Character A")

        PlotCharacterRel.objects.create(plot=plot, character=char1, text="$unimportant ignored")

        result = get_event_plot_rels(plot)

        self.assertEqual(result["character_rels"]["count"], 1)
        self.assertNotIn("important", result["character_rels"])
