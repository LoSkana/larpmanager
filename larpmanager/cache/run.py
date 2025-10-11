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
import ast

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.cache.button import get_event_button_cache
from larpmanager.cache.feature import get_event_features
from larpmanager.models.event import Run
from larpmanager.models.form import _get_writing_mapping


def reset_cache_run(a, s):
    key = cache_run_key(a, s)
    cache.delete(key)


def cache_run_key(a, s):
    return f"run_{a}_{s}"


def get_cache_run(a, s):
    key = cache_run_key(a, s)
    res = cache.get(key)
    if not res:
        res = init_cache_run(a, s)
        cache.set(key, res)
    return res


def init_cache_run(a, s):
    try:
        try:
            s, n = s.split("-")
            n = int(n)
        except ValueError:
            n = 1

        run = Run.objects.select_related("event").get(event__assoc_id=a, event__slug=s, number=n)
        return run.id
    except ObjectDoesNotExist:
        return None


def on_run_pre_save_invalidate_cache(instance):
    """Handle run pre-save cache invalidation.

    Args:
        instance: Run instance being saved
    """
    if instance.pk:
        reset_cache_run(instance.event.assoc_id, instance.get_slug())


def on_event_pre_save_invalidate_cache(instance):
    """Handle event pre-save cache invalidation.

    Args:
        instance: Event instance being saved
    """
    if instance.pk:
        for run in instance.runs.all():
            reset_cache_run(instance.assoc_id, run.get_slug())


def reset_cache_config_run(run):
    key = cache_config_run_key(run)
    cache.delete(key)


def cache_config_run_key(run):
    return f"run_config_{run.id}"


def get_cache_config_run(run):
    key = cache_config_run_key(run)
    res = cache.get(key)
    if not res:
        res = init_cache_config_run(run)
        cache.set(key, res)
    return res


def init_cache_config_run(run):
    """
    Initialize and build cache configuration data for a run.

    Args:
        run: Run instance to initialize cache for

    Returns:
        dict: Cache configuration context with buttons, limitations, and display settings
    """
    ev_features = get_event_features(run.event_id)
    ctx = {
        "buttons": get_event_button_cache(run.event_id),
        "limitations": run.event.get_config("show_limitations", False),
        "user_character_max": run.event.get_config("user_character_max", 0),
        "cover_orig": run.event.get_config("cover_orig", False),
        "px_user": run.event.get_config("px_user", False),
    }

    if run.event.parent:
        ctx["px_user"] = run.event.parent.get_config("px_user", False)

    mapping = _get_writing_mapping()
    for config_name in ["character", "faction", "quest", "trait"]:
        if mapping[config_name] not in ev_features:
            continue
        res = {}
        val = run.get_config("show_" + config_name, "[]")
        for el in ast.literal_eval(val):
            res[el] = 1
        ctx["show_" + config_name] = res

    res = {}
    val = run.get_config("show_addit", "[]")
    for el in ast.literal_eval(val):
        res[el] = 1
    ctx["show_addit"] = res

    return ctx


def on_run_post_save_reset_config_cache(instance):
    """Handle run post-save cache reset.

    Args:
        instance: Run instance that was saved
    """
    if instance.pk:
        reset_cache_config_run(instance)


def on_event_post_save_reset_config_cache(instance):
    """Handle event post-save cache reset.

    Args:
        instance: Event instance that was saved
    """
    if instance.pk:
        for run in instance.runs.all():
            reset_cache_config_run(run)
