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

from django.core.cache import cache

from larpmanager.models.event import Event
from larpmanager.models.form import QuestionType, WritingQuestion


def event_fields_key(event_id):
    return f"event_fields_{event_id}"


def reset_event_fields_cache(event_id):
    cache.delete(event_fields_key(event_id))


def update_event_fields(event_id):
    res = {}
    event = Event.objects.get(pk=event_id)
    que = event.get_elements(WritingQuestion).filter(typ__in=QuestionType.get_def_types())
    for el in que.values(("typ", "display", "applicable")):
        if el["applicable"] not in res:
            res[el["applicable"]] = {}
        el["applicable"][el["typ"]] = el["display"]
    cache.set(event_fields_key(event_id), res)
    return res


def get_event_fields_cache(event_id):
    res = cache.get(event_fields_key(event_id))
    if res is None:
        res = update_event_fields(event_id)
    return res
