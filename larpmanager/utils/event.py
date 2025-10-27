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

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch, Q
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.button import event_button_key
from larpmanager.cache.feature import clear_event_features_cache, get_event_features
from larpmanager.cache.fields import clear_event_fields_cache
from larpmanager.cache.role import has_event_permission
from larpmanager.models.access import EventRole, get_event_organizers
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
from larpmanager.models.registration import RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, Faction, FactionType
from larpmanager.utils.common import copy_class


def get_character_filter(character, character_registrations, active_filters):
    """Check if character should be included based on filter criteria.

    Args:
        character: Character instance to check
        character_registrations (dict): Mapping of character IDs to registrations
        active_filters (list): Filter criteria ('free', 'mirror', etc.)

    Returns:
        bool: True if character passes all filters
    """
    if "free" in active_filters:
        if character.id in character_registrations:
            return False
    if "mirror" in active_filters and character.mirror_id:
        if character.mirror_id in character_registrations:
            return False
    return True


def get_event_filter_characters(context, character_filters):
    """Get filtered characters organized by factions for event display.

    Args:
        context (dict): Event context to update
        character_filters (list): Character filter criteria

    Side effects:
        Updates context with filtered factions and characters lists
    """
    context["factions"] = []

    character_registrations = {}
    for registration_character_relation in RegistrationCharacterRel.objects.filter(
        reg__run=context["run"], reg__cancellation_date__isnull=True
    ).select_related("reg", "reg__member"):
        character_registrations[registration_character_relation.character_id] = registration_character_relation.reg

    characters_by_id = {}
    for character in context["event"].get_elements(Character).filter(hide=False):
        if character.id in character_registrations:
            character.reg = character_registrations[character.id]
            character.member = character_registrations[character.id].member
        characters_by_id[character.id] = character

    if "faction" in context["features"] and context["show_faction"]:
        faction_query = context["event"].get_elements(Faction).filter(typ=FactionType.PRIM).order_by("order")
        character_prefetch = Prefetch(
            "characters",
            queryset=Character.objects.filter(hide=False).order_by("number"),
        )
        for faction in faction_query.prefetch_related(character_prefetch):
            faction.data = faction.show_red()
            faction.chars = []
            for character in faction.characters.all():
                if character.hide:
                    continue
                if not get_character_filter(character, character_registrations, character_filters):
                    continue
                character.data = character.show_red()
                faction.chars.append(character)
            if len(faction.chars) == 0:
                continue
            context["factions"].append(faction)
    else:
        default_faction = Faction()
        default_faction.number = 0
        default_faction.name = "all"
        default_faction.data = default_faction.show_red()
        default_faction.chars = []
        for _character_id, character in characters_by_id.items():
            if not get_character_filter(character, character_registrations, character_filters):
                continue
            character.data = character.show_red()
            default_faction.chars.append(character)
        context["factions"].append(default_faction)


def has_access_character(request, context):
    """Check if user has access to view/edit a specific character.

    Args:
        request: Django HTTP request object
        context (dict): Context with character information

    Returns:
        bool: True if user has access (organizer, owner, or player)
    """
    if has_event_permission(request, context, context["event"].slug, "orga_characters"):
        return True

    member_id = context["member"].id

    if "owner_id" in context["char"] and context["char"]["owner_id"] == member_id:
        return True

    if "player_id" in context["char"] and context["char"]["player_id"] == member_id:
        return True

    return False


def update_run_plan_on_event_change(instance):
    """Set run plan from association default if not already set.

    Args:
        instance: Run instance that was saved
    """
    if not instance.plan and instance.event:
        updates = {"plan": instance.event.assoc.plan}
        Run.objects.filter(pk=instance.pk).update(**updates)


def clear_event_button_cache(event_instance):
    cache.delete(event_button_key(event_instance.event_id))


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
            for feature in event.parent.features.all():
                event.features.add(feature)

            # Use flag to prevent recursion instead of disconnecting signal
            event._skip_campaign_setup = True
            event.save()
            del event._skip_campaign_setup


def create_default_event_setup(event):
    """Setup event with runs, tickets, and forms after save.

    Args:
        event: Event instance that was saved
    """
    if event.template:
        return

    if not event.runs.exists():
        Run.objects.create(event=event, number=1)

    event_features = get_event_features(event.id)

    save_event_tickets(event_features, event)

    save_event_registration_form(event_features, event)

    save_event_character_form(event_features, event)

    clear_event_features_cache(event.id)

    clear_event_fields_cache(event.id)


def save_event_tickets(features, instance):
    """Create default registration tickets for event.

    Args:
        features (dict): Enabled features for the event
        instance: Event instance to create tickets for
    """
    # create tickets if not exists
    tickets = [
        ("", TicketTier.STANDARD, "Standard"),
        ("waiting", TicketTier.WAITING, "Waiting"),
        ("filler", TicketTier.FILLER, "Filler"),
    ]
    for ticket in tickets:
        if ticket[0] and ticket[0] not in features:
            continue
        if not RegistrationTicket.objects.filter(event=instance, tier=ticket[1]).exists():
            RegistrationTicket.objects.create(event=instance, tier=ticket[1], name=ticket[2])


def save_event_character_form(features: dict, instance) -> None:
    """Create character form questions based on enabled features.

    This function initializes character form questions for an event based on the
    enabled features. It creates default writing question types and adds feature-specific
    writing elements as needed.

    Args:
        features: Dictionary of enabled features for the event, where keys are
                 feature names and values indicate if they're active
        instance: Event instance to create form for

    Returns:
        None

    Note:
        - Returns early if 'character' feature is not enabled
        - Uses parent event's form if instance has a parent
        - Activates organization language before processing
    """
    # Early return if character feature is not enabled
    if "character" not in features:
        return

    # Use parent event's form if this event has a parent
    if instance.parent:
        return

    # Activate the organization's language for proper localization
    _activate_orga_lang(instance)

    # Define default question types with their properties
    # (name, status, visibility, max_length)
    def_tps = {
        WritingQuestionType.NAME: ("Name", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 1000),
        WritingQuestionType.TEASER: ("Presentation", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 10000),
        WritingQuestionType.SHEET: ("Text", QuestionStatus.MANDATORY, QuestionVisibility.PRIVATE, 50000),
    }

    # Get basic custom question types from the system
    custom_tps = BaseQuestionType.get_basic_types()

    # Initialize character form questions with both custom and default types
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

    # Add plot writing elements with modified teaser settings if plot feature is enabled
    if "plot" in features:
        # Create a copy of default types with modified teaser for plot concept
        plot_tps = dict(def_tps)
        plot_tps[WritingQuestionType.TEASER] = (
            "Concept",
            QuestionStatus.MANDATORY,
            QuestionVisibility.PUBLIC,
            3000,
        )
        _init_writing_element(instance, plot_tps, [QuestionApplicable.PLOT])


def _init_writing_element(instance, default_question_types, question_applicables):
    """Initialize writing questions for specific applicables in an event instance.

    Args:
        instance: Event instance to initialize writing elements for
        default_question_types: Dictionary of default question types and their configurations
        question_applicables: List of QuestionApplicable types to create questions for
    """
    for applicable in question_applicables:
        # if there are already questions for this applicable, skip
        if instance.get_elements(WritingQuestion).filter(applicable=applicable).exists():
            continue

        writing_questions = [
            WritingQuestion(
                event=instance,
                typ=question_type,
                name=_(config[0]),
                status=config[1],
                visibility=config[2],
                max_length=config[3],
                applicable=applicable,
            )
            for question_type, config in default_question_types.items()
        ]
        WritingQuestion.objects.bulk_create(writing_questions)


def _init_character_form_questions(
    custom_types: set,
    default_types: dict,
    features: set,
    instance,
) -> None:
    """Initialize character form questions during model setup.

    Sets up default and custom question types for character creation forms,
    managing question creation and deletion based on enabled features and
    existing question configurations.

    Args:
        custom_types: Set of custom question types to exclude from processing
        default_types: Dictionary mapping default question types to their configuration
                (name, status, visibility, max_length)
        features: Set of enabled feature names
        instance: Event instance to create questions for

    Returns:
        None
    """
    # Get existing character questions and their types
    existing_questions = instance.get_elements(WritingQuestion).filter(applicable=QuestionApplicable.CHARACTER)
    existing_types = set(existing_questions.values_list("typ", flat=True).distinct())

    # Get all available question types, excluding custom ones
    choices = dict(WritingQuestionType.choices)
    available_types = choices.keys()
    available_types -= custom_types

    # Create default question types if no questions exist yet
    if not existing_types:
        for question_type, config in default_types.items():
            WritingQuestion.objects.create(
                event=instance,
                typ=question_type,
                name=_(config[0]),
                status=config[1],
                visibility=config[2],
                max_length=config[3],
                applicable=QuestionApplicable.CHARACTER,
            )

    # Determine which types should not be removed (defaults + px feature)
    protected_types = set(default_types.keys())
    if "px" in features:
        protected_types.add(WritingQuestionType.COMPUTED)
    available_types -= protected_types

    # Process each remaining question type based on feature availability
    for question_type in sorted(list(available_types)):
        # Create question if feature is enabled but question doesn't exist
        if question_type in features and question_type not in existing_types:
            WritingQuestion.objects.create(
                event=instance,
                typ=question_type,
                name=_(question_type.capitalize()),
                status=QuestionStatus.HIDDEN,
                visibility=QuestionVisibility.HIDDEN,
                max_length=1000,
                applicable=QuestionApplicable.CHARACTER,
            )
        # Remove question if feature is disabled but question exists
        if question_type not in features and question_type in existing_types:
            WritingQuestion.objects.filter(event=instance, typ=question_type).delete()


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


def _activate_orga_lang(instance) -> None:
    """Activate the most common language among event organizers.

    Determines the most frequently used language among all organizers
    of the given event instance and activates it for the current context.
    Falls back to English if no organizers are found.

    Args:
        instance: Event instance to get organizers from.
    """
    # Count language frequency among organizers
    language_frequency = {}
    for organizer in get_event_organizers(instance):
        organizer_language = organizer.language

        # Track language occurrence count
        if organizer_language not in language_frequency:
            language_frequency[organizer_language] = 1
        else:
            language_frequency[organizer_language] += 1

    # Select most common language or default to English
    if language_frequency:
        most_common_language = max(language_frequency, key=language_frequency.get)
    else:
        most_common_language = "en"

    # Activate the selected language
    activate(most_common_language)


def assign_previous_campaign_character(registration) -> None:
    """Auto-assign last character from previous campaign run to new registration.

    Automatically assigns the character from the most recent campaign run to a new
    registration if the event is part of a campaign series. Only applies when the
    member doesn't already have a character assigned to the current run.

    Args:
        registration: Registration instance to assign character to. Must have
            a member and run associated with it.

    Returns:
        None

    Note:
        - Only works for campaign events with a parent event
        - Skips cancelled registrations
        - Preserves custom character attributes from previous run
        - Does nothing if character already assigned to current run
    """
    # Skip if registration has no member or is cancelled
    if not registration.member:
        return

    if registration.cancellation_date:
        return

    # Only proceed if this is a campaign event with parent
    if "campaign" not in get_event_features(registration.run.event_id):
        return
    if not registration.run.event.parent:
        return

    # Skip if member already has a character assigned to this run
    if RegistrationCharacterRel.objects.filter(reg__member=registration.member, reg__run=registration.run).count() > 0:
        return

    # Find the most recent run from the same campaign series
    previous_campaign_run = (
        Run.objects.filter(
            Q(event__parent=registration.run.event.parent) | Q(event_id=registration.run.event.parent_id)
        )
        .exclude(event_id=registration.run.event_id)
        .order_by("-end")
        .first()
    )
    if not previous_campaign_run:
        return

    # Get character relationship from previous run and create new one
    previous_character_relation = RegistrationCharacterRel.objects.filter(
        reg__member=registration.member, reg__run=previous_campaign_run
    ).first()
    if previous_character_relation:
        new_character_relation = RegistrationCharacterRel.objects.create(
            reg=registration, character=previous_character_relation.character
        )

        # Copy custom character attributes from previous run
        for custom_attribute_name in ["name", "pronoun", "song", "public", "private"]:
            if hasattr(previous_character_relation, "custom_" + custom_attribute_name):
                attribute_value = getattr(previous_character_relation, "custom_" + custom_attribute_name)
                setattr(new_character_relation, "custom_" + custom_attribute_name, attribute_value)
        new_character_relation.save()
