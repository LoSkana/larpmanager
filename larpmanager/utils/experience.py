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
from decimal import Decimal
from typing import Optional

from django.db.models import Prefetch, Q

from larpmanager.cache.config import save_all_element_configs
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


def update_px(char):
    start = char.event.get_config("px_start", 0)

    # if any ability is available with cost 0, get it
    for ability in get_available_ability_px(char, 0):
        if ability.cost == 0:
            char.px_ability_list.add(ability)

    abilities = get_current_ability_px(char)

    addit = {
        "px_tot": int(start) + sum(char.px_delivery_list.values_list("amount", flat=True)),
        "px_used": sum([ability.cost for ability in abilities]),
    }

    addit["px_avail"] = addit["px_tot"] - addit["px_used"]

    save_all_element_configs(char, addit)

    apply_rules_computed(char)


def get_current_ability_px(char):
    # get all abilities already learned by the character
    current_char_abilities = set(char.px_ability_list.values_list("pk", flat=True))

    # get the options selected for the character
    que = WritingChoice.objects.filter(element_id=char.id, question__applicable=QuestionApplicable.CHARACTER)
    current_char_choices = set(que.values_list("option_id", flat=True))

    # get all modifiers
    all_modifiers = (
        char.event.get_elements(ModifierPx)
        .order_by("order")
        .prefetch_related(
            Prefetch("abilities", queryset=AbilityPx.objects.only("id")),
            Prefetch("prerequisites", queryset=AbilityPx.objects.only("id")),
            Prefetch("requirements", queryset=WritingOption.objects.only("id")),
        )
    )

    abilities = []
    for ability in char.px_ability_list.all():
        # check modifiers to update cost
        check_modifier_ability_px(ability, all_modifiers, current_char_abilities, current_char_choices)
        abilities.append(ability)

    return abilities


def check_available_ability_px(ability, current_char_abilities, current_char_choices):
    prereq_ids = set(ability.prerequisites.values_list("id", flat=True))
    requirements_ids = set(ability.requirements.values_list("id", flat=True))
    return prereq_ids.issubset(current_char_abilities) and requirements_ids.issubset(current_char_choices)


def check_modifier_ability_px(ability, all_modifiers, current_char_abilities, current_char_choices):
    for modifier in all_modifiers:
        if ability.id not in modifier.abilities.values_list("id", flat=True):
            continue

        prereq_ids = set(modifier.prerequisites.values_list("id", flat=True))
        if prereq_ids and not prereq_ids.issubset(current_char_abilities):
            continue

        requirements_ids = set(ability.requirements.values_list("id", flat=True))
        if requirements_ids and not requirements_ids.issubset(current_char_choices):
            continue

        ability.cost = modifier.cost
        return


def get_available_ability_px(char, px_avail=None):
    # get all abilities already learned by the character
    current_char_abilities = set(char.px_ability_list.values_list("pk", flat=True))

    # get the options selected for the character
    que = WritingChoice.objects.filter(element_id=char.id, question__applicable=QuestionApplicable.CHARACTER)
    current_char_choices = set(que.values_list("option_id", flat=True))

    # get px available
    if px_avail is None:
        add_char_addit(char)
        px_avail = int(char.addit.get("px_avail", 0))

    # filter all abilities given we have the requested prerequisites / requirements
    all_abilities = (
        char.event.get_elements(AbilityPx)
        .filter(visible=True)
        .exclude(pk__in=current_char_abilities)
        .select_related("typ")
        .order_by("name")
    ).prefetch_related(
        Prefetch("prerequisites", queryset=AbilityPx.objects.only("id")),
        Prefetch("requirements", queryset=WritingOption.objects.only("id")),
    )

    # get all modifiers
    all_modifiers = (
        char.event.get_elements(ModifierPx)
        .order_by("order")
        .prefetch_related(
            Prefetch("abilities", queryset=AbilityPx.objects.only("id")),
            Prefetch("prerequisites", queryset=AbilityPx.objects.only("id")),
            Prefetch("requirements", queryset=WritingOption.objects.only("id")),
        )
    )

    # results
    abilities = []
    for ability in all_abilities:
        if not check_available_ability_px(ability, current_char_abilities, current_char_choices):
            continue

        # check modifiers to update cost
        check_modifier_ability_px(ability, all_modifiers, current_char_abilities, current_char_choices)

        # check cost
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
    char.addit = {}
    configs = CharacterConfig.objects.filter(character__id=char.id)
    if not configs.count():
        update_px(char)
        configs = CharacterConfig.objects.filter(character__id=char.id)

    for config in configs:
        char.addit[config.name] = config.value
