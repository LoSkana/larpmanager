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

from larpmanager.models.writing import CharacterConfig

# Kept in its own leaf module (only depends on models.writing) so that both
# forms.utils and utils.services.character can import it without a circular import.


def filter_playing_characters(queryset: Any, run: Any) -> Any:
    """Restrict characters to active ones assigned to a non cancelled registration of the run.

    Args:
        queryset: Character queryset to filter
        run: Run the characters must be playing in

    Returns:
        Filtered character queryset

    """
    inactive_ids = CharacterConfig.objects.filter(
        character_id__in=queryset.values_list("id", flat=True),
        name="inactive",
        value="True",
    ).values_list("character_id", flat=True)

    return (
        queryset.exclude(id__in=inactive_ids)
        .filter(rcrs__registration__run=run, rcrs__registration__cancellation_date__isnull=True)
        .distinct()
    )
