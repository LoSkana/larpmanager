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
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings as conf_settings
from django.core.management.base import BaseCommand

from larpmanager.management.commands.utils import check_virtualenv
from larpmanager.models.larpmanager import LarpManagerTutorial


class LiteralDumper(yaml.SafeDumper):
    """YAML dumper writing multi-line strings as literal blocks."""


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    """Represent multi-line strings with the literal block style."""
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


LiteralDumper.add_representer(str, _represent_str)


class Command(BaseCommand):
    """Django management command."""

    help = "Export tutorials to yaml"

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002
        """Write every tutorial to larpmanager/fixtures/tutorial.yaml, warning about images outside static."""
        check_virtualenv()

        entries = []
        for tutorial in LarpManagerTutorial.objects.order_by("order", "slug"):
            descr = (tutorial.descr or "").replace("\r\n", "\n").replace("\r", "\n")
            descr = "\n".join(line.rstrip() for line in descr.strip().split("\n"))
            for media_src in re.findall(r'src="(/media/[^"]+)"', descr):
                self.stdout.write(
                    self.style.WARNING(f"{tutorial.slug}: {media_src} must be moved to /static/tutorials/")
                )
            entries.append(
                {
                    "model": "larpmanager.larpmanagertutorial",
                    "fields": {"slug": tutorial.slug, "order": tutorial.order, "name": tutorial.name, "descr": descr},
                }
            )

        fixture_path = Path(conf_settings.BASE_DIR) / ".." / "larpmanager" / "fixtures" / "tutorial.yaml"
        with fixture_path.open("w", encoding="utf-8") as fixture_file:
            yaml.dump(entries, fixture_file, Dumper=LiteralDumper, sort_keys=False, allow_unicode=False, width=100000)
