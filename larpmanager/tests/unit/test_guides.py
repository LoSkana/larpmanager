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

"""Tests for the guide video migration and the grouping of the guides list."""

from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.test import RequestFactory

from larpmanager.models.larpmanager import LarpManagerGuide
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.views.larpmanager import guides

EMBEDDED = """<p>Intro</p>
<div class="guide-container"><iframe class="guide-video" src="https://www.youtube.com/embed/HVR-T_8AQ" allowfullscreen="allowfullscreen">
  </iframe></div>
<hr>
<h2>Step</h2>"""


class TestGuideVideoMigration(BaseTestCase):
    """Move of the videos embedded in the guide texts to their field."""

    def test_video_moved_to_field_and_back(self) -> None:
        """The embed leaves the text for video_id, other text stays, and the move reverses."""
        migration = import_module("larpmanager.migrations.0199_larpmanagerguide_group_video_id")
        guide = LarpManagerGuide.objects.create(title="Guide", slug="guide", text=EMBEDDED)
        plain = LarpManagerGuide.objects.create(title="Plain", slug="plain", text="<p>No video</p>")

        migration.move_video_to_field(apps, None)
        guide.refresh_from_db()
        plain.refresh_from_db()
        assert guide.video_id == "HVR-T_8AQ"
        assert guide.text == "<p>Intro</p>\n<hr>\n<h2>Step</h2>"
        assert plain.video_id is None
        assert plain.text == "<p>No video</p>"

        migration.move_video_to_text(apps, None)
        guide.refresh_from_db()
        assert "youtube.com/embed/HVR-T_8AQ" in guide.text


class TestGuidesList(BaseTestCase):
    """Grouping of the published guides."""

    def test_groups_keep_first_appearance_order(self) -> None:
        """Guides are grouped by name, in number order, without unpublished ones."""
        for number, slug, group, published in (
            (1, "first", "Writing", True),
            (2, "second", "Payments", True),
            (3, "third", "Writing", True),
            (4, "draft", "Drafts", False),
            (5, "loose", None, True),
        ):
            LarpManagerGuide.objects.create(number=number, title=slug, slug=slug, group=group, published=published)

        with (
            patch("larpmanager.views.larpmanager.get_lm_contact", return_value={}),
            patch("larpmanager.views.larpmanager.get_larpmanager_texts", return_value={}),
            patch("larpmanager.views.larpmanager.render") as render,
        ):
            guides(RequestFactory().get("/guides/"))

        groups = render.call_args.args[2]["groups"]
        assert list(groups) == ["Writing", "Payments", ""]
        assert [guide.slug for guide in groups["Writing"]] == ["first", "third"]
