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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.registration import registration_payments_status
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
def orga_casting_preferences(request, s, typ=0):
    ctx = check_event_permission(request, s, "orga_casting_preferences")
    casting_details(ctx, typ)
    if typ == 0:
        casting_preferences_characters(ctx)
    else:
        casting_preferences_traits(ctx, typ)

    return render(request, "larpmanager/event/casting/preferences.html", ctx)


@login_required
def orga_casting_history(request, s, typ=0):
    ctx = check_event_permission(request, s, "orga_casting_history")
    casting_details(ctx, typ)
    if typ == 0:
        casting_history_characters(ctx)
    else:
        casting_history_traits(ctx)

    return render(request, "larpmanager/event/casting/history.html", ctx)


def assign_casting(request, ctx, typ):
    """
    Handle character casting assignment for organizers.

    Args:
        request: HTTP request object with assignment data
        ctx: Context dictionary with casting information
        typ: Type of casting assignment (0 for characters, other for traits)
    """
    # TODO Assign member to mirror_inv
    mirror = "mirror" in ctx["features"]
    res = request.POST.get("res")
    if not res:
        messages.error(request, _("Results not present"))
        return
    err = ""
    for sp in res.split():
        aux = sp.split("_")
        try:
            mb = Member.objects.get(pk=aux[0].replace("p", ""))
            reg = Registration.objects.get(member=mb, run=ctx["run"], cancellation_date__isnull=True)
            eid = aux[1].replace("c", "")
            if typ == 0:
                if mirror:
                    char = Character.objects.get(pk=eid)
                    if char.mirror:
                        eid = char.mirror_id

                RegistrationCharacterRel.objects.create(character_id=eid, reg=reg)
            else:
                AssignmentTrait.objects.create(trait_id=eid, run_id=reg.run_id, member=mb, typ=typ)
        except Exception as e:
            print(e)
            err += str(e)
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
            - features: Dict of enabled features
        options: Dictionary containing:
            - factions: List of allowed faction IDs for filtering

    Returns:
        Tuple containing:
            - choices: Dict mapping character IDs to display names
            - taken: List of character IDs that are already assigned
            - mirrors: Dict mapping character IDs to their mirror character IDs
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


def get_casting_choices_quests(ctx):
    choices = {}
    taken = []
    for q in Quest.objects.filter(event=ctx["event"], typ=ctx["quest_type"]).order_by("number"):
        # gr = q.show()["name"]
        for t in Trait.objects.filter(quest=q).order_by("number"):
            if AssignmentTrait.objects.filter(trait=t, run=ctx["run"]).count() > 0:
                taken.append(t.id)
            choices[t.id] = f"{q.name} - {t.name}"
    return choices, taken, {}


def check_player_skip_characters(reg, ctx):
    # check it has a number of characters assigned less the allowed amount
    casting_chars = int(ctx["event"].get_config("casting_characters", 1))
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
        if reg.member.id not in cache_membs:
            return True

        # Determine actual membership status, accounting for AIM membership
        status = cache_membs[reg.member.id]
        if status == "a" and reg.member.id in cache_aim:
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
            didnt_choose.append(reg.member.id)
        else:
            preferences[reg.member.id] = pref

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
    ctx["reg_priority"] = int(ctx["event"].get_config("casting_reg_priority", 0))
    ctx["pay_priority"] = int(ctx["event"].get_config("casting_pay_priority", 0))


def _casting_prepare(ctx, request, typ):
    cache_aim = get_membership_fee_year(request.assoc["id"])
    cache_membs = {}
    memb_que = Membership.objects.filter(assoc_id=request.assoc["id"])
    for el in memb_que.values("member_id", "status"):
        cache_membs[el["member_id"]] = el["status"]
    castings = {}
    for el in Casting.objects.filter(run=ctx["run"], typ=typ).order_by("pref"):
        if el.member_id not in castings:
            castings[el.member_id] = []
        castings[el.member_id].append(el)
    return cache_aim, cache_membs, castings


def _get_player_info(players, reg):
    # player info
    players[reg.member.id] = {
        "name": str(reg.member),
        "prior": 1,
        "email": reg.member.email,
    }
    if reg.ticket:
        players[reg.member.id]["prior"] = reg.ticket.casting_priority
    # set registration days (number of days from registration created)
    players[reg.member.id]["reg_days"] = -get_time_diff_today(reg.created.date()) + 1
    # set payment days (number of days from full payment date, or default value 1)
    players[reg.member.id]["pay_days"] = -get_time_diff_today(reg.payment_date) + 1 if reg.payment_date else 1


def _get_player_preferences(allowed, castings, chosen, nopes, reg):
    # get player preferences
    pref = []
    if reg.member_id in castings:
        for c in castings[reg.member_id]:
            if allowed and c.element not in allowed:
                continue
            p = c.element
            pref.append(p)
            chosen[p] = 1
            if c.nope:
                if reg.member.id not in nopes:
                    nopes[reg.member.id] = []
                nopes[reg.member.id].append(p)
    return pref


def _fill_not_chosen(choices, chosen, ctx, preferences, taken):
    # adds 3 non taken characters to each player preferences to resolve unlucky ties
    not_chosen = []
    for cid in choices.keys():
        if cid not in chosen and cid not in taken:
            not_chosen.append(cid)
    not_chosen.sort()
    not_chosen_add = min(ctx["casting_add"], len(not_chosen))
    for _mid, pref in preferences.items():
        random.shuffle(not_chosen)
        for i in range(0, not_chosen_add):
            pref.append(not_chosen[i])
    return not_chosen, not_chosen_add


@login_required
def orga_casting(request, s, typ=None, tick=""):
    """Handle organizational casting assignments.

    Args:
        request: HTTP request object
        s: Event slug
        typ: Casting type identifier (defaults to 0 if None)
        tick: Ticket identifier string

    Returns:
        HttpResponse: Casting template with form and data or redirect after assignment
    """
    ctx = check_event_permission(request, s, "orga_casting")
    if typ is None:
        return redirect("orga_casting", s=ctx["run"].get_slug(), typ=0)
    ctx["typ"] = typ
    ctx["tick"] = tick
    if request.method == "POST":
        form = OrganizerCastingOptionsForm(request.POST, ctx=ctx)
        if not form.is_valid():
            raise Http404("form not valid")
        if request.POST.get("submit"):
            assign_casting(request, ctx, typ)
            return redirect(request.path_info)
    else:
        form = OrganizerCastingOptionsForm(ctx=ctx)
    casting_details(ctx, typ)
    get_casting_data(request, ctx, typ, form)
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
