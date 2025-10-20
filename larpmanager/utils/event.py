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
from typing import Any, Optional

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch, Q
from django.http import Http404, HttpRequest
from django.urls import reverse
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.button import event_button_key
from larpmanager.cache.feature import clear_event_features_cache, get_event_features
from larpmanager.cache.fields import clear_event_fields_cache, get_event_fields_cache
from larpmanager.cache.permission import get_event_permission_feature
from larpmanager.cache.role import get_event_roles, has_event_permission
from larpmanager.cache.run import get_cache_config_run, get_cache_run
from larpmanager.models.access import EventRole, get_event_organizers
from larpmanager.models.association import Association
from larpmanager.models.event import Event, EventConfig, EventText, Run
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    QuestionVisibility,
    RegistrationQuestion,
    RegistrationQuestionType,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, Faction, FactionType
from larpmanager.utils.base import def_user_ctx, get_index_permissions
from larpmanager.utils.common import copy_class
from larpmanager.utils.exceptions import FeatureError, PermissionError, UnknowRunError, check_event_feature
from larpmanager.utils.registration import check_signup, registration_status


def get_event(request: HttpRequest, slug: str, number: Optional[int] = None) -> dict[str, Any]:
    """Get event context from slug and number.

    Retrieves event context information including run details, event data, and
    associated features. Handles association validation and TinyMCE configuration.

    Args:
        request: Django HTTP request object containing user context, or None
        slug: Event slug identifier used to locate the event
        number: Optional run number to append to slug for specific event runs

    Returns:
        Dictionary containing event context with the following keys:
            - run: Event run object
            - event: Event object
            - features: Dictionary of event features
            - a_id: Association ID
            - show_available_chars: Localized string for UI display

    Raises:
        Http404: If event doesn't exist or belongs to wrong association

    Note:
        Modifies global TinyMCE configuration if 'paste_text' feature is enabled.
    """
    # Initialize context from user request or empty dict
    if request:
        ctx = def_user_ctx(request)
    else:
        ctx = {}

    try:
        # Construct full slug with run number if provided
        if number:
            slug += f"-{number}"

        # Retrieve run object and populate context
        get_run(ctx, slug)

        # Validate association ownership or set association ID
        if "a_id" in ctx:
            if ctx["event"].assoc_id != ctx["a_id"]:
                raise Http404("wrong assoc")
        else:
            ctx["a_id"] = ctx["event"].assoc_id

        # Load event-specific features
        ctx["features"] = get_event_features(ctx["event"].id)

        # Configure TinyMCE paste behavior based on features
        if "paste_text" in ctx["features"]:
            conf_settings.TINYMCE_DEFAULT_CONFIG["paste_as_text"] = True

        # Add localized UI text for character display
        ctx["show_available_chars"] = _("Show available characters")

        return ctx
    except ObjectDoesNotExist as err:
        raise Http404("Event does not exist") from err


def get_event_run(request, s: str, signup: bool = False, slug: str | None = None, status: bool = False) -> dict:
    """Get comprehensive event run context with permissions and features.

    Retrieves event context and enhances it with user permissions, feature access,
    and registration status based on the provided parameters.

    Args:
        request: Django HTTP request object containing user and session data
        s: Event slug identifier for the target event
        signup: Whether to check and validate signup eligibility for the user
        slug: Optional feature slug to verify user access permissions
        status: Whether to include detailed registration status information

    Returns:
        Complete event context dictionary containing:
            - Event and run objects
            - User permissions and roles
            - Feature access flags
            - Registration status (if requested)
            - Association configuration
            - Staff permissions and sidebar state

    Raises:
        Http404: If event is not found or user lacks required permissions
        PermissionDenied: If user cannot access requested features
    """
    # Get base event context with run information
    ctx = get_event(request, s)

    # Validate user signup eligibility if requested
    if signup:
        check_signup(request, ctx)

    # Verify feature access permissions for specific functionality
    if slug:
        check_event_feature(request, ctx, slug)

    # Add registration status details to context
    if status:
        registration_status(ctx["run"], request.user)

    # Configure user permissions and sidebar for authorized users
    if has_event_permission(request, ctx, s):
        get_index_event_permissions(ctx, request, s)
        ctx["is_sidebar_open"] = request.session.get("is_sidebar_open", True)

    # Set association slug from request or event object
    if hasattr(request, "assoc"):
        ctx["assoc_slug"] = request.assoc["slug"]
    else:
        ctx["assoc_slug"] = ctx["event"].assoc.slug

    # Configure staff permissions for character management access
    if has_event_permission(request, ctx, s, "orga_characters"):
        ctx["staff"] = "1"
        ctx["skip"] = "1"

    # Finalize run context preparation and return complete context
    prepare_run(ctx)

    return ctx


def prepare_run(ctx: dict) -> None:
    """Prepare run context with visibility and field configurations.

    This function configures the context for a LARP event run by setting up
    visibility controls and writing field configurations based on user permissions
    and event settings.

    Args:
        ctx: Event context dictionary containing 'run', 'event', and optionally
            'staff' and 'features' keys. Modified in place.

    Returns:
        None: Function modifies ctx dictionary in place.

    Side Effects:
        - Updates ctx with run configuration from cache
        - Sets visibility flags for writing elements when user has staff access
        - Configures additional feature visibility based on available features
        - Adds writing fields configuration to context
    """
    # Get cached run configuration for the current run
    config_run = get_cache_config_run(ctx["run"])

    # Check if user has staff access or writing field visibility is disabled
    if "staff" in ctx or not ctx["event"].get_config("writing_field_visibility", False):
        # Enable full visibility for staff users
        ctx["show_all"] = "1"

        # Configure visibility for main writing elements (character, faction, quest, trait)
        for el in ["character", "faction", "quest", "trait"]:
            config_name = f"show_{el}"
            if config_name not in config_run:
                config_run[config_name] = {}
            # Show all fields (name, teaser, text) for each element
            config_run[config_name].update({"name": 1, "teaser": 1, "text": 1})

        # Configure visibility for additional features if they exist
        for el in ["plot", "relationships", "speedlarp", "prologue", "workshop", "print_pdf"]:
            config_name = "show_addit"
            if config_name not in config_run:
                config_run[config_name] = {}
            # Only show feature if it's available in the current context
            if el in ctx["features"]:
                config_run[config_name][el] = True

    # Update context with the configured run settings
    ctx.update(config_run)

    # Add writing fields configuration to the context
    ctx["writing_fields"] = get_event_fields_cache(ctx["event"].id)


def get_run(ctx: dict, s: str) -> None:
    """Load run and event data from cache and database.

    Retrieves run information using the provided slug and association ID,
    then updates the context dictionary with run and event objects.
    Uses select_related and defer optimizations for performance.

    Args:
        ctx: Context dictionary to update with run and event data.
        s: Run slug identifier used to locate the specific run.

    Raises:
        UnknowRunError: If run cannot be found or any database error occurs.

    Note:
        This function modifies the ctx dictionary in-place by adding
        'run' and 'event' keys.
    """
    try:
        # Get cached run ID using association ID and slug
        res = get_cache_run(ctx["a_id"], s)

        # Build optimized query with select_related for event
        que = Run.objects.select_related("event")

        # Define fields to defer for performance optimization
        fields = [
            "search",
            "balance",
            "event__tagline",
            "event__where",
            "event__authors",
            "event__description",
            "event__genre",
            "event__cover",
            "event__carousel_img",
            "event__carousel_text",
            "event__features",
            "event__background",
            "event__font",
            "event__pri_rgb",
            "event__sec_rgb",
            "event__ter_rgb",
        ]

        # Apply deferral and fetch the run object
        que = que.defer(*fields)
        ctx["run"] = que.get(pk=res)

        # Extract related event object for context
        ctx["event"] = ctx["run"].event
    except Exception as err:
        raise UnknowRunError() from err


def get_character_filter(ch, regs: dict, filters: list) -> bool:
    """Check if character should be included based on filter criteria.

    Args:
        ch: Character instance to check
        regs: Mapping of character IDs to registrations
        filters: Filter criteria ('free', 'mirror', etc.)

    Returns:
        True if character passes all filters, False otherwise
    """
    # Check if character is free (not registered)
    if "free" in filters:
        if ch.id in regs:
            return False

    # Check if character's mirror is free (not registered)
    if "mirror" in filters and ch.mirror_id:
        if ch.mirror_id in regs:
            return False

    return True


def get_event_filter_characters(ctx: dict, filters: list) -> None:
    """Get filtered characters organized by factions for event display.

    Retrieves characters from an event's registrations and organizes them by
    factions based on filtering criteria. Updates the context with filtered
    faction and character data for display purposes.

    Args:
        ctx: Event context dictionary containing 'run', 'event', 'features',
             and 'show_faction' keys. Will be updated with 'factions' list.
        filters: List of character filter criteria to apply when selecting
                characters for display.

    Returns:
        None: Function modifies ctx in-place by adding 'factions' key.

    Side Effects:
        - Updates ctx['factions'] with list of Faction objects
        - Each faction contains filtered characters with registration data
        - Characters get additional 'reg', 'member', and 'data' attributes
    """
    ctx["factions"] = []

    # Build registration lookup dictionary for active registrations
    regs = {}
    for el in RegistrationCharacterRel.objects.filter(
        reg__run=ctx["run"], reg__cancellation_date__isnull=True
    ).select_related("reg", "reg__member"):
        regs[el.character_id] = el.reg

    # Build character lookup dictionary with registration data
    chars = {}
    for c in ctx["event"].get_elements(Character).filter(hide=False):
        if c.id in regs:
            c.reg = regs[c.id]
            c.member = regs[c.id].member
        chars[c.id] = c

    # Organize characters by factions if faction feature is enabled
    if "faction" in ctx["features"] and ctx["show_faction"]:
        # Get primary factions ordered by their display order
        que = ctx["event"].get_elements(Faction).filter(typ=FactionType.PRIM).order_by("order")
        prefetch = Prefetch(
            "characters",
            queryset=Character.objects.filter(hide=False).order_by("number"),
        )

        # Process each faction and filter its characters
        for f in que.prefetch_related(prefetch):
            f.data = f.show_red()
            f.chars = []

            # Filter characters within this faction
            for ch in f.characters.all():
                if ch.hide:
                    continue
                if not get_character_filter(ch, regs, filters):
                    continue
                ch.data = ch.show_red()
                f.chars.append(ch)

            # Only include factions that have visible characters
            if len(f.chars) == 0:
                continue
            ctx["factions"].append(f)
    else:
        # Create single "all" faction when faction feature is disabled
        f = Faction()
        f.number = 0
        f.name = "all"
        f.data = f.show_red()
        f.chars = []

        # Add all filtered characters to the single faction
        for _ch_id, ch in chars.items():
            if not get_character_filter(ch, regs, filters):
                continue
            ch.data = ch.show_red()
            f.chars.append(ch)
        ctx["factions"].append(f)


def has_access_character(request: HttpRequest, ctx: dict) -> bool:
    """Check if user has access to view/edit a specific character.

    This function determines whether the current user has permission to access
    a character based on three criteria: organizer permissions, character
    ownership, or being assigned as the character's player.

    Args:
        request: Django HTTP request object containing user information
        ctx (dict): Context dictionary containing character and event data.
                   Expected keys: 'char' (with 'owner_id', 'player_id'),
                   'event' (with 'slug' attribute)

    Returns:
        bool: True if user has access (organizer, owner, or player), False otherwise
    """
    # Check if user has organizer permissions for character management
    if has_event_permission(request, ctx, ctx["event"].slug, "orga_characters"):
        return True

    # Get the current user's member ID for ownership/player checks
    member_id = request.user.member.id

    # Check if user is the character owner
    if "owner_id" in ctx["char"] and ctx["char"]["owner_id"] == member_id:
        return True

    # Check if user is assigned as the character's player
    if "player_id" in ctx["char"] and ctx["char"]["player_id"] == member_id:
        return True

    # No access permissions found
    return False


def check_event_permission(request: HttpRequest, s: str, perm: str | list[str] | None = None) -> dict:
    """Check event permissions and prepare management context.

    This function validates user permissions for event management operations and
    prepares the necessary context for rendering management pages.

    Args:
        request: Django HTTP request object containing user and session data
        s: Event slug identifier for the target event
        perm: Required permission(s) - can be a single permission string,
              a list of permissions, or None for basic access

    Returns:
        Dictionary containing event context with management permissions including:
        - Event and run objects
        - Available features
        - Tutorial configuration
        - Config URL if applicable
        - Management flags

    Raises:
        PermissionError: If user lacks required permissions for the event
        FeatureError: If required feature is not enabled for the event
    """
    # Get basic event context and run information
    ctx = get_event_run(request, s)

    # Verify user has the required permissions for this event
    if not has_event_permission(request, ctx, s, perm):
        raise PermissionError()

    # Process permission-specific features and configuration
    if perm:
        # Handle both single permission and list of permissions
        if isinstance(perm, list):
            perm = perm[0]

        # Extract feature, tutorial, and config data for this permission
        (feature, tutorial, config) = get_event_permission_feature(perm)

        # Set tutorial context if not already present
        if "tutorial" not in ctx:
            ctx["tutorial"] = tutorial

        # Add config URL if user has config permissions and config exists
        if config and has_event_permission(request, ctx, s, "orga_config"):
            ctx["config"] = reverse("orga_config", args=[ctx["run"].get_slug(), config])

        # Verify required feature is enabled for this event
        if feature != "def" and feature not in ctx["features"]:
            raise FeatureError(path=request.path, feature=feature, run=ctx["run"].id)

    # Load additional event permissions and set management flags
    get_index_event_permissions(ctx, request, s)
    ctx["orga_page"] = 1
    ctx["manage"] = 1

    return ctx


def get_index_event_permissions(ctx: dict, request: HttpRequest, slug: str, check: bool = True) -> None:
    """Load event permissions and roles for management interface.

    Retrieves user roles and permissions for a specific event, updating the context
    dictionary with role names and event permissions. Optionally enforces permission
    requirements based on the check parameter.

    Args:
        ctx: Context dictionary to update with permissions and roles.
        request: Django HTTP request object containing user information.
        slug: Event slug identifier for permission lookup.
        check: Whether to enforce permission requirements. Defaults to True.

    Raises:
        PermissionError: If check=True and user has no event permissions or organizer role.

    Side Effects:
        - Updates ctx with 'role_names' if user has event roles
        - Updates ctx with 'event_pms' containing event permissions
    """
    # Get user's event roles and permissions
    (is_organizer, user_event_permissions, names) = get_event_roles(request, slug)

    # Override organizer status if user has association admin role
    if "assoc_role" in ctx and 1 in ctx["assoc_role"]:
        is_organizer = True

    # Enforce permission check if required
    if check and not names and not is_organizer:
        raise PermissionError()

    # Add role names to context if user has roles
    if names:
        ctx["role_names"] = names

    # Get event features and build permissions index
    features = get_event_features(ctx["event"].id)
    ctx["event_pms"] = get_index_permissions(ctx, features, is_organizer, user_event_permissions, "event")


def update_run_plan_on_event_change(instance):
    """Set run plan from association default if not already set.

    Args:
        instance: Run instance that was saved
    """
    if not instance.plan and instance.event:
        updates = {"plan": instance.event.assoc.plan}
        Run.objects.filter(pk=instance.pk).update(**updates)


def clear_event_button_cache(instance):
    cache.delete(event_button_key(instance.event_id))


def prepare_campaign_event_data(instance):
    """Prepare campaign event data before saving.

    Args:
        instance: Event instance being saved
    """
    if instance.pk:
        try:
            old_instance = Event.objects.get(pk=instance.pk)
            instance._old_parent_id = old_instance.parent_id
        except ObjectDoesNotExist:
            instance._old_parent_id = None
    else:
        instance._old_parent_id = None


def copy_parent_event_to_campaign(event):
    """Setup campaign event by copying from parent.

    Args:
        event: Event instance that was saved
    """
    if event.parent_id:
        # noinspection PyProtectedMember
        if event._old_parent_id != event.parent_id:
            # copy config, texts, roles, features
            copy_class(event.pk, event.parent_id, EventConfig)
            copy_class(event.pk, event.parent_id, EventText)
            copy_class(event.pk, event.parent_id, EventRole)
            for fn in event.parent.features.all():
                event.features.add(fn)

            # Use flag to prevent recursion instead of disconnecting signal
            event._skip_campaign_setup = True
            event.save()
            del event._skip_campaign_setup


def create_default_event_setup(event: Event) -> None:
    """Setup event with runs, tickets, and forms after save.

    Creates default configurations for a newly saved event including:
    - Default run if none exist
    - Event-specific ticket tiers
    - Registration and character forms based on enabled features
    - Cache cleanup for updated configurations

    Args:
        event: Event instance that was saved and needs default setup

    Returns:
        None

    Note:
        Skips setup if event is marked as a template.
    """
    # Skip setup for template events
    if event.template:
        return

    # Create default run if no runs exist for this event
    if not event.runs.exists():
        Run.objects.create(event=event, number=1)

    # Get enabled features for this event to determine what to configure
    features = get_event_features(event.id)

    # Configure event-specific ticket tiers based on enabled features
    save_event_tickets(features, event)

    # Set up registration form with appropriate fields for this event
    save_event_registration_form(features, event)

    # Configure character creation form based on event requirements
    save_event_character_form(features, event)

    # Clear cached feature and field data to reflect new configurations
    clear_event_features_cache(event.id)
    clear_event_fields_cache(event.id)


def save_event_tickets(features: dict, instance: Event) -> None:
    """Create default registration tickets for event.

    Creates three types of registration tickets (Standard, Waiting, Filler) for the given
    event instance. Only creates tickets that don't already exist and respects feature
    flags for conditional ticket types.

    Args:
        features: Dictionary of enabled features for the event, used to check if
                 conditional ticket types should be created.
        instance: Event instance to create registration tickets for.

    Returns:
        None
    """
    # Define ticket configurations: (feature_key, tier_enum, display_name)
    # Empty feature_key means ticket is always created regardless of features
    tickets = [
        ("", TicketTier.STANDARD, "Standard"),
        ("waiting", TicketTier.WAITING, "Waiting"),
        ("filler", TicketTier.FILLER, "Filler"),
    ]

    # Process each ticket configuration
    for ticket in tickets:
        # Skip ticket creation if required feature is not enabled
        if ticket[0] and ticket[0] not in features:
            continue

        # Create ticket only if it doesn't already exist for this event and tier
        if not RegistrationTicket.objects.filter(event=instance, tier=ticket[1]).exists():
            RegistrationTicket.objects.create(event=instance, tier=ticket[1], name=ticket[2])


def save_event_character_form(features: dict, instance: Event) -> None:
    """Create character form questions based on enabled features.

    This function initializes character form questions for an event based on
    the features that are enabled. It creates default question types and
    handles special cases for different feature combinations.

    Args:
        features: Dictionary containing enabled features for the event.
            Expected to contain feature names as keys.
        instance: Event instance to create form for. Should have 'parent'
            attribute and support character form creation.

    Returns:
        None: This function modifies the instance in place.

    Note:
        If the event has a parent event, this function returns early as
        child events inherit form configuration from their parent.
    """
    # Early return if character feature is not enabled
    if "character" not in features:
        return

    # Child events inherit form configuration from parent
    if instance.parent:
        return

    # Activate organization language for proper localization
    _activate_orga_lang(instance)

    # Define default question types with their properties
    # Format: (label, status, visibility, max_length)
    def_tps = {
        WritingQuestionType.NAME: ("Name", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 1000),
        WritingQuestionType.TEASER: ("Presentation", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 10000),
        WritingQuestionType.SHEET: ("Text", QuestionStatus.MANDATORY, QuestionVisibility.PRIVATE, 50000),
    }

    # Get available custom question types from the system
    custom_tps = BaseQuestionType.get_basic_types()

    # Initialize basic character form questions
    _init_character_form_questions(custom_tps, def_tps, features, instance)

    # Add quest and trait writing elements if questbuilder feature is enabled
    if "questbuilder" in features:
        _init_writing_element(instance, def_tps, [QuestionApplicable.QUEST, QuestionApplicable.TRAIT])

    # Add prologue writing elements if prologue feature is enabled
    if "prologue" in features:
        _init_writing_element(instance, def_tps, [QuestionApplicable.PROLOGUE])

    # Add faction writing elements if faction feature is enabled
    if "faction" in features:
        _init_writing_element(instance, def_tps, [QuestionApplicable.FACTION])

    # Add plot writing elements with custom teaser configuration
    if "plot" in features:
        # Create modified question types for plot with shorter teaser
        plot_tps = dict(def_tps)
        plot_tps[WritingQuestionType.TEASER] = (
            "Concept",
            QuestionStatus.MANDATORY,
            QuestionVisibility.PUBLIC,
            3000,
        )
        _init_writing_element(instance, plot_tps, [QuestionApplicable.PLOT])


def _init_writing_element(instance, def_tps, applicables):
    """Initialize writing questions for specific applicables in an event instance.

    Args:
        instance: Event instance to initialize writing elements for
        def_tps: Dictionary of default question types and their configurations
        applicables: List of QuestionApplicable types to create questions for
    """
    for applicable in applicables:
        # if there are already questions for this applicable, skip
        if instance.get_elements(WritingQuestion).filter(applicable=applicable).exists():
            continue

        objs = [
            WritingQuestion(
                event=instance,
                typ=typ,
                name=_(cfg[0]),
                status=cfg[1],
                visibility=cfg[2],
                max_length=cfg[3],
                applicable=applicable,
            )
            for typ, cfg in def_tps.items()
        ]
        WritingQuestion.objects.bulk_create(objs)


def _init_character_form_questions(
    custom_tps: set,
    def_tps: dict,
    features: set,
    instance: Event | Association,
) -> None:
    """Initialize character form questions during model setup.

    Sets up default and custom question types for character creation forms,
    managing question creation and deletion based on enabled features and
    existing question configurations.

    Args:
        custom_tps: Set of custom question type identifiers to exclude from processing.
        def_tps: Dictionary mapping question types to their default configuration tuples
                (name, status, visibility, max_length).
        features: Set of enabled feature identifiers for the event/organization.
        instance: The event or organization instance to configure questions for.

    Returns:
        None
    """
    # Get existing character-applicable questions and their types
    que = instance.get_elements(WritingQuestion).filter(applicable=QuestionApplicable.CHARACTER)
    types = set(que.values_list("typ", flat=True).distinct())

    # Determine available question types, excluding custom ones
    choices = dict(WritingQuestionType.choices)
    all_types = choices.keys()
    all_types -= custom_tps

    # Create default question types if no questions exist yet
    if not types:
        for el, add in def_tps.items():
            WritingQuestion.objects.create(
                event=instance,
                typ=el,
                name=_(add[0]),
                status=add[1],
                visibility=add[2],
                max_length=add[3],
                applicable=QuestionApplicable.CHARACTER,
            )

    # Determine which types should not be removed (defaults + computed if px feature enabled)
    not_to_remove = set(def_tps.keys())
    if "px" in features:
        not_to_remove.add(WritingQuestionType.COMPUTED)
    all_types -= not_to_remove

    # Process each remaining question type based on feature availability
    for el in sorted(list(all_types)):
        # Create question if feature is enabled but question doesn't exist
        if el in features and el not in types:
            WritingQuestion.objects.create(
                event=instance,
                typ=el,
                name=_(el.capitalize()),
                status=QuestionStatus.HIDDEN,
                visibility=QuestionVisibility.HIDDEN,
                max_length=1000,
                applicable=QuestionApplicable.CHARACTER,
            )
        # Remove question if feature is disabled but question exists
        if el not in features and el in types:
            WritingQuestion.objects.filter(event=instance, typ=el).delete()


def save_event_registration_form(features: dict, instance) -> None:
    """Create registration form questions based on enabled features.

    This function manages the creation and deletion of registration questions
    for an event based on the features that are enabled. It ensures that
    default question types are always present and adds/removes feature-specific
    questions as needed.

    Args:
        features: Dictionary of enabled features for the event, where keys
            are feature names and values indicate if the feature is active.
        instance: Event instance to create the registration form for.

    Returns:
        None
    """
    # Activate the organization's language for proper translations
    _activate_orga_lang(instance)

    # Define default question types that should always be present
    def_tps = {RegistrationQuestionType.TICKET}

    # Help text descriptions for default question types
    help_texts = {
        RegistrationQuestionType.TICKET: _("Your registration ticket"),
    }

    # Get basic question types that are always available
    basic_tps = BaseQuestionType.get_basic_types()

    # Query existing questions and get their types
    que = instance.get_elements(RegistrationQuestion)
    types = set(que.values_list("typ", flat=True).distinct())

    # Get all available question type choices and filter out basic types
    choices = dict(RegistrationQuestionType.choices)
    all_types = choices.keys()
    all_types -= basic_tps

    # Create default question types if they don't exist
    for el in def_tps:
        if el not in types:
            RegistrationQuestion.objects.create(
                event=instance,
                typ=el,
                name=choices[el],
                description=help_texts.get(el, ""),
                status=QuestionStatus.MANDATORY,
            )

    # Determine which types should not be removed (protected types)
    not_to_remove = set(def_tps)
    all_types -= not_to_remove

    # Define help texts for feature-specific question types
    help_texts = {
        "additional_tickets": _("Reserve additional tickets beyond your own"),
        "pay_what_you_want": _("Freely indicate the amount of your donation"),
        "reg_surcharges": _("Registration surcharge"),
        "reg_quotas": _(
            "Number of installments to split the fee: payments and deadlines will be equally divided from the registration date"
        ),
    }

    # Process each feature-specific question type
    for el in sorted(list(all_types)):
        # Add question if feature is enabled but question doesn't exist
        if el in features and el not in types:
            RegistrationQuestion.objects.create(
                event=instance,
                typ=el,
                name=_(choices[el].capitalize()),
                description=help_texts.get(el, ""),
                status=QuestionStatus.OPTIONAL,
            )
        # Remove question if feature is disabled but question exists
        if el not in features and el in types:
            RegistrationQuestion.objects.filter(event=instance, typ=el).delete()


def _activate_orga_lang(instance: Event) -> None:
    """Activate the most common language among event organizers.

    Analyzes the language preferences of all organizers for the given event
    instance and activates the most frequently used language. Falls back to
    English if no organizers are found or no languages are specified.

    Args:
        instance: The event instance to analyze organizers for.
    """
    # Initialize dictionary to count language occurrences
    langs = {}

    # Iterate through all event organizers and count their languages
    for orga in get_event_organizers(instance):
        lang = orga.language
        if lang not in langs:
            langs[lang] = 1
        else:
            langs[lang] += 1

    # Determine the most common language or fall back to English
    if langs:
        max_lang = max(langs, key=langs.get)
    else:
        max_lang = "en"

    # Activate the selected language
    activate(max_lang)


def assign_previous_campaign_character(registration: Registration) -> None:
    """Auto-assign last character for campaign registrations.

    Automatically assigns the character from the previous campaign run to a new
    registration if the event is part of a campaign series. This ensures character
    continuity across campaign events.

    Args:
        registration: Registration instance to assign character to. Must have a
                     member and run associated with it.

    Returns:
        None

    Note:
        This function only operates on campaign events with a parent event.
        If the registration already has a character assigned, no action is taken.
    """
    # Early returns for invalid registration states
    if not registration.member:
        return

    if registration.cancellation_date:
        return

    # Check if this is a campaign event with parent
    if "campaign" not in get_event_features(registration.run.event_id):
        return
    if not registration.run.event.parent:
        return

    # Skip if character already assigned to this registration
    if RegistrationCharacterRel.objects.filter(reg__member=registration.member, reg__run=registration.run).count() > 0:
        return

    # Find the most recent run in the same campaign
    last = (
        Run.objects.filter(
            Q(event__parent=registration.run.event.parent) | Q(event_id=registration.run.event.parent_id)
        )
        .exclude(event_id=registration.run.event_id)
        .order_by("-end")
        .first()
    )
    if not last:
        return

    # Get the character relationship from the previous run
    old_rcr = RegistrationCharacterRel.objects.filter(reg__member=registration.member, reg__run=last).first()
    if old_rcr:
        # Create new character relationship for current registration
        rcr = RegistrationCharacterRel.objects.create(reg=registration, character=old_rcr.character)

        # Copy custom character attributes from previous registration
        for s in ["name", "pronoun", "song", "public", "private"]:
            if hasattr(old_rcr, "custom_" + s):
                value = getattr(old_rcr, "custom_" + s)
                setattr(rcr, "custom_" + s, value)
        rcr.save()
