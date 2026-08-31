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

from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    QuestionVisibility,
    RegistrationOption,
    RegistrationQuestion,
    RegistrationQuestionApplicable,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.writing import get_event_class_parent, get_event_elements
from larpmanager.utils.io.upload.constants import MAX_CSV_ROWS
from larpmanager.utils.io.upload.csv_file import _get_file
from larpmanager.utils.io.upload.features import (
    _get_config_from_question_type,
    _get_feature_from_question_type,
    activate_configs,
    activate_features,
)
from larpmanager.utils.io.upload.parsing import (
    _get_row_name,
    _skip_row_field,
    _to_decimal,
    _to_int,
    invert_dict,
)
from larpmanager.utils.io.upload.relations import _assign_requirements

if TYPE_CHECKING:
    from django.forms import Form


def form_load(
    context: dict,
    form: Form,
    *,
    is_registration: bool = True,
    applicable: str = RegistrationQuestionApplicable.REGISTRATION,
) -> list[str]:
    """Load form questions and options from uploaded files.

    Processes uploaded CSV/Excel files to create form questions and their
    associated options. Handles both registration and writing question types.

    Args:
        context: Context dictionary containing event data and configuration
        form: Upload form instance with cleaned file data
        is_registration: Flag indicating whether to load registration questions
            (True) or writing questions (False). Defaults to True.
        applicable: For registration questions, which form they belong to
            (RegistrationQuestionApplicable). Ignored for writing questions.

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
            if len(questions_dataframe) > MAX_CSV_ROWS:
                return [f"ERR - File too large: {len(questions_dataframe)} rows exceeds limit of {MAX_CSV_ROWS}"]
            # Create question objects from each row in the DataFrame
            for question_row in questions_dataframe.to_dict(orient="records"):
                log_messages.append(
                    _questions_load(context, question_row, is_registration=is_registration, applicable=applicable)
                )

    # Process options file upload
    options_file = form.cleaned_data.get("second", None)
    if options_file:
        # Parse uploaded options file into DataFrame
        (options_dataframe, options_log_messages) = _get_file(context, options_file, 1)
        if options_dataframe is not None:
            # Determine question model class based on registration type
            question_model_class = WritingQuestion
            questions_lookup = get_event_elements(context["event"].id, question_model_class, context=context)
            if is_registration:
                question_model_class = RegistrationQuestion
                questions_lookup = get_event_elements(
                    context["event"].id, question_model_class, context=context
                ).filter(applicable=applicable)

            # Build lookup dictionary mapping question names to IDs
            questions_by_name = {
                question["name"].lower(): question["id"] for question in questions_lookup.values("id", "name")
            }

            # Create option objects for each row, linking to existing questions
            for option_row in options_dataframe.to_dict(orient="records"):
                options_log_messages.append(
                    _options_load(context, option_row, questions_by_name, is_registration=is_registration)
                )

        # Combine logs from options processing with existing logs
        log_messages.extend(options_log_messages)

    return log_messages


def _get_or_create_registration_question(
    context: dict, question_name: str, applicable: str = RegistrationQuestionApplicable.REGISTRATION
) -> tuple[RegistrationQuestion, bool]:
    """Get or create a registration question instance.

    Args:
        context: Context dictionary containing event information
        question_name: Name of the question to create or retrieve
        applicable: Which form the question belongs to (RegistrationQuestionApplicable);
            scopes both the lookup and the value set on creation, so uploading to one
            form never matches or edits a same-named question of the other form

    Returns:
        Tuple of (question_instance, was_created)

    """
    matching_questions = RegistrationQuestion.objects.filter(
        event=context["event"],
        name__iexact=question_name,
        applicable=applicable,
    )
    if matching_questions.exists():
        return matching_questions.first(), False

    return (
        RegistrationQuestion.objects.create(
            event=context["event"],
            name=question_name,
            applicable=applicable,
        ),
        True,
    )


def _get_or_create_writing_question(
    context: dict, question_name: str, row_data: dict, field_mappings: dict
) -> tuple[WritingQuestion | None, bool] | str:
    """Get or create a writing question instance.

    Args:
        context: Context dictionary containing event information
        question_name: Name of the question to create or retrieve
        row_data: Row data containing applicable field
        field_mappings: Field validation mappings

    Returns:
        Tuple of (question_instance, was_created) or error string

    """
    if "applicable" not in row_data:
        return "ERR - missing applicable column"

    applicable_value = row_data["applicable"]
    if applicable_value not in field_mappings["applicable"]:
        return "ERR - unknown applicable"

    applicable = field_mappings["applicable"][applicable_value]

    event = get_event_class_parent(context["event"].id, WritingQuestion, context=context)

    # For special (non-basic) WritingQuestionTypes, look up by type+applicable.
    # These questions are auto-created by configuration and are unique per type.
    raw_typ = str(row_data.get("typ", "")).lower().strip()
    typ_value = field_mappings.get("typ", {}).get(raw_typ, "")
    if typ_value and typ_value not in BaseQuestionType.get_basic_types():
        matching_by_type = WritingQuestion.objects.filter(
            event=event,
            typ=typ_value,
            applicable=applicable,
        )
        if matching_by_type.exists():
            return matching_by_type.first(), False

    matching_questions = WritingQuestion.objects.filter(
        event=event,
        name__iexact=question_name,
        applicable=applicable,
    )
    if matching_questions.exists():
        return matching_questions.first(), False

    return (
        WritingQuestion.objects.create(
            event_id=event,
            name=question_name,
            applicable=applicable,
        ),
        True,
    )


def _process_question_field(
    field_name: str,
    field_value: str,
    field_mappings: dict,
    question_instance: RegistrationQuestion | WritingQuestion,
) -> str | None:
    """Process and validate a single question field.

    Args:
        field_name: Name of the field to process
        field_value: Value of the field
        field_mappings: Field validation mappings
        question_instance: Question instance to update

    Returns:
        Error message string if validation fails, None otherwise

    """
    # Skip empty/NaN values and already processed fields
    if _skip_row_field(field_name, field_value, ("applicable", "name")):
        return None

    validated_value = field_value

    # Apply mapping validation if field has defined mappings
    if field_name in field_mappings:
        validated_value = validated_value.lower().strip()
        if validated_value not in field_mappings[field_name]:
            return f"ERR - unknow value {field_value} for field {field_name}"
        validated_value = field_mappings[field_name][validated_value]

    # Handle special case for max_length field conversion
    if field_name == "max_length":
        validated_value = _to_int(field_value)

    # Set the validated value on the instance
    setattr(question_instance, field_name, validated_value)
    return None


def _questions_load(
    context: dict,
    row_data: dict,
    *,
    is_registration: bool,
    applicable: str = RegistrationQuestionApplicable.REGISTRATION,
) -> str:
    """Load and validate question data from upload files.

    Processes question configurations for registration or character forms,
    creating or updating RegistrationQuestion or WritingQuestion instances
    based on the row data and validation mappings.

    Args:
        context: Context dictionary containing event and processing information
        row_data: Data row from upload file containing question configuration
        is_registration: True for registration questions, False for writing questions
        applicable: For registration questions, which form they belong to
            (RegistrationQuestionApplicable). Ignored for writing questions.

    Returns:
        Status message indicating success or error details

    """
    # Extract and validate the required name field
    question_name = row_data.get("name")
    if not question_name:
        return "ERR - name not found"

    # Get field validation mappings for the question type
    field_mappings = _get_mappings(is_registration=is_registration)

    # Get or create the question instance
    if is_registration:
        question_instance, was_created = _get_or_create_registration_question(context, question_name, applicable)
    else:
        result = _get_or_create_writing_question(context, question_name, row_data, field_mappings)
        if isinstance(result, str):
            return result
        question_instance, was_created = result

    # Process and validate each field in the row data
    for field_name, field_value in row_data.items():
        error = _process_question_field(field_name, field_value, field_mappings, question_instance)
        if error:
            return error

    # Save the configured instance to database
    question_instance.save()

    # For writing questions, activate required features/configs based on question type
    if not is_registration:
        feature_slug = _get_feature_from_question_type(question_instance.typ)
        if feature_slug:
            activate_features(context, {feature_slug})
        config_name = _get_config_from_question_type(question_instance.typ)
        if config_name:
            activate_configs(context, {config_name})

    # Return appropriate success message based on operation
    return f"OK - Created {question_name}" if was_created else f"OK - Updated {question_name}"


def _get_mappings(*, is_registration: bool) -> dict[str, dict[str, str]]:
    """Generate mappings for question field types and attributes.

    Args:
        is_registration: When False (character form), includes additional
                        WritingQuestionType values in the type mapping.

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

    # Add writing-specific question types if needed (character form upload)
    if not is_registration:
        # update typ with WritingQuestionType values not covered by BaseQuestionType mapping
        question_type_mapping = mappings["typ"]

        # Iterate through writing question type choices
        for question_type_key, _label in WritingQuestionType.choices:
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
    if "question" not in csv_row:
        return "ERR - column question missing"

    option_name, err = _get_row_name(csv_row)
    if err:
        return err

    # Find the associated question by name (case-insensitive)
    question_name_lower = csv_row["question"].lower()
    if question_name_lower not in question_name_to_id_map:
        return "ERR - question not found"
    question_id = question_name_to_id_map[question_name_lower]

    # Get or create the option instance
    was_created, option_instance = _get_option(
        import_context, option_name, question_id, is_registration=is_registration
    )

    # Process each field in the CSV row
    for field_name, field_value in csv_row.items():
        # Skip empty/NaN values (except relation columns), and fields that are already processed
        if _skip_row_field(field_name, field_value, ("question", "name")):
            continue
        processed_value = field_value

        # Convert numeric fields to appropriate types
        if field_name == "max_available":
            processed_value = _to_int(processed_value)
        elif field_name == "price":
            processed_value = _to_decimal(processed_value)

        # Handle requirements field with special processing, only adding the uploaded ones
        if field_name == "requirements":
            _assign_requirements(import_context, option_instance, [], field_value, replace=False)
            continue

        # Set the field value on the instance
        setattr(option_instance, field_name, processed_value)

    # Save the instance to database
    option_instance.save()

    # Return appropriate success message
    if was_created:
        return f"OK - Created {option_name}"
    return f"OK - Updated {option_name}"


def _get_option(
    context: dict, option_name: str, parent_question_id: int, *, is_registration: bool
) -> tuple[bool, RegistrationOption | WritingOption]:
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
        matching_options = RegistrationOption.objects.filter(
            event=context["event"],
            question_id=parent_question_id,
            name__iexact=option_name,
        )
        if matching_options.exists():
            option_instance = matching_options.first()
            was_created = False
        else:
            option_instance = RegistrationOption.objects.create(
                event=context["event"],
                question_id=parent_question_id,
                name=option_name,
            )
            was_created = True
    else:
        event = get_event_class_parent(context["event"].id, WritingOption, context=context)
        matching_options = WritingOption.objects.filter(
            event=event,
            name__iexact=option_name,
            question_id=parent_question_id,
        )
        if matching_options.exists():
            option_instance = matching_options.first()
            was_created = False
        else:
            option_instance = WritingOption.objects.create(
                event_id=event,
                name=option_name,
                question_id=parent_question_id,
            )
            was_created = True
    return was_created, option_instance
