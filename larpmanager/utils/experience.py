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

from larpmanager.cache.config import get_event_config, save_all_element_configs, save_single_config
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


def _build_px_context(character) -> tuple[set[int], set[int], dict[int, list[tuple[int, set[int], set[int]]]]]:
    """Build context for character experience point calculations.

    Gathers character abilities, choices, and modifiers with optimized queries
    to create the foundation for PX cost and availability calculations.

    Args:
        character: Character instance for which to build the PX context.

    Returns:
        A tuple containing:
        - Set of ability IDs already learned by the character
        - Set of option IDs selected for the character
        - Dictionary mapping ability IDs to lists of modifier tuples (cost, prerequisites, requirements)
    """
    # Get all abilities already learned by the character
    # This creates a set of primary keys for efficient lookup operations
    current_character_abilities = set(character.px_ability_list.values_list("pk", flat=True))

    # Get the options selected for the character from writing choices
    # Filter by character ID and applicable question type for accuracy
    current_character_choices = set(
        WritingChoice.objects.filter(
            element_id=character.id, question__applicable=QuestionApplicable.CHARACTER
        ).values_list("option_id", flat=True)
    )

    # Get all modifiers with optimized prefetch for related objects
    # Use only() to limit fields and prefetch_related to avoid N+1 queries
    all_modifiers = (
        character.event.get_elements(ModifierPx)
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
    modifiers_by_ability = defaultdict(list)
    for modifier in all_modifiers:
        # Extract IDs from prefetched objects to avoid additional queries
        # Use list comprehension and set comprehension for performance
        ability_ids = [ability.id for ability in modifier.abilities.all()]
        prerequisite_ids = {ability.id for ability in modifier.prerequisites.all()}
        requirement_ids = {option.id for option in modifier.requirements.all()}

        # Create payload tuple with modifier data for easy access
        payload = (modifier.cost, prerequisite_ids, requirement_ids)

        # Map each ability to its applicable modifiers
        for ability_id in ability_ids:
            modifiers_by_ability[ability_id].append(payload)

    return current_character_abilities, current_character_choices, modifiers_by_ability


def _apply_modifier_cost(
    ability,
    modifiers_by_ability_id: dict[int, list[tuple]],
    character_ability_ids: set[int],
    character_choice_ids: set[int],
) -> None:
    """Apply the first matching modifier cost to an ability.

    Iterates through modifiers for the given ability and applies the cost from
    the first modifier whose prerequisites and requirements are satisfied.

    Args:
        ability: Ability object to modify.
        modifiers_by_ability_id: Mapping of ability IDs to lists of (cost, prereq_ids, req_ids) tuples.
        character_ability_ids: Set of ability IDs the character currently has.
        character_choice_ids: Set of choice IDs the character currently has.
    """
    # Look only at modifiers for this specific ability
    for cost, prerequisite_ability_ids, required_choice_ids in modifiers_by_ability_id.get(ability.id, ()):
        # Check if ability prerequisites are met
        if prerequisite_ability_ids and not prerequisite_ability_ids.issubset(character_ability_ids):
            continue
        # Check if choice requirements are met
        if required_choice_ids and not required_choice_ids.issubset(character_choice_ids):
            continue
        # Apply the cost from the first valid modifier
        ability.cost = cost
        break  # First valid wins


def get_free_abilities(char: Character) -> list:
    """Return the list of free abilities for a character."""
    config_name = _free_abilities_cache_key()
    config_value = char.get_config(config_name, "[]")
    return ast.literal_eval(config_value)


def _free_abilities_cache_key() -> str:
    # Return cache key for free abilities
    return "free_abilities"


def set_free_abilities(char: Character, frees: list[int]) -> None:
    """Save free abilities for a character."""
    config_name = _free_abilities_cache_key()
    save_single_config(char, config_name, json.dumps(frees))


def calculate_character_experience_points(character):
    """
    Update character experience points and apply ability calculations.

    Args:
        character: Character instance to update
    """
    if "px" not in get_event_features(character.event_id):
        return

    starting_experience_points = get_event_config(character.event_id, "px_start", 0)

    _handle_free_abilities(character)

    current_abilities = get_current_ability_px(character)

    total_experience_points = int(starting_experience_points) + (
        character.px_delivery_list.aggregate(total=Coalesce(Sum("amount"), 0))["total"] or 0
    )
    used_experience_points = sum(ability.cost for ability in current_abilities)

    experience_data = {
        "px_tot": total_experience_points,
        "px_used": used_experience_points,
        "px_avail": total_experience_points - used_experience_points,
    }

    save_all_element_configs(character, experience_data)

    apply_rules_computed(character)


def _handle_free_abilities(character):
    """
    Handle free abilities that characters should automatically receive.

    Args:
        character: Character instance to process
    """
    free_ability_ids = get_free_abilities(character)

    # look for available ability with cost 0, and not already in the free list: get them!
    for ability in get_available_ability_px(character, 0):
        if ability.visible and ability.cost == 0:
            if ability.id not in free_ability_ids:
                character.px_ability_list.add(ability)
                free_ability_ids.append(ability.id)

    # look for current abilities with cost non 0, yet got in the past as free: remove them!
    for ability in get_current_ability_px(character):
        if ability.visible and ability.cost > 0:
            if ability.id in free_ability_ids:
                removed_ability_ids = remove_char_ability(character, ability.id)
                free_ability_ids = list(set(free_ability_ids) - set(removed_ability_ids))

    set_free_abilities(character, free_ability_ids)


def get_current_ability_px(character: Character) -> list[AbilityPx]:
    """
    Get current abilities with modified costs for a character.

    Retrieves character abilities and applies cost modifications based on
    character context including current abilities, choices, and modifiers.

    Args:
        character: The character to get abilities for

    Returns:
        List of abilities with modified costs applied
    """
    # Build the context for PX calculations including current abilities and modifiers
    current_character_abilities, current_character_choices, modifiers_by_ability = _build_px_context(character)

    # Get character abilities ordered by name, only fetching needed fields for performance
    abilities_queryset = character.px_ability_list.only("id", "cost").order_by("name")

    # Process each ability and apply cost modifications
    abilities_with_modified_costs = []
    for ability in abilities_queryset:
        # Apply modifier-based cost adjustments based on character context
        _apply_modifier_cost(ability, modifiers_by_ability, current_character_abilities, current_character_choices)
        abilities_with_modified_costs.append(ability)
    return abilities_with_modified_costs


def check_available_ability_px(ability, current_char_abilities, current_char_choices) -> bool:
    """Check if an ability is available based on prerequisites and requirements.

    Args:
        ability: Ability to check availability for
        current_char_abilities: Set of current character abilities
        current_char_choices: Set of current character choices

    Returns:
        True if all prerequisites and requirements are met, False otherwise
    """
    # Extract prerequisite IDs from the ability
    prerequisite_ids = {ability.id for ability in ability.prerequisites.all()}

    # Extract requirement IDs from the ability
    requirement_ids = {option.id for option in ability.requirements.all()}

    # Check if all prerequisites and requirements are satisfied
    return prerequisite_ids.issubset(current_char_abilities) and requirement_ids.issubset(current_char_choices)


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
    current_character_abilities, current_character_choices, modifiers_by_ability = _build_px_context(char)

    # Calculate available PX if not provided
    if px_avail is None:
        add_char_addit(char)
        px_avail = int(char.addit.get("px_avail", 0))

    # Get all visible abilities excluding those already owned by character
    all_abilities = (
        char.event.get_elements(AbilityPx)
        .filter(visible=True)
        .exclude(pk__in=current_character_abilities)
        .select_related("typ")
        .order_by("name")
        .prefetch_related(
            Prefetch("prerequisites", queryset=AbilityPx.objects.only("id")),
            Prefetch("requirements", queryset=WritingOption.objects.only("id")),
        )
    )

    available_abilities = []
    for ability in all_abilities:
        # Check if character meets prerequisites and requirements
        if not check_available_ability_px(ability, current_character_abilities, current_character_choices):
            continue

        # Apply cost modifiers based on character's current state
        _apply_modifier_cost(ability, modifiers_by_ability, current_character_abilities, current_character_choices)

        # Filter out abilities that cost more than available PX
        if ability.cost > px_avail:
            continue

        available_abilities.append(ability)

    return available_abilities


def on_experience_characters_m2m_changed(
    sender, instance: Optional[DeliveryPx], action: str, pk_set: Optional[set], **kwargs
) -> None:
    """Handle m2m changes for experience-character relationships."""
    # Only process relevant m2m actions
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    # Handle direct Character instance updates
    if isinstance(instance, Character):
        calculate_character_experience_points(instance)
    else:
        # Get characters from pk_set or instance relationship
        if pk_set:
            characters = Character.objects.filter(pk__in=pk_set)
        else:
            characters = instance.characters.all()

        # Update experience points for each affected character
        for char in characters:
            calculate_character_experience_points(char)


def on_rule_abilities_m2m_changed(
    sender: type, instance: RulePx, action: str, pk_set: set[int] | None, **kwargs
) -> None:
    """Handle changes to rule abilities many-to-many relationships.

    Recalculates experience points for all characters in the event when
    rule abilities are added, removed, or cleared.
    """
    # Only process meaningful m2m changes
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    # Get the parent event containing this rule
    event = instance.event.get_class_parent(RulePx)

    # Recalculate experience for all characters in the event
    for char in event.get_elements(Character).all():
        calculate_character_experience_points(char)


def on_modifier_abilities_m2m_changed(
    sender: type, instance: ModifierPx, action: str, pk_set: set[int] | None, **kwargs
) -> None:
    """Handle modifier abilities m2m changes by recalculating character experience."""
    # Only process relevant m2m actions
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    # Get the event containing this modifier
    event = instance.event.get_class_parent(ModifierPx)

    # Recalculate experience for all characters in the event
    for char in event.get_elements(Character).all():
        calculate_character_experience_points(char)


def apply_rules_computed(char) -> None:
    """
    Apply computed field rules to calculate character statistics.

    This function processes all computed writing questions for a character's event,
    applies mathematical rules based on the character's abilities, and saves the
    calculated values as writing answers.

    Args:
        char: Character instance to apply rules to. Must have an associated event
              and ability list.

    Returns:
        None: Function modifies character data in-place by creating/updating
              WritingAnswer objects.

    Note:
        Division operations are safe-guarded against division by zero.
        Computed values are formatted to remove trailing zeros and decimal points.
    """
    # Get the character's event and initialize computed question values
    event = char.event
    computed_questions = event.get_elements(WritingQuestion).filter(typ=WritingQuestionType.COMPUTED)
    computed_field_values = {question.id: Decimal(0) for question in computed_questions}

    # Retrieve character's ability IDs for rule filtering
    character_ability_ids = char.px_ability_list.values_list("pk", flat=True)

    # Get applicable rules: either global rules or rules matching character's abilities
    applicable_rules = (
        event.get_elements(RulePx)
        .filter(Q(abilities__isnull=True) | Q(abilities__in=character_ability_ids))
        .distinct()
        .order_by("order")
    )

    # Define mathematical operations with division-by-zero protection
    operations = {
        Operation.ADDITION: lambda current_value, rule_amount: current_value + rule_amount,
        Operation.SUBTRACTION: lambda current_value, rule_amount: current_value - rule_amount,
        Operation.MULTIPLICATION: lambda current_value, rule_amount: current_value * rule_amount,
        Operation.DIVISION: lambda current_value, rule_amount: current_value / rule_amount
        if rule_amount != 0
        else current_value,
    }

    # Apply each rule to update the corresponding computed field value
    for rule in applicable_rules:
        field_id = rule.field.id
        computed_field_values[field_id] = operations.get(
            rule.operation, lambda current_value, rule_amount: current_value
        )(computed_field_values[field_id], rule.amount)

    # Save computed values as WritingAnswer objects with clean formatting
    for question_id, computed_value in computed_field_values.items():
        (writing_answer, created) = WritingAnswer.objects.get_or_create(question_id=question_id, element_id=char.id)
        # Format decimal value and remove trailing zeros/decimal point
        writing_answer.text = format(computed_value, "f").rstrip("0").rstrip(".")
        writing_answer.save()


def add_char_addit(character):
    """
    Add additional configuration data to character object.

    Args:
        character: Character instance to add additional data to
    """
    character.addit = {}
    character_configs = CharacterConfig.objects.filter(character__id=character.id)
    if not character_configs.count():
        calculate_character_experience_points(character)
        character_configs = CharacterConfig.objects.filter(character__id=character.id)

    for character_config in character_configs:
        character.addit[character_config.name] = character_config.value


def remove_char_ability(char, ability_id):
    """
    Remove character ability and all dependent abilities.

    Args:
        char: Character instance
        ability_id: ID of ability to remove
    """
    ability_ids_to_remove = {ability_id}

    while True:
        dependent_abilities_queryset = (
            char.px_ability_list.filter(prerequisites__in=ability_ids_to_remove).values_list("id", flat=True).distinct()
        )
        newly_found_dependent_ids = set(dependent_abilities_queryset) - ability_ids_to_remove
        if not newly_found_dependent_ids:
            break
        ability_ids_to_remove |= newly_found_dependent_ids

    # atomic removal
    with transaction.atomic():
        char.px_ability_list.remove(*ability_ids_to_remove)

    return ability_ids_to_remove


def update_characters_experience_on_ability_change(instance: AbilityPx) -> None:
    """Update experience points for all characters with this ability."""
    # Recalculate experience for each character that has this ability
    for character in instance.characters.all():
        calculate_character_experience_points(character)


def refresh_delivery_characters(instance: DeliveryPx) -> None:
    """Refresh all characters associated with this delivery option."""
    for character in instance.characters.all():
        character.save()


def update_characters_experience_on_rule_change(instance: RulePx) -> None:
    """Updates experience points for all characters when experience rules change."""
    # Get the event containing the rule
    parent_event = instance.event.get_class_parent(RulePx)

    # Recalculate experience for all characters in the event
    for character in parent_event.get_elements(Character).all():
        calculate_character_experience_points(character)


def update_characters_experience_on_modifier_change(instance: ModifierPx) -> None:
    """Update experience points for all characters when a modifier changes."""
    parent_event = instance.event.get_class_parent(ModifierPx)
    for character in parent_event.get_elements(Character).all():
        calculate_character_experience_points(character)
