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

import logging
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest

from larpmanager.models.access import AssocRole, EventRole
from larpmanager.models.event import DevelopStatus, Run
from larpmanager.models.registration import Registration
from larpmanager.utils.auth import is_lm_admin

logger = logging.getLogger(__name__)


def cache_event_links(request: HttpRequest) -> dict:
    """Get cached event navigation links for authenticated user.

    Builds and caches navigation context including registrations, roles,
    and accessible runs for the user within the current association.

    Args:
        request: Django HTTP request with authenticated user and association

    Returns:
        Dict with keys: reg_menu, assoc_role, event_role, all_runs, open_runs, topbar
    """
    ctx = {}
    # Skip if not authenticated or no association
    if not request.user.is_authenticated or request.assoc["id"] == 0:
        return ctx

    # Return cached data if available
    ctx = cache.get(get_cache_event_key(request.user.id, request.assoc["id"]))
    if ctx:
        return ctx

    # Build navigation context from scratch
    ctx = {}
    ref = datetime.now() - timedelta(days=10)
    ref = ref.date()

    member = request.user.member

    # Get user's active registrations for upcoming events
    que = Registration.objects.filter(member=member, run__end__gte=ref)
    que = que.filter(cancellation_date__isnull=True, run__event__assoc_id=request.assoc["id"])
    que = que.select_related("run", "run__event")
    ctx["reg_menu"] = [(r.run.get_slug(), str(r.run)) for r in que]

    assoc_id = request.assoc["id"]

    # Collect association-level roles
    ctx["assoc_role"] = {}
    for ar in member.assoc_roles.filter(assoc_id=assoc_id):
        ctx["assoc_role"][ar.number] = ar.id
    # Grant admin role to LarpManager admins
    if is_lm_admin(request):
        ctx["assoc_role"][1] = 1

    # Collect event-level roles
    ctx["event_role"] = {}
    for er in member.event_roles.filter(event__assoc_id=assoc_id).select_related("event"):
        if er.event.slug not in ctx["event_role"]:
            ctx["event_role"][er.event.slug] = {}
        ctx["event_role"][er.event.slug][er.number] = er.id

    # Build accessible runs list based on user's roles
    ctx["all_runs"] = {}
    ctx["open_runs"] = {}
    all_runs = Run.objects.filter(event__assoc_id=assoc_id).select_related("event").order_by("end")
    admin = 1 in ctx["assoc_role"]
    for r in all_runs:
        # Skip deleted events
        if r.event.deleted:
            continue
        # Determine user's roles for this run
        roles = None
        if admin:
            roles = [1]
        if r.event.slug in ctx["event_role"]:
            roles = list(ctx["event_role"][r.event.slug].keys())
        if not roles:
            continue
        ctx["all_runs"][r.id] = roles
        # Add to open runs if not completed or cancelled
        if r.development not in (DevelopStatus.DONE, DevelopStatus.CANC):
            ctx["open_runs"][r.id] = {
                "slug": r.get_slug(),
                "e": r.event.slug,
                "r": r.number,
                "s": str(r),
                "k": (r.start if r.start else datetime.max.date()),
            }

    # Determine if topbar should be shown
    ctx["topbar"] = ctx["event_role"] or ctx["assoc_role"]

    # Cache for 60 seconds
    cache.set(get_cache_event_key(request.user.id, request.assoc["id"]), ctx, 60)
    return ctx


def clear_run_event_links_cache(event):
    """Reset event link cache for all users with roles in the event.

    Args:
        event: Event instance to reset links for

    Side effects:
        Clears link cache for event role members, association executives, and superusers
    """
    for er in EventRole.objects.filter(event=event).prefetch_related("members"):
        for mb in er.members.all():
            reset_event_links(mb.id, event.assoc_id)
    try:
        ar = AssocRole.objects.prefetch_related("members").get(assoc=event.assoc, number=1)
        for mb in ar.members.all():
            reset_event_links(mb.id, event.assoc_id)
    except ObjectDoesNotExist:
        pass

    superusers = User.objects.filter(is_superuser=True)
    for user in superusers:
        reset_event_links(user.member.id, event.assoc_id)


def on_registration_post_save_reset_event_links(instance):
    """Handle registration post-save event link reset.

    Args:
        instance: Registration instance that was saved

    Side effects:
        Clears event link cache for the registered member
    """
    if not instance.member:
        return

    reset_event_links(instance.member.user.id, instance.run.event.assoc_id)


def reset_event_links(uid, aid):
    """Clear event link cache for a specific user and association.

    Args:
        uid (int): User ID
        aid (int): Association ID

    Side effects:
        Removes cached event links from cache
    """
    cache.delete(get_cache_event_key(uid, aid))


def get_cache_event_key(uid, aid):
    """Generate cache key for user event links.

    Args:
        uid (int): User ID
        aid (int): Association ID

    Returns:
        str: Cache key for user event links
    """
    return f"ctx_event_links_{uid}_{aid}"
