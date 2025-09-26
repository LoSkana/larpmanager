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


def _build_px_context(char):
    """Build context for character experience point calculations.

    Gathers character abilities, choices, and modifiers with optimized queries
    to create the foundation for PX cost and availability calculations.
    """
    # get all abilities already learned by the character
    current_char_abilities = set(char.px_ability_list.values_list("pk", flat=True))

    # get the options selected for the character
    current_char_choices = set(
        WritingChoice.objects.filter(element_id=char.id, question__applicable=QuestionApplicable.CHARACTER).values_list(
            "option_id", flat=True
        )
    )

    # get all modifiers
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

    # build mapping for cost, prereq, reqs
    mods_by_ability = defaultdict(list)
    for m in all_modifiers:
        # Nessuna query extra: usa i risultati del prefetch in memoria
        ability_ids = [a.id for a in m.abilities.all()]
        prereq_ids = {a.id for a in m.prerequisites.all()}
        req_ids = {o.id for o in m.requirements.all()}
        payload = (m.cost, prereq_ids, req_ids)
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


def update_px(char):
    """
    Update character experience points and apply ability calculations.

    Args:
        char: Character instance to update
    """
    start = char.event.get_config("px_start", 0)

    _handle_free_abilities(char)

    abilities = get_current_ability_px(char)

    px_tot = int(start) + (char.px_delivery_list.aggregate(t=Coalesce(Sum("amount"), 0))["t"] or 0)
    px_used = sum(a.cost for a in abilities)

    addit = {
        "px_tot": px_tot,
        "px_used": px_used,
        "px_avail": px_tot - px_used,
    }

    save_all_element_configs(char, addit)

    apply_rules_computed(char)


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


def get_current_ability_px(char):
    current_char_abilities, current_char_choices, mods_by_ability = _build_px_context(char)

    abilities_qs = char.px_ability_list.only("id", "cost").order_by("name")

    abilities = []
    for ability in abilities_qs:
        _apply_modifier_cost(ability, mods_by_ability, current_char_abilities, current_char_choices)
        abilities.append(ability)
    return abilities


def check_available_ability_px(ability, current_char_abilities, current_char_choices):
    prereq_ids = {a.id for a in ability.prerequisites.all()}
    requirements_ids = {o.id for o in ability.requirements.all()}
    return prereq_ids.issubset(current_char_abilities) and requirements_ids.issubset(current_char_choices)


def get_available_ability_px(char, px_avail=None):
    """Get list of abilities available for purchase with character's PX.

    Args:
        char: Character instance
        px_avail: Available PX points (calculated if None)

    Returns:
        List of AbilityPx instances that can be purchased
    """
    current_char_abilities, current_char_choices, mods_by_ability = _build_px_context(char)

    if px_avail is None:
        add_char_addit(char)
        px_avail = int(char.addit.get("px_avail", 0))

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
        if not check_available_ability_px(ability, current_char_abilities, current_char_choices):
            continue

        _apply_modifier_cost(ability, mods_by_ability, current_char_abilities, current_char_choices)

        if ability.cost > px_avail:
            continue

        abilities.append(ability)

    return abilities


def px_characters_changed(sender, instance: Optional[DeliveryPx], action, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    if isinstance(instance, Character):
        update_px(instance)
    else:
        if pk_set:
            characters = Character.objects.filter(pk__in=pk_set)
        else:
            characters = instance.characters.all()

        for char in characters:
            update_px(char)


def rule_abilities_changed(sender, instance, action, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    event = instance.event.get_class_parent(RulePx)
    for char in event.get_elements(Character).all():
        update_px(char)


def modifier_abilities_changed(sender, instance, action, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    event = instance.event.get_class_parent(ModifierPx)
    for char in event.get_elements(Character).all():
        update_px(char)


def apply_rules_computed(char):
    """
    Apply computed field rules to calculate character statistics.

    Args:
        char: Character instance to apply rules to
    """
    # save computed field
    event = char.event
    computed_ques = event.get_elements(WritingQuestion).filter(typ=WritingQuestionType.COMPUTED)
    values = {question.id: Decimal(0) for question in computed_ques}

    # apply rules
    ability_ids = char.px_ability_list.values_list("pk", flat=True)
    rules = (
        event.get_elements(RulePx)
        .filter(Q(abilities__isnull=True) | Q(abilities__in=ability_ids))
        .distinct()
        .order_by("order")
    )
    ops = {
        Operation.ADDITION: lambda x, y: x + y,
        Operation.SUBTRACTION: lambda x, y: x - y,
        Operation.MULTIPLICATION: lambda x, y: x * y,
        Operation.DIVISION: lambda x, y: x / y if y != 0 else x,
    }

    for rule in rules:
        f_id = rule.field.id
        values[f_id] = ops.get(rule.operation, lambda x, y: x)(values[f_id], rule.amount)

    for question_id, value in values.items():
        (qa, created) = WritingAnswer.objects.get_or_create(question_id=question_id, element_id=char.id)
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
        update_px(char)
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
