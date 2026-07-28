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
# https://larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary

"""Tests for text-version snapshots."""

from larpmanager.models.writing import Plot, PlotCharacterRel, TextVersion, TextVersionChoices
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.edit.backend import save_version


class TestTextVersionPlotRoles(BaseTestCase):
    """Ensure plot-role text is retained in writing snapshots."""

    def setUp(self) -> None:
        """Create a plot and two assigned characters."""
        super().setUp()
        event = self.create_event(name="Text version event")
        self.plot = Plot.objects.create(event=event, number=1, name="The lost crown", text="Plot text")
        self.ari = self.character(event=event, number=1, name="Ari")
        other_character = self.character(event=event, number=2, name="Bea")
        PlotCharacterRel.objects.create(plot=self.plot, character=self.ari, text="<p>Find the crown.</p>")
        PlotCharacterRel.objects.create(plot=self.plot, character=other_character, text="<p>Guard the gate.</p>")

    def test_plot_version_contains_plot_text_and_every_character_role(self) -> None:
        """Saving a plot snapshots its text together with all assigned roles."""
        save_version(self.plot, TextVersionChoices.PLOT, self.organizer())

        version = TextVersion.objects.get(tp=TextVersionChoices.PLOT, eid=self.plot.id)

        self.assertEqual(  # noqa: PT009
            version.text,
            "Plot text\nCharacters\nAri: Find the crown.\nBea: Guard the gate.\n",
        )

    def test_character_version_contains_its_plot_role(self) -> None:
        """Saving a character also snapshots the role text assigned by each plot."""
        save_version(self.ari, TextVersionChoices.CHARACTER, self.organizer())

        version = TextVersion.objects.get(tp=TextVersionChoices.CHARACTER, eid=self.ari.id)

        self.assertEqual(version.text, "\nPlots\nThe lost crown: Find the crown.\n")  # noqa: PT009
