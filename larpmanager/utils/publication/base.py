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

import logging
from datetime import timedelta

from django.utils import timezone

from larpmanager.cache.config import get_association_config
from larpmanager.models.access import EventRole
from larpmanager.utils.larpmanager.tasks import background_auto
from larpmanager.utils.publication.ildb import (
    ILDB_RUN_CONFIG,
    _build_crew,
    _get_ildb_context,
    _sync_crew_full,
    sync_cast as sync_cast_ildb,
    sync_crew_member,
    sync_event as sync_event_ildb,
)

logger = logging.getLogger(__name__)

PUB_QUEUE = "pub"


@background_auto(queue=PUB_QUEUE)
def publish_event(event_id: int) -> None:
    """Publish an event on all linked platforms."""
    sync_event_ildb(event_id)


@background_auto(queue=PUB_QUEUE)
def publish_registration(registration_id: int, run_id: int | None) -> None:
    """Background task: sync a single cast entry on ILDB after a registration changes."""
    sync_cast_ildb(registration_id, run_id)


@background_auto(queue=PUB_QUEUE)
def publish_event_role(event_role_id: int) -> None:
    """Background task: full crew sync after EventRole metadata changes."""
    role = EventRole.objects.select_related("event__association").get(pk=event_role_id)
    ctx = _get_ildb_context(role.event)
    if not ctx or not get_association_config(ctx.association.id, "publication_crew", default_value=False):
        return
    crew = _build_crew(role.event)
    one_month_ago = timezone.now().date() - timedelta(days=30)
    for run in role.event.runs.filter(end__gte=one_month_ago, end__lte=timezone.now().date()):
        stored = run.get_config(ILDB_RUN_CONFIG, default_value="")
        if stored and stored not in ("True", "False"):
            ctx.ildb_event_id = stored
            _sync_crew_full(crew, ctx)


@background_auto(queue=PUB_QUEUE)
def publish_crew_member(event_role_id: int, member_id: int, *, delete: bool = False) -> None:
    """Background task: sync a single crew member after an EventRole m2m add/remove."""
    sync_crew_member(event_role_id, member_id, delete=delete)
