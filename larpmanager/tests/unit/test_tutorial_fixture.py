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

"""Tests for the tutorial and guide fixtures loaded on deploy."""

import re
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management import call_command

from larpmanager.models.larpmanager import LarpManagerGuide, LarpManagerTutorial
from larpmanager.tests.unit.base import BaseTestCase

ROOT = Path(settings.BASE_DIR).parent
FIXTURES = ROOT / "larpmanager" / "fixtures"
TUTORIAL_STATIC = ROOT / "larpmanager" / "static" / "tutorials"


def _fields(fixture: str) -> list[dict]:
    """Return the fields of every entry of a fixture."""
    with (FIXTURES / f"{fixture}.yaml").open(encoding="utf-8") as fixture_file:
        return [entry["fields"] for entry in yaml.safe_load(fixture_file)]


class TestTutorialFixture(BaseTestCase):
    """Content of tutorial.yaml and guide.yaml."""

    def test_tutorial_slugs_unique(self) -> None:
        """Every tutorial has a unique slug, a name and a description."""
        tutorials = _fields("tutorial")
        slugs = [tutorial["slug"] for tutorial in tutorials]
        assert len(slugs) == len(set(slugs))
        for tutorial in tutorials:
            assert tutorial["name"]
            assert tutorial["descr"]

    def test_tutorial_images_exist(self) -> None:
        """Every image is a static tutorial file that exists, and every file is used."""
        referenced = set()
        for tutorial in _fields("tutorial"):
            for src in re.findall(r'<img[^>]*src="([^"]*)"', tutorial["descr"]):
                assert src.startswith("/static/tutorials/"), f"{tutorial['slug']}: {src}"
                referenced.add(src.removeprefix("/static/tutorials/"))
        present = {path.name for path in TUTORIAL_STATIC.iterdir()}
        assert referenced - present == set(), "missing images"
        assert present - referenced == set(), "unused images"

    def test_tutorial_links_to_tutorials_exist(self) -> None:
        """Links to other tutorials point to existing slugs."""
        tutorials = _fields("tutorial")
        slugs = {tutorial["slug"] for tutorial in tutorials}
        for tutorial in tutorials:
            for slug in re.findall(r'href="https://larpmanager\.com/tutorials/([^/"#]+)', tutorial["descr"]):
                assert slug in slugs, f"{tutorial['slug']} links missing tutorial {slug}"

    def test_guides_have_video(self) -> None:
        """Every published guide has a YouTube video id."""
        for guide in _fields("guide"):
            if guide.get("published"):
                assert re.search(r"^[\w-]+$", guide.get("video_id") or ""), guide["slug"]

    def test_import_loads_and_prunes(self) -> None:
        """Importing loads every tutorial and guide video, and deletes tutorials not in the fixture."""
        LarpManagerTutorial.objects.create(name="Old", slug="old-tutorial", descr="<p>Old</p>")
        call_command("import_features", verbosity=0)
        assert not LarpManagerTutorial.objects.filter(slug="old-tutorial").exists()
        assert LarpManagerTutorial.objects.count() == len(_fields("tutorial"))
        assert LarpManagerGuide.objects.get(slug="xp").video_id == "eFpxNMqGq1c"
