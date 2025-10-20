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
import ast
import json
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.db.models.functions import Coalesce

from larpmanager.cache.config import save_all_element_configs, save_single_config
from larpmanager.cache.feature import get_event_features
from larpmanager.models.experience import AbilityPx, DeliveryPx, ModifierPx, Operation, RulePx
from larpmanager.models.form import (
    QuestionApplicable,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.writing import Character, CharacterConfig


def _build_px_context(char) -> tuple[set[int], set[int], dict[int, list[tuple[int, set[int], set[int]]]]]:
    """Build context for character experience point calculations.

    Gathers character abilities, choices, and modifiers with optimized queries
    to create the foundation for PX cost and availability calculations.

    Args:
        char: Character instance for which to build the PX context.

    Returns:
        A tuple containing:
        - Set of ability IDs already learned by the character
        - Set of option IDs selected for the character
        - Dictionary mapping ability IDs to lists of modifier tuples (cost, prerequisites, requirements)
    """
    # Get all abilities already learned by the character
    # This creates a set of primary keys for efficient lookup operations
    current_char_abilities = set(char.px_ability_list.values_list("pk", flat=True))

    # Get the options selected for the character from writing choices
    # Filter by character ID and applicable question type for accuracy
    current_char_choices = set(
        WritingChoice.objects.filter(element_id=char.id, question__applicable=QuestionApplicable.CHARACTER).values_list(
            "option_id", flat=True
        )
    )

    # Get all modifiers with optimized prefetch for related objects
    # Use only() to limit fields and prefetch_related to avoid N+1 queries
    all_modifiers = (
        char.event.get_elements(ModifierPx)
        .only("id", "order", "cost")
        .order_by("order")
        .prefetch_related(
            Prefetch("abilities", queryset=AbilityPx.objects.only("id")),
            Prefetch("prerequisites", queryset=AbilityPx.objects.only("id")),
            Prefetch("requirements", queryset=WritingOption.objects.only("id")),
        )
    )

    # Build mapping for cost, prerequisites, and requirements by ability
    # This creates an efficient lookup structure for modifier calculations
    mods_by_ability = defaultdict(list)
    for m in all_modifiers:
        # Extract IDs from prefetched objects to avoid additional queries
        # Use list comprehension and set comprehension for performance
        ability_ids = [a.id for a in m.abilities.all()]
        prereq_ids = {a.id for a in m.prerequisites.all()}
        req_ids = {o.id for o in m.requirements.all()}

        # Create payload tuple with modifier data for easy access
        payload = (m.cost, prereq_ids, req_ids)

        # Map each ability to its applicable modifiers
        for aid in ability_ids:
            mods_by_ability[aid].append(payload)

    return current_char_abilities, current_char_choices, mods_by_ability


def _apply_modifier_cost(ability, mods_by_ability, current_char_abilities, current_char_choices):
    # look only inf modifiers for that ability
    for cost, prereq_ids, req_ids in mods_by_ability.get(ability.id, ()):
        if prereq_ids and not prereq_ids.issubset(current_char_abilities):
            continue
        if req_ids and not req_ids.issubset(current_char_choices):
            continue
        ability.cost = cost
        break  # first valid wins


def get_free_abilities(char):
    config_name = _free_abilities_idx()
    val = char.get_config(config_name, "[]")
    return ast.literal_eval(val)


def _free_abilities_idx():
    return "free_abilities"


def set_free_abilities(char, frees):
    config_name = _free_abilities_idx()
    save_single_config(char, config_name, json.dumps(frees))


def calculate_character_experience_points(char: Character) -> None:
    """
    Update character experience points and apply ability calculations.

    This function calculates the total, used, and available experience points
    for a character, updates their configuration, and applies computed rules.
    Only processes characters for events that have the "px" feature enabled.

    Args:
        char: Character instance to update with experience point calculations

    Returns:
        None
    """
    # Check if experience points feature is enabled for this event
    if "px" not in get_event_features(char.event_id):
        return

    # Get starting experience points from event configuration
    start = char.event.get_config("px_start", 0)

    # Handle any free abilities that don't cost experience points
    _handle_free_abilities(char)

    # Get all current abilities and their experience point costs
    abilities = get_current_ability_px(char)

    # Calculate total experience points from starting amount and deliveries
    px_tot = int(start) + (char.px_delivery_list.aggregate(t=Coalesce(Sum("amount"), 0))["t"] or 0)

    # Calculate used experience points from ability costs
    px_used = sum(a.cost for a in abilities)

    # Prepare experience point summary for character configuration
    addit = {
        "px_tot": px_tot,
        "px_used": px_used,
        "px_avail": px_tot - px_used,
    }

    # Save experience point calculations to character configuration
    save_all_element_configs(char, addit)

    # Apply any computed rules based on updated experience points
    apply_rules_computed(char)


def _handle_free_abilities(char: Character) -> None:
    """
    Handle free abilities that characters should automatically receive.

    This function manages the automatic assignment and removal of free abilities
    based on their current cost. Abilities with cost 0 are automatically added
    to the character, while abilities that previously had cost 0 but now have
    a positive cost are removed.

    Args:
        char: Character instance to process for free ability management

    Returns:
        None
    """
    # Get the current list of free abilities for this character
    free_abilities = get_free_abilities(char)

    # Process available abilities with cost 0 - these should be automatically assigned
    # Look for abilities that are visible, cost 0, and not already in the free list
    for ability in get_available_ability_px(char, 0):
        if ability.visible and ability.cost == 0:
            # Add ability to character if not already marked as free
            if ability.id not in free_abilities:
                char.px_ability_list.add(ability)
                free_abilities.append(ability.id)

    # Process current abilities that may need removal
    # Look for abilities that now cost more than 0 but were previously free
    for ability in get_current_ability_px(char):
        if ability.visible and ability.cost > 0:
            # Remove ability if it was previously free but now has a cost
            if ability.id in free_abilities:
                removed_ids = remove_char_ability(char, ability.id)
                # Update free abilities list by removing all removed IDs
                free_abilities = list(set(free_abilities) - set(removed_ids))

    # Save the updated free abilities list back to the character
    set_free_abilities(char, free_abilities)


def get_current_ability_px(char: Character) -> list:
    """Get current ability PX costs for a character with applied modifiers.

    Retrieves all abilities available to the character and applies any cost
    modifiers based on the character's current state and choices.

    Args:
        char: Character instance to get abilities for

    Returns:
        list: List of ability objects with modified costs applied
    """
    # Build context for current character state and modifiers
    current_char_abilities, current_char_choices, mods_by_ability = _build_px_context(char)

    # Query abilities with only required fields for performance
    abilities_qs = char.px_ability_list.only("id", "cost").order_by("name")

    # Process each ability and apply cost modifiers
    abilities = []
    for ability in abilities_qs:
        # Apply any cost modifiers based on character state
        _apply_modifier_cost(ability, mods_by_ability, current_char_abilities, current_char_choices)
        abilities.append(ability)
    return abilities


def check_available_ability_px(ability, current_char_abilities, current_char_choices):
    prereq_ids = {a.id for a in ability.prerequisites.all()}
    requirements_ids = {o.id for o in ability.requirements.all()}
    return prereq_ids.issubset(current_char_abilities) and requirements_ids.issubset(current_char_choices)


def get_available_ability_px(char, px_avail: int | None = None) -> list:
    """Get list of abilities available for purchase with character's PX.

    Retrieves all visible abilities that the character can purchase based on their
    available PX points, prerequisites, and requirements. Applies cost modifiers
    and filters out unaffordable abilities.

    Args:
        char: Character instance to check abilities for
        px_avail: Available PX points. If None, calculated from character's
            additional data

    Returns:
        List of AbilityPx instances that the character can purchase with their
        current PX and that meet all prerequisites and requirements
    """
    # Build context with current character abilities, choices, and modifiers
    current_char_abilities, current_char_choices, mods_by_ability = _build_px_context(char)

    # Calculate available PX if not provided
    if px_avail is None:
        add_char_addit(char)
        px_avail = int(char.addit.get("px_avail", 0))

    # Get all visible abilities excluding those already owned by character
    all_abilities = (
        char.event.get_elements(AbilityPx)
        .filter(visible=True)
        .exclude(pk__in=current_char_abilities)
        .select_related("typ")
        .order_by("name")
        .prefetch_related(
            Prefetch("prerequisites", queryset=AbilityPx.objects.only("id")),
            Prefetch("requirements", queryset=WritingOption.objects.only("id")),
        )
    )

    abilities = []
    for ability in all_abilities:
        # Check if character meets prerequisites and requirements
        if not check_available_ability_px(ability, current_char_abilities, current_char_choices):
            continue

        # Apply cost modifiers based on character's current state
        _apply_modifier_cost(ability, mods_by_ability, current_char_abilities, current_char_choices)

        # Filter out abilities that cost more than available PX
        if ability.cost > px_avail:
            continue

        abilities.append(ability)

    return abilities


def on_experience_characters_m2m_changed(sender, instance: Optional[DeliveryPx], action, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    if isinstance(instance, Character):
        calculate_character_experience_points(instance)
    else:
        if pk_set:
            characters = Character.objects.filter(pk__in=pk_set)
        else:
            characters = instance.characters.all()

        for char in characters:
            calculate_character_experience_points(char)


def on_rule_abilities_m2m_changed(sender, instance, action, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    event = instance.event.get_class_parent(RulePx)
    for char in event.get_elements(Character).all():
        calculate_character_experience_points(char)


def on_modifier_abilities_m2m_changed(sender, instance, action, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    event = instance.event.get_class_parent(ModifierPx)
    for char in event.get_elements(Character).all():
        calculate_character_experience_points(char)


def apply_rules_computed(char: Character) -> None:
    """
    Apply computed field rules to calculate character statistics.

    This function processes computation rules for a character's event, calculating
    values based on the character's abilities and applying mathematical operations
    defined in the rules. The computed values are then saved as WritingAnswer objects.

    Args:
        char: Character instance to apply rules to. Must have an associated event
              and px_ability_list relationship.

    Returns:
        None: Function modifies the database state by creating/updating WritingAnswer objects.

    Note:
        Rules are applied in order as defined by the 'order' field. Division by zero
        is handled by keeping the original value unchanged.
    """
    # Get the character's event and initialize computed questions
    event = char.event
    computed_ques = event.get_elements(WritingQuestion).filter(typ=WritingQuestionType.COMPUTED)

    # Initialize values dictionary with zero for each computed question
    values = {question.id: Decimal(0) for question in computed_ques}

    # Get character's ability IDs for rule filtering
    ability_ids = char.px_ability_list.values_list("pk", flat=True)

    # Filter rules that apply to this character (no abilities specified or character has the ability)
    rules = (
        event.get_elements(RulePx)
        .filter(Q(abilities__isnull=True) | Q(abilities__in=ability_ids))
        .distinct()
        .order_by("order")
    )

    # Define mathematical operations with division by zero protection
    ops = {
        Operation.ADDITION: lambda x, y: x + y,
        Operation.SUBTRACTION: lambda x, y: x - y,
        Operation.MULTIPLICATION: lambda x, y: x * y,
        Operation.DIVISION: lambda x, y: x / y if y != 0 else x,
    }

    # Apply each rule in order to calculate field values
    for rule in rules:
        f_id = rule.field.id
        values[f_id] = ops.get(rule.operation, lambda x, y: x)(values[f_id], rule.amount)

    # Save computed values as WritingAnswer objects
    for question_id, value in values.items():
        (qa, created) = WritingAnswer.objects.get_or_create(question_id=question_id, element_id=char.id)

        # Format decimal value removing trailing zeros and decimal point if integer
        qa.text = format(value, "f").rstrip("0").rstrip(".")
        qa.save()


def add_char_addit(char: Character) -> None:
    """
    Add additional configuration data to character object.

    This function populates the character's `addit` attribute with configuration
    data from CharacterConfig objects. If no configurations exist, it calculates
    experience points first to generate the necessary configs.

    Args:
        char (Character): Character instance to add additional data to.
            The character object will be modified in-place with an `addit`
            attribute containing configuration key-value pairs.

    Returns:
        None: The function modifies the character object in-place.

    Note:
        The `addit` attribute will be a dictionary where keys are config names
        and values are the corresponding config values.
    """
    # Initialize the additional data dictionary
    char.addit = {}

    # Fetch existing character configurations
    configs = CharacterConfig.objects.filter(character__id=char.id)

    # If no configs exist, calculate experience points to generate them
    if not configs.count():
        calculate_character_experience_points(char)
        configs = CharacterConfig.objects.filter(character__id=char.id)

    # Populate the addit dictionary with config name-value pairs
    for config in configs:
        char.addit[config.name] = config.value


def remove_char_ability(char: Character, ability_id: int) -> set[int]:
    """
    Remove character ability and all dependent abilities.

    This function recursively identifies and removes abilities that depend on the
    specified ability, ensuring no orphaned dependencies remain.

    Args:
        char: Character instance with px_ability_list relationship
        ability_id: ID of the ability to remove

    Returns:
        Set of ability IDs that were removed, including the original ability
        and all its dependents

    Note:
        The removal is performed atomically to ensure database consistency.
    """
    # Start with the target ability to remove
    to_remove_ids = {ability_id}

    # Recursively find all dependent abilities
    while True:
        # Query for abilities that have prerequisites in our removal set
        dependents_qs = (
            char.px_ability_list.filter(prerequisites__in=to_remove_ids).values_list("id", flat=True).distinct()
        )

        # Find new dependencies not already marked for removal
        new_ids = set(dependents_qs) - to_remove_ids
        if not new_ids:
            break

        # Add newly found dependencies to removal set
        to_remove_ids |= new_ids

    # Perform atomic removal to ensure database consistency
    with transaction.atomic():
        char.px_ability_list.remove(*to_remove_ids)

    return to_remove_ids


def update_characters_experience_on_ability_change(instance):
    for char in instance.characters.all():
        calculate_character_experience_points(char)


def refresh_delivery_characters(instance):
    for char in instance.characters.all():
        char.save()


def update_characters_experience_on_rule_change(instance):
    event = instance.event.get_class_parent(RulePx)
    for char in event.get_elements(Character).all():
        calculate_character_experience_points(char)


def update_characters_experience_on_modifier_change(instance):
    event = instance.event.get_class_parent(ModifierPx)
    for char in event.get_elements(Character).all():
        calculate_character_experience_points(char)
