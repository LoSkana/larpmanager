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

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from larpmanager.fixtures.demos import DEMO_BUILDERS
from larpmanager.management.commands.utils import check_virtualenv


class Command(BaseCommand):
    """Django management command."""

    help = "Create (or fetch) the template associations used by LarpManagerDemoType, from larpmanager/fixtures/demos"

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002
        """Run every registered demo builder inside a transaction, idempotently."""
        check_virtualenv()

        for builder in DEMO_BUILDERS:
            with transaction.atomic():
                demo_type = builder()
            self.stdout.write(self.style.SUCCESS(f"Demo type ready: {demo_type.slug}"))
