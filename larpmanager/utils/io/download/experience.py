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

from larpmanager.cache.experience import has_multiple_exp_systems
from larpmanager.models.experience import AbilityExp, AbilityTypeExp, CriterionExp, DeliveryExp, ModifierExp, RuleExp
from larpmanager.models.writing import Character, CharacterConfig, get_event_class_parent, get_event_elements


def _add_system_header(context: Any, column_headers: list[str]) -> bool:
    """Append the system column header when the event has multiple systems, and report it."""
    multiple_systems = has_multiple_exp_systems(context["event"].id)
    if multiple_systems:
        column_headers.append("system")
    return multiple_systems


def _system_cell(element: Any) -> str:
    """Return the experience system name of an element, empty string when unset."""
    return element.system.name if element.system else ""


def _visible_cell(element: Any) -> str:
    """Return the visible flag of an element as the lowercase text the upload accepts."""
    return "true" if element.visible else "false"


def export_abilities(context: Any) -> Any:
    """Export abilities data for an event.

    Args:
        context: Context dictionary containing event information

    Returns:
        list: Single-item list containing tuple of ("abilities", keys, values)
              where keys are column headers and values are ability data rows

    """
    column_headers = ["name", "cost", "typ", "descr", "prerequisites", "requirements", "visible"]
    multiple_systems = _add_system_header(context, column_headers)

    ability_queryset = (
        get_event_elements(context["event"].id, AbilityExp, context=context)
        .order_by("number")
        .select_related("typ", "system")
        .prefetch_related("requirements", "prerequisites")
    )
    ability_rows = []
    for ability in ability_queryset:
        row_data = [
            ability.name,
            ability.cost,
            ability.typ.name if ability.typ else "",
            ability.descr,
            ", ".join([prereq.name for prereq in ability.prerequisites.all()]),
            ", ".join([req.name for req in ability.requirements.all()]),
            _visible_cell(ability),
        ]
        if multiple_systems:
            row_data.append(_system_cell(ability))
        ability_rows.append(row_data)

    return [("abilities", column_headers, ability_rows)]


def export_ability_types(context: Any) -> Any:
    """Export ability types data for an event."""
    column_headers = ["name"]

    type_queryset = context["event"].get_elements(AbilityTypeExp).order_by("order")
    type_rows = [[ability_type.name] for ability_type in type_queryset]

    return [("ability_types", column_headers, type_rows)]


def export_criterions(context: Any) -> Any:
    """Export criterions data for an event."""
    column_headers = ["number", "name", "operation", "amount", "prerequisites", "requirements", "factions", "order"]
    multiple_systems = _add_system_header(context, column_headers)

    criterion_queryset = (
        get_event_elements(context["event"].id, CriterionExp, context=context)
        .order_by("order")
        .select_related("system")
        .prefetch_related("prerequisites", "requirements", "factions")
    )
    criterion_rows = []
    for criterion in criterion_queryset:
        row_data = [
            criterion.number,
            criterion.name,
            criterion.operation,
            criterion.amount,
            ", ".join([prereq.name for prereq in criterion.prerequisites.all()]),
            ", ".join([req.name for req in criterion.requirements.all()]),
            ", ".join([faction.name for faction in criterion.factions.all()]),
            criterion.order,
        ]
        if multiple_systems:
            row_data.append(_system_cell(criterion))
        criterion_rows.append(row_data)

    return [("criterions", column_headers, criterion_rows)]


def export_deliveries(context: Any) -> Any:
    """Export deliveries data for an event."""
    column_headers = ["number", "name", "amount", "characters", "order"]
    multiple_systems = _add_system_header(context, column_headers)

    delivery_queryset = (
        get_event_elements(context["event"].id, DeliveryExp, context=context)
        .order_by("order")
        .select_related("system")
        .prefetch_related("characters")
    )
    delivery_rows = []
    for delivery in delivery_queryset:
        row_data = [
            delivery.number,
            delivery.name,
            delivery.amount,
            ", ".join([character.name for character in delivery.characters.all()]),
            delivery.order,
        ]
        if multiple_systems:
            row_data.append(_system_cell(delivery))
        delivery_rows.append(row_data)

    return [("deliveries", column_headers, delivery_rows)]


def export_rules(context: Any) -> Any:
    """Export rules data for an event."""
    column_headers = ["number", "abilities", "field", "operation", "amount", "order"]

    rule_queryset = (
        get_event_elements(context["event"].id, RuleExp, context=context)
        .order_by("order")
        .select_related("field")
        .prefetch_related("abilities")
    )
    rule_rows = [
        [
            rule.number,
            ", ".join([ability.name for ability in rule.abilities.all()]),
            rule.field.name if rule.field else "",
            rule.operation,
            rule.amount,
            rule.order,
        ]
        for rule in rule_queryset
    ]

    return [("rules", column_headers, rule_rows)]


def export_modifiers(context: Any) -> Any:
    """Export modifiers data for an event."""
    column_headers = ["number", "abilities", "cost", "prerequisites", "requirements", "order"]

    modifier_queryset = (
        get_event_elements(context["event"].id, ModifierExp, context=context)
        .order_by("order")
        .prefetch_related("abilities", "prerequisites", "requirements")
    )
    modifier_rows = [
        [
            modifier.number,
            ", ".join([ability.name for ability in modifier.abilities.all()]),
            modifier.cost,
            ", ".join([prereq.name for prereq in modifier.prerequisites.all()]),
            ", ".join([req.name for req in modifier.requirements.all()]),
            modifier.order,
        ]
        for modifier in modifier_queryset
    ]

    return [("modifiers", column_headers, modifier_rows)]


def export_character_configs(context: Any) -> Any:
    """Export CharacterConfig entries for all characters in the event."""
    column_headers = ["character", "name", "value"]
    event_id = get_event_class_parent(context["event"].id, Character, context=context)
    rows = [
        [cfg.character.name, cfg.name, cfg.value]
        for cfg in CharacterConfig.objects.filter(character__event_id=event_id, deleted__isnull=True)
        .select_related("character")
        .order_by("character__number", "name")
    ]
    return [("character_config", column_headers, rows)]
