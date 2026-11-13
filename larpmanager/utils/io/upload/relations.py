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

from typing import Any

from larpmanager.cache.experience import clear_event_exp_systems_cache, get_event_exp_systems
from larpmanager.models.experience import AbilityExp, AbilityTypeExp, Operation, SystemExp
from larpmanager.models.writing import get_event_class_parent, get_event_elements
from larpmanager.utils.io.upload.constants import (
    _REL_CHARACTERS,
    _REL_FACTIONS,
    _REL_PREREQUISITES,
    _REL_REQUIREMENTS,
    MAX_COMMA_VALUES,
)
from larpmanager.utils.io.upload.parsing import _to_decimal, _to_int


def _assign_relation(
    context: dict,
    element: Any,
    logs: list[str],
    value: object,
    relation: tuple[str, type, str],
    *,
    replace: bool = True,
) -> None:
    """Assign a many-to-many relation of an element from comma-separated names.

    Args:
        context: Context dict containing 'event' key with Event instance
        element: Target element owning the relation
        logs: List to append error messages to
        value: Comma-separated element names
        relation: Tuple of relation attribute name, related model, and label used in errors
        replace: If set, the uploaded list replaces the current one, so that the upload stays
            idempotent and an empty value clears the relation; otherwise names are only added

    """
    (relation_name, related_model, label) = relation
    raw_names = [raw_name for raw_name in str(value).split(",") if raw_name.strip()]
    if len(raw_names) > MAX_COMMA_VALUES:
        logs.append(f"ERR - Too many {relation_name}: {len(raw_names)} exceeds limit of {MAX_COMMA_VALUES}")
        return

    # A relation needs a primary key, while the fields set so far are left to the final save of the row
    if element.pk is None:
        element.save()

    manager = getattr(element, relation_name)
    if replace:
        manager.clear()
    for raw_name in raw_names:
        # Look up the related element by name (case-insensitive)
        related_element = (
            get_event_elements(context["event"].id, related_model, context=context)
            .filter(name__iexact=raw_name.strip())
            .first()
        )
        if related_element:
            manager.add(related_element)
        else:
            logs.append(f"{label} not found: {raw_name}")


def _assign_prereq(
    context: dict,
    element: AbilityExp,
    logs: list[str],
    value: str,
) -> None:
    """Assign prerequisite abilities to an element from comma-separated names."""
    _assign_relation(context, element, logs, value, _REL_PREREQUISITES)


def _assign_requirements(
    context: dict,
    writing_element: Any,
    error_logs: list[str],
    requirement_names: str,
    *,
    replace: bool = True,
) -> None:
    """Assign writing option requirements to an element from comma-separated names."""
    _assign_relation(context, writing_element, error_logs, requirement_names, _REL_REQUIREMENTS, replace=replace)


def _assign_abilities(
    context: dict,
    element: Any,
    logs: list[str],
    value: str,
) -> None:
    """Assign abilities to element from comma-separated names."""
    for ability_name in value.split(","):
        ability = (
            get_event_elements(context["event"].id, AbilityExp, context=context)
            .filter(name__iexact=ability_name.strip())
            .first()
        )
        if ability:
            element.save()
            element.abilities.add(ability)
        else:
            logs.append(f"Ability not found: {ability_name}")


def _assign_factions(context: dict, element: Any, logs: list[str], value: str) -> None:
    """Assign factions to an element from comma-separated names."""
    _assign_relation(context, element, logs, value, _REL_FACTIONS)


def _assign_characters(context: dict, element: Any, logs: list[str], value: str) -> None:
    """Assign characters to an element from comma-separated names."""
    _assign_relation(context, element, logs, value, _REL_CHARACTERS)


def _assign_numeric(element: Any, logs: list[str], field_name: str, value: object, *, decimal: bool = False) -> None:
    """Assign a numeric field to an element, logging an error for values that cannot be parsed."""
    try:
        setattr(element, field_name, _to_decimal(value) if decimal else _to_int(value))
    except (TypeError, ValueError, ArithmeticError):
        logs.append(f"ERR - invalid {field_name} value: {value}")


def _assign_type(
    context: dict,
    ability_element: AbilityExp,
    error_logs: list[str],
    ability_type_name: str,
) -> None:
    """Assign ability type to element from event context."""
    # Query ability type by name from event context
    ability_type = (
        get_event_elements(context["event"].id, AbilityTypeExp, context=context)
        .filter(name__iexact=ability_type_name)
        .first()
    )
    if ability_type:
        ability_element.typ = ability_type
    else:
        # Log error if ability type not found
        error_logs.append(f"ERR - quest type not found: {ability_type_name}")


def _assign_system(context: dict, element: Any, logs: list[str], value: str) -> None:
    """Assign the experience system to an element by name."""
    system = (
        get_event_elements(context["event"].id, SystemExp, context=context).filter(name__iexact=value.strip()).first()
    )
    if system:
        element.system = system
    else:
        logs.append(f"ERR - system not found: {value}")


def _assign_operation(element: Any, logs: list[str], value: str) -> None:
    """Assign the operation to an element by value string (ADD/SUB/MUL/DIV)."""
    operation_map = {op.value: op for op in Operation}
    op_val = value.strip().upper()
    if op_val in operation_map:
        element.operation = operation_map[op_val]
    else:
        logs.append(f"ERR - unknown operation: {value}")


def _resolve_exp_system(event: Any, *, context: dict | None = None) -> Any:
    """Return the first SystemExp for the event, creating it if none exists."""
    systems = get_event_exp_systems(event.id)
    if systems:
        return systems[0]
    parent_id = get_event_class_parent(event.id, SystemExp, context=context)
    system = SystemExp.objects.create(event_id=parent_id, name="XP", number=1)
    clear_event_exp_systems_cache(parent_id)
    return system
