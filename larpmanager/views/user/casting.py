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
import logging
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all
from larpmanager.mail.base import mail_confirm_casting
from larpmanager.models.casting import AssignmentTrait, Casting, CastingAvoid, Quest, QuestType, Trait
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.models.writing import Character, Faction, FactionType
from larpmanager.utils.common import get_element
from larpmanager.utils.event import get_event_filter_characters, get_event_run
from larpmanager.utils.exceptions import check_event_feature
from larpmanager.utils.registration import registration_status

logger = logging.getLogger(__name__)


def casting_characters(ctx, reg):
    """Populate context with character choices available for casting based on registration.

    Args:
        ctx: Context dictionary to be populated with character choices and factions
        reg: Registration object containing ticket tier information
    """
    filter_filler = hasattr(reg, "ticket") and reg.ticket and reg.ticket.tier != TicketTier.FILLER
    filters = {"png": True, "free": True, "mirror": True, "filler": filter_filler, "nonfiller": not filter_filler}
    get_event_filter_characters(ctx, filters)
    choices = {}
    facts = []
    num = 0
    for fac in ctx["factions"]:
        k = fac.data["name"]
        choices[k] = {}
        facts.append(k)
        for char in fac.chars:
            choices[k][char.id] = char.show(ctx["run"])
            num += 1

    ctx["factions"] = json.dumps(facts)
    ctx["choices"] = json.dumps(choices)

    ctx["faction_filter"] = ctx["event"].get_elements(Faction).filter(typ=FactionType.TRASV)


def casting_quest_traits(ctx, typ):
    """Populate context with available quest traits for casting.

    Args:
        ctx: Template context dictionary to update
        typ: Quest type identifier
    """
    choices = {}
    factions = []
    num = 0
    for quest in Quest.objects.filter(event=ctx["event"], typ=typ, hide=False).order_by("number"):
        gr = quest.show()["name"]
        dc = {}
        for trait in Trait.objects.filter(quest=quest, hide=False).order_by("number"):
            if AssignmentTrait.objects.filter(trait=trait, run=ctx["run"]).count() > 0:
                continue
            dc[trait.id] = trait.show()
            num += 1
        if len(dc.keys()) == 0:
            continue
        choices[gr] = dc
        factions.append(gr)

    ctx["factions"] = json.dumps(list(factions))
    ctx["choices"] = json.dumps(choices)


def casting_details(ctx, typ):
    """Prepare casting context with configuration details and labels.

    Args:
        ctx: Template context dictionary to update
        typ: Quest type identifier (>0 for quests, 0 for characters)

    Returns:
        Updated context dictionary
    """
    get_event_cache_all(ctx)

    if typ > 0:
        data = ctx["quest_types"][typ]
        ctx["gl_name"] = data["name"]
        ctx["cl_name"] = _("Quest")
        ctx["el_name"] = _("Trait")
    else:
        ctx["gl_name"] = _("Characters")
        ctx["cl_name"] = _("Faction")
        ctx["el_name"] = _("Character")

    ctx["typ"] = typ
    ctx["casting_add"] = int(ctx["event"].get_config("casting_add", 0))
    ctx["casting_min"] = int(ctx["event"].get_config("casting_min", 5))
    ctx["casting_max"] = int(ctx["event"].get_config("casting_max", 5))
    for s in ["show_pref", "history", "avoid"]:
        ctx["casting_" + s] = ctx["event"].get_config("casting_" + s, False)
    return ctx


@login_required
def casting(request: HttpRequest, s: str, typ: int = 0) -> HttpResponse:
    """Handle user casting preferences for LARP events.

    This view manages the casting preference selection process for registered users,
    including validation of registration status and processing of preference submissions.

    Args:
        request: Django HTTP request object containing user session and POST data
        s: Event slug identifier used to retrieve the specific event run
        typ: Casting type identifier for different casting categories (default: 0)

    Returns:
        HttpResponse: Rendered casting form template or redirect response to appropriate page

    Raises:
        Http404: If event or run is not found via get_event_run
        PermissionDenied: If user lacks required casting feature permissions
    """
    # Get event context and validate user access permissions
    ctx = get_event_run(request, s, signup=True, status=True)
    check_event_feature(request, ctx, "casting")

    # Verify user has completed event registration
    if ctx["run"].reg is None:
        messages.success(request, _("You must signed up in order to select your preferences") + "!")
        return redirect("gallery", s=ctx["run"].get_slug())

    # Check if user is on waiting list (cannot set preferences)
    if ctx["run"].reg and ctx["run"].reg.ticket and ctx["run"].reg.ticket.tier == TicketTier.WAITING:
        messages.success(
            request,
            _(
                "You are on the waiting list, you must be registered with a regular ticket to be "
                "able to select your preferences!"
            ),
        )
        return redirect("gallery", s=ctx["run"].get_slug())

    # Load casting details and options for the specified type
    casting_details(ctx, typ)
    logger.debug(
        f"Casting context for typ {typ}: {ctx.get('gl_name', 'Unknown')}, features: {list(ctx.get('features', {}).keys())}"
    )

    # Set template path for rendering
    red = "larpmanager/event/casting/casting.html"

    # Check if user has already completed casting assignments
    _check_already_done(ctx, request, typ)

    # If assignments are already done, render read-only view
    if "assigned" in ctx:
        return render(request, red, ctx)

    # Load any previously saved preferences for this casting type
    _get_previous(ctx, request, typ)

    # Process POST request with new casting preferences
    if request.method == "POST":
        prefs = {}
        # Extract preference choices from form data
        for i in range(0, ctx["casting_max"]):
            k = f"choice{i}"
            if k not in request.POST:
                continue
            pref = int(request.POST[k])

            # Validate no duplicate preferences selected
            if pref in prefs.values():
                messages.warning(request, _("You have indicated several preferences towards the same element!"))
                return redirect("casting", s=ctx["run"].get_slug(), typ=typ)
            prefs[i] = pref

        # Save preferences and redirect to refresh page
        _casting_update(ctx, prefs, request, typ)
        return redirect(request.path_info)

    # Render casting form for GET requests
    return render(request, red, ctx)


def _get_previous(ctx, request, typ):
    """Retrieve previous casting choices and avoidance preferences.

    Args:
        ctx: Context dictionary to update
        request: HTTP request object
        typ: Casting type (0 for characters, other for quest types)
    """
    # compila already
    already = [
        c.element for c in Casting.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).order_by("pref")
    ]
    ctx["already"] = json.dumps(already)
    if typ == 0:
        casting_characters(ctx, ctx["run"].reg)
    else:
        check_event_feature(request, ctx, "questbuilder")
        get_element(ctx, typ, "quest_type", QuestType, by_number=True)
        casting_quest_traits(ctx, ctx["quest_type"])
    try:
        ca = CastingAvoid.objects.get(run=ctx["run"], member=request.user.member, typ=typ)
        ctx["avoid"] = ca.text
    except ObjectDoesNotExist:
        pass


def _check_already_done(ctx, request, typ):
    # check already done
    if typ == 0:
        casting_chars = int(ctx["run"].event.get_config("casting_characters", 1))
        if ctx["run"].reg.rcrs.count() >= casting_chars:
            chars = []
            for el in ctx["run"].reg.rcrs.values_list("character__number", flat=True):
                chars.append(ctx["chars"][el]["name"])
            ctx["assigned"] = ", ".join(chars)
    else:
        try:
            at = AssignmentTrait.objects.get(run=ctx["run"], member=request.user.member, typ=typ)
            ctx["assigned"] = f"{at.trait.quest.show()['name']} - {at.trait.show()['name']}"
        except ObjectDoesNotExist:
            pass


def _casting_update(ctx: dict, prefs: dict[str, int], request, typ: int) -> None:
    """Update casting preferences for a member and send confirmation email.

    This function handles the complete casting preference workflow: clearing existing
    preferences, creating new ones, managing avoidance preferences, and sending
    confirmation emails to the user.

    Args:
        ctx: Context dictionary containing run data and other casting configuration.
            Must include 'run' key with Run instance.
        prefs: Dictionary mapping preference items to their priority rankings.
            Keys are item IDs, values are preference order numbers.
        request: HTTP request object containing user data and POST parameters.
            Must have authenticated user with associated member.
        typ: Casting type identifier. 0 for character casting, 1 for trait casting.

    Returns:
        None: Function performs database operations and sends messages/emails.
    """
    # Clear all existing casting preferences for this user, run, and type
    Casting.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).delete()

    # Create new casting preferences based on submitted data
    for i, pref in prefs.items():
        Casting.objects.create(run=ctx["run"], member=request.user.member, typ=typ, element=pref, pref=i)

    # Handle casting avoidance preferences if feature is enabled
    avoid = None
    if "casting_avoid" in ctx and ctx["casting_avoid"]:
        # Clear existing avoidance preferences
        CastingAvoid.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).delete()

        # Process new avoidance text from form submission
        avoid = ""
        if "avoid" in request.POST:
            avoid = request.POST["avoid"]

        # Create new avoidance record if text was provided
        if avoid and len(avoid) > 0:
            CastingAvoid.objects.create(run=ctx["run"], member=request.user.member, typ=typ, text=avoid)

    # Show success message to user
    messages.success(request, _("Preferences saved!"))

    # Build preference list for confirmation email
    lst = []
    for c in Casting.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).order_by("pref"):
        if typ == 0:
            # Character casting: get character name
            lst.append(Character.objects.get(pk=c.element).show(ctx["run"])["name"])
        else:
            # Trait casting: get quest and trait names
            trait = Trait.objects.get(pk=c.element)
            lst.append(f"{trait.quest.show()['name']} - {trait.show()['name']}")

    # Send confirmation email with updated preferences
    # mail_confirm_casting_bkg(request.user.member.id, ctx['run'].id, ctx['gl_name'], lst)
    mail_confirm_casting(request.user.member, ctx["run"], ctx["gl_name"], lst, avoid)


def get_casting_preferences(
    number: int, ctx: dict, typ: int = 0, casts: Optional[QuerySet] = None
) -> tuple[int, str, dict[int, int]]:
    """Calculate and return casting preference statistics.

    Analyzes casting preferences for a specific character/element number within
    a run, calculating total preferences, average preference value, and
    distribution across preference levels.

    Args:
        number: Character/element number to calculate preferences for
        ctx: Context dictionary containing 'run' and 'casting_max' keys,
             optionally 'staff' for filtering
        typ: Casting type identifier (default: 0)
        casts: Optional pre-filtered casting queryset. If None, will query
               based on element, run, and typ parameters

    Returns:
        A tuple containing:
        - total_preferences (int): Total number of casting preferences found
        - average_preference (str): Average preference value formatted to 2 decimals,
                                   or "-" if no preferences exist
        - distribution_dict (dict): Mapping of preference values to their counts
    """
    tot_pref = 0
    sum_pref = 0

    # Initialize distribution dictionary with all possible preference values
    distr = {}
    for v in range(0, ctx["casting_max"] + 1):
        distr[v] = 0

    # Get casting queryset if not provided
    if casts is None:
        casts = Casting.objects.filter(element=number, run=ctx["run"], typ=typ)
        # Filter active casts unless staff context is present
        if "staff" not in ctx:
            casts = casts.filter(active=True)

    # Process each casting preference
    for cs in casts:
        v = int(cs.pref + 1)  # Convert preference to 1-based index
        tot_pref += 1
        sum_pref += v
        # Update distribution count if preference value is valid
        if v in distr:
            distr[v] += 1

    # Calculate average preference or return placeholder
    if tot_pref == 0:
        avg_pref = "-"
    else:
        avg_pref = "%.2f" % (sum_pref * 1.0 / tot_pref)

    return tot_pref, avg_pref, distr


def casting_preferences_characters(ctx):
    """Process character casting preferences with filtering.

    Args:
        ctx: Context dictionary containing run and casting data

    Side effects:
        Updates ctx with filtered character list and casting preferences
    """
    filters = {"png": True}
    if not "staff" not in ctx:
        filters["free"] = True
        filters["mirror"] = True
    get_event_filter_characters(ctx, filters)
    ctx["list"] = []

    casts = {}
    for c in Casting.objects.filter(run=ctx["run"], typ=0, active=True):
        if c.element not in casts:
            casts[c.element] = []
        casts[c.element].append(c)

    for fac in ctx["factions"]:
        for ch in fac.chars:
            cc = []
            if ch.id in casts:
                cc = casts[ch.id]
            logger.debug(f"Character {ch.id} casting preferences: {len(cc)} entries")
            el = {
                "group_dis": fac.data["name"],
                "name_dis": ch.data["name"],
                "pref": get_casting_preferences(ch.id, ctx, 0, cc),
            }
            ctx["list"].append(el)


def casting_preferences_traits(ctx, typ):
    """Load casting preferences data for traits.

    Args:
        ctx: Context dictionary to populate with trait preference data
        typ: Quest type number to filter traits

    Raises:
        Http404: If the quest type doesn't exist for the event

    Side effects:
        Populates ctx["list"] with trait preference data
    """
    try:
        qtyp = QuestType.objects.get(event=ctx["event"], number=typ)
    except ObjectDoesNotExist as err:
        raise Http404() from err

    ctx["list"] = []
    for quest in Quest.objects.filter(event=ctx["event"], typ=qtyp, hide=False).order_by("number"):
        gr = quest.show()["name"]
        for trait in Trait.objects.filter(quest=quest, hide=False).order_by("number"):
            if "staff" not in ctx and AssignmentTrait.objects.filter(trait=trait, run=ctx["run"]).count() > 0:
                continue
            el = {
                "group_dis": gr,
                "name_dis": trait.show()["name"],
                "pref": get_casting_preferences(trait.id, ctx, qtyp.number),
            }
            ctx["list"].append(el)


@login_required
def casting_preferences(request: HttpRequest, s: str, typ: int = 0) -> HttpResponse:
    """Display casting preferences interface for characters or traits.

    Provides a web interface for users to set their casting preferences during
    event registration. Supports both character preferences and trait-based
    preferences depending on the type parameter.

    Args:
        request: Django HTTP request object containing user session and data
        s: Event slug identifier used to locate the specific event
        typ: Preference type selector - 0 for character preferences,
             any other value for trait-based preferences

    Returns:
        HttpResponse: Rendered casting preferences page with context data

    Raises:
        Http404: When casting preferences are disabled for the event or
                when the user is not properly registered for the event
    """
    # Get event context and verify user signup status
    ctx = get_event_run(request, s, signup=True, status=True)
    casting_details(ctx, typ)

    # Check if casting preferences are enabled for this event
    if not ctx["casting_show_pref"]:
        raise Http404("Not cool, bro!")

    # Build features map and check registration status
    features_map = {ctx["event"].slug: ctx["features"]}
    registration_status(ctx["run"], request.user, features_map=features_map)

    # Verify user has valid registration for this event
    if ctx["run"].reg is None:
        raise Http404("not registered")

    # Route to appropriate preference handler based on type
    if typ == 0:
        # Handle character-based casting preferences
        casting_preferences_characters(ctx)
    else:
        # Handle trait-based preferences (requires questbuilder feature)
        check_event_feature(request, ctx, "questbuilder")
        casting_preferences_traits(ctx, typ)

    return render(request, "larpmanager/event/casting/preferences.html", ctx)


def casting_history_characters(ctx):
    """Build casting history list showing character preferences by registration.

    Creates a comprehensive view of all registrations with their character
    casting preferences, handling mirror characters and preference ordering.
    """
    ctx["list"] = []
    ctx["cache"] = {}
    for ch in ctx["event"].get_elements(Character).filter(hide=False).select_related("mirror"):
        ctx["cache"][ch.id] = ch

    casts = {}
    for c in Casting.objects.filter(run=ctx["run"], typ=0).order_by("pref"):
        if c.member_id not in casts:
            casts[c.member_id] = []
        casts[c.member_id].append(c)

    query = (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.NPC])
        .select_related("member")
    )

    for reg in query:
        reg.prefs = {}
        if reg.member_id not in casts:
            continue
        for c in casts[reg.member_id]:
            if c.element not in ctx["cache"]:
                continue
            ch = ctx["cache"][c.element]
            if ch.mirror:
                # TODO see how to manage it
                continue

            if ch:
                v = f"#{ch.number} {ch.name}"
            else:
                v = "-----"

            reg.prefs[c.pref + 1] = v
        ctx["list"].append(reg)


def casting_history_traits(ctx: dict) -> None:
    """
    Process casting history and character traits for display.

    Populates the context dictionary with casting data including member preferences
    and trait information for a specific run and casting type.

    Args:
        ctx: Context dictionary containing 'run', 'typ', and 'event' keys.
             Will be populated with 'list' (registrations) and 'cache' (trait names).

    Returns:
        None: Function modifies the ctx dictionary in place.
    """
    # Initialize context containers for casting data
    ctx["list"] = []
    ctx["cache"] = {}

    # Group casting preferences by member ID
    casts = {}
    for c in Casting.objects.filter(run=ctx["run"], typ=ctx["typ"]).order_by("pref"):
        if c.member_id not in casts:
            casts[c.member_id] = []
        casts[c.member_id].append(c)

    # Build trait cache with formatted names including quest information
    que = Trait.objects.filter(event=ctx["event"], hide=False)
    for el in que.select_related("quest"):
        nm = f"#{el.number} {el.name}"
        # Append quest name if trait belongs to a quest
        if el.quest:
            nm = f"{nm} ({el.quest.name})"
        ctx["cache"][el.id] = nm

    # Process registrations and attach casting preferences
    for reg in (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.NPC])
        .select_related("member")
    ):
        reg.prefs = {}
        # Skip members without casting preferences
        if reg.member_id not in casts:
            continue

        # Map casting preferences to trait names from cache
        for c in casts[reg.member_id]:
            if c.element not in ctx["cache"]:
                continue
            reg.prefs[c.pref + 1] = ctx["cache"][c.element]
        ctx["list"].append(reg)

    # Log processing statistics for debugging
    logger.debug(
        f"Casting history context for typ {ctx.get('typ', 0)}: {len(ctx.get('list', []))} registrations processed"
    )


@login_required
def casting_history(request: HttpRequest, s: str, typ: int = 0) -> HttpResponse:
    """Display casting history for characters or traits.

    This view provides access to casting history data for events, allowing users
    to view historical casting decisions for either characters or traits based
    on the typ parameter.

    Args:
        request: The HTTP request object containing user and session data
        s: Event slug identifier used to locate the specific event
        typ: History type selector - 0 for character history, 1 for trait history.
             Defaults to 0 (character history)

    Returns:
        HttpResponse: Rendered casting history template with context data

    Raises:
        Http404: If casting history feature is not enabled for the event
        Http404: If user is not registered for the event and not staff
    """
    # Get event context and verify user signup status
    ctx = get_event_run(request, s, signup=True, status=True)
    casting_details(ctx, typ)

    # Check if casting history feature is enabled for this event
    if not ctx["casting_history"]:
        raise Http404("Not cool, bro!")

    # Verify user registration or staff access
    if ctx["run"].reg is None and "staff" not in ctx:
        raise Http404("not registered")

    # Populate casting details for the specified type
    casting_details(ctx, typ)

    # Handle different history types
    if typ == 0:
        # Load character casting history
        casting_history_characters(ctx)
    else:
        # For trait history, verify questbuilder feature access
        check_event_feature(request, ctx, "questbuilder")
        casting_history_traits(ctx)

    # Render the casting history template with populated context
    return render(request, "larpmanager/event/casting/history.html", ctx)
