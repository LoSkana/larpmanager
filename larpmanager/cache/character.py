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

from django.conf import settings as conf_settings
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


def get_event_cache_characters(ctx: dict, res: dict) -> dict:
    """Cache character data for an event including assignments and registrations.

    This function populates the results dictionary with character data for caching purposes.
    It handles character assignments, player data retrieval, and applies filtering based on
    event configuration and mirror functionality.

    Args:
        ctx: Context dictionary containing event data, features, run information, and event config.
        res: Results dictionary to populate with character data and metadata.

    Returns:
        The updated results dictionary with character data, assignments, and max character number.
    """
    res["chars"] = {}

    # Check if mirror feature is enabled for character filtering
    mirror = "mirror" in ctx["features"]

    # Build assignments mapping from character number to registration relation
    ctx["assignments"] = {}
    reg_que = RegistrationCharacterRel.objects.filter(reg__run=ctx["run"])
    for el in reg_que.select_related("character", "reg", "reg__member"):
        ctx["assignments"][el.character.number] = el

    # Get event configuration for hiding uncasted characters
    hide_uncasted_characters = ctx["event"].get_config("gallery_hide_uncasted_characters", False)

    # Get list of assigned character IDs for mirror filtering
    assigned_chars = RegistrationCharacterRel.objects.filter(reg__run=ctx["run"]).values_list("character_id", flat=True)

    # Process each character for the event cache
    que = ctx["event"].get_elements(Character).filter(hide=False).order_by("number")
    for ch in que.prefetch_related("factions_list"):
        # Skip mirror characters that are already assigned
        if mirror and ch.mirror_id in assigned_chars:
            continue

        # Build character data and search for player information
        data = ch.show(ctx["run"])
        data["fields"] = {}
        search_player(ch, data, ctx)

        # Hide uncasted characters if configuration is enabled
        if hide_uncasted_characters and data["player_id"] == 0:
            data["hide"] = True

        res["chars"][int(data["number"])] = data

    # Add field data to the cache
    get_event_cache_fields(ctx, res)

    # Set the maximum character number for reference
    if res["chars"]:
        res["max_ch_number"] = max(res["chars"], key=int)
    else:
        res["max_ch_number"] = 0

    return res


def get_event_cache_fields(ctx: dict, res: dict, only_visible: bool = True) -> None:
    """
    Retrieve and cache writing fields for characters in an event.

    This function populates character data with their associated writing field
    responses, including both multiple choice selections and text answers.

    Args:
        ctx: Context dictionary containing features and questions data
        res: Result dictionary with character data under 'chars' key
        only_visible: Whether to include only visible fields. Defaults to True.

    Returns:
        None: Modifies res dictionary in-place by adding field data to characters

    Note:
        Function returns early if 'character' feature is not enabled or if
        no questions are available in the context.
    """
    # Early return if character feature is not enabled
    if "character" not in ctx["features"]:
        return

    # Retrieve visible question IDs and populate ctx with questions
    visible_writing_fields(ctx, QuestionApplicable.CHARACTER, only_visible=only_visible)
    if "questions" not in ctx:
        return

    # Extract question IDs from context for database filtering
    question_idxs = ctx["questions"].keys()

    # Create mapping from character IDs to their position numbers in results
    mapping = {}
    for ch_num, ch in res["chars"].items():
        mapping[ch["id"]] = ch_num

    # Retrieve and process multiple choice answers for characters
    # Each choice can have multiple options selected per question
    ans_que = WritingChoice.objects.filter(question_id__in=question_idxs)
    for el in ans_que.values_list("element_id", "question_id", "option_id"):
        # Skip if character not in current event mapping
        if el[0] not in mapping:
            continue

        # Map database values to result structure
        ch_num = mapping[el[0]]
        question = el[1]
        value = el[2]

        # Initialize fields list for question if not exists, then append choice
        fields = res["chars"][ch_num]["fields"]
        if question not in fields:
            fields[question] = []
        fields[question].append(value)

    # Retrieve and process text answers for characters
    # Each text answer is a single value per question
    ans_que = WritingAnswer.objects.filter(question_id__in=question_idxs)
    for el in ans_que.values_list("element_id", "question_id", "text"):
        # Skip if character not in current event mapping
        if el[0] not in mapping:
            continue

        # Map database values to result structure
        ch_num = mapping[el[0]]
        question = el[1]
        value = el[2]

        # Set text answer directly (single value, not list)
        res["chars"][ch_num]["fields"][question] = value


def get_character_element_fields(ctx, character_id, only_visible=True):
    return get_writing_element_fields(
        ctx, "character", QuestionApplicable.CHARACTER, character_id, only_visible=only_visible
    )


def get_writing_element_fields(
    ctx: dict, feature_name: str, applicable, element_id: int, only_visible: bool = True
) -> dict:
    """
    Get writing fields for a specific element with visibility filtering.

    Retrieves writing questions, options, and field values for a given element,
    applying visibility filters based on context configuration.

    Args:
        ctx: Context dictionary containing event and configuration data including
             'questions', 'options', and visibility settings
        feature_name: Name of the feature (e.g., 'character', 'faction') used
                     for determining visibility key
        applicable: QuestionApplicable enum value defining question scope
        element_id: Unique identifier of the element to retrieve fields for
        only_visible: Whether to include only visible fields. Defaults to True

    Returns:
        Dictionary containing:
            - questions: Available questions from context
            - options: Available options from context
            - fields: Mapping of question_id to field values (text or list of option_ids)
    """
    # Apply visibility filtering to populate context with visible fields
    visible_writing_fields(ctx, applicable, only_visible=only_visible)

    # Filter questions based on visibility configuration
    # Only include questions that are explicitly shown or when show_all is enabled
    question_visible = []
    for question_id in ctx["questions"].keys():
        config = str(question_id)
        if "show_all" not in ctx and config not in ctx[f"show_{feature_name}"]:
            continue
        question_visible.append(question_id)

    # Retrieve text answers for visible questions
    # Store direct text responses in fields dictionary
    fields = {}
    que = WritingAnswer.objects.filter(element_id=element_id, question_id__in=question_visible)
    for el in que.values_list("question_id", "text"):
        fields[el[0]] = el[1]

    # Retrieve choice answers for visible questions
    # Group multiple choice options into lists per question
    que = WritingChoice.objects.filter(element_id=element_id, question_id__in=question_visible)
    for el in que.values_list("question_id", "option_id"):
        if el[0] not in fields:
            fields[el[0]] = []
        fields[el[0]].append(el[1])

    return {"questions": ctx["questions"], "options": ctx["options"], "fields": fields}


def get_event_cache_factions(ctx: dict, res: dict) -> None:
    """Build cached faction data for events.

    Organizes faction information by type and prepares faction selection options,
    handling characters without primary factions and creating faction-character
    mappings for the event cache.

    Args:
        ctx: Context dictionary containing event information with 'event' key
        res: Result dictionary to be populated with faction data, modified in-place

    Returns:
        None: Function modifies res in-place, adding 'factions' and 'factions_typ' keys

    Note:
        - Creates a fake faction (number 0) for characters without primary factions
        - Only includes factions that have associated characters
        - Organizes factions by type for easy lookup
    """
    # Initialize faction data structures
    res["factions"] = {}
    res["factions_typ"] = {}

    # If faction feature is not enabled, create single default faction with all characters
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

    # Find characters without a primary faction (faction 0)
    void_primary = []
    for number, ch in res["chars"].items():
        if "factions" in ch and 0 in ch["factions"]:
            void_primary.append(number)

    # Create fake faction for characters without primary faction
    if void_primary:
        res["factions"][0] = {
            "name": "",
            "number": 0,
            "typ": FactionType.PRIM,
            "teaser": "",
            "characters": void_primary,
        }
        res["factions_typ"][FactionType.PRIM] = [0]

    # Process real factions from the event
    for f in ctx["event"].get_elements(Faction).order_by("number"):
        # Get faction display data
        el = f.show_red()
        el["characters"] = []

        # Find characters belonging to this faction
        for number, ch in res["chars"].items():
            if el["number"] in ch["factions"]:
                el["characters"].append(number)

        # Skip factions with no characters
        if not el["characters"]:
            continue

        # Add faction to results and organize by type
        res["factions"][f.number] = el
        if f.typ not in res["factions_typ"]:
            res["factions_typ"][f.typ] = []
        res["factions_typ"][f.typ].append(f.number)


def get_event_cache_traits(ctx: dict, res: dict) -> None:
    """Build cached trait and quest data for events.

    Organizes character traits, quest types, and related game mechanics data,
    including trait relationships, character assignments, and quest type
    mappings for efficient event cache operations.

    Args:
        ctx: Context dictionary containing event information with 'event' and 'run' keys
        res: Result dictionary to be populated with trait and quest data, must contain 'chars' key

    Returns:
        None: Function modifies res in-place, adding quest types, traits, and relationships

    Side Effects:
        Modifies res dictionary by adding:
        - quest_types: Mapping of quest type numbers to their display data
        - quests: Mapping of quest numbers to their display data
        - traits: Mapping of trait numbers to enhanced trait data with relationships
        - max_tr_number: Maximum trait number or 0 if no traits exist
    """
    # Build quest types mapping ordered by number
    res["quest_types"] = {}
    for qt in QuestType.objects.filter(event=ctx["event"]).order_by("number"):
        res["quest_types"][qt.number] = qt.show()

    # Build quests mapping with type relationships
    res["quests"] = {}
    for qt in Quest.objects.filter(event=ctx["event"]).order_by("number").select_related("typ"):
        res["quests"][qt.number] = qt.show()

    # Build trait relationships mapping (traits that reference other traits)
    aux = {}
    for t in Trait.objects.filter(event=ctx["event"]).prefetch_related("traits"):
        aux[t.number] = []
        # Add related trait numbers, excluding self-references
        for at in t.traits.all():
            if at.number == t.number:
                continue
            aux[t.number].append(at.number)

    # Build main traits mapping with character assignments
    res["traits"] = {}
    que = AssignmentTrait.objects.filter(run=ctx["run"]).order_by("typ")

    # Process each assigned trait and link to character
    for at in que.select_related("trait", "trait__quest", "trait__quest__typ"):
        trait = at.trait.show()
        trait["quest"] = at.trait.quest.number
        trait["typ"] = at.trait.quest.typ.number
        trait["traits"] = aux[at.trait.number]

        # Find the character this trait is assigned to
        found = None
        for _number, ch in res["chars"].items():
            if "player_id" in ch and ch["player_id"] == at.member_id:
                found = ch
                break

        # Skip if character not found in cache
        if not found:
            continue

        # Initialize character traits list if needed
        if "traits" not in found:
            found["traits"] = []

        # Link trait to character and vice versa
        found["traits"].append(trait["number"])
        trait["char"] = found["number"]
        res["traits"][trait["number"]] = trait

    # Set maximum trait number for cache optimization
    if res["traits"]:
        res["max_tr_number"] = max(res["traits"], key=int)
    else:
        res["max_tr_number"] = 0


def get_event_cache_all(ctx):
    k = get_event_cache_all_key(ctx["run"])
    res = cache.get(k)
    if res is None:
        res = init_event_cache_all(ctx)
        cache.set(k, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    ctx.update(res)


def clear_run_cache_and_media(run):
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
    if res is None:
        return
    if isinstance(instance, Faction):
        update_event_cache_all_faction(instance, res)
    if isinstance(instance, Character):
        update_event_cache_all_character(instance, res, run)
        get_event_cache_factions({"event": run.event}, res)
    if isinstance(instance, RegistrationCharacterRel):
        update_event_cache_all_character_reg(instance, res, run)
    cache.set(k, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)


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


def update_member_event_character_cache(instance):
    que = RegistrationCharacterRel.objects.filter(reg__member_id=instance.id, reg__cancellation_date__isnull=True)
    que = que.select_related("character", "reg", "reg__run")
    for rcr in que:
        update_event_cache_all(rcr.reg.run, rcr)


def on_character_pre_save_update_cache(char):
    if not char.pk:
        clear_event_cache_all_runs(char.event)
        return

    try:
        prev = Character.objects.get(pk=char.pk)

        lst = ["player_id", "mirror_id"]
        if has_different_cache_values(char, prev, lst):
            clear_event_cache_all_runs(char.event)
        else:
            update_event_cache_all_runs(char.event, char)
    except Exception:
        clear_event_cache_all_runs(char.event)


def on_character_factions_m2m_changed(sender, **kwargs):
    action = kwargs.pop("action", None)
    if action not in ["post_add", "post_remove", "post_clear"]:
        return

    instance: Optional[Faction] = kwargs.pop("instance", None)
    clear_event_cache_all_runs(instance.event)


def on_faction_pre_save_update_cache(instance):
    if not instance.pk:
        clear_event_cache_all_runs(instance.event)
        return

    prev = Faction.objects.get(pk=instance.pk)

    lst = ["typ"]
    if has_different_cache_values(instance, prev, lst):
        clear_event_cache_all_runs(instance.event)

    lst = ["name", "teaser"]
    if has_different_cache_values(instance, prev, lst):
        update_event_cache_all_runs(instance.event, instance)


def on_quest_type_pre_save_update_cache(instance):
    if not instance.pk:
        clear_event_cache_all_runs(instance.event)
        return

    lst = ["name"]
    prev = QuestType.objects.get(pk=instance.pk)
    if has_different_cache_values(instance, prev, lst):
        clear_event_cache_all_runs(instance.event)


def on_quest_pre_save_update_cache(instance):
    if not instance.pk:
        clear_event_cache_all_runs(instance.event)
        return

    lst = ["name", "teaser", "typ_id"]
    prev = Quest.objects.get(pk=instance.pk)
    if has_different_cache_values(instance, prev, lst):
        clear_event_cache_all_runs(instance.event)


def on_trait_pre_save_update_cache(instance):
    if not instance.pk:
        clear_event_cache_all_runs(instance.event)
        return

    lst = ["name", "teaser", "quest_id"]
    prev = Trait.objects.get(pk=instance.pk)
    if has_different_cache_values(instance, prev, lst):
        clear_event_cache_all_runs(instance.event)


def update_event_cache_all_runs(event, instance):
    for r in event.runs.all():
        update_event_cache_all(r, instance)


def reset_character_registration_cache(instance):
    if instance.reg:
        instance.reg.save()
    clear_run_cache_and_media(instance.reg.run)


def clear_event_cache_all_runs(event):
    for r in event.runs.all():
        clear_run_cache_and_media(r)
    # reset also runs of child events
    for child in Event.objects.filter(parent=event).prefetch_related("runs"):
        for r in child.runs.all():
            clear_run_cache_and_media(r)
    if event.parent:
        # reset also runs of sibling events
        for child in Event.objects.filter(parent=event.parent).prefetch_related("runs"):
            for r in child.runs.all():
                clear_run_cache_and_media(r)
        # reset also runs of parent event
        for r in event.parent.runs.all():
            clear_run_cache_and_media(r)
