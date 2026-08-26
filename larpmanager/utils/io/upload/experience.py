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

from typing import TYPE_CHECKING

import pandas as pd
from django.db import transaction

from larpmanager.models.experience import AbilityExp, AbilityTypeExp, CriterionExp, DeliveryExp, ModifierExp, RuleExp
from larpmanager.models.form import WritingQuestion
from larpmanager.models.member import LogOperationType
from larpmanager.utils.core.common import get_event_class_parent, get_event_elements
from larpmanager.utils.edit.backend import save_log
from larpmanager.utils.io.upload.constants import _ABILITY_PLAIN_FIELDS, _RELATION_COLUMNS, MAX_CSV_ROWS
from larpmanager.utils.io.upload.csv_file import _get_file
from larpmanager.utils.io.upload.parsing import (
    _get_row_name,
    _get_row_number,
    _is_blank,
    _is_missing,
    _relation_value,
    _row_result,
    _skip_row_field,
    _to_decimal,
    _to_int,
)
from larpmanager.utils.io.upload.relations import (
    _assign_abilities,
    _assign_characters,
    _assign_factions,
    _assign_numeric,
    _assign_operation,
    _assign_prereq,
    _assign_requirements,
    _assign_system,
    _assign_type,
    _resolve_exp_system,
)

if TYPE_CHECKING:
    from django.forms import Form


def abilities_load(context: dict, form: Form) -> list[str]:
    """Load abilities from uploaded file and process each row."""
    # Extract and validate input file data
    (input_dataframe, processing_logs) = _get_file(context, form.cleaned_data["first"], 0)

    # Process each row if valid dataframe exists
    if input_dataframe is not None:
        if len(input_dataframe) > MAX_CSV_ROWS:
            return [f"ERR - File too large: {len(input_dataframe)} rows exceeds limit of {MAX_CSV_ROWS}"]
        for ability_row in input_dataframe.to_dict(orient="records"):
            # Load individual ability and collect processing logs
            processing_logs.append(_ability_load(context, ability_row))
    return processing_logs


def _skip_ability_field(field_name: str, field_value: object) -> bool:
    """Return whether an ability CSV field must be skipped, because already handled or empty.

    Unlike the other experience elements, an empty cell never clears an ability relation:
    the stored prerequisites and requirements are kept, and only a filled cell replaces them.
    """
    if field_name in ("name", "cost"):
        return True
    return _is_missing(field_value) or _is_blank(field_value)


def _apply_ability_field(
    context: dict, ability_element: AbilityExp, logs: list[str], field_name: str, field_value: object
) -> None:
    """Apply a single CSV field to an AbilityExp instance."""
    if field_name == "typ":
        _assign_type(context, ability_element, logs, field_value)
    elif field_name == "prerequisites":
        _assign_prereq(context, ability_element, logs, str(field_value))
    elif field_name == "requirements":
        _assign_requirements(context, ability_element, logs, str(field_value))
    elif field_name == "system":
        _assign_system(context, ability_element, logs, str(field_value))
    elif field_name == "visible":
        ability_element.visible = str(field_value).lower().strip() == "true"
    elif field_name in _ABILITY_PLAIN_FIELDS:
        setattr(ability_element, field_name, field_value)
    else:
        logs.append(f"WARN - unknown column ignored: {field_name}")


@transaction.atomic
def _ability_load(context: dict, csv_row: dict) -> str:
    """Load ability data from CSV row for bulk import.

    Creates or updates ability objects with comprehensive field validation,
    type assignment, prerequisite parsing, and requirement processing.

    Args:
        context: Context dictionary containing event and related data
        csv_row: Dictionary representing a CSV row with ability data

    Returns:
        str: Status message indicating success/failure of the operation

    Raises:
        ValueError: When required 'name' column is missing from csv_row
        AttributeError: When accessing invalid model fields

    """
    name, err = _get_row_name(csv_row)
    if err:
        return err

    event = context["event"]
    parent_event = get_event_class_parent(event.id, AbilityExp, context=context)

    # Match the stored ability ignoring case, so that a different casing updates it instead of duplicating it
    ability_element = AbilityExp.objects.filter(event=parent_event, name__iexact=name).order_by("number").first()
    was_created = ability_element is None
    if was_created:
        ability_element = AbilityExp.objects.create(
            event_id=parent_event,
            name=name,
            system=_resolve_exp_system(event, context=context),
        )

    logs = []

    # Apply cost only if the column is present in the uploaded file and has a valid value
    if "cost" in csv_row:
        cost_value = csv_row["cost"]
        if cost_value is not None and cost_value != "" and not pd.isna(cost_value):
            _assign_numeric(ability_element, logs, "cost", cost_value)

    # Process each field in the CSV row
    for field_name, field_value in csv_row.items():
        if _skip_ability_field(field_name, field_value):
            continue
        _apply_ability_field(context, ability_element, logs, field_name, field_value)

    # Save the element to database
    ability_element.save()

    # Log the operation for audit trail
    save_log(context, AbilityExp, ability_element, operation_type=LogOperationType.UPLOAD)

    # Return appropriate success message, together with the errors collected on its fields
    status = f"OK - Created {ability_element}" if was_created else f"OK - Updated {ability_element}"
    return _row_result(status, logs)


def ability_types_load(context: dict, form: Form) -> list[str]:
    """Load ability types from uploaded file and process each row."""
    (input_dataframe, processing_logs) = _get_file(context, form.cleaned_data["first"], 0)

    if input_dataframe is not None:
        if len(input_dataframe) > MAX_CSV_ROWS:
            return [f"ERR - File too large: {len(input_dataframe)} rows exceeds limit of {MAX_CSV_ROWS}"]
        for type_row in input_dataframe.to_dict(orient="records"):
            processing_logs.append(_ability_type_load(context, type_row))
    return processing_logs


def _ability_type_load(context: dict, csv_row: dict) -> str:
    """Load ability type data from a CSV row for bulk import."""
    name, err = _get_row_name(csv_row)
    if err:
        return err

    event = context["event"]
    parent_event = event.get_class_parent(AbilityTypeExp)

    # Match the stored ability type ignoring case, so a different casing updates it instead of duplicating it
    ability_type = AbilityTypeExp.objects.filter(event=parent_event, name__iexact=name).order_by("number").first()
    was_created = ability_type is None
    if was_created:
        ability_type = AbilityTypeExp.objects.create(event=parent_event, name=name)

    save_log(context, AbilityTypeExp, ability_type, operation_type=LogOperationType.UPLOAD)

    return f"OK - Created {ability_type}" if was_created else f"OK - Updated {ability_type}"


def rules_load(context: dict, form: Form) -> list[str]:
    """Load rules from uploaded file and process each row."""
    (input_dataframe, processing_logs) = _get_file(context, form.cleaned_data["first"], 0)
    if input_dataframe is not None:
        for rule_row in input_dataframe.to_dict(orient="records"):
            processing_logs.append(_rule_load(context, rule_row))
    return processing_logs


def _assign_rule_field(context: dict, rule: RuleExp, logs: list[str], value: str) -> None:
    """Assign the WritingQuestion FK field to a rule by name."""
    field_obj = (
        get_event_elements(context["event"].id, WritingQuestion, context=context)
        .filter(name__iexact=value.strip())
        .first()
    )
    if field_obj:
        rule.field = field_obj
    else:
        logs.append(f"ERR - field not found: {value}")


def _apply_rule_field(context: dict, rule: RuleExp, logs: list[str], field_name: str, field_value: object) -> None:
    """Apply a single CSV field to a RuleExp instance."""
    if field_name == "abilities":
        _assign_abilities(context, rule, logs, str(field_value))
    elif field_name == "field":
        _assign_rule_field(context, rule, logs, str(field_value))
    elif field_name == "amount":
        rule.amount = _to_decimal(field_value)
    elif field_name == "number":
        rule.number = _to_int(field_value)
    elif field_name == "order":
        rule.order = _to_int(field_value)
    elif field_name == "operation":
        _assign_operation(rule, logs, str(field_value))
    else:
        setattr(rule, field_name, field_value)


def _rule_load(context: dict, csv_row: dict) -> str:
    """Load rule data from CSV row for bulk import."""
    number, err = _get_row_number(csv_row)
    if err:
        return err

    event = context["event"]
    event_parent = get_event_class_parent(event.id, RuleExp, context=context)

    rule = RuleExp.objects.filter(event=event_parent, number=number).first()
    was_created = rule is None
    if was_created:
        rule = RuleExp(event_id=event_parent, number=number)

    logs = []
    abilities_value = None

    for field_name, field_value in csv_row.items():
        if field_value is None or field_name == "number":
            continue
        try:
            if pd.isna(field_value):
                continue
        except (TypeError, ValueError):
            pass
        if field_name == "abilities":
            abilities_value = str(field_value)
        else:
            _apply_rule_field(context, rule, logs, field_name, field_value)

    if was_created and not rule.field_id:
        return f"ERR - Cannot create rule '{number}': missing required 'field'"

    rule.save()
    save_log(context, RuleExp, rule, operation_type=LogOperationType.UPLOAD)

    if abilities_value:
        _assign_abilities(context, rule, logs, abilities_value)

    return f"OK - Created {rule}" if was_created else f"OK - Updated {rule}"


def modifiers_load(context: dict, form: Form) -> list[str]:
    """Load modifiers from uploaded file and process each row."""
    (input_dataframe, processing_logs) = _get_file(context, form.cleaned_data["first"], 0)
    if input_dataframe is not None:
        for modifier_row in input_dataframe.to_dict(orient="records"):
            processing_logs.append(_modifier_load(context, modifier_row))
    return processing_logs


def _modifier_load(context: dict, csv_row: dict) -> str:
    """Load modifier data from CSV row for bulk import."""
    number, err = _get_row_number(csv_row)
    if err:
        return err

    event = context["event"]

    (modifier, was_created) = ModifierExp.objects.get_or_create(
        event_id=get_event_class_parent(event.id, ModifierExp, context=context),
        number=number,
        defaults={"order": 0},
    )

    logs = []

    for field_name, field_value in csv_row.items():
        if not field_value or pd.isna(field_value) or field_name == "number":
            continue

        if field_name == "abilities":
            _assign_abilities(context, modifier, logs, str(field_value))
            continue

        if field_name == "prerequisites":
            _assign_prereq(context, modifier, logs, str(field_value))
            continue

        if field_name == "requirements":
            _assign_requirements(context, modifier, logs, str(field_value))
            continue

        if field_name == "cost":
            modifier.cost = _to_int(field_value)
            continue

        if field_name == "order":
            modifier.order = _to_int(field_value)
            continue

        setattr(modifier, field_name, field_value)

    modifier.save()
    save_log(context, ModifierExp, modifier, operation_type=LogOperationType.UPLOAD)

    return f"OK - Created {modifier}" if was_created else f"OK - Updated {modifier}"


def criterions_load(context: dict, form: Form) -> list[str]:
    """Load criterions from uploaded file and process each row."""
    (input_dataframe, processing_logs) = _get_file(context, form.cleaned_data["first"], 0)
    if input_dataframe is not None:
        if len(input_dataframe) > MAX_CSV_ROWS:
            return [f"ERR - File too large: {len(input_dataframe)} rows exceeds limit of {MAX_CSV_ROWS}"]
        for criterion_row in input_dataframe.to_dict(orient="records"):
            processing_logs.append(_criterion_load(context, criterion_row))
    return processing_logs


def _apply_criterion_field(
    context: dict, criterion: CriterionExp, logs: list[str], field_name: str, field_value: object
) -> None:
    """Apply a single CSV field to a CriterionExp instance."""
    if field_name not in _RELATION_COLUMNS and _is_blank(field_value):
        return

    if field_name == "prerequisites":
        _assign_prereq(context, criterion, logs, _relation_value(field_value))
    elif field_name == "requirements":
        _assign_requirements(context, criterion, logs, _relation_value(field_value))
    elif field_name == "factions":
        _assign_factions(context, criterion, logs, _relation_value(field_value))
    elif field_name == "system":
        _assign_system(context, criterion, logs, str(field_value))
    elif field_name == "operation":
        _assign_operation(criterion, logs, str(field_value))
    elif field_name == "amount":
        _assign_numeric(criterion, logs, "amount", field_value, decimal=True)
    elif field_name == "order":
        _assign_numeric(criterion, logs, "order", field_value)
    elif field_name == "name":
        criterion.name = str(field_value).strip()
    else:
        logs.append(f"WARN - unknown column ignored: {field_name}")


@transaction.atomic
def _criterion_load(context: dict, csv_row: dict) -> str:
    """Load criterion data from CSV row for bulk import."""
    number, err = _get_row_number(csv_row)
    if err:
        return err

    event = context["event"]
    parent_event = get_event_class_parent(event.id, CriterionExp, context=context)

    criterion = CriterionExp.objects.filter(event=parent_event, number=number).first()
    was_created = criterion is None
    if was_created:
        # The name is required to create a criterion, while it may be omitted when updating one
        name, err = _get_row_name(csv_row)
        if err:
            return err
        criterion = CriterionExp.objects.create(
            event_id=parent_event,
            number=number,
            name=name,
            system=_resolve_exp_system(event, context=context),
            order=0,
        )

    logs = []

    for field_name, field_value in csv_row.items():
        if _skip_row_field(field_name, field_value, ("number",)):
            continue
        _apply_criterion_field(context, criterion, logs, field_name, field_value)

    criterion.save()
    save_log(context, CriterionExp, criterion, operation_type=LogOperationType.UPLOAD)

    status = f"OK - Created {criterion}" if was_created else f"OK - Updated {criterion}"
    return _row_result(status, logs)


def deliveries_load(context: dict, form: Form) -> list[str]:
    """Load deliveries from uploaded file and process each row."""
    (input_dataframe, processing_logs) = _get_file(context, form.cleaned_data["first"], 0)
    if input_dataframe is not None:
        if len(input_dataframe) > MAX_CSV_ROWS:
            return [f"ERR - File too large: {len(input_dataframe)} rows exceeds limit of {MAX_CSV_ROWS}"]
        for delivery_row in input_dataframe.to_dict(orient="records"):
            processing_logs.append(_delivery_load(context, delivery_row))
    return processing_logs


def _row_delivery_number(csv_row: dict, logs: list[str]) -> int | None:
    """Return the number requested by the row, None when missing or unparsable."""
    value = csv_row.get("number")
    if _is_missing(value) or _is_blank(value):
        return None
    try:
        return _to_int(value)
    except (TypeError, ValueError, ArithmeticError):
        logs.append(f"WARN - invalid number value, assigned automatically: {value}")
        return None


def _free_delivery_number(parent_event: object, number: int | None, logs: list[str]) -> int | None:
    """Return the requested number, only if not already taken by another delivery."""
    if number is None:
        return None
    if DeliveryExp.objects.filter(event=parent_event, number=number).exists():
        logs.append(f"WARN - number already taken, assigned automatically: {number}")
        return None
    return number


def _find_delivery(parent_event: object, name: str, number: int | None, logs: list[str]) -> DeliveryExp | None:
    """Return the existing delivery the row refers to, None when it must be created.

    Delivery names are not unique, so when several share the uploaded name the number
    of the row selects which one is updated, falling back to the lowest numbered.
    """
    matches = list(DeliveryExp.objects.filter(event=parent_event, name__iexact=name).order_by("number"))
    if not matches:
        return None
    if len(matches) == 1:
        chosen = matches[0]
    else:
        chosen = next((match for match in matches if match.number == number), matches[0])
        logs.append(f"WARN - several deliveries named {name}, updated the one with number {chosen.number}")

    # The number of an existing delivery is never reassigned from the file
    if number is not None and number != chosen.number:
        logs.append(f"WARN - number kept as {chosen.number}, ignoring the uploaded one: {number}")
    return chosen


def _apply_delivery_field(
    context: dict, delivery: DeliveryExp, logs: list[str], field_name: str, field_value: object
) -> None:
    """Apply a single CSV field to a DeliveryExp instance."""
    if field_name not in _RELATION_COLUMNS and _is_blank(field_value):
        return

    if field_name == "system":
        _assign_system(context, delivery, logs, str(field_value))
    elif field_name == "characters":
        _assign_characters(context, delivery, logs, _relation_value(field_value))
    elif field_name in ("amount", "order"):
        _assign_numeric(delivery, logs, field_name, field_value)
    else:
        logs.append(f"WARN - unknown column ignored: {field_name}")


@transaction.atomic
def _delivery_load(context: dict, csv_row: dict) -> str:
    """Load delivery data from CSV row for bulk import."""
    name, err = _get_row_name(csv_row)
    if err:
        return err

    event = context["event"]
    parent_event = get_event_class_parent(event.id, DeliveryExp, context=context)

    logs = []
    number = _row_delivery_number(csv_row, logs)

    delivery = _find_delivery(parent_event, name, number, logs)
    was_created = delivery is None
    if was_created:
        # Keep the uploaded number only on creation, and only when still available
        fields = {"system": _resolve_exp_system(event, context=context), "amount": 0}
        free_number = _free_delivery_number(parent_event, number, logs)
        if free_number is not None:
            fields["number"] = free_number
        delivery = DeliveryExp.objects.create(event_id=parent_event, name=name, **fields)

    for field_name, field_value in csv_row.items():
        if _skip_row_field(field_name, field_value, ("name", "number")):
            continue
        _apply_delivery_field(context, delivery, logs, field_name, field_value)

    delivery.save()
    save_log(context, DeliveryExp, delivery, operation_type=LogOperationType.UPLOAD)

    status = f"OK - Created {delivery}" if was_created else f"OK - Updated {delivery}"
    return _row_result(status, logs)
