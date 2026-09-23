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

from django.contrib.auth.models import AnonymousUser
from django.http import Http404, HttpRequest, HttpResponse

from larpmanager.cache.association import get_cache_association
from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.writing import get_writing_element_fields
from larpmanager.models.form import QuestionApplicable
from larpmanager.models.writing import Character, Faction, FactionType, Handout, get_event_elements
from larpmanager.utils.core.base import get_event_context
from larpmanager.utils.core.common import get_element, get_handout
from larpmanager.utils.core.exceptions import NotFoundError
from larpmanager.utils.io.pdf.sheets import (
    print_character,
    print_character_friendly,
    print_faction,
    print_gallery,
    print_handout,
    print_profiles,
)
from larpmanager.utils.larpmanager.tasks import background_auto
from larpmanager.utils.services.character import get_char_check


def print_handout_go(context: dict, handout_uuid: str) -> HttpResponse:
    """Retrieve handout and generate printable version."""
    get_handout(context, handout_uuid)
    return print_handout(context)


def get_fake_request(association_slug: str) -> HttpRequest | None:
    """Create a fake HTTP request with association and anonymous user."""
    request = HttpRequest()
    request.association = get_cache_association(association_slug)
    if request.association is None:
        return None
    request.user = AnonymousUser()
    request.session = {}
    return request


@background_auto(queue="pdf", skip_duplicates=True)
def print_handout_bkg(association_slug: str, event_slug: str, handout_uuid: str) -> None:
    """Print handout by creating a fake request and delegating to print_handout_go."""
    request = get_fake_request(association_slug)
    if request is None:
        return
    context = get_event_context(request, event_slug, check_visibility=False)
    print_handout_go(context, handout_uuid)


def print_character_go(context: dict, character_uuid: str) -> None:
    """Print character information, handling missing character gracefully."""
    try:
        # Validate character access and retrieve character data
        get_char_check(None, context, character_uuid, bypass_access_checks=True)

        # Generate and cache character print outputs
        print_character(context, force=True)
        print_character_friendly(context, force=True)
    except Http404:
        pass
    except NotFoundError:
        pass


@background_auto(queue="pdf", skip_duplicates=True)
def print_character_bkg(association_slug: str, event_slug: str, character_uuid: str) -> None:
    """Print character background for a given association, event slug, and character."""
    request = get_fake_request(association_slug)
    if request is None:
        return
    context = get_event_context(request, event_slug, check_visibility=False)
    print_character_go(context, character_uuid)


def print_faction_go(context: dict, faction_uuid: str) -> None:
    """Print faction sheet, handling missing faction gracefully."""
    try:
        get_element(context, faction_uuid, "faction", Faction)
        faction_obj = context["faction"]
        get_event_cache_all(context)

        # Build sheet data directly from the faction instance (show_complete adds "text")
        sheet_faction = faction_obj.show_complete()
        characters = []
        if faction_obj.typ == FactionType.SECRET:
            member_numbers = set(faction_obj.characters.values_list("number", flat=True))
            characters = [number for number in context["chars"] if number in member_numbers]
        else:
            for character_number, character_data in context["chars"].items():
                if faction_obj.number in character_data.get("factions", []):
                    characters.append(character_number)
        sheet_faction["characters"] = characters
        context["sheet_faction"] = sheet_faction

        # Load all faction fields for this event, bypassing visibility filtering so the
        # organizer sheet prints every answer, not just the ones visible to players
        context["show_all"] = True
        context["fact"] = get_writing_element_fields(
            context,
            "faction",
            QuestionApplicable.FACTION,
            context["faction"].id,
            only_visible=False,
        )

        print_faction(context, force=True)
    except Http404:
        pass
    except NotFoundError:
        pass


@background_auto(queue="pdf", skip_duplicates=True)
def print_faction_bkg(association_slug: str, event_slug: str, faction_uuid: str) -> None:
    """Print faction background for a given association, event slug, and faction."""
    request = get_fake_request(association_slug)
    if request is None:
        return
    context = get_event_context(request, event_slug, check_visibility=False)
    print_faction_go(context, faction_uuid)


@background_auto(queue="pdf", skip_duplicates=True)
def print_run_bkg(association_slug: str, event_slug: str) -> None:
    """Print all background materials for a run including gallery, profiles, characters, and handouts.

    Args:
        association_slug: The association object containing event data
        event_slug: String identifier for the specific run

    Returns:
        None

    """
    # Create fake request context and get event run data
    request = get_fake_request(association_slug)
    if request is None:
        return
    context = get_event_context(request, event_slug, check_visibility=False)

    # Print gallery and character profiles
    print_gallery(context)
    print_profiles(context)

    # Print individual character sheets for all characters in the event
    for character_uuid in get_event_elements(context["run"].event_id, Character, context=context).values_list(
        "uuid", flat=True
    ):
        print_character_go(context, character_uuid)

    # Print all handouts associated with the event
    for handout_uuid in get_event_elements(context["run"].event_id, Handout, context=context).values_list(
        "uuid", flat=True
    ):
        print_handout_go(context, handout_uuid)
