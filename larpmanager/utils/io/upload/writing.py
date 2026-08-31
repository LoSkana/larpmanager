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

from typing import TYPE_CHECKING, Any

import pandas as pd

from larpmanager.cache.question import get_cached_writing_questions
from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    RegistrationAnswer,
    RegistrationChoice,
    WritingAnswer,
    WritingChoice,
    WritingQuestionType,
)
from larpmanager.models.member import LogOperationType, Member
from larpmanager.models.writing import (
    Character,
    CharacterStatus,
    Faction,
    Plot,
    PlotCharacterRel,
    Relationship,
    get_event_class_parent,
    get_event_elements,
)
from larpmanager.utils.edit.backend import save_log
from larpmanager.utils.io.upload.constants import MAX_COMMA_VALUES, MAX_CSV_ROWS
from larpmanager.utils.io.upload.csv_file import _get_file
from larpmanager.utils.io.upload.features import _activate_features_from_columns
from larpmanager.utils.io.upload.parsing import _strip_number_prefix, _text_to_html_paragraphs

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.forms import Form

    from larpmanager.models.base import BaseModel
    from larpmanager.models.registration import Registration


def writing_load(context: dict, form: Form) -> list[str]:
    """Load writing data from uploaded files and process relationships.

    Processes uploaded files containing writing elements and their relationships.
    Handles both character and plot types with their respective relationship data.

    Args:
        context: Context dictionary containing event, writing_typ, and typ keys
        form: Django form object with cleaned_data containing uploaded files

    Returns:
        List of log messages documenting the loading process and any errors

    Note:
        For character type, processes main data file and optional relationships file.
        For plot type, processes main data file and optional plot relationships file.

    """
    logs = []

    # Process main writing data file
    uploaded_file = form.cleaned_data.get("first", None)
    if uploaded_file:
        (input_dataframe, logs) = _get_file(context, uploaded_file, 0)

        # Get questions for the writing type with their options
        writing_questions = get_cached_writing_questions(context["event"].id, context["writing_typ"])
        questions_dict = _get_questions(writing_questions)

        # Activate features based on uploaded columns
        if input_dataframe is not None:
            _activate_features_from_columns(context, input_dataframe.columns.tolist(), writing_questions)

        # Process each row of writing data
        if input_dataframe is not None:
            if len(input_dataframe) > MAX_CSV_ROWS:
                return [f"ERR - File too large: {len(input_dataframe)} rows exceeds limit of {MAX_CSV_ROWS}"]
            for row in input_dataframe.to_dict(orient="records"):
                logs.append(element_load(context, row, questions_dict))

    # Process character relationships if type is character
    if context["typ"] == "character":
        _writing_load_relationships(context, form, logs)

    # Process plot relationships if type is plot
    if context["typ"] == "plot":
        _writing_load_plot_rels(context, form, logs)

    return logs


def _writing_load_relationships(context: dict, form: Form, logs: list[str]) -> None:
    """Load character relationships from uploaded file.

    Processes an uploaded CSV/Excel file containing character relationship data,
    creating or updating CharacterRel objects to link characters with relationship
    descriptions.

    Args:
        context: View context dictionary containing event and other request data
        form: Form object with cleaned_data containing the uploaded file
        logs: List to append processing status messages to

    Side Effects:
        - Creates or updates CharacterRel objects in the database
        - Appends status messages to the logs list

    """
    uploaded_file = form.cleaned_data.get("second", None)
    if uploaded_file:
        # Load relationships file and get character mapping
        (input_dataframe, new_logs) = _get_file(context, uploaded_file, 1)
        character_name_to_id = {
            element["name"].lower(): element["id"]
            for element in get_event_elements(context["event"].id, Character, context=context).values("id", "name")
        }

        # Process each relationship row
        if input_dataframe is not None:
            for row in input_dataframe.to_dict(orient="records"):
                new_logs.append(_relationships_load(row, character_name_to_id))
        logs.extend(new_logs)


def _writing_load_plot_rels(context: dict, form: Form, logs: list[str]) -> None:
    """Load plot-character relationships from uploaded file.

    Processes an uploaded CSV/Excel file containing plot-character relationship data,
    creating or updating PlotCharacterRel objects to link characters to plots with
    optional descriptive text.

    Args:
        context: View context dictionary containing event and other request data
        form: Form object with cleaned_data containing the uploaded file
        logs: List to append processing status messages to

    Side Effects:
        - Creates or updates PlotCharacterRel objects in the database
        - Appends status messages to the logs list

    """
    uploaded_file = form.cleaned_data.get("second", None)
    if uploaded_file:
        # Load plot relationships file and get character/plot mappings
        (input_dataframe, new_logs) = _get_file(context, uploaded_file, 1)
        character_name_to_id = {
            element["name"].lower(): element["id"]
            for element in get_event_elements(context["event"].id, Character, context=context).values("id", "name")
        }
        plot_name_to_id = {
            element["name"].lower(): element["id"]
            for element in get_event_elements(context["event"].id, Plot, context=context).values("id", "name")
        }

        # Process each plot relationship row
        if input_dataframe is not None:
            for row in input_dataframe.to_dict(orient="records"):
                new_logs.append(_plot_rels_load(row, character_name_to_id, plot_name_to_id))
        logs.extend(new_logs)


def _plot_rels_load(row: dict, chars: dict[str, int], plots: dict[str, int]) -> str:
    """Load plot-character relationships from row data.

    Creates or updates PlotCharacterRel objects based on the provided row data,
    linking characters to plots with optional descriptive text.

    Args:
        row: Dictionary containing character, plot, and text data
        chars: Mapping of character names (lowercase) to character IDs
        plots: Mapping of plot names (lowercase) to plot IDs

    Returns:
        Status message indicating success or failure with details

    """
    # Extract and normalize character name from row data
    character_name = row.get("character", "").lower()
    if character_name not in chars:
        return f"ERR - source not found {character_name}"
    character_id = chars[character_name]

    # Extract and normalize plot name from row data
    plot_name = row.get("plot", "").lower()
    if plot_name not in plots:
        return f"ERR - target not found {plot_name}"
    plot_id = plots[plot_name]

    # Create or retrieve existing plot-character relationship
    plot_character_relationship, _created = PlotCharacterRel.objects.get_or_create(
        character_id=character_id, plot_id=plot_id
    )

    # Update relationship text and save to database
    plot_character_relationship.text = _text_to_html_paragraphs(row.get("text") or "")
    plot_character_relationship.save()
    return f"OK - Plot role {character_name} {plot_name}"


def _relationships_load(row: dict, chars: dict) -> str:
    """Load relationships from CSV row data.

    Creates or updates a Relationship object based on source and target character
    names provided in the row data. Characters are looked up in the chars dictionary
    using lowercase names as keys.

    Args:
        row: Dictionary containing relationship data with 'source', 'target', and 'text' keys
        chars: Dictionary mapping lowercase character names to character IDs

    Returns:
        Status message indicating success or error with details

    """
    # Get source character name and validate it exists
    source_character_name = row.get("source", "").lower()
    if source_character_name not in chars:
        return f"ERR - source not found {source_character_name}"
    source_character_id = chars[source_character_name]

    # Get target character name and validate it exists
    target_character_name = row.get("target", "").lower()
    if target_character_name not in chars:
        return f"ERR - target not found {target_character_name}"
    target_character_id = chars[target_character_name]

    # Create or retrieve relationship and update text
    relationship, _created = Relationship.objects.get_or_create(
        source_id=source_character_id, target_id=target_character_id
    )
    relationship.text = _text_to_html_paragraphs(row.get("text") or "")
    relationship.save()
    return f"OK - Relationship {source_character_name} {target_character_name}"


def _get_questions(questions_queryset: QuerySet) -> dict:
    """Build a dictionary mapping question names to their metadata."""
    questions_by_name = {}
    for question in questions_queryset:
        # Extract options as name->id mapping
        options_by_name = {option["name"].lower(): option["id"] for option in question["options"]}

        # Store question metadata with lowercase name as key
        questions_by_name[question["name"].lower()] = {
            "id": question["id"],
            "typ": question["typ"],
            "options": options_by_name,
        }
    return questions_by_name


def _assign_text_answer(
    target_element: Registration | Character,
    question: dict[str, Any],
    field_value: str,
    *,
    is_registration: bool,
) -> None:
    """Create or update a text/paragraph/editor answer, converting plain text to HTML paragraphs."""
    if is_registration:
        answer, _created = RegistrationAnswer.objects.get_or_create(
            registration_id=target_element.id, question_id=question["id"]
        )
    else:
        answer, _created = WritingAnswer.objects.get_or_create(element_id=target_element.id, question_id=question["id"])

    if question["typ"] in [BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR]:
        answer.text = _text_to_html_paragraphs(field_value)
    else:
        answer.text = field_value
    answer.save()


def _assign_choice_answer(
    target_element: Registration | Character,
    field_name: str,
    field_value: str,
    available_questions: dict[str, Any],
    error_logs: list[str],
    *,
    is_registration: bool = False,
) -> None:
    """Assign choice answers to form elements during bulk import.

    Processes choice field assignments with validation, option matching,
    and proper relationship creation for registration or character forms.
    """
    field_name = field_name.lower()
    if field_name not in available_questions:
        return

    question = available_questions[field_name]

    # check if answer
    if question["typ"] in [BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR]:
        _assign_text_answer(target_element, question, field_value, is_registration=is_registration)

    # check if choice
    else:
        option_values = field_value.split(",")
        if len(option_values) > MAX_COMMA_VALUES:
            error_logs.append(
                f"Problem with question {field_name}: too many options ({len(option_values)}, max {MAX_COMMA_VALUES})"
            )
            return

        if is_registration:
            RegistrationChoice.objects.filter(registration_id=target_element.id, question_id=question["id"]).delete()
        else:
            WritingChoice.objects.filter(element_id=target_element.id, question_id=question["id"]).delete()

        for original_input_option in option_values:
            normalized_input_option = original_input_option.lower().strip()
            option_id = question["options"].get(normalized_input_option)
            if not option_id:
                error_logs.append(f"Problem with question {field_name}: couldn't find option {normalized_input_option}")
                continue

            if is_registration:
                RegistrationChoice.objects.create(
                    registration_id=target_element.id,
                    question_id=question["id"],
                    option_id=option_id,
                )
            else:
                WritingChoice.objects.create(
                    element_id=target_element.id,
                    question_id=question["id"],
                    option_id=option_id,
                )


def element_load(context: dict, csv_row: dict, element_questions: dict) -> str:
    """Load generic element data from CSV row for bulk import.

    Processes element creation or updates with field validation,
    question processing, and proper logging for various element types.

    Args:
        context: Context dictionary with field_name, typ, event, and fields
        csv_row: CSV row data as dictionary with field names and values
        element_questions: List of questions for element processing

    Returns:
        Status message string indicating success/failure and operation details

    """
    # Validate that the required field name exists in the CSV row
    primary_field_name = context["field_name"].lower()
    if primary_field_name not in csv_row:
        return "ERR - There is no name in fields"

    # Extract element name and determine the appropriate model class
    element_name = csv_row[primary_field_name]

    # Handle NaN or empty element names (e.g. blank rows in CSV)
    if pd.isna(element_name) or not str(element_name).strip():
        return "ERR - empty name"

    # Remove initial "#number " pattern from name
    element_name = _strip_number_prefix(str(element_name))
    question_applicable_type = QuestionApplicable.get_applicable(context["typ"])
    writing_model_class = QuestionApplicable.get_applicable_inverse(question_applicable_type)

    # Get the target event - use parent if in campaign and element is inheritable
    target_event = get_event_class_parent(context["event"].id, writing_model_class, context=context)

    # Try to find existing element or create new one
    element = writing_model_class.objects.filter(event=target_event, name__iexact=element_name).first()
    if element:
        is_newly_created = False
    else:
        element = writing_model_class.objects.create(event_id=target_event, name=element_name)
        is_newly_created = True

    # Initialize logging for field processing errors
    error_logs = []

    # Normalize field names to lowercase for consistent processing
    context["fields"] = {key.lower(): content for key, content in context["fields"].items()}

    # Process each field in the CSV row and update element
    for field_name, field_value in csv_row.items():
        _writing_load_field(context, element, field_name, field_value, element_questions, error_logs)

    # Save the element and log the operation
    element.save()
    save_log(context, writing_model_class, element, operation_type=LogOperationType.UPLOAD)

    # Return appropriate status message based on processing results
    if error_logs:
        return "KO - " + ",".join(error_logs)

    if is_newly_created:
        return f"OK - Created {element_name}"
    return f"OK - Updated {element_name}"


def _writing_load_field(
    context: dict, element: BaseModel, field: str, value: str, questions: dict, logs: list[str]
) -> None:
    """Load writing field data during upload processing.

    Processes individual field values from upload data and updates the writing element
    accordingly. Handles special fields like 'typ' and 'quest' with object lookups,
    and delegates other field types to question loading.

    Args:
        context: Context dictionary containing event and field information
        element: Writing element instance to update with field data
        field: Name of the field being processed
        value: Value from upload data for this field
        questions: Dictionary mapping field names to question instances
        logs: List to append error messages to during processing

    """
    # Skip processing if value is NaN/null
    if pd.isna(value):
        return

    # Handle quest type field with case-insensitive lookup
    if field == "typ":
        quest_type = (
            get_event_elements(context["event"].id, QuestType, context=context).filter(name__iexact=value).first()
        )
        if quest_type:
            element.typ = quest_type
        else:
            logs.append(f"ERR - quest type not found: {value}")
        return

    # Handle quest field with case-insensitive lookup
    if field == "quest":
        quest = get_event_elements(context["event"].id, Quest, context=context).filter(name__iexact=value).first()
        if quest:
            element.quest = quest
        else:
            logs.append(f"ERR - quest not found: {value}")
        return

    # Get field type from context configuration; skip unknown fields
    if field not in context["fields"]:
        logs.append(f"ERR - field not found: {field}")
        return
    field_type = context["fields"][field]

    # Skip processing for name fields and explicitly skipped fields
    if field_type in [WritingQuestionType.NAME, "skip"]:
        return

    # Wrap plain multiline text in HTML paragraphs so line breaks render correctly.
    # Only free-text fields need this; factions, choices, and other lookup-based
    # fields must keep their raw value so name matching against the DB still works.
    if field_type in [WritingQuestionType.SHEET, *BaseQuestionType.get_answer_types()]:
        html_formatted_value = _text_to_html_paragraphs(value)
    else:
        html_formatted_value = str(value).strip()
    if not html_formatted_value:
        return

    # Delegate to question loading for all other field types
    _writing_question_load(context, element, field, field_type, logs, questions, html_formatted_value)


def _set_character_status(element: Character, value: str, logs: list[str]) -> None:
    """Set character status from key value (c, s, r, a)."""
    value_lower = str(value).strip().lower()
    for key, _display in CharacterStatus.choices:
        if value_lower == key.lower():
            element.status = key
            return
    logs.append(f"ERR - status not found: {value}")


def _set_assigned_member(element: Character, email: str, logs: list[str]) -> None:
    """Set assigned staff member from email address."""
    try:
        member = Member.objects.get(user__email__iexact=email.strip())
        element.assigned = member
    except Member.DoesNotExist:
        logs.append(f"ERR - assigned member not found: {email}")


def _writing_question_load(
    context: dict,
    writing_element: Character | Plot | Faction,
    question_field: str,
    question_type: WritingQuestionType,
    processing_logs: list[str],
    questions_dict: dict[str, Any],
    field_value: str,
) -> None:
    """Process and load writing question values into element fields.

    Args:
        context: Context dictionary
        writing_element: Target writing element to update
        question_field: Field identifier
        question_type: WritingQuestionType enum value
        processing_logs: List to collect processing logs
        questions_dict: Dictionary of questions
        field_value: Value to assign to the field

    """
    if question_type == WritingQuestionType.MIRROR:
        _get_mirror_instance(context, writing_element, field_value, processing_logs)
    elif question_type == WritingQuestionType.HIDE:
        writing_element.hide = field_value.lower() == "true"
    elif question_type == WritingQuestionType.LOCKED:
        writing_element.locked = field_value.lower() == "true"
    elif question_type == WritingQuestionType.FACTIONS:
        _assign_faction(context, writing_element, field_value, processing_logs)
    elif question_type == WritingQuestionType.TEASER:
        writing_element.teaser = field_value
    elif question_type == WritingQuestionType.SHEET:
        writing_element.text = field_value
    elif question_type == WritingQuestionType.TITLE:
        writing_element.title = field_value
    elif question_type == "character_status":
        _set_character_status(writing_element, field_value, processing_logs)
    elif question_type == "character_assigned":
        _set_assigned_member(writing_element, field_value, processing_logs)
    # TODO: implement
    else:
        _assign_choice_answer(writing_element, question_field, field_value, questions_dict, processing_logs)


def _get_mirror_instance(
    context: dict,
    character_element: Character,
    mirror_character_name: str,
    error_logs: list[str],
) -> None:
    """Fetch and assign mirror character instance from event."""
    mirror_character = (
        get_event_elements(context["event"].id, Character, context=context)
        .filter(name__iexact=mirror_character_name)
        .first()
    )
    if mirror_character:
        character_element.mirror = mirror_character
    else:
        error_logs.append(f"ERR - mirror not found: {mirror_character_name}")


def _assign_faction(context: dict, element: Character, value: str, logs: list[str]) -> None:
    """Assign character to factions by comma-separated faction names.

    Args:
        context: Dictionary containing event and other context data
        element: Character instance to assign to factions
        value: Comma-separated string of faction names
        logs: List to append error messages to

    """
    faction_names = value.split(",")
    if len(faction_names) > MAX_COMMA_VALUES:
        logs.append(f"ERR - Too many factions: {len(faction_names)} exceeds limit of {MAX_COMMA_VALUES}")
        return

    element.save()
    # Process each faction name in the comma-separated list
    for faction_name in faction_names:
        # Find faction by case-insensitive name match for the event
        faction = Faction.objects.filter(name__iexact=faction_name.strip(), event=context["event"]).first()
        if faction:
            faction.characters.add(element)
        else:
            # Log faction not found errors
            logs.append(f"Faction not found: {faction_name}")
