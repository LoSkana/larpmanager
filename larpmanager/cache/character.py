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

import os
import shutil
from typing import Optional

from django.core.cache import cache

from larpmanager.cache.feature import get_event_features
from larpmanager.cache.fields import visible_writing_fields
from larpmanager.cache.registration import search_player
from larpmanager.models.casting import AssignmentTrait, Quest, QuestType, Trait
from larpmanager.models.event import Event
from larpmanager.models.form import (
    QuestionApplicable,
    WritingAnswer,
    WritingChoice,
)
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character, Faction, FactionType


def delete_all_in_path(path):
    """Recursively delete all contents within a directory path.

    Args:
        path (str): Directory path to clean
    """
    if os.path.exists(path):
        # Remove all contents inside the path
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)


def get_event_cache_all_key(run):
    """Generate cache key for event data.

    Args:
        run: Run instance

    Returns:
        str: Cache key for event factions and characters
    """
    return f"event_factions_characters_{run.event.slug}_{run.number}"


def init_event_cache_all(ctx):
    """Initialize complete event cache with characters, factions, and traits.

    Args:
        ctx: Context dictionary containing event and feature data

    Returns:
        dict: Cached event data including characters, factions, and traits
    """
    res = {}
    get_event_cache_characters(ctx, res)

    get_event_cache_factions(ctx, res)

    if "questbuilder" in ctx["features"]:
        get_event_cache_traits(ctx, res)

    return res


def get_event_cache_characters(ctx, res):
    """Cache character data for an event including assignments and registrations.

    Args:
        ctx: Context dictionary with event data
        res: Results dictionary to populate with character data
    """
    res["chars"] = {}
    mirror = "mirror" in ctx["features"]

    # get assignments
    ctx["assignments"] = {}
    reg_que = RegistrationCharacterRel.objects.filter(reg__run=ctx["run"])
    for el in reg_que.select_related("character", "reg", "reg__member"):
        ctx["assignments"][el.character.number] = el

    hide_uncasted_characters = ctx["event"].get_config("gallery_hide_uncasted_characters", False)

    assigned_chars = RegistrationCharacterRel.objects.filter(reg__run=ctx["run"]).values_list("character_id", flat=True)

    # get player data
    que = ctx["event"].get_elements(Character).filter(hide=False).order_by("number")
    for ch in que.prefetch_related("factions_list"):
        if mirror and ch.mirror_id in assigned_chars:
            continue

        data = ch.show(ctx["run"])
        data["fields"] = {}
        search_player(ch, data, ctx)
        if hide_uncasted_characters and data["player_id"] == 0:
            data["hide"] = True

        res["chars"][int(data["number"])] = data

    get_event_cache_fields(ctx, res)

    if res["chars"]:
        res["max_ch_number"] = max(res["chars"], key=int)
    else:
        res["max_ch_number"] = 0

    return res


def get_event_cache_fields(ctx, res, only_visible=True):
    """
    Retrieve and cache writing fields for characters in an event.

    Args:
        ctx: Context dictionary containing features and questions
        res: Result dictionary with character data
        only_visible: Whether to include only visible fields (default: True)
    """
    if "character" not in ctx["features"]:
        return

    # get visible question ids
    visible_writing_fields(ctx, QuestionApplicable.CHARACTER, only_visible=only_visible)
    if "questions" not in ctx:
        return

    question_idxs = ctx["questions"].keys()

    # ids to number
    mapping = {}
    for ch_num, ch in res["chars"].items():
        mapping[ch["id"]] = ch_num

    # get choices for characters of the event
    ans_que = WritingChoice.objects.filter(question_id__in=question_idxs)
    for el in ans_que.values_list("element_id", "question_id", "option_id"):
        if el[0] not in mapping:
            continue
        ch_num = mapping[el[0]]
        question = el[1]
        value = el[2]
        fields = res["chars"][ch_num]["fields"]
        if question not in fields:
            fields[question] = []
        fields[question].append(value)

    # get answers for characters of the event
    ans_que = WritingAnswer.objects.filter(question_id__in=question_idxs)
    for el in ans_que.values_list("element_id", "question_id", "text"):
        if el[0] not in mapping:
            continue
        ch_num = mapping[el[0]]
        question = el[1]
        value = el[2]
        res["chars"][ch_num]["fields"][question] = value


def get_character_element_fields(ctx, character_id, only_visible=True):
    return get_writing_element_fields(
        ctx, "character", QuestionApplicable.CHARACTER, character_id, only_visible=only_visible
    )


def get_writing_element_fields(ctx, feature_name, applicable, element_id, only_visible=True):
    """
    Get writing fields for a specific element with visibility filtering.

    Args:
        ctx: Context dictionary with event and configuration data
        feature_name: Name of the feature (e.g., 'character', 'faction')
        applicable: QuestionApplicable enum value
        element_id: ID of the element to get fields for
        only_visible: Whether to include only visible fields (default: True)

    Returns:
        dict: Dictionary with questions, options, and field values
    """
    visible_writing_fields(ctx, applicable, only_visible=only_visible)

    # remove not visible questions
    question_visible = []
    for question_id in ctx["questions"].keys():
        config = str(question_id)
        if "show_all" not in ctx and config not in ctx[f"show_{feature_name}"]:
            continue
        question_visible.append(question_id)

    fields = {}
    que = WritingAnswer.objects.filter(element_id=element_id, question_id__in=question_visible)
    for el in que.values_list("question_id", "text"):
        fields[el[0]] = el[1]
    que = WritingChoice.objects.filter(element_id=element_id, question_id__in=question_visible)
    for el in que.values_list("question_id", "option_id"):
        if el[0] not in fields:
            fields[el[0]] = []
        fields[el[0]].append(el[1])

    return {"questions": ctx["questions"], "options": ctx["options"], "fields": fields}


def get_event_cache_factions(ctx, res):
    """Build cached faction data for events.

    Organizes faction information by type and prepares faction selection options,
    handling characters without primary factions and creating faction-character
    mappings for the event cache.

    Args:
        ctx (dict): Context dictionary containing event information
        res (dict): Result dictionary to be populated with faction data

    Returns:
        None: Function modifies res in-place, adding faction mappings and metadata
    """
    res["factions"] = {}
    res["factions_typ"] = {}

    if "faction" not in get_event_features(ctx["event"].id):
        res["factions"][0] = {
            "name": "",
            "number": 0,
            "typ": FactionType.PRIM,
            "teaser": "",
            "characters": list(res["chars"].keys()),
        }
        res["factions_typ"][FactionType.PRIM] = [0]
        return

    # add characters without a primary to a fake one
    void_primary = []
    for number, ch in res["chars"].items():
        if "factions" in ch and 0 in ch["factions"]:
            void_primary.append(number)
    if void_primary:
        res["factions"][0] = {
            "name": "",
            "number": 0,
            "typ": FactionType.PRIM,
            "teaser": "",
            "characters": void_primary,
        }
        res["factions_typ"][FactionType.PRIM] = [0]
    # add real factions
    for f in ctx["event"].get_elements(Faction).order_by("number"):
        el = f.show_red()
        el["characters"] = []
        for number, ch in res["chars"].items():
            if el["number"] in ch["factions"]:
                el["characters"].append(number)
        if not el["characters"]:
            continue
        res["factions"][f.number] = el
        if f.typ not in res["factions_typ"]:
            res["factions_typ"][f.typ] = []
        res["factions_typ"][f.typ].append(f.number)


def get_event_cache_traits(ctx, res):
    """Build cached trait and quest data for events.

    Organizes character traits, quest types, and related game mechanics data,
    including trait relationships, character assignments, and quest type
    mappings for efficient event cache operations.

    Args:
        ctx (dict): Context dictionary containing event information
        res (dict): Result dictionary to be populated with trait and quest data

    Returns:
        None: Function modifies res in-place, adding quest types, traits, and relationships
    """
    res["quest_types"] = {}
    for qt in QuestType.objects.filter(event=ctx["event"]).order_by("number"):
        res["quest_types"][qt.number] = qt.show()
    res["quests"] = {}
    for qt in Quest.objects.filter(event=ctx["event"]).order_by("number").select_related("typ"):
        res["quests"][qt.number] = qt.show()
    aux = {}
    for t in Trait.objects.filter(event=ctx["event"]).prefetch_related("traits"):
        aux[t.number] = []
        for at in t.traits.all():
            if at.number == t.number:
                continue
            aux[t.number].append(at.number)
    res["traits"] = {}
    que = AssignmentTrait.objects.filter(run=ctx["run"]).order_by("typ")
    for at in que.select_related("trait", "trait__quest", "trait__quest__typ"):
        trait = at.trait.show()
        trait["quest"] = at.trait.quest.number
        trait["typ"] = at.trait.quest.typ.number
        trait["traits"] = aux[at.trait.number]

        found = None
        for _number, ch in res["chars"].items():
            if "player_id" in ch and ch["player_id"] == at.member_id:
                found = ch
                break
        if not found:
            continue
        if "traits" not in found:
            found["traits"] = []
        found["traits"].append(trait["number"])
        trait["char"] = found["number"]
        res["traits"][trait["number"]] = trait
    if res["traits"]:
        res["max_tr_number"] = max(res["traits"], key=int)
    else:
        res["max_tr_number"] = 0


def get_event_cache_all(ctx):
    k = get_event_cache_all_key(ctx["run"])
    res = cache.get(k)
    if not res:
        res = init_event_cache_all(ctx)
        cache.set(k, res)

    ctx.update(res)


def reset_run(run):
    reset_event_cache_all(run)
    media_path = run.get_media_filepath()
    delete_all_in_path(media_path)


def reset_event_cache_all(run):
    k = get_event_cache_all_key(run)
    cache.delete(k)


def update_character_fields(instance, data):
    features = get_event_features(instance.event.id)
    if "character" not in features:
        return

    ctx = {"features": features, "event": instance.event}
    data.update(get_character_element_fields(ctx, instance.pk, only_visible=False))


def update_event_cache_all(run, instance):
    k = get_event_cache_all_key(run)
    res = cache.get(k)
    if not res:
        return
    if isinstance(instance, Faction):
        update_event_cache_all_faction(instance, res)
    if isinstance(instance, Character):
        update_event_cache_all_character(instance, res, run)
        get_event_cache_factions({"event": run.event}, res)
    if isinstance(instance, RegistrationCharacterRel):
        update_event_cache_all_character_reg(instance, res, run)
    cache.set(k, res)


def update_event_cache_all_character_reg(instance, res, run):
    char = instance.character
    data = char.show()
    search_player(char, data, {"run": run, "assignments": {char.number: instance}})
    if char.number not in res["chars"]:
        res["chars"][char.number] = {}
    res["chars"][char.number].update(data)


def update_event_cache_all_character(instance, res, run):
    data = instance.show(run)
    update_character_fields(instance, data)
    search_player(instance, data, {"run": run})
    if instance.number not in res["chars"]:
        res["chars"][instance.number] = {}
    res["chars"][instance.number].update(data)


def update_event_cache_all_faction(instance, res):
    data = instance.show()
    if instance.number in res["factions"]:
        res["factions"][instance.number].update(data)
    else:
        res["factions"][instance.number] = data


def has_different_cache_values(instance, prev, lst):
    for v in lst:
        p_v = getattr(prev, v)
        c_v = getattr(instance, v)
        if p_v != c_v:
            return True

    return False


def handle_update_event_characters(instance):
    que = RegistrationCharacterRel.objects.filter(reg__member_id=instance.id, reg__cancellation_date__isnull=True)
    que = que.select_related("character", "reg", "reg__run")
    for rcr in que:
        update_event_cache_all(rcr.reg.run, rcr)


def handle_character_pre_save(char):
    if not char.pk:
        reset_event_cache_all_runs(char.event)
        return

    try:
        prev = Character.objects.get(pk=char.pk)

        lst = ["player_id", "mirror_id"]
        if has_different_cache_values(char, prev, lst):
            reset_event_cache_all_runs(char.event)
        else:
            update_event_cache_all_runs(char.event, char)
    except Exception:
        reset_event_cache_all_runs(char.event)


def character_factions_changed(sender, **kwargs):
    action = kwargs.pop("action", None)
    if action not in ["post_add", "post_remove", "post_clear"]:
        return

    instance: Optional[Faction] = kwargs.pop("instance", None)
    reset_event_cache_all_runs(instance.event)


def handle_faction_pre_save(instance):
    if not instance.pk:
        reset_event_cache_all_runs(instance.event)
        return

    prev = Faction.objects.get(pk=instance.pk)

    lst = ["typ"]
    if has_different_cache_values(instance, prev, lst):
        reset_event_cache_all_runs(instance.event)

    lst = ["name", "teaser"]
    if has_different_cache_values(instance, prev, lst):
        update_event_cache_all_runs(instance.event, instance)


def handle_quest_type_presave(instance):
    if not instance.pk:
        reset_event_cache_all_runs(instance.event)
        return

    lst = ["name"]
    prev = QuestType.objects.get(pk=instance.pk)
    if has_different_cache_values(instance, prev, lst):
        reset_event_cache_all_runs(instance.event)


def handle_quest_presave(instance):
    if not instance.pk:
        reset_event_cache_all_runs(instance.event)
        return

    lst = ["name", "teaser", "typ_id"]
    prev = Quest.objects.get(pk=instance.pk)
    if has_different_cache_values(instance, prev, lst):
        reset_event_cache_all_runs(instance.event)


def handle_trait_presave(instance):
    if not instance.pk:
        reset_event_cache_all_runs(instance.event)
        return

    lst = ["name", "teaser", "quest_id"]
    prev = Trait.objects.get(pk=instance.pk)
    if has_different_cache_values(instance, prev, lst):
        reset_event_cache_all_runs(instance.event)


def update_event_cache_all_runs(event, instance):
    for r in event.runs.all():
        update_event_cache_all(r, instance)


def handle_registration_character_reset(instance):
    if instance.reg:
        instance.reg.save()
    reset_run(instance.reg.run)


def reset_event_cache_all_runs(event):
    for r in event.runs.all():
        reset_run(r)
    # reset also runs of child events
    for child in Event.objects.filter(parent=event).prefetch_related("runs"):
        for r in child.runs.all():
            reset_run(r)
    if event.parent:
        # reset also runs of sibling events
        for child in Event.objects.filter(parent=event.parent).prefetch_related("runs"):
            for r in child.runs.all():
                reset_run(r)
        # reset also runs of parent event
        for r in event.parent.runs.all():
            reset_run(r)
