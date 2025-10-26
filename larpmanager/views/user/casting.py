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
from larpmanager.cache.config import get_event_config
from larpmanager.mail.base import mail_confirm_casting
from larpmanager.models.casting import AssignmentTrait, Casting, CastingAvoid, Quest, QuestType, Trait
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.models.writing import Character, Faction, FactionType
from larpmanager.utils.base import get_event_context
from larpmanager.utils.common import get_element
from larpmanager.utils.event import get_event_filter_characters
from larpmanager.utils.exceptions import check_event_feature
from larpmanager.utils.registration import registration_status

logger = logging.getLogger(__name__)


def casting_characters(context: dict, reg: Registration) -> None:
    """Populate context with character choices available for casting based on registration.

    This function filters available characters based on registration ticket tier,
    organizes them by faction, and prepares JSON data for frontend consumption.

    Args:
        context (dict): Context dictionary to be populated with character choices and factions.
                   Will be modified in-place with 'factions', 'choices', and 'faction_filter' keys.
        reg: Registration object containing ticket tier information used for filtering.

    Returns:
        None: Function modifies the context dictionary in-place.

    Note:
        - Filters out filler characters for non-filler ticket tiers
        - Converts faction and character data to JSON for frontend use
        - Adds faction filter for transversal faction types
    """
    # Determine if we should filter out filler characters based on ticket tier
    filter_filler = hasattr(reg, "ticket") and reg.ticket and reg.ticket.tier != TicketTier.FILLER

    # Set up character filters based on registration type
    filters = {"png": True, "free": True, "mirror": True, "filler": filter_filler, "nonfiller": not filter_filler}
    get_event_filter_characters(context, filters)

    # Initialize data structures for organizing characters by faction
    character_choices_by_faction = {}
    faction_names = []
    total_characters = 0

    # Process each faction and organize characters within it
    for faction in context["factions"]:
        faction_name = faction.data["name"]
        character_choices_by_faction[faction_name] = {}
        faction_names.append(faction_name)

        # Add each character from the faction to choices with display info
        for character in faction.chars:
            character_choices_by_faction[faction_name][character.id] = character.show(context["run"])
            total_characters += 1

    # Convert faction and character data to JSON for frontend consumption
    context["factions"] = json.dumps(faction_names)
    context["choices"] = json.dumps(character_choices_by_faction)

    # Add faction filter for transversal faction types
    context["faction_filter"] = context["event"].get_elements(Faction).filter(typ=FactionType.TRASV)


def casting_quest_traits(context: dict, typ: str) -> None:
    """Populate context with available quest traits for casting.

    Filters quests by event and type, then collects unassigned traits
    for each quest. Updates the context with faction names and trait
    choices formatted as JSON strings for frontend consumption.

    Args:
        context: Template context dictionary to update with faction and choice data
        typ: Quest type identifier to filter quests

    Returns:
        None: Function modifies context dictionary in-place
    """
    trait_choices = {}
    faction_names = []
    total_traits = 0

    # Iterate through quests filtered by event, type, and visibility
    for quest in Quest.objects.filter(event=context["event"], typ=typ, hide=False).order_by("number"):
        faction_name = quest.show()["name"]
        available_traits = {}

        # Collect traits for this quest that aren't already assigned
        for trait in Trait.objects.filter(quest=quest, hide=False).order_by("number"):
            # Skip traits that are already assigned to the current run
            if AssignmentTrait.objects.filter(trait=trait, run=context["run"]).count() > 0:
                continue
            available_traits[trait.id] = trait.show()
            total_traits += 1

        # Only include quests that have available traits
        if len(available_traits.keys()) == 0:
            continue

        # Add quest and its traits to choices, track faction name
        trait_choices[faction_name] = available_traits
        faction_names.append(faction_name)

    # Serialize data as JSON for frontend consumption
    context["factions"] = json.dumps(list(faction_names))
    context["choices"] = json.dumps(trait_choices)


def casting_details(context: dict, casting_type: int) -> dict:
    """Prepare casting context with configuration details and labels.

    Configures the template context for casting operations by setting up
    appropriate labels and configuration values based on the casting type.

    Args:
        context: Template context dictionary to update with casting configuration
        casting_type: Quest type identifier - positive values for quests, 0 for characters

    Returns:
        Updated context dictionary with casting-specific configuration and labels

    Note:
        For casting_type > 0: Configures quest-related labels and data
        For casting_type = 0: Configures character-related labels
    """
    # Load event cache data into context
    get_event_cache_all(context)

    # Configure labels based on casting type (quest vs character)
    if casting_type > 0:
        quest_type_data = context["quest_types"][casting_type]
        context["gl_name"] = quest_type_data["name"]
        context["cl_name"] = _("Quest")
        context["el_name"] = _("Trait")
    else:
        context["gl_name"] = _("Characters")
        context["cl_name"] = _("Faction")
        context["el_name"] = _("Character")

    # Set type identifier and numeric casting configuration
    context["typ"] = casting_type
    for config_key, default_value in (("add", 0), ("min", 5), ("max", 5)):
        context[f"casting_{config_key}"] = int(
            get_event_config(context["event"].id, f"casting_{config_key}", default_value, context)
        )

    # Set boolean casting preferences from event configuration
    for preference_name in ["show_pref", "history", "avoid"]:
        context["casting_" + preference_name] = get_event_config(
            context["event"].id, "casting_" + preference_name, False, context
        )

    return context


@login_required
def casting(request: HttpRequest, event_slug: str, typ: int = 0) -> HttpResponse:
    """Handle user casting preferences for LARP events.

    This view manages the casting preference selection process for registered users,
    including validation of registration status and processing of preference submissions.

    Args:
        request: Django HTTP request object containing user session and POST data
        event_slug: Event slug identifier used to retrieve the specific event run
        typ: Casting type identifier for different casting categories (default: 0)

    Returns:
        HttpResponse: Rendered casting form template or redirect response to appropriate page

    Raises:
        Http404: If event or run is not found via get_event_context
        PermissionDenied: If user lacks required casting feature permissions
    """
    # Get event context and validate user access permissions
    context = get_event_context(request, event_slug, signup=True, include_status=True)
    check_event_feature(request, context, "casting")

    # Verify user has completed event registration
    if context["run"].reg is None:
        messages.success(request, _("You must signed up in order to select your preferences") + "!")
        return redirect("gallery", event_slug=context["run"].get_slug())

    # Check if user is on waiting list (cannot set preferences)
    if context["run"].reg and context["run"].reg.ticket and context["run"].reg.ticket.tier == TicketTier.WAITING:
        messages.success(
            request,
            _(
                "You are on the waiting list, you must be registered with a regular ticket to be "
                "able to select your preferences!"
            ),
        )
        return redirect("gallery", event_slug=context["run"].get_slug())

    # Load casting details and options for the specified type
    casting_details(context, typ)
    logger.debug(
        f"Casting context for typ {typ}: {context.get('gl_name', 'Unknown')}, features: {list(context.get('features', {}).keys())}"
    )

    # Set template path for rendering
    red = "larpmanager/event/casting/casting.html"

    # Check if user has already completed casting assignments
    _check_already_done(context, request, typ)

    # If assignments are already done, render read-only view
    if "assigned" in context:
        return render(request, red, context)

    # Load any previously saved preferences for this casting type
    _get_previous(context, request, typ)

    # Process POST request with new casting preferences
    if request.method == "POST":
        prefs = {}
        # Extract preference choices from form data
        for i in range(0, context["casting_max"]):
            k = f"choice{i}"
            if k not in request.POST:
                continue
            pref = int(request.POST[k])

            # Validate no duplicate preferences selected
            if pref in prefs.values():
                messages.warning(request, _("You have indicated several preferences towards the same element!"))
                return redirect("casting", event_slug=context["run"].get_slug(), typ=typ)
            prefs[i] = pref

        # Save preferences and redirect to refresh page
        _casting_update(context, prefs, request, typ)
        return redirect(request.path_info)

    # Render casting form for GET requests
    return render(request, red, context)


def _get_previous(context: dict, request: HttpRequest, typ: int) -> None:
    """Retrieve previous casting choices and avoidance preferences.

    Fetches existing casting choices for a member and populates the context
    with serialized data. Also retrieves casting avoidance preferences if they exist.

    Args:
        context: Context dictionary to update with casting data
        request: HTTP request object containing user information
        typ: Casting type identifier (0 for characters, other values for quest types)

    Returns:
        None: Function modifies context dictionary in place
    """
    # Retrieve all previous casting choices for this member, run, and type
    # ordered by preference to maintain selection order
    previous_choices = [
        casting.element
        for casting in Casting.objects.filter(run=context["run"], member=request.user.member, typ=typ).order_by("pref")
    ]

    # Serialize casting choices as JSON for frontend consumption
    context["already"] = json.dumps(previous_choices)

    # Handle different casting types with appropriate data population
    if typ == 0:
        # For character casting, populate available characters
        casting_characters(context, context["run"].reg)
    else:
        # For quest casting, verify permissions and populate quest data
        check_event_feature(request, context, "questbuilder")
        get_element(context, typ, "quest_type", QuestType, by_number=True)
        casting_quest_traits(context, context["quest_type"])

    # Attempt to retrieve avoidance preferences for this casting type
    try:
        casting_avoidance = CastingAvoid.objects.get(run=context["run"], member=request.user.member, typ=typ)
        context["avoid"] = casting_avoidance.text
    except ObjectDoesNotExist:
        # No avoidance preferences found, continue without setting avoid context
        pass


def _check_already_done(context, request, assignment_type):
    # check already done
    if assignment_type == 0:
        casting_chars = int(get_event_config(context["run"].event_id, "casting_characters", 1))
        if context["run"].reg.rcrs.count() >= casting_chars:
            character_names = []
            for character_number in context["run"].reg.rcrs.values_list("character__number", flat=True):
                character_names.append(context["chars"][character_number]["name"])
            context["assigned"] = ", ".join(character_names)
    else:
        try:
            assignment_trait = AssignmentTrait.objects.get(
                run=context["run"], member=request.user.member, typ=assignment_type
            )
            context["assigned"] = (
                f"{assignment_trait.trait.quest.show()['name']} - {assignment_trait.trait.show()['name']}"
            )
        except ObjectDoesNotExist:
            pass


def _casting_update(context: dict, prefs: dict[str, int], request, typ: int) -> None:
    """Update casting preferences for a member and send confirmation email.

    This function handles the complete casting preference workflow: clearing existing
    preferences, creating new ones, managing avoidance preferences, and sending
    confirmation emails to the user.

    Args:
        context: Context dictionary containing run data and other casting configuration.
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
    Casting.objects.filter(run=context["run"], member=request.user.member, typ=typ).delete()

    # Create new casting preferences based on submitted data
    for preference_order, element_id in prefs.items():
        Casting.objects.create(
            run=context["run"], member=request.user.member, typ=typ, element=element_id, pref=preference_order
        )

    # Handle casting avoidance preferences if feature is enabled
    avoidance_text = None
    if "casting_avoid" in context and context["casting_avoid"]:
        # Clear existing avoidance preferences
        CastingAvoid.objects.filter(run=context["run"], member=request.user.member, typ=typ).delete()

        # Process new avoidance text from form submission
        avoidance_text = ""

        # Get avoidance text from POST data if provided
        if "avoid" in request.POST:
            avoidance_text = request.POST["avoid"]

        # Create new avoidance record if text was provided
        if avoidance_text and len(avoidance_text) > 0:
            CastingAvoid.objects.create(run=context["run"], member=request.user.member, typ=typ, text=avoidance_text)

    # Show success message to user
    messages.success(request, _("Preferences saved!"))

    # Build preference list for confirmation email
    preference_names_list = []
    for casting_preference in Casting.objects.filter(run=context["run"], member=request.user.member, typ=typ).order_by(
        "pref"
    ):
        if typ == 0:
            # Character casting: get character name
            preference_names_list.append(
                Character.objects.get(pk=casting_preference.element).show(context["run"])["name"]
            )
        else:
            # Trait casting: get quest and trait names
            trait = Trait.objects.get(pk=casting_preference.element)
            preference_names_list.append(f"{trait.quest.show()['name']} - {trait.show()['name']}")

    # Send confirmation email with updated preferences
    # mail_confirm_casting_bkg(request.user.member.id, context['run'].id, context['gl_name'], preference_names_list)
    mail_confirm_casting(request.user.member, context["run"], context["gl_name"], preference_names_list, avoidance_text)


def get_casting_preferences(
    element_number: int, context: dict, casting_type: int = 0, casting_queryset: Optional[QuerySet] = None
) -> tuple[int, str, dict[int, int]]:
    """Calculate and return casting preference statistics.

    Analyzes casting preferences for a specific character/element number within
    a run, calculating total preferences, average preference value, and
    distribution across preference levels.

    Args:
        element_number: Character/element number to calculate preferences for
        context: Context dictionary containing 'run' and 'casting_max' keys,
             optionally 'staff' for filtering
        casting_type: Casting type identifier (default: 0)
        casting_queryset: Optional pre-filtered casting queryset. If None, will query
               based on element, run, and casting_type parameters

    Returns:
        A tuple containing:
        - total_preferences (int): Total number of casting preferences found
        - average_preference (str): Average preference value formatted to 2 decimals,
                                   or "-" if no preferences exist
        - preference_distribution (dict): Mapping of preference values to their counts
    """
    total_preferences = 0
    preference_sum = 0

    # Initialize distribution dictionary with all possible preference values
    preference_distribution = {}
    for preference_value in range(0, context["casting_max"] + 1):
        preference_distribution[preference_value] = 0

    # Get casting queryset if not provided
    if casting_queryset is None:
        casting_queryset = Casting.objects.filter(element=element_number, run=context["run"], typ=casting_type)
        # Filter active casts unless staff context is present
        if "staff" not in context:
            casting_queryset = casting_queryset.filter(active=True)

    # Process each casting preference
    for casting in casting_queryset:
        preference_value = int(casting.pref + 1)  # Convert preference to 1-based index
        total_preferences += 1
        preference_sum += preference_value
        # Update distribution count if preference value is valid
        if preference_value in preference_distribution:
            preference_distribution[preference_value] += 1

    # Calculate average preference or return placeholder
    if total_preferences == 0:
        average_preference = "-"
    else:
        average_preference = "%.2f" % (preference_sum * 1.0 / total_preferences)

    return total_preferences, average_preference, preference_distribution


def casting_preferences_characters(context: dict) -> None:
    """Process character casting preferences with filtering.

    Filters characters based on PNG status and staff permissions, then processes
    casting preferences for each character within their factions.

    Args:
        context: Context dictionary containing:
            - run: Event run object
            - casting data and filtering parameters
            - factions: List of faction objects with character data

    Returns:
        None

    Side Effects:
        Updates context with:
        - Filtered character list based on PNG/staff/free/mirror status
        - 'list': List of dictionaries containing character casting preferences
    """
    # Set up base filters for character selection
    filters = {"png": True}
    if not "staff" not in context:
        filters["free"] = True
        filters["mirror"] = True

    # Apply character filtering based on event criteria
    get_event_filter_characters(context, filters)
    context["list"] = []

    # Build casting preferences dictionary indexed by character ID
    castings_by_character = {}
    for casting in Casting.objects.filter(run=context["run"], typ=0, active=True):
        if casting.element not in castings_by_character:
            castings_by_character[casting.element] = []
        castings_by_character[casting.element].append(casting)

    # Process each faction and its characters
    for faction in context["factions"]:
        for character in faction.chars:
            # Get casting preferences for current character
            character_castings = []
            if character.id in castings_by_character:
                character_castings = castings_by_character[character.id]

            # Log character processing for debugging
            logger.debug(f"Character {character.id} casting preferences: {len(character_castings)} entries")

            # Build character entry with faction, name, and preferences
            character_entry = {
                "group_dis": faction.data["name"],
                "name_dis": character.data["name"],
                "pref": get_casting_preferences(character.id, context, 0, character_castings),
            }
            context["list"].append(character_entry)


def casting_preferences_traits(context: dict, quest_type_number: int) -> None:
    """Load casting preferences data for traits.

    Populates the context dictionary with trait preference data filtered by quest type.
    Only includes traits that are not hidden and, if not staff context, excludes traits
    that already have assignments in the current run.

    Args:
        context: Context dictionary containing 'event', 'run', and optionally 'staff' keys.
             Will be populated with trait preference data in 'list' key.
        quest_type_number: Quest type number used to filter traits by their associated quest type.

    Raises:
        Http404: If the quest type doesn't exist for the event.

    Note:
        This function has side effects - it modifies the context dictionary by adding
        a 'list' key containing trait preference data.
    """
    # Get the quest type for the given event and type number
    try:
        quest_type = QuestType.objects.get(event=context["event"], number=quest_type_number)
    except ObjectDoesNotExist as err:
        raise Http404() from err

    # Initialize the list to store trait preference data
    context["list"] = []

    # Iterate through all visible quests of the specified type
    for quest in Quest.objects.filter(event=context["event"], typ=quest_type, hide=False).order_by("number"):
        # Get the quest group name for display
        quest_group_name = quest.show()["name"]

        # Process each visible trait within the current quest
        for trait in Trait.objects.filter(quest=quest, hide=False).order_by("number"):
            # Skip traits that already have assignments (unless in staff context)
            if "staff" not in context and AssignmentTrait.objects.filter(trait=trait, run=context["run"]).count() > 0:
                continue

            # Build trait preference data structure
            trait_data = {
                "group_dis": quest_group_name,
                "name_dis": trait.show()["name"],
                "pref": get_casting_preferences(trait.id, context, quest_type.number),
            }
            context["list"].append(trait_data)


@login_required
def casting_preferences(request: HttpRequest, event_slug: str, typ: int = 0) -> HttpResponse:
    """Display casting preferences interface for characters or traits.

    Provides a web interface for users to set their casting preferences during
    event registration. Supports both character preferences and trait-based
    preferences depending on the type parameter.

    Args:
        request: Django HTTP request object containing user session and data
        event_slug: Event slug identifier used to locate the specific event
        typ: Preference type selector - 0 for character preferences,
             any other value for trait-based preferences

    Returns:
        HttpResponse: Rendered casting preferences page with context data

    Raises:
        Http404: When casting preferences are disabled for the event or
                when the user is not properly registered for the event
    """
    # Get event context and verify user signup status
    context = get_event_context(request, event_slug, signup=True, include_status=True)
    casting_details(context, typ)

    # Check if casting preferences are enabled for this event
    if not context["casting_show_pref"]:
        raise Http404("Not cool, bro!")

    # Build features map and check registration status
    ctx_reg = {"features_map": {context["event"].id: context["features"]}}
    registration_status(context["run"], request.user, ctx_reg)

    # Verify user has valid registration for this event
    if context["run"].reg is None:
        raise Http404("not registered")

    # Route to appropriate preference handler based on type
    if typ == 0:
        # Handle character-based casting preferences
        casting_preferences_characters(context)
    else:
        # Handle trait-based preferences (requires questbuilder feature)
        check_event_feature(request, context, "questbuilder")
        casting_preferences_traits(context, typ)

    return render(request, "larpmanager/event/casting/preferences.html", context)


def casting_history_characters(context: dict) -> None:
    """Build casting history list showing character preferences by registration.

    Creates a comprehensive view of all registrations with their character
    casting preferences, handling mirror characters and preference ordering.
    The function populates the context with a list of registrations and their
    associated character preferences.

    Args:
        context: Context dictionary containing 'event' and 'run' keys. Will be
             modified to include 'list' and 'cache' keys with registration
             data and character cache respectively.

    Returns:
        None: Function modifies the context dictionary in place.

    Note:
        Mirror characters are currently skipped (TODO: implement proper handling).
        Only considers non-cancelled registrations excluding STAFF and NPC tiers.
    """
    # Initialize context with empty list and character cache
    context["list"] = []
    context["cache"] = {}

    # Build character cache for quick lookup, excluding hidden characters
    for character in context["event"].get_elements(Character).filter(hide=False).select_related("mirror"):
        context["cache"][character.id] = character

    # Group casting preferences by member ID for efficient processing
    casting_preferences_by_member = {}
    for casting in Casting.objects.filter(run=context["run"], typ=0).order_by("pref"):
        if casting.member_id not in casting_preferences_by_member:
            casting_preferences_by_member[casting.member_id] = []
        casting_preferences_by_member[casting.member_id].append(casting)

    # Query all valid registrations (non-cancelled, non-staff/NPC)
    registration_query = (
        Registration.objects.filter(run=context["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.NPC])
        .select_related("member")
    )

    # Process each registration and build preference data
    for registration in registration_query:
        registration.prefs = {}

        # Skip registrations without casting preferences
        if registration.member_id not in casting_preferences_by_member:
            continue

        # Process each casting preference for this member
        for casting in casting_preferences_by_member[registration.member_id]:
            # Skip if character not in cache (deleted/invalid)
            if casting.element not in context["cache"]:
                continue

            character = context["cache"][casting.element]

            # Skip mirror characters (TODO: implement proper handling)
            if character.mirror:
                continue

            # Format character display string with number and name
            if character:
                character_display = f"#{character.number} {character.name}"
            else:
                character_display = "-----"

            # Store preference with 1-based indexing
            registration.prefs[casting.pref + 1] = character_display

        # Add processed registration to final list
        context["list"].append(registration)


def casting_history_traits(context: dict) -> None:
    """
    Process casting history and character traits for display in the casting interface.

    This function populates the context dictionary with casting preferences and trait
    information for registrations in a specific run and casting type. It builds a
    mapping of traits and processes casting preferences for each registered member.

    Populates the context dictionary with casting data including member preferences
    and trait information for a specific run and casting type.

    Args:
        context: Context dictionary containing 'run', 'typ', and 'event' keys.
             Will be populated with 'list' (registrations) and 'cache' (trait names).

    Returns:
        None: Function modifies the context dictionary in place.
    """
    # Initialize context containers for casting data
    context["list"] = []
    context["cache"] = {}

    # Group casting preferences by member ID
    casting_preferences_by_member = {}
    for casting in Casting.objects.filter(run=context["run"], typ=context["typ"]).order_by("pref"):
        if casting.member_id not in casting_preferences_by_member:
            casting_preferences_by_member[casting.member_id] = []
        casting_preferences_by_member[casting.member_id].append(casting)

    # Build trait cache with formatted names including quest information
    traits_query = Trait.objects.filter(event=context["event"], hide=False)
    for trait in traits_query.select_related("quest"):
        trait_name = f"#{trait.number} {trait.name}"
        # Append quest name if trait belongs to a quest
        if trait.quest:
            trait_name = f"{trait_name} ({trait.quest.name})"
        context["cache"][trait.id] = trait_name

    # Process registrations and attach casting preferences
    for registration in (
        Registration.objects.filter(run=context["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.NPC])
        .select_related("member")
    ):
        registration.prefs = {}
        # Skip members without casting preferences
        if registration.member_id not in casting_preferences_by_member:
            continue

        # Map casting preferences to trait names from cache
        for casting in casting_preferences_by_member[registration.member_id]:
            if casting.element not in context["cache"]:
                continue
            # Convert 0-based preference to 1-based for display
            registration.prefs[casting.pref + 1] = context["cache"][casting.element]
        context["list"].append(registration)

    # Log processing statistics for debugging
    logger.debug(
        f"Casting history context for typ {context.get('typ', 0)}: {len(context.get('list', []))} registrations processed"
    )


@login_required
def casting_history(request: HttpRequest, event_slug: str, typ: int = 0) -> HttpResponse:
    """Display casting history for characters or traits.

    This view provides access to casting history data for events, allowing users
    to view historical casting decisions for either characters or traits based
    on the typ parameter.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event slug identifier used to locate the specific event
        typ: History type selector - 0 for character history, 1 for trait history.
             Defaults to 0 (character history)

    Returns:
        HttpResponse: Rendered casting history template with context data

    Raises:
        Http404: If casting history feature is not enabled for the event
        Http404: If user is not registered for the event and not staff
    """
    # Get event context and verify user signup status
    context = get_event_context(request, event_slug, signup=True, include_status=True)
    casting_details(context, typ)

    # Check if casting history feature is enabled for this event
    if not context["casting_history"]:
        raise Http404("Not cool, bro!")

    # Verify user registration or staff access
    if context["run"].reg is None and "staff" not in context:
        raise Http404("not registered")

    # Populate casting details for the specified type
    casting_details(context, typ)

    # Handle different history types
    if typ == 0:
        # Load character casting history
        casting_history_characters(context)
    else:
        # For trait history, verify questbuilder feature access
        check_event_feature(request, context, "questbuilder")
        casting_history_traits(context)

    # Render the casting history template with populated context
    return render(request, "larpmanager/event/casting/history.html", context)
