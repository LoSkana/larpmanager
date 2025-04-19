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
from django.db.models.signals import pre_save
from django.dispatch import receiver

from larpmanager.models.event import Run, Event


def reset_cache_run(s, n):
    key = cache_run_key(s, n)
    cache.delete(key)


def cache_run_key(s, n):
    return f"run_{s}_{n}"


def get_cache_run(s, n):
    key = cache_run_key(s, n)
    res = cache.get(key)
    if not res:
        res = init_cache_run(s, n)
        cache.set(key, res)
    return res


def init_cache_run(s, n):
    try:
        run = Run.objects.select_related("event").get(event__slug=s, number=n)
        # res = {'run': run.as_dict(), 'event': run.event.as_dict() }
        return run.id
    except Exception:
        return None


@receiver(pre_save, sender=Run)
def pre_save_Run(sender, instance, **kwargs):
    if instance.pk:
        reset_cache_run(instance.event.slug, instance.number)


@receiver(pre_save, sender=Event)
def pre_save_Event(sender, instance, **kwargs):
    if instance.pk:
        for run in instance.runs.all():
            reset_cache_run(instance.slug, run.number)
