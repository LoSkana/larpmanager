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

import json
import random
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.registration import registration_payments_status
from larpmanager.cache.config import get_event_config
from larpmanager.forms.miscellanea import OrganizerCastingOptionsForm
from larpmanager.models.casting import AssignmentTrait, Casting, CastingAvoid, Quest, QuestType, Trait
from larpmanager.models.member import Member, Membership
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    TicketTier,
)
from larpmanager.models.writing import Character, Faction, FactionType
from larpmanager.utils.base import check_event_context
from larpmanager.utils.common import get_element, get_time_diff_today
from larpmanager.utils.deadlines import get_membership_fee_year
from larpmanager.views.user.casting import (
    casting_details,
    casting_history_characters,
    casting_history_traits,
    casting_preferences_characters,
    casting_preferences_traits,
)


@login_required
def orga_casting_preferences(request: HttpRequest, event_slug: str, typ: int = 0) -> HttpResponse:
    """Handle casting preferences for characters or traits based on type."""
    # Check user permissions for casting preferences
    context = check_event_context(request, event_slug, "orga_casting_preferences")

    # Get base casting details
    casting_details(context, typ)

    # Load preferences based on type
    if typ == 0:
        casting_preferences_characters(context)
    else:
        casting_preferences_traits(context, typ)

    return render(request, "larpmanager/event/casting/preferences.html", context)


@login_required
def orga_casting_history(request: HttpRequest, event_slug: str, typ: int = 0) -> HttpResponse:
    """Render casting history page with characters or traits based on type.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        typ: History type (0 for characters, 1 for traits)

    Returns:
        Rendered casting history template
    """
    # Check user permissions for casting history access
    context = check_event_context(request, event_slug, "orga_casting_history")

    # Add casting details to context
    casting_details(context, typ)

    # Add type-specific history data to context
    if typ == 0:
        casting_history_characters(context)
    else:
        casting_history_traits(context)

    return render(request, "larpmanager/event/casting/history.html", context)


def assign_casting(request: HttpRequest, context: dict, assignment_type: int) -> None:
    """
    Handle character casting assignment for organizers.

    Processes POST data to assign members to characters or traits in a LARP event.
    Supports mirror character functionality where assignments can be redirected
    to mirror characters if enabled.

    Args:
        request: HTTP request object containing assignment data in POST
        context: Context dictionary containing casting information and feature flags
        assignment_type: Type of casting assignment (0 for characters, other for traits)

    Returns:
        None: Function modifies database state and adds messages to request

    Raises:
        No exceptions are raised, but errors are collected and displayed as messages
    """
    # TODO Assign member to mirror_inv
    # Check if mirror character feature is enabled
    mirror_enabled = "mirror" in context["features"]

    # Extract assignment results from POST data
    assignment_results = request.POST.get("res")
    if not assignment_results:
        messages.error(request, _("Results not present"))
        return

    # Initialize error collection string
    error_messages = ""

    # Process each assignment in the results string
    for assignment_string in assignment_results.split():
        parts = assignment_string.split("_")
        try:
            # Extract member ID and get member object
            member = Member.objects.get(pk=parts[0].replace("p", ""))

            # Get active registration for this member and run
            registration = Registration.objects.get(member=member, run=context["run"], cancellation_date__isnull=True)

            # Extract entity ID (character or trait)
            entity_id = parts[1].replace("c", "")

            # Handle character assignment (assignment_type == 0)
            if assignment_type == 0:
                # Check for mirror character redirection
                if mirror_enabled:
                    character = Character.objects.get(pk=entity_id)
                    if character.mirror:
                        entity_id = character.mirror_id

                # Create character assignment relationship
                RegistrationCharacterRel.objects.create(character_id=entity_id, reg=registration)
            else:
                # Create trait assignment for non-character types
                AssignmentTrait.objects.create(
                    trait_id=entity_id, run_id=registration.run_id, member=member, typ=assignment_type
                )

        except Exception as exception:
            # Collect any errors that occur during processing
            print(exception)
            error_messages += str(exception)

    # Display collected errors to user if any occurred
    if error_messages:
        messages.error(request, error_messages)


def get_casting_choices_characters(
    context: dict, filtering_options: dict
) -> tuple[dict[int, str], list[int], dict[int, str], list[int]]:
    """Get character choices for casting with filtering and availability status.

    Retrieves all available characters for casting based on faction filtering,
    tracking which characters are already taken and handling mirror relationships.

    Args:
        context: Context dictionary containing:
            - event: Event instance for character filtering
            - run: Run instance for registration filtering
            - features: dict of enabled features
        filtering_options: Dictionary containing:
            - factions: List of allowed faction IDs for filtering

    Returns:
        Tuple containing:
            - character_choices: dict mapping character IDs to display names
            - taken_character_ids: List of character IDs that are already assigned
            - mirror_character_mapping: dict mapping character IDs to their mirror character IDs
            - allowed_character_ids: List of character IDs allowed by faction filtering
    """
    character_choices = {}
    mirror_character_mapping = {}
    taken_character_ids = []

    # Build list of allowed characters based on faction filtering
    allowed_character_ids = []
    if "faction" in context["features"]:
        # Get primary factions for the event
        primary_factions_query = context["event"].get_elements(Faction).filter(typ=FactionType.PRIM)
        for faction_element in primary_factions_query.order_by("number"):
            # Skip factions not in the allowed filtering_options
            if str(faction_element.id) not in filtering_options["factions"]:
                continue
            # Add all characters from this faction to allowed list
            allowed_character_ids.extend(faction_element.characters.values_list("id", flat=True))

    # Get characters that are already registered for this run
    registered_character_ids = RegistrationCharacterRel.objects.filter(reg__run=context["run"]).values_list(
        "character_id", flat=True
    )

    # Process all characters for the event (excluding hidden ones)
    characters_query = context["event"].get_elements(Character)
    for character in characters_query.exclude(hide=True):
        # Skip characters not allowed by faction filtering
        if allowed_character_ids and character.id not in allowed_character_ids:
            continue

        # Mark character as taken if already registered
        if character.id in registered_character_ids:
            taken_character_ids.append(character.id)

        # Handle mirror character relationships
        if character.mirror_id:
            # Mark character as taken if its mirror is registered
            if character.mirror_id in registered_character_ids:
                taken_character_ids.append(character.id)
            # Store mirror relationship mapping
            mirror_character_mapping[character.id] = str(character.mirror_id)

        # Add character to character_choices with display name
        character_choices[character.id] = str(character)

    return character_choices, taken_character_ids, mirror_character_mapping, allowed_character_ids


def get_casting_choices_quests(context: dict) -> tuple[dict[int, str], list[int], dict]:
    """Get quest-based casting choices and track assigned traits.

    Args:
        context: Context dict containing 'event', 'quest_type', and 'run'

    Returns:
        Tuple of (choices dict, taken trait IDs, empty dict)
    """
    trait_choices = {}
    assigned_trait_ids = []

    # Get all quests for the event and quest type, ordered by number
    for quest in Quest.objects.filter(event=context["event"], typ=context["quest_type"]).order_by("number"):
        # Process traits for each quest
        for trait in Trait.objects.filter(quest=quest).order_by("number"):
            # Check if trait is already assigned to someone in this run
            if AssignmentTrait.objects.filter(trait=trait, run=context["run"]).count() > 0:
                assigned_trait_ids.append(trait.id)

            # Build choice label with quest and trait names
            trait_choices[trait.id] = f"{quest.name} - {trait.name}"

    return trait_choices, assigned_trait_ids, {}


def check_player_skip_characters(registration_character_rel: RegistrationCharacterRel, context: dict) -> bool:
    """Check if registration has reached maximum allowed characters."""
    # Get max characters allowed from event config
    max_characters_allowed = int(get_event_config(context["event"].id, "casting_characters", 1, context))

    # Check if current character count meets or exceeds limit
    return RegistrationCharacterRel.objects.filter(reg=registration_character_rel).count() >= max_characters_allowed


def check_player_skip_quests(registration, trait_type):
    return (
        AssignmentTrait.objects.filter(
            run_id=registration.run_id, member_id=registration.member_id, typ=trait_type
        ).count()
        > 0
    )


def check_casting_player(
    context: dict,
    registration,
    casting_filter_options: dict,
    casting_type: int,
    cached_membership_statuses: dict,
    cached_aim_memberships: dict,
) -> bool:
    """Check if player should be skipped in casting based on various criteria.

    This function evaluates multiple filtering criteria to determine whether
    a registered player should be excluded from casting assignments.

    Args:
        context: Context dictionary containing features data and configuration
        registration: Registration instance representing the player's registration
        casting_filter_options: Dictionary with casting filter options (tickets, memberships, pays)
        casting_type: Casting type identifier (0 for characters, other values for quests)
        cached_membership_statuses: Cached membership statuses keyed by member ID
        cached_aim_memberships: Cached aim membership data for additional status checks

    Returns:
        True if player should be skipped in casting, False otherwise

    Example:
        >>> should_skip = check_casting_player(context, registration, filters, 0, memb_cache, aim_cache)
    """
    # Filter by ticket type - skip if player's ticket not in allowed list
    if "tickets" in casting_filter_options and str(registration.ticket_id) not in casting_filter_options["tickets"]:
        return True

    # Filter by membership status when membership feature is enabled
    if "membership" in context["features"]:
        # Skip if member not found in membership cache
        if registration.member_id not in cached_membership_statuses:
            return True

        # Determine actual membership status, accounting for AIM membership
        membership_status = cached_membership_statuses[registration.member_id]
        if membership_status == "a" and registration.member_id in cached_aim_memberships:
            membership_status = "p"  # Override status for AIM members

        # Skip if membership status not in allowed list
        if "memberships" in casting_filter_options and membership_status not in casting_filter_options["memberships"]:
            return True

    # Filter by payment status - check current payment state
    registration_payments_status(registration)
    if "pays" in casting_filter_options and registration.payment_status:
        # Skip if payment status not in allowed list
        if registration.payment_status not in casting_filter_options["pays"]:
            return True

    # Check for existing assignments based on casting type
    if casting_type == 0:
        # Character casting - check if already assigned to character
        has_existing_assignment = check_player_skip_characters(registration, context)
    else:
        # Quest casting - check if already assigned to quest
        has_existing_assignment = check_player_skip_quests(registration, casting_type)

    # Skip if player already has assignments
    if has_existing_assignment:
        return True

    return False


def get_casting_data(
    request: HttpRequest, context: dict, casting_type: int, form: "OrganizerCastingOptionsForm"
) -> None:
    """Retrieve and process casting data for automated character assignment algorithm.

    Collects player preferences, character choices, ticket types, membership status,
    payment status, and avoidance lists. Processes data into JSON-serialized format
    for client-side casting algorithm execution with priority weighting.

    Args:
        request: HTTP request object for association context
        context: Context dictionary to populate with casting data
        casting_type: Casting type (0 for characters, other for quest traits)
        form: Form with filtering options (tickets, membership, payment status)

    Side effects:
        - Adds JSON-serialized casting data to context (choices, players, preferences, etc.)
        - Loads membership and payment status caches
        - Calculates registration and payment priorities
        - Filters players based on form options
    """
    # Extract filtering options from form (tickets, membership status, payment status)
    filter_options = form.get_data()

    # Load casting configuration (max choices, additional padding)
    casting_details(context, casting_type)

    # Initialize data structures for casting algorithm
    players_info = {}  # Player info with priorities
    players_without_choices = []  # Players who didn't submit preferences
    player_preferences = {}  # Player->Character preference mappings
    character_avoidances = {}  # Characters players want to avoid
    chosen_characters = {}  # Characters that have been selected by at least one player

    # Get available choices based on casting type
    if casting_type == 0:
        # Character casting - includes faction filtering and mirror handling
        (available_choices, taken_characters, mirror_characters, allowed_factions) = get_casting_choices_characters(
            context, filter_options
        )
    else:
        # Quest trait casting
        get_element(context, casting_type, "quest_type", QuestType, by_number=True)
        allowed_factions = None
        (available_choices, taken_characters, mirror_characters) = get_casting_choices_quests(context)

    # Load cached membership and casting preference data
    cache_aim, cache_memberships, casting_submissions = _casting_prepare(context, request, casting_type)

    # Process each registration to build player preferences
    registrations_query = Registration.objects.filter(run=context["run"], cancellation_date__isnull=True)
    # Exclude non-participant ticket types from casting
    registrations_query = registrations_query.exclude(
        ticket__tier__in=[TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC]
    )
    registrations_query = registrations_query.order_by("created").select_related("ticket", "member")
    for registration in registrations_query:
        # Skip players that don't match filter criteria (ticket, membership, payment)
        if check_casting_player(context, registration, filter_options, casting_type, cache_memberships, cache_aim):
            continue

        # Add player info with ticket priority and registration/payment dates
        _get_player_info(players_info, registration)

        # Extract player's character preferences from casting submissions
        player_choice_list = _get_player_preferences(
            allowed_factions, casting_submissions, chosen_characters, character_avoidances, registration
        )

        # Track players who didn't submit preferences
        if len(player_choice_list) == 0:
            players_without_choices.append(registration.member_id)
        else:
            player_preferences[registration.member_id] = player_choice_list

    # Add random unchosen characters to resolve ties fairly
    unchosen_characters, unchosen_padding = _fill_not_chosen(
        available_choices, chosen_characters, context, player_preferences, taken_characters
    )

    # Load character avoidance texts (reasons players can't play certain characters)
    avoidance_texts = {}
    for avoidance_entry in CastingAvoid.objects.filter(run=context["run"], typ=casting_type):
        avoidance_texts[avoidance_entry.member_id] = avoidance_entry.text

    # Serialize all data to JSON for client-side casting algorithm
    context["num_choices"] = min(context["casting_max"] + unchosen_padding, len(available_choices))
    context["choices"] = json.dumps(available_choices)
    context["mirrors"] = json.dumps(mirror_characters)
    context["players"] = json.dumps(players_info)
    context["preferences"] = json.dumps(player_preferences)
    context["taken"] = json.dumps(taken_characters)
    context["not_chosen"] = json.dumps(unchosen_characters)
    context["chosen"] = json.dumps(list(chosen_characters.keys()))
    context["didnt_choose"] = json.dumps(players_without_choices)
    context["nopes"] = json.dumps(character_avoidances)
    context["avoids"] = json.dumps(avoidance_texts)

    # Load priority configuration for algorithm weighting
    for priority_key in ("reg_priority", "pay_priority"):
        context[priority_key] = int(get_event_config(context["event"].id, f"casting_{priority_key}", 0, context))


def _casting_prepare(context: dict, request, typ: str) -> tuple[int, dict[int, str], dict[int, list]]:
    """Prepare casting data for a specific run and type.

    Args:
        context: Context dictionary containing run information
        request: HTTP request object with association data
        typ: Type of casting to filter

    Returns:
        tuple: A tuple containing:
            - membership_fee_year: Membership fee year for the association
            - member_id_to_status: Dictionary mapping member IDs to their membership status
            - member_id_to_castings: Dictionary mapping member IDs to their list of casting objects
    """
    # Get the membership fee year for the current association
    membership_fee_year = get_membership_fee_year(context["association_id"])

    # Build cache of member statuses for the association
    member_id_to_status = {}
    membership_query = Membership.objects.filter(association_id=context["association_id"])
    for membership in membership_query.values("member_id", "status"):
        member_id_to_status[membership["member_id"]] = membership["status"]

    # Group casting objects by member ID for the specified run and type
    member_id_to_castings = {}
    for casting in Casting.objects.filter(run=context["run"], typ=typ).order_by("pref"):
        # Initialize member's casting list if not exists
        if casting.member_id not in member_id_to_castings:
            member_id_to_castings[casting.member_id] = []
        member_id_to_castings[casting.member_id].append(casting)

    return membership_fee_year, member_id_to_status, member_id_to_castings


def _get_player_info(players: dict, registration: Registration) -> None:
    """
    Update the players dictionary with registration information for a single player.

    Args:
        players (dict): Dictionary to store player information, keyed by member ID
        registration: Registration object containing member and ticket information

    Returns:
        None: Function modifies the players dictionary in-place
    """
    # Initialize basic player information with default priority
    players[registration.member_id] = {
        "name": str(registration.member),
        "prior": 1,
        "email": registration.member.email,
    }

    # Override priority if ticket has casting priority defined
    if registration.ticket:
        players[registration.member_id]["prior"] = registration.ticket.casting_priority

    # Calculate registration days (number of days from registration creation)
    players[registration.member_id]["reg_days"] = -get_time_diff_today(registration.created.date()) + 1

    # Calculate payment days (number of days from full payment, default to 1 if unpaid)
    players[registration.member_id]["pay_days"] = (
        -get_time_diff_today(registration.payment_date) + 1 if registration.payment_date else 1
    )


def _get_player_preferences(allowed: set | None, castings: dict, chosen: dict, nopes: dict, reg: Registration) -> list:
    """Get player preferences from casting data.

    Processes casting choices for a registration, filtering by allowed elements
    and tracking both chosen preferences and rejected options.

    Args:
        allowed: Set of allowed elements to filter by, or None for no filtering
        castings: Dictionary mapping member IDs to their casting choices
        chosen: Dictionary to track chosen elements (modified in-place)
        nopes: Dictionary to track rejected elements by member (modified in-place)
        reg: Registration object containing member information

    Returns:
        List of preference elements for the player
    """
    # Initialize preferences list
    preferences = []

    # Check if this member has any casting choices
    if reg.member_id in castings:
        # Process each casting choice for this member
        for casting_choice in castings[reg.member_id]:
            # Skip elements not in allowed set (if filtering is enabled)
            if allowed and casting_choice.element not in allowed:
                continue

            # Add element to preferences and mark as chosen
            element = casting_choice.element
            preferences.append(element)
            chosen[element] = 1

            # Track rejected preferences ("nopes") for this member
            if casting_choice.nope:
                if reg.member_id not in nopes:
                    nopes[reg.member_id] = []
                nopes[reg.member_id].append(element)

    return preferences


def _fill_not_chosen(choices: dict, chosen: set, context: dict, preferences: dict, taken: set) -> tuple[list, int]:
    """Fill player preferences with non-chosen characters to resolve unlucky ties.

    This function adds up to `context["casting_add"]` non-taken characters to each
    player's preference list. Characters are shuffled randomly for each player
    to ensure fair distribution when resolving casting conflicts.

    Args:
        choices: Dictionary mapping character IDs to character data
        chosen: Set of character IDs that have already been chosen
        context: Context dictionary containing casting configuration (must have "casting_add" key)
        preferences: Dictionary mapping member IDs to their character preference lists
        taken: Set of character IDs that are unavailable/taken

    Returns:
        tuple: A tuple containing:
            - list: Sorted list of available character IDs that weren't chosen or taken
            - int: Number of characters actually added to each preference list
    """
    # Collect all character IDs that are available (not chosen and not taken)
    available_character_ids = []
    for character_id in choices.keys():
        if character_id not in chosen and character_id not in taken:
            available_character_ids.append(character_id)

    # Sort the available characters for consistent ordering
    available_character_ids.sort()

    # Determine how many characters to add (limited by available characters)
    characters_to_add_count = min(context["casting_add"], len(available_character_ids))

    # Add randomly shuffled available characters to each player's preferences
    for _member_id, preference_list in preferences.items():
        # Shuffle for each player to ensure fair random distribution
        random.shuffle(available_character_ids)
        # Add the specified number of characters to this player's preferences
        for index in range(0, characters_to_add_count):
            preference_list.append(available_character_ids[index])

    return available_character_ids, characters_to_add_count


@login_required
def orga_casting(request: HttpRequest, event_slug: str, typ: Optional[int] = None, tick: str = "") -> HttpResponse:
    """Handle organizational casting assignments for LARP events.

    Manages the casting assignment process for event organizers, allowing them to
    assign participants to specific casting types and roles within an event.

    Args:
        request: The HTTP request object containing user data and POST parameters
        event_slug: Event slug identifier used to identify the specific event
        typ: Casting type identifier. If None, redirects to default type 0
        tick: Ticket identifier string for specific participant casting

    Returns:
        HttpResponse: Rendered casting template with form and casting data,
                     or redirect response after successful assignment

    Raises:
        Http404: When the submitted form is not valid
    """
    # Check user permissions for accessing casting functionality
    context = check_event_context(request, event_slug, "orga_casting")

    # Redirect to default casting type if none specified
    if typ is None:
        return redirect("orga_casting", event_slug=context["run"].get_slug(), typ=0)

    # Set context variables for template rendering
    context["typ"] = typ
    context["tick"] = tick

    # Handle POST request for casting assignment
    if request.method == "POST":
        form = OrganizerCastingOptionsForm(request.POST, context=context)

        # Validate form data before processing
        if not form.is_valid():
            raise Http404("form not valid")

        # Process casting assignment if submit button was clicked
        if request.POST.get("submit"):
            assign_casting(request, context, typ)
            return redirect(request.path_info)
    else:
        # Initialize empty form for GET requests
        form = OrganizerCastingOptionsForm(context=context)

    # Retrieve and populate casting details for the specified type
    casting_details(context, typ)

    # Get casting data and populate form with current selections
    get_casting_data(request, context, typ, form)

    # Add form to context and render template
    context["form"] = form
    return render(request, "larpmanager/orga/casting.html", context)


@login_required
def orga_casting_toggle(request, event_slug, typ):
    context = check_event_context(request, event_slug, "orga_casting")
    try:
        pid = request.POST["pid"]
        oid = request.POST["oid"]
        c = Casting.objects.get(run=context["run"], typ=typ, member_id=pid, element=oid)
        c.nope = not c.nope
        c.save()
        return JsonResponse({"res": "ok"})
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko"})
