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
"""Generic model-instance copy between events.

Split out of larpmanager.utils.core.copy: larpmanager.forms.event needs copy_class,
while larpmanager.utils.core.copy itself needs form classes from forms.event, so
keeping both in one module would create an import cycle.
"""

from __future__ import annotations

import logging
from typing import Any

from larpmanager.models.utils import my_uuid_short

logger = logging.getLogger(__name__)

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
