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

from larpmanager.models.event import EventButton


def event_button_key(event_id):
    return f"event_button_{event_id}"


def update_event_button(event_id):
    res = []
    for el in EventButton.objects.filter(event_id=event_id).order_by("number"):
        res.append((el.name, el.tooltip, el.link))
    cache.set(event_button_key(event_id), res)
    return res


def get_event_button_cache(event_id):
    res = cache.get(event_button_key(event_id))
    if res is None:
        res = update_event_button(event_id)
    return res
