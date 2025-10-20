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

from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest

from larpmanager.models.access import AssocRole, EventRole
from larpmanager.models.event import DevelopStatus, Event, Run
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

    # Cache for 1 day
    cache.set(get_cache_event_key(request.user.id, request.assoc["id"]), ctx, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return ctx


def clear_run_event_links_cache(event: Event) -> None:
    """Reset event link cache for all users with roles in the event.

    This function clears the cached event links for three categories of users:
    1. All members with roles in the specific event
    2. Association executives (role number 1) for the event's association
    3. All superusers in the system

    Args:
        event: Event instance to reset links for. Must have assoc_id attribute.

    Returns:
        None

    Side Effects:
        Clears link cache entries via reset_event_links() for all relevant users.
        May perform multiple database queries to fetch role memberships.
    """
    # Clear cache for all members with roles in this specific event
    for er in EventRole.objects.filter(event=event).prefetch_related("members"):
        for mb in er.members.all():
            reset_event_links(mb.id, event.assoc_id)

    # Clear cache for association executives (role number 1)
    # These users typically have access to all events in the association
    try:
        ar = AssocRole.objects.prefetch_related("members").get(assoc_id=event.assoc_id, number=1)
        for mb in ar.members.all():
            reset_event_links(mb.id, event.assoc_id)
    except ObjectDoesNotExist:
        pass

    # Clear cache for all superusers since they have global access
    superusers = User.objects.filter(is_superuser=True)
    for user in superusers:
        reset_event_links(user.member.id, event.assoc_id)


def on_registration_post_save_reset_event_links(instance: Registration) -> None:
    """Handle registration post-save event link reset.

    This function is triggered after a Registration model instance is saved.
    It clears the cached event links for the registered member to ensure
    fresh data is displayed after registration changes.

    Args:
        instance: Registration instance that was saved

    Returns:
        None

    Side Effects:
        Clears event link cache for the registered member's user and associated event
    """
    # Early return if no member is associated with the registration
    if not instance.member:
        return

    # Reset cached event links for the member's user and event association
    reset_event_links(instance.member.user.id, instance.run.event.assoc_id)


def reset_event_links(uid: int, aid: int) -> None:
    """Clear event link cache for a specific user and association.

    This function removes cached event links from the cache system to ensure
    fresh data is loaded on the next request.

    Args:
        uid: User ID to clear cache for
        aid: Association ID to clear cache for

    Returns:
        None

    Side Effects:
        Removes cached event links from the cache system using the generated
        cache key for the specified user and association combination.
    """
    # Generate cache key for the specific user-association combination
    cache_key = get_cache_event_key(uid, aid)

    # Remove the cached event links from cache
    cache.delete(cache_key)


def get_cache_event_key(uid: int, aid: int) -> str:
    """Generate cache key for user event links.

    Creates a unique cache key string for storing user-specific event links
    based on user ID and association ID combination.

    Args:
        uid: User ID for cache key generation
        aid: Association ID for cache key generation

    Returns:
        Formatted cache key string for user event links storage

    Example:
        >>> get_cache_event_key(123, 456)
        'ctx_event_links_123_456'
    """
    # Generate cache key using user and association IDs
    return f"ctx_event_links_{uid}_{aid}"
