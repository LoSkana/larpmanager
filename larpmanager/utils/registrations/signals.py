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

import math
from typing import Any

from django.core.exceptions import ObjectDoesNotExist

from larpmanager.accounting.registration import handle_registration_accounting_updates
from larpmanager.cache.accounting import clear_registration_accounting_cache
from larpmanager.cache.basic import get_run_event_id
from larpmanager.cache.config import get_event_config
from larpmanager.cache.links import on_registration_post_save_reset_event_links
from larpmanager.cache.question import get_cached_registration_questions
from larpmanager.cache.registration_counts import clear_registration_counts_cache
from larpmanager.cache.run import get_event_run_ids
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    WritingChoice,
)
from larpmanager.models.registration import Registration, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, get_event_elements
from larpmanager.utils.core.clone_guard import is_clone_active
from larpmanager.utils.core.nav import invalidate_user_nav_entries
from larpmanager.utils.publication.base import publish_registration


def get_reduced_available_count(run: Any) -> int:
    """Calculate remaining reduced ticket slots based on patron registrations and ratio.

    Args:
        run: Run object to calculate reduced tickets for

    Returns:
        Number of reduced tickets still available

    """
    # Get the ratio for reduced tickets per patron registrations
    reduced_tickets_per_patron_ratio = int(get_event_config(run.event_id, "reduced_ratio"))

    # Count current reduced and patron registrations (excluding cancelled)
    reduced_registrations_count = Registration.objects.filter(
        run=run,
        ticket__tier=TicketTier.REDUCED,
        cancellation_date__isnull=True,
    ).count()
    patron_registrations_count = Registration.objects.filter(
        run=run,
        ticket__tier=TicketTier.PATRON,
        cancellation_date__isnull=True,
        tot_payed__gt=0,
    ).count()

    # Calculate available reduced slots: floor(patron_count * ratio / 10) - used_reduced
    return (
        math.floor(patron_registrations_count * reduced_tickets_per_patron_ratio / 10.0) - reduced_registrations_count
    )


def process_registration_event_change(registration: Registration) -> None:
    """Handle registration updates when switching between events.

    When a registration is moved from one event to another, this function attempts
    to preserve the registration data by finding equivalent tickets, questions, and
    options in the new event based on name matching.

    Args:
        registration: The Registration instance being saved with a potentially
                     changed event assignment.

    Returns:
        None

    Note:
        This function performs case-insensitive name matching to find equivalent
        elements in the target event. If no matching elements are found, the
        corresponding fields are set to None.

    """
    # Early return if this is a new registration (no existing data to migrate)
    if not registration.pk:
        return

    try:
        # Fetch the previous state to compare event changes
        previous_registration = Registration.objects.get(pk=registration.pk)
    except ObjectDoesNotExist:
        return

    # Skip processing if the event hasn't actually changed
    context: dict = {}
    if get_run_event_id(previous_registration.run_id, context=context) == get_run_event_id(
        registration.run_id, context=context
    ):
        return

    # Attempt to find a matching ticket in the new event by name
    # This preserves the ticket assignment when moving between events
    ticket_name = registration.ticket.name
    try:
        registration.ticket = get_event_elements(
            get_run_event_id(registration.run_id, context=context), RegistrationTicket
        ).get(name__iexact=ticket_name)
    except ObjectDoesNotExist:
        registration.ticket = None

    cached_questions = get_cached_registration_questions(get_run_event_id(registration.run_id, context=context))

    # Process all registration choices (question/option pairs)
    # Try to find matching questions and options in the new event
    for registration_choice in RegistrationChoice.objects.filter(
        registration=registration, question__typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]
    ):
        question_name = registration_choice.question.name
        option_name = registration_choice.option.name

        try:
            # Find matching question and option in the new event
            matched_question = next(q for q in cached_questions if q["name"].lower() == question_name.lower())
            registration_choice.question_id = matched_question["id"]
            registration_choice.option = get_event_elements(
                get_run_event_id(registration.run_id, context=context), RegistrationOption
            ).get(
                question_id=matched_question["id"],
                name__iexact=option_name,
            )
            registration_choice.save()
        except (StopIteration, ObjectDoesNotExist):
            # Clear the choice if no matching question/option found
            registration_choice.question = None
            registration_choice.option = None

    # Process all registration answers (free-form question responses)
    # Attempt to preserve answers by finding matching questions
    for registration_answer in RegistrationAnswer.objects.filter(
        registration=registration,
        question__typ__in=[BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR],
    ):
        question_name = registration_answer.question.name

        try:
            # Find matching question in the new event to preserve the answer
            matched_question = next(q for q in cached_questions if q["name"].lower() == question_name.lower())
            registration_answer.question_id = matched_question["id"]
            registration_answer.save()
        except StopIteration:
            # Clear the answer if no matching question found
            registration_answer.question = None


def check_character_ticket_options(registration: Registration, character: Character) -> None:
    """Remove writing choices incompatible with registration ticket.

    Removes writing choices for a character that are not available
    for the specific ticket type of the registration.

    Args:
        registration: Registration object containing ticket information
        character: Character object to check writing choices for

    """
    # Get the ticket ID from the registration
    registration_ticket_id = registration.ticket.id

    # Track choice IDs that need to be deleted
    incompatible_choice_ids = []

    # Iterate through all writing choices for this character
    choices = WritingChoice.objects.filter(element_id=character.id).prefetch_related("option__tickets")
    for writing_choice in choices:
        # Get list of ticket IDs that allow this writing option
        allowed_ticket_ids = [ticket.pk for ticket in writing_choice.option.tickets.all()]

        # If option has ticket restrictions and current ticket not allowed
        if allowed_ticket_ids and registration_ticket_id not in allowed_ticket_ids:
            incompatible_choice_ids.append(writing_choice.id)

    # Remove all incompatible choices in a single query
    WritingChoice.objects.filter(pk__in=incompatible_choice_ids).delete()


def process_character_ticket_options(instance: Registration) -> None:
    """Process ticket options for characters associated with a registration instance.

    This function checks ticket options for both characters directly associated
    with the registration instance and characters belonging to the member in
    the same event.

    Args:
        instance: Registration instance containing member, ticket, and run information.
                 Must have attributes: member, ticket, run, characters.

    Returns:
        None

    """
    # Early return if no member is associated with the instance
    if not instance.member:
        return

    # Early return if no ticket is associated with the instance
    if not instance.ticket:
        return

    # Process ticket options for characters directly linked to this registration,
    # plus all characters owned by the member in this event
    event_id = get_run_event_id(instance.run_id)
    characters = set(instance.characters.all()) | set(
        get_event_elements(event_id, Character).filter(player=instance.member)
    )
    for character in characters:
        check_character_ticket_options(instance, character)


def reset_registration_ticket(instance: RegistrationTicket) -> None:
    """Clear accounting cache for all runs in the ticket's event."""
    for run_id in get_event_run_ids(instance.event_id):
        clear_registration_accounting_cache(run_id)
        clear_registration_counts_cache(run_id)


def apply_registration_post_save_updates(registration: Registration) -> None:
    """Apply the cache/accounting updates that must run after a Registration is saved."""
    if is_clone_active():
        return

    # Signup requests awaiting approval have no ticket/characters yet: skip
    if registration.pending:
        return

    # Soft deleted registrations only need their caches dropped, not their data recomputed
    if not registration.deleted:
        process_character_ticket_options(registration)
        handle_registration_accounting_updates(registration)

    clear_registration_accounting_cache(registration.run_id)
    on_registration_post_save_reset_event_links(registration)
    if registration.member_id:
        invalidate_user_nav_entries(registration.member_id)
    clear_registration_counts_cache(registration.run_id)

    if not registration.deleted:
        publish_registration(registration.id)
