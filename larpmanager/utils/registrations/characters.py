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
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.basic import get_run_basic_cache
from larpmanager.cache.config import get_event_config
from larpmanager.cache.registration_counts import get_run_assigned_character_ids
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.models.form import QuestionApplicable, WritingChoice, WritingOption
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    CharacterStatus,
    get_event_class_parent,
    get_event_elements,
)
from larpmanager.utils.core.exceptions import PaymentProofError, PendingApprovalError, SignupError, WaitingError

if TYPE_CHECKING:
    from collections.abc import Iterable

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


def is_character_access_locked(registration: Registration | None, features: dict | set, context: dict) -> bool:
    """Return whether character access is locked until the registration is paid.

    Lifted by any payment received or any registration payment proof submitted.
    The result is cached in the context per registration.
    """
    if not registration or "payment" not in features:
        return False

    cache = context.setdefault("character_access_locked", {})
    if registration.id not in cache:
        cache[registration.id] = _compute_character_access_locked(registration, context)
    return cache[registration.id]


def _compute_character_access_locked(registration: Registration, context: dict) -> bool:
    """Compute the character access lock for a registration."""
    event_id = get_run_basic_cache(registration.run_id, context=context)["event_id"]
    if not get_event_config(event_id, "user_character_payment_required", context=context):
        return False

    # Nothing to pay, or a payment already received
    if not registration.tot_iscr or registration.tot_payed:
        return False

    proof_statuses = {PaymentStatus.SUBMITTED, PaymentStatus.CONFIRMED, PaymentStatus.CHECKED}
    payment_invoices_dict = context.get("payment_invoices_dict")
    if payment_invoices_dict is not None:
        return not any(
            invoice.status in proof_statuses and invoice.typ == PaymentType.REGISTRATION
            for invoice in payment_invoices_dict.get(registration.id, [])
        )
    return not PaymentInvoice.objects.filter(
        registration_id=registration.id,
        typ=PaymentType.REGISTRATION,
        status__in=proof_statuses,
    ).exists()


def check_character_payment_lock(context: dict) -> None:
    """Raise if the player cannot access characters until the registration payment is completed."""
    if context.get("staff"):
        return

    registration = get_player_signup(context)
    if is_character_access_locked(registration, context.get("features", {}), context):
        raise PaymentProofError(str(registration.uuid))


def get_character_full_options(
    run_id: int,
    character_id: int,
    exclude_character_ids: Iterable[int] = (),
    *,
    lock: bool = False,
) -> list[WritingOption]:
    """Return the limited options of the character with no spots left in the run.

    Spots are taken only by the characters assigned to active registrations of the run.

    Args:
        run_id: Run the character would be assigned to
        character_id: Character to check
        exclude_character_ids: Characters to ignore in the count (e.g. being replaced)
        lock: Lock the option rows, to be used inside a transaction

    Returns:
        List of the options exceeding their max_available

    """
    return get_characters_full_options(run_id, [character_id], exclude_character_ids, lock=lock).get(character_id, [])


def get_characters_full_options(
    run_id: int,
    character_ids: Iterable[int],
    exclude_character_ids: Iterable[int] = (),
    *,
    lock: bool = False,
) -> dict[int, list[WritingOption]]:
    """Return, for each character, its limited options with no spots left in the run.

    Each character is ignored in the count of its own options.

    Args:
        run_id: Run the characters would be assigned to
        character_ids: Characters to check
        exclude_character_ids: Characters to ignore in the count (e.g. being replaced)
        lock: Lock the option rows, to be used inside a transaction

    Returns:
        Dict of character id to the list of its options exceeding their max_available

    """
    character_option_ids: dict[int, set[int]] = {}
    for element_id, option_id in WritingChoice.objects.filter(
        element_id__in=list(character_ids),
        question__applicable=QuestionApplicable.CHARACTER,
    ).values_list("element_id", "option_id"):
        character_option_ids.setdefault(element_id, set()).add(option_id)

    all_option_ids = set().union(*character_option_ids.values())
    options_query = WritingOption.objects.filter(pk__in=all_option_ids, max_available__gt=0)
    if lock:
        options_query = options_query.select_for_update(of=("self",))
    options = list(options_query.select_related("question").order_by("question__order", "order"))
    if not options:
        return {}

    # Characters taking the spots of each option in the run
    option_takers: dict[int, set[int]] = {}
    for option_id, element_id in (
        WritingChoice.objects.filter(
            option_id__in=[option.id for option in options],
            element_id__in=get_run_assigned_character_ids(run_id),
        )
        .exclude(element_id__in=list(exclude_character_ids))
        .values_list("option_id", "element_id")
    ):
        option_takers.setdefault(option_id, set()).add(element_id)

    full_options = {}
    for character_id, option_ids in character_option_ids.items():
        character_full = [
            option
            for option in options
            if option.id in option_ids
            and len(option_takers.get(option.id, set()) - {character_id}) >= option.max_available
        ]
        if character_full:
            full_options[character_id] = character_full

    return full_options


def get_character_option_ids(character_id: int) -> set[int]:
    """Return the ids of the options chosen by the character."""
    return set(
        WritingChoice.objects.filter(
            element_id=character_id,
            question__applicable=QuestionApplicable.CHARACTER,
        ).values_list("option_id", flat=True)
    )


def get_character_new_full_options(
    run_id: int, character_id: int, previous_option_ids: set[int]
) -> list[WritingOption]:
    """Return the options newly chosen by a character assigned to the run, with no spots left.

    The option rows are locked, so it must be called inside a transaction.
    """
    if not get_run_assigned_character_ids(run_id).filter(character_id=character_id).exists():
        return []

    full_options = get_character_full_options(run_id, character_id, lock=True)
    return [option for option in full_options if option.id not in previous_option_ids]


def format_full_options(options: list[WritingOption]) -> str:
    """Return the full options as a readable list of question and option names."""
    return ", ".join(f"{option.question.name}: {option.name}" for option in options)


def get_character_full_options_message(character: Character, options: list[WritingOption]) -> str:
    """Return the message explaining that the character options have no spots left."""
    return _("Character %(character)s cannot be assigned: no spots left for %(options)s") % {
        "character": character.name,
        "options": format_full_options(options),
    }


def get_character_new_full_options_error(options: list[WritingOption]) -> str:
    """Return the error for options chosen meanwhile by other characters, until no spots were left."""
    return _("No spots left for %(options)s, please choose different options") % {
        "options": format_full_options(options),
    }


def get_character_full_options_warning(character: Character, options: list[WritingOption]) -> str:
    """Return the warning for a character assigned over the spots of its options."""
    return _("Character %(character)s assigned, but exceeds the spots available for %(options)s") % {
        "character": character.name,
        "options": format_full_options(options),
    }


def _get_assignable_characters(context: dict, registration: Registration) -> tuple[list[Character], int]:
    """Return the active player characters not yet assigned to the registration, with the free slots.

    Args:
        context: Context dictionary containing event and member data
        registration: Registration of the player

    Returns:
        Tuple of the assignable characters and the number of free slots (character_play_max)

    """
    # Get the number of characters the player can play at the same time
    character_play_max = get_character_play_max(context["event"].id, context)

    # Get currently assigned character IDs for this registration
    assigned_character_ids = set(registration.rcrs.values_list("character_id", flat=True))

    # Skip if player already plays the maximum number of characters
    free_slots = character_play_max - len(assigned_character_ids)
    if free_slots <= 0:
        return [], free_slots

    # Get all characters belonging to this player for the event
    characters = get_player_characters(context["member"], context["event"].id)
    if not characters:
        return [], free_slots

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
    return assignable_characters, free_slots


def will_auto_assign_character(context: dict, character_id: int | None) -> bool:
    """Check if the character will be auto-assigned to the player signup on save.

    Args:
        context: Context dictionary containing event and member data
        character_id: Character to check, None for a character about to be created

    Returns:
        True if the assignable characters, including this one, fit in the free slots

    """
    registration = get_player_signup(context)
    if not registration:
        return False

    assignable_characters, free_slots = _get_assignable_characters(context, registration)
    candidates = len(assignable_characters)
    if character_id is None:
        # The new character is one more candidate
        candidates += 1
    elif character_id not in {char.id for char in assignable_characters}:
        return False

    return 0 < candidates <= free_slots


def check_assign_character(context: dict) -> list[tuple[Character, list[WritingOption]]]:
    """Check and assign characters to player signup.

    Automatically assigns available characters to a player's signup up to the number of
    characters playable at the same time (character_play_max), skipping characters that
    are inactive or already assigned to this registration. When the player owns more
    assignable characters than free slots, nothing is assigned: the choice is left to
    the player on the character list page. Characters whose limited options have no
    spots left in the run are not assigned.

    Args:
        context: Context dictionary containing event data

    Returns:
        List of the characters not assigned for full options, with those options

    """
    # Get registration
    registration = get_player_signup(context)
    if not registration:
        return []

    assignable_characters, free_slots = _get_assignable_characters(context, registration)
    if not assignable_characters:
        return []

    # Leave the choice to the player when there are more candidates than free slots
    if len(assignable_characters) > free_slots:
        return []

    # Auto-assign the remaining characters, skipping those with full options
    blocked = []
    for character in assignable_characters:
        full_options = get_character_full_options(registration.run_id, character.id, lock=True)
        if full_options:
            blocked.append((character, full_options))
            continue
        RegistrationCharacterRel.objects.create(character_id=character.id, registration=registration)

    return blocked
