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

from typing import Optional

from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from larpmanager.cache.feature import get_event_features
from larpmanager.models.experience import AbilityPx, DeliveryPx, update_px
from larpmanager.models.form import QuestionApplicable, WritingChoice
from larpmanager.models.writing import Character
from larpmanager.utils.common import add_char_addit


@receiver(post_save, sender=Character)
def post_character_update_px(sender, instance, *args, **kwargs):
    if "px" in get_event_features(instance.event_id):
        update_px(instance)


@receiver(post_save, sender=AbilityPx)
def post_save_ability_px(sender, instance, *args, **kwargs):
    for char in instance.characters.all():
        update_px(char)


@receiver(post_save, sender=DeliveryPx)
def post_save_delivery_px(sender, instance, *args, **kwargs):
    for char in instance.characters.all():
        char.save()


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


m2m_changed.connect(px_characters_changed, sender=DeliveryPx.characters.through)
m2m_changed.connect(px_characters_changed, sender=AbilityPx.characters.through)


def check_available_ability_px(ability, current_char_abilities, current_char_choices):
    prereq_ids = set(ability.prerequisites.values_list("id", flat=True))
    dependent_ids = set(ability.dependents.values_list("id", flat=True))
    return prereq_ids.issubset(current_char_abilities) and dependent_ids.issubset(current_char_choices)


def get_available_ability_px(char):
    # get all abilities already learned by the character
    current_char_abilities = set(char.px_ability_list.values_list("pk", flat=True))

    # get the options selected for the character
    que = WritingChoice.objects.filter(element_id=char.id, question__applicable=QuestionApplicable.CHARACTER)
    current_char_choices = set(que.values_list("option_id", flat=True))

    # get px available
    add_char_addit(char)
    px_avail = char.addit.get("px_avail", 0)

    # filter all abilities given we have the requested prerequisites / dependents
    all_abilities = (
        char.event.get_elements(AbilityPx)
        .filter(visible=True, cost__lte=px_avail)
        .exclude(pk__in=current_char_abilities)
        .select_related("typ")
        .prefetch_related("prerequisites", "dependents")
        .order_by("name")
    )

    # results
    result = {}
    for el in all_abilities:
        if not check_available_ability_px(el, current_char_abilities, current_char_choices):
            continue

        if el.typ_id not in result:
            result[el.typ_id] = {"name": el.typ.name, "order": el.typ.id, "list": {}}

        result[el.typ_id]["list"][el.id] = f"{el.name} - {el.cost}"

    return result
