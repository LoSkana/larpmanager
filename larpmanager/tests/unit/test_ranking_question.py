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
"""Tests for the ranking question helpers and widget."""

from larpmanager.forms.widgets import RankingWidget
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.registrations.questions import get_ranking_names, sanitize_ranking

UUIDS = ["u1", "u2", "u3"]
NAMES = {"u1": "Alpha", "u2": "Beta", "u3": "Gamma"}


class TestRankingQuestion(BaseTestCase):
    """Test cases for ranking sanitization, name resolution and rendering"""

    def test_sanitize_keeps_submitted_order(self) -> None:
        """A complete valid ranking is kept as submitted"""
        assert sanitize_ranking("u3,u1,u2", UUIDS) == "u3,u1,u2"

    def test_sanitize_drops_unknown_and_duplicates(self) -> None:
        """Tampered values are dropped, missing items appended in their default order"""
        assert sanitize_ranking("u2,evil,u2", UUIDS) == "u2,u1,u3"

    def test_sanitize_empty_value(self) -> None:
        """An empty submission falls back to the default order"""
        assert sanitize_ranking(None, UUIDS) == "u1,u2,u3"

    def test_sanitize_max_rank(self) -> None:
        """Only the first max_rank items are kept"""
        assert sanitize_ranking("u3,u1,u2", UUIDS, max_rank=2) == "u3,u1"

    def test_ranking_names(self) -> None:
        """Uuids are resolved in order, unknown ones skipped"""
        assert get_ranking_names("u2,gone,u1", NAMES) == ["Beta", "Alpha"]
        assert get_ranking_names("", NAMES) == []

    def test_widget_renders_items_in_order(self) -> None:
        """The widget renders the items in the given order with the max rank"""
        widget = RankingWidget(items=[("u2", "Beta"), ("u1", "Alpha")], max_rank=1)
        html = widget.render("que", "u2", attrs={"id": "id_que"})
        assert html.index("Beta") < html.index("Alpha")
        assert 'data-max-rank="1"' in html

    def test_widget_read_only(self) -> None:
        """When disabled the widget shows only the ranked items as a plain list"""
        widget = RankingWidget(items=[("u2", "Beta"), ("u1", "Alpha")], max_rank=1)
        html = widget.render("que", "u2", attrs={"id": "id_que", "disabled": True})
        assert "ranking-readonly" in html
        assert "Beta" in html
        assert "Alpha" not in html
