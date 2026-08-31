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

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.cache.question import get_cached_registration_questions
from larpmanager.models.member import LogOperationType, Membership, MembershipStatus
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket
from larpmanager.models.writing import Character, get_event_elements
from larpmanager.utils.edit.backend import save_log
from larpmanager.utils.io.upload.constants import MAX_COMMA_VALUES, MAX_CSV_ROWS
from larpmanager.utils.io.upload.csv_file import _get_file
from larpmanager.utils.io.upload.parsing import _is_missing, _to_decimal, _to_int
from larpmanager.utils.io.upload.writing import _assign_choice_answer, _get_questions

if TYPE_CHECKING:
    from django.forms import Form


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
    registration_questions: dict[str, object],
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

    if _is_missing(field_value):
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
    target_object: object,
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
        character = (
            get_event_elements(context["event"].id, Character, context=context)
            .filter(name__iexact=character_name)
            .first()
        )
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
