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

"""Tests for the choice widgets that collapse the options not selected."""

from larpmanager.forms.widgets import DescriptionCheckboxSelectMultiple, DescriptionRadioSelect
from larpmanager.tests.unit.base import BaseTestCase

CHOICES = [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]


class TestCollapseUnselectedOptions(BaseTestCase):
    """Test cases for the collapse_unselected flag of the description widgets"""

    @staticmethod
    def _render_radio(value: str, *, collapse: bool) -> str:
        widget = DescriptionRadioSelect(choices=CHOICES, collapse_unselected=collapse)
        return widget.render("que", value, attrs={"id": "id_que"})

    @staticmethod
    def _render_checkbox(value: list[str], *, collapse: bool) -> str:
        widget = DescriptionCheckboxSelectMultiple(choices=CHOICES, collapse_unselected=collapse)
        return widget.render("que", value, attrs={"id": "id_que"})

    def test_radio_hides_unselected(self) -> None:
        """On edit only the selected radio stays visible, the others are collapsed"""
        html = self._render_radio("b", collapse=True)
        assert html.count("opt-collapsed hide") == len(CHOICES) - 1
        # the wrapper of the selected option carries no collapse class
        selected_block = html.split('value="b"')[0].rsplit("<div", 1)[1]
        assert "opt-collapsed" not in selected_block
        assert "opt-show-more" in html

    def test_checkbox_hides_unselected(self) -> None:
        """Multiple choice collapses every option that is not among the selected ones"""
        html = self._render_checkbox(["a", "c"], collapse=True)
        assert html.count("opt-collapsed hide") == 1
        assert "opt-show-more" in html

    def test_no_collapse_when_flag_off(self) -> None:
        """Creation forms pass the flag off, so every option is rendered visible"""
        html = self._render_radio("b", collapse=False)
        assert "opt-collapsed" not in html
        assert "opt-show-more" not in html

    def test_no_collapse_without_selection(self) -> None:
        """Nothing is collapsed when no option is selected, or the field would look empty"""
        html = self._render_radio("", collapse=True)
        assert "opt-collapsed" not in html
        assert "opt-show-more" not in html

    def test_no_collapse_when_all_selected(self) -> None:
        """Nothing is collapsed when every option is already selected"""
        html = self._render_checkbox(["a", "b", "c"], collapse=True)
        assert "opt-collapsed" not in html
        assert "opt-show-more" not in html

    def test_container_keeps_widget_attributes(self) -> None:
        """Attributes set on the widget are rendered on the container, as Django does"""
        widget = DescriptionRadioSelect(
            attrs={"class": "my-radio-class", "data-test": "x"}, choices=CHOICES, collapse_unselected=True
        )
        html = widget.render("que", "a", attrs={"id": "id_que"})
        container = html[: html.index(">") + 1]
        assert 'id="id_que"' in container
        assert "my-radio-class" in container
        assert 'data-test="x"' in container
