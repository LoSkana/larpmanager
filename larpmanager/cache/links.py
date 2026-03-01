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
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.utils import timezone

from larpmanager.models.access import AssociationRole, EventRole
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.models.registration import Registration
from larpmanager.utils.auth.admin import is_lm_admin

if TYPE_CHECKING:
    from django.http import HttpRequest

    from larpmanager.models.member import Member


logger = logging.getLogger(__name__)


def cache_event_links(request: HttpRequest, context: dict) -> None:
    """Get cached event navigation links for authenticated user.

    Builds and caches navigation context including registrations, roles,
    and accessible runs for the user within the current association.

    Args:
        request: Django HTTP request with authenticated user and association
        context: Dict for context information

    Returns:
        Dict with keys: reg_menu, association_role, event_role, all_runs, open_runs, topbar

    """
    # Skip if not authenticated or no association
    if not context["member"] or context["association_id"] == 0:
        return

    # Return cached data if available
    cache_links_key = get_cache_event_key(context["member"].id, context["association_id"])
    navigation_context = cache.get(cache_links_key)
    if not navigation_context:
        # Build navigation context from scratch
        navigation_context = _build_navigation_context(request, context)

        # Cache for 1 day
        cache.set(
            cache_links_key,
            navigation_context,
            timeout=conf_settings.CACHE_TIMEOUT_1_DAY,
        )

    context.update(navigation_context)
    return


def _build_navigation_context(request: HttpRequest, context: dict) -> dict:
    """Build navigation context for authenticated user."""
    cutoff_date = (timezone.now() - timedelta(days=10)).date()
    member = context["member"]
    association_id = context["association_id"]
    navigation_context = {}

    # Get user's active registrations for upcoming events
    active_registrations = Registration.objects.filter(
        member=member,
        run__end__gte=cutoff_date,
        cancellation_date__isnull=True,
        run__event__association_id=association_id,
    ).select_related("run", "run__event")
    navigation_context["reg_menu"] = [
        (registration.run.get_slug(), str(registration.run)) for registration in active_registrations
    ]

    # Collect roles
    navigation_context["association_role"] = _get_association_roles(member, association_id, request)
    navigation_context["event_role"] = _get_event_roles(member, association_id)

    # Build accessible runs
    navigation_context.update(
        _get_accessible_runs(association_id, navigation_context["association_role"], navigation_context["event_role"]),
    )

    # Determine if topbar should be shown
    navigation_context["topbar_admin"] = bool(
        navigation_context["event_role"] or navigation_context["association_role"]
    )

    # Store personal theme preference (overrides event/association theme)
    navigation_context["member_theme"] = member.get_config("member_theme", default_value="")

    return navigation_context


def _get_association_roles(member: Member, association_id: int, request: HttpRequest) -> dict[int, int]:
    """Get association-level roles for the member."""
    association_roles: dict[int, int] = {}
    for association_role in member.association_roles.filter(association_id=association_id):
        association_roles[association_role.number] = association_role.id

    # Grant admin role to LarpManager admins
    if is_lm_admin(request):
        association_roles[1] = 1

    return association_roles


def _get_event_roles(member: Member, association_id: int) -> dict[str, dict[int, int]]:
    """Get event-level roles for the member."""
    event_roles = {}
    for event_role in member.event_roles.filter(event__association_id=association_id).select_related("event"):
        event_slug = event_role.event.slug
        event_roles.setdefault(event_slug, {})[event_role.number] = event_role.id
    return event_roles


def _get_accessible_runs(association_id: int, association_roles: dict, event_roles: dict) -> dict:
    """Get runs accessible to the user based on their roles."""
    result = {"all_runs": {}, "open_runs": {}, "past_runs": {}}
    all_runs = Run.objects.filter(event__association_id=association_id).select_related("event").order_by("end")
    is_admin = 1 in association_roles

    for run in all_runs:
        if run.event.deleted:
            continue

        roles = _determine_run_roles(run, event_roles, is_admin=is_admin)
        if not roles:
            continue

        result["all_runs"][run.id] = roles

        # Create run element for display
        run_element = {
            "slug": run.get_slug(),
            "e": run.event.slug,
            "r": run.number,
            "s": str(run),
            "k": (run.start if run.start else datetime.max.replace(tzinfo=UTC).date()),
        }

        # Categorize as open or past run
        target_dict = "open_runs" if run.development not in (DevelopStatus.DONE, DevelopStatus.CANC) else "past_runs"
        result[target_dict][run.id] = run_element

    return result


def _determine_run_roles(run: Run, event_roles_by_slug: dict[str, dict], *, is_admin: bool) -> list[int] | None:
    """Determine user roles for a specific run."""
    if is_admin:
        return [1]
    return list(event_roles_by_slug.get(run.event.slug, {}).keys()) or None


def clear_run_event_links_cache(event: Event) -> None:
    """Reset event link cache for all users with roles in the event.

    This function clears the cached event links for three categories of users:
    1. All members with roles in the specific event
    2. Association executives (role number 1) for the event's association
    3. All superusers in the system

    Args:
        event: Event instance to reset links for. Must have association_id attribute.

    Returns:
        None

    Side Effects:
        Clears link cache entries via reset_event_links() for all relevant users.
        May perform multiple database queries to fetch role memberships.

    """
    # Clear cache for all members with roles in this specific event
    for event_role in EventRole.objects.filter(event=event).prefetch_related("members"):
        for member in event_role.members.all():
            reset_event_links(member.id, event.association_id)

    # Clear cache for association executives (role number 1)
    # These users typically have access to all events in the association
    try:
        association_role = AssociationRole.objects.prefetch_related("members").get(
            association_id=event.association_id,
            number=1,
        )
        for member in association_role.members.all():
            reset_event_links(member.id, event.association_id)
    except ObjectDoesNotExist:
        logger.debug("Association role #1 not found for association %s", event.association_id)

    # Clear cache for all superusers since they have global access
    superusers = User.objects.filter(is_superuser=True)
    for superuser in superusers:
        reset_event_links(superuser.member.id, event.association_id)


def on_registration_post_save_reset_event_links(instance: Registration) -> None:
    """Handle registration post-save event link reset."""
    # Early return if no member is associated with the registration
    if not instance.member:
        return

    # Reset cached event links for the member and event association
    reset_event_links(instance.member_id, instance.run.event.association_id)


def reset_event_links(member_id: int, association_id: int) -> None:
    """Clear event link cache for a specific member and association."""
    # Generate cache key for the specific member-association combination
    cache_key = get_cache_event_key(member_id, association_id)

    # Remove the cached event links from cache
    cache.delete(cache_key)


def get_cache_event_key(member_id: int, association_id: int) -> str:
    """Generate cache key for member event links."""
    # Generate cache key using member and association IDs
    return f"ctx_event_links_{member_id}_{association_id}"
