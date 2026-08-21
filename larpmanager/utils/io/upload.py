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
import re
import shutil
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from PIL import Image

from larpmanager.cache.experience import clear_event_exp_systems_cache, get_event_exp_systems
from larpmanager.cache.question import get_cached_registration_questions, get_cached_writing_questions
from larpmanager.models.base import Feature
from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.event import EventConfig
from larpmanager.models.experience import (
    AbilityExp,
    AbilityTypeExp,
    CriterionExp,
    DeliveryExp,
    ModifierExp,
    Operation,
    RuleExp,
    SystemExp,
)
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    QuestionVisibility,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    RegistrationQuestionApplicable,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.member import LogOperationType, Member, Membership, MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.utils import UploadToPathAndRename
from larpmanager.models.writing import (
    Character,
    CharacterStatus,
    Faction,
    Plot,
    PlotCharacterRel,
    Relationship,
)
from larpmanager.utils.core.common import get_event_class_parent, get_event_elements
from larpmanager.utils.edit.backend import save_log
from larpmanager.utils.io.download import _get_column_names
from larpmanager.utils.security import (
    FileSecurityError,
    safe_extract_zip,
    sanitize_dataframe,
    validate_file_size,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.forms import Form

    from larpmanager.models.base import BaseModel
    from larpmanager.models.event import Run

logger = logging.getLogger(__name__)

MAX_CSV_ROWS = 10_000
MAX_COMMA_VALUES = 100
MAX_CSV_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_PROFILE_IMAGE_SIZE = 1024 * 1024  # 1MB
MAX_PROFILE_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB: guard against decompression bombs
_QUALITY_START = 95
_QUALITY_STEP = 10
_QUALITY_MIN = 20
_SCALE_STEP = 0.1
_SCALE_MIN = 0.1


def normalize_profile_image(img_data: bytes) -> bytes:
    """Normalize and reduce uploaded profile size."""
    if len(img_data) > MAX_PROFILE_UPLOAD_SIZE:
        msg = "Uploaded image exceeds maximum allowed size"
        raise ValueError(msg)

    # Always converts to JPEG. Reduces quality in steps first, then scales down.
    with Image.open(io.BytesIO(img_data)) as im:
        if im.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[3])
            rgb = background
        else:
            rgb = im.convert("RGB")
        width, height = rgb.size

        quality = _QUALITY_START
        while quality >= _QUALITY_MIN:
            buf = io.BytesIO()
            rgb.save(buf, format="JPEG", quality=quality)
            if buf.tell() <= MAX_PROFILE_IMAGE_SIZE:
                return buf.getvalue()
            quality -= _QUALITY_STEP

        scale = 1.0 - _SCALE_STEP
        while scale >= _SCALE_MIN:
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            resized = rgb.resize(new_size, Image.LANCZOS)
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=_QUALITY_MIN)
            if buf.tell() <= MAX_PROFILE_IMAGE_SIZE:
                return buf.getvalue()
            scale -= _SCALE_STEP

        buf.seek(0)
        return buf.read()


def _normalize_numeric(value: str) -> str:
    """Normalize numeric string by replacing comma decimal separator with dot."""
    return str(value).replace(",", ".")


def _to_int(value: str) -> int:
    """Convert numeric string to integer, handling both comma and dot decimal separators."""
    return int(float(_normalize_numeric(value)))


def _to_decimal(value: str) -> Decimal:
    """Convert numeric string to Decimal, handling both comma and dot decimal separators."""
    return Decimal(_normalize_numeric(value))


def _is_missing(value: object) -> bool:
    """Return whether a CSV cell carries no value at all (None or NaN).

    An empty string is not missing: it is an explicit request to clear the field.
    """
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _is_blank(value: object) -> bool:
    """Return whether a CSV cell holds no meaningful text."""
    return not str(value).strip()


def _strip_number_prefix(name: str) -> str:
    """Strip initial '#number ' pattern from name."""
    return re.sub(r"^#\d+\s+", "", name)


_HTML_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>")


def _text_to_html_paragraphs(value: str) -> str:
    """Wrap plain-text lines in <p> tags so line breaks render in HTML fields.

    Lines that already contain HTML markup are left untouched, since uploaders
    sometimes paste pre-formatted HTML for some lines but not others.
    """
    text = str(value).strip()
    if not text:
        return text
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "".join(line if _HTML_TAG_RE.search(line) else f"<p>{line}</p>" for line in lines)


def go_upload(context: dict, upload_form_data: Any) -> Any:
    """Route uploaded files to appropriate processing functions.

    Args:
        context: Context dictionary with upload type and settings
        upload_form_data: Uploaded file form data

    Returns:
        list: Result messages from processing function

    """
    # FIX

    upload_type = context["typ"]

    dispatch = {
        "registration_form": lambda: form_load(
            context, upload_form_data, is_registration=True, applicable=RegistrationQuestionApplicable.REGISTRATION
        ),
        "matchmaker_form": lambda: form_load(
            context, upload_form_data, is_registration=True, applicable=RegistrationQuestionApplicable.MATCHMAKER
        ),
        "character_form": lambda: form_load(context, upload_form_data, is_registration=False),
        "registration": lambda: registrations_load(context, upload_form_data),
        "exp_abilitie": lambda: abilities_load(context, upload_form_data),
        "exp_rule": lambda: rules_load(context, upload_form_data),
        "exp_modifier": lambda: modifiers_load(context, upload_form_data),
        "exp_criterion": lambda: criterions_load(context, upload_form_data),
        "exp_deliverie": lambda: deliveries_load(context, upload_form_data),
        "registration_ticket": lambda: tickets_load(context, upload_form_data),
    }
    handler = dispatch.get(upload_type)
    if handler:
        return handler()
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

    """
    # Early return if no file provided
    if not uploaded_file:
        return None

    # SECURITY: Validate file size to prevent memory exhaustion
    try:
        validate_file_size(uploaded_file)
    except FileSecurityError:
        logger.exception("File size validation failed: %s")
        return None

    # Define encoding priority list - most common first
    encodings = [
        "utf-8-sig",
        "utf-8",
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

            # Read with size limit already validated above (prevent issues with compressed data)
            file_content = uploaded_file.read()

            # Decode file content with current encoding
            decoded_content = file_content.decode(encoding)
            string_buffer = io.StringIO(decoded_content)

            # Parse CSV with automatic delimiter detection
            df = pd.read_csv(string_buffer, encoding=encoding, sep=None, engine="python", dtype=str)

            # Sanitize all values to prevent formula injection
            return sanitize_dataframe(df)

        except Exception as parsing_error:  # noqa: BLE001 - Must try all encodings on any parsing error
            # Log error and continue to next encoding
            logger.debug("Failed to parse CSV with encoding %s: %s", encoding, parsing_error)
            continue

    # Return None if all encodings failed
    return None


def _get_file(context: dict, file: Any, column_id: int | None = None) -> tuple[pd.DataFrame | None, list[str]]:
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
    # Check if file was provided
    if not file:
        return None, ["ERR - No file provided. Please select a file to upload"]

    # Check file size before parsing to prevent memory exhaustion
    file_size = getattr(file, "size", None)
    if file_size is None and hasattr(file, "file"):
        file_size = getattr(file.file, "size", None)
    if file_size is not None and file_size > MAX_CSV_FILE_SIZE:
        max_mb = MAX_CSV_FILE_SIZE / (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        return None, [f"ERR - File too large: {actual_mb:.1f}MB exceeds limit of {max_mb:.0f}MB"]

    # Get available column names from context
    _get_column_names(context)
    allowed_column_names = []

    # Add columns from specific column_id if provided
    if column_id is not None:
        allowed_column_names.extend(list(context["columns"][column_id].keys()))

    # Add fields from context if available
    if "fields" in context:
        allowed_column_names.extend(context["fields"].keys())

    # Add columns accepted on upload but not shown in the template
    allowed_column_names.extend(context.get("extra_columns", []))

    # Convert all allowed column names to lowercase for comparison
    allowed_column_names = [column_name.lower() for column_name in allowed_column_names]

    # Read and parse the uploaded CSV file
    input_dataframe = _read_uploaded_csv(file)
    if input_dataframe is None:
        return None, ["ERR - Could not parse the uploaded file. Please check the file format and encoding"]

    # Normalize column names to lowercase for validation
    input_dataframe.columns = [column.lower() for column in input_dataframe.columns]

    # Drop the columns that are not recognized, reporting them once instead of on every row
    not_recognized = [column for column in input_dataframe.columns if column.lower() not in allowed_column_names]
    logs = []
    if not_recognized:
        logs.append(f"WARN - columns ignored: {', '.join(not_recognized)}")
        input_dataframe = input_dataframe.drop(columns=not_recognized)

    return input_dataframe, logs


def registrations_load(context: dict, uploaded_file_form: Form) -> list[str]:
    """Load registration data from uploaded CSV file."""
    (input_dataframe, processing_logs) = _get_file(context, uploaded_file_form.cleaned_data["first"], 0)

    registration_questions = get_cached_registration_questions(context["event"].id)
    questions_mapping = _get_questions(registration_questions)

    if input_dataframe is not None:
        if len(input_dataframe) > MAX_CSV_ROWS:
            return [f"ERR - File too large: {len(input_dataframe)} rows exceeds limit of {MAX_CSV_ROWS}"]
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
        _registration_field_load(context, registration, field_name, field_value, registration_questions, error_logs)

    # Save registration and log the action
    registration.save()
    save_log(context, Registration, registration, operation_type=LogOperationType.UPLOAD)

    # Generate appropriate status message
    if error_logs:
        status_message = "KO - " + ",".join(error_logs)
    elif was_created:
        status_message = f"OK - Created {member}"
    else:
        status_message = f"OK - Updated {member}"

    return status_message


def _registration_field_load(
    context: dict,
    registration: Registration,
    field_name: str,
    field_value: str,
    registration_questions: dict[str, Any],
    error_logs: list[str],
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

    question_info = registration_questions.get(field_name)
    field_type = question_info["typ"] if question_info else None

    if field_type == "ticket":
        _assign_elem(context, registration, "ticket", field_value, RegistrationTicket, error_logs)
    elif field_name == "characters":
        _reg_assign_characters(context, registration, field_value, error_logs)
    elif field_type == "pay_what_you_want":
        registration.pay_what = _to_decimal(field_value)
    elif field_type == "reg_surcharges":
        registration.surcharge = _to_decimal(field_value)
    elif field_type == "reg_quotas":
        registration.quota = _to_decimal(field_value)
    elif field_type == "additional_tickets":
        registration.additionals = _to_int(field_value)
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
    target_object: Any,
    field_name: str,
    lookup_value: str,
    model_type: type,
    error_logs: list[str],
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
    # Check if value is a digit to determine lookup method
    if lookup_value.isdigit():
        # Look up element by number for the given event
        try:
            element = model_type.objects.get(event=context["event"], number=int(lookup_value))
        except ObjectDoesNotExist:
            # Log error if element not found and return without assignment
            error_logs.append(f"ERR - element {field_name} not found")
            return
    else:
        # Look up element by name (case-insensitive) for the given event
        element = model_type.objects.filter(event=context["event"], name__iexact=lookup_value).first()
        if not element:
            # Log error if element not found and return without assignment
            error_logs.append(f"ERR - element {field_name} not found")
            return

    # Assign the found element to the object field
    target_object.__setattr__(field_name, element)


def _get_feature_from_question_type(question_type: str) -> str | None:
    """Get feature slug required for a WritingQuestionType."""
    question_type_to_feature = {
        WritingQuestionType.FACTIONS: "faction",
        WritingQuestionType.MIRROR: "casting",
    }
    return question_type_to_feature.get(question_type)


def _get_config_from_question_type(question_type: str) -> str | None:
    """Get config name required for a WritingQuestionType."""
    question_type_to_config = {
        WritingQuestionType.TITLE: "character_title",
        WritingQuestionType.PROGRESS: "character_progress",
        WritingQuestionType.ASSIGNED: "character_assigned",
    }
    return question_type_to_config.get(question_type)


def _activate_features_from_columns(context: dict, column_names: list[str], writing_questions: QuerySet) -> None:
    """Activate features and configs automatically based on uploaded column names.

    Detects which features and configurations are required by the uploaded columns
    and activates them on the event if not already enabled.

    Args:
        context: Context dictionary with event information
        column_names: List of column names from uploaded CSV
        writing_questions: QuerySet of WritingQuestion objects for the event

    """
    # Build mapping of question names to question types
    question_name_to_type = {q["name"].lower(): q["typ"] for q in writing_questions}

    # Collect features and configs that need to be activated
    features_to_activate = set()
    configs_to_activate = set()

    # Check each column to see if it requires a feature or config
    for column_name in column_names:
        column_lower = column_name.lower()

        # Check if column matches a writing question
        if column_lower in question_name_to_type:
            question_type = question_name_to_type[column_lower]

            # Check if this question type requires a feature
            feature_slug = _get_feature_from_question_type(question_type)
            if feature_slug:
                features_to_activate.add(feature_slug)

            # Check if this question type requires a config
            config_name = _get_config_from_question_type(question_type)
            if config_name:
                configs_to_activate.add(config_name)

    activate_features(context, features_to_activate)

    activate_configs(context, configs_to_activate)


def activate_features(context: dict, features_to_activate: set) -> None:
    """Activate features if not already enabled."""
    if not features_to_activate:
        return

    # Get currently enabled features
    enabled_features = set(context["event"].features.values_list("slug", flat=True))

    # Find features that need to be activated
    features_to_add = features_to_activate - enabled_features

    if features_to_add:
        # Get Feature objects for the slugs that need to be added
        features = Feature.objects.filter(slug__in=features_to_add)

        # Add features to the event
        for feature in features:
            context["event"].features.add(feature)
            logger.info("Auto-activated feature '%s' for event %s", feature.slug, context["event"])


def activate_configs(context: dict, configs_to_activate: set) -> None:
    """Activate configs if not already enabled."""
    if not configs_to_activate:
        return

    # Get currently enabled configs
    enabled_configs = set(
        EventConfig.objects.filter(event=context["event"], name__in=configs_to_activate).values_list("name", flat=True)
    )

    # Find configs that need to be activated
    configs_to_add = configs_to_activate - enabled_configs

    if configs_to_add:
        # Create config entries with True value
        for config_name in configs_to_add:
            EventConfig.objects.create(event=context["event"], name=config_name, value="True")
            logger.info("Auto-activated config '%s' for event %s", config_name, context["event"])


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
    RegistrationCharacterRel.objects.filter(registration=registration).delete()

    # Handle multiple characters separated by commas
    character_names = [name.strip() for name in character_names_string.split(",")]
    if len(character_names) > MAX_COMMA_VALUES:
        error_logs.append(f"ERR - Too many characters: {len(character_names)} exceeds limit of {MAX_COMMA_VALUES}")
        return

    for character_name in character_names:
        if not character_name:
            continue

        # Find character by name in the current event
        character = get_event_elements(context["event"].id, Character).filter(name__iexact=character_name).first()
        if not character:
            error_logs.append(f"ERR - Character not found: {character_name}")
            continue

        # Check if character is already assigned to another active registration
        existing_assignments = RegistrationCharacterRel.objects.filter(
            registration__run=context["run"],
            registration__cancellation_date__isnull=True,
            character=character,
        )
        if existing_assignments.exclude(registration_id=registration.id).exists():
            error_logs.append(f"ERR - character already assigned: {character_name}")
            continue

        # Create the character assignment relationship
        RegistrationCharacterRel.objects.get_or_create(registration=registration, character=character)


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
        writing_questions = get_cached_writing_questions(context["event"], context["writing_typ"])
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
            for element in get_event_elements(context["event"].id, Character).values("id", "name")
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
            for element in get_event_elements(context["event"].id, Character).values("id", "name")
        }
        plot_name_to_id = {
            element["name"].lower(): element["id"]
            for element in get_event_elements(context["event"].id, Plot).values("id", "name")
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
    plot_character_relationship, _ = PlotCharacterRel.objects.get_or_create(character_id=character_id, plot_id=plot_id)

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
    relationship, _ = Relationship.objects.get_or_create(source_id=source_character_id, target_id=target_character_id)
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
        answer, _ = RegistrationAnswer.objects.get_or_create(
            registration_id=target_element.id, question_id=question["id"]
        )
    else:
        answer, _ = WritingAnswer.objects.get_or_create(element_id=target_element.id, question_id=question["id"])

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
    target_event = get_event_class_parent(context["event"].id, writing_model_class)

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
        quest_type = get_event_elements(context["event"].id, QuestType).filter(name__iexact=value).first()
        if quest_type:
            element.typ = quest_type
        else:
            logs.append(f"ERR - quest type not found: {value}")
        return

    # Handle quest field with case-insensitive lookup
    if field == "quest":
        quest = get_event_elements(context["event"].id, Quest).filter(name__iexact=value).first()
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
        get_event_elements(context["event"].id, Character).filter(name__iexact=mirror_character_name).first()
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
            questions_lookup = get_event_elements(context["event"].id, question_model_class)
            if is_registration:
                question_model_class = RegistrationQuestion
                questions_lookup = get_event_elements(context["event"].id, question_model_class).filter(
                    applicable=applicable
                )

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


def invert_dict(dictionary: dict[str, str]) -> dict[str, str]:
    """Invert dictionary keys and values, normalizing values to lowercase and stripping whitespace."""
    return {value.lower().strip(): key for key, value in dictionary.items()}


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

    event = get_event_class_parent(context["event"].id, WritingQuestion)

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
    # Skip empty values and already processed fields
    if not field_value or pd.isna(field_value) or field_name in ["applicable", "name"]:
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
        for question_type_key, _ in WritingQuestionType.choices:
            # Add missing keys to maintain consistency
            if question_type_key not in question_type_mapping:
                question_type_mapping[question_type_key] = question_type_key

    return mappings


def _options_load(import_context: dict, csv_row: dict, question_name_to_id_map: dict, *, is_registration: bool) -> str:  # noqa: C901 - Complex CSV option parsing logic
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
        # Skip empty or NaN values
        if not field_value or pd.isna(field_value):
            continue
        processed_value = field_value

        # Skip fields that are already processed
        if field_name in ["question", "name"]:
            continue

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
        event = get_event_class_parent(context["event"].id, WritingOption)
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


def get_csv_upload_tmp(csv_upload: Any, run: Run) -> str:
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
    tmp_file = str(Path(conf_settings.MEDIA_ROOT) / "tmp")

    # Add event-specific subdirectory
    tmp_file = str(Path(tmp_file) / run.event.slug)

    # Ensure directory exists
    if not Path(tmp_file).exists():
        Path(tmp_file).mkdir(mode=0o770, parents=True, exist_ok=True)

    # Generate timestamped filename
    tmp_file = str(Path(tmp_file) / timezone.now().strftime("%Y-%m-%d-%H:%M:%S"))

    # Write uploaded file chunks to temporary file
    with Path(tmp_file).open("wb") as destination:
        destination.writelines(csv_upload.chunks())

    return tmp_file


def cover_load(context: dict, z_obj: Any) -> None:
    """Handle cover image upload and processing from ZIP archive.

    Args:
        context: Context dictionary containing run and event information
        z_obj: ZIP file object containing character cover images

    Side effects:
        Extracts ZIP contents, processes images, updates character cover fields,
        and moves files to proper media directory structure
    """
    # extract images
    fpath = str(Path(conf_settings.MEDIA_ROOT) / "cover_load")
    fpath = str(Path(fpath) / context["run"].event.slug)
    fpath = str(Path(fpath) / str(context["run"].number))
    if Path(fpath).exists():
        shutil.rmtree(fpath)

    safe_extract_zip(z_obj, fpath)
    covers = {}
    # get images
    for root, _dirnames, filenames in os.walk(fpath):
        for el in filenames:
            num = Path(el).stem
            covers[num] = str(Path(root) / el)
    logger.debug("Extracted covers: %s", covers)
    upload_to = UploadToPathAndRename("character/cover/")
    # cicle characters
    for c in get_event_elements(context["run"].event_id, Character):
        num = str(c.number)
        if num not in covers:
            continue
        fn = upload_to.__call__(c, covers[num])
        c.cover = fn
        c.save()
        Path(covers[num]).rename(Path(conf_settings.MEDIA_ROOT) / fn)


def _get_row_name(csv_row: dict) -> tuple[str | None, str | None]:
    """Extract and validate name from a CSV row. Returns (name, error) tuple."""
    if "name" not in csv_row:
        return None, "ERR - There is no name column"
    name = csv_row["name"]
    try:
        if pd.isna(name):
            return None, "ERR - Empty name, row skipped"
    except (TypeError, ValueError):
        pass
    stripped_name = str(name).strip()
    if not stripped_name:
        return None, "ERR - Empty name, row skipped"
    return stripped_name, None


def _get_row_number(csv_row: dict) -> tuple[int | None, str | None]:
    """Extract and validate number from a CSV row. Returns (number, error) tuple."""
    if "number" not in csv_row:
        return None, "ERR - There is no number column"
    number = csv_row["number"]
    try:
        if pd.isna(number):
            return None, "ERR - Empty number, row skipped"
    except (TypeError, ValueError):
        pass
    try:
        return int(number), None
    except (TypeError, ValueError):
        return None, f"ERR - Invalid number value: {number}"


def tickets_load(context: dict, form: Form) -> list[str]:
    """Load tickets from uploaded file data."""
    # Extract and validate file data from form
    (uploaded_dataframe, log_messages) = _get_file(context, form.cleaned_data["first"], 0)

    # Process each row if data frame is valid
    if uploaded_dataframe is not None:
        if len(uploaded_dataframe) > MAX_CSV_ROWS:
            return [f"ERR - File too large: {len(uploaded_dataframe)} rows exceeds limit of {MAX_CSV_ROWS}"]
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
    name, err = _get_row_name(csv_row)
    if err:
        return err

    # Get or create ticket object for the event
    (ticket, was_created) = RegistrationTicket.objects.get_or_create(event=context["event"], name=name)

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
            processed_value = _to_int(field_value)
        if field_name == "price":
            processed_value = _to_decimal(field_value)

        # Set the field value on the ticket object
        setattr(ticket, field_name, processed_value)

    # Save the ticket and log the operation
    ticket.save()
    save_log(context, RegistrationTicket, ticket, operation_type=LogOperationType.UPLOAD)

    # Return appropriate success message
    return f"OK - Created {ticket}" if was_created else f"OK - Updated {ticket}"


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


def _resolve_exp_system(event: Any) -> Any:
    """Return the first SystemExp for the event, creating it if none exists."""
    systems = get_event_exp_systems(event)
    if systems:
        return systems[0]
    system = SystemExp.objects.create(event_id=get_event_class_parent(event.id, SystemExp), name="XP", number=1)
    clear_event_exp_systems_cache(get_event_class_parent(event.id, SystemExp))
    return system


def _assign_system(context: dict, element: Any, logs: list[str], value: str) -> None:
    """Assign the experience system to an element by name."""
    system = get_event_elements(context["event"].id, SystemExp).filter(name__iexact=value.strip()).first()
    if system:
        element.system = system
    else:
        logs.append(f"ERR - system not found: {value}")


_ABILITY_PLAIN_FIELDS = frozenset({"descr"})

# Criterion and delivery columns whose empty value is meaningful: it clears the relation instead of being ignored
_RELATION_COLUMNS = frozenset({"prerequisites", "requirements", "factions", "characters"})


def _relation_value(value: object) -> str:
    """Normalize a relation cell, reading a missing value as empty so that it clears the relation."""
    return "" if _is_missing(value) else str(value)


def _skip_row_field(field_name: str, field_value: object, handled: tuple[str, ...]) -> bool:
    """Return whether a CSV field must be skipped, because already handled or holding no value.

    Relation columns are never skipped: an empty cell there clears the relation.
    """
    if field_name in handled:
        return True
    return field_name not in _RELATION_COLUMNS and _is_missing(field_value)


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
    parent_event = get_event_class_parent(event.id, AbilityExp)

    # Match the stored ability ignoring case, so that a different casing updates it instead of duplicating it
    ability_element = AbilityExp.objects.filter(event=parent_event, name__iexact=name).order_by("number").first()
    was_created = ability_element is None
    if was_created:
        ability_element = AbilityExp.objects.create(
            event_id=parent_event,
            name=name,
            system=_resolve_exp_system(event),
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


def _assign_type(
    context: dict,
    ability_element: AbilityExp,
    error_logs: list[str],
    ability_type_name: str,
) -> None:
    """Assign ability type to element from event context."""
    # Query ability type by name from event context
    ability_type = (
        get_event_elements(context["event"].id, AbilityTypeExp).filter(name__iexact=ability_type_name).first()
    )
    if ability_type:
        ability_element.typ = ability_type
    else:
        # Log error if ability type not found
        error_logs.append(f"ERR - quest type not found: {ability_type_name}")


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
            get_event_elements(context["event"].id, related_model).filter(name__iexact=raw_name.strip()).first()
        )
        if related_element:
            manager.add(related_element)
        else:
            logs.append(f"{label} not found: {raw_name}")


_REL_PREREQUISITES = ("prerequisites", AbilityExp, "Prerequisite")
_REL_REQUIREMENTS = ("requirements", WritingOption, "requirements")


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
    writing_element: BaseModel,
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
        ability = get_event_elements(context["event"].id, AbilityExp).filter(name__iexact=ability_name.strip()).first()
        if ability:
            element.save()
            element.abilities.add(ability)
        else:
            logs.append(f"Ability not found: {ability_name}")


def rules_load(context: dict, form: Form) -> list[str]:
    """Load rules from uploaded file and process each row."""
    (input_dataframe, processing_logs) = _get_file(context, form.cleaned_data["first"], 0)
    if input_dataframe is not None:
        for rule_row in input_dataframe.to_dict(orient="records"):
            processing_logs.append(_rule_load(context, rule_row))
    return processing_logs


def _assign_rule_field(context: dict, rule: RuleExp, logs: list[str], value: str) -> None:
    """Assign the WritingQuestion FK field to a rule by name."""
    field_obj = get_event_elements(context["event"].id, WritingQuestion).filter(name__iexact=value.strip()).first()
    if field_obj:
        rule.field = field_obj
    else:
        logs.append(f"ERR - field not found: {value}")


def _assign_operation(element: Any, logs: list[str], value: str) -> None:
    """Assign the operation to an element by value string (ADD/SUB/MUL/DIV)."""
    operation_map = {op.value: op for op in Operation}
    op_val = value.strip().upper()
    if op_val in operation_map:
        element.operation = operation_map[op_val]
    else:
        logs.append(f"ERR - unknown operation: {value}")


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
    event_parent = get_event_class_parent(event.id, RuleExp)

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
        event=get_event_class_parent(event.id, ModifierExp),
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


def _row_result(status: str, logs: list[str]) -> str:
    """Combine the row status with the errors collected while applying its fields."""
    return "; ".join([status, *logs]) if logs else status


_REL_FACTIONS = ("factions", Faction, "Faction")
_REL_CHARACTERS = ("characters", Character, "Character")


def _assign_factions(context: dict, element: Any, logs: list[str], value: str) -> None:
    """Assign factions to an element from comma-separated names."""
    _assign_relation(context, element, logs, value, _REL_FACTIONS)


def _assign_characters(context: dict, element: Any, logs: list[str], value: str) -> None:
    """Assign characters to an element from comma-separated names."""
    _assign_relation(context, element, logs, value, _REL_CHARACTERS)


def criterions_load(context: dict, form: Form) -> list[str]:
    """Load criterions from uploaded file and process each row."""
    (input_dataframe, processing_logs) = _get_file(context, form.cleaned_data["first"], 0)
    if input_dataframe is not None:
        if len(input_dataframe) > MAX_CSV_ROWS:
            return [f"ERR - File too large: {len(input_dataframe)} rows exceeds limit of {MAX_CSV_ROWS}"]
        for criterion_row in input_dataframe.to_dict(orient="records"):
            processing_logs.append(_criterion_load(context, criterion_row))
    return processing_logs


def _assign_numeric(element: Any, logs: list[str], field_name: str, value: object, *, decimal: bool = False) -> None:
    """Assign a numeric field to an element, logging an error for values that cannot be parsed."""
    try:
        setattr(element, field_name, _to_decimal(value) if decimal else _to_int(value))
    except (TypeError, ValueError, ArithmeticError):
        logs.append(f"ERR - invalid {field_name} value: {value}")


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
    parent_event = get_event_class_parent(event.id, CriterionExp)

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
            system=_resolve_exp_system(event),
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


def _free_delivery_number(parent_event: Any, number: int | None, logs: list[str]) -> int | None:
    """Return the requested number, only if not already taken by another delivery."""
    if number is None:
        return None
    if DeliveryExp.objects.filter(event=parent_event, number=number).exists():
        logs.append(f"WARN - number already taken, assigned automatically: {number}")
        return None
    return number


def _find_delivery(parent_event: Any, name: str, number: int | None, logs: list[str]) -> DeliveryExp | None:
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
    parent_event = get_event_class_parent(event.id, DeliveryExp)

    logs = []
    number = _row_delivery_number(csv_row, logs)

    delivery = _find_delivery(parent_event, name, number, logs)
    was_created = delivery is None
    if was_created:
        # Keep the uploaded number only on creation, and only when still available
        fields = {"system": _resolve_exp_system(event), "amount": 0}
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
