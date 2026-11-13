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

from django.db.models import F

from larpmanager.cache.question import get_cached_registration_questions
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    QuestionVisibility,
    RegistrationOption,
    RegistrationQuestionApplicable,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.registration import RegistrationTicket, TicketTier
from larpmanager.models.writing import get_event_elements
from larpmanager.utils.io.download.columns import _get_column_names
from larpmanager.utils.io.download.core import zip_exports

if TYPE_CHECKING:
    from django.http import HttpResponse


def orga_registration_form_download(context: dict) -> HttpResponse:
    """Download registration form data as a ZIP archive."""
    applicable = context.get("registration_typ", RegistrationQuestionApplicable.REGISTRATION)
    return zip_exports(context, export_registration_form(context, applicable), "Registration form")


def export_registration_form(
    context: dict, applicable: str = RegistrationQuestionApplicable.REGISTRATION
) -> list[tuple[str, list, list]]:
    """Export registration data to Excel format.

    Extracts registration questions and options from the event context and formats
    them for Excel export with proper column mappings and ordered data.

    Args:
        context: Context dictionary containing event and form data. Must include
            'event' key with an Event object that has get_event_elements method.
        applicable: RegistrationQuestionApplicable value scoping which questions/options
            are exported (registration vs matchmaker form).

    Returns:
        List of tuples where each tuple contains:
            - str: Sheet name for Excel export
            - list: Column headers
            - list: Data rows for the sheet

    """
    # Initialize mappings for question types and status values
    mappings = {
        "typ": BaseQuestionType.get_mapping(),
        "status": QuestionStatus.get_mapping(),
    }

    # Set export type and extract column names from context
    context["typ"] = "registration_form"
    _get_column_names(context)

    # Extract registration questions data
    column_headers = context["columns"][0].keys()
    questions = get_cached_registration_questions(context["event"].id, applicable=applicable)
    question_values = _extract_values(column_headers, questions, mappings)

    # Initialize exports list with registration questions sheet
    excel_exports = [("registration_questions", column_headers, question_values)]

    # Prepare registration options data with modified key for relation
    option_headers = list(context["columns"][1].keys())
    modified_option_headers = option_headers.copy()
    modified_option_headers[0] = f"{modified_option_headers[0]}__name"

    # Query registration options ordered by question order and option order, scoped to the
    # same form type as the questions above
    options_queryset = get_event_elements(context["event"].id, RegistrationOption, context=context).select_related(
        "question"
    )
    options_queryset = options_queryset.filter(question__applicable=applicable)
    options_queryset = options_queryset.order_by(F("question__order"), "order")
    option_values = _extract_values(modified_option_headers, options_queryset, mappings)

    # Add registration options sheet to exports
    excel_exports.append(("registration_options", option_headers, option_values))
    return excel_exports


def _extract_values(field_names: list, objects: list, field_mappings: dict) -> list[list]:
    """Extract and transform values from queryset based on field mappings.

    Args:
        field_names: List of field names to extract from queryset
        objects: List of items to extract values from
        field_mappings: Dictionary mapping field names to value transformation dictionaries

    Returns:
        List of lists containing extracted and transformed values for each row

    """
    all_values = []

    # Iterate through each row in the question list
    for row in objects:
        row_values = []

        # Process each field-value pair in the current row
        for field_name in field_names:
            # Handle Django's double-underscore notation for related fields
            if "__" in field_name:
                # Traverse the relationship chain (e.g., "question__name" -> row.question.name)
                field_value = row
                for part in field_name.split("__"):
                    # Support both dict and object access
                    field_value = field_value[part] if isinstance(field_value, dict) else getattr(field_value, part)
            else:
                # Support both dict and object access
                field_value = row[field_name] if isinstance(row, dict) else getattr(row, field_name)

            # Apply mapping transformation if field and value exist in mappings
            if field_value in field_mappings.get(field_name, {}):
                transformed_value = field_mappings[field_name][field_value]
            else:
                transformed_value = field_value
            row_values.append(transformed_value)

        # Add processed row to results
        all_values.append(row_values)

    return all_values


def orga_character_form_download(context: dict) -> HttpResponse:
    """Generate and download character forms as a zip archive."""
    return zip_exports(context, export_character_form(context), "Character form")


def export_character_form(context: dict) -> list[tuple[str, list, list]]:
    """Export character form questions and options to CSV format.

    This function extracts writing questions and their associated options from an event
    and formats them for CSV export. It processes question metadata (type, status,
    applicability, visibility) and organizes the data into exportable tuples.

    Args:
        context: Context dictionary containing:
            - event: Event object with writing questions and options
            - columns: Column configuration for export formatting

    Returns:
        List of export tuples, each containing:
            - name (str): Export section name ('writing_questions' or 'writing_options')
            - keys (list): Column headers for CSV export
            - values (list): Data rows for CSV export

    Note:
        The function exports two sections:
        1. Writing questions with their metadata
        2. Writing options linked to their parent questions

    """
    # Define mappings for enum fields to human-readable values
    field_mappings = {
        "typ": BaseQuestionType.get_mapping(),
        "status": QuestionStatus.get_mapping(),
        "applicable": QuestionApplicable.get_mapping(),
        "visibility": QuestionVisibility.get_mapping(),
    }

    # Set context type and prepare column configuration
    context["typ"] = "character_form"
    _get_column_names(context)

    # Extract and export writing questions
    column_headers = context["columns"][0].keys()
    questions_queryset = get_event_elements(context["event"].id, WritingQuestion, context=context).order_by(
        "applicable", "order"
    )
    question_values = _extract_values(column_headers, questions_queryset, field_mappings)

    # Initialize exports list with writing questions data
    exports = [("writing_questions", column_headers, question_values)]

    # Prepare column configuration for writing options
    option_headers = list(context["columns"][1].keys())
    modified_option_headers = option_headers.copy()
    # Modify first column to include question name relationship
    modified_option_headers[0] = f"{modified_option_headers[0]}__name"

    # Extract and export writing options with related question data
    options_queryset = get_event_elements(context["event"].id, WritingOption, context=context).select_related(
        "question"
    )
    options_queryset = options_queryset.order_by(F("question__order"), "order")
    option_values = _extract_values(modified_option_headers, options_queryset, field_mappings)

    # Add writing options data to exports
    exports.append(("writing_options", option_headers, option_values))
    return exports


def orga_tickets_download(request_context: dict) -> HttpResponse:
    """Download tickets as a ZIP archive."""
    return zip_exports(request_context, export_tickets(request_context), "Tickets")


def export_tickets(context: dict) -> list[tuple[str, list[str], list]]:
    """Export ticket data for the given event context.

    Args:
        context: Event context dictionary containing the event object.

    Returns:
        List containing tuple of (table_name, headers, data_rows).

    """
    # Define field mappings for data transformation
    mappings = {
        "tier": TicketTier.get_mapping(),
    }

    # Specify fields to extract from ticket objects
    field_keys = ["name", "tier", "description", "price", "max_available"]

    # Get all registration tickets for the event, ordered by number
    tickets_queryset = get_event_elements(context["event"].id, RegistrationTicket, context=context).order_by("number")

    # Extract and transform values using the defined mappings
    extracted_values = _extract_values(field_keys, tickets_queryset, mappings)

    return [("tickets", field_keys, extracted_values)]
