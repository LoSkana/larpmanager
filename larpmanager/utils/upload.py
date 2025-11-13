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

import io
import logging
import os
import shutil
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.experience import AbilityPx, AbilityTypePx
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    QuestionVisibility,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.utils import UploadToPathAndRename
from larpmanager.models.writing import (
    Character,
    Faction,
    Plot,
    PlotCharacterRel,
    Relationship,
)
from larpmanager.utils.download import _get_column_names
from larpmanager.utils.edit import save_log
from typing import Any

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.forms import Form

    from larpmanager.models.base import BaseModel

logger = logging.getLogger(__name__)


def go_upload(context: dict, upload_form_data: Any) -> Any:
    """Route uploaded files to appropriate processing functions.

    Args:
        context: Context dictionary with upload type and settings
        upload_form_data: Uploaded file form data

    Returns:
        list: Result messages from processing function

    """
    # FIX
    # if request.POST.get("upload") == "cover":
    #     # check extension
    #     if zipfile.is_zipfile(upload_form_data[0]):
    #         with zipfile.ZipFile(upload_form_data[0]) as z_obj:
    #             cover_load(context, z_obj)
    #         z_obj.close()
    #         return ""

    upload_type = context["typ"]

    if upload_type == "registration_form":
        return form_load(context, upload_form_data, is_registration=True)
    if upload_type == "character_form":
        return form_load(context, upload_form_data, is_registration=False)
    if upload_type == "registration":
        return registrations_load(context, upload_form_data)
    if upload_type == "px_abilitie":
        return abilities_load(context, upload_form_data)
    if upload_type == "registration_ticket":
        return tickets_load(context, upload_form_data)
    return writing_load(context, upload_form_data)


def _read_uploaded_csv(uploaded_file: Any) -> pd.DataFrame | None:
    """Read CSV file with multiple encoding fallbacks.

    Attempts to read a CSV file using various character encodings to handle
    files from different sources and systems. Falls back through common
    encodings until successful parsing or all options are exhausted.

    Args:
        uploaded_file: Django uploaded file object containing CSV data.

    Returns:
        pandas.DataFrame or None: Parsed CSV data with all columns as strings,
            or None if parsing failed with all attempted encodings.

    Raises:
        None: All exceptions are caught and handled internally.

    """
    # Early return if no file provided
    if not uploaded_file:
        return None

    # Define encoding priority list - most common first
    encodings = [
        "utf-8",
        "utf-8-sig",
        "latin1",
        "windows-1252",
        "utf-16",
        "utf-32",
        "ascii",
        "mac-roman",
        "cp437",
        "cp850",
    ]

    # Try each encoding until one succeeds
    for encoding in encodings:
        try:
            # Reset file pointer to beginning
            uploaded_file.seek(0)

            # Decode file content with current encoding
            decoded_content = uploaded_file.read().decode(encoding)
            string_buffer = io.StringIO(decoded_content)

            # Parse CSV with automatic delimiter detection
            return pd.read_csv(string_buffer, encoding=encoding, sep=None, engine="python", dtype=str)
        except Exception as parsing_error:
            # Log error and continue to next encoding
            logger.debug("Failed to parse CSV with encoding %s: %s", encoding, parsing_error)
            continue

    # Return None if all encodings failed
    return None


def _get_file(context: dict, file: Any, column_id: str | None = None) -> tuple[any, list[str]]:
    """Get file path and save uploaded file to media directory.

    Args:
        context: Context dictionary containing event information and column definitions.
        file: Uploaded file object to be processed.
        column_id: Optional column identifier for file naming. Defaults to None.

    Returns:
        A tuple containing:
            - DataFrame: Processed pandas DataFrame if successful, None if failed.
            - list[str]: List of error messages, empty if no errors occurred.

    Note:
        Function validates that all columns in the uploaded CSV are recognized
        based on the context configuration.

    """
    # Get available column names from context
    _get_column_names(context)
    allowed_column_names = []

    # Add columns from specific column_id if provided
    if column_id is not None:
        allowed_column_names.extend(list(context["columns"][column_id].keys()))

    # Add fields from context if available
    if "fields" in context:
        allowed_column_names.extend(context["fields"].keys())

    # Convert all allowed column names to lowercase for comparison
    allowed_column_names = [column_name.lower() for column_name in allowed_column_names]

    # Read and parse the uploaded CSV file
    input_dataframe = _read_uploaded_csv(file)
    if input_dataframe is None:
        return None, ["ERR - Could not read input csv"]

    # Normalize column names to lowercase for validation
    input_dataframe.columns = [column.lower() for column in input_dataframe.columns]

    # Validate that all columns are recognized
    for column in input_dataframe.columns:
        if column.lower() not in allowed_column_names:
            return None, [f"ERR - column not recognized: {column}"]

    return input_dataframe, []


def registrations_load(context: dict, uploaded_file_form: Any) -> Any:
    """Load registration data from uploaded CSV file.

    Args:
        context: Context dictionary with event and form settings
        uploaded_file_form: Form data containing uploaded CSV file

    Returns:
        str: HTML formatted result message with processing statistics

    """
    (input_dataframe, processing_logs) = _get_file(context, uploaded_file_form.cleaned_data["first"], 0)

    registration_questions = context["event"].get_elements(RegistrationQuestion).prefetch_related("options")
    questions_mapping = _get_questions(registration_questions)

    if input_dataframe is not None:
        for registration_row in input_dataframe.to_dict(orient="records"):
            processing_logs.append(_reg_load(context, registration_row, questions_mapping))
    return processing_logs


def _reg_load(context: dict, csv_row: dict, registration_questions: dict) -> str:
    """Load registration data from CSV row for bulk import.

    Creates or updates registrations with field validation, membership checks,
    and question processing for event registration imports.

    Args:
        context: Context dictionary containing event and run information
        csv_row: Dictionary representing a CSV row with registration data
        registration_questions: List of registration questions for the event

    Returns:
        str: Status message indicating success/failure and details

    Raises:
        ObjectDoesNotExist: When user email or membership is not found

    """
    # Validate required email column exists
    if "email" not in csv_row:
        return "ERR - There is no email column"

    # Find user by email (case-insensitive)
    try:
        user = User.objects.get(email__iexact=csv_row["email"].strip())
    except ObjectDoesNotExist:
        return "ERR - Email not found"

    member = user.member

    # Check if user has valid membership for this association
    try:
        membership = Membership.objects.get(member=member, association_id=context["event"].association_id)
    except ObjectDoesNotExist:
        return "ERR - Sharing data not found"

    # Verify user has approved data sharing
    if membership.status == MembershipStatus.EMPTY:
        return "ERR - User has not approved sharing of data"

    # Get or create registration for this run and member
    (registration, was_created) = Registration.objects.get_or_create(
        run=context["run"],
        member=member,
        cancellation_date__isnull=True,
    )

    error_logs = []

    # Process each field in the CSV row
    for field_name, field_value in csv_row.items():
        _reg_field_load(context, registration, field_name, field_value, registration_questions, error_logs)

    # Save registration and log the action
    registration.save()
    save_log(context["member"], Registration, registration)

    # Generate appropriate status message
    if error_logs:
        status_message = "KO - " + ",".join(error_logs)
    elif was_created:
        status_message = f"OK - Created {member}"
    else:
        status_message = f"OK - Updated {member}"

    return status_message


def _reg_field_load(
    context: Any, registration: Any, field_name: Any, field_value: Any, registration_questions: Any, error_logs: Any
) -> None:
    """Load individual registration field from CSV data.

    Args:
        context: Context dictionary with event data
        registration: Registration instance to update
        field_name: Field name from CSV
        field_value: Field value from CSV
        registration_questions: Dictionary of registration questions
        error_logs: List to append error messages to

    """
    if field_name == "email":
        return

    if not field_value or pd.isna(field_value):
        return

    if field_name == "ticket":
        _assign_elem(context, registration, field_name, field_value, RegistrationTicket, error_logs)
    elif field_name == "characters":
        _reg_assign_characters(context, registration, field_value, error_logs)
    elif field_name == "pwyw":
        registration.pay_what = Decimal(field_value)
    else:
        _assign_choice_answer(
            registration,
            field_name,
            field_value,
            registration_questions,
            error_logs,
            is_registration=True,
        )


def _assign_elem(
    context: dict,
    target_object: object,
    field_name: str,
    lookup_value: str,
    model_type: type,
    error_logs: list,
) -> None:
    """Assign an element to an object field based on value lookup.

    Attempts to find an element by number (if value is digit) or by name (case-insensitive).
    If the element is not found, logs an error and returns without assignment.

    Args:
        context: Context dictionary containing event information
        target_object: Target object to assign the element to
        field_name: Field name on the target object
        lookup_value: Value to search for (number or name)
        model_type: Model type to query for the element
        error_logs: List to append error messages to

    """
    try:
        # Check if value is a digit to determine lookup method
        if lookup_value.isdigit():
            # Look up element by number for the given event
            element = model_type.objects.get(event=context["event"], number=int(lookup_value))
        else:
            # Look up element by name (case-insensitive) for the given event
            element = model_type.objects.get(event=context["event"], name__iexact=lookup_value)
    except ObjectDoesNotExist:
        # Log error if element not found and return without assignment
        error_logs.append(f"ERR - element {field_name} not found")
        return

    # Assign the found element to the object field
    target_object.__setattr__(field_name, element)


def _reg_assign_characters(
    context: dict,
    registration: Registration,
    character_names_string: str,
    error_logs: list[str],
) -> None:
    """Assign characters to a registration based on comma-separated character names.

    Args:
        context: Context dictionary containing event and run information
        registration: Registration object to assign characters to
        character_names_string: Comma-separated string of character names
        error_logs: List to append error messages to

    """
    # Clear existing character assignments for this registration
    RegistrationCharacterRel.objects.filter(reg=registration).delete()

    # Handle multiple characters separated by commas
    character_names = [name.strip() for name in character_names_string.split(",")]

    for character_name in character_names:
        if not character_name:
            continue

        # Find character by name in the current event
        try:
            character = Character.objects.get(event=context["event"], name__iexact=character_name)
        except ObjectDoesNotExist:
            error_logs.append(f"ERR - Character not found: {character_name}")
            continue

        # Check if character is already assigned to another active registration
        existing_assignments = RegistrationCharacterRel.objects.filter(
            reg__run=context["run"],
            reg__cancellation_date__isnull=True,
            character=character,
        )
        if existing_assignments.exclude(reg_id=registration.id).exists():
            error_logs.append(f"ERR - character already assigned: {character_name}")
            continue

        # Create the character assignment relationship
        RegistrationCharacterRel.objects.get_or_create(reg=registration, character=character)


def writing_load(context: dict, form: Any) -> list[str]:
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
        writing_questions = (
            context["event"]
            .get_elements(WritingQuestion)
            .filter(applicable=context["writing_typ"])
            .prefetch_related("options")
        )
        questions_dict = _get_questions(writing_questions)

        # Process each row of writing data
        if input_dataframe is not None:
            for row in input_dataframe.to_dict(orient="records"):
                logs.append(element_load(context, row, questions_dict))

    # Process character relationships if type is character
    if context["typ"] == "character":
        uploaded_file = form.cleaned_data.get("second", None)
        if uploaded_file:
            # Load relationships file and get character mapping
            (input_dataframe, new_logs) = _get_file(context, uploaded_file, 1)
            character_name_to_id = {
                element["name"].lower(): element["id"]
                for element in context["event"].get_elements(Character).values("id", "name")
            }

            # Process each relationship row
            if input_dataframe is not None:
                for row in input_dataframe.to_dict(orient="records"):
                    new_logs.append(_relationships_load(row, character_name_to_id))
            logs.extend(new_logs)

    # Process plot relationships if type is plot
    if context["typ"] == "plot":
        uploaded_file = form.cleaned_data.get("second", None)
        if uploaded_file:
            # Load plot relationships file and get character/plot mappings
            (input_dataframe, new_logs) = _get_file(context, uploaded_file, 1)
            character_name_to_id = {
                element["name"].lower(): element["id"]
                for element in context["event"].get_elements(Character).values("id", "name")
            }
            plot_name_to_id = {
                element["name"].lower(): element["id"]
                for element in context["event"].get_elements(Plot).values("id", "name")
            }

            # Process each plot relationship row
            if input_dataframe is not None:
                for row in input_dataframe.to_dict(orient="records"):
                    new_logs.append(_plot_rels_load(row, character_name_to_id, plot_name_to_id))
            logs.extend(new_logs)

    return logs


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
    plot_character_relationship, _ = PlotCharacterRel.objects.get_or_create(character_id=character_id, plot_id=plot_id)

    # Update relationship text and save to database
    plot_character_relationship.text = row.get("text")
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
    relationship, _ = Relationship.objects.get_or_create(source_id=source_character_id, target_id=target_character_id)
    relationship.text = row.get("text")
    relationship.save()
    return f"OK - Relationship {source_character_name} {target_character_name}"


def _get_questions(questions_queryset: QuerySet) -> dict:
    """Build a dictionary mapping question names to their metadata.

    Args:
        questions_queryset: QuerySet of question objects with name, id, typ, and options attributes.

    Returns:
        Dictionary with lowercase question names as keys and question metadata as values.

    """
    questions_by_name = {}
    for question in questions_queryset:
        # Extract options as name->id mapping
        options_by_name = {option.name.lower(): option.id for option in question.options.all()}

        # Store question metadata with lowercase name as key
        questions_by_name[question.name.lower()] = {"id": question.id, "typ": question.typ, "options": options_by_name}
    return questions_by_name


def _assign_choice_answer(
    target_element: Any,
    field_name: Any,
    field_value: Any,
    available_questions: Any,
    error_logs: Any,
    *,
    is_registration: Any = False,
) -> None:
    """Assign choice answers to form elements during bulk import.

    Processes choice field assignments with validation, option matching,
    and proper relationship creation for registration or character forms.
    """
    field_name = field_name.lower()
    if field_name not in available_questions:
        error_logs.append(f"ERR - question not found {field_name}")
        return

    question = available_questions[field_name]

    # check if answer
    if question["typ"] in [BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR]:
        if is_registration:
            answer, _ = RegistrationAnswer.objects.get_or_create(reg_id=target_element.id, question_id=question["id"])
        else:
            answer, _ = WritingAnswer.objects.get_or_create(element_id=target_element.id, question_id=question["id"])
        answer.text = field_value
        answer.save()

    # check if choice
    else:
        if is_registration:
            RegistrationChoice.objects.filter(reg_id=target_element.id, question_id=question["id"]).delete()
        else:
            WritingChoice.objects.filter(element_id=target_element.id, question_id=question["id"]).delete()

        for original_input_option in field_value.split(","):
            normalized_input_option = original_input_option.lower().strip()
            option_id = question["options"].get(normalized_input_option)
            if not option_id:
                error_logs.append(f"Problem with question {field_name}: couldn't find option {normalized_input_option}")
                continue

            if is_registration:
                RegistrationChoice.objects.create(
                    reg_id=target_element.id,
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
    question_applicable_type = QuestionApplicable.get_applicable(context["typ"])
    writing_model_class = QuestionApplicable.get_applicable_inverse(question_applicable_type)

    # Try to find existing element or create new one
    is_newly_created = False
    try:
        element = writing_model_class.objects.get(event=context["event"], name__iexact=element_name)
    except ObjectDoesNotExist:
        element = writing_model_class.objects.create(event=context["event"], name=element_name)
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
    save_log(context["member"], writing_model_class, element)

    # Return appropriate status message based on processing results
    if error_logs:
        return "KO - " + ",".join(error_logs)

    if is_newly_created:
        return f"OK - Created {element_name}"
    return f"OK - Updated {element_name}"


def _writing_load_field(context: dict, element: BaseModel, field: str, value: any, questions: dict, logs: list) -> None:
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
        try:
            element.typ = context["event"].get_elements(QuestType).get(name__iexact=value)
        except ObjectDoesNotExist:
            logs.append(f"ERR - quest type not found: {value}")
        return

    # Handle quest field with case-insensitive lookup
    if field == "quest":
        try:
            element.quest = context["event"].get_elements(Quest).get(name__iexact=value)
        except ObjectDoesNotExist:
            logs.append(f"ERR - quest not found: {value}")
        return

    # Get field type from context configuration
    field_type = context["fields"][field]

    # Skip processing for name fields and explicitly skipped fields
    if field_type in [WritingQuestionType.NAME, "skip"]:
        return

    # Convert multiline text to HTML break tags and strip whitespace
    html_formatted_value = "<br />".join(str(value).strip().split("\n"))
    if not html_formatted_value:
        return

    # Delegate to question loading for all other field types
    _writing_question_load(context, element, field, field_type, logs, questions, html_formatted_value)


def _writing_question_load(
    context: Any,
    writing_element: Any,
    question_field: Any,
    question_type: Any,
    processing_logs: Any,
    questions_dict: Any,
    field_value: Any,
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
    elif question_type == WritingQuestionType.FACTIONS:
        _assign_faction(context, writing_element, field_value, processing_logs)
    elif question_type == WritingQuestionType.TEASER:
        writing_element.teaser = field_value
    elif question_type == WritingQuestionType.SHEET:
        writing_element.text = field_value
    elif question_type == WritingQuestionType.TITLE:
        writing_element.title = field_value
    # TODO: implement
    # elif question_type == QuestionType.COVER:
    #     writing_element.cover = field_value
    # elif question_type == QuestionType.PROGRESS:
    #     writing_element.cover = field_value
    # elif question_type == QuestionType.ASSIGNED:
    #     writing_element.cover = field_value
    else:
        _assign_choice_answer(writing_element, question_field, field_value, questions_dict, processing_logs)


def _get_mirror_instance(
    context: dict,
    character_element: Character,
    mirror_character_name: str,
    error_logs: list[str],
) -> None:
    """Fetch and assign mirror character instance from event."""
    try:
        character_element.mirror = context["event"].get_elements(Character).get(name__iexact=mirror_character_name)
    except ObjectDoesNotExist:
        error_logs.append(f"ERR - mirror not found: {mirror_character_name}")


def _assign_faction(context: dict, element: Character, value: str, logs: list[str]) -> None:
    """Assign character to factions by comma-separated faction names.

    Args:
        context: Dictionary containing event and other context data
        element: Character instance to assign to factions
        value: Comma-separated string of faction names
        logs: List to append error messages to

    """
    # Process each faction name in the comma-separated list
    for faction_name in value.split(","):
        try:
            # Find faction by case-insensitive name match for the event
            faction = Faction.objects.get(name__iexact=faction_name.strip(), event=context["event"])

            # Save element and add to faction's characters
            element.save()  # to be sure
            faction.characters.add(element)
            faction.save()
        except ObjectDoesNotExist:
            # Log faction not found errors
            logs.append(f"Faction not found: {faction_name}")


def form_load(context: dict, form: Any, *, is_registration: bool = True) -> list[str]:
    """Load form questions and options from uploaded files.

    Processes uploaded CSV/Excel files to create form questions and their
    associated options. Handles both registration and writing question types.

    Args:
        context: Context dictionary containing event data and configuration
        form: Upload form instance with cleaned file data
        is_registration: Flag indicating whether to load registration questions
            (True) or writing questions (False). Defaults to True.

    Returns:
        List of log messages generated during the upload processing operations.
        Each message describes the success or failure of individual operations.

    Note:
        Expects 'first' field to contain questions file and 'second' field
        to contain options file. Files are processed sequentially.

    """
    log_messages = []

    # Process questions file upload
    questions_file = form.cleaned_data.get("first", None)
    if questions_file:
        # Parse uploaded questions file into DataFrame
        (questions_dataframe, log_messages) = _get_file(context, questions_file, 0)
        if questions_dataframe is not None:
            # Create question objects from each row in the DataFrame
            for question_row in questions_dataframe.to_dict(orient="records"):
                log_messages.append(_questions_load(context, question_row, is_registration=is_registration))

    # Process options file upload
    options_file = form.cleaned_data.get("second", None)
    if options_file:
        # Parse uploaded options file into DataFrame
        (options_dataframe, options_log_messages) = _get_file(context, options_file, 1)
        if options_dataframe is not None:
            # Determine question model class based on registration type
            question_model_class = WritingQuestion
            if is_registration:
                question_model_class = RegistrationQuestion

            # Build lookup dictionary mapping question names to IDs
            questions_by_name = {
                question["name"].lower(): question["id"]
                for question in context["event"].get_elements(question_model_class).values("id", "name")
            }

            # Create option objects for each row, linking to existing questions
            for option_row in options_dataframe.to_dict(orient="records"):
                options_log_messages.append(
                    _options_load(context, option_row, questions_by_name, is_registration=is_registration)
                )

        # Combine logs from options processing with existing logs
        log_messages.extend(options_log_messages)

    return log_messages


def invert_dict(dictionary: dict[str, str]) -> dict[str, str]:
    """Invert dictionary keys and values, normalizing values to lowercase and stripping whitespace."""
    return {value.lower().strip(): key for key, value in dictionary.items()}


def _questions_load(context: dict, row_data: dict, *, is_registration: bool) -> str:
    """Load and validate question data from upload files.

    Processes question configurations for registration or character forms,
    creating or updating RegistrationQuestion or WritingQuestion instances
    based on the row data and validation mappings.

    Args:
        context: Context dictionary containing event and processing information
        row_data: Data row from upload file containing question configuration
        is_registration: True for registration questions, False for writing questions

    Returns:
        Status message indicating success or error details

    """
    # Extract and validate the required name field
    question_name = row_data.get("name")
    if not question_name:
        return "ERR - name not found"

    # Get field validation mappings for the question type
    field_mappings = _get_mappings(is_registration=is_registration)

    if is_registration:
        # Create or get registration question instance
        question_instance, was_created = RegistrationQuestion.objects.get_or_create(
            event=context["event"],
            name__iexact=question_name,
            defaults={"name": question_name},
        )
    else:
        # Writing questions require additional 'applicable' field validation
        if "applicable" not in row_data:
            return "ERR - missing applicable column"
        applicable_value = row_data["applicable"]
        if applicable_value not in field_mappings["applicable"]:
            return "ERR - unknown applicable"

        # Create or get writing question instance with applicable field
        question_instance, was_created = WritingQuestion.objects.get_or_create(
            event=context["event"],
            name__iexact=question_name,
            applicable=field_mappings["applicable"][applicable_value],
            defaults={"name": question_name},
        )

    # Process and validate each field in the row data
    for field_name, field_value in row_data.items():
        # Skip empty values and already processed fields
        if not field_value or pd.isna(field_value) or field_name in ["applicable", "name"]:
            continue

        validated_value = field_value
        # Apply mapping validation if field has defined mappings
        if field_name in field_mappings:
            validated_value = validated_value.lower().strip()
            if validated_value not in field_mappings[field_name]:
                return f"ERR - unknow value {field_value} for field {field_name}"
            validated_value = field_mappings[field_name][validated_value]

        # Handle special case for max_length field conversion
        if field_name == "max_length":
            validated_value = int(field_value)

        # Set the validated value on the instance
        setattr(question_instance, field_name, validated_value)

    # Save the configured instance to database
    question_instance.save()

    # Return appropriate success message based on operation
    return f"OK - Created {question_name}" if was_created else f"OK - Updated {question_name}"


def _get_mappings(*, is_registration: bool) -> dict[str, dict[str, str]]:
    """Generate mappings for question field types and attributes.

    Args:
        is_registration: Whether to include additional registration-specific
                        question types in the type mapping.

    Returns:
        Dictionary containing inverted mappings for question types, status,
        applicable contexts, and visibility settings.

    """
    # Create base mappings by inverting enum dictionaries
    mappings = {
        "typ": invert_dict(BaseQuestionType.get_mapping()),
        "status": invert_dict(QuestionStatus.get_mapping()),
        "applicable": invert_dict(QuestionApplicable.get_mapping()),
        "visibility": invert_dict(QuestionVisibility.get_mapping()),
    }

    # Add registration-specific question types if needed
    if is_registration:
        # update typ with new types
        question_type_mapping = mappings["typ"]

        # Iterate through writing question type choices
        for question_type_key, _ in WritingQuestionType.choices:
            # Add missing keys to maintain consistency
            if question_type_key not in question_type_mapping:
                question_type_mapping[question_type_key] = question_type_key

    return mappings


def _options_load(import_context: dict, csv_row: dict, question_name_to_id_map: dict, *, is_registration: bool) -> str:
    """Load question options from CSV row for bulk import.

    Creates or updates question options with proper validation,
    ordering, and association with the correct question type.

    Args:
        import_context: Context dictionary containing import configuration
        csv_row: CSV row data as dictionary with column headers as keys
        question_name_to_id_map: Dictionary mapping question names to question IDs
        is_registration: Boolean flag indicating if this is for registration

    Returns:
        Status message string indicating success/failure of the operation
        Format: "OK - Created/Updated {name}" or "ERR - {error_description}"

    """
    # Validate required fields are present in the CSV row
    for field in ["name", "question"]:
        if field not in csv_row:
            return f"ERR - column {field} missing"

    # Extract and validate the option name
    option_name = csv_row["name"]
    if not option_name:
        return "ERR - empty name"

    # Find the associated question by name (case-insensitive)
    question_name_lower = csv_row["question"].lower()
    if question_name_lower not in question_name_to_id_map:
        return "ERR - question not found"
    question_id = question_name_to_id_map[question_name_lower]

    # Get or create the option instance
    was_created, option_instance = _get_option(import_context, is_registration, option_name, question_id)

    # Process each field in the CSV row
    for field_name, field_value in csv_row.items():
        # Skip empty or NaN values
        if not field_value or pd.isna(field_value):
            continue
        processed_value = field_value

        # Skip fields that are already processed
        if field_name in ["question", "name"]:
            continue

        # Convert numeric fields to appropriate types
        if field_name in ["max_available", "price"]:
            processed_value = int(processed_value)

        # Handle requirements field with special processing
        if field_name == "requirements":
            _assign_requirements(import_context, option_instance, [], field_value)
            continue

        # Set the field value on the instance
        setattr(option_instance, field_name, processed_value)

    # Save the instance to database
    option_instance.save()

    # Return appropriate success message
    if was_created:
        return f"OK - Created {option_name}"
    return f"OK - Updated {option_name}"


def _get_option(context: Any, is_registration: Any, option_name: Any, parent_question_id: Any) -> Any:
    """Get or create a question option for registration or writing forms.

    Args:
        context: Context dictionary containing event data
        is_registration: Boolean indicating if this is for registration (True) or writing (False)
        option_name: Name of the option
        parent_question_id: ID of the parent question

    Returns:
        tuple: (created, instance) where created is bool and instance is the option object

    """
    if is_registration:
        option_instance, was_created = RegistrationOption.objects.get_or_create(
            event=context["event"],
            question_id=parent_question_id,
            name__iexact=option_name,
            defaults={"name": option_name},
        )
    else:
        option_instance, was_created = WritingOption.objects.get_or_create(
            event=context["event"],
            name__iexact=option_name,
            question_id=parent_question_id,
            defaults={"name": option_name},
        )
    return was_created, option_instance


def get_csv_upload_tmp(csv_upload: Any, run: Any) -> str:
    """Create a temporary file for CSV upload processing.

    Creates a temporary directory structure under MEDIA_ROOT/tmp/event_slug/
    and saves the uploaded CSV file with a timestamp-based filename.

    Args:
        csv_upload: The uploaded CSV file object with chunks() method
        run: Run object containing event information with slug attribute

    Returns:
        str: Full path to the created temporary file

    """
    # Create base temporary directory path
    tmp_file = os.path.join(conf_settings.MEDIA_ROOT, "tmp")

    # Add event-specific subdirectory
    tmp_file = os.path.join(tmp_file, run.event.slug)

    # Ensure directory exists
    if not os.path.exists(tmp_file):
        Path(tmp_file).mkdir(parents=True, exist_ok=True)

    # Generate timestamped filename
    tmp_file = os.path.join(tmp_file, timezone.now().strftime("%Y-%m-%d-%H:%M:%S"))

    # Write uploaded file chunks to temporary file
    with open(tmp_file, "wb") as destination:
        destination.writelines(csv_upload.chunks())

    return tmp_file


def cover_load(context: Any, z_obj: Any) -> None:
    """Handle cover image upload and processing from ZIP archive.

    Args:
        context: Context dictionary containing run and event information
        z_obj: ZIP file object containing character cover images

    Side effects:
        Extracts ZIP contents, processes images, updates character cover fields,
        and moves files to proper media directory structure

    """
    # extract images
    fpath = os.path.join(conf_settings.MEDIA_ROOT, "cover_load")
    fpath = os.path.join(fpath, context["run"].event.slug)
    fpath = os.path.join(fpath, str(context["run"].number))
    if os.path.exists(fpath):
        shutil.rmtree(fpath)
    z_obj.extractall(path=fpath)
    covers = {}
    # get images
    for root, _dirnames, filenames in os.walk(fpath):
        for el in filenames:
            num = Path(el).stem
            covers[num] = os.path.join(root, el)
    logger.debug("Extracted covers: %s", covers)
    upload_to = UploadToPathAndRename("character/cover/")
    # cicle characters
    for c in context["run"].event.get_elements(Character):
        num = str(c.number)
        if num not in covers:
            continue
        fn = upload_to.__call__(c, covers[num])
        c.cover = fn
        c.save()
        Path(covers[num]).rename(Path(conf_settings.MEDIA_ROOT) / fn)


def tickets_load(context: dict, form: Form) -> list[str]:
    """Load tickets from uploaded file data.

    Args:
        context: Context dictionary containing processing state
        form: Form containing cleaned file data

    Returns:
        List of log messages from the loading process

    """
    # Extract and validate file data from form
    (uploaded_dataframe, log_messages) = _get_file(context, form.cleaned_data["first"], 0)

    # Process each row if data frame is valid
    if uploaded_dataframe is not None:
        # Convert dataframe to dictionary records and process each ticket
        for ticket_row in uploaded_dataframe.to_dict(orient="records"):
            log_messages.append(_ticket_load(context, ticket_row))
    return log_messages


def _ticket_load(context: dict, csv_row: dict) -> str:
    """Load ticket data from CSV row for bulk import.

    Creates or updates RegistrationTicket objects with proper validation,
    price handling, and relationship setup for event registration.

    Args:
        context: Context dictionary containing event and other bulk import data
        csv_row: Dictionary representing a single CSV row with ticket data

    Returns:
        str: Status message indicating success ("OK - Created/Updated") or error ("ERR - ...")

    Raises:
        ValueError: When numeric conversion fails for max_available or price fields

    """
    # Validate required name column exists
    if "name" not in csv_row:
        return "ERR - There is no name column"

    # Get or create ticket object for the event
    (ticket, was_created) = RegistrationTicket.objects.get_or_create(event=context["event"], name=csv_row["name"])

    # Define field mappings for enumeration values
    field_value_mappings = {
        "tier": invert_dict(TicketTier.get_mapping()),
    }

    # Process each field in the CSV row
    for field_name, field_value in csv_row.items():
        # Skip empty values, NaN values, and the name field (already processed)
        if not field_value or pd.isna(field_value) or field_name in ["name"]:
            continue

        processed_value = field_value

        # Handle mapped enumeration fields
        if field_name in field_value_mappings:
            processed_value = processed_value.lower().strip()
            if processed_value not in field_value_mappings[field_name]:
                return f"ERR - unknow value {field_value} for field {field_name}"
            processed_value = field_value_mappings[field_name][processed_value]

        # Convert numeric fields to appropriate types
        if field_name == "max_available":
            processed_value = int(field_value)
        if field_name == "price":
            processed_value = float(field_value)

        # Set the field value on the ticket object
        setattr(ticket, field_name, processed_value)

    # Save the ticket and log the operation
    ticket.save()
    save_log(context["member"], RegistrationTicket, ticket)

    # Return appropriate success message
    return f"OK - Created {ticket}" if was_created else f"OK - Updated {ticket}"


def abilities_load(context: dict, form: Any) -> list:
    """Load abilities from uploaded file and process each row.

    Args:
        context: Context dictionary containing processing state
        form: Form object with cleaned data containing file reference

    Returns:
        List of processing logs from ability loading operations

    """
    # Extract and validate input file data
    (input_dataframe, processing_logs) = _get_file(context, form.cleaned_data["first"], 0)

    # Process each row if valid dataframe exists
    if input_dataframe is not None:
        for ability_row in input_dataframe.to_dict(orient="records"):
            # Load individual ability and collect processing logs
            processing_logs.append(_ability_load(context, ability_row))
    return processing_logs


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
    # Validate required name column exists
    if "name" not in csv_row:
        return "ERR - There is no name column"

    # Get or create ability object using event's class parent
    (ability_element, was_created) = AbilityPx.objects.get_or_create(
        event=context["event"].get_class_parent(AbilityPx),
        name=csv_row["name"],
    )

    logs = []

    # Process each field in the CSV row
    for field_name, field_value in csv_row.items():
        # Skip empty, NaN values, or the name field (already processed)
        if not field_value or pd.isna(field_value) or field_name in ["name"]:
            continue
        processed_value = field_value

        # Handle type field assignment
        if field_name == "typ":
            _assign_type(context, ability_element, logs, field_value)
            continue

        # Convert cost field to integer
        if field_name == "cost":
            processed_value = int(field_value)

        # Handle prerequisites field parsing
        if field_name == "prerequisites":
            _assign_prereq(context, ability_element, logs, field_value)
            continue

        # Handle requirements field processing
        if field_name == "requirements":
            _assign_requirements(context, ability_element, logs, field_value)
            continue

        # Convert visible field to boolean
        if field_name == "visible":
            processed_value = field_value.lower().strip() == "true"

        # Set the attribute on the element
        setattr(ability_element, field_name, processed_value)

    # Save the element to database
    ability_element.save()

    # Log the operation for audit trail
    save_log(context["member"], AbilityPx, ability_element)

    # Return appropriate success message
    return f"OK - Created {ability_element}" if was_created else f"OK - Updated {ability_element}"


def _assign_type(
    context: dict,
    ability_element: AbilityPx,
    error_logs: list[str],
    ability_type_name: str,
) -> None:
    """Assign ability type to element from event context.

    Args:
        context: Dict containing event with ability types
        ability_element: Ability element to assign type to
        error_logs: List to append error messages to
        ability_type_name: Name of ability type to find

    """
    try:
        # Query ability type by name from event context
        ability_element.typ = context["event"].get_elements(AbilityTypePx).get(name__iexact=ability_type_name)
    except ObjectDoesNotExist:
        # Log error if ability type not found
        error_logs.append(f"ERR - quest type not found: {ability_type_name}")


def _assign_prereq(
    context: dict,
    element: AbilityPx,
    logs: list[str],
    value: str,
) -> None:
    """Assign prerequisites to an ability from comma-separated names.

    Args:
        context: Dictionary containing 'event' key with Event instance
        element: Target ability to add prerequisites to
        logs: List to append error messages
        value: Comma-separated prerequisite ability names

    """
    # Parse each prerequisite name from the comma-separated string
    for prerequisite_name in value.split(","):
        try:
            # Look up prerequisite ability by name (case-insensitive)
            prerequisite_element = context["event"].get_elements(AbilityPx).get(name__iexact=prerequisite_name.strip())

            # Ensure element is saved before adding M2M relationship
            element.save()
            element.prerequisites.add(prerequisite_element)
        except ObjectDoesNotExist:
            logs.append(f"Prerequisite not found: {prerequisite_name}")


def _assign_requirements(
    context: dict,
    writing_element: BaseModel,
    error_logs: list[str],
    requirement_names: str,
) -> None:
    """Assign writing option requirements to a writing element by parsing comma-separated names.

    Args:
        context: Context dict containing 'event' key with Event instance
        writing_element: WritingElement to add requirements to
        error_logs: List to append error messages to
        requirement_names: Comma-separated string of requirement names

    """
    # Process each requirement name from comma-separated string
    for requirement_name in requirement_names.split(","):
        try:
            # Look up writing option by case-insensitive name match
            writing_option = context["event"].get_elements(WritingOption).get(name__iexact=requirement_name.strip())
            writing_element.save()  # to be sure

            # Add the requirement to the writing element
            writing_element.requirements.add(writing_option)
        except ObjectDoesNotExist:
            error_logs.append(f"requirements not found: {requirement_name}")
