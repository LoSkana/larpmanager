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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.event import OrgaAppearanceForm, OrgaEventForm
from larpmanager.forms.miscellanea import OrgaCopyForm
from larpmanager.models.access import EventRole
from larpmanager.models.accounting import Discount
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event, EventButton, EventConfig, EventText
from larpmanager.models.form import RegistrationOption, RegistrationQuestion, WritingOption, WritingQuestion
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
from larpmanager.utils.common import copy_class
from larpmanager.utils.event import check_event_permission


def correct_rels_many(e_id, cls_p, cls, field, rel_field="number"):
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
    cache_t = {}

    for obj in cls_p.objects.filter(event_id=e_id):
        rel_value = getattr(obj, rel_field)
        cache_t[rel_value] = obj.id

    for obj in cls.objects.filter(event_id=e_id):
        m2m_field = getattr(obj, field)
        m2m_data = list(m2m_field.all())
        new_values = []

        for old_rel in m2m_data:
            v = getattr(old_rel, rel_field)
            new_rel = cache_t[v]
            new_values.append(new_rel)

        m2m_field.set(new_values, clear=True)


def correct_rels(e_id, p_id, cls_p, cls, field, rel_field="number"):
    """Correct model relationships after copying event elements.

    Args:
        e_id: Target event ID
        p_id: Source parent event ID
        cls_p: Parent model class to match
        cls: Model class to update relationships for
        field: Relationship field name to correct
        rel_field: Field to use for matching (default: "number")
    """
    cache_f = {}
    cache_t = {}
    field = field + "_id"

    for obj in cls_p.objects.filter(event_id=p_id):
        rel_value = getattr(obj, rel_field)
        cache_f[obj.id] = rel_value

    for obj in cls_p.objects.filter(event_id=e_id):
        rel_value = getattr(obj, rel_field)
        cache_t[rel_value] = obj.id

    for obj in cls.objects.filter(event_id=e_id):
        v = getattr(obj, field)
        if v not in cache_f:
            continue
        v = cache_f[v]
        v = cache_t[v]
        setattr(obj, field, v)
        obj.save()


def correct_relationship(e_id, p_id):
    """Correct character relationships after event copying.

    Args:
        e_id: Target event ID with copied characters
        p_id: Source parent event ID with original characters
    """
    cache_f = {}
    cache_t = {}
    for obj in Character.objects.filter(event_id=p_id):
        cache_f[obj.id] = obj.number
    for obj in Character.objects.filter(event_id=e_id):
        cache_t[obj.number] = obj.id
    # ~ field = 'character_id'
    # ~ for obj in Registration.objects.filter(run_id=ctx['run'].id):
    # ~ v = getattr(obj, field)
    # ~ if v not in cache_f:
    # ~ continue
    # ~ v = cache_f[v]
    # ~ v = cache_t[v]
    # ~ setattr(obj, field, v)
    # ~ obj.save()

    # copy complicated
    # Relationship
    # print(cache_f)
    # print(cache_t)
    for rel in Relationship.objects.filter(source__event_id=p_id):
        # print(rel)

        v = rel.source_id
        # print(rel.source_id)
        if v not in cache_f:
            continue
        v = cache_f[v]
        if v not in cache_t:
            continue
        v = cache_t[v]
        rel.source_id = v

        v = rel.target_id
        if v not in cache_f:
            continue
        v = cache_f[v]
        if v not in cache_t:
            continue
        v = cache_t[v]
        rel.target_id = v

        if Relationship.objects.filter(source_id=rel.source_id, target_id=rel.target_id).count() > 0:
            continue

        rel.pk = None
        rel.save()


def correct_workshop(e_id: int, p_id: int) -> None:
    """
    Correct workshop data mappings during event copying process.

    This function copies workshop modules, questions, and options from a source event
    to a target event, maintaining proper relationships between the copied objects.

    Args:
        e_id: Target event ID to copy workshop data to
        p_id: Source event ID to copy workshop data from

    Returns:
        None
    """
    # Build mapping cache from source event workshop modules (ID -> number)
    cache_f = {}
    cache_t = {}
    for obj in WorkshopModule.objects.filter(event_id=p_id):
        cache_f[obj.id] = obj.number

    # Build mapping cache from target event workshop modules (number -> ID)
    for obj in WorkshopModule.objects.filter(event_id=e_id):
        cache_t[obj.number] = obj.id

    # Copy workshop questions from source to target event
    # Update module references using the mapping caches
    for el in WorkshopQuestion.objects.filter(module__event_id=p_id):
        v = el.module_id
        v = cache_f[v]  # Get source module number
        v = cache_t[v]  # Get target module ID
        el.module_id = v

        # Create new question object in target event
        el.pk = None
        el.save()

    # Rebuild caches for workshop questions mapping
    cache_f = {}
    cache_t = {}
    for obj in WorkshopQuestion.objects.filter(module__event_id=p_id):
        cache_f[obj.id] = obj.number

    # Build mapping from target event questions (number -> ID)
    for obj in WorkshopQuestion.objects.filter(module__event_id=e_id):
        cache_t[obj.number] = obj.id

    # Copy workshop options from source to target event
    # Update question references using the mapping caches
    for el in WorkshopOption.objects.filter(question__module__event_id=p_id):
        v = el.question_id
        v = cache_f[v]  # Get source question number
        v = cache_t[v]  # Get target question ID
        el.question_id = v

        # Create new option object in target event
        el.pk = None
        el.save()


def correct_plot_character(e_id, p_id):
    """Correct plot-character relationships after event copying.

    Args:
        e_id: Target event ID with copied elements
        p_id: Source parent event ID with original elements
    """
    cache_c = {}
    for obj in Character.objects.values_list("id", "number").filter(event_id=p_id):
        n_obj = Character.objects.values_list("id").get(event_id=e_id, number=obj[1])[0]
        cache_c[obj[0]] = n_obj

    cache_p = {}
    for obj in Plot.objects.values_list("id", "number").filter(event_id=p_id):
        n_obj = Plot.objects.values_list("id").get(event_id=e_id, number=obj[1])[0]
        cache_p[obj[0]] = n_obj

    for el in PlotCharacterRel.objects.filter(character__event_id=p_id):
        n_c = cache_c[el.character_id]
        n_p = cache_p[el.plot_id]
        if PlotCharacterRel.objects.filter(character_id=n_c, plot_id=n_p).count() > 0:
            continue

        el.character_id = n_c
        el.plot_id = n_p
        el.pk = None
        el.save()


def copy_character_config(e_id, p_id):
    """Copy character configuration settings from parent to target event.

    Args:
        e_id: Target event ID to copy configurations to
        p_id: Parent event ID to copy configurations from
    """
    CharacterConfig.objects.filter(character__event_id=e_id).delete()
    cache = {}
    for obj in Character.objects.filter(event_id=e_id):
        cache[obj.number] = obj.id

    for obj in Character.objects.filter(event_id=p_id):
        new_id = cache[obj.number]
        for el in CharacterConfig.objects.filter(character=obj):
            for _idx in range(2):
                try:
                    with transaction.atomic():
                        cg, created = CharacterConfig.objects.update_or_create(
                            character_id=new_id, name=el.name, defaults={"value": el.value}
                        )
                    break
                except IntegrityError:
                    if _idx == 0:
                        continue
                    raise


def copy(request: HttpRequest, ctx: dict, parent: Event, event: Event, targets: list) -> HttpResponseRedirect | None:
    """Copy event data from a parent event to the current event.

    Args:
        request: The HTTP request object
        ctx: Context dictionary for the operation
        parent: The source event to copy data from
        event: The target event to copy data to
        targets: List of data types to copy

    Returns:
        HttpResponseRedirect if error occurs, None if successful
    """
    # Validate parent event exists
    if not parent:
        return messages.error(request, _("Parent empty"))

    # Extract event IDs for copying operations
    p_id = parent.id
    e_id = event.id

    # Prevent copying from the same event
    if p_id == e_id:
        return messages.error(request, _("Can't copy from same event"))

    # Copy event-specific data based on targets
    copy_event(ctx, e_id, targets, event, p_id, parent)

    # Copy registration data between events
    copy_registration(e_id, targets, p_id)

    # Copy writing/story data between events
    copy_writing(e_id, targets, p_id)

    # Save changes to the target event
    event.save()

    # Notify user of successful completion
    messages.success(request, _("Copy done"))


def copy_event(ctx, e_id, targets, event, p_id, parent):
    """
    Copy event data and related objects from parent to new event.

    Args:
        ctx: Context dictionary with form information
        e_id: Target event ID
        targets: List of elements to copy
        event: Target event instance
        p_id: Source parent event ID
        parent: Source parent event instance
    """
    # Define copy actions for each target type
    copy_actions = {
        "event": lambda: _copy_event_fields(ctx, event, parent),
        "config": lambda: copy_class(e_id, p_id, EventConfig),
        "appearance": lambda: _copy_appearance_fields(ctx, event, parent),
        "text": lambda: copy_class(e_id, p_id, EventText),
        "role": lambda: copy_class(e_id, p_id, EventRole),
        "features": lambda: _copy_features(event, parent),
        "navigation": lambda: copy_class(e_id, p_id, EventButton),
    }

    # Execute copy actions for each target in the list
    for target in targets:
        if target in copy_actions:
            copy_actions[target]()


def _copy_event_fields(ctx, event, parent):
    """Copy basic event fields from parent to child event."""
    for s in get_all_fields_from_form(OrgaEventForm, ctx):
        if s == "slug":
            continue
        v = getattr(parent, s)
        setattr(event, s, v)
    event.name = "copy - " + event.name


def _copy_appearance_fields(ctx, event, parent):
    """Copy appearance fields from parent to child event."""
    for s in get_all_fields_from_form(OrgaAppearanceForm, ctx):
        if s == "event_css":
            copy_css(ctx, event, parent)
        else:
            v = getattr(parent, s)
            setattr(event, s, v)


def _copy_features(event, parent):
    """Copy features from parent to child event."""
    for fn in parent.features.all():
        event.features.add(fn)
    event.save()


def copy_registration(e_id: int, targets: list[str], p_id: int) -> None:
    """Copy registration components from one event to another based on specified targets.

    Args:
        e_id: Source event ID to copy from
        targets: List of registration component types to copy ('ticket', 'question',
                'discount', 'quota', 'installment', 'surcharge')
        p_id: Target event ID to copy to
    """
    # Copy registration tickets if requested
    if "ticket" in targets:
        copy_class(e_id, p_id, RegistrationTicket)

    # Copy registration questions and their options, then fix relationships
    if "question" in targets:
        copy_class(e_id, p_id, RegistrationQuestion)
        copy_class(e_id, p_id, RegistrationOption)
        correct_rels(e_id, p_id, RegistrationQuestion, RegistrationOption, "question", "name")

    # Copy discount configurations
    if "discount" in targets:
        copy_class(e_id, p_id, Discount)

    # Copy registration quotas
    if "quota" in targets:
        copy_class(e_id, p_id, RegistrationQuota)

    # Copy installment plans and link them to tickets
    if "installment" in targets:
        copy_class(e_id, p_id, RegistrationInstallment)
        correct_rels_many(e_id, RegistrationTicket, RegistrationInstallment, "tickets", "name")

    # Copy surcharge configurations
    if "surcharge" in targets:
        copy_class(e_id, p_id, RegistrationSurcharge)


def copy_writing(e_id: int, targets: list[str], p_id: int) -> None:
    """Copy writing elements from parent to child event.

    This function copies various writing-related elements (characters, factions,
    quests, etc.) from a parent event to a target event based on the specified
    target types.

    Args:
        e_id: Target event ID where elements will be copied to
        targets: List of element types to copy. Valid values include:
            'character', 'faction', 'quest', 'prologue', 'speedlarp',
            'plot', 'handout', 'workshop'
        p_id: Parent event ID to copy elements from

    Returns:
        None
    """
    # Copy character-related elements and fix relationships
    if "character" in targets:
        copy_class(e_id, p_id, Character)
        # correct relationship
        correct_relationship(e_id, p_id)
        # character fields
        copy_class(e_id, p_id, WritingQuestion)
        copy_class(e_id, p_id, WritingOption)
        copy_character_config(e_id, p_id)
        correct_rels(e_id, p_id, WritingQuestion, WritingOption, "question", "name")

    # Copy faction elements
    if "faction" in targets:
        copy_class(e_id, p_id, Faction)

    # Copy quest-related elements and fix relationships
    if "quest" in targets:
        copy_class(e_id, p_id, QuestType)
        copy_class(e_id, p_id, Quest)
        copy_class(e_id, p_id, Trait)
        correct_rels(e_id, p_id, QuestType, Quest, "typ")
        correct_rels(e_id, p_id, Quest, Trait, "quest")

    # Copy prologue elements
    if "prologue" in targets:
        copy_class(e_id, p_id, Prologue)

    # Copy speedlarp elements
    if "speedlarp" in targets:
        copy_class(e_id, p_id, SpeedLarp)

    # Copy plot elements and fix character relationships
    if "plot" in targets:
        copy_class(e_id, p_id, Plot)
        # correct plotcharacterrels
        correct_plot_character(e_id, p_id)

    # Copy handout and template elements
    if "handout" in targets:
        copy_class(e_id, p_id, Handout)
        copy_class(e_id, p_id, HandoutTemplate)

    # Copy workshop elements and fix relationships
    if "workshop" in targets:
        copy_class(e_id, p_id, WorkshopModule)
        # correct workshop
        correct_workshop(e_id, p_id)


def copy_css(ctx, event, parent) -> None:
    """Copy CSS file from parent event to current event.

    Args:
        ctx: Context object
        event: Target event to copy CSS to
        parent: Source event to copy CSS from
    """
    # Initialize appearance form and get source CSS path
    app_form = OrgaAppearanceForm(ctx=ctx)
    path = app_form.get_css_path(parent)

    # Exit early if source CSS file doesn't exist
    if not default_storage.exists(path):
        return

    # Read CSS content from source file
    value = default_storage.open(path).read().decode("utf-8")

    # Generate new CSS ID and save to target event
    event.css_code = generate_id(32)
    npath = app_form.get_css_path(event)
    default_storage.save(npath, ContentFile(value))


@login_required
def orga_copy(request, s):
    """Handle event copying functionality for organizers.

    Args:
        request: HTTP request object
        s: Event slug identifier

    Returns:
        HttpResponse: Rendered copy form template or redirect after successful copy
    """
    ctx = check_event_permission(request, s, "orga_copy")

    if request.method == "POST":
        form = OrgaCopyForm(request.POST, request.FILES, ctx=ctx)
        if form.is_valid():
            pt = form.cleaned_data["parent"]
            targets = form.cleaned_data["target"]
            parent = Event.objects.get(pk=pt, assoc_id=ctx["a_id"])
            event = ctx["event"]
            copy(request, ctx, parent, event, targets)

    else:
        form = OrgaCopyForm(ctx=ctx)

    ctx["form"] = form

    return render(request, "larpmanager/orga/copy.html", ctx)


def get_all_fields_from_form(instance, ctx):
    """
    Return names of all available fields from given Form instance.

    :arg instance: Form instance
    :returns list of field names
    :rtype: list
    """

    fields = list(instance(ctx=ctx).base_fields)

    for field in list(instance(ctx=ctx).declared_fields):
        if field not in fields:
            fields.append(field)

    for s in ["slug"]:
        if s in fields:
            fields.remove(s)

    return fields
