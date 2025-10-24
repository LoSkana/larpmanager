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


def _apply_modifier_cost(
    ability,
    mods_by_ability: dict[int, list[tuple]],
    current_char_abilities: set[int],
    current_char_choices: set[int],
) -> None:
    """Apply the first matching modifier cost to an ability.

    Iterates through modifiers for the given ability and applies the cost from
    the first modifier whose prerequisites and requirements are satisfied.

    Args:
        ability: Ability object to modify.
        mods_by_ability: Mapping of ability IDs to lists of (cost, prereq_ids, req_ids) tuples.
        current_char_abilities: Set of ability IDs the character currently has.
        current_char_choices: Set of choice IDs the character currently has.
    """
    # Look only at modifiers for this specific ability
    for cost, prereq_ids, req_ids in mods_by_ability.get(ability.id, ()):
        # Check if ability prerequisites are met
        if prereq_ids and not prereq_ids.issubset(current_char_abilities):
            continue
        # Check if choice requirements are met
        if req_ids and not req_ids.issubset(current_char_choices):
            continue
        # Apply the cost from the first valid modifier
        ability.cost = cost
        break  # First valid wins


def get_free_abilities(char: Character) -> list:
    """Return the list of free abilities for a character."""
    config_name = _free_abilities_idx()
    val = char.get_config(config_name, "[]")
    return ast.literal_eval(val)


def _free_abilities_idx():
    return "free_abilities"


def set_free_abilities(char: Character, frees: list[int]) -> None:
    """Save free abilities for a character."""
    config_name = _free_abilities_idx()
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


def _handle_free_abilities(char):
    """
    Handle free abilities that characters should automatically receive.

    Args:
        char: Character instance to process
    """
    free_abilities = get_free_abilities(char)

    # look for available ability with cost 0, and not already in the free list: get them!
    for ability in get_available_ability_px(char, 0):
        if ability.visible and ability.cost == 0:
            if ability.id not in free_abilities:
                char.px_ability_list.add(ability)
                free_abilities.append(ability.id)

    # look for current abilities with cost non 0, yet got in the past as free: remove them!
    for ability in get_current_ability_px(char):
        if ability.visible and ability.cost > 0:
            if ability.id in free_abilities:
                removed_ids = remove_char_ability(char, ability.id)
                free_abilities = list(set(free_abilities) - set(removed_ids))

    set_free_abilities(char, free_abilities)


def get_current_ability_px(char: Character) -> list[AbilityPx]:
    """
    Get current abilities with modified costs for a character.

    Retrieves character abilities and applies cost modifications based on
    character context including current abilities, choices, and modifiers.

    Args:
        char: The character to get abilities for

    Returns:
        List of abilities with modified costs applied
    """
    # Build the context for PX calculations including current abilities and modifiers
    current_char_abilities, current_char_choices, mods_by_ability = _build_px_context(char)

    # Get character abilities ordered by name, only fetching needed fields for performance
    abilities_qs = char.px_ability_list.only("id", "cost").order_by("name")

    # Process each ability and apply cost modifications
    abilities = []
    for ability in abilities_qs:
        # Apply modifier-based cost adjustments based on character context
        _apply_modifier_cost(ability, mods_by_ability, current_char_abilities, current_char_choices)
        abilities.append(ability)
    return abilities


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
    prereq_ids = {a.id for a in ability.prerequisites.all()}

    # Extract requirement IDs from the ability
    requirements_ids = {o.id for o in ability.requirements.all()}

    # Check if all prerequisites and requirements are satisfied
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
    computed_ques = event.get_elements(WritingQuestion).filter(typ=WritingQuestionType.COMPUTED)
    values = {question.id: Decimal(0) for question in computed_ques}

    # Retrieve character's ability IDs for rule filtering
    ability_ids = char.px_ability_list.values_list("pk", flat=True)

    # Get applicable rules: either global rules or rules matching character's abilities
    rules = (
        event.get_elements(RulePx)
        .filter(Q(abilities__isnull=True) | Q(abilities__in=ability_ids))
        .distinct()
        .order_by("order")
    )

    # Define mathematical operations with division-by-zero protection
    ops = {
        Operation.ADDITION: lambda x, y: x + y,
        Operation.SUBTRACTION: lambda x, y: x - y,
        Operation.MULTIPLICATION: lambda x, y: x * y,
        Operation.DIVISION: lambda x, y: x / y if y != 0 else x,
    }

    # Apply each rule to update the corresponding computed field value
    for rule in rules:
        f_id = rule.field.id
        values[f_id] = ops.get(rule.operation, lambda x, y: x)(values[f_id], rule.amount)

    # Save computed values as WritingAnswer objects with clean formatting
    for question_id, value in values.items():
        (qa, created) = WritingAnswer.objects.get_or_create(question_id=question_id, element_id=char.id)
        # Format decimal value and remove trailing zeros/decimal point
        qa.text = format(value, "f").rstrip("0").rstrip(".")
        qa.save()


def add_char_addit(char):
    """
    Add additional configuration data to character object.

    Args:
        char: Character instance to add additional data to
    """
    char.addit = {}
    configs = CharacterConfig.objects.filter(character__id=char.id)
    if not configs.count():
        calculate_character_experience_points(char)
        configs = CharacterConfig.objects.filter(character__id=char.id)

    for config in configs:
        char.addit[config.name] = config.value


def remove_char_ability(char, ability_id):
    """
    Remove character ability and all dependent abilities.

    Args:
        char: Character instance
        ability_id: ID of ability to remove
    """
    to_remove_ids = {ability_id}

    while True:
        dependents_qs = (
            char.px_ability_list.filter(prerequisites__in=to_remove_ids).values_list("id", flat=True).distinct()
        )
        new_ids = set(dependents_qs) - to_remove_ids
        if not new_ids:
            break
        to_remove_ids |= new_ids

    # atomic removal
    with transaction.atomic():
        char.px_ability_list.remove(*to_remove_ids)

    return to_remove_ids


def update_characters_experience_on_ability_change(instance):
    for char in instance.characters.all():
        calculate_character_experience_points(char)


def refresh_delivery_characters(instance):
    for char in instance.characters.all():
        char.save()


def update_characters_experience_on_rule_change(instance: RulePx) -> None:
    """Updates experience points for all characters when experience rules change."""
    # Get the event containing the rule
    event = instance.event.get_class_parent(RulePx)

    # Recalculate experience for all characters in the event
    for char in event.get_elements(Character).all():
        calculate_character_experience_points(char)


def update_characters_experience_on_modifier_change(instance: ModifierPx) -> None:
    """Update experience points for all characters when a modifier changes."""
    event = instance.event.get_class_parent(ModifierPx)
    for char in event.get_elements(Character).all():
        calculate_character_experience_points(char)
