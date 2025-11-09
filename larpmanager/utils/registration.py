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

import math
from datetime import datetime
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.config import get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.registration import get_reg_counts
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.models.event import Event, PreRegistration, Run
from larpmanager.models.form import (
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingChoice,
)
from larpmanager.models.member import Member, MembershipStatus, get_user_membership
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, CharacterConfig, CharacterStatus
from larpmanager.utils.common import format_datetime, get_time_diff_today
from larpmanager.utils.exceptions import RewokedMembershipError, SignupError, WaitingError


def registration_available(run: Run, features: dict, context: dict | None = None) -> None:
    """Check if registration is available based on capacity and rules.

    Validates registration availability considering maximum participants,
    ticket quotas, and advanced registration constraints. Updates the run's
    status dictionary with availability information.

    Args:
        run: The run object containing event and status information
        features: Dictionary of enabled features for the event
        context: Optional context dictionary containing cached data

    Returns:
        None: Function modifies run.status in-place

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    # Skip advanced registration rules if no maximum participant limit is set
    if run.event.max_pg == 0:
        run.status["primary"] = True
        return

    # Get registration counts if not provided
    registration_counts = context.get("reg_counts")
    if registration_counts is None:
        registration_counts = get_reg_counts(run)

    # Calculate remaining primary tickets
    remaining_primary_tickets = run.event.max_pg - registration_counts.get("count_player", 0)

    # Get event features if not provided
    if not features:
        features = get_event_features(run.event_id)

    # Check if primary tickets are available
    if remaining_primary_tickets > 0:
        run.status["primary"] = True

        # Show urgency warning when tickets are running low
        percentage_threshold_for_urgency = 0.3
        absolute_threshold_for_urgency = 10
        if (
            remaining_primary_tickets < absolute_threshold_for_urgency
            or remaining_primary_tickets * 1.0 / run.event.max_pg < percentage_threshold_for_urgency
        ):
            run.status["count"] = remaining_primary_tickets
            run.status["additional"] = (
                _(" Hurry: only %(num)d tickets available") % {"num": remaining_primary_tickets} + "."
            )
        return

    # Check if filler tickets are available (fallback option)
    if "filler" in features and _available_filler(run, registration_counts):
        return

    # Check if waiting list is available (last resort option)
    if "waiting" in features and _available_waiting(run, registration_counts):
        return

    # No registration options available - mark as closed
    run.status["closed"] = True
    return


def _available_waiting(registration: Registration, registration_counts: dict) -> bool:
    """Check if waiting list spots are available for a registration.

    Args:
        registration: Registration object with event and status attributes
        registration_counts: Dictionary containing registration counts including 'count_wait'

    Returns:
        bool: True if waiting list spots are available, False otherwise

    Side Effects:
        Modifies registration.status dictionary with waiting availability information

    """
    # Handle infinite waiting list capacity
    if registration.event.max_waiting == 0:
        registration.status["waiting"] = True
        registration.status["count"] = None  # Infinite
        return True

    # Check if limited waiting list has available spots
    if registration.event.max_waiting > 0:
        # Calculate remaining waiting list capacity
        remaining_waiting_spots = registration.event.max_waiting - registration_counts["count_wait"]

        # Set status if spots are available
        if remaining_waiting_spots > 0:
            registration.status["waiting"] = True
            registration.status["count"] = remaining_waiting_spots
            registration.status["additional"] = (
                _(" Hurry: only %(num)d tickets available") % {"num": remaining_waiting_spots} + "."
            )
            return True

    # No waiting list spots available
    return False


def _available_filler(registration, registration_counts) -> bool:
    """Check if filler tickets are available for the given registration.

    Args:
        registration: Registration object with event and status attributes
        registration_counts: Dictionary containing registration counts including 'count_fill'

    Returns:
        bool: True if filler tickets are available, False otherwise

    Side Effects:
        Modifies registration.status dictionary with filler availability information

    """
    # Handle infinite filler tickets case
    if registration.event.max_filler == 0:
        registration.status["filler"] = True
        registration.status["count"] = None  # Infinite
        return True

    # Handle limited filler tickets case
    if registration.event.max_filler > 0:
        # Calculate remaining filler tickets
        remaining_filler = registration.event.max_filler - registration_counts["count_fill"]

        # Check if any filler tickets are still available
        if remaining_filler > 0:
            registration.status["filler"] = True
            registration.status["count"] = remaining_filler
            # Add urgency message for limited availability
            registration.status["additional"] = (
                _(" Hurry: only %(num)d tickets available") % {"num": remaining_filler} + "."
            )
            return True

    # No filler tickets available
    return False


def get_match_reg(r: Run, my_regs: list[Registration]) -> Registration | None:
    """Find registration matching the given run ID.

    Args:
        r: Run object to match against
        my_regs: List of registration objects to search

    Returns:
        Matching registration or None if not found

    """
    # Iterate through registrations to find matching run
    for m in my_regs:
        if m and m.run_id == r.id:
            return m
    return None


def registration_status_signed(
    run: Run,
    reg: Registration,
    member: Member,
    features: dict[str, Any],
    register_url: str,
    context: dict | None = None,
) -> None:
    """Update the registration status for a signed user based on membership and payment features.

    Args:
        run: The run object containing event and status information
        reg: The registration object with ticket and user details
        member: The member object for the registered user
        features: Dictionary of enabled features for the event
        register_url: URL for the registration page
        context: Optional context dictionary containing cached data:
            - character_rels_dict: Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects
            - payment_invoices_dict: Dictionary mapping registration IDs to lists of PaymentInvoice objects

    Returns:
        None: Updates run.status["text"] in place

    Raises:
        RewokedMembershipError: When membership status is revoked

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    # Initialize character registration status for the run
    registration_status_characters(run, features, context)

    # Get user membership for the event's association
    user_membership = get_user_membership(member, run.event.association_id)

    # Build base registration message with ticket info if available
    registration_message = _("Registration confirmed")
    is_provisional = is_reg_provisional(reg, features=features, event=run.event, context=context)

    # Update message for provisional registrations
    if is_provisional:
        registration_message = _("Provisional registration")

    # Append ticket name if ticket exists
    if reg.ticket:
        registration_message += f" ({reg.ticket.name})"
    registration_text = f"<a href='{register_url}'>{registration_message}</a>"

    # Handle membership feature requirements and status checks
    if "membership" in features:
        # Check for revoked membership status and raise error
        if user_membership.status in [MembershipStatus.REWOKED]:
            raise RewokedMembershipError()

        # Handle incomplete membership applications (empty, joined, uploaded)
        if user_membership.status in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
            membership_url = reverse("membership")
            completion_message = _("please upload your membership application to proceed") + "."
            text_url = f", <a href='{membership_url}'>{completion_message}</a>"
            run.status["text"] = registration_text + text_url
            return

        # Handle pending membership approval (submitted but not approved)
        if user_membership.status in [MembershipStatus.SUBMITTED]:
            run.status["text"] = registration_text + ", " + _("awaiting member approval to proceed with payment")
            return

    # Handle payment feature processing and related status updates
    if "payment" in features:
        # Process payment status and return if payment handling is complete
        if _status_payment(registration_text, run, context):
            return

    # Check for incomplete user profile and prompt completion
    if not user_membership.compiled:
        profile_url = reverse("profile")
        completion_message = _("please fill in your profile") + "."
        text_url = f", <a href='{profile_url}'>{completion_message}</a>"
        run.status["text"] = registration_text + text_url
        return

    # Handle provisional registration status (no further action needed)
    if is_provisional:
        run.status["text"] = registration_text
        return

    # Set final confirmed registration status for completed registrations
    run.status["text"] = registration_text

    # Add patron appreciation message for patron tier tickets
    if reg.ticket and reg.ticket.tier == TicketTier.PATRON:
        run.status["text"] += " " + _("Thanks for your support") + "!"


def _status_payment(register_text: str, run: Run, context: dict | None = None) -> bool:
    """Check payment status and update registration status text accordingly.

    Handles pending payments, wire transfers, and payment alerts with
    appropriate messaging and links to payment processing pages.

    Args:
        register_text: Base registration status text to append to
        run: Registration run object containing registration and status info
        context: Optional context dictionary containing cached data:
            - payment_invoices_dict: Dictionary mapping registration IDs to lists of PaymentInvoice objects

    Returns:
        True if payment status was processed and status text updated, False otherwise

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    payment_invoices_dict = context.get("payment_invoices_dict")

    # Get payment invoices for this registration
    if payment_invoices_dict is not None:
        invoices = payment_invoices_dict.get(run.reg.id, [])
        # Filter for pending payments
        pending_invoices = [
            invoice
            for invoice in invoices
            if invoice.status == PaymentStatus.SUBMITTED and invoice.typ == PaymentType.REGISTRATION
        ]
        # Filter for wire transfer payments
        wire_created_invoices = [
            invoice
            for invoice in invoices
            if invoice.status == PaymentStatus.CREATED
            and invoice.typ == PaymentType.REGISTRATION
            and hasattr(invoice, "method")
            and invoice.method
            and invoice.method.slug == "wire"
        ]
    else:
        # Fallback to database queries if no precalculated data available
        pending_invoices = list(
            PaymentInvoice.objects.filter(
                idx=run.reg.id,
                member_id=run.reg.member_id,
                status=PaymentStatus.SUBMITTED,
                typ=PaymentType.REGISTRATION,
            )
        )
        wire_created_invoices = list(
            PaymentInvoice.objects.filter(
                idx=run.reg.id,
                member_id=run.reg.member_id,
                status=PaymentStatus.CREATED,
                typ=PaymentType.REGISTRATION,
                method__slug="wire",
            )
        )

    # Handle pending payment status
    if pending_invoices:
        run.status["text"] = register_text + ", " + _("payment pending confirmation")
        return True

    # Process payment alerts for unpaid registrations
    if run.reg.alert:
        # Handle wire transfer specific messaging
        if wire_created_invoices:
            payment_url = reverse("acc_reg", args=[run.reg.id])
            message = _("to confirm it proceed with payment") + "."
            text_url = f", <a href='{payment_url}'>{message}</a>"
            note = _("If you have made a transfer, please upload the receipt for it to be processed") + "!"
            run.status["text"] = f"{register_text}{text_url} ({note})"
            return True

        # Handle general payment alert with deadline warning
        payment_url = reverse("acc_reg", args=[run.reg.id])
        message = _("to confirm it proceed with payment") + "."
        text_url = f", <a href='{payment_url}'>{message}</a>"

        # Add cancellation warning if deadline passed
        if run.reg.deadline < 0:
            text_url += "<i> (" + _("If no payment is received, registration may be cancelled") + ")</i>"

        run.status["text"] = register_text + text_url
        return True

    return False


def registration_status(
    run: Run,
    member: Member,
    context: dict,
) -> None:
    """Determine registration status and availability for users.

    Checks registration constraints, deadlines, and feature requirements
    to determine if a user can register for an event.

    Args:
        run: Event run object to check registration status for
        member: Member object attempting registration
        context: Dict context dictionary, optionally containing cached data for efficiency:
            - my_regs: Pre-filtered user registrations
            - features_map: Cached features mapping
            - reg_counts: Pre-calculated registration counts dictionary
            - character_rels_dict: Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects
            - payment_invoices_dict: Dictionary mapping registration IDs to lists of PaymentInvoice objects
            - pre_registrations_dict: Dictionary mapping event IDs to PreRegistration objects

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    run.status = {"open": True, "details": "", "text": "", "additional": ""}

    registration_find(run, member, context)

    features = _get_features_map(run, context)

    registration_available(run, features, context)
    register_url = reverse("register", args=[run.get_slug()])

    if member:
        membership = context["membership"]
        if membership.status in [MembershipStatus.REWOKED]:
            return

        if run.reg:
            registration_status_signed(run, run.reg, member, features, register_url, context)
            return

    if run.end and get_time_diff_today(run.end) < 0:
        return

    # check pre-register
    if get_event_config(run.event_id, "pre_register_active", False, context=context):
        _status_preregister(run, member, context)

    current_datetime = datetime.today()
    # check registration open
    if "registration_open" in features:
        if not run.registration_open:
            run.status["open"] = False
            run.status["text"] = run.status.get("text") or _("Registrations not open") + "!"
            return
        if run.registration_open > current_datetime:
            run.status["open"] = False
            run.status["text"] = run.status.get("text") or _("Registrations not open") + "!"
            run.status["details"] = _("Opening at: %(date)s") % {
                "date": run.registration_open.strftime(format_datetime)
            }
            return

    # signup open, not already signed in
    status = run.status
    messages = {
        "primary": _("Registration is open!"),
        "filler": _("Sign up as a filler!"),
        "waiting": _("Join the waiting list!"),
    }

    # pick the first matching message (or None)
    selected_message = next((msg for key, msg in messages.items() if key in status), None)

    # if it's a primary/filler, copy over the additional details
    if selected_message and any(key in status for key in ("primary", "filler")):
        status["details"] = status["additional"]

    # wrap in a link if we have a message, otherwise show closed
    status["text"] = (
        f"<a href='{register_url}'>{selected_message}</a>" if selected_message else _("Registration closed") + "."
    )


def _status_preregister(run: Run, member: Member, context: dict | None = None) -> None:
    """Update run status based on user's pre-registration state.

    Sets the run status text to either confirm existing pre-registration
    or provide a link to pre-register for the event.

    Args:
        run: Event run object to update status for
        member: Member object to check pre-registration status
        context: Optional context dictionary containing cached pre-registration data

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    # Get cached pre-registrations dictionary from context
    pre_registrations_dict = context.get("pre_registrations_dict")

    # Check if user already has a pre-registration for this event
    has_pre_registration = False
    if member:
        # Use cached data if available, otherwise query database
        if pre_registrations_dict is not None:
            # Use cached data if available
            has_pre_registration = run.event_id in pre_registrations_dict
        else:
            # Fallback to database query if no cache provided
            has_pre_registration = PreRegistration.objects.filter(
                event_id=run.event_id, member=member, deleted__isnull=True
            ).exists()

    # Set status message based on pre-registration state
    if has_pre_registration:
        status_message = _("Pre-registration confirmed") + "!"
        run.status["text"] = status_message
    else:
        # Create pre-registration link for unauthenticated or non-pre-registered users
        status_message = _("Pre-register to the event") + "!"
        preregister_url = reverse("pre_register", args=[run.event.slug])
        run.status["text"] = f"<a href='{preregister_url}'>{status_message}</a>"


def _get_features_map(run: Run, context: dict):
    """Get features map from context or create it if not available.

    Args:
        run: Run object to get features for
        context: Context dictionary that may contain 'features_map'

    Returns:
        dict: Features dictionary for the run's event

    """
    if context is None:
        context = {}

    features_map = context.get("features_map")
    if features_map is None:
        features_map = {}
    if run.event_id not in features_map:
        features_map[run.event_id] = get_event_features(run.event_id)
    return features_map[run.event_id]


def registration_find(run: Run, member: Member, context: dict | None = None):
    """Find and attach registration for a user to a run.

    Searches for an active registration (non-cancelled, non-redeemed) for the given
    user and run. Sets run.reg to the found registration or None if not found.

    Args:
        run: The Run object to find registration for
        member: The Member object to search registration for
        context: Optional context dictionary containing cached data:
            - my_regs: Pre-fetched registrations queryset for performance optimization

    Returns:
        None: Function modifies run.reg attribute in-place

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    # Early return if user is not authenticated
    if not member:
        run.reg = None
        return

    # Use pre-fetched registrations if provided
    cached_registrations = context.get("my_regs")
    if cached_registrations is not None:
        run.reg = cached_registrations.get(run.id)
        return

    # Query database for active registration (non-cancelled, non-redeemed)
    try:
        registration_queryset = Registration.objects.select_related("ticket")
        run.reg = registration_queryset.get(
            run=run, member=member, redeem_code__isnull=True, cancellation_date__isnull=True
        )
    except ObjectDoesNotExist:
        # No active registration found for this user and run
        run.reg = None


def check_character_maximum(event, member) -> tuple[bool, int]:
    """Check if member has reached the maximum character limit for an event.

    Args:
        event: The event to check character limits for
        member: The member whose character count to verify

    Returns:
        Tuple of (has_reached_limit, max_allowed_characters)

    """
    # Get all characters for this member in the event
    characters = event.get_elements(Character).filter(player=member)

    # Get IDs of inactive characters (those with CharacterConfig inactive=True)
    inactive_character_ids = CharacterConfig.objects.filter(
        character__in=characters, name="inactive", value="True"
    ).values_list("character_id", flat=True)

    # Count only active characters (exclude inactive ones)
    current_character_count = characters.exclude(id__in=inactive_character_ids).count()

    # Get the maximum allowed characters from event configuration
    maximum_characters_allowed = int(get_event_config(event.id, "user_character_max", 0))

    # Return whether limit is reached and the maximum allowed
    return current_character_count >= maximum_characters_allowed, maximum_characters_allowed


def registration_status_characters(run: Run, features: dict, context: dict | None = None) -> None:
    """Update registration status with character assignment information.

    Displays assigned characters with approval status and provides links
    for character creation or selection based on event configuration.

    Args:
        run: The run object containing registration information
        features: Dictionary of enabled event features
        context: Optional context dictionary containing cached data:
            - character_rels_dict: Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects

    Returns:
        None: Function modifies run.status["details"] in place

    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    character_rels_dict = context.get("character_rels_dict")

    # Get character relationships either from provided dict or database query
    if character_rels_dict is not None:
        registration_character_rels = character_rels_dict.get(run.reg.id, [])
    else:
        query = RegistrationCharacterRel.objects.filter(reg_id=run.reg.id)
        registration_character_rels = query.order_by("character__number").select_related("character")

    # Check if character approval is required for this event
    approval_required = get_event_config(run.event_id, "user_character_approval", False, context=context)

    # Build list of character links with names and approval status
    character_links = []
    for character_rel in registration_character_rels:
        character_url = reverse("character", args=[run.get_slug(), character_rel.character.number])
        character_name = character_rel.character.name

        # Use custom name if provided
        if character_rel.custom_name:
            character_name = character_rel.custom_name

        # Add approval status if character approval is enabled and not approved
        if approval_required and character_rel.character.status != CharacterStatus.APPROVED:
            character_name += f" ({_(character_rel.character.get_status_display())})"

        # Create clickable link for character
        character_url = f"<a href='{character_url}'>{character_name}</a>"
        character_links.append(character_url)

    # Add character information to status details based on number of characters
    if len(character_links) == 1:
        run.status["details"] += _("Your character is") + " " + character_links[0]
    elif len(character_links) > 1:
        run.status["details"] += _("Your characters are") + ": " + ", ".join(character_links)

    _status_approval(character_links, features, run)


def _status_approval(is_character_assigned: bool, features: dict, run: Any) -> None:
    """Add character creation/selection links to run status based on feature availability.

    This function checks if the user_character feature is enabled and the registration
    is not on a waiting list, then adds appropriate character creation or selection
    links to the run status details.

    Args:
        is_character_assigned: Boolean indicating if character is already assigned
        features: Dictionary of enabled features for the event
        run: Run object containing registration and event information

    Returns:
        None: Modifies run.status["details"] in place

    """
    # Check if user_character feature is enabled
    if "user_character" not in features:
        return

    # Skip if registration is on waiting list
    if run.reg.ticket and run.reg.ticket.tier == TicketTier.WAITING:
        return

    # Get character creation limits for this user and event
    can_create_character, maximum_characters = check_character_maximum(run.event, run.reg.member)

    # Show character creation link if user can create more characters
    if not can_create_character:
        url = reverse("character_create", args=[run.get_slug()])
        if run.status["details"]:
            run.status["details"] += " - "
        message = _("Access character creation!")
        run.status["details"] += f"<a href='{url}'>{message}</a>"

    # Show character selection link if no characters assigned but max chars available
    elif not is_character_assigned and maximum_characters:
        url = reverse("character_list", args=[run.get_slug()])
        if run.status["details"]:
            run.status["details"] += " - "
        message = _("Select your character!")
        run.status["details"] += f"<a href='{url}'>{message}</a>"


def get_registration_options(instance) -> list[tuple[str, str]]:
    """Get formatted list of registration options and answers for display.

    This function retrieves all registration questions for a given event run,
    filters out skipped questions based on features, and returns the answers
    in a formatted list of question-answer pairs.

    Args:
        instance: Registration instance containing the run and event information.

    Returns:
        List of tuples where each tuple contains:
            - question_name (str): The name of the registration question
            - answer_text (str): The formatted answer text (comma-separated for choices)

    Note:
        Questions are filtered based on event features and individual skip conditions.
        Choice questions are formatted as comma-separated option names.

    """
    formatted_results = []
    applicable_questions = []
    question_ids_cache = []

    # Get event features and filter applicable questions
    event_features = get_event_features(instance.run.event_id)
    for question in RegistrationQuestion.get_instance_questions(instance.run.event, event_features):
        if question.skip(instance, event_features):
            continue
        applicable_questions.append(question)
        question_ids_cache.append(question.id)

    # Fetch text answers for all relevant questions
    text_answers_by_question = {}
    for answer in RegistrationAnswer.objects.filter(question_id__in=question_ids_cache, reg=instance):
        text_answers_by_question[answer.question_id] = answer.text

    # Fetch choice answers and group by question
    choice_options_by_question = {}
    for choice in RegistrationChoice.objects.filter(question_id__in=question_ids_cache, reg=instance).select_related(
        "option"
    ):
        if choice.question_id not in choice_options_by_question:
            choice_options_by_question[choice.question_id] = []
        choice_options_by_question[choice.question_id].append(choice.option)

    # Build result list with question names and formatted answers
    if len(applicable_questions) > 0:
        for question in applicable_questions:
            # Handle multiple choice questions
            if question.id in choice_options_by_question:
                formatted_choices = ",".join([option.name for option in choice_options_by_question[question.id]])
                formatted_results.append((question.name, formatted_choices))

            # Handle text answer questions
            if question.id in text_answers_by_question:
                formatted_results.append((question.name, text_answers_by_question[question.id]))

    return formatted_results


def get_player_characters(member: Member, event: Event) -> QuerySet[Character]:
    """Get all characters a player has for an event, ordered by most recently updated."""
    return event.get_elements(Character).filter(player=member).order_by("-updated")


def get_player_signup(request: HttpRequest, context: dict) -> Registration | None:
    """Get active registration for current user in the given run context."""
    # Filter registrations for current run and user, excluding cancelled ones
    active_registrations = Registration.objects.filter(
        run=context["run"], member=context["member"], cancellation_date__isnull=True
    )

    # Return first registration if exists
    if active_registrations:
        return active_registrations[0]

    return None


def check_signup(request: HttpRequest, context: dict) -> None:
    """Check if player signup is valid and not in waiting status.

    Args:
        request: HTTP request object
        context: Context dictionary containing run information

    Raises:
        SignupError: If no valid signup found
        WaitingError: If signup ticket is in waiting tier

    """
    # Get player registration for current run
    registration = get_player_signup(request, context)
    if not registration:
        raise SignupError(context["run"].get_slug())

    # Check if registration is in waiting list
    if registration.ticket and registration.ticket.tier == TicketTier.WAITING:
        raise WaitingError(context["run"].get_slug())


def check_assign_character(request: HttpRequest, context: dict) -> None:
    """Check and assign a character to player signup if conditions are met.

    Automatically assigns the first available character to a player's signup
    if they have exactly one character and no existing character assignments.

    Args:
        request: HTTP request object containing user information
        context: Context dictionary containing event data

    Returns:
        None: Function performs side effects only

    """
    # Get the player's registration for this event
    registration = get_player_signup(request, context)
    if not registration:
        return

    # Skip if player already has character assignments
    if registration.rcrs.exists():
        return

    # Get all characters belonging to this player for the event
    characters = get_player_characters(context["member"], context["event"])
    if not characters:
        return

    # Get IDs of inactive characters (those with CharacterConfig inactive=True)
    character_ids = [char.id for char in characters]
    inactive_character_ids = set(
        CharacterConfig.objects.filter(character_id__in=character_ids, name="inactive", value="True").values_list(
            "character_id", flat=True
        )
    )

    # Filter out inactive characters
    active_characters = [char for char in characters if char.id not in inactive_character_ids]
    if not active_characters:
        return

    # Auto-assign the first active character to the registration
    RegistrationCharacterRel.objects.create(character_id=active_characters[0].id, reg=registration)


def get_reduced_available_count(run) -> int:
    """Calculate remaining reduced ticket slots based on patron registrations and ratio.

    Args:
        run: Run object to calculate reduced tickets for

    Returns:
        Number of reduced tickets still available

    """
    # Get the ratio for reduced tickets per patron registrations
    reduced_tickets_per_patron_ratio = int(get_event_config(run.event_id, "reduced_ratio", 10))

    # Count current reduced and patron registrations (excluding cancelled)
    reduced_registrations_count = Registration.objects.filter(
        run=run, ticket__tier=TicketTier.REDUCED, cancellation_date__isnull=True
    ).count()
    patron_registrations_count = Registration.objects.filter(
        run=run, ticket__tier=TicketTier.PATRON, cancellation_date__isnull=True
    ).count()
    # silv = Registration.objects.filter(run=run, ticket__tier=RegistrationTicket.SILVER).count()

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
    if previous_registration.run.event_id == registration.run.event_id:
        return

    # Attempt to find a matching ticket in the new event by name
    # This preserves the ticket assignment when moving between events
    ticket_name = registration.ticket.name
    try:
        registration.ticket = registration.run.event.get_elements(RegistrationTicket).get(name__iexact=ticket_name)
    except ObjectDoesNotExist:
        registration.ticket = None

    # Process all registration choices (question/option pairs)
    # Try to find matching questions and options in the new event
    for registration_choice in RegistrationChoice.objects.filter(reg=registration):
        question_name = registration_choice.question.name
        option_name = registration_choice.option.name

        try:
            # Find matching question and option in the new event
            registration_choice.question = registration.run.event.get_elements(RegistrationQuestion).get(
                name__iexact=question_name
            )
            registration_choice.option = registration.run.event.get_elements(RegistrationOption).get(
                question=registration_choice.question, name__iexact=option_name
            )
            registration_choice.save()
        except ObjectDoesNotExist:
            # Clear the choice if no matching question/option found
            registration_choice.question = None
            registration_choice.option = None

    # Process all registration answers (free-form question responses)
    # Attempt to preserve answers by finding matching questions
    for registration_answer in RegistrationAnswer.objects.filter(reg=registration):
        question_name = registration_answer.question.name

        try:
            # Find matching question in the new event to preserve the answer
            registration_answer.question = registration.run.event.get_elements(RegistrationQuestion).get(
                name__iexact=question_name
            )
            registration_answer.save()
        except ObjectDoesNotExist:
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
    for writing_choice in WritingChoice.objects.filter(element_id=character.id):
        # Get list of ticket IDs that allow this writing option
        allowed_ticket_ids = writing_choice.option.tickets.values_list("pk", flat=True)

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

    # Get the event from the registration run
    event = instance.run.event

    # Process ticket options for characters directly linked to this registration
    for character in instance.characters.all():
        check_character_ticket_options(instance, character)

    # Process ticket options for all characters owned by the member in this event
    for character in event.get_elements(Character).filter(player=instance.member):
        check_character_ticket_options(instance, character)
