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

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.event import OrgaAppearanceForm, OrgaEventForm
from larpmanager.forms.miscellanea import OrgaCopyForm
from larpmanager.models.access import EventRole
from larpmanager.models.accounting import Discount
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event, EventButton, EventConfig, EventText
from larpmanager.models.form import (
    RegistrationOption,
    RegistrationQuestion,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.miscellanea import WorkshopModule, WorkshopOption, WorkshopQuestion
from larpmanager.models.registration import (
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSurcharge,
    RegistrationTicket,
)
from larpmanager.models.utils import generate_id
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    Faction,
    Handout,
    HandoutTemplate,
    Plot,
    PlotCharacterRel,
    Prologue,
    Relationship,
    SpeedLarp,
)
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import copy_class

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponseRedirect

logger = logging.getLogger(__name__)


def correct_rels_many(e_id: Any, cls_p: Any, cls: Any, field: Any, rel_field: Any = "number") -> None:
    """Correct many-to-many relationships after copying event elements.

    Args:
        e_id: Target event ID
        cls_p: Parent model class to match against
        cls: Model class to update many-to-many relationships for
        field: Many-to-many field name to correct
        rel_field: Field to use for matching elements (default: "number")

    Side effects:
        Updates many-to-many relationships for all objects of cls in the event

    """
    old_id_to_new_id = {}

    for parent_obj in cls_p.objects.filter(event_id=e_id):
        relation_value = getattr(parent_obj, rel_field)
        old_id_to_new_id[relation_value] = parent_obj.id

    for target_obj in cls.objects.filter(event_id=e_id):
        many_to_many_field = getattr(target_obj, field)
        current_relations = list(many_to_many_field.all())
        new_relation_ids = []

        for old_relation in current_relations:
            relation_value = getattr(old_relation, rel_field)
            new_relation_id = old_id_to_new_id[relation_value]
            new_relation_ids.append(new_relation_id)

        many_to_many_field.set(new_relation_ids, clear=True)


def correct_rels(
    target_event_id: Any,
    source_event_id: Any,
    parent_model_class: Any,
    child_model_class: Any,
    relationship_field: Any,
    matching_field: Any = "number",
) -> None:
    """Correct model relationships after copying event elements.

    Args:
        target_event_id: Target event ID
        source_event_id: Source parent event ID
        parent_model_class: Parent model class to match
        child_model_class: Model class to update relationships for
        relationship_field: Relationship field name to correct
        matching_field: Field to use for matching (default: "number")

    """
    source_id_to_match_value = {}
    match_value_to_target_id = {}
    relationship_field_id = relationship_field + "_id"

    for parent_obj in parent_model_class.objects.filter(event_id=source_event_id):
        match_value = getattr(parent_obj, matching_field)
        source_id_to_match_value[parent_obj.id] = match_value

    for parent_obj in parent_model_class.objects.filter(event_id=target_event_id):
        match_value = getattr(parent_obj, matching_field)
        match_value_to_target_id[match_value] = parent_obj.id

    objects_to_update = []
    for child_obj in child_model_class.objects.filter(event_id=target_event_id):
        source_parent_id = getattr(child_obj, relationship_field_id)
        if source_parent_id not in source_id_to_match_value:
            continue
        match_value = source_id_to_match_value[source_parent_id]
        target_parent_id = match_value_to_target_id[match_value]
        setattr(child_obj, relationship_field_id, target_parent_id)
        objects_to_update.append(child_obj)

    if objects_to_update:
        child_model_class.objects.bulk_update(objects_to_update, [relationship_field_id])


def correct_relationship(e_id: Any, p_id: Any) -> None:
    """Correct character relationships after event copying.

    Args:
        e_id: Target event ID with copied characters
        p_id: Source parent event ID with original characters

    """
    source_character_map = {}
    target_character_map = {}
    for character in Character.objects.filter(event_id=p_id):
        source_character_map[character.id] = character.number
    for character in Character.objects.filter(event_id=e_id):
        target_character_map[character.number] = character.id

    # Pre-fetch existing relationships
    existing_relationships = set(
        Relationship.objects.filter(source__event_id=e_id).values_list("source_id", "target_id")
    )

    for relationship in Relationship.objects.filter(source__event_id=p_id):
        new_source_id = relationship.source_id
        if new_source_id not in source_character_map:
            continue
        new_source_id = source_character_map[new_source_id]
        if new_source_id not in target_character_map:
            continue
        new_source_id = target_character_map[new_source_id]
        relationship.source_id = new_source_id

        new_target_id = relationship.target_id
        if new_target_id not in source_character_map:
            continue
        new_target_id = source_character_map[new_target_id]
        if new_target_id not in target_character_map:
            continue
        new_target_id = target_character_map[new_target_id]
        relationship.target_id = new_target_id

        # Check existence using pre-fetched set instead of query
        if (relationship.source_id, relationship.target_id) in existing_relationships:
            continue

        relationship.pk = None
        relationship.save()


def correct_workshop(e_id: int, p_id: int) -> None:
    """Correct workshop data mappings during event copying process.

    This function copies workshop modules, questions, and options from a source event
    to a target event, maintaining proper relationships between the copied objects.

    Args:
        e_id: Target event ID to copy workshop data to
        p_id: Source event ID to copy workshop data from

    Returns:
        None

    """
    # Build mapping cache from source event workshop modules (ID -> number)
    source_module_id_to_number = {}
    target_module_number_to_id = {}
    for module in WorkshopModule.objects.filter(event_id=p_id):
        source_module_id_to_number[module.id] = module.number

    # Build mapping cache from target event workshop modules (number -> ID)
    for module in WorkshopModule.objects.filter(event_id=e_id):
        target_module_number_to_id[module.number] = module.id

    # Copy workshop questions from source to target event
    # Update module references using the mapping caches
    for question in WorkshopQuestion.objects.filter(module__event_id=p_id):
        module_id = question.module_id
        module_number = source_module_id_to_number[module_id]  # Get source module number
        target_module_id = target_module_number_to_id[module_number]  # Get target module ID
        question.module_id = target_module_id

        # Create new question object in target event
        question.pk = None
        question.save()

    # Rebuild caches for workshop questions mapping
    source_question_id_to_number = {}
    target_question_number_to_id = {}
    for question in WorkshopQuestion.objects.filter(module__event_id=p_id):
        source_question_id_to_number[question.id] = question.number

    # Build mapping from target event questions (number -> ID)
    for question in WorkshopQuestion.objects.filter(module__event_id=e_id):
        target_question_number_to_id[question.number] = question.id

    # Copy workshop options from source to target event
    # Update question references using the mapping caches
    for option in WorkshopOption.objects.filter(question__module__event_id=p_id):
        question_id = option.question_id
        question_number = source_question_id_to_number[question_id]  # Get source question number
        target_question_id = target_question_number_to_id[question_number]  # Get target question ID
        option.question_id = target_question_id

        # Create new option object in target event
        option.pk = None
        option.save()


def _copy_character_field_values(target_event_id: int, source_event_id: int) -> None:
    """Copy character answers and choices from source to target event.

    This function copies WritingAnswer and WritingChoice objects associated with
    characters from a source event to a target event, updating element_id references
    to point to the corresponding characters in the target event.

    Args:
        target_event_id: Target event ID to copy answers/choices to
        source_event_id: Source event ID to copy answers/choices from

    Returns:
        None

    """
    # Build mapping cache from source characters (ID -> number)
    source_character_map = {}
    for character in Character.objects.filter(event_id=source_event_id):
        source_character_map[character.id] = character.number

    # Build mapping cache from target characters (number -> ID)
    target_character_map = {}
    for character in Character.objects.filter(event_id=target_event_id):
        target_character_map[character.number] = character.id

    # Build mapping cache from source questions (ID -> name) for question matching
    source_question_map = {}
    for question in WritingQuestion.objects.filter(event_id=source_event_id):
        source_question_map[question.id] = question.name

    # Build mapping cache from target questions (name -> ID)
    target_question_map = {}
    for question in WritingQuestion.objects.filter(event_id=target_event_id):
        target_question_map[question.name] = question.id

    _copy_character_answers(
        source_character_map, source_event_id, source_question_map, target_character_map, target_question_map
    )

    _copy_character_choices(
        source_character_map,
        source_event_id,
        source_question_map,
        target_character_map,
        target_event_id,
        target_question_map,
    )


def _copy_character_answers(
    source_character_map: dict[int, int],
    source_event_id: int,
    source_question_map: dict[int, str],
    target_character_map: dict[int, int],
    target_question_map: dict[str, int],
) -> None:
    """Copy WritingAnswer objects from source event to target event.

    This function iterates through all WritingAnswer objects in the source event
    and creates copies in the target event, updating character and question references
    to point to the corresponding objects in the target event.

    Args:
        source_character_map: Mapping of source character IDs to character numbers
        source_event_id: Source event ID to copy answers from
        source_question_map: Mapping of source question IDs to question names
        target_character_map: Mapping of character numbers to target character IDs
        target_question_map: Mapping of question names to target question IDs

    Returns:
        None

    """
    # Copy WritingAnswer objects
    for answer in WritingAnswer.objects.filter(question__event_id=source_event_id):
        # Skip if character doesn't exist in mapping
        if answer.element_id not in source_character_map:
            continue

        character_number = source_character_map[answer.element_id]

        # Skip if character doesn't exist in target event
        if character_number not in target_character_map:
            continue

        # Skip if question doesn't exist in mapping
        if answer.question_id not in source_question_map:
            continue

        question_name = source_question_map[answer.question_id]

        # Skip if question doesn't exist in target event
        if question_name not in target_question_map:
            continue

        # Update references to target event
        answer.element_id = target_character_map[character_number]
        answer.question_id = target_question_map[question_name]

        # Create new answer object in target event
        answer.pk = None
        answer.save()


def _build_option_mappings(
    source_event_id: int,
    target_event_id: int,
    source_question_map: dict[int, str],
    target_question_map: dict[str, int],
) -> tuple[dict[int, str], dict[str, int]]:
    """Build option mappings for source and target events.

    Args:
        source_event_id: Source event ID
        target_event_id: Target event ID
        source_question_map: Mapping of source question IDs to question names
        target_question_map: Mapping of question names to target question IDs

    Returns:
        Tuple of (source_option_map, target_option_map)

    """
    # Build mapping cache from source options (ID -> key)
    source_option_id_to_key = {}
    for option in WritingOption.objects.filter(event_id=source_event_id):
        question_name = source_question_map.get(option.question_id)
        if question_name:
            source_option_id_to_key[option.id] = f"{question_name}:{option.name}"

    # Build mapping cache from target options (key -> ID)
    target_option_key_to_id = {}
    for option in WritingOption.objects.filter(event_id=target_event_id):
        for name, qid in target_question_map.items():
            if qid == option.question_id:
                target_option_key_to_id[f"{name}:{option.name}"] = option.id
                break

    return source_option_id_to_key, target_option_key_to_id


def _copy_character_choices(
    source_character_map: dict[int, int],
    source_event_id: int,
    source_question_map: dict[int, str],
    target_character_map: dict[int, int],
    target_event_id: int,
    target_question_map: dict[str, int],
) -> None:
    """Copy WritingChoice objects from source event to target event.

    This function iterates through all WritingChoice objects in the source event
    and creates copies in the target event, updating character, question, and option
    references to point to the corresponding objects in the target event.

    Args:
        source_character_map: Mapping of source character IDs to character numbers
        source_event_id: Source event ID to copy choices from
        source_question_map: Mapping of source question IDs to question names
        target_character_map: Mapping of character numbers to target character IDs
        target_event_id: Target event ID to copy choices to
        target_question_map: Mapping of question names to target question IDs

    Returns:
        None

    """
    source_option_map, target_option_map = _build_option_mappings(
        source_event_id, target_event_id, source_question_map, target_question_map
    )

    # Copy WritingChoice objects
    for choice in WritingChoice.objects.filter(question__event_id=source_event_id):
        _copy_single_choice(
            choice,
            source_character_map,
            target_character_map,
            source_question_map,
            target_question_map,
            source_option_map,
            target_option_map,
        )


def _copy_single_choice(
    choice: WritingChoice,
    source_character_map: dict[int, int],
    target_character_map: dict[int, int],
    source_question_map: dict[int, str],
    target_question_map: dict[str, int],
    source_option_map: dict[int, str],
    target_option_map: dict[str, int],
) -> None:
    """Copy a single WritingChoice to target event if all references are valid.

    Args:
        choice: WritingChoice object to copy
        source_character_map: Mapping of source character IDs to character numbers
        target_character_map: Mapping of character numbers to target character IDs
        source_question_map: Mapping of source question IDs to question names
        target_question_map: Mapping of question names to target question IDs
        source_option_map: Mapping of source option IDs to option keys
        target_option_map: Mapping of option keys to target option IDs

    Returns:
        None

    """
    # Validate and get character number
    if choice.element_id not in source_character_map:
        return
    character_number = source_character_map[choice.element_id]
    if character_number not in target_character_map:
        return

    # Validate and get question name
    if choice.question_id not in source_question_map:
        return
    question_name = source_question_map[choice.question_id]
    if question_name not in target_question_map:
        return

    # Validate and get option key
    if choice.option_id not in source_option_map:
        return
    option_key = source_option_map[choice.option_id]
    if option_key not in target_option_map:
        return

    # Update references to target event
    choice.element_id = target_character_map[character_number]
    choice.question_id = target_question_map[question_name]
    choice.option_id = target_option_map[option_key]

    # Create new choice object in target event
    choice.pk = None
    choice.save()


def correct_plot_character(e_id: Any, p_id: Any) -> None:
    """Correct plot-character relationships after event copying.

    Args:
        e_id: Target event ID with copied elements
        p_id: Source parent event ID with original elements

    """
    character_id_mapping = {}
    for old_character in Character.objects.values_list("id", "number").filter(event_id=p_id):
        new_character_id = Character.objects.values_list("id").get(event_id=e_id, number=old_character[1])[0]
        character_id_mapping[old_character[0]] = new_character_id

    plot_id_mapping = {}
    for old_plot in Plot.objects.values_list("id", "number").filter(event_id=p_id):
        new_plot_id = Plot.objects.values_list("id").get(event_id=e_id, number=old_plot[1])[0]
        plot_id_mapping[old_plot[0]] = new_plot_id

    # Pre-fetch existing plot-character relationships
    existing_plot_character_rels = set(
        PlotCharacterRel.objects.filter(character__event_id=e_id).values_list("character_id", "plot_id")
    )

    for relationship in PlotCharacterRel.objects.filter(character__event_id=p_id):
        new_character_id = character_id_mapping[relationship.character_id]
        new_plot_id = plot_id_mapping[relationship.plot_id]

        # Check existence using pre-fetched set instead of query
        if (new_character_id, new_plot_id) in existing_plot_character_rels:
            continue

        relationship.character_id = new_character_id
        relationship.plot_id = new_plot_id
        relationship.pk = None
        relationship.save()


def copy_character_config(e_id: Any, p_id: Any) -> None:
    """Copy character configuration settings from parent to target event.

    Args:
        e_id: Target event ID to copy configurations to
        p_id: Parent event ID to copy configurations from

    """
    CharacterConfig.objects.filter(character__event_id=e_id).delete()
    character_id_by_number = {}
    for character in Character.objects.filter(event_id=e_id):
        character_id_by_number[character.number] = character.id

    # Pre-fetch all character configs
    configs_by_character = defaultdict(list)
    for config in CharacterConfig.objects.filter(character__event_id=p_id).select_related("character"):
        configs_by_character[config.character_id].append(config)

    for parent_character in Character.objects.filter(event_id=p_id):
        target_character_id = character_id_by_number[parent_character.number]
        for config in configs_by_character[parent_character.id]:
            for retry_attempt in range(2):
                try:
                    with transaction.atomic():
                        _character_config, _created = CharacterConfig.objects.update_or_create(
                            character_id=target_character_id,
                            name=config.name,
                            defaults={"value": config.value},
                        )
                    break
                except IntegrityError:
                    if retry_attempt == 0:
                        continue
                    raise


def copy(
    request: HttpRequest,
    context: dict,
    parent_event: Event,
    target_event: Event,
    data_types_to_copy: list,
) -> HttpResponseRedirect | None:
    """Copy event data from a parent event to the current event.

    Args:
        request: The HTTP request object
        context: Context dictionary for the operation
        parent_event: The source event to copy data from
        target_event: The target event to copy data to
        data_types_to_copy: List of data types to copy

    Returns:
        HttpResponseRedirect if error occurs, None if successful

    """
    # Validate parent event exists
    if not parent_event:
        return messages.error(request, _("Parent empty"))

    # Extract event IDs for copying operations
    parent_event_id = parent_event.id
    target_event_id = target_event.id

    # Prevent copying from the same event
    if parent_event_id == target_event_id:
        return messages.error(request, _("Can't copy from same event"))

    # Copy event-specific data based on targets
    copy_event(context, target_event_id, data_types_to_copy, target_event, parent_event_id, parent_event)

    # Copy registration data between events
    copy_registration(target_event_id, data_types_to_copy, parent_event_id)

    # Copy writing/story data between events
    copy_writing(target_event_id, data_types_to_copy, parent_event_id)

    # Save changes to the target event
    target_event.save()

    # Notify user of successful completion
    messages.success(request, _("Copy done"))
    return None


def copy_event(
    context: dict[str, Any],
    target_event_id: Any,
    elements_to_copy: Any,
    target_event: object,
    source_event_id: Any,
    source_event: object,
) -> None:
    """Copy event data and related objects from parent to new event.

    Args:
        context: Context dictionary with form information
        target_event_id: Target event ID
        elements_to_copy: List of elements to copy
        target_event: Target event instance
        source_event_id: Source parent event ID
        source_event: Source parent event instance

    """
    # Define copy actions for each target type
    copy_actions = {
        "event": lambda: _copy_event_fields(context, target_event, source_event),
        "config": lambda: copy_class(target_event_id, source_event_id, EventConfig),
        "appearance": lambda: _copy_appearance_fields(context, target_event, source_event),
        "text": lambda: copy_class(target_event_id, source_event_id, EventText),
        "role": lambda: copy_class(target_event_id, source_event_id, EventRole),
        "features": lambda: _copy_features(target_event, source_event),
        "navigation": lambda: copy_class(target_event_id, source_event_id, EventButton),
    }

    # Execute copy actions for each target in the list
    for element_type in elements_to_copy:
        if element_type in copy_actions:
            copy_actions[element_type]()


def _copy_event_fields(context: dict[str, Any], event: object, parent_event: object) -> None:
    """Copy basic event fields from parent to child event."""
    for field_name in get_all_fields_from_form(OrgaEventForm, context):
        if field_name == "slug":
            continue
        field_value = getattr(parent_event, field_name)
        setattr(event, field_name, field_value)
    event.name = "copy - " + event.name


def _copy_appearance_fields(context: dict[str, Any], child_event: object, parent_event: object) -> None:
    """Copy appearance fields from parent to child event."""
    for field_name in get_all_fields_from_form(OrgaAppearanceForm, context):
        if field_name == "event_css":
            copy_css(context, child_event, parent_event)
        else:
            field_value = getattr(parent_event, field_name)
            setattr(child_event, field_name, field_value)


def _copy_features(event: object, parent: Any) -> None:
    """Copy features from parent to child event."""
    for feature in parent.features.all():
        event.features.add(feature)
    event.save()


def copy_registration(source_event_id: int, targets: list[str], target_event_id: int) -> None:
    """Copy registration components from one event to another based on specified targets.

    Args:
        source_event_id: Source event ID to copy from
        targets: List of registration component types to copy ('ticket', 'question',
                'discount', 'quota', 'installment', 'surcharge')
        target_event_id: Target event ID to copy to

    """
    # Copy registration tickets if requested
    if "ticket" in targets:
        copy_class(source_event_id, target_event_id, RegistrationTicket)

    # Copy registration questions and their options, then fix relationships
    if "question" in targets:
        copy_class(source_event_id, target_event_id, RegistrationQuestion)
        copy_class(source_event_id, target_event_id, RegistrationOption)
        correct_rels(source_event_id, target_event_id, RegistrationQuestion, RegistrationOption, "question", "name")

    # Copy discount configurations
    if "discount" in targets:
        copy_class(source_event_id, target_event_id, Discount)

    # Copy registration quotas
    if "quota" in targets:
        copy_class(source_event_id, target_event_id, RegistrationQuota)

    # Copy installment plans and link them to tickets
    if "installment" in targets:
        copy_class(source_event_id, target_event_id, RegistrationInstallment)
        correct_rels_many(source_event_id, RegistrationTicket, RegistrationInstallment, "tickets", "name")

    # Copy surcharge configurations
    if "surcharge" in targets:
        copy_class(source_event_id, target_event_id, RegistrationSurcharge)


def copy_writing(target_event_id: int, targets: list[str], parent_event_id: int) -> None:
    """Copy writing elements from parent to child event.

    This function copies various writing-related elements (characters, factions,
    quests, etc.) from a parent event to a target event based on the specified
    target types.

    Args:
        target_event_id: Target event ID where elements will be copied to
        targets: List of element types to copy. Valid values include:
            'character', 'faction', 'quest', 'prologue', 'speedlarp',
            'plot', 'handout', 'workshop'
        parent_event_id: Parent event ID to copy elements from

    Returns:
        None

    """
    # Copy character-related elements and fix relationships
    if "character" in targets:
        copy_class(target_event_id, parent_event_id, Character)
        # correct relationship
        correct_relationship(target_event_id, parent_event_id)
        # character fields
        copy_class(target_event_id, parent_event_id, WritingQuestion)
        copy_class(target_event_id, parent_event_id, WritingOption)
        copy_character_config(target_event_id, parent_event_id)
        correct_rels(target_event_id, parent_event_id, WritingQuestion, WritingOption, "question", "name")
        # copy character answers and choices
        _copy_character_field_values(target_event_id, parent_event_id)

    # Copy faction elements
    if "faction" in targets:
        copy_class(target_event_id, parent_event_id, Faction)

    # Copy quest-related elements and fix relationships
    if "quest" in targets:
        copy_class(target_event_id, parent_event_id, QuestType)
        copy_class(target_event_id, parent_event_id, Quest)
        copy_class(target_event_id, parent_event_id, Trait)
        correct_rels(target_event_id, parent_event_id, QuestType, Quest, "typ")
        correct_rels(target_event_id, parent_event_id, Quest, Trait, "quest")

    # Copy prologue elements
    if "prologue" in targets:
        copy_class(target_event_id, parent_event_id, Prologue)

    # Copy speedlarp elements
    if "speedlarp" in targets:
        copy_class(target_event_id, parent_event_id, SpeedLarp)

    # Copy plot elements and fix character relationships
    if "plot" in targets:
        copy_class(target_event_id, parent_event_id, Plot)
        # correct plotcharacterrels
        correct_plot_character(target_event_id, parent_event_id)

    # Copy handout and template elements
    if "handout" in targets:
        copy_class(target_event_id, parent_event_id, Handout)
        copy_class(target_event_id, parent_event_id, HandoutTemplate)

    # Copy workshop elements and fix relationships
    if "workshop" in targets:
        copy_class(target_event_id, parent_event_id, WorkshopModule)
        # correct workshop
        correct_workshop(target_event_id, parent_event_id)


def copy_css(context: dict[str, Any], event: Event, parent: Any) -> None:
    """Copy CSS file from parent event to current event.

    Args:
        context: Context object
        event: Target event to copy CSS to
        parent: Source event to copy CSS from

    """
    # Initialize appearance form and get source CSS path
    appearance_form = OrgaAppearanceForm(context=context)
    source_css_path = appearance_form.get_css_path(parent)

    # Exit early if source CSS file doesn't exist
    if not default_storage.exists(source_css_path):
        return

    # Read CSS content from source file
    try:
        css_content = default_storage.open(source_css_path).read().decode("utf-8")

        # Generate new CSS ID and save to target event
        event.css_code = generate_id(32)
        target_css_path = appearance_form.get_css_path(event)
        default_storage.save(target_css_path, ContentFile(css_content))
    except (OSError, UnicodeDecodeError, PermissionError):
        logger.exception("Failed to copy CSS file from %s", source_css_path)
        # Continue without copying CSS - event will work without custom CSS


@login_required
def orga_copy(request: HttpRequest, event_slug: str) -> Any:
    """Handle event copying functionality for organizers.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier

    Returns:
        HttpResponse: Rendered copy form template or redirect after successful copy

    """
    context = check_event_context(request, event_slug, "orga_copy")

    if request.method == "POST":
        form = OrgaCopyForm(request.POST, request.FILES, context=context)
        if form.is_valid():
            pt = form.cleaned_data["parent"]
            targets = form.cleaned_data["target"]
            parent = Event.objects.get(pk=pt, association_id=context["association_id"])
            event = context["event"]
            copy(request, context, parent, event, targets)

    else:
        form = OrgaCopyForm(context=context)

    context["form"] = form

    return render(request, "larpmanager/orga/copy.html", context)


def get_all_fields_from_form(form_class: Any, context: dict[str, Any]) -> Any:
    """Return names of all available fields from given Form instance."""
    fields = list(form_class(context=context).base_fields)

    for field_name in list(form_class(context=context).declared_fields):
        if field_name not in fields:
            fields.append(field_name)

    for excluded_field in ["slug"]:
        if excluded_field in fields:
            fields.remove(excluded_field)

    return fields
