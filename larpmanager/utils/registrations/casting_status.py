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

from typing import TYPE_CHECKING

from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_event_config
from larpmanager.models.casting import Casting
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import CharacterStatus
from larpmanager.utils.core.common import feature_visible
from larpmanager.utils.registrations.availability import get_character_options_availability
from larpmanager.utils.registrations.characters import (
    check_character_maximum,
    get_character_play_max,
    get_player_characters_ids,
    get_player_pending_characters,
)

if TYPE_CHECKING:
    from larpmanager.models.event import Run


def registration_status_characters(
    run: Run, registration: Registration, run_status: dict, features: dict, context: dict | None = None
) -> None:
    """Update registration status with character assignment information.

    Displays assigned characters with approval status and provides links
    for character creation or selection based on event configuration.

    Args:
        run: The run object containing status information
        registration: The registration object with character relationships
        features: Dictionary of enabled event features
        run_status: Dictionary with run status
        context: Optional context dictionary containing cached data:
            - character_rels_dict: Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    character_rels_dict = context.get("character_rels_dict")

    # Get character relationships either from provided dict or database query
    if character_rels_dict is not None:
        registration_character_rels = character_rels_dict.get(registration.id, [])
    else:
        query = RegistrationCharacterRel.objects.filter(registration_id=registration.id)
        registration_character_rels = query.order_by("character__number").select_related("character")

    # Build list of character links with names and approval status
    character_links_data = [
        _get_character_links(run, context, features, character_rel) for character_rel in registration_character_rels
    ]
    run_status["character_links"] = character_links_data
    character_links = [_character_links_html(character_entry) for character_entry in character_links_data]

    # Add character information to status details based on number of characters
    if len(character_links) == 1:
        run_status["details_characters"] = format_html("{}: {}", _("Your character is"), character_links[0])
    elif len(character_links) > 1:
        run_status["details_characters"] = format_html(
            "{}: {}",
            _("Your characters are"),
            format_html_join(" - ", "{}", ((link,) for link in character_links)),
        )

    assigned_count = len(character_links)
    is_assigned = assigned_count > 0

    # Count the player's own characters still available to be chosen
    selectable_count = 0
    owned_count = 0
    can_switch = False
    play_max = get_character_play_max(run.event_id, context)
    if "user_character" in features:
        owned_ids = get_player_characters_ids(registration.member, run.event_id, context)
        assigned_ids = {character_rel.character_id for character_rel in registration_character_rels}
        selectable_count = len(owned_ids - assigned_ids)
        owned_count = len(owned_ids)

        # With no free slot, the played character can still be swapped, if the player created it
        can_switch = play_max == 1 and bool(assigned_ids) and assigned_ids <= owned_ids

    _status_approval(
        run,
        registration,
        run_status,
        features,
        {
            "assigned": assigned_count,
            "selectable": selectable_count,
            "owned": owned_count,
            "play_max": play_max,
        },
        can_switch=can_switch,
        context=context,
    )
    _status_casting(run, registration, run_status, features, context, is_character_assigned=is_assigned)


def _get_character_links(run: Run, context: dict, features: dict, character_rel: RegistrationCharacterRel) -> dict:
    """Builds structured data with links for the character quick access bar."""
    character_url = reverse("character", args=[run.get_slug(), character_rel.character.uuid])
    character_name = character_rel.character.name
    character_uuid = character_rel.character.uuid

    # Use custom name if provided
    if character_rel.custom_name:
        character_name = character_rel.custom_name

    # Add approval status if character approval is enabled and not approved
    approval_required = get_event_config(run.event_id, "user_character_approval", context=context)
    if approval_required and character_rel.character.status != CharacterStatus.APPROVED:
        character_name += f" ({_(character_rel.character.get_status_display())})"

    # Create clickable link for character
    character_links = [
        {
            "url": character_url,
            "label": character_name,
            "tooltip": _("Access your character sheet"),
            "icon": "fa-solid fa-person",
        }
    ]

    allowed_sidebar = context.get("demo_allowed_sidebar")

    if feature_visible("user_character", features, allowed_sidebar):
        character_links.append(
            {
                "url": reverse("character_edit", args=[run.get_slug(), character_uuid]),
                "label": _("Edit"),
                "tooltip": _("Edit your character's details"),
                "icon": "fa-solid fa-pen-to-square",
            }
        )

    if feature_visible("experience", features, allowed_sidebar) and get_event_config(
        run.event_id, "exp_user", context=context
    ):
        character_links.append(
            {
                "url": reverse("character_abilities", args=[run.get_slug(), character_uuid]),
                "label": _("Abilities"),
                "tooltip": _("Buy abilities for your character"),
                "icon": "fa-solid fa-bolt",
            }
        )

    if feature_visible("custom_character", features, allowed_sidebar):
        character_links.append(
            {
                "url": reverse("character_customize", args=[run.get_slug(), character_uuid]),
                "label": _("Customize"),
                "tooltip": _("Modify the character details to make it yours"),
                "icon": "fa-solid fa-palette",
            }
        )

    if feature_visible("player_relationships", features, allowed_sidebar):
        character_links.append(
            {
                "url": reverse("character_relationships", args=[run.get_slug(), character_uuid]),
                "label": _("Relationships"),
                "tooltip": _("Fill in your character's relationships"),
                "icon": "fa-solid fa-people-arrows",
            }
        )

    if feature_visible("help", features, allowed_sidebar):
        character_links.append(
            {
                "url": reverse("help", args=[run.get_slug()]),
                "label": _("Questions"),
                "tooltip": _("Write your questions about the character directly to the authors here."),
                "icon": "fa-solid fa-circle-question",
            }
        )

    return {"name": character_name, "links": character_links}


def _character_links_html(character_entry: dict) -> str:
    """Render the character quick access links as an HTML snippet."""
    character_link_snippets = [
        format_html(
            '<span class="lm_tooltip"><a href="{}">{}</a><span class="lm_tooltiptext">{}!</span></span>',
            link["url"],
            link["label"],
            link["tooltip"],
        )
        for link in character_entry["links"]
    ]

    return format_html_join(" | ", "{}", ((snippet,) for snippet in character_link_snippets))


def _status_approval(
    run: Run,
    registration: Registration,
    run_status: dict,
    features: dict,
    character_counts: dict,
    *,
    can_switch: bool,
    context: dict | None = None,
) -> None:
    """Add character creation/selection actions to run status based on feature availability.

    This function checks if the user_character feature is enabled and the registration
    is not on a waiting list, then fills run_status["character_actions"] with the available
    actions (create a new character, choose an existing one, confirm a character pending
    approval), and run_status["character_change"] / run_status["character_create"] with the
    links to swap the played character or to create another one, shown only on the event page.

    Args:
        run: Run object containing event information
        registration: The registration object
        features: Dictionary of enabled features for the event
        run_status: Dictionary with run status
        character_counts: Counts of assigned, selectable and owned characters, plus the play maximum
        can_switch: Whether the played character can be swapped for another one of the player
        context: Optional context dictionary, used to read the user_character_approval config

    """
    # Check if user_character feature is enabled
    if "user_character" not in features:
        return

    # Skip if registration is on waiting list
    if registration.ticket and registration.ticket.tier == TicketTier.WAITING:
        return

    # Get character creation limits for this user and event
    reached_maximum, maximum_characters = check_character_maximum(run.event_id, registration.member)

    assigned_count = character_counts["assigned"]
    selectable_count = character_counts["selectable"]
    owned_count = character_counts["owned"]
    play_max = character_counts["play_max"]

    character_actions = []

    # With more characters allowed, the player already created one is only offered to create another
    if not reached_maximum and owned_count and maximum_characters > 1:
        run_status["character_create"] = {
            "url": reverse("character_create", args=[run.get_slug()]),
            "label": _("Create another character"),
            "tooltip": _("Create another character!"),
            "icon": "fa-solid fa-wand-magic-sparkles",
        }
    # Show character creation action if user can create more characters
    elif not reached_maximum:
        character_actions.append(
            {
                "url": reverse("character_create", args=[run.get_slug()]),
                "label": _("Create your character"),
                "label_long": _("Create the character you will play in this event!"),
                "tooltip": _("Create your character!"),
                "icon": "fa-solid fa-wand-magic-sparkles",
                "status_type": "todo",
                "status_icon": "fa-solid fa-list-check",
                "options_availability": get_character_options_availability(run),
            }
        )

    # Show character selection action if the player has free slots and characters to choose from
    if selectable_count and assigned_count < play_max:
        character_actions.append(
            {
                "url": reverse("character_list", args=[run.get_slug()]),
                "label": _("Choose your character"),
                "label_long": _("Choose the character you will play in this event!"),
                "tooltip": _("Choose your character!"),
                "icon": "fa-solid fa-users-viewfinder",
                "status_type": "todo",
                "status_icon": "fa-solid fa-list-check",
            }
        )

    # Offer the change link when all slots are taken, but the player can swap the played character
    elif selectable_count and can_switch:
        run_status["character_change"] = {
            "url": reverse("character_list", args=[run.get_slug()]),
            "label": _("Change your character"),
            "tooltip": _("Change your character!"),
            "icon": "fa-solid fa-right-left",
        }

    # Offer a confirm action for the player's own characters still awaiting proposal to the staff
    if "user_character" in features and get_event_config(run.event_id, "user_character_approval", context=context):
        pending_characters = get_player_pending_characters(registration.member, run.event_id, context)
        character_actions.extend(
            {
                "url": reverse("character_confirm", args=[run.get_slug(), character_uuid]),
                "label": _("Confirm character"),
                "label_long": _("Confirm your character %(name)s is ready to propose to the staff!")
                % {"name": character_name},
                "tooltip": _("Confirm your character!"),
                "icon": "fa-solid fa-check",
                "status_type": "todo",
                "status_icon": "fa-solid fa-list-check",
            }
            for character_uuid, character_name in pending_characters
        )

    if character_actions:
        run_status["character_actions"] = character_actions


def casting_preferences_pending(
    run: Run,
    registration: Registration,
    features: dict,
    context: dict | None = None,
    *,
    is_character_assigned: bool = False,
) -> bool:
    """Return True if casting is active and the member still needs to submit preferences.

    Skipped once the character is assigned (casting already happened), once the
    member has already submitted preferences for this run, if the ticket is on
    the waiting list, or if characters aren't visible to players yet.
    """
    if "casting" not in features:
        return False

    if registration.ticket and registration.ticket.tier == TicketTier.WAITING:
        return False

    if is_character_assigned:
        return False

    field_visibility = get_event_config(run.event_id, "writing_field_visibility", context=context)
    if field_visibility and not (context or {}).get("show_character"):
        return False

    return not Casting.objects.filter(run=run, member=registration.member, typ=0).exists()


def _status_casting(
    run: Run,
    registration: Registration,
    run_status: dict,
    features: dict,
    context: dict | None = None,
    *,
    is_character_assigned: bool,
) -> None:
    """Add a reminder link to submit casting preferences, if not already done."""
    if not casting_preferences_pending(
        run, registration, features, context, is_character_assigned=is_character_assigned
    ):
        return

    run_status["casting_action"] = {
        "url": reverse("casting", args=[run.get_slug()]),
        "label": _("Select your preferences"),
        "label_long": _("Select your casting preferences!"),
        "icon": "fa-solid fa-people-arrows",
    }
