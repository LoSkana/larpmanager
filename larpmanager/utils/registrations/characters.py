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

from django.core.exceptions import ObjectDoesNotExist

from larpmanager.cache.config import get_event_config
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    CharacterStatus,
    get_event_class_parent,
    get_event_elements,
)
from larpmanager.utils.core.exceptions import PendingApprovalError, SignupError, WaitingError

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from larpmanager.models.event import Run
    from larpmanager.models.member import Member


def registration_find(run: Run, member: Member) -> Registration | None:
    """Find registration for a user to a run.

    Searches for an active registration (non-cancelled, non-redeemed) for the given
    user and run.

    Args:
        run: The Run object to find registration for
        member: The Member object to search registration for

    Returns:
        Registration | None: The found registration or None if not found

    """
    # Early return if user is not authenticated
    if not member:
        return None

    # Query database for active registration (non-cancelled, non-redeemed)
    try:
        registration_queryset = Registration.objects.select_related("ticket")
        return registration_queryset.get(
            run=run,
            member=member,
            redeem_code__isnull=True,
            cancellation_date__isnull=True,
        )
    except ObjectDoesNotExist:
        # No active registration found for this user and run
        return None


def check_character_maximum(event_id: int, member: Any) -> tuple[bool, int]:
    """Check if member has reached the maximum character limit for an event.

    Args:
        event_id: The event id to check character limits for
        member: The member whose character count to verify

    Returns:
        Tuple of (has_reached_limit, max_allowed_characters)

    """
    # Get all characters for this member in the event
    characters = get_event_elements(event_id, Character).filter(player=member)

    # Get IDs of inactive characters (those with CharacterConfig inactive=True)
    inactive_character_ids = CharacterConfig.objects.filter(
        character__in=characters,
        name="inactive",
        value="True",
    ).values_list("character_id", flat=True)

    # Count only active characters (exclude inactive ones)
    current_character_count = characters.exclude(id__in=inactive_character_ids).count()

    # Get the maximum allowed characters from event configuration
    maximum_characters_allowed = int(get_event_config(event_id, "user_character_max"))

    # Return whether limit is reached and the maximum allowed
    return current_character_count >= maximum_characters_allowed, maximum_characters_allowed


def get_character_play_max(event_id: int, context: dict | None = None) -> int:
    """Return how many characters a player can play at the same time in an event."""
    return max(1, int(get_event_config(event_id, "character_play_max", context=context)))


def get_player_characters_ids(member: Member, event_id: int, context: dict | None = None) -> set[int]:
    """Get ids of the player's characters for an event, from the batched cache when available.

    Args:
        member: Player owning the characters
        event_id: Event id the characters belong to
        context: Optional context dictionary, optionally containing cached data:
            - player_characters_dict: Dictionary mapping event IDs to lists of
              (id, uuid, name, status) tuples

    Returns:
        Set of character IDs owned by the player in the event

    """
    player_characters_dict = (context or {}).get("player_characters_dict")
    if player_characters_dict is not None:
        entries = player_characters_dict.get(get_event_class_parent(event_id, Character, context=context), [])
        return {entry[0] for entry in entries}

    return set(get_player_characters(member, event_id).values_list("id", flat=True))


def get_player_pending_characters(member: Member, event_id: int, context: dict | None = None) -> list[tuple[str, str]]:
    """Get (uuid, name) of the player's characters awaiting confirmation, from the batched cache when available.

    Args:
        member: Player owning the characters
        event_id: Event ID the characters belong to
        context: Optional context dictionary, optionally containing cached data:
            - player_characters_dict: Dictionary mapping event IDs to lists of
              (id, uuid, name, status) tuples

    Returns:
        List of (uuid, name) for characters with status CREATION or REVIEW

    """
    pending_statuses = {CharacterStatus.CREATION, CharacterStatus.REVIEW}

    player_characters_dict = (context or {}).get("player_characters_dict")
    if player_characters_dict is not None:
        entries = player_characters_dict.get(get_event_class_parent(event_id, Character, context=context), [])
        return [(uuid, name) for _id, uuid, name, status in entries if status in pending_statuses]

    query = get_event_elements(event_id, Character, context=context).filter(player=member, status__in=pending_statuses)
    return list(query.values_list("uuid", "name"))


def get_player_characters(member: Member, event_id: int) -> QuerySet[Character]:
    """Get all characters a player has for an event, ordered by most recently updated."""
    return get_event_elements(event_id, Character).filter(player=member).order_by("-updated")


def get_player_signup(context: dict) -> Registration | None:
    """Get active registration for current user in the given run context."""
    if "registration" in context and context["registration"] is not None:
        return context["registration"]

    # Filter registrations for current run and user, excluding cancelled ones
    active_registrations = Registration.objects.filter(
        run=context["run"],
        member=context["member"],
        cancellation_date__isnull=True,
    )

    # Return first registration if exists
    if active_registrations:
        return active_registrations[0]

    return None


def check_signup(context: dict) -> None:
    """Check if player signup is valid and not in waiting status."""
    # Skip signup check for event staff (admins/organizers)
    if context.get("staff"):
        return

    # Get registration
    registration = get_player_signup(context)
    if not registration:
        raise SignupError(context["run"].get_slug())

    # Signup request still awaiting organizer approval
    if registration.pending:
        raise PendingApprovalError(context["run"].get_slug())

    # Check if registration is in waiting list
    if registration.ticket and registration.ticket.tier == TicketTier.WAITING:
        raise WaitingError(context["run"].get_slug())


def check_assign_character(context: dict) -> None:
    """Check and assign characters to player signup.

    Automatically assigns available characters to a player's signup up to the number of
    characters playable at the same time (character_play_max), skipping characters that
    are inactive or already assigned to this registration. When the player owns more
    assignable characters than free slots, nothing is assigned: the choice is left to
    the player on the character list page.

    Args:
        context: Context dictionary containing event data

    Returns:
        None: Function performs side effects only

    """
    # Get registration
    registration = get_player_signup(context)
    if not registration:
        return

    # Get the number of characters the player can play at the same time
    character_play_max = get_character_play_max(context["event"].id, context)

    # Get currently assigned character IDs for this registration
    assigned_character_ids = set(registration.rcrs.values_list("character_id", flat=True))

    # Skip if player already plays the maximum number of characters
    free_slots = character_play_max - len(assigned_character_ids)
    if free_slots <= 0:
        return

    # Get all characters belonging to this player for the event
    characters = get_player_characters(context["member"], context["event"].id)
    if not characters:
        return

    # Get IDs of inactive characters (those with CharacterConfig inactive=True)
    character_ids = [char.id for char in characters]
    inactive_character_ids = set(
        CharacterConfig.objects.filter(character_id__in=character_ids, name="inactive", value="True").values_list(
            "character_id",
            flat=True,
        ),
    )

    # Filter to get assignable characters (active and not already assigned)
    assignable_characters = [
        char for char in characters if char.id not in inactive_character_ids and char.id not in assigned_character_ids
    ]
    if not assignable_characters:
        return

    # Leave the choice to the player when there are more candidates than free slots
    if len(assignable_characters) > free_slots:
        return

    # Auto-assign the remaining characters
    for character in assignable_characters:
        RegistrationCharacterRel.objects.create(character_id=character.id, registration=registration)
