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
from django.http import HttpRequest, HttpResponse
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


def correct_rels_many(e_id: int, cls_p: type, cls: type, field: str, rel_field: str = "number") -> None:
    """Correct many-to-many relationships after copying event elements.

    This function rebuilds many-to-many relationships between copied event elements
    by matching them based on a specified field value (typically 'number').

    Args:
        e_id: Target event ID to filter objects by.
        cls_p: Parent model class to match against and build lookup cache from.
        cls: Model class to update many-to-many relationships for.
        field: Name of the many-to-many field to correct on cls objects.
        rel_field: Field name to use for matching elements between old and new
            objects. Defaults to "number".

    Returns:
        None

    Side Effects:
        Updates many-to-many relationships for all objects of cls in the specified event.
        Clears existing relationships and sets new ones based on the lookup cache.
    """
    # Build lookup cache mapping rel_field values to new object IDs
    cache_t = {}
    for obj in cls_p.objects.filter(event_id=e_id):
        rel_value = getattr(obj, rel_field)
        cache_t[rel_value] = obj.id

    # Update many-to-many relationships for each target object
    for obj in cls.objects.filter(event_id=e_id):
        m2m_field = getattr(obj, field)
        m2m_data = list(m2m_field.all())
        new_values = []

        # Map old relationships to new object IDs using the cache
        for old_rel in m2m_data:
            v = getattr(old_rel, rel_field)
            new_rel = cache_t[v]
            new_values.append(new_rel)

        # Replace all existing relationships with the corrected ones
        m2m_field.set(new_values, clear=True)


def correct_rels(e_id: int, p_id: int, cls_p: type, cls: type, field: str, rel_field: str = "number") -> None:
    """Correct model relationships after copying event elements.

    This function updates relationship references in copied event elements to point
    to the corresponding objects in the target event rather than the source event.

    Args:
        e_id: Target event ID where relationships should be corrected
        p_id: Source parent event ID from which elements were copied
        cls_p: Parent model class to match relationships against
        cls: Model class whose relationships need to be updated
        field: Base name of the relationship field to correct (without '_id' suffix)
        rel_field: Field name used for matching objects between events (default: "number")

    Returns:
        None

    Example:
        correct_rels(new_event_id, old_event_id, Character, Assignment, "character")
    """
    # Cache to store mapping from source object ID to its identifier value
    cache_f = {}
    # Cache to store mapping from identifier value to target object ID
    cache_t = {}
    # Append '_id' suffix to get the actual foreign key field name
    field = field + "_id"

    # Build mapping from source event objects: object_id -> identifier_value
    for obj in cls_p.objects.filter(event_id=p_id):
        rel_value = getattr(obj, rel_field)
        cache_f[obj.id] = rel_value

    # Build mapping from target event objects: identifier_value -> object_id
    for obj in cls_p.objects.filter(event_id=e_id):
        rel_value = getattr(obj, rel_field)
        cache_t[rel_value] = obj.id

    # Update relationships in target event objects
    for obj in cls.objects.filter(event_id=e_id):
        v = getattr(obj, field)
        # Skip if source relationship doesn't exist in cache
        if v not in cache_f:
            continue
        # Get identifier value from source object
        v = cache_f[v]
        # Get corresponding target object ID
        v = cache_t[v]
        # Update the relationship field and save
        setattr(obj, field, v)
        obj.save()


def correct_relationship(e_id: int, p_id: int) -> None:
    """Correct character relationships after event copying.

    This function maps character relationships from a source event to a target event
    by creating new relationship records with updated character IDs. It handles the
    ID mapping between original and copied characters.

    Args:
        e_id: Target event ID containing copied characters
        p_id: Source parent event ID containing original characters
    """
    # Build mapping cache from original character ID to character number
    cache_f = {}
    cache_t = {}

    # Cache original characters: ID -> number mapping
    for obj in Character.objects.filter(event_id=p_id):
        cache_f[obj.id] = obj.number

    # Cache copied characters: number -> ID mapping
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

    # Process each relationship from the source event
    for rel in Relationship.objects.filter(source__event_id=p_id):
        # Map source character ID to new event
        v = rel.source_id
        if v not in cache_f:
            continue
        v = cache_f[v]  # Get character number
        if v not in cache_t:
            continue
        v = cache_t[v]  # Get new character ID
        rel.source_id = v

        # Map target character ID to new event
        v = rel.target_id
        if v not in cache_f:
            continue
        v = cache_f[v]  # Get character number
        if v not in cache_t:
            continue
        v = cache_t[v]  # Get new character ID
        rel.target_id = v

        # Skip if relationship already exists in target event
        if Relationship.objects.filter(source_id=rel.source_id, target_id=rel.target_id).count() > 0:
            continue

        # Create new relationship record with mapped IDs
        rel.pk = None
        rel.save()


def correct_workshop(e_id: int, p_id: int) -> None:
    """
    Correct workshop data mappings during event copying process.

    This function copies workshop modules, questions, and options from a source event
    to a target event, maintaining proper relationships between the copied objects.

    Args:
        e_id: Target event ID to copy to
        p_id: Source event ID to copy from

    Returns:
        None
    """
    # Build mapping cache for workshop modules from source event
    cache_f = {}
    cache_t = {}
    for obj in WorkshopModule.objects.filter(event_id=p_id):
        cache_f[obj.id] = obj.number

    # Build reverse mapping cache for workshop modules in target event
    for obj in WorkshopModule.objects.filter(event_id=e_id):
        cache_t[obj.number] = obj.id

    # Copy workshop questions from source to target event
    for el in WorkshopQuestion.objects.filter(module__event_id=p_id):
        # Map source module ID to target module ID via number
        v = el.module_id
        v = cache_f[v]
        v = cache_t[v]
        el.module_id = v

        # Create new question record in target event
        el.pk = None
        el.save()

    # Build mapping cache for workshop questions from source event
    cache_f = {}
    cache_t = {}
    for obj in WorkshopQuestion.objects.filter(module__event_id=p_id):
        cache_f[obj.id] = obj.number

    # Build reverse mapping cache for workshop questions in target event
    for obj in WorkshopQuestion.objects.filter(module__event_id=e_id):
        cache_t[obj.number] = obj.id

    # Copy workshop options from source to target event
    for el in WorkshopOption.objects.filter(question__module__event_id=p_id):
        # Map source question ID to target question ID via number
        v = el.question_id
        v = cache_f[v]
        v = cache_t[v]
        el.question_id = v

        # Create new option record in target event
        el.pk = None
        el.save()


def correct_plot_character(e_id: int, p_id: int) -> None:
    """Correct plot-character relationships after event copying.

    Creates new PlotCharacterRel objects in the target event by mapping
    characters and plots from the source event to their corresponding
    copies in the target event.

    Args:
        e_id: Target event ID containing copied elements
        p_id: Source parent event ID containing original elements
    """
    # Build character mapping cache: source_id -> target_id
    cache_c = {}
    for obj in Character.objects.values_list("id", "number").filter(event_id=p_id):
        n_obj = Character.objects.values_list("id").get(event_id=e_id, number=obj[1])[0]
        cache_c[obj[0]] = n_obj

    # Build plot mapping cache: source_id -> target_id
    cache_p = {}
    for obj in Plot.objects.values_list("id", "number").filter(event_id=p_id):
        n_obj = Plot.objects.values_list("id").get(event_id=e_id, number=obj[1])[0]
        cache_p[obj[0]] = n_obj

    # Copy plot-character relationships to target event
    for el in PlotCharacterRel.objects.filter(character__event_id=p_id):
        # Map source IDs to target IDs
        n_c = cache_c[el.character.id]
        n_p = cache_p[el.plot.id]

        # Skip if relationship already exists in target event
        if PlotCharacterRel.objects.filter(character_id=n_c, plot_id=n_p).count() > 0:
            continue

        # Create new relationship in target event
        el.character_id = n_c
        el.plot_id = n_p
        el.pk = None
        el.save()


def copy_character_config(e_id: int, p_id: int) -> None:
    """Copy character configuration settings from parent to target event.

    This function copies all character configurations from a parent event to a target event.
    It first clears existing configurations in the target event, then maps characters by
    number and copies all configuration settings with retry logic for integrity constraints.

    Args:
        e_id: Target event ID to copy configurations to
        p_id: Parent event ID to copy configurations from

    Raises:
        IntegrityError: If character configuration creation fails after retry
    """
    # Clear existing character configurations in target event
    CharacterConfig.objects.filter(character__event_id=e_id).delete()

    # Build cache mapping character numbers to IDs in target event
    cache = {}
    for obj in Character.objects.filter(event_id=e_id):
        cache[obj.number] = obj.id

    # Iterate through characters in parent event
    for obj in Character.objects.filter(event_id=p_id):
        new_id = cache[obj.number]

        # Copy all configuration settings for current character
        for el in CharacterConfig.objects.filter(character=obj):
            # Retry logic to handle potential integrity constraint violations
            for _idx in range(2):
                try:
                    with transaction.atomic():
                        cg, created = CharacterConfig.objects.update_or_create(
                            character_id=new_id, name=el.name, defaults={"value": el.value}
                        )
                    break
                except IntegrityError:
                    # Retry once on integrity error, then re-raise
                    if _idx == 0:
                        continue
                    raise


def copy(request: HttpRequest, ctx: dict, parent: Event, event: Event, targets: list[str]) -> None:
    """
    Copy data from a parent event to a target event.

    This function orchestrates the copying of event-related data including
    event configuration, registration settings, and writing elements from
    a parent event to the target event.

    Args:
        request: The HTTP request object containing user session and message framework
        ctx: Context dictionary containing additional data for the copy operation
        parent: The source event to copy data from
        event: The target event to copy data to
        targets: List of target identifiers specifying what data to copy

    Returns:
        None: Function uses Django messages framework to communicate results

    Side Effects:
        - Displays error messages if validation fails
        - Displays success message if copy completes
        - Modifies the target event and saves it to database
        - Creates new registration, writing, and other related objects
    """
    # Validate that parent event exists
    if not parent:
        return messages.error(request, _("Parent empty"))

    # Extract event IDs for comparison and processing
    p_id = parent.id
    e_id = event.id

    # Prevent copying from event to itself
    if p_id == e_id:
        return messages.error(request, _("Can't copy from same event"))

    # Copy core event data and configuration
    copy_event(ctx, e_id, targets, event, p_id, parent)

    # Copy registration-related data (tickets, questions, etc.)
    copy_registration(e_id, targets, p_id)

    # Copy writing elements (backgrounds, stories, etc.)
    copy_writing(e_id, targets, p_id)

    # Persist all changes to the target event
    event.save()

    # Notify user of successful completion
    messages.success(request, _("Copy done"))


def copy_event(ctx: dict, e_id: int, targets: list[str], event: Event, p_id: int, parent: Event) -> None:
    """
    Copy event data and related objects from parent to new event.

    Executes a series of copy operations based on the specified target types,
    transferring data from a source parent event to a target event.

    Args:
        ctx: Context dictionary containing form information and metadata
        e_id: Target event ID for the destination event
        targets: List of element types to copy (e.g., 'event', 'config', 'text')
        event: Target event instance to copy data into
        p_id: Source parent event ID for the origin event
        parent: Source parent event instance to copy data from

    Returns:
        None: Function performs copy operations in-place
    """
    # Define copy actions for each target type
    # Maps target type strings to their corresponding copy functions
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
    # Only processes targets that have defined copy actions
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
    """Copy registration-related objects from one event to another.

    Args:
        e_id: The source event ID to copy from
        targets: List of target types to copy (ticket, question, discount, quota, installment, surcharge)
        p_id: The destination event ID to copy to

    Returns:
        None
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

    # Copy installment plans and fix ticket relationships
    if "installment" in targets:
        copy_class(e_id, p_id, RegistrationInstallment)
        correct_rels_many(e_id, RegistrationTicket, RegistrationInstallment, "tickets", "name")

    # Copy surcharge configurations
    if "surcharge" in targets:
        copy_class(e_id, p_id, RegistrationSurcharge)


def copy_writing(e_id: int, targets: list[str], p_id: int) -> None:
    """Copy writing elements from parent to child event.

    Copies various writing-related objects (characters, factions, quests, etc.)
    from a parent event to a target event based on specified target types.

    Args:
        e_id: Target event ID to copy elements to
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

    # Copy handout-related elements
    if "handout" in targets:
        copy_class(e_id, p_id, Handout)
        copy_class(e_id, p_id, HandoutTemplate)

    # Copy workshop elements and fix relationships
    if "workshop" in targets:
        copy_class(e_id, p_id, WorkshopModule)
        # correct workshop
        correct_workshop(e_id, p_id)


def copy_css(ctx, event, parent):
    app_form = OrgaAppearanceForm(ctx=ctx)
    path = app_form.get_css_path(parent)
    if not default_storage.exists(path):
        return
    value = default_storage.open(path).read().decode("utf-8")
    event.css_code = generate_id(32)
    npath = app_form.get_css_path(event)
    default_storage.save(npath, ContentFile(value))


@login_required
def orga_copy(request: HttpRequest, s: str) -> HttpResponse:
    """Handle event copying functionality for organizers.

    This view allows organizers to copy event configurations and data from a parent
    event to one or more target events within the same association.

    Args:
        request: The HTTP request object containing user data and form submission
        s: The event slug identifier used to identify the current event context

    Returns:
        HttpResponse: Either a rendered copy form template for GET requests or a
                     redirect response after successful copy operation for POST requests

    Raises:
        PermissionDenied: If user lacks 'orga_copy' permission for the event
        Event.DoesNotExist: If parent event is not found in the association
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_copy")

    if request.method == "POST":
        # Process form submission with copy operation
        form = OrgaCopyForm(request.POST, request.FILES, ctx=ctx)
        if form.is_valid():
            # Extract validated form data
            pt = form.cleaned_data["parent"]
            targets = form.cleaned_data["target"]

            # Get parent event from database within association scope
            parent = Event.objects.get(pk=pt, assoc_id=ctx["a_id"])
            event = ctx["event"]

            # Execute the copy operation
            copy(request, ctx, parent, event, targets)

    else:
        # Initialize empty form for GET requests
        form = OrgaCopyForm(ctx=ctx)

    # Add form to template context
    ctx["form"] = form

    return render(request, "larpmanager/orga/copy.html", ctx)


def get_all_fields_from_form(instance, ctx) -> list[str]:
    """
    Return names of all available fields from given Form instance.

    Args:
        instance: Form class to instantiate and extract fields from
        ctx: Context dictionary passed to form initialization

    Returns:
        List of field names excluding system fields like 'slug'
    """
    # Get base fields from form instance
    fields = list(instance(ctx=ctx).base_fields)

    # Add any declared fields that aren't already in base_fields
    for field in list(instance(ctx=ctx).declared_fields):
        if field not in fields:
            fields.append(field)

    # Remove system fields that shouldn't be included
    for s in ["slug"]:
        if s in fields:
            fields.remove(s)

    return fields
