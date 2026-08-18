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

from types import SimpleNamespace

from larpmanager.forms.base import FormMixin
from larpmanager.forms.widgets import DescriptionCheckboxSelectMultiple, DescriptionRadioSelect
from larpmanager.tests.unit.base import BaseTestCase

CHOICES = [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]


class TestCollapseUnselectedOptions(BaseTestCase):
    """Test cases for the collapse_unselected flag of the description widgets"""

    @staticmethod
    def _render_radio(value: str, *, collapse: bool | None = True) -> str:
        widget = DescriptionRadioSelect(choices=CHOICES, collapse_unselected=collapse)
        return widget.render("que", value, attrs={"id": "id_que"})

    @staticmethod
    def _render_checkbox(value: list[str], *, collapse: bool | None = True) -> str:
        widget = DescriptionCheckboxSelectMultiple(choices=CHOICES, collapse_unselected=collapse)
        return widget.render("que", value, attrs={"id": "id_que"})

    def test_radio_hides_unselected(self) -> None:
        """On edit only the selected radio stays visible, the others are collapsed"""
        html = self._render_radio("b")
        assert html.count("opt-collapsed hide") == len(CHOICES) - 1
        # the wrapper of the selected option carries no collapse class
        selected_block = html.split('value="b"')[0].rsplit("<div", 1)[1]
        assert "opt-collapsed" not in selected_block
        assert "opt-show-more" in html

    def test_checkbox_hides_unselected(self) -> None:
        """Multiple choice collapses every option that is not among the selected ones"""
        html = self._render_checkbox(["a", "c"])
        assert html.count("opt-collapsed hide") == 1
        assert "opt-show-more" in html

    def test_no_collapse_when_flag_off(self) -> None:
        """Widgets not opting in render every option visible, with no toggle at all"""
        html = self._render_radio("b", collapse=None)
        assert "opt-collapsed" not in html
        assert "opt-show-more" not in html

    def test_new_element_expanded_with_toggle(self) -> None:
        """Creation forms start expanded, but still offer the link to collapse the options"""
        html = self._render_radio("", collapse=False)
        assert html.count('class="opt-wrap"') == len(CHOICES)
        assert "opt-collapsed" not in html
        assert "opt-show-more" in html
        # the link starts on the hide label, as the options are visible
        assert '<span class="sl-show hide">' in html
        assert '<span class="sl-hide">' in html

    def test_collapse_without_selection(self) -> None:
        """Editing collapses the options even when none of them is selected"""
        html = self._render_radio("")
        assert html.count("opt-collapsed hide") == len(CHOICES)
        assert '<span class="sl-show">' in html

    def test_no_collapse_when_all_selected(self) -> None:
        """Nothing is collapsed when every option is already selected, the toggle stays available"""
        html = self._render_checkbox(["a", "b", "c"])
        assert "opt-collapsed" not in html
        assert '<span class="sl-hide">' in html

    def test_no_toggle_with_single_option(self) -> None:
        """With a single option there is nothing to toggle, the option stays visible"""
        widget = DescriptionRadioSelect(choices=[("a", "Alpha")], collapse_unselected=True)
        html = widget.render("que", "", attrs={"id": "id_que"})
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

    def test_no_toggle_below_collapse_min(self) -> None:
        """With fewer options than the configured minimum the toggle is not shown"""
        widget = DescriptionRadioSelect(choices=CHOICES, collapse_unselected=True, collapse_min=5)
        html = widget.render("que", "a", attrs={"id": "id_que"})
        assert "opt-collapsed" not in html
        assert "opt-show-more" not in html

    def test_toggle_at_collapse_min(self) -> None:
        """Reaching the configured minimum of options enables the toggle"""
        widget = DescriptionRadioSelect(choices=CHOICES, collapse_unselected=True, collapse_min=3)
        html = widget.render("que", "a", attrs={"id": "id_que"})
        assert html.count("opt-collapsed hide") == len(CHOICES) - 1
        assert "opt-show-more" in html

    def test_gated_options_left_out_of_the_count(self) -> None:
        """Options hidden by their unmet requirements do not count toward the minimum"""
        widget = DescriptionRadioSelect(choices=CHOICES, collapse_unselected=True, collapse_min=3, gated_options={"c"})
        html = widget.render("que", "a", attrs={"id": "id_que"})
        # only two options are on the page: below the minimum, nothing is collapsed
        assert "opt-collapsed" not in html
        assert "opt-show-more" not in html

    def test_gated_options_do_not_block_the_toggle(self) -> None:
        """The remaining options are still collapsed when they are enough on their own"""
        widget = DescriptionRadioSelect(choices=CHOICES, collapse_unselected=True, collapse_min=2, gated_options={"c"})
        html = widget.render("que", "a", attrs={"id": "id_que"})
        # the selected "a" stays visible, the others are collapsed: the gated "c" is only
        # left out of the count, the client keeps it hidden with its own class
        assert html.count("opt-collapsed hide") == len(CHOICES) - 1
        assert "opt-show-more" in html


class _CollapseForm(FormMixin):
    """Minimal form stub exposing the collapse state logic of FormMixin."""

    def __init__(self, params: dict) -> None:
        self.params = params
        self.instance = SimpleNamespace(pk=1)


class TestCollapseFormState(BaseTestCase):
    """Test cases for the collapse state resolved by the forms"""

    def test_edit_collapses(self) -> None:
        """A regular edit form starts with the unselected options collapsed"""
        assert _CollapseForm({})._collapse_unselected is True

    def test_frame_disables_collapse(self) -> None:
        """A dashboard element form rendered inside an iframe popup never collapses the options"""
        assert _CollapseForm({"frame": True})._collapse_unselected is None

    def test_writing_frame_keeps_collapse(self) -> None:
        """A writing element edited inside an iframe still collapses the unselected options"""
        assert _CollapseForm({"frame": True, "is_writing": True})._collapse_unselected is True

    def test_excel_edit_disables_collapse(self) -> None:
        """A double click single field edit never collapses the options"""
        assert _CollapseForm({"excel_edit": True})._collapse_unselected is None

    def test_modal_disables_collapse(self) -> None:
        """A quick edit modal never collapses the options"""
        assert _CollapseForm({"is_modal": True})._collapse_unselected is None
