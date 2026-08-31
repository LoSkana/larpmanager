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

from typing import TYPE_CHECKING, Any

from django.dispatch import Signal

from larpmanager.cache.config import get_event_config
from larpmanager.cache.registration_counts import clear_registration_counts_cache
from larpmanager.cache.run import get_event_run_ids
from larpmanager.models.registration import Registration, RegistrationCharacterRel
from larpmanager.utils.core.common import _search_char_reg

if TYPE_CHECKING:
    from larpmanager.models.writing import Character

# Fired instead of calling into utils.registrations.signals directly, so this cache
# module does not depend on business-logic modules at load time. Connected in
# models/signals.py, which is already the central place wiring cross-module signals.
character_registration_updated = Signal()


def on_character_update_registration_cache(instance: Character) -> None:
    """Clear registration caches and update related registrations when character changes."""
    # Clear registration count caches for all event runs
    for run_id in get_event_run_ids(instance.event_id):
        clear_registration_counts_cache(run_id)

    # Refresh nav/publication caches if character approval is enabled, since the
    # character's approval status is shown on the registration's public/nav data
    if get_event_config(instance.event_id, "user_character_approval"):
        for relation in RegistrationCharacterRel.objects.filter(character=instance).select_related(
            "registration__run", "registration__run__event", "registration__ticket", "registration__member"
        ):
            character_registration_updated.send(sender=Registration, registration=relation.registration)


def search_player(character: Character, json_output: dict[str, Any], context: dict) -> None:
    """Search for players in registration cache and populate results.

    This function attempts to find player registration data for a given character,
    either from a pre-loaded assignments cache or by querying the database directly.
    It populates the character object with registration and member information.

    Args:
        character: Character instance with player data to be populated
        json_output (dict): JSON object to populate with search results
        context (dict): Context dictionary containing search parameters, assignments cache,
                   and run information

    Returns:
        None: Function modifies character and json_output objects in place

    """
    # Check if assignments are pre-loaded in context (cache hit)
    if "assignments" in context:
        if character.number in context["assignments"]:
            # Populate character with cached registration data
            character.rcr = context["assignments"][character.number]
            character.registration = character.rcr.registration
            character.member = character.registration.member
        else:
            # Character not found in assignments cache
            character.rcr = None
            character.registration = None
            character.member = None
    else:
        # No cache available, query database directly
        query = RegistrationCharacterRel.objects.select_related("registration", "registration__member").filter(
            registration__run_id=context["run"].id,
            character=character,
        )
        if query:
            # Fetch registration character relationship with related objects
            character.rcr = query.first()
            character.registration = character.rcr.registration
            character.member = character.registration.member
        else:
            # Registration not found or database error
            character.rcr = None
            character.registration = None
            character.member = None

    # Process character registration data if available
    if character.registration:
        _search_char_reg(context, character, json_output)
    else:
        # No registration found, set default player ID and UUID
        json_output["player_uuid"] = None
