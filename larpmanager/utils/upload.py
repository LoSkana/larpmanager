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

import io
import os
import shutil
from datetime import datetime
from decimal import Decimal

import pandas as pd
from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import UploadedFile
from django.forms import Form
from django.http import HttpRequest

from larpmanager.models.base import BaseModel
from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.event import Run
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


def go_upload(request, ctx, form):
    """Route uploaded files to appropriate processing functions.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary with upload type and settings
        form: Uploaded file form data

    Returns:
        list: Result messages from processing function
    """
    # FIX
    # if request.POST.get("upload") == "cover":
    #     # check extension
    #     if zipfile.is_zipfile(form[0]):
    #         with zipfile.ZipFile(form[0]) as z_obj:
    #             cover_load(ctx, z_obj)
    #         z_obj.close()
    #         return ""

    if ctx["typ"] == "registration_form":
        return form_load(request, ctx, form, is_registration=True)
    elif ctx["typ"] == "character_form":
        return form_load(request, ctx, form, is_registration=False)
    elif ctx["typ"] == "registration":
        return registrations_load(request, ctx, form)
    elif ctx["typ"] == "px_abilitie":
        return abilities_load(request, ctx, form)
    elif ctx["typ"] == "registration_ticket":
        return tickets_load(request, ctx, form)
    else:
        return writing_load(request, ctx, form)


def _read_uploaded_csv(uploaded_file) -> pd.DataFrame | None:
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
            decoded = uploaded_file.read().decode(encoding)
            text_io = io.StringIO(decoded)

            # Parse CSV with automatic delimiter detection
            return pd.read_csv(text_io, encoding=encoding, sep=None, engine="python", dtype=str)
        except Exception as err:
            # Log error and continue to next encoding
            print(err)
            continue

    # Return None if all encodings failed
    return None


def _get_file(ctx: dict, file, column_id: str = None) -> tuple[any, list[str]]:
    """Get file path and save uploaded file to media directory.

    Args:
        ctx: Context dictionary containing event information and column definitions.
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
    _get_column_names(ctx)
    allowed = []

    # Add columns from specific column_id if provided
    if column_id is not None:
        allowed.extend(list(ctx["columns"][column_id].keys()))

    # Add fields from context if available
    if "fields" in ctx:
        allowed.extend(ctx["fields"].keys())

    # Convert all allowed column names to lowercase for comparison
    allowed = [a.lower() for a in allowed]

    # Read and parse the uploaded CSV file
    input_df = _read_uploaded_csv(file)
    if input_df is None:
        return None, ["ERR - Could not read input csv"]

    # Normalize column names to lowercase for validation
    input_df.columns = [c.lower() for c in input_df.columns]

    # Validate that all columns are recognized
    for col in input_df.columns:
        if col.lower() not in allowed:
            return None, [f"ERR - column not recognized: {col}"]

    return input_df, []


def registrations_load(request, ctx, form):
    """Load registration data from uploaded CSV file.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary with event and form settings
        form: Form data containing uploaded CSV file

    Returns:
        str: HTML formatted result message with processing statistics
    """
    (input_df, logs) = _get_file(ctx, form.cleaned_data["first"], 0)

    que = ctx["event"].get_elements(RegistrationQuestion).prefetch_related("options")
    questions = _get_questions(que)

    if input_df is not None:
        for row in input_df.to_dict(orient="records"):
            logs.append(_reg_load(request, ctx, row, questions))
    return logs


def _reg_load(request, ctx: dict, row: dict, questions: list) -> str:
    """Load registration data from CSV row for bulk import.

    Creates or updates registrations with field validation, membership checks,
    and question processing for event registration imports.

    Args:
        request: HTTP request object containing user information
        ctx: Context dictionary containing event and run information
        row: Dictionary representing a CSV row with registration data
        questions: List of registration questions for the event

    Returns:
        str: Status message indicating success/failure and details

    Raises:
        ObjectDoesNotExist: When user email or membership is not found
    """
    # Validate required email column exists
    if "email" not in row:
        return "ERR - There is no email column"

    # Find user by email (case-insensitive)
    try:
        user = User.objects.get(email__iexact=row["email"].strip())
    except ObjectDoesNotExist:
        return "ERR - Email not found"

    member = user.member

    # Check if user has valid membership for this association
    try:
        membership = Membership.objects.get(member=member, assoc_id=ctx["event"].assoc_id)
    except ObjectDoesNotExist:
        return "ERR - Sharing data not found"

    # Verify user has approved data sharing
    if membership.status == MembershipStatus.EMPTY:
        return "ERR - User has not approved sharing of data"

    # Get or create registration for this run and member
    (reg, cr) = Registration.objects.get_or_create(run=ctx["run"], member=member, cancellation_date__isnull=True)

    logs = []

    # Process each field in the CSV row
    for field, value in row.items():
        _reg_field_load(ctx, reg, field, value, questions, logs)

    # Save registration and log the action
    reg.save()
    save_log(request.user.member, Registration, reg)

    # Generate appropriate status message
    if logs:
        msg = "KO - " + ",".join(logs)
    elif cr:
        msg = f"OK - Created {member}"
    else:
        msg = f"OK - Updated {member}"

    return msg


def _reg_field_load(ctx, reg, field, value, questions, logs):
    """Load individual registration field from CSV data.

    Args:
        ctx: Context dictionary with event data
        reg: Registration instance to update
        field: Field name from CSV
        value: Field value from CSV
        questions: Dictionary of registration questions
        logs: List to append error messages to
    """
    if field == "email":
        return

    if not value or pd.isna(value):
        return

    if field == "ticket":
        _assign_elem(ctx, reg, field, value, RegistrationTicket, logs)
    elif field == "characters":
        _reg_assign_characters(ctx, reg, value, logs)
    elif field == "pwyw":
        reg.pay_what = Decimal(value)
    else:
        _assign_choice_answer(reg, field, value, questions, logs, is_registration=True)


def _assign_elem(ctx: dict, obj: object, field: str, value: str, typ: type, logs: list) -> None:
    """
    Assign an element to an object field based on value lookup.

    Args:
        ctx: Context dictionary containing event information
        obj: Target object to assign the field to
        field: Name of the field to assign
        value: Value to search for (number or name)
        typ: Model type to query for the element
        logs: List to append error messages to

    Returns:
        None
    """
    try:
        # Check if value is numeric to determine lookup strategy
        if value.isdigit():
            # Lookup by number field for numeric values
            el = typ.objects.get(event=ctx["event"], number=int(value))
        else:
            # Lookup by name field (case-insensitive) for string values
            el = typ.objects.get(event=ctx["event"], name__iexact=value)
    except ObjectDoesNotExist:
        # Log error and return early if element not found
        logs.append(f"ERR - element {field} not found")
        return

    # Assign the found element to the specified field
    obj.__setattr__(field, el)


def _reg_assign_characters(ctx: dict, reg: Registration, value: str, logs: list[str]) -> None:
    """Assign characters to a registration based on comma-separated character names.

    Args:
        ctx: Context dictionary containing 'event' and 'run' information
        reg: Registration object to assign characters to
        value: Comma-separated string of character names
        logs: List to append error messages to
    """
    # Clear existing character assignments for this registration
    RegistrationCharacterRel.objects.filter(reg=reg).delete()

    # Handle multiple characters separated by commas
    character_names = [name.strip() for name in value.split(",")]

    for char_name in character_names:
        # Skip empty character names
        if not char_name:
            continue

        # Try to find the character by name (case insensitive)
        try:
            char = Character.objects.get(event=ctx["event"], name__iexact=char_name)
        except ObjectDoesNotExist:
            logs.append(f"ERR - Character not found: {char_name}")
            continue

        # Check if character is already assigned to another active registration
        que = RegistrationCharacterRel.objects.filter(
            reg__run=ctx["run"],
            reg__cancellation_date__isnull=True,
            character=char,
        )

        # Exclude current registration from the check
        if que.exclude(reg_id=reg.id).exists():
            logs.append(f"ERR - character already assigned: {char_name}")
            continue

        # Create the character assignment relationship
        RegistrationCharacterRel.objects.get_or_create(reg=reg, character=char)


def writing_load(request, ctx: dict, form) -> list[str]:
    """Load writing data from uploaded files and process relationships.

    Processes uploaded files containing writing elements and their relationships.
    Handles both character and plot types with their respective relationship data.

    Args:
        request: HTTP request object containing user and session data
        ctx: Context dictionary containing event, writing_typ, and typ keys
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
        (input_df, logs) = _get_file(ctx, uploaded_file, 0)

        # Get questions for the writing type with their options
        que = (
            ctx["event"].get_elements(WritingQuestion).filter(applicable=ctx["writing_typ"]).prefetch_related("options")
        )
        questions = _get_questions(que)

        # Process each row of writing data
        if input_df is not None:
            for row in input_df.to_dict(orient="records"):
                logs.append(element_load(request, ctx, row, questions))

    # Process character relationships if type is character
    if ctx["typ"] == "character":
        uploaded_file = form.cleaned_data.get("second", None)
        if uploaded_file:
            # Load relationships file and get character mapping
            (input_df, new_logs) = _get_file(ctx, uploaded_file, 1)
            chars = {el["name"].lower(): el["id"] for el in ctx["event"].get_elements(Character).values("id", "name")}

            # Process each relationship row
            if input_df is not None:
                for row in input_df.to_dict(orient="records"):
                    new_logs.append(_relationships_load(row, chars))
            logs.extend(new_logs)

    # Process plot relationships if type is plot
    if ctx["typ"] == "plot":
        uploaded_file = form.cleaned_data.get("second", None)
        if uploaded_file:
            # Load plot relationships file and get character/plot mappings
            (input_df, new_logs) = _get_file(ctx, uploaded_file, 1)
            chars = {el["name"].lower(): el["id"] for el in ctx["event"].get_elements(Character).values("id", "name")}
            plots = {el["name"].lower(): el["id"] for el in ctx["event"].get_elements(Plot).values("id", "name")}

            # Process each plot relationship row
            if input_df is not None:
                for row in input_df.to_dict(orient="records"):
                    new_logs.append(_plot_rels_load(row, chars, plots))
            logs.extend(new_logs)

    return logs


def _plot_rels_load(row: dict, chars: dict[str, int], plots: dict[str, int]) -> str:
    """Load plot-character relationships from a row of data.

    Args:
        row: Dictionary containing character, plot, and text data
        chars: Mapping of character names (lowercase) to character IDs
        plots: Mapping of plot names (lowercase) to plot IDs

    Returns:
        Status message indicating success or failure with details
    """
    # Extract and normalize character name from row data
    char = row.get("character", "").lower()
    if char not in chars:
        return f"ERR - source not found {char}"
    char_id = chars[char]

    # Extract and normalize plot name from row data
    plot = row.get("plot", "").lower()
    if plot not in plots:
        return f"ERR - target not found {plot}"
    plot_id = plots[plot]

    # Create or retrieve the plot-character relationship
    rel, _ = PlotCharacterRel.objects.get_or_create(character_id=char_id, plot_id=plot_id)

    # Update relationship text and save to database
    rel.text = row.get("text")
    rel.save()
    return f"OK - Plot role {char} {plot}"


def _relationships_load(row: dict, chars: dict[str, int]) -> str:
    """Load relationship data from a row into the database.

    Args:
        row: Dictionary containing relationship data with 'source', 'target', and 'text' keys
        chars: Dictionary mapping character names (lowercase) to their IDs

    Returns:
        Status message indicating success or error details
    """
    # Extract and validate source character
    source_char = row.get("source", "").lower()
    if source_char not in chars:
        return f"ERR - source not found {source_char}"
    source_id = chars[source_char]

    # Extract and validate target character
    target_char = row.get("target", "").lower()
    if target_char not in chars:
        return f"ERR - target not found {target_char}"
    target_id = chars[target_char]

    # Create or retrieve relationship and update text
    relation, _ = Relationship.objects.get_or_create(source_id=source_id, target_id=target_id)
    relation.text = row.get("text")
    relation.save()

    return f"OK - Relationship {source_char} {target_char}"


def _get_questions(que):
    questions = {}
    for question in que:
        options = {option.name.lower(): option.id for option in question.options.all()}
        questions[question.name.lower()] = {"id": question.id, "typ": question.typ, "options": options}
    return questions


def _assign_choice_answer(element, field, value, questions, logs, is_registration=False):
    """Assign choice answers to form elements during bulk import.

    Processes choice field assignments with validation, option matching,
    and proper relationship creation for registration or character forms.
    """
    field = field.lower()
    if field not in questions:
        logs.append(f"ERR - question not found {field}")
        return

    question = questions[field]

    # check if answer
    if question["typ"] in [BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR]:
        if is_registration:
            answer, _ = RegistrationAnswer.objects.get_or_create(reg_id=element.id, question_id=question["id"])
        else:
            answer, _ = WritingAnswer.objects.get_or_create(element_id=element.id, question_id=question["id"])
        answer.text = value
        answer.save()

    # check if choice
    else:
        if is_registration:
            RegistrationChoice.objects.filter(reg_id=element.id, question_id=question["id"]).delete()
        else:
            WritingChoice.objects.filter(element_id=element.id, question_id=question["id"]).delete()

        for input_opt_orig in value.split(","):
            input_opt = input_opt_orig.lower().strip()
            option_id = question["options"].get(input_opt)
            if not option_id:
                logs.append(f"Problem with question {field}: couldn't find option {input_opt}")
                continue

            if is_registration:
                RegistrationChoice.objects.create(reg_id=element.id, question_id=question["id"], option_id=option_id)
            else:
                WritingChoice.objects.create(element_id=element.id, question_id=question["id"], option_id=option_id)


def element_load(request, ctx: dict, row: dict, questions: list) -> str:
    """Load generic element data from CSV row for bulk import.

    Processes element creation or updates with field validation,
    question processing, and proper logging for various element types.

    Args:
        request: HTTP request object containing user information
        ctx: Context dictionary with field_name, typ, event, and fields
        row: CSV row data as dictionary with field names and values
        questions: List of questions for element processing

    Returns:
        Status message string indicating success/failure and operation details
    """
    # Validate that the required field name exists in the CSV row
    field_name = ctx["field_name"].lower()
    if field_name not in row:
        return "ERR - There is no name in fields"

    # Extract element name and determine the appropriate model class
    name = row[field_name]
    typ = QuestionApplicable.get_applicable(ctx["typ"])
    writing_cls = QuestionApplicable.get_applicable_inverse(typ)

    # Try to find existing element or create new one
    created = False
    try:
        element = writing_cls.objects.get(event=ctx["event"], name__iexact=name)
    except ObjectDoesNotExist:
        element = writing_cls.objects.create(event=ctx["event"], name=name)
        created = True

    # Initialize logging for field processing errors
    logs = []

    # Normalize field names to lowercase for consistent processing
    ctx["fields"] = {key.lower(): content for key, content in ctx["fields"].items()}

    # Process each field in the CSV row and update element
    for field, value in row.items():
        _writing_load_field(ctx, element, field, value, questions, logs)

    # Save the element and log the operation
    element.save()
    save_log(request.user.member, writing_cls, element)

    # Return appropriate status message based on processing results
    if logs:
        return "KO - " + ",".join(logs)

    if created:
        return f"OK - Created {name}"
    else:
        return f"OK - Updated {name}"


def _writing_load_field(ctx: dict, element: BaseModel, field: str, value: any, questions: dict, logs: list) -> None:
    """
    Load writing field data during upload processing.

    Processes individual field values from upload data and updates the writing element
    accordingly. Handles special fields like 'typ' and 'quest' with object lookups,
    and delegates other field types to question loading.

    Parameters
    ----------
    ctx : dict
        Context dictionary containing event and field information
    element : WritingElement
        Writing element instance to update with field data
    field : str
        Name of the field being processed
    value : any
        Value from upload data for this field
    questions : dict
        Dictionary mapping field names to question instances
    logs : list
        List to append error messages to during processing

    Returns
    -------
    None
        Function modifies element and logs in place
    """
    # Skip processing if value is NaN/null
    if pd.isna(value):
        return

    # Handle quest type field with case-insensitive lookup
    if field == "typ":
        try:
            element.typ = ctx["event"].get_elements(QuestType).get(name__iexact=value)
        except ObjectDoesNotExist:
            logs.append(f"ERR - quest type not found: {value}")
        return

    # Handle quest field with case-insensitive lookup
    if field == "quest":
        try:
            element.quest = ctx["event"].get_elements(Quest).get(name__iexact=value)
        except ObjectDoesNotExist:
            logs.append(f"ERR - quest not found: {value}")
        return

    # Get field type from context configuration
    field_type = ctx["fields"][field]

    # Skip processing for name fields and explicitly skipped fields
    if field_type in [WritingQuestionType.NAME, "skip"]:
        return

    # Convert multiline text to HTML break tags and strip whitespace
    value = "<br />".join(str(value).strip().split("\n"))
    if not value:
        return

    # Delegate to question loading for all other field types
    _writing_question_load(ctx, element, field, field_type, logs, questions, value)


def _writing_question_load(ctx, element, field, field_type, logs, questions, value):
    """Process and load writing question values into element fields.

    Args:
        ctx: Context dictionary
        element: Target writing element to update
        field: Field identifier
        field_type: WritingQuestionType enum value
        logs: List to collect processing logs
        questions: Dictionary of questions
        value: Value to assign to the field
    """
    if field_type == WritingQuestionType.MIRROR:
        _get_mirror_instance(ctx, element, value, logs)
    elif field_type == WritingQuestionType.HIDE:
        element.hide = value.lower() == "true"
    elif field_type == WritingQuestionType.FACTIONS:
        _assign_faction(ctx, element, value, logs)
    elif field_type == WritingQuestionType.TEASER:
        element.teaser = value
    elif field_type == WritingQuestionType.SHEET:
        element.text = value
    elif field_type == WritingQuestionType.TITLE:
        element.title = value
    # TODO implement
    # elif field_type == QuestionType.COVER:
    #     element.cover = value
    # elif field_type == QuestionType.PROGRESS:
    #     element.cover = value
    # elif field_type == QuestionType.ASSIGNED:
    #     element.cover = value
    else:
        _assign_choice_answer(element, field, value, questions, logs)


def _get_mirror_instance(ctx, element, value, logs):
    try:
        element.mirror = ctx["event"].get_elements(Character).get(name__iexact=value)
    except ObjectDoesNotExist:
        logs.append(f"ERR - mirror not found: {value}")


def _assign_faction(ctx, element, value, logs):
    for fac_name in value.split(","):
        try:
            fac = Faction.objects.get(name__iexact=fac_name.strip(), event=ctx["event"])
            element.save()  # to be sure
            fac.characters.add(element)
            fac.save()
        except ObjectDoesNotExist:
            logs.append(f"Faction not found: {fac_name}")


def form_load(request, ctx: dict, form, is_registration: bool = True) -> list[str]:
    """Load form questions and options from uploaded files.

    Processes uploaded CSV/Excel files to create form questions and their
    associated options. Handles both registration and writing question types.

    Args:
        request: HTTP request object containing the upload request
        ctx: Context dictionary containing event data and configuration
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
    logs = []

    # Process questions file upload
    uploaded_file = form.cleaned_data.get("first", None)
    if uploaded_file:
        # Parse uploaded questions file into DataFrame
        (input_df, logs) = _get_file(ctx, uploaded_file, 0)
        if input_df is not None:
            # Create question objects from each row in the DataFrame
            for row in input_df.to_dict(orient="records"):
                logs.append(_questions_load(ctx, row, is_registration))

    # Process options file upload
    uploaded_file = form.cleaned_data.get("second", None)
    if uploaded_file:
        # Parse uploaded options file into DataFrame
        (input_df, new_logs) = _get_file(ctx, uploaded_file, 1)
        if input_df is not None:
            # Determine question model class based on registration type
            question_cls = WritingQuestion
            if is_registration:
                question_cls = RegistrationQuestion

            # Build lookup dictionary mapping question names to IDs
            questions = {
                el["name"].lower(): el["id"] for el in ctx["event"].get_elements(question_cls).values("id", "name")
            }

            # Create option objects for each row, linking to existing questions
            for row in input_df.to_dict(orient="records"):
                new_logs.append(_options_load(ctx, row, questions, is_registration))

        # Combine logs from options processing with existing logs
        logs.extend(new_logs)

    return logs


def invert_dict(d):
    return {v.lower().strip(): k for k, v in d.items()}


def _questions_load(ctx: dict, row: dict, is_registration: bool) -> str:
    """Load and validate question data from upload files.

    Processes question configurations for registration or character forms,
    creating or updating RegistrationQuestion or WritingQuestion instances
    based on the row data and validation mappings.

    Args:
        ctx: Context dictionary containing event and processing information
        row: Data row from upload file containing question configuration
        is_registration: True for registration questions, False for writing questions

    Returns:
        Status message indicating success or error details
    """
    # Extract and validate the required name field
    name = row.get("name")
    if not name:
        return "ERR - name not found"

    # Get field validation mappings for the question type
    mappings = _get_mappings(is_registration)

    if is_registration:
        # Create or get registration question instance
        instance, created = RegistrationQuestion.objects.get_or_create(
            event=ctx["event"],
            name__iexact=name,
            defaults={"name": name},
        )
    else:
        # Writing questions require additional 'applicable' field validation
        if "applicable" not in row:
            return "ERR - missing applicable column"
        applicable = row["applicable"]
        if applicable not in mappings["applicable"]:
            return "ERR - unknown applicable"

        # Create or get writing question instance with applicable field
        instance, created = WritingQuestion.objects.get_or_create(
            event=ctx["event"],
            name__iexact=name,
            applicable=mappings["applicable"][applicable],
            defaults={"name": name},
        )

    # Process and validate each field in the row data
    for field, value in row.items():
        # Skip empty values and already processed fields
        if not value or pd.isna(value) or field in ["applicable", "name"]:
            continue

        new_value = value
        # Apply mapping validation if field has defined mappings
        if field in mappings:
            new_value = new_value.lower().strip()
            if new_value not in mappings[field]:
                return f"ERR - unknow value {value} for field {field}"
            new_value = mappings[field][new_value]

        # Handle special case for max_length field conversion
        if field == "max_length":
            new_value = int(value)

        # Set the validated value on the instance
        setattr(instance, field, new_value)

    # Save the configured instance to database
    instance.save()

    # Return appropriate success message based on operation
    if created:
        msg = f"OK - Created {name}"
    else:
        msg = f"OK - Updated {name}"
    return msg


def _get_mappings(is_registration: bool) -> dict[str, dict[str, str]]:
    """Generate mappings for question types and attributes.

    Args:
        is_registration: Whether to include writing question types for registration forms.

    Returns:
        Dictionary containing inverted mappings for question types, status,
        applicable context, and visibility settings.
    """
    # Create base mappings by inverting enum dictionaries
    mappings = {
        "typ": invert_dict(BaseQuestionType.get_mapping()),
        "status": invert_dict(QuestionStatus.get_mapping()),
        "applicable": invert_dict(QuestionApplicable.get_mapping()),
        "visibility": invert_dict(QuestionVisibility.get_mapping()),
    }

    # Add writing question types for registration forms
    if is_registration:
        # Update typ mapping with additional writing question types
        typ_mapping = mappings["typ"]
        for key, _ in WritingQuestionType.choices:
            # Only add new types that aren't already present
            if key not in typ_mapping:
                typ_mapping[key] = key

    return mappings


def _options_load(ctx: dict, row: dict, questions: dict, is_registration: bool) -> str:
    """Load question options from CSV row for bulk import.

    Creates or updates question options with proper validation,
    ordering, and association with the correct question type.

    Args:
        ctx: Context dictionary containing import configuration
        row: CSV row data as dictionary with column headers as keys
        questions: Dictionary mapping question names to question IDs
        is_registration: Boolean flag indicating if this is for registration

    Returns:
        Status message string indicating success/failure of the operation
        Format: "OK - Created/Updated {name}" or "ERR - {error_description}"
    """
    # Validate required fields are present in the CSV row
    for field in ["name", "question"]:
        if field not in row:
            return f"ERR - column {field} missing"

    # Extract and validate the option name
    name = row["name"]
    if not name:
        return "ERR - empty name"

    # Find the associated question by name (case-insensitive)
    question = row["question"].lower()
    if question not in questions:
        return "ERR - question not found"
    question_id = questions[question]

    # Get or create the option instance
    created, instance = _get_option(ctx, is_registration, name, question_id)

    # Process each field in the CSV row
    for field, value in row.items():
        # Skip empty or NaN values
        if not value or pd.isna(value):
            continue
        new_value = value

        # Skip fields that are already processed
        if field in ["question", "name"]:
            continue

        # Convert numeric fields to appropriate types
        if field in ["max_available", "price"]:
            new_value = int(new_value)

        # Handle requirements field with special processing
        if field == "requirements":
            _assign_requirements(ctx, instance, [], value)
            continue

        # Set the field value on the instance
        setattr(instance, field, new_value)

    # Save the instance to database
    instance.save()

    # Return appropriate success message
    if created:
        return f"OK - Created {name}"
    else:
        return f"OK - Updated {name}"


def _get_option(ctx, is_registration, name, question_id):
    """Get or create a question option for registration or writing forms.

    Args:
        ctx: Context dictionary containing event data
        is_registration: Boolean indicating if this is for registration (True) or writing (False)
        name: Name of the option
        question_id: ID of the parent question

    Returns:
        tuple: (created, instance) where created is bool and instance is the option object
    """
    if is_registration:
        instance, created = RegistrationOption.objects.get_or_create(
            event=ctx["event"],
            question_id=question_id,
            name__iexact=name,
            defaults={"name": name},
        )
    else:
        instance, created = WritingOption.objects.get_or_create(
            event=ctx["event"],
            name__iexact=name,
            question_id=question_id,
            defaults={"name": name},
        )
    return created, instance


def get_csv_upload_tmp(csv_upload: UploadedFile, run: Run) -> str:
    """
    Create a temporary file for uploaded CSV data.

    Args:
        csv_upload: The uploaded CSV file object
        run: The run instance associated with the upload

    Returns:
        str: The absolute path to the created temporary file

    Creates a temporary directory structure under MEDIA_ROOT/tmp/event_slug/
    and saves the uploaded CSV file with a timestamp-based filename.
    """
    # Create base temporary directory path
    tmp_file = os.path.join(conf_settings.MEDIA_ROOT, "tmp")

    # Add event-specific subdirectory
    tmp_file = os.path.join(tmp_file, run.event.slug)

    # Ensure the directory exists
    if not os.path.exists(tmp_file):
        os.makedirs(tmp_file)

    # Generate timestamped filename and create full path
    tmp_file = os.path.join(tmp_file, datetime.now().strftime("%Y-%m-%d-%H:%M:%S"))

    # Write uploaded file data to temporary location
    with open(tmp_file, "wb") as destination:
        for chunk in csv_upload.chunks():
            destination.write(chunk)

    return tmp_file


def cover_load(ctx, z_obj):
    """Handle cover image upload and processing from ZIP archive.

    Args:
        ctx: Context dictionary containing run and event information
        z_obj: ZIP file object containing character cover images

    Side effects:
        Extracts ZIP contents, processes images, updates character cover fields,
        and moves files to proper media directory structure
    """
    # extract images
    fpath = os.path.join(conf_settings.MEDIA_ROOT, "cover_load")
    fpath = os.path.join(fpath, ctx["run"].event.slug)
    fpath = os.path.join(fpath, str(ctx["run"].number))
    if os.path.exists(fpath):
        shutil.rmtree(fpath)
    z_obj.extractall(path=fpath)
    covers = {}
    # get images
    for root, _dirnames, filenames in os.walk(fpath):
        for el in filenames:
            num = os.path.splitext(el)[0]
            covers[num] = os.path.join(root, el)
    print(covers)
    upload_to = UploadToPathAndRename("character/cover/")
    # cicle characters
    for c in ctx["run"].event.get_elements(Character):
        num = str(c.number)
        if num not in covers:
            continue
        fn = upload_to.__call__(c, covers[num])
        c.cover = fn
        c.save()
        os.rename(covers[num], os.path.join(conf_settings.MEDIA_ROOT, fn))


def tickets_load(request: HttpRequest, ctx: dict, form: Form) -> list[str]:
    """Load tickets from uploaded file and process each record.

    Args:
        request: The HTTP request object containing user and session data
        ctx: Context dictionary containing processing state and configuration
        form: Form instance with cleaned data including the uploaded file

    Returns:
        List of log messages from the ticket loading process
    """
    # Extract and validate the uploaded file, expecting tickets data
    (input_df, logs) = _get_file(ctx, form.cleaned_data["first"], 0)

    # Process each ticket record if file was successfully loaded
    if input_df is not None:
        # Convert DataFrame to dictionary records for individual processing
        for row in input_df.to_dict(orient="records"):
            # Load each ticket record and collect processing logs
            logs.append(_ticket_load(request, ctx, row))

    return logs


def _ticket_load(request, ctx: dict, row: dict) -> str:
    """Load ticket data from CSV row for bulk import.

    Creates or updates RegistrationTicket objects with proper validation,
    price handling, and relationship setup for event registration.

    Args:
        request: HTTP request object containing user context
        ctx: Context dictionary containing event and other bulk import data
        row: Dictionary representing a single CSV row with ticket data

    Returns:
        str: Status message indicating success ("OK - Created/Updated") or error ("ERR - ...")

    Raises:
        ValueError: When numeric conversion fails for max_available or price fields
    """
    # Validate required name column exists
    if "name" not in row:
        return "ERR - There is no name column"

    # Get or create ticket object for the event
    (ticket, cr) = RegistrationTicket.objects.get_or_create(event=ctx["event"], name=row["name"])

    # Define field mappings for enumeration values
    mappings = {
        "tier": invert_dict(TicketTier.get_mapping()),
    }

    # Process each field in the CSV row
    for field, value in row.items():
        # Skip empty values, NaN values, and the name field (already processed)
        if not value or pd.isna(value) or field in ["name"]:
            continue

        new_value = value

        # Handle mapped enumeration fields
        if field in mappings:
            new_value = new_value.lower().strip()
            if new_value not in mappings[field]:
                return f"ERR - unknow value {value} for field {field}"
            new_value = mappings[field][new_value]

        # Convert numeric fields to appropriate types
        if field == "max_available":
            new_value = int(value)
        if field == "price":
            new_value = float(value)

        # Set the field value on the ticket object
        setattr(ticket, field, new_value)

    # Save the ticket and log the operation
    ticket.save()
    save_log(request.user.member, RegistrationTicket, ticket)

    # Return appropriate success message
    if cr:
        msg = f"OK - Created {ticket}"
    else:
        msg = f"OK - Updated {ticket}"

    return msg


def abilities_load(request: HttpRequest, ctx: dict, form: Form) -> list[str]:
    """Load abilities from uploaded file and process each row.

    Args:
        request: The HTTP request object containing user session and metadata
        ctx: Context dictionary containing processing state and configuration
        form: Django form object with cleaned data including the uploaded file

    Returns:
        List of log messages generated during the ability loading process

    Note:
        Processes abilities from the first uploaded file in the form data.
        Each row in the file is processed individually through _ability_load.
    """
    # Extract and parse the uploaded file, getting DataFrame and initial logs
    (input_df, logs) = _get_file(ctx, form.cleaned_data["first"], 0)

    # Process each row if file was successfully parsed
    if input_df is not None:
        # Convert DataFrame to list of dictionaries for row-by-row processing
        for row in input_df.to_dict(orient="records"):
            # Process individual ability record and append result to logs
            logs.append(_ability_load(request, ctx, row))

    return logs


def _ability_load(request, ctx: dict, row: dict) -> str:
    """Load ability data from CSV row for bulk import.

    Creates or updates ability objects with comprehensive field validation,
    type assignment, prerequisite parsing, and requirement processing.

    Args:
        request: HTTP request object containing user information
        ctx: Context dictionary containing event and related data
        row: Dictionary representing a CSV row with ability data

    Returns:
        str: Status message indicating success/failure of the operation

    Raises:
        ValueError: When required 'name' column is missing from row
        AttributeError: When accessing invalid model fields
    """
    # Validate required name column exists
    if "name" not in row:
        return "ERR - There is no name column"

    # Get or create ability object using event's class parent
    (element, cr) = AbilityPx.objects.get_or_create(event=ctx["event"].get_class_parent(AbilityPx), name=row["name"])

    logs = []

    # Process each field in the CSV row
    for field, value in row.items():
        # Skip empty, NaN values, or the name field (already processed)
        if not value or pd.isna(value) or field in ["name"]:
            continue
        new_value = value

        # Handle type field assignment
        if field == "typ":
            _assign_type(ctx, element, logs, value)
            continue

        # Convert cost field to integer
        if field == "cost":
            new_value = int(value)

        # Handle prerequisites field parsing
        if field == "prerequisites":
            _assign_prereq(ctx, element, logs, value)
            continue

        # Handle requirements field processing
        if field == "requirements":
            _assign_requirements(ctx, element, logs, value)
            continue

        # Convert visible field to boolean
        if field == "visible":
            new_value = value.lower().strip() == "true"

        # Set the attribute on the element
        setattr(element, field, new_value)

    # Save the element to database
    element.save()

    # Log the operation for audit trail
    save_log(request.user.member, AbilityPx, element)

    # Return appropriate success message
    if cr:
        msg = f"OK - Created {element}"
    else:
        msg = f"OK - Updated {element}"

    return msg


def _assign_type(ctx, element, logs, value):
    try:
        element.typ = ctx["event"].get_elements(AbilityTypePx).get(name__iexact=value)
    except ObjectDoesNotExist:
        logs.append(f"ERR - quest type not found: {value}")


def _assign_prereq(ctx, element, logs, value):
    for name in value.split(","):
        try:
            prereq = ctx["event"].get_elements(AbilityPx).get(name__iexact=name.strip())
            element.save()  # to be sure
            element.prerequisites.add(prereq)
        except ObjectDoesNotExist:
            logs.append(f"Prerequisite not found: {name}")


def _assign_requirements(ctx, element, logs, value):
    for name in value.split(","):
        try:
            option = ctx["event"].get_elements(WritingOption).get(name__iexact=name.strip())
            element.save()  # to be sure
            element.requirements.add(option)
        except ObjectDoesNotExist:
            logs.append(f"requirements not found: {name}")
