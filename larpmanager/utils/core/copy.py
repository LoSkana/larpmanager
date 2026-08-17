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
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.translation import gettext_lazy as _

from larpmanager.models.access import EventRole
from larpmanager.models.accounting import Discount
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event, EventButton, EventConfig, EventText, ProgressStep
from larpmanager.models.experience import AbilityExp, AbilityTemplateExp, AbilityTypeExp, DeliveryExp, SystemExp
from larpmanager.models.form import (
    RegistrationOption,
    RegistrationQuestion,
    RegistrationQuestionApplicable,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.member import LogOperationType
from larpmanager.models.miscellanea import WorkshopModule, WorkshopOption, WorkshopQuestion
from larpmanager.models.registration import (
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSection,
    RegistrationSurcharge,
    RegistrationTicket,
)
from larpmanager.models.utils import generate_id, my_uuid_short
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
    RelationshipTag,
    SpeedLarp,
)
from larpmanager.utils.edit.backend import save_log

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponseRedirect

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CopyElement:
    """Definition of a group of elements that can be selected one by one during a copy."""

    model: type
    match_fields: tuple[str, ...] = ("name",)
    extra_filter: dict[str, Any] = field(default_factory=dict)


# Types of elements that can be copied, in the order they are shown
COPY_TARGETS: list[tuple[str, Any]] = [
    ("event", _("Event")),
    ("config", _("Configuration")),
    ("appearance", _("Appearance")),
    ("text", _("Texts")),
    ("navigation", _("Navigation")),
    ("role", _("Roles")),
    ("features", _("Features")),
    ("ticket", _("Registration Tickets")),
    ("question", _("Registration Form")),
    ("matchmaker_question", _("Matchmaker Form")),
    ("discount", _("Discount")),
    ("quota", _("Registration Quota")),
    ("installment", _("Registration Installment")),
    ("surcharge", _("Registration Surcharge")),
    ("writing_question", _("Character Sheet")),
    ("character", _("Characters")),
    ("experience", _("Experience")),
    ("faction", _("Factions")),
    ("quest", _("Quests and Traits")),
    ("prologue", _("Prologues")),
    ("speedlarp", _("SpeedLarps")),
    ("plot", _("Plots")),
    ("handout", _("Handout and templates")),
    ("workshop", _("Workshops")),
]

# Types made of multiple elements, of which single ones can be selected
COPY_ELEMENTS: dict[str, CopyElement] = {
    "text": CopyElement(EventText, match_fields=("typ", "language")),
    "navigation": CopyElement(EventButton),
    "role": CopyElement(EventRole),
    "ticket": CopyElement(RegistrationTicket),
    "question": CopyElement(
        RegistrationQuestion, extra_filter={"applicable": RegistrationQuestionApplicable.REGISTRATION}
    ),
    "matchmaker_question": CopyElement(
        RegistrationQuestion, extra_filter={"applicable": RegistrationQuestionApplicable.MATCHMAKER}
    ),
    "discount": CopyElement(Discount),
    "quota": CopyElement(RegistrationQuota, match_fields=("number",)),
    "installment": CopyElement(RegistrationInstallment, match_fields=("number",)),
    "surcharge": CopyElement(RegistrationSurcharge, match_fields=("number",)),
    "writing_question": CopyElement(WritingQuestion),
    "character": CopyElement(Character),
    "experience": CopyElement(AbilityExp),
    "faction": CopyElement(Faction),
    "quest": CopyElement(QuestType),
    "prologue": CopyElement(Prologue),
    "speedlarp": CopyElement(SpeedLarp),
    "plot": CopyElement(Plot),
    "handout": CopyElement(Handout),
    "workshop": CopyElement(WorkshopModule),
}


def get_copy_choices(features: Any) -> list[tuple[str, Any]]:
    """Return the element types available for copy, given the features of the event."""
    return [(key, label) for key, label in COPY_TARGETS if key != "matchmaker_question" or "matchmaker" in features]


def _element_label(instance: Any) -> str:
    """Return a short label for an element, avoiding the event name repeated by __str__."""
    name = getattr(instance, "name", None)
    if not name:
        return str(instance)
    if isinstance(instance, WritingQuestion):
        return f"{name} ({instance.get_applicable_display()})"
    return str(name)


def get_copy_sections(source_event_id: int, targets: list[str]) -> list[dict]:
    """List the single elements available for each selected type of the source event.

    Args:
        source_event_id: Event the elements are copied from
        targets: Types of elements selected for the copy

    Returns:
        List of sections, each with the type key, its label, and its elements

    """
    labels = dict(COPY_TARGETS)
    sections = []

    for key in targets:
        if key not in COPY_ELEMENTS:
            continue
        element = COPY_ELEMENTS[key]
        queryset = element.model.objects.filter(event_id=source_event_id, **element.extra_filter)
        elements = [{"id": instance.pk, "label": _element_label(instance)} for instance in queryset]
        if not elements:
            continue
        sections.append({"key": key, "label": labels.get(key, key), "elements": elements})

    return sections


def read_copy_picks(request: HttpRequest, targets: list[str]) -> dict[str, list[int]]:
    """Read from the request the single elements selected for each type."""
    picks = {}
    for key in targets:
        if key not in COPY_ELEMENTS:
            continue
        picks[key] = [int(value) for value in request.POST.getlist(f"pick_{key}") if value.isdigit()]
    return picks


COPY_SKIPPED_FIELDS = frozenset({"id", "uuid", "media_token", "access_token", "created", "updated", "number"})


def _copy_object_fields(target_object: Any, source_object: Any) -> None:
    """Overwrite the concrete fields of an existing target object with the source values."""
    # noinspection PyProtectedMember
    for model_field in source_object._meta.concrete_fields:  # noqa: SLF001  # Django model metadata
        if model_field.name in COPY_SKIPPED_FIELDS or model_field.primary_key or model_field.name == "event":
            continue
        setattr(target_object, model_field.attname, getattr(source_object, model_field.attname))


def _has_event_field(model_class: type) -> bool:
    """Check if the model is directly scoped to an event."""
    # noinspection PyProtectedMember
    return any(model_field.name == "event" for model_field in model_class._meta.concrete_fields)  # noqa: SLF001


def _clone_object(source_object: Any, target_event_id: int, *, keep_number: bool) -> Any:
    """Create a copy of the source object inside the target event."""
    source_object.pk = None
    if _has_event_field(type(source_object)):
        source_object.event_id = target_event_id
    # noinspection PyProtectedMember
    source_object._state.adding = True  # noqa: SLF001  # Django model state
    # Regenerate unique fields that need new values for the copy
    if hasattr(source_object, "uuid"):
        source_object.uuid = None  # Let UuidMixin.save() regenerate with retry logic
    if hasattr(source_object, "media_token"):
        source_object.media_token = ""  # Let auto_set_media_token signal regenerate
    for field_name, generation_function in {"access_token": my_uuid_short}.items():
        if not hasattr(source_object, field_name):
            continue
        setattr(source_object, field_name, generation_function())
    # Without a matching number in the target event, let the numbering be assigned anew
    if not keep_number and hasattr(source_object, "number"):
        source_object.number = None
    source_object.save()
    return source_object


def copy_class(
    target_event_id: int,
    source_event_id: int,
    model_class: type,
    extra_filter: dict[str, Any] | None = None,
    source_ids: list[int] | None = None,
    match_fields: tuple[str, ...] = ("name",),
    skip_m2m: tuple[str, ...] = (),
    target_filter: dict[str, Any] | None = None,
) -> dict[int, int]:
    """Copy objects of a given class from source event to target event.

    Objects of the target event are never deleted: a source object is written over the
    target object sharing the same match fields, or added as a new object when missing.

    Args:
        target_event_id: Target event ID to copy objects to
        source_event_id: Source event ID to copy objects from
        model_class: Django model class to copy instances of
        extra_filter: Optional additional filter kwargs restricting which objects are
            copied from the source, and matched in the target
        source_ids: Optional list of source object IDs, to copy only a subset of them
        match_fields: Fields identifying the same element across the two events
        skip_m2m: Many to many field names not to be copied (typically remapped later)
        target_filter: Optional filter kwargs restricting the target objects considered
            for the match, used for elements identified only inside their parent

    Returns:
        Mapping of source object ID to the corresponding target object ID

    """
    source_queryset = model_class.objects.all()
    if _has_event_field(model_class):
        source_queryset = source_queryset.filter(event_id=source_event_id)
    if extra_filter:
        source_queryset = source_queryset.filter(**extra_filter)
    if source_ids is not None:
        source_queryset = source_queryset.filter(pk__in=source_ids)

    id_map = {}
    for source_object in source_queryset:
        source_id = source_object.pk
        try:
            # save a copy of m2m relations
            many_to_many_data = {}

            # noinspection PyProtectedMember
            for model_field in source_object._meta.many_to_many:  # noqa: SLF001  # Django model metadata
                if model_field.name in skip_m2m:
                    continue
                many_to_many_data[model_field.name] = list(getattr(source_object, model_field.name).all())

            target_object = _find_matching_object(
                target_event_id, model_class, source_object, match_fields, extra_filter, target_filter
            )
            if target_object:
                _copy_object_fields(target_object, source_object)
                target_object.save()
            else:
                target_object = _clone_object(source_object, target_event_id, keep_number="number" in match_fields)

            id_map[source_id] = target_object.pk

            # copy m2m relations
            for field_name, related_values in many_to_many_data.items():
                getattr(target_object, field_name).set(related_values)
        except Exception as error:  # noqa: BLE001 - Complex object cloning may fail in many ways, log and continue
            logger.warning("found exp: %s", error)

    return id_map


def _find_matching_object(
    target_event_id: int,
    model_class: type,
    source_object: Any,
    match_fields: tuple[str, ...],
    extra_filter: dict[str, Any] | None,
    target_filter: dict[str, Any] | None = None,
) -> Any:
    """Return the target event object corresponding to the source one, if any."""
    lookup = {field_name: getattr(source_object, field_name) for field_name in match_fields}
    if any(value is None or value == "" for value in lookup.values()):
        return None

    target_queryset = model_class.objects.filter(**lookup)
    if _has_event_field(model_class):
        target_queryset = target_queryset.filter(event_id=target_event_id)
    if extra_filter:
        target_queryset = target_queryset.filter(**extra_filter)
    if target_filter:
        target_queryset = target_queryset.filter(**target_filter)
    return target_queryset.first()


def match_map(
    target_event_id: int,
    source_event_id: int,
    model_class: type,
    extra_filter: dict[str, Any] | None = None,
    match_fields: tuple[str, ...] = ("name",),
) -> dict[int, int]:
    """Map source event objects to the target event ones sharing the same match fields.

    Used to remap relationships towards elements that were not part of the copy.
    """
    target_queryset = model_class.objects.filter(event_id=target_event_id)
    source_queryset = model_class.objects.filter(event_id=source_event_id)
    if extra_filter:
        target_queryset = target_queryset.filter(**extra_filter)
        source_queryset = source_queryset.filter(**extra_filter)

    target_ids = {}
    for target_object in target_queryset:
        target_ids[tuple(getattr(target_object, field_name) for field_name in match_fields)] = target_object.pk

    id_map = {}
    for source_object in source_queryset:
        key = tuple(getattr(source_object, field_name) for field_name in match_fields)
        if key in target_ids:
            id_map[source_object.pk] = target_ids[key]

    return id_map


def remap_fk(model_class: type, copied: dict[int, int], parent_map: dict[int, int], field_name: str) -> None:
    """Point the foreign key of copied objects to the target event counterparts.

    Args:
        model_class: Model class of the copied objects
        copied: Mapping of source object ID to target object ID
        parent_map: Mapping of source related object ID to target related object ID
        field_name: Name of the foreign key field to remap

    """
    if not copied:
        return

    field_id = field_name + "_id"
    nullable = model_class._meta.get_field(field_name).null  # noqa: SLF001  # Django model metadata

    source_values = dict(model_class.objects.filter(pk__in=copied.keys()).values_list("pk", field_id))
    targets = model_class.objects.in_bulk(list(copied.values()))

    objects_to_update = []
    for source_id, target_id in copied.items():
        target_object = targets.get(target_id)
        if target_object is None:
            continue
        source_parent_id = source_values.get(source_id)
        target_parent_id = parent_map.get(source_parent_id)
        if target_parent_id is None and not (nullable and source_parent_id is not None):
            continue
        setattr(target_object, field_id, target_parent_id)
        objects_to_update.append(target_object)

    if objects_to_update:
        model_class.objects.bulk_update(objects_to_update, [field_id])


def remap_m2m(model_class: type, copied: dict[int, int], parent_map: dict[int, int], field_name: str) -> None:
    """Point a many to many relation of copied objects to the target event counterparts.

    Related elements without a counterpart in the target event are dropped.

    Args:
        model_class: Model class of the copied objects
        copied: Mapping of source object ID to target object ID
        parent_map: Mapping of source related object ID to target related object ID
        field_name: Name of the many to many field to remap

    """
    if not copied:
        return

    targets = model_class.objects.in_bulk(list(copied.values()))

    for source_object in model_class.objects.filter(pk__in=copied.keys()):
        target_object = targets.get(copied[source_object.pk])
        if target_object is None:
            continue
        related_ids = [
            parent_map[related_id]
            for related_id in getattr(source_object, field_name).values_list("pk", flat=True)
            if related_id in parent_map
        ]
        getattr(target_object, field_name).set(related_ids)


def copy_children(
    target_event_id: int,
    source_event_id: int,
    model_class: type,
    parent_map: dict[int, int],
    parent_field: str,
    match_fields: tuple[str, ...] = ("name",),
    skip_m2m: tuple[str, ...] = (),
) -> dict[int, int]:
    """Copy the children of already copied elements, matching them inside their own parent.

    Args:
        target_event_id: Target event ID to copy objects to
        source_event_id: Source event ID to copy objects from
        model_class: Model class of the children
        parent_map: Mapping of source parent ID to target parent ID
        parent_field: Name of the foreign key field pointing to the parent
        match_fields: Fields identifying the same child inside a given parent
        skip_m2m: Many to many field names not to be copied

    Returns:
        Mapping of source child ID to the corresponding target child ID

    """
    child_map = {}
    parent_field_id = parent_field + "_id"

    for source_parent_id, target_parent_id in parent_map.items():
        children_ids = list(
            model_class.objects.filter(**{parent_field_id: source_parent_id}).values_list("pk", flat=True)
        )
        if not children_ids:
            continue
        child_map.update(
            copy_class(
                target_event_id,
                source_event_id,
                model_class,
                source_ids=children_ids,
                match_fields=match_fields,
                skip_m2m=skip_m2m,
                target_filter={parent_field_id: target_parent_id},
            )
        )

    remap_fk(model_class, child_map, parent_map, parent_field)
    return child_map


def _element_map(
    target_event_id: int,
    source_event_id: int,
    model_class: type,
    copied: dict[int, int],
    match_fields: tuple[str, ...] = ("name",),
) -> dict[int, int]:
    """Map source elements to target ones, using the copied elements and the already existing ones."""
    return {**match_map(target_event_id, source_event_id, model_class, match_fields=match_fields), **copied}


def _remap_progress(model_class: type, copied: dict[int, int], target_event_id: int, source_event_id: int) -> None:
    """Point the progress step of copied writing elements to the target event ones."""
    if not copied:
        return
    remap_fk(model_class, copied, match_map(target_event_id, source_event_id, ProgressStep), "progress")


def copy(
    request: HttpRequest,
    context: dict,
    parent_event: Event,
    target_event: Event,
    data_types_to_copy: list,
    picks: dict[str, list[int]] | None = None,
) -> HttpResponseRedirect | None:
    """Copy event data from a parent event to the current event.

    Elements of the target event are never deleted: copied elements overwrite the ones
    with the same name, the others are left untouched.

    Args:
        request: The HTTP request object
        context: Context dictionary for the operation
        parent_event: The source event to copy data from
        target_event: The target event to copy data to
        data_types_to_copy: List of data types to copy
        picks: Optional single elements selected for each data type

    Returns:
        HttpResponseRedirect if error occurs, None if successful

    """
    # Validate parent event exists
    if not parent_event:
        return messages.error(request, _("No value has been selected for parent."))

    picks = picks or {}

    # Extract event IDs for copying operations
    parent_event_id = parent_event.id
    target_event_id = target_event.id

    # Prevent copying from the same event
    if parent_event_id == target_event_id:
        return messages.error(request, _("Can't copy from same event"))

    # Copy event-specific data based on targets
    copy_event(context, target_event_id, data_types_to_copy, target_event, parent_event_id, parent_event, picks)

    # Copy registration data between events
    copy_registration(target_event_id, parent_event_id, data_types_to_copy, picks)

    # Copy writing/story data between events
    copy_writing(target_event_id, parent_event_id, data_types_to_copy, picks)

    # Save changes to the target event
    target_event.save()
    save_log(
        context,
        Event,
        target_event,
        target_event.uuid,
        operation_type=LogOperationType.BULK,
        info=f"copy from event {parent_event_id}",
    )

    # Notify user of successful completion
    messages.success(request, _("Copy done"))
    return None


def copy_event(
    context: dict,
    target_event_id: Any,
    elements_to_copy: Any,
    target_event: object,
    source_event_id: Any,
    source_event: object,
    picks: dict[str, list[int]],
) -> None:
    """Copy event data and related objects from parent to new event.

    Args:
        context: Context dictionary with form information
        target_event_id: Target event ID
        elements_to_copy: List of elements to copy
        target_event: Target event instance
        source_event_id: Source parent event ID
        source_event: Source parent event instance
        picks: Single elements selected for each data type

    """
    # Define copy actions for each target type
    copy_actions = {
        "event": lambda: _copy_event_fields(context, target_event, source_event),
        "config": lambda: copy_class(target_event_id, source_event_id, EventConfig),
        "appearance": lambda: _copy_appearance_fields(context, target_event, source_event),
        "text": lambda: copy_class(
            target_event_id, source_event_id, EventText, source_ids=picks.get("text"), match_fields=("typ", "language")
        ),
        "role": lambda: copy_class(target_event_id, source_event_id, EventRole, source_ids=picks.get("role")),
        "features": lambda: _copy_features(target_event, source_event),
        "navigation": lambda: copy_class(
            target_event_id, source_event_id, EventButton, source_ids=picks.get("navigation")
        ),
    }

    # Execute copy actions for each target in the list
    for element_type in elements_to_copy:
        if element_type in copy_actions:
            copy_actions[element_type]()


def _copy_event_fields(context: dict, event: object, parent_event: object) -> None:
    """Copy basic event fields from parent to child event."""
    # Imported here, the event forms import this module: a top level import would be circular
    from larpmanager.forms.event import OrgaEventForm  # noqa: PLC0415

    for field_name in get_all_fields_from_form(OrgaEventForm, context):
        if field_name == "slug":
            continue
        field_value = getattr(parent_event, field_name)
        setattr(event, field_name, field_value)
    event.name = "copy - " + event.name


def _copy_appearance_fields(context: dict, child_event: object, parent_event: object) -> None:
    """Copy appearance fields from parent to child event."""
    # Imported here, the event forms import this module: a top level import would be circular
    from larpmanager.forms.event import OrgaAppearanceForm  # noqa: PLC0415

    for field_name in get_all_fields_from_form(OrgaAppearanceForm, context):
        if field_name == "event_css":
            copy_css(context, child_event, parent_event)
        elif field_name == "theme":
            continue
        else:
            field_value = getattr(parent_event, field_name)
            setattr(child_event, field_name, field_value)


def _copy_features(event: object, parent: Any) -> None:
    """Copy features from parent to child event."""
    for feature in parent.features.all():
        event.features.add(feature)
    event.save()


def copy_registration(
    target_event_id: int, source_event_id: int, targets: list[str], picks: dict[str, list[int]]
) -> None:
    """Copy registration components from one event to another based on specified targets.

    Args:
        target_event_id: Target event ID to copy to
        source_event_id: Source event ID to copy from
        targets: List of registration component types to copy
        picks: Single elements selected for each data type

    """
    # Copy registration tickets if requested
    ticket_map = {}
    if "ticket" in targets:
        ticket_map = copy_class(target_event_id, source_event_id, RegistrationTicket, source_ids=picks.get("ticket"))

    # Copy registration questions and their options, for each selected form type
    applicables = {
        "question": RegistrationQuestionApplicable.REGISTRATION,
        "matchmaker_question": RegistrationQuestionApplicable.MATCHMAKER,
    }
    for key, applicable in applicables.items():
        if key in targets:
            _copy_registration_questions(target_event_id, source_event_id, applicable, picks.get(key), ticket_map)

    # Copy discount configurations
    if "discount" in targets:
        copy_class(target_event_id, source_event_id, Discount, source_ids=picks.get("discount"))

    # Copy registration quotas
    if "quota" in targets:
        copy_class(
            target_event_id, source_event_id, RegistrationQuota, source_ids=picks.get("quota"), match_fields=("number",)
        )

    # Copy installment plans and link them to tickets
    if "installment" in targets:
        installment_map = copy_class(
            target_event_id,
            source_event_id,
            RegistrationInstallment,
            source_ids=picks.get("installment"),
            match_fields=("number",),
            skip_m2m=("tickets",),
        )
        tickets = _element_map(target_event_id, source_event_id, RegistrationTicket, ticket_map)
        remap_m2m(RegistrationInstallment, installment_map, tickets, "tickets")

    # Copy surcharge configurations
    if "surcharge" in targets:
        copy_class(
            target_event_id,
            source_event_id,
            RegistrationSurcharge,
            source_ids=picks.get("surcharge"),
            match_fields=("number",),
        )


def _copy_registration_questions(
    target_event_id: int,
    source_event_id: int,
    applicable: str,
    question_ids: list[int] | None,
    ticket_map: dict[int, int],
) -> None:
    """Copy registration questions of a given form type, with their sections and options."""
    question_filter = {"applicable": applicable}
    questions = RegistrationQuestion.objects.filter(event_id=source_event_id, **question_filter)
    if question_ids is not None:
        questions = questions.filter(pk__in=question_ids)

    selected_ids = list(questions.values_list("pk", flat=True))
    if not selected_ids:
        return

    # Copy only the sections holding the selected questions
    section_ids = [value for value in questions.values_list("section_id", flat=True) if value]
    section_map = copy_class(target_event_id, source_event_id, RegistrationSection, source_ids=section_ids)

    question_map = copy_class(
        target_event_id,
        source_event_id,
        RegistrationQuestion,
        extra_filter=question_filter,
        source_ids=selected_ids,
        skip_m2m=("tickets", "factions"),
    )
    remap_fk(RegistrationQuestion, question_map, section_map, "section")

    # Copy the options of each copied question
    copy_children(target_event_id, source_event_id, RegistrationOption, question_map, "question")

    # Point the question relations to the tickets and factions of the target event
    tickets = _element_map(target_event_id, source_event_id, RegistrationTicket, ticket_map)
    remap_m2m(RegistrationQuestion, question_map, tickets, "tickets")
    factions = match_map(target_event_id, source_event_id, Faction)
    remap_m2m(RegistrationQuestion, question_map, factions, "factions")


def _copy_writing_questions(
    target_event_id: int, source_event_id: int, targets: list[str], picks: dict[str, list[int]]
) -> tuple[dict[int, int], dict[int, int]]:
    """Copy character sheet questions and their options, returning both id mappings."""
    # When only characters are copied, all questions are needed to carry over their values
    question_ids = picks.get("writing_question") if "writing_question" in targets else None

    question_map = copy_class(
        target_event_id, source_event_id, WritingQuestion, source_ids=question_ids, skip_m2m=("requirements",)
    )
    option_map = copy_children(
        target_event_id, source_event_id, WritingOption, question_map, "question", skip_m2m=("requirements",)
    )

    # Point the prerequisites to the options of the target event
    remap_m2m(WritingQuestion, question_map, option_map, "requirements")
    remap_m2m(WritingOption, option_map, option_map, "requirements")

    return question_map, option_map


def _copy_characters(
    target_event_id: int,
    source_event_id: int,
    picks: dict[str, list[int]],
    question_map: dict[int, int],
    option_map: dict[int, int],
) -> dict[int, int]:
    """Copy characters with their configs, relationships, answers and choices."""
    character_map = copy_class(
        target_event_id, source_event_id, Character, source_ids=picks.get("character"), skip_m2m=("characters",)
    )
    if not character_map:
        return character_map

    characters = _element_map(target_event_id, source_event_id, Character, character_map)
    remap_m2m(Character, character_map, characters, "characters")
    remap_fk(Character, character_map, characters, "mirror")
    _remap_progress(Character, character_map, target_event_id, source_event_id)

    # Copy the configurations of each copied character
    copy_children(target_event_id, source_event_id, CharacterConfig, character_map, "character")

    # Copy relationships, keeping the tags they refer to
    tag_map = copy_class(target_event_id, source_event_id, RelationshipTag)
    _copy_relationships(target_event_id, source_event_id, characters, tag_map)

    # Copy the values given by the characters to the sheet questions
    _copy_writing_values(source_event_id, characters, question_map, option_map)

    return character_map


def _copy_relationships(
    target_event_id: int, source_event_id: int, characters: dict[int, int], tag_map: dict[int, int]
) -> None:
    """Copy character relationships, pointing them to the characters of the target event."""
    tags = _element_map(target_event_id, source_event_id, RelationshipTag, tag_map)

    for relationship in Relationship.objects.filter(source__event_id=source_event_id).prefetch_related("tags"):
        target_source_id = characters.get(relationship.source_id)
        target_target_id = characters.get(relationship.target_id)
        if not target_source_id or not target_target_id:
            continue

        target_relationship, _created = Relationship.objects.update_or_create(
            source_id=target_source_id,
            target_id=target_target_id,
            defaults={"text": relationship.text, "auto": relationship.auto},
        )
        tag_ids = [tags[tag_id] for tag_id in relationship.tags.values_list("pk", flat=True) if tag_id in tags]
        target_relationship.tags.set(tag_ids)


def _copy_writing_values(
    source_event_id: int,
    characters: dict[int, int],
    question_map: dict[int, int],
    option_map: dict[int, int],
) -> None:
    """Copy answers and choices given by the characters to the sheet questions."""
    for answer in WritingAnswer.objects.filter(question__event_id=source_event_id):
        target_element_id = characters.get(answer.element_id)
        target_question_id = question_map.get(answer.question_id)
        if not target_element_id or not target_question_id:
            continue
        WritingAnswer.objects.update_or_create(
            element_id=target_element_id, question_id=target_question_id, defaults={"text": answer.text}
        )

    for choice in WritingChoice.objects.filter(question__event_id=source_event_id):
        target_element_id = characters.get(choice.element_id)
        target_question_id = question_map.get(choice.question_id)
        target_option_id = option_map.get(choice.option_id)
        if not target_element_id or not target_question_id or not target_option_id:
            continue
        WritingChoice.objects.update_or_create(
            element_id=target_element_id, option_id=target_option_id, defaults={"question_id": target_question_id}
        )


def _copy_experience(
    target_event_id: int, source_event_id: int, ability_ids: list[int] | None, character_map: dict[int, int]
) -> None:
    """Copy experience elements (systems, ability types, abilities, deliveries) between events."""
    system_map = copy_class(target_event_id, source_event_id, SystemExp)
    type_map = copy_class(target_event_id, source_event_id, AbilityTypeExp)
    template_map = copy_class(target_event_id, source_event_id, AbilityTemplateExp)

    ability_map = copy_class(
        target_event_id,
        source_event_id,
        AbilityExp,
        source_ids=ability_ids,
        skip_m2m=("characters", "prerequisites", "requirements"),
    )
    remap_fk(AbilityExp, ability_map, system_map, "system")
    remap_fk(AbilityExp, ability_map, type_map, "typ")
    remap_fk(AbilityExp, ability_map, template_map, "template")

    characters = _element_map(target_event_id, source_event_id, Character, character_map)
    remap_m2m(AbilityExp, ability_map, characters, "characters")
    remap_m2m(
        AbilityExp,
        ability_map,
        _element_map(target_event_id, source_event_id, AbilityExp, ability_map),
        "prerequisites",
    )
    remap_m2m(AbilityExp, ability_map, match_map(target_event_id, source_event_id, WritingOption), "requirements")

    delivery_map = copy_class(target_event_id, source_event_id, DeliveryExp, skip_m2m=("characters",))
    remap_fk(DeliveryExp, delivery_map, system_map, "system")
    remap_m2m(DeliveryExp, delivery_map, characters, "characters")


def copy_writing(target_event_id: int, source_event_id: int, targets: list[str], picks: dict[str, list[int]]) -> None:
    """Copy writing elements from parent to child event.

    Args:
        target_event_id: Target event ID where elements will be copied to
        source_event_id: Parent event ID to copy elements from
        targets: List of element types to copy
        picks: Single elements selected for each data type

    """
    # Copy character sheet questions, then characters with their values
    question_map = {}
    option_map = {}
    character_map = {}
    if "writing_question" in targets or "character" in targets:
        question_map, option_map = _copy_writing_questions(target_event_id, source_event_id, targets, picks)
    if "character" in targets:
        character_map = _copy_characters(target_event_id, source_event_id, picks, question_map, option_map)

    characters = _element_map(target_event_id, source_event_id, Character, character_map)

    # Copy experience elements
    if "experience" in targets:
        _copy_experience(target_event_id, source_event_id, picks.get("experience"), character_map)

    _copy_writing_elements(target_event_id, source_event_id, targets, picks, characters)


def _copy_writing_elements(
    target_event_id: int,
    source_event_id: int,
    targets: list[str],
    picks: dict[str, list[int]],
    characters: dict[int, int],
) -> None:
    """Copy the writing elements not tied to the character sheet."""
    # Copy faction elements
    if "faction" in targets:
        faction_map = copy_class(
            target_event_id, source_event_id, Faction, source_ids=picks.get("faction"), skip_m2m=("characters",)
        )
        remap_m2m(Faction, faction_map, characters, "characters")
        _remap_progress(Faction, faction_map, target_event_id, source_event_id)

    # Copy quest-related elements
    if "quest" in targets:
        _copy_quests(target_event_id, source_event_id, picks.get("quest"))

    # Copy prologue elements
    if "prologue" in targets:
        prologue_map = copy_class(target_event_id, source_event_id, Prologue, source_ids=picks.get("prologue"))
        _remap_progress(Prologue, prologue_map, target_event_id, source_event_id)

    # Copy speedlarp elements
    if "speedlarp" in targets:
        copy_class(target_event_id, source_event_id, SpeedLarp, source_ids=picks.get("speedlarp"))

    # Copy plot elements and their character relations
    if "plot" in targets:
        plot_map = copy_class(
            target_event_id, source_event_id, Plot, source_ids=picks.get("plot"), skip_m2m=("characters",)
        )
        remap_m2m(Plot, plot_map, characters, "characters")
        _remap_progress(Plot, plot_map, target_event_id, source_event_id)
        _copy_plot_characters(plot_map, characters)

    # Copy handout and template elements
    if "handout" in targets:
        template_map = copy_class(target_event_id, source_event_id, HandoutTemplate)
        handout_map = copy_class(target_event_id, source_event_id, Handout, source_ids=picks.get("handout"))
        remap_fk(Handout, handout_map, template_map, "template")
        _remap_progress(Handout, handout_map, target_event_id, source_event_id)

    # Copy workshop elements, with their questions and options
    if "workshop" in targets:
        module_map = copy_class(target_event_id, source_event_id, WorkshopModule, source_ids=picks.get("workshop"))
        workshop_question_map = copy_children(target_event_id, source_event_id, WorkshopQuestion, module_map, "module")
        copy_children(target_event_id, source_event_id, WorkshopOption, workshop_question_map, "question")


def _copy_quests(target_event_id: int, source_event_id: int, quest_type_ids: list[int] | None) -> None:
    """Copy quest types with their quests and traits."""
    type_map = copy_class(target_event_id, source_event_id, QuestType, source_ids=quest_type_ids)
    quest_map = copy_children(target_event_id, source_event_id, Quest, type_map, "typ")
    trait_map = copy_children(target_event_id, source_event_id, Trait, quest_map, "quest", skip_m2m=("traits",))
    remap_m2m(Trait, trait_map, _element_map(target_event_id, source_event_id, Trait, trait_map), "traits")
    _remap_progress(Quest, quest_map, target_event_id, source_event_id)
    _remap_progress(Trait, trait_map, target_event_id, source_event_id)


def _copy_plot_characters(plot_map: dict[int, int], characters: dict[int, int]) -> None:
    """Copy the relations between copied plots and the characters of the target event."""
    for relation in PlotCharacterRel.objects.filter(plot_id__in=plot_map.keys()):
        target_plot_id = plot_map.get(relation.plot_id)
        target_character_id = characters.get(relation.character_id)
        if not target_plot_id or not target_character_id:
            continue
        PlotCharacterRel.objects.update_or_create(
            plot_id=target_plot_id, character_id=target_character_id, defaults={"text": relation.text}
        )


def copy_css(context: dict, event: Event, parent: Any) -> None:
    """Copy CSS file from parent event to current event.

    Args:
        context: Context object
        event: Target event to copy CSS to
        parent: Source event to copy CSS from

    """
    # Imported here, the event forms import this module: a top level import would be circular
    from larpmanager.forms.event import OrgaAppearanceForm  # noqa: PLC0415

    # Initialize appearance form and get source CSS path
    appearance_form = OrgaAppearanceForm(context=context)
    source_css_path = appearance_form.get_css_path(parent)

    # Exit early if source CSS file doesn't exist
    if not default_storage.exists(source_css_path):
        return

    # Read CSS content from source file
    try:
        css_content = default_storage.open(source_css_path).read().decode("utf-8")

        # Generate new CSS ID and save to target event
        event.css_code = generate_id(32)
        target_css_path = appearance_form.get_css_path(event)
        default_storage.save(target_css_path, ContentFile(css_content))
    except (OSError, UnicodeDecodeError, PermissionError):
        logger.exception("Failed to copy CSS file from %s", source_css_path)
        # Continue without copying CSS - event will work without custom CSS


def get_all_fields_from_form(form_class: Any, context: dict) -> Any:
    """Return names of all available fields from given Form instance."""
    fields = list(form_class(context=context).base_fields)

    for field_name in list(form_class(context=context).declared_fields):
        if field_name not in fields:
            fields.append(field_name)

    for excluded_field in ["slug"]:
        if excluded_field in fields:
            fields.remove(excluded_field)

    return fields
