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

from typing import Any

from django.core.management.base import BaseCommand

from larpmanager.models.association import Association
from larpmanager.utils.services.association import _reset_all_association


class Command(BaseCommand):
    """Django management command."""

    help = "Reset all caches"

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002
        """Print email mappings for associations and admin."""
        for association in Association.objects.all():
            _reset_all_association(association.id, association.slug)
