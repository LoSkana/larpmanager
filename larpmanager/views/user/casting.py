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


def casting_characters(ctx: dict, reg: Registration) -> None:
    """Populate context with character choices available for casting based on registration.

    This function filters available characters based on registration ticket tier,
    organizes them by faction, and prepares JSON data for frontend consumption.

    Args:
        ctx (dict): Context dictionary to be populated with character choices and factions.
                   Will be modified in-place with 'factions', 'choices', and 'faction_filter' keys.
        reg: Registration object containing ticket tier information used for filtering.

    Returns:
        None: Function modifies the ctx dictionary in-place.

    Note:
        - Filters out filler characters for non-filler ticket tiers
        - Converts faction and character data to JSON for frontend use
        - Adds faction filter for transversal faction types
    """
    # Determine if we should filter out filler characters based on ticket tier
    filter_filler = hasattr(reg, "ticket") and reg.ticket and reg.ticket.tier != TicketTier.FILLER

    # Set up character filters based on registration type
    filters = {"png": True, "free": True, "mirror": True, "filler": filter_filler, "nonfiller": not filter_filler}
    get_event_filter_characters(ctx, filters)

    # Initialize data structures for organizing characters by faction
    choices = {}
    facts = []
    num = 0

    # Process each faction and organize characters within it
    for fac in ctx["factions"]:
        k = fac.data["name"]
        choices[k] = {}
        facts.append(k)

        # Add each character from the faction to choices with display info
        for char in fac.chars:
            choices[k][char.id] = char.show(ctx["run"])
            num += 1

    # Convert faction and character data to JSON for frontend consumption
    ctx["factions"] = json.dumps(facts)
    ctx["choices"] = json.dumps(choices)

    # Add faction filter for transversal faction types
    ctx["faction_filter"] = ctx["event"].get_elements(Faction).filter(typ=FactionType.TRASV)


def casting_quest_traits(ctx: dict, typ: str) -> None:
    """Populate context with available quest traits for casting.

    Filters quests by event and type, then collects unassigned traits
    for each quest. Updates the context with faction names and trait
    choices formatted as JSON strings for frontend consumption.

    Args:
        ctx: Template context dictionary to update with faction and choice data
        typ: Quest type identifier to filter quests

    Returns:
        None: Function modifies ctx dictionary in-place
    """
    choices = {}
    factions = []
    num = 0

    # Iterate through quests filtered by event, type, and visibility
    for quest in Quest.objects.filter(event=ctx["event"], typ=typ, hide=False).order_by("number"):
        gr = quest.show()["name"]
        dc = {}

        # Collect traits for this quest that aren't already assigned
        for trait in Trait.objects.filter(quest=quest, hide=False).order_by("number"):
            # Skip traits that are already assigned to the current run
            if AssignmentTrait.objects.filter(trait=trait, run=ctx["run"]).count() > 0:
                continue
            dc[trait.id] = trait.show()
            num += 1

        # Only include quests that have available traits
        if len(dc.keys()) == 0:
            continue

        # Add quest and its traits to choices, track faction name
        choices[gr] = dc
        factions.append(gr)

    # Serialize data as JSON for frontend consumption
    ctx["factions"] = json.dumps(list(factions))
    ctx["choices"] = json.dumps(choices)


def casting_details(ctx: dict, typ: int) -> dict:
    """Prepare casting context with configuration details and labels.

    Configures the template context for casting operations by setting up
    appropriate labels and configuration values based on the casting type.

    Args:
        ctx: Template context dictionary to update with casting configuration
        typ: Quest type identifier - positive values for quests, 0 for characters

    Returns:
        Updated context dictionary with casting-specific configuration and labels

    Note:
        For typ > 0: Configures quest-related labels and data
        For typ = 0: Configures character-related labels
    """
    # Load event cache data into context
    get_event_cache_all(ctx)

    # Configure labels based on casting type (quest vs character)
    if typ > 0:
        data = ctx["quest_types"][typ]
        ctx["gl_name"] = data["name"]
        ctx["cl_name"] = _("Quest")
        ctx["el_name"] = _("Trait")
    else:
        ctx["gl_name"] = _("Characters")
        ctx["cl_name"] = _("Faction")
        ctx["el_name"] = _("Character")

    # Set type identifier and numeric casting configuration
    ctx["typ"] = typ
    ctx["casting_add"] = int(ctx["event"].get_config("casting_add", 0))
    ctx["casting_min"] = int(ctx["event"].get_config("casting_min", 5))
    ctx["casting_max"] = int(ctx["event"].get_config("casting_max", 5))

    # Set boolean casting preferences from event configuration
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


def _get_previous(ctx: dict, request: HttpRequest, typ: int) -> None:
    """Retrieve previous casting choices and avoidance preferences.

    Fetches existing casting choices for a member and populates the context
    with serialized data. Also retrieves casting avoidance preferences if they exist.

    Args:
        ctx: Context dictionary to update with casting data
        request: HTTP request object containing user information
        typ: Casting type identifier (0 for characters, other values for quest types)

    Returns:
        None: Function modifies ctx dictionary in place
    """
    # Retrieve all previous casting choices for this member, run, and type
    # ordered by preference to maintain selection order
    already = [
        c.element for c in Casting.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).order_by("pref")
    ]

    # Serialize casting choices as JSON for frontend consumption
    ctx["already"] = json.dumps(already)

    # Handle different casting types with appropriate data population
    if typ == 0:
        # For character casting, populate available characters
        casting_characters(ctx, ctx["run"].reg)
    else:
        # For quest casting, verify permissions and populate quest data
        check_event_feature(request, ctx, "questbuilder")
        get_element(ctx, typ, "quest_type", QuestType, by_number=True)
        casting_quest_traits(ctx, ctx["quest_type"])

    # Attempt to retrieve avoidance preferences for this casting type
    try:
        ca = CastingAvoid.objects.get(run=ctx["run"], member=request.user.member, typ=typ)
        ctx["avoid"] = ca.text
    except ObjectDoesNotExist:
        # No avoidance preferences found, continue without setting avoid context
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


def _casting_update(ctx: dict, prefs: dict, request: HttpRequest, typ: int) -> None:
    """Update casting preferences for a member and send confirmation email.

    This function manages casting preferences by first deleting existing preferences,
    then creating new ones based on the provided preferences dictionary. It also
    handles casting avoidance text if the feature is enabled.

    Args:
        ctx: Context dictionary containing run and other casting-related data
        prefs: Dictionary mapping preference order (int) to element IDs
        request: HTTP request object containing user and POST data
        typ: Casting type identifier (0 for character, 1 for trait)

    Returns:
        None: Function performs side effects (database updates, email sending)
    """
    # Delete all existing casting preferences for this user, run, and type
    Casting.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).delete()

    # Create new casting preferences based on the provided preferences dictionary
    for i, pref in prefs.items():
        Casting.objects.create(run=ctx["run"], member=request.user.member, typ=typ, element=pref, pref=i)

    # Handle casting avoidance feature if enabled in the context
    avoid = None
    if "casting_avoid" in ctx and ctx["casting_avoid"]:
        # Clear existing avoidance preferences
        CastingAvoid.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).delete()
        avoid = ""

        # Get avoidance text from POST data if provided
        if "avoid" in request.POST:
            avoid = request.POST["avoid"]

        # Create new avoidance record if text is provided
        if avoid and len(avoid) > 0:
            CastingAvoid.objects.create(run=ctx["run"], member=request.user.member, typ=typ, text=avoid)

    # Display success message to the user
    messages.success(request, _("Preferences saved!"))

    # Build list of preference names for email confirmation
    lst = []
    for c in Casting.objects.filter(run=ctx["run"], member=request.user.member, typ=typ).order_by("pref"):
        if typ == 0:
            # For character casting, get character name
            lst.append(Character.objects.get(pk=c.element).show(ctx["run"])["name"])
        else:
            # For trait casting, get quest and trait names
            trait = Trait.objects.get(pk=c.element)
            lst.append(f"{trait.quest.show()['name']} - {trait.show()['name']}")

    # Send confirmation email with casting preferences
    mail_confirm_casting(request.user.member, ctx["run"], ctx["gl_name"], lst, avoid)


def get_casting_preferences(
    number: int, ctx: dict, typ: int = 0, casts: Optional[QuerySet] = None
) -> tuple[int, str, dict[int, int]]:
    """Calculate and return casting preference statistics for a given element.

    Analyzes casting preferences for a specific character or element number,
    computing total preferences, average preference value, and distribution
    across all possible preference levels.

    Args:
        number: Character or element number to calculate preferences for.
        ctx: Context dictionary containing run information and casting configuration.
            Must include 'run' and 'casting_max' keys.
        typ: Casting type identifier. Defaults to 0.
        casts: Optional pre-filtered casting queryset. If None, will be fetched
            based on element, run, and typ parameters.

    Returns:
        A tuple containing:
            - Total number of preferences (int)
            - Average preference as formatted string or "-" if no preferences (str)
            - Distribution dictionary mapping preference values to counts (dict)

    Note:
        Preference values are internally adjusted by adding 1 to stored values.
        Staff context affects filtering of active castings only.
    """
    tot_pref = 0
    sum_pref = 0
    distr = {}

    # Get casting data if not provided
    if casts is None:
        casts = Casting.objects.filter(element=number, run=ctx["run"], typ=typ)
        # Filter for active castings unless staff context
        if "staff" not in ctx:
            casts = casts.filter(active=True)

    # Initialize distribution dictionary for all possible preference values
    for v in range(0, ctx["casting_max"] + 1):
        distr[v] = 0

    # Process each casting to calculate statistics
    for cs in casts:
        v = int(cs.pref + 1)  # Adjust preference value by adding 1
        tot_pref += 1
        sum_pref += v
        # Update distribution count if value is valid
        if v in distr:
            distr[v] += 1

    # Calculate average preference or return placeholder
    if tot_pref == 0:
        avg_pref = "-"
    else:
        avg_pref = "%.2f" % (sum_pref * 1.0 / tot_pref)

    return tot_pref, avg_pref, distr


def casting_preferences_characters(ctx: dict) -> None:
    """Process character casting preferences with filtering.

    Filters characters based on PNG status and staff permissions, then processes
    casting preferences for each character within their factions.

    Args:
        ctx: Context dictionary containing:
            - run: Event run object
            - casting data and filtering parameters
            - factions: List of faction objects with character data

    Returns:
        None

    Side Effects:
        Updates ctx with:
        - Filtered character list based on PNG/staff/free/mirror status
        - 'list': List of dictionaries containing character casting preferences
    """
    # Set up base filters for character selection
    filters = {"png": True}
    if not "staff" not in ctx:
        filters["free"] = True
        filters["mirror"] = True

    # Apply character filtering based on event criteria
    get_event_filter_characters(ctx, filters)
    ctx["list"] = []

    # Build casting preferences dictionary indexed by character ID
    casts = {}
    for c in Casting.objects.filter(run=ctx["run"], typ=0, active=True):
        if c.element not in casts:
            casts[c.element] = []
        casts[c.element].append(c)

    # Process each faction and its characters
    for fac in ctx["factions"]:
        for ch in fac.chars:
            # Get casting preferences for current character
            cc = []
            if ch.id in casts:
                cc = casts[ch.id]

            # Log character processing for debugging
            logger.debug(f"Character {ch.id} casting preferences: {len(cc)} entries")

            # Build character entry with faction, name, and preferences
            el = {
                "group_dis": fac.data["name"],
                "name_dis": ch.data["name"],
                "pref": get_casting_preferences(ch.id, ctx, 0, cc),
            }
            ctx["list"].append(el)


def casting_preferences_traits(ctx: dict, typ: int) -> None:
    """Load casting preferences data for traits.

    Populates the context dictionary with trait preference data filtered by quest type.
    Only includes traits that are not hidden and, if not staff context, excludes traits
    that already have assignments in the current run.

    Args:
        ctx: Context dictionary containing 'event', 'run', and optionally 'staff' keys.
             Will be populated with trait preference data in 'list' key.
        typ: Quest type number used to filter traits by their associated quest type.

    Raises:
        Http404: If the quest type doesn't exist for the event.

    Note:
        This function has side effects - it modifies the ctx dictionary by adding
        a 'list' key containing trait preference data.
    """
    # Get the quest type for the given event and type number
    try:
        qtyp = QuestType.objects.get(event=ctx["event"], number=typ)
    except ObjectDoesNotExist as err:
        raise Http404() from err

    # Initialize the list to store trait preference data
    ctx["list"] = []

    # Iterate through all visible quests of the specified type
    for quest in Quest.objects.filter(event=ctx["event"], typ=qtyp, hide=False).order_by("number"):
        # Get the quest group name for display
        gr = quest.show()["name"]

        # Process each visible trait within the current quest
        for trait in Trait.objects.filter(quest=quest, hide=False).order_by("number"):
            # Skip traits that already have assignments (unless in staff context)
            if "staff" not in ctx and AssignmentTrait.objects.filter(trait=trait, run=ctx["run"]).count() > 0:
                continue

            # Build trait preference data structure
            el = {
                "group_dis": gr,
                "name_dis": trait.show()["name"],
                "pref": get_casting_preferences(trait.id, ctx, qtyp.number),
            }
            ctx["list"].append(el)


@login_required
def casting_preferences(request: HttpRequest, s: str, typ: int = 0) -> HttpResponse:
    """Display casting preferences interface for characters or traits.

    This view handles the display of casting preferences for either characters
    or traits based on the typ parameter. It ensures the user is properly
    registered and has appropriate permissions before showing preferences.

    Args:
        request: Django HTTP request object containing user and session data
        s: Event slug identifier used to locate the specific event
        typ: Preference type indicator (0 for characters, any other value for traits)

    Returns:
        HttpResponse: Rendered casting preferences page template

    Raises:
        Http404: If casting preferences are not enabled for this event
        Http404: If user is not registered for the event run
    """
    # Get event context and validate user signup status
    ctx = get_event_run(request, s, signup=True, status=True)
    casting_details(ctx, typ)

    # Check if casting preferences are enabled for this event
    if not ctx["casting_show_pref"]:
        raise Http404("Not cool, bro!")

    # Prepare features mapping and check registration status
    features_map = {ctx["event"].slug: ctx["features"]}
    registration_status(ctx["run"], request.user, features_map=features_map)

    # Ensure user is registered for this event run
    if ctx["run"].reg is None:
        raise Http404("not registered")

    # Handle character preferences or trait preferences based on type
    if typ == 0:
        casting_preferences_characters(ctx)
    else:
        # Verify questbuilder feature is available for trait preferences
        check_event_feature(request, ctx, "questbuilder")
        casting_preferences_traits(ctx, typ)

    return render(request, "larpmanager/event/casting/preferences.html", ctx)


def casting_history_characters(ctx: dict) -> None:
    """Build casting history list showing character preferences by registration.

    Creates a comprehensive view of all registrations with their character
    casting preferences, handling mirror characters and preference ordering.
    The function populates the context with a list of registrations and their
    associated character preferences.

    Args:
        ctx: Context dictionary containing 'event' and 'run' keys. Will be
             modified to include 'list' and 'cache' keys with registration
             data and character cache respectively.

    Returns:
        None: Function modifies the ctx dictionary in place.

    Note:
        Mirror characters are currently skipped (TODO: implement proper handling).
        Only considers non-cancelled registrations excluding STAFF and NPC tiers.
    """
    # Initialize context with empty list and character cache
    ctx["list"] = []
    ctx["cache"] = {}

    # Build character cache for quick lookup, excluding hidden characters
    for ch in ctx["event"].get_elements(Character).filter(hide=False).select_related("mirror"):
        ctx["cache"][ch.id] = ch

    # Group casting preferences by member ID for efficient processing
    casts = {}
    for c in Casting.objects.filter(run=ctx["run"], typ=0).order_by("pref"):
        if c.member_id not in casts:
            casts[c.member_id] = []
        casts[c.member_id].append(c)

    # Query all valid registrations (non-cancelled, non-staff/NPC)
    query = (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.NPC])
        .select_related("member")
    )

    # Process each registration and build preference data
    for reg in query:
        reg.prefs = {}

        # Skip registrations without casting preferences
        if reg.member_id not in casts:
            continue

        # Process each casting preference for this member
        for c in casts[reg.member_id]:
            # Skip if character not in cache (deleted/invalid)
            if c.element not in ctx["cache"]:
                continue

            ch = ctx["cache"][c.element]

            # Skip mirror characters (TODO: implement proper handling)
            if ch.mirror:
                continue

            # Format character display string with number and name
            if ch:
                v = f"#{ch.number} {ch.name}"
            else:
                v = "-----"

            # Store preference with 1-based indexing
            reg.prefs[c.pref + 1] = v

        # Add processed registration to final list
        ctx["list"].append(reg)


def casting_history_traits(ctx: dict[str, any]) -> None:
    """
    Process casting history and character traits for display in the casting interface.

    This function populates the context dictionary with casting preferences and trait
    information for registrations in a specific run and casting type. It builds a
    mapping of traits and processes casting preferences for each registered member.

    Args:
        ctx: Context dictionary containing 'run', 'typ', and 'event' keys.
             Will be populated with 'list' (processed registrations) and
             'cache' (trait ID to name mapping).

    Returns:
        None: Modifies the ctx dictionary in place.

    Note:
        Only processes non-cancelled registrations excluding STAFF and NPC tiers.
        Casting preferences are numbered starting from 1 for display purposes.
    """
    # Initialize context data structures
    ctx["list"] = []
    ctx["cache"] = {}

    # Build casting preferences mapping by member ID
    casts = {}
    for c in Casting.objects.filter(run=ctx["run"], typ=ctx["typ"]).order_by("pref"):
        if c.member_id not in casts:
            casts[c.member_id] = []
        casts[c.member_id].append(c)

    # Build trait cache with formatted names including quest context
    que = Trait.objects.filter(event=ctx["event"], hide=False)
    for el in que.select_related("quest"):
        nm = f"#{el.number} {el.name}"
        # Append quest name if trait belongs to a specific quest
        if el.quest:
            nm = f"{nm} ({el.quest.name})"
        ctx["cache"][el.id] = nm

    # Process registrations and map their casting preferences
    for reg in (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.NPC])
        .select_related("member")
    ):
        reg.prefs = {}
        # Skip members without casting preferences
        if reg.member_id not in casts:
            continue

        # Map casting preferences to trait names for display
        for c in casts[reg.member_id]:
            if c.element not in ctx["cache"]:
                continue
            # Convert 0-based preference to 1-based for display
            reg.prefs[c.pref + 1] = ctx["cache"][c.element]
        ctx["list"].append(reg)

    # Log processing summary for debugging
    logger.debug(
        f"Casting history context for typ {ctx.get('typ', 0)}: {len(ctx.get('list', []))} registrations processed"
    )


@login_required
def casting_history(request: HttpRequest, s: str, typ: int = 0) -> HttpResponse:
    """Display casting history for characters or traits.

    This view shows the historical casting data for either characters or traits
    based on the typ parameter. Requires the user to be registered for the event
    and casting history to be enabled.

    Args:
        request: The HTTP request object containing user and session data
        s: Event slug identifier used to locate the specific event
        typ: History type selector - 0 for character history, 1 for trait history.
             Defaults to 0 (characters)

    Returns:
        HttpResponse: Rendered template displaying the casting history data

    Raises:
        Http404: When casting history feature is disabled for the event
        Http404: When user is not registered for the event and not staff
    """
    # Get event context and verify user registration/status
    ctx = get_event_run(request, s, signup=True, status=True)
    casting_details(ctx, typ)

    # Check if casting history feature is enabled for this event
    if not ctx["casting_history"]:
        raise Http404("Not cool, bro!")

    # Verify user registration or staff privileges
    if ctx["run"].reg is None and "staff" not in ctx:
        raise Http404("not registered")

    # Refresh casting details after validation
    casting_details(ctx, typ)

    # Route to appropriate history handler based on type
    if typ == 0:
        # Handle character casting history
        casting_history_characters(ctx)
    else:
        # Handle trait casting history (requires questbuilder feature)
        check_event_feature(request, ctx, "questbuilder")
        casting_history_traits(ctx)

    return render(request, "larpmanager/event/casting/history.html", ctx)
