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

import json
import logging
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.config import get_event_config
from larpmanager.mail.base import mail_confirm_casting
from larpmanager.models.casting import AssignmentTrait, Casting, CastingAvoid, Quest, QuestType, Trait
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.models.writing import Character, Faction, FactionType
from larpmanager.utils.core.base import get_event_context
from larpmanager.utils.core.common import get_element
from larpmanager.utils.core.exceptions import check_event_feature
from larpmanager.utils.services.event import get_event_filter_characters
from larpmanager.utils.users.registration import registration_status

if TYPE_CHECKING:
    from django.db.models import QuerySet

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
    valid_character_ids = set()

    # Process each faction and organize characters within it
    for faction in context["factions"]:
        faction_name = faction.data["name"]
        character_choices_by_faction[faction_name] = {}
        faction_names.append(faction_name)

        # Add each character from the faction to choices with display info, sorted by number
        for character in sorted(faction.chars, key=lambda c: c.number):
            character_choices_by_faction[faction_name][character.id] = character.show(context["run"])
            valid_character_ids.add(character.id)
            total_characters += 1

    # Convert faction and character data to JSON for frontend consumption
    context["factions"] = json.dumps(faction_names)
    context["choices"] = json.dumps(character_choices_by_faction)
    context["valid_element_ids"] = valid_character_ids

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
    valid_trait_ids = set()

    # Pre-fetch all assigned traits for this run
    assigned_trait_ids_set = set(AssignmentTrait.objects.filter(run=context["run"]).values_list("trait_id", flat=True))

    # Iterate through quests filtered by event, type, and visibility
    for quest in (
        Quest.objects.filter(event=context["event"], typ=typ, hide=False).order_by("number").prefetch_related("traits")
    ):
        faction_name = quest.show()["name"]
        available_traits = {}

        # Collect traits for this quest that aren't already assigned
        for trait in quest.traits.filter(hide=False).order_by("number"):
            # Skip traits that are already assigned using pre-fetched set
            if trait.id in assigned_trait_ids_set:
                continue
            available_traits[trait.id] = trait.show()
            valid_trait_ids.add(trait.id)
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
    context["valid_element_ids"] = valid_trait_ids


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
            get_event_config(
                context["event"].id, f"casting_{config_key}", default_value=default_value, context=context
            ),
        )

    # Set boolean casting preferences from event configuration
    for preference_name in ["show_pref", "history", "avoid"]:
        context["casting_" + preference_name] = get_event_config(
            context["event"].id,
            "casting_" + preference_name,
            default_value=False,
            context=context,
        )

    return context


@login_required
def casting(request: HttpRequest, event_slug: str, casting_type: int = 0) -> HttpResponse:
    """Handle user casting preferences for LARP events.

    This view manages the casting preference selection process for registered users,
    including validation of registration status and processing of preference submissions.

    Args:
        request: Django HTTP request object containing user session and POST data
        event_slug: Event slug identifier used to retrieve the specific event run
        casting_type: Casting type identifier for different casting categories (default: 0)

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
                "able to select your preferences!",
            ),
        )
        return redirect("gallery", event_slug=context["run"].get_slug())

    # Load casting details and options for the specified type
    casting_details(context, casting_type)
    logger.debug(
        "Casting context for casting_type %s: %s, features: %s",
        casting_type,
        context.get("gl_name", "Unknown"),
        list(context.get("features", {}).keys()),
    )

    # Set template path for rendering
    red = "larpmanager/event/casting/casting.html"

    # Check if user has already completed casting assignments
    _check_already_done(context, casting_type)

    # If assignments are already done, render read-only view
    if "assigned" in context:
        return render(request, red, context)

    # Load any previously saved preferences for this casting type
    _get_previous(context, request, casting_type)

    # Process POST request with new casting preferences
    if request.method == "POST":
        prefs = {}
        valid_element_ids = context.get("valid_element_ids", set())
        validation_error = None

        # Extract preference choices from form data
        for i in range(context["casting_max"]):
            k = f"choice{i}"
            if k not in request.POST:
                continue
            pref = int(request.POST[k])

            # Validate element ID is in the allowed list (not hidden, etc.)
            if pref not in valid_element_ids:
                messages.error(request, _("Invalid selection detected, please select from the available options"))
                validation_error = True
                break

            # Validate no duplicate preferences selected
            if pref in prefs.values():
                messages.warning(request, _("You have indicated more than one preferences towards the same element"))
                validation_error = True
                break
            prefs[i] = pref

        # Handle validation errors or save preferences
        if validation_error:
            return redirect("casting", event_slug=context["run"].get_slug(), casting_type=casting_type)

        # Save preferences and redirect to refresh page
        _casting_update(context, prefs, request, casting_type)
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
        casting_item.element
        for casting_item in Casting.objects.filter(run=context["run"], member=context["member"], typ=typ).order_by(
            "pref"
        )
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
        casting_avoidance = CastingAvoid.objects.get(run=context["run"], member=context["member"], typ=typ)
        context["avoid"] = casting_avoidance.text
    except ObjectDoesNotExist:
        # No avoidance preferences found, continue without setting avoid context
        pass


def _check_already_done(context: dict, assignment_type: int) -> None:
    """Check if assignment already exists and update context accordingly.

    For character assignments (type 0), checks if max characters reached and lists assigned characters.
    For trait assignments (type != 0), checks if trait already assigned and shows quest/trait info.

    Args:
        context: View context dictionary to update with assignment info
        assignment_type: 0 for character assignment, other values for trait types

    """
    # Check if character assignment already done (type 0)
    if assignment_type == 0:
        casting_chars = int(get_event_config(context["run"].event_id, "casting_characters", default_value=1))
        if context["run"].reg.rcrs.count() >= casting_chars:
            # Collect names of all assigned characters
            character_names = [
                context["chars"][character_number]["name"]
                for character_number in context["run"].reg.rcrs.values_list("character__number", flat=True)
            ]
            context["assigned"] = ", ".join(character_names)
    else:
        # Check if trait assignment already exists
        try:
            assignment_trait = AssignmentTrait.objects.get(
                run=context["run"],
                member=context["member"],
                typ=assignment_type,
            )
            # Format quest and trait names for display
            context["assigned"] = (
                f"{assignment_trait.trait.quest.show()['name']} - {assignment_trait.trait.show()['name']}"
            )
        except ObjectDoesNotExist:
            pass


def _handle_casting_avoidance(context: dict, request: Any, typ: int) -> str | None:
    """Handle casting avoidance preferences update.

    Args:
        context: Context dictionary with run and member data
        request: HTTP request object with POST data
        typ: Casting type identifier

    Returns:
        Avoidance text if provided, None otherwise
    """
    if not context.get("casting_avoid"):
        return None

    # Clear existing avoidance preferences
    CastingAvoid.objects.filter(run=context["run"], member=context["member"], typ=typ).delete()

    # Get avoidance text from POST data if provided
    avoidance_text = request.POST.get("avoid", "")

    # Create new avoidance record if text was provided
    if avoidance_text and len(avoidance_text) > 0:
        CastingAvoid.objects.create(run=context["run"], member=context["member"], typ=typ, text=avoidance_text)
        return avoidance_text

    return None


def _build_preference_names_list(context: dict, typ: int) -> list[str]:
    """Build list of preference names for email confirmation.

    Args:
        context: Context dictionary with run and member data
        typ: Casting type (0 for characters, other for traits)

    Returns:
        List of preference names as strings
    """
    preference_names_list = []
    casting_preferences = list(
        Casting.objects.filter(run=context["run"], member=context["member"], typ=typ).order_by("pref")
    )

    if not casting_preferences:
        return preference_names_list

    # Batch fetch all characters or traits
    element_ids = [cp.element for cp in casting_preferences]

    if typ == 0:
        # Character casting: batch fetch all characters
        characters_dict = {
            char.id: char for char in Character.objects.filter(pk__in=element_ids).select_related("event")
        }
        for casting_preference in casting_preferences:
            character = characters_dict.get(casting_preference.element)
            if character:
                preference_names_list.append(character.show(context["run"])["name"])
    else:
        # Trait casting: batch fetch all traits with their quests
        traits_dict = {trait.id: trait for trait in Trait.objects.filter(pk__in=element_ids).select_related("quest")}
        for casting_preference in casting_preferences:
            trait = traits_dict.get(casting_preference.element)
            if trait:
                preference_names_list.append(f"{trait.quest.show()['name']} - {trait.show()['name']}")

    return preference_names_list


def _casting_update(context: dict, prefs: dict, request: Any, typ: int) -> None:
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
    Casting.objects.filter(run=context["run"], member=context["member"], typ=typ).delete()

    # Create new casting preferences based on submitted data
    for preference_order, element_id in prefs.items():
        Casting.objects.create(
            run=context["run"],
            member=context["member"],
            typ=typ,
            element=element_id,
            pref=preference_order,
        )

    # Handle casting avoidance preferences if feature is enabled
    avoidance_text = _handle_casting_avoidance(context, request, typ)

    # Show success message to user
    messages.success(request, _("Preferences saved!"))

    # Build preference list for confirmation email
    preference_names_list = _build_preference_names_list(context, typ)

    # Send confirmation email with updated preferences
    mail_confirm_casting(context["member"], context["run"], context["gl_name"], preference_names_list, avoidance_text)


def get_casting_preferences(
    element_number: int,
    context: dict,
    casting_type: int = 0,
    casting_queryset: QuerySet | None = None,
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
    for preference_value in range(context["casting_max"] + 1):
        preference_distribution[preference_value] = 0

    # Get casting queryset if not provided
    if casting_queryset is None:
        casting_queryset = Casting.objects.filter(element=element_number, run=context["run"], typ=casting_type)
        # Filter active casts unless staff context is present
        if "staff" not in context:
            casting_queryset = casting_queryset.filter(active=True)

    # Process each casting preference
    for casting_item in casting_queryset:
        preference_value = int(casting_item.pref + 1)  # Convert preference to 1-based index
        total_preferences += 1
        preference_sum += preference_value
        # Update distribution count if preference value is valid
        if preference_value in preference_distribution:
            preference_distribution[preference_value] += 1

    # Calculate average preference or return placeholder
    average_preference = "-" if total_preferences == 0 else "%.2f" % (preference_sum * 1.0 / total_preferences)

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
    for casting_item in Casting.objects.filter(run=context["run"], typ=0, active=True):
        if casting_item.element not in castings_by_character:
            castings_by_character[casting_item.element] = []
        castings_by_character[casting_item.element].append(casting_item)

    # Process each faction and its characters
    for faction in context["factions"]:
        for character in faction.chars:
            # Get casting preferences for current character
            character_castings = []
            if character.id in castings_by_character:
                character_castings = castings_by_character[character.id]

            # Log character processing for debugging
            logger.debug("Character %s casting preferences: %s entries", character.id, len(character_castings))

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
        raise Http404 from err

    # Initialize the list to store trait preference data
    context["list"] = []

    # Pre-fetch all assigned traits for this run
    assigned_trait_ids_set = set(AssignmentTrait.objects.filter(run=context["run"]).values_list("trait_id", flat=True))

    # Iterate through all visible quests of the specified type
    for quest in (
        Quest.objects.filter(event=context["event"], typ=quest_type, hide=False)
        .order_by("number")
        .prefetch_related("traits")
    ):
        # Get the quest group name for display
        quest_group_name = quest.show()["name"]

        # Process each visible trait within the current quest
        for trait in quest.traits.filter(hide=False).order_by("number"):
            # Skip traits that already have assignments using pre-fetched set (unless in staff context)
            if "staff" not in context and trait.id in assigned_trait_ids_set:
                continue

            # Build trait preference data structure
            trait_data = {
                "group_dis": quest_group_name,
                "name_dis": trait.show()["name"],
                "pref": get_casting_preferences(trait.id, context, quest_type.number),
            }
            context["list"].append(trait_data)


@login_required
def casting_preferences(request: HttpRequest, event_slug: str, casting_type: int = 0) -> HttpResponse:
    """Display casting preferences interface for characters or traits.

    Provides a web interface for users to set their casting preferences during
    event registration. Supports both character preferences and trait-based
    preferences depending on the type parameter.

    Args:
        request: Django HTTP request object containing user session and data
        event_slug: Event slug identifier used to locate the specific event
        casting_type: Preference type selector - 0 for character preferences,
             any other value for trait-based preferences

    Returns:
        HttpResponse: Rendered casting preferences page with context data

    Raises:
        Http404: When casting preferences are disabled for the event or
                when the user is not properly registered for the event

    """
    # Get event context and verify user signup status
    context = get_event_context(request, event_slug, signup=True, include_status=True)
    casting_details(context, casting_type)

    # Check if casting preferences are enabled for this event
    if not context["casting_show_pref"]:
        msg = "Not cool, bro!"
        raise Http404(msg)

    # Build features map and check registration status
    context.update({"features_map": {context["event"].id: context["features"]}})
    registration_status(context["run"], context["member"], context)

    # Verify user has valid registration for this event
    if context["run"].reg is None:
        msg = "not registered"
        raise Http404(msg)

    # Route to appropriate preference handler based on type
    if casting_type == 0:
        # Handle character-based casting preferences
        casting_preferences_characters(context)
    else:
        # Handle trait-based preferences (requires questbuilder feature)
        check_event_feature(request, context, "questbuilder")
        casting_preferences_traits(context, casting_type)

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
    for casting_item in Casting.objects.filter(run=context["run"], typ=0).order_by("pref"):
        if casting_item.member_id not in casting_preferences_by_member:
            casting_preferences_by_member[casting_item.member_id] = []
        casting_preferences_by_member[casting_item.member_id].append(casting_item)

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
        for casting_item in casting_preferences_by_member[registration.member_id]:
            # Skip if character not in cache (deleted/invalid)
            if casting_item.element not in context["cache"]:
                continue

            character = context["cache"][casting_item.element]

            # Skip mirror characters (TODO: implement proper handling)
            if character.mirror:
                continue

            # Format character display string with number and name
            character_display = f"#{character.number} {character.name}" if character else "-----"

            # Store preference with 1-based indexing
            registration.prefs[casting_item.pref + 1] = character_display

        # Add processed registration to final list
        context["list"].append(registration)


def casting_history_traits(context: dict) -> None:
    """Process casting history and character traits for display in the casting interface.

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
    for casting_item in Casting.objects.filter(run=context["run"], typ=context["typ"]).order_by("pref"):
        if casting_item.member_id not in casting_preferences_by_member:
            casting_preferences_by_member[casting_item.member_id] = []
        casting_preferences_by_member[casting_item.member_id].append(casting_item)

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
        for casting_item in casting_preferences_by_member[registration.member_id]:
            if casting_item.element not in context["cache"]:
                continue
            # Convert 0-based preference to 1-based for display
            registration.prefs[casting_item.pref + 1] = context["cache"][casting_item.element]
        context["list"].append(registration)

    # Log processing statistics for debugging
    logger.debug(
        "Casting history context for typ %s: %s registrations processed",
        context.get("typ", 0),
        len(context.get("list", [])),
    )


@login_required
def casting_history(request: HttpRequest, event_slug: str, casting_type: int = 0) -> HttpResponse:
    """Display casting history for characters or traits.

    This view provides access to casting history data for events, allowing users
    to view historical casting decisions for either characters or traits based
    on the casting_type parameter.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event slug identifier used to locate the specific event
        casting_type: History type selector - 0 for character history, 1 for trait history.
             Defaults to 0 (character history)

    Returns:
        HttpResponse: Rendered casting history template with context data

    Raises:
        Http404: If casting history feature is not enabled for the event
        Http404: If user is not registered for the event and not staff

    """
    # Get event context and verify user signup status
    context = get_event_context(request, event_slug, signup=True, include_status=True)
    casting_details(context, casting_type)

    # Check if casting history feature is enabled for this event
    if not context["casting_history"]:
        msg = "Not cool, bro!"
        raise Http404(msg)

    # Verify user registration or staff access
    if context["run"].reg is None and "staff" not in context:
        msg = "not registered"
        raise Http404(msg)

    # Populate casting details for the specified type
    casting_details(context, casting_type)

    # Handle different history types
    if casting_type == 0:
        # Load character casting history
        casting_history_characters(context)
    else:
        # For trait history, verify questbuilder feature access
        check_event_feature(request, context, "questbuilder")
        casting_history_traits(context)

    # Render the casting history template with populated context
    return render(request, "larpmanager/event/casting/history.html", context)
