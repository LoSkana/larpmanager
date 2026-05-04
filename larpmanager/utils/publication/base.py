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
from typing import TYPE_CHECKING

from larpmanager.cache.config import get_association_config
from larpmanager.models.access import EventRole
from larpmanager.utils.larpmanager.tasks import background_auto
from larpmanager.utils.publication.ildb import (
    _get_ildb_context,
    sync_cast as sync_cast_ildb,
    sync_crew as sync_crew_ildb,
    sync_event as sync_event_ildb,
)

if TYPE_CHECKING:
    from larpmanager.models.event import Run

logger = logging.getLogger(__name__)

PUB_QUEUE = "pub"


@background_auto(queue=PUB_QUEUE, skip_duplicates=True)
def publish_event(event_id: int) -> None:
    """Publish an event on all linked platforms."""
    sync_event_ildb(event_id)


@background_auto(queue=PUB_QUEUE, skip_duplicates=True)
def publish_registration(registration_id: int, run_id: int | None = None) -> None:
    """Background task: sync a single cast entry on ILDB after a registration changes."""
    sync_cast_ildb(registration_id, run_id)


@background_auto(queue=PUB_QUEUE, skip_duplicates=True)
def publish_event_role(event_role_id: int) -> None:
    """Background task: full crew sync after EventRole metadata changes."""
    role = EventRole.objects.select_related("event__association").get(pk=event_role_id)
    ctx = _get_ildb_context(role.event)
    if not ctx or not get_association_config(ctx.association.id, "publication_crew", default_value=False):
        return
    sync_crew_ildb(role.event, ctx)


def publish_event_all(run: Run) -> None:
    """Sync publication data for the event, all registrations, and all event roles."""
    publish_event(run.event_id)
    for reg_id in run.registrations.values_list("id", flat=True):
        publish_registration(reg_id, run.id)
    for role_id in run.event.eventrole_set.filter(deleted__isnull=True).values_list("id", flat=True):
        publish_event_role(role_id)
