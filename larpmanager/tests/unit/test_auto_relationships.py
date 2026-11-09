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

"""Unit tests for the relationships created from character references."""

import pytest
from django.core.cache import cache

from larpmanager.models.writing import Character, Plot, PlotCharacterRel, Relationship
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.services.character import get_character_relationships, update_character_referenced_chars


@pytest.mark.django_db
class TestAutoRelationships(BaseTestCase):
    """Check the text and the visibility of relationships created from references."""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.event = self.create_event(name="Vaelmoor")
        self.run = self.event.runs.first()
        self.hero = Character.objects.create(event=self.event, name="Lucian", number=1)
        self.rival = Character.objects.create(event=self.event, name="Aurelio", number=2)

    def _auto_relationship(self) -> Relationship:
        update_character_referenced_chars(self.hero.id)
        return Relationship.objects.get(source=self.hero, target=self.rival, auto=True)

    def test_sheet_text_reference_has_empty_text(self) -> None:
        self.hero.text = "<p>Your rival is #2</p>"
        self.hero.save()
        assert self._auto_relationship().text == ""

    def test_plot_reference_keeps_plot_name(self) -> None:
        self.hero.text = "<p>Your rival is #2</p>"
        self.hero.save()
        plot = Plot.objects.create(event=self.event, name="The Succession", text="<p>#2 claims the throne</p>")
        PlotCharacterRel.objects.create(plot=plot, character=self.hero)
        assert self._auto_relationship().text == "<b><i>The Succession</i></b>"

    def test_empty_auto_relationship_shown_on_sheet(self) -> None:
        self.hero.text = "<p>Your rival is #2</p>"
        self.hero.save()
        self._auto_relationship()
        context = {"character": self.hero, "event": self.event, "run": self.run, "factions": {}}
        get_character_relationships(context)
        assert [entry["name"] for entry in context["rel"]] == [self.rival.name]

    def test_empty_manual_relationship_hidden_on_sheet(self) -> None:
        Relationship.objects.create(source=self.hero, target=self.rival, text="")
        context = {"character": self.hero, "event": self.event, "run": self.run, "factions": {}}
        get_character_relationships(context)
        assert context["rel"] == []
