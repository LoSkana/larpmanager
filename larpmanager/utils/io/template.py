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
"""Generation of example CSV templates offered as download for the upload forms."""

from __future__ import annotations

from typing import Any

from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    RegistrationQuestionType,
    WritingQuestionType,
)
from larpmanager.utils.io.download import _get_column_names

# Example value shown for each question type in the generated templates
TEMPLATE_VALUE_MAPPING = {
    BaseQuestionType.SINGLE: "option name",
    BaseQuestionType.MULTIPLE: "option names (comma separated)",
    BaseQuestionType.TEXT: "field text",
    BaseQuestionType.PARAGRAPH: "field long text",
    BaseQuestionType.EDITOR: "field html text",
    WritingQuestionType.NAME: "element name",
    WritingQuestionType.TEASER: "element presentation",
    WritingQuestionType.SHEET: "element text",
    WritingQuestionType.COVER: "element cover (utils path)",
    WritingQuestionType.FACTIONS: "faction names (comma separated)",
    WritingQuestionType.TITLE: "title short text",
    WritingQuestionType.MIRROR: "name of mirror character",
    WritingQuestionType.HIDE: "hide (true or false)",
    WritingQuestionType.LOCKED: "locked (true or false)",
    WritingQuestionType.PROGRESS: "name of progress step",
    WritingQuestionType.ASSIGNED: "name of assigned staff",
    WritingQuestionType.COMPUTED: "computed value (read-only)",
    "character_status": "character status (c/s/r/a)",
    "character_assigned": "name of assigned staff",
    RegistrationQuestionType.TICKET: "name of the ticket",
    RegistrationQuestionType.ADDITIONAL: "number of additional tickets",
    RegistrationQuestionType.PWYW: "amount of free donation",
    RegistrationQuestionType.QUOTA: "number of quotas to split the fee",
    RegistrationQuestionType.SURCHARGE: "surcharge applied",
}


def build_upload_template(context: dict, upload_type: str) -> list[tuple[str, list[str], list[list[str]]]]:
    """Build the example template exports for the given upload type.

    Fills the column names in the context, then dispatches to the builder matching
    the requested type, falling back to the generic form template.

    Args:
        context: Context dictionary, must contain the event and the "typ" entry
        upload_type: Type of elements the template is generated for

    Returns:
        List of tuples containing template name, column keys, and row values

    """
    _get_column_names(context)

    # Writing elements share a single builder, driven by the writing type in the context
    if context.get("writing_typ"):
        return _writing_template(context, upload_type, TEMPLATE_VALUE_MAPPING)

    if upload_type == "registration":
        return _reg_template(context, upload_type, TEMPLATE_VALUE_MAPPING)

    builders = {
        "registration_ticket": _ticket_template,
        "exp_abilitie": _ability_template,
        "exp_ability_type": _ability_type_template,
        "exp_rule": _rule_template,
        "exp_modifier": _modifier_template,
        "exp_criterion": _criterion_template,
        "exp_deliverie": _delivery_template,
    }
    return builders.get(upload_type, _form_template)(context)


def _ticket_template(context: dict) -> Any:
    """Generate template for ticket tier uploads with example data."""
    export_data = []
    field_example_values = {
        "name": "Basic Ticket",
        "tier": "1",
        "description": "Standard admission ticket",
        "price": "50",
        "max_available": "100",
    }
    column_names = list(context["columns"][0].keys())
    example_row_values = []
    for field_name, example_value in field_example_values.items():
        if field_name not in column_names:
            continue
        example_row_values.append(example_value)
    export_data.append(("tickets", column_names, [example_row_values]))
    return export_data


def _ability_template(context: dict) -> Any:
    """Generate template for ability uploads with example data.

    Args:
        context: Context dictionary containing column definitions

    Returns:
        list: Export data containing ability template with example values

    """
    export_data = []
    field_example_values = {
        "name": "Ability name",
        "cost": "Ability cost",
        "typ": "Ability type",
        "descr": "Ability description",
        "prerequisites": "Prerequisite abilities, comma-separated",
        "requirements": "Character options, comma-separated",
        "visible": "true",
        "system": "Experience system name",
    }
    column_names = list(context["columns"][0].keys())
    example_row_values = [field_example_values.get(column_name, "") for column_name in column_names]
    export_data.append(("abilities", column_names, [example_row_values]))
    return export_data


def _ability_type_template(context: dict) -> Any:
    """Generate template for ability type uploads with example data."""
    field_example_values = {"name": "Ability type name"}
    column_names = list(context["columns"][0].keys())
    example_row = [field_example_values.get(column_name, "") for column_name in column_names]
    return [("ability_types", column_names, [example_row])]


def _rule_template(context: dict) -> Any:
    """Generate template for rule uploads with example data."""
    field_example_values = {
        "name": "Rule name",
        "abilities": "Ability name, comma-separated",
        "field": "Character field name",
        "operation": "ADD",
        "amount": "10",
        "order": "1",
    }
    column_names = list(context["columns"][0].keys())
    example_row = [field_example_values.get(column_name, "") for column_name in column_names]
    return [("rules", column_names, [example_row])]


def _modifier_template(context: dict) -> Any:
    """Generate template for modifier uploads with example data."""
    field_example_values = {
        "name": "Modifier name",
        "abilities": "Ability name, comma-separated",
        "cost": "5",
        "prerequisites": "Prerequisite ability, comma-separated",
        "requirements": "Character option, comma-separated",
        "order": "1",
    }
    column_names = list(context["columns"][0].keys())
    example_row = [field_example_values.get(column_name, "") for column_name in column_names]
    return [("modifiers", column_names, [example_row])]


def _criterion_template(context: dict) -> Any:
    """Generate template for criterion uploads with example data."""
    field_example_values = {
        "number": "1",
        "name": "Criterion name",
        "operation": "ADD",
        "amount": "10",
        "prerequisites": "Prerequisite abilities, comma-separated",
        "requirements": "Character options, comma-separated",
        "factions": "Factions name, comma-separated",
        "order": "1",
        "system": "Experience system name",
    }
    column_names = list(context["columns"][0].keys())
    example_row = [field_example_values.get(column_name, "") for column_name in column_names]
    return [("criterions", column_names, [example_row])]


def _delivery_template(context: dict) -> Any:
    """Generate template for delivery uploads with example data."""
    field_example_values = {
        "number": "1",
        "name": "Delivery name",
        "amount": "10",
        "characters": "Characters name, comma-separated",
        "order": "1",
        "system": "Experience system name",
    }
    column_names = list(context["columns"][0].keys())
    example_row = [field_example_values.get(column_name, "") for column_name in column_names]
    return [("deliveries", column_names, [example_row])]


def _form_template(context: dict) -> list[tuple[str, list[str], list[list[str]]]]:
    """Generate template files for form questions and options upload.

    Creates sample data templates for both questions and options that can be used
    for bulk upload functionality. The templates include predefined values that
    serve as examples for users.

    Args:
        context: Context dictionary containing column definitions with the structure:
            - columns[0]: Dictionary with question field definitions
            - columns[1]: Dictionary with option field definitions

    Returns:
        List of tuples where each tuple contains:
            - str: Template type ("questions" or "options")
            - list[str]: Column headers/keys
            - list[list[str]]: Sample data rows

    """
    template_exports = []

    # Define sample data for questions template
    sample_question_data = {
        "name": "Question Name",
        "typ": "multi-choice",
        "description": "Question Description",
        "status": "optional",
        "applicable": "character",
        "visibility": "public",
        "max_length": "1",
    }

    # Extract available question fields from context
    question_column_keys = list(context["columns"][0].keys())

    # Build values list matching available fields, preserving column order
    question_sample_values = [sample_question_data.get(field_name, "") for field_name in question_column_keys]

    # Add questions template to exports
    template_exports.append(("questions", question_column_keys, [question_sample_values]))

    # Define sample data for options template
    sample_option_data = {
        "question": "Question Name",
        "name": "Option Name",
        "description": "Option description",
        "max_available": "2",
        "price": "10",
        "requirements": "Other Option Name",
    }

    # Extract available option fields from context
    option_column_keys = list(context["columns"][1].keys())

    # Build values list matching available fields, preserving column order
    option_sample_values = [sample_option_data.get(field_name, "") for field_name in option_column_keys]

    # Add options template to exports
    template_exports.append(("options", option_column_keys, [option_sample_values]))

    return template_exports


def _reg_template(
    context: dict,
    template_type: str,
    value_mapping: dict,
) -> list[tuple[str, list[str], list[list[str]]]]:
    """Generate registration template data for export.

    Creates a template with predefined default values and dynamic fields
    based on the provided context and value mapping.

    Args:
        context: Context dictionary containing columns and fields information
        template_type: Template type identifier for naming
        value_mapping: Mapping of field types to their default values

    Returns:
        List of tuples containing template name, column keys, and row values

    """
    # Extract existing column keys from context
    column_keys = list(context["columns"][0].keys())
    column_keys.extend([key for key in context["fields"] if key not in column_keys])

    # Define default values for common registration fields
    default_values = {"email": "user@test.it", "characters": "Test Character"}

    # Create row values
    row_values = []
    for key in column_keys:
        if key in default_values:
            row_values.append(default_values[key])
        else:
            field_type = context["fields"][key]
            row_values.append(value_mapping[field_type])

    # Create export tuple with template name, keys, and values
    return [(f"{template_type} - template", column_keys, [row_values])]


def _writing_template(
    context: dict,
    type_prefix: str,
    value_mapping: dict,
) -> list[tuple[str, list[str], list[list[str]]]]:
    """Generate template data for writing export with field mappings.

    Creates export templates for different writing types including base templates
    and conditional templates for relationships and roles based on features.

    Args:
        context: Context dictionary containing:
            - fields: Dict mapping field names to field types
            - writing_typ: QuestionApplicable enum value for writing type
            - features: Set of enabled feature names
            - columns: Dict containing column definitions (when applicable)
        type_prefix: Type string used as prefix for the template name
        value_mapping: Dictionary mapping field types to their example values

    Returns:
        List of tuples containing template data where each tuple is:
        (template_name, column_keys, row_values_list)

    """
    # Extract non-skipped fields and their corresponding example values
    column_keys = [key for key, field_type in context["fields"].items() if field_type != "skip"]
    example_values = [
        value_mapping[field_type] for _field, field_type in context["fields"].items() if field_type != "skip"
    ]

    # Add type-specific prefix fields based on writing type
    if context["writing_typ"] == QuestionApplicable.QUEST:
        column_keys.insert(0, "typ")
        example_values.insert(0, "name of quest type")
    elif context["writing_typ"] == QuestionApplicable.TRAIT:
        column_keys.insert(0, "quest")
        example_values.insert(0, "name of quest")

    # Create base template export
    template_exports = [(f"{type_prefix} - template", column_keys, [example_values])]

    # Add relationships template for character writing when feature is enabled
    if context["writing_typ"] == QuestionApplicable.CHARACTER and "relationships" in context["features"]:
        template_exports.append(
            (
                "relationships - template",
                list(context["columns"][1].keys()),
                [["Test Character", "Another Character", "Super pals"]],
            ),
        )

    # Add roles template for plot writing
    if context["writing_typ"] == QuestionApplicable.PLOT:
        template_exports.append(
            (
                "roles - template",
                list(context["columns"][1].keys()),
                [["Test Plot", "Test Character", "Gonna be a super star"]],
            ),
        )
    return template_exports
