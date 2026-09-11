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

from typing import TYPE_CHECKING

from larpmanager.cache.config import get_event_config

if TYPE_CHECKING:
    from django.http import HttpRequest

    from larpmanager.models.base import BaseModel

# Tolerance in seconds when comparing the version stamp of the loaded form with the saved one,
# to absorb the rounding of the stamp sent to the browser and back
STALE_TOLERANCE = 0.001


def set_auto_save(context: dict, config_name: str = "writing_disable_auto") -> None:
    """Activate the background auto-save of a player-facing writing form, unless disabled for the event."""
    context["auto_save"] = not get_event_config(
        context["event"].id,
        config_name,
        context=context,
    )


def init_auto_save(context: dict, instance: BaseModel | None) -> None:
    """Seed the auto-save context with the version stamp of the loaded element.

    Used by the browser to detect, on the next auto-save, whether the element was
    saved elsewhere in the meantime. No-op when auto-save is not active for the form.
    """
    if not context.get("auto_save"):
        return

    context["base_updated"] = ""
    if instance is not None and instance.pk:
        context["base_updated"] = f"{instance.updated.timestamp():.6f}"


def is_stale(context: dict, request: HttpRequest, instance: BaseModel | None) -> bool:
    """Check if the element was saved elsewhere after the form currently posted was loaded."""
    if not context.get("auto_save") or instance is None or not instance.pk:
        return False

    posted = request.POST.get("base_updated")
    if not posted:
        return False

    try:
        base_updated = float(posted)
    except ValueError:
        return False

    # The instance is loaded fresh in this request, so its stamp is the current one
    return instance.updated.timestamp() - base_updated > STALE_TOLERANCE
