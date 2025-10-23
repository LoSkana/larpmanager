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
from larpmanager.utils.common import get_element, get_time_diff_today
from larpmanager.utils.deadlines import get_membership_fee_year
from larpmanager.utils.event import check_event_permission
from larpmanager.views.user.casting import (
    casting_details,
    casting_history_characters,
    casting_history_traits,
    casting_preferences_characters,
    casting_preferences_traits,
)


@login_required
def orga_casting_preferences(request: HttpRequest, s: str, typ: int = 0) -> HttpResponse:
    """Handle casting preferences for characters or traits based on type."""
    # Check user permissions for casting preferences
    ctx = check_event_permission(request, s, "orga_casting_preferences")

    # Get base casting details
    casting_details(ctx, typ)

    # Load preferences based on type
    if typ == 0:
        casting_preferences_characters(ctx)
    else:
        casting_preferences_traits(ctx, typ)

    return render(request, "larpmanager/event/casting/preferences.html", ctx)


@login_required
def orga_casting_history(request: HttpRequest, s: str, typ: int = 0) -> HttpResponse:
    """Render casting history page with characters or traits based on type.

    Args:
        request: HTTP request object
        s: Event slug identifier
        typ: History type (0 for characters, 1 for traits)

    Returns:
        Rendered casting history template
    """
    # Check user permissions for casting history access
    ctx = check_event_permission(request, s, "orga_casting_history")

    # Add casting details to context
    casting_details(ctx, typ)

    # Add type-specific history data to context
    if typ == 0:
        casting_history_characters(ctx)
    else:
        casting_history_traits(ctx)

    return render(request, "larpmanager/event/casting/history.html", ctx)


def assign_casting(request: HttpRequest, ctx: dict, typ: int) -> None:
    """
    Handle character casting assignment for organizers.

    Processes POST data to assign members to characters or traits in a LARP event.
    Supports mirror character functionality where assignments can be redirected
    to mirror characters if enabled.

    Args:
        request: HTTP request object containing assignment data in POST
        ctx: Context dictionary containing casting information and feature flags
        typ: Type of casting assignment (0 for characters, other for traits)

    Returns:
        None: Function modifies database state and adds messages to request

    Raises:
        No exceptions are raised, but errors are collected and displayed as messages
    """
    # TODO Assign member to mirror_inv
    # Check if mirror character feature is enabled
    mirror = "mirror" in ctx["features"]

    # Extract assignment results from POST data
    res = request.POST.get("res")
    if not res:
        messages.error(request, _("Results not present"))
        return

    # Initialize error collection string
    err = ""

    # Process each assignment in the results string
    for sp in res.split():
        aux = sp.split("_")
        try:
            # Extract member ID and get member object
            mb = Member.objects.get(pk=aux[0].replace("p", ""))

            # Get active registration for this member and run
            reg = Registration.objects.get(member=mb, run=ctx["run"], cancellation_date__isnull=True)

            # Extract entity ID (character or trait)
            eid = aux[1].replace("c", "")

            # Handle character assignment (typ == 0)
            if typ == 0:
                # Check for mirror character redirection
                if mirror:
                    char = Character.objects.get(pk=eid)
                    if char.mirror:
                        eid = char.mirror_id

                # Create character assignment relationship
                RegistrationCharacterRel.objects.create(character_id=eid, reg=reg)
            else:
                # Create trait assignment for non-character types
                AssignmentTrait.objects.create(trait_id=eid, run_id=reg.run_id, member=mb, typ=typ)

        except Exception as e:
            # Collect any errors that occur during processing
            print(e)
            err += str(e)

    # Display collected errors to user if any occurred
    if err:
        messages.error(request, err)


def get_casting_choices_characters(
    ctx: dict, options: dict
) -> tuple[dict[int, str], list[int], dict[int, str], list[int]]:
    """Get character choices for casting with filtering and availability status.

    Retrieves all available characters for casting based on faction filtering,
    tracking which characters are already taken and handling mirror relationships.

    Args:
        ctx: Context dictionary containing:
            - event: Event instance for character filtering
            - run: Run instance for registration filtering
            - features: dict of enabled features
        options: Dictionary containing:
            - factions: List of allowed faction IDs for filtering

    Returns:
        Tuple containing:
            - choices: dict mapping character IDs to display names
            - taken: List of character IDs that are already assigned
            - mirrors: dict mapping character IDs to their mirror character IDs
            - allowed: List of character IDs allowed by faction filtering
    """
    choices = {}
    mirrors = {}
    taken = []

    # Build list of allowed characters based on faction filtering
    allowed = []
    if "faction" in ctx["features"]:
        # Get primary factions for the event
        que = ctx["event"].get_elements(Faction).filter(typ=FactionType.PRIM)
        for el in que.order_by("number"):
            # Skip factions not in the allowed options
            if str(el.id) not in options["factions"]:
                continue
            # Add all characters from this faction to allowed list
            allowed.extend(el.characters.values_list("id", flat=True))

    # Get characters that are already registered for this run
    chars = RegistrationCharacterRel.objects.filter(reg__run=ctx["run"]).values_list("character_id", flat=True)

    # Process all characters for the event (excluding hidden ones)
    que = ctx["event"].get_elements(Character)
    for c in que.exclude(hide=True):
        # Skip characters not allowed by faction filtering
        if allowed and c.id not in allowed:
            continue

        # Mark character as taken if already registered
        if c.id in chars:
            taken.append(c.id)

        # Handle mirror character relationships
        if c.mirror_id:
            # Mark character as taken if its mirror is registered
            if c.mirror_id in chars:
                taken.append(c.id)
            # Store mirror relationship mapping
            mirrors[c.id] = str(c.mirror_id)

        # Add character to choices with display name
        choices[c.id] = str(c)

    return choices, taken, mirrors, allowed


def get_casting_choices_quests(ctx: dict) -> tuple[dict[int, str], list[int], dict]:
    """Get quest-based casting choices and track assigned traits.

    Args:
        ctx: Context dict containing 'event', 'quest_type', and 'run'

    Returns:
        Tuple of (choices dict, taken trait IDs, empty dict)
    """
    choices = {}
    taken = []

    # Get all quests for the event and quest type, ordered by number
    for q in Quest.objects.filter(event=ctx["event"], typ=ctx["quest_type"]).order_by("number"):
        # gr = q.show()["name"]

        # Process traits for each quest
        for t in Trait.objects.filter(quest=q).order_by("number"):
            # Check if trait is already assigned to someone in this run
            if AssignmentTrait.objects.filter(trait=t, run=ctx["run"]).count() > 0:
                taken.append(t.id)

            # Build choice label with quest and trait names
            choices[t.id] = f"{q.name} - {t.name}"

    return choices, taken, {}


def check_player_skip_characters(reg, ctx):
    # check it has a number of characters assigned less the allowed amount
    casting_chars = int(get_event_config(ctx["event"].id, "casting_characters", 1, ctx))
    return RegistrationCharacterRel.objects.filter(reg=reg).count() >= casting_chars


def check_player_skip_quests(reg, typ):
    return AssignmentTrait.objects.filter(run_id=reg.run_id, member_id=reg.member_id, typ=typ).count() > 0


def check_casting_player(ctx: dict, reg, options: dict, typ: int, cache_membs: dict, cache_aim: dict) -> bool:
    """Check if player should be skipped in casting based on various criteria.

    This function evaluates multiple filtering criteria to determine whether
    a registered player should be excluded from casting assignments.

    Args:
        ctx: Context dictionary containing features data and configuration
        reg: Registration instance representing the player's registration
        options: Dictionary with casting filter options (tickets, memberships, pays)
        typ: Casting type identifier (0 for characters, other values for quests)
        cache_membs: Cached membership statuses keyed by member ID
        cache_aim: Cached aim membership data for additional status checks

    Returns:
        True if player should be skipped in casting, False otherwise

    Example:
        >>> should_skip = check_casting_player(ctx, registration, filters, 0, memb_cache, aim_cache)
    """
    # Filter by ticket type - skip if player's ticket not in allowed list
    if "tickets" in options and str(reg.ticket_id) not in options["tickets"]:
        return True

    # Filter by membership status when membership feature is enabled
    if "membership" in ctx["features"]:
        # Skip if member not found in membership cache
        if reg.member_id not in cache_membs:
            return True

        # Determine actual membership status, accounting for AIM membership
        status = cache_membs[reg.member_id]
        if status == "a" and reg.member_id in cache_aim:
            status = "p"  # Override status for AIM members

        # Skip if membership status not in allowed list
        if "memberships" in options and status not in options["memberships"]:
            return True

    # Filter by payment status - check current payment state
    registration_payments_status(reg)
    if "pays" in options and reg.payment_status:
        # Skip if payment status not in allowed list
        if reg.payment_status not in options["pays"]:
            return True

    # Check for existing assignments based on casting type
    if typ == 0:
        # Character casting - check if already assigned to character
        check = check_player_skip_characters(reg, ctx)
    else:
        # Quest casting - check if already assigned to quest
        check = check_player_skip_quests(reg, typ)

    # Skip if player already has assignments
    if check:
        return True

    return False


def get_casting_data(request: HttpRequest, ctx: dict, typ: int, form: "OrganizerCastingOptionsForm") -> None:
    """Retrieve and process casting data for automated character assignment algorithm.

    Collects player preferences, character choices, ticket types, membership status,
    payment status, and avoidance lists. Processes data into JSON-serialized format
    for client-side casting algorithm execution with priority weighting.

    Args:
        request: HTTP request object for association context
        ctx: Context dictionary to populate with casting data
        typ: Casting type (0 for characters, other for quest traits)
        form: Form with filtering options (tickets, membership, payment status)

    Side effects:
        - Adds JSON-serialized casting data to ctx (choices, players, preferences, etc.)
        - Loads membership and payment status caches
        - Calculates registration and payment priorities
        - Filters players based on form options
    """
    # Extract filtering options from form (tickets, membership status, payment status)
    options = form.get_data()

    # Load casting configuration (max choices, additional padding)
    casting_details(ctx, typ)

    # Initialize data structures for casting algorithm
    players = {}  # Player info with priorities
    didnt_choose = []  # Players who didn't submit preferences
    preferences = {}  # Player->Character preference mappings
    nopes = {}  # Characters players want to avoid
    chosen = {}  # Characters that have been selected by at least one player

    # Get available choices based on casting type
    if typ == 0:
        # Character casting - includes faction filtering and mirror handling
        (choices, taken, mirrors, allowed) = get_casting_choices_characters(ctx, options)
    else:
        # Quest trait casting
        get_element(ctx, typ, "quest_type", QuestType, by_number=True)
        allowed = None
        (choices, taken, mirrors) = get_casting_choices_quests(ctx)

    # Load cached membership and casting preference data
    cache_aim, cache_membs, castings = _casting_prepare(ctx, request, typ)

    # Process each registration to build player preferences
    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
    # Exclude non-participant ticket types from casting
    que = que.exclude(ticket__tier__in=[TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC])
    que = que.order_by("created").select_related("ticket", "member")
    for reg in que:
        # Skip players that don't match filter criteria (ticket, membership, payment)
        if check_casting_player(ctx, reg, options, typ, cache_membs, cache_aim):
            continue

        # Add player info with ticket priority and registration/payment dates
        _get_player_info(players, reg)

        # Extract player's character preferences from casting submissions
        pref = _get_player_preferences(allowed, castings, chosen, nopes, reg)

        # Track players who didn't submit preferences
        if len(pref) == 0:
            didnt_choose.append(reg.member_id)
        else:
            preferences[reg.member_id] = pref

    # Add random unchosen characters to resolve ties fairly
    not_chosen, not_chosen_add = _fill_not_chosen(choices, chosen, ctx, preferences, taken)

    # Load character avoidance texts (reasons players can't play certain characters)
    avoids = {}
    for el in CastingAvoid.objects.filter(run=ctx["run"], typ=typ):
        avoids[el.member_id] = el.text

    # Serialize all data to JSON for client-side casting algorithm
    ctx["num_choices"] = min(ctx["casting_max"] + not_chosen_add, len(choices))
    ctx["choices"] = json.dumps(choices)
    ctx["mirrors"] = json.dumps(mirrors)
    ctx["players"] = json.dumps(players)
    ctx["preferences"] = json.dumps(preferences)
    ctx["taken"] = json.dumps(taken)
    ctx["not_chosen"] = json.dumps(not_chosen)
    ctx["chosen"] = json.dumps(list(chosen.keys()))
    ctx["didnt_choose"] = json.dumps(didnt_choose)
    ctx["nopes"] = json.dumps(nopes)
    ctx["avoids"] = json.dumps(avoids)

    # Load priority configuration for algorithm weighting
    for key in ("reg_priority", "pay_priority"):
        ctx[key] = int(get_event_config(ctx["event"].id, f"casting_{key}", 0, ctx))


def _casting_prepare(ctx: dict, request, typ: str) -> tuple[int, dict[int, str], dict[int, list]]:
    """Prepare casting data for a specific run and type.

    Args:
        ctx: Context dictionary containing run information
        request: HTTP request object with association data
        typ: Type of casting to filter

    Returns:
        tuple: A tuple containing:
            - cache_aim: Membership fee year for the association
            - cache_membs: Dictionary mapping member IDs to their membership status
            - castings: Dictionary mapping member IDs to their list of casting objects
    """
    # Get the membership fee year for the current association
    cache_aim = get_membership_fee_year(request.assoc["id"])

    # Build cache of member statuses for the association
    cache_membs = {}
    memb_que = Membership.objects.filter(assoc_id=request.assoc["id"])
    for el in memb_que.values("member_id", "status"):
        cache_membs[el["member_id"]] = el["status"]

    # Group casting objects by member ID for the specified run and type
    castings = {}
    for el in Casting.objects.filter(run=ctx["run"], typ=typ).order_by("pref"):
        # Initialize member's casting list if not exists
        if el.member_id not in castings:
            castings[el.member_id] = []
        castings[el.member_id].append(el)

    return cache_aim, cache_membs, castings


def _get_player_info(players: dict, reg: Registration) -> None:
    """
    Update the players dictionary with registration information for a single player.

    Args:
        players (dict): Dictionary to store player information, keyed by member ID
        reg: Registration object containing member and ticket information

    Returns:
        None: Function modifies the players dictionary in-place
    """
    # Initialize basic player information with default priority
    players[reg.member_id] = {
        "name": str(reg.member),
        "prior": 1,
        "email": reg.member.email,
    }

    # Override priority if ticket has casting priority defined
    if reg.ticket:
        players[reg.member_id]["prior"] = reg.ticket.casting_priority

    # Calculate registration days (number of days from registration creation)
    players[reg.member_id]["reg_days"] = -get_time_diff_today(reg.created.date()) + 1

    # Calculate payment days (number of days from full payment, default to 1 if unpaid)
    players[reg.member_id]["pay_days"] = -get_time_diff_today(reg.payment_date) + 1 if reg.payment_date else 1


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
    pref = []

    # Check if this member has any casting choices
    if reg.member_id in castings:
        # Process each casting choice for this member
        for c in castings[reg.member_id]:
            # Skip elements not in allowed set (if filtering is enabled)
            if allowed and c.element not in allowed:
                continue

            # Add element to preferences and mark as chosen
            p = c.element
            pref.append(p)
            chosen[p] = 1

            # Track rejected preferences ("nopes") for this member
            if c.nope:
                if reg.member_id not in nopes:
                    nopes[reg.member_id] = []
                nopes[reg.member_id].append(p)

    return pref


def _fill_not_chosen(choices: dict, chosen: set, ctx: dict, preferences: dict, taken: set) -> tuple[list, int]:
    """Fill player preferences with non-chosen characters to resolve unlucky ties.

    This function adds up to `ctx["casting_add"]` non-taken characters to each
    player's preference list. Characters are shuffled randomly for each player
    to ensure fair distribution when resolving casting conflicts.

    Args:
        choices: Dictionary mapping character IDs to character data
        chosen: Set of character IDs that have already been chosen
        ctx: Context dictionary containing casting configuration (must have "casting_add" key)
        preferences: Dictionary mapping member IDs to their character preference lists
        taken: Set of character IDs that are unavailable/taken

    Returns:
        tuple: A tuple containing:
            - list: Sorted list of available character IDs that weren't chosen or taken
            - int: Number of characters actually added to each preference list
    """
    # Collect all character IDs that are available (not chosen and not taken)
    not_chosen = []
    for cid in choices.keys():
        if cid not in chosen and cid not in taken:
            not_chosen.append(cid)

    # Sort the available characters for consistent ordering
    not_chosen.sort()

    # Determine how many characters to add (limited by available characters)
    not_chosen_add = min(ctx["casting_add"], len(not_chosen))

    # Add randomly shuffled available characters to each player's preferences
    for _mid, pref in preferences.items():
        # Shuffle for each player to ensure fair random distribution
        random.shuffle(not_chosen)
        # Add the specified number of characters to this player's preferences
        for i in range(0, not_chosen_add):
            pref.append(not_chosen[i])

    return not_chosen, not_chosen_add


@login_required
def orga_casting(request: HttpRequest, s: str, typ: Optional[int] = None, tick: str = "") -> HttpResponse:
    """Handle organizational casting assignments for LARP events.

    Manages the casting assignment process for event organizers, allowing them to
    assign participants to specific casting types and roles within an event.

    Args:
        request: The HTTP request object containing user data and POST parameters
        s: Event slug identifier used to identify the specific event
        typ: Casting type identifier. If None, redirects to default type 0
        tick: Ticket identifier string for specific participant casting

    Returns:
        HttpResponse: Rendered casting template with form and casting data,
                     or redirect response after successful assignment

    Raises:
        Http404: When the submitted form is not valid
    """
    # Check user permissions for accessing casting functionality
    ctx = check_event_permission(request, s, "orga_casting")

    # Redirect to default casting type if none specified
    if typ is None:
        return redirect("orga_casting", s=ctx["run"].get_slug(), typ=0)

    # Set context variables for template rendering
    ctx["typ"] = typ
    ctx["tick"] = tick

    # Handle POST request for casting assignment
    if request.method == "POST":
        form = OrganizerCastingOptionsForm(request.POST, ctx=ctx)

        # Validate form data before processing
        if not form.is_valid():
            raise Http404("form not valid")

        # Process casting assignment if submit button was clicked
        if request.POST.get("submit"):
            assign_casting(request, ctx, typ)
            return redirect(request.path_info)
    else:
        # Initialize empty form for GET requests
        form = OrganizerCastingOptionsForm(ctx=ctx)

    # Retrieve and populate casting details for the specified type
    casting_details(ctx, typ)

    # Get casting data and populate form with current selections
    get_casting_data(request, ctx, typ, form)

    # Add form to context and render template
    ctx["form"] = form
    return render(request, "larpmanager/orga/casting.html", ctx)


@login_required
def orga_casting_toggle(request, s, typ):
    ctx = check_event_permission(request, s, "orga_casting")
    try:
        pid = request.POST["pid"]
        oid = request.POST["oid"]
        c = Casting.objects.get(run=ctx["run"], typ=typ, member_id=pid, element=oid)
        c.nope = not c.nope
        c.save()
        return JsonResponse({"res": "ok"})
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko"})
