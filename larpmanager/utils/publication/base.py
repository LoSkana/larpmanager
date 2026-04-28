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
from larpmanager.models.registration import Registration
from larpmanager.utils.larpmanager.tasks import background_auto
from larpmanager.utils.publication.ildb import (
    ILDB_RUN_CONFIG,
    _build_cast,
    _build_crew,
    _get_ildb_context,
    _upload_cast,
    _upload_crew,
    publish_event as ildb_publish_event,
)

logger = logging.getLogger(__name__)

PUB_QUEUE = "pub"


@background_auto(queue=PUB_QUEUE)
def publish_registration(registration_id: int) -> None:
    """Background task: sync cast/crew on ILDB after a registration or character assignment changes."""
    reg = Registration.objects.select_related("run__event__association").get(pk=registration_id)
    run = reg.run
    ctx = _get_ildb_context(run.event, run)
    if not ctx or not ctx.ildb_event_id:
        return
    if get_association_config(ctx.association.id, "ildb_crew", default_value=False):
        _upload_crew(_build_crew(run.event), ctx)
    if get_association_config(ctx.association.id, "ildb_cast", default_value=False):
        _upload_cast(_build_cast(run), ctx)


@background_auto(queue=PUB_QUEUE)
def publish_event_role(event_role_id: int) -> None:
    """Background task: sync crew on ILDB after an EventRole changes."""
    role = EventRole.objects.select_related("event__association").get(pk=event_role_id)
    ctx = _get_ildb_context(role.event)
    if not ctx or not get_association_config(ctx.association.id, "ildb_crew", default_value=False):
        return
    crew = _build_crew(role.event)
    one_month_ago = timezone.now().date() - timedelta(days=30)
    for run in role.event.runs.filter(end__gte=one_month_ago, end__lte=timezone.now().date()):
        stored = run.get_config(ILDB_RUN_CONFIG, default_value="")
        if stored and stored not in ("True", "False"):
            ctx.ildb_event_id = stored
            _upload_crew(crew, ctx)


# Maps internal stored values to ILDB Italian API values


@background_auto(queue=PUB_QUEUE)
def publish_event(event_id: int) -> None:
    """Publish an event on all linked platforms."""
    ildb_publish_event(event_id)
