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

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.config import get_event_config
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.registration import get_reg_counts
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.models.event import PreRegistration, Run
from larpmanager.models.form import (
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingChoice,
)
from larpmanager.models.member import Member, MembershipStatus, get_user_membership
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.common import format_datetime, get_time_diff_today
from larpmanager.utils.exceptions import RewokedMembershipError, SignupError, WaitingError


def registration_available(run: Run, features: dict, ctx: dict | None = None) -> None:
    """Check if registration is available based on capacity and rules.

    Validates registration availability considering maximum participants,
    ticket quotas, and advanced registration constraints. Updates the run's
    status dictionary with availability information.

    Args:
        run: The run object containing event and status information
        features: Dictionary of enabled features for the event
        ctx: Optional context dictionary containing cached data

    Returns:
        None: Function modifies run.status in-place
    """
    # Extract values from context dictionary if provided
    if ctx is None:
        ctx = {}

    # Skip advanced registration rules if no maximum participant limit is set
    if run.event.max_pg == 0:
        run.status["primary"] = True
        return

    # Get registration counts if not provided
    reg_counts = ctx.get("reg_counts")
    if reg_counts is None:
        reg_counts = get_reg_counts(run)

    # Calculate remaining primary tickets
    remaining_pri = run.event.max_pg - reg_counts.get("count_player", 0)

    # Get event features if not provided
    if not features:
        features = get_event_features(run.event_id)

    # Check if primary tickets are available
    if remaining_pri > 0:
        run.status["primary"] = True

        # Show urgency warning when tickets are running low
        perc_signed = 0.3
        max_signed = 10
        if remaining_pri < max_signed or remaining_pri * 1.0 / run.event.max_pg < perc_signed:
            run.status["count"] = remaining_pri
            run.status["additional"] = _(" Hurry: only %(num)d tickets available") % {"num": remaining_pri} + "."
        return

    # Check if filler tickets are available (fallback option)
    if "filler" in features and _available_filler(run, reg_counts):
        return

    # Check if waiting list is available (last resort option)
    if "waiting" in features and _available_waiting(run, reg_counts):
        return

    # No registration options available - mark as closed
    run.status["closed"] = True
    return


def _available_waiting(r: Registration, reg_counts: dict) -> bool:
    """Check if waiting list spots are available for a registration.

    Args:
        r: Registration object with event and status attributes
        reg_counts: Dictionary containing registration counts including 'count_wait'

    Returns:
        bool: True if waiting list spots are available, False otherwise

    Side Effects:
        Modifies r.status dictionary with waiting availability information
    """
    # Handle infinite waiting list capacity
    if r.event.max_waiting == 0:
        r.status["waiting"] = True
        r.status["count"] = None  # Infinite
        return True

    # Check if limited waiting list has available spots
    if r.event.max_waiting > 0:
        # Calculate remaining waiting list capacity
        remaining_waiting = r.event.max_waiting - reg_counts["count_wait"]

        # Set status if spots are available
        if remaining_waiting > 0:
            r.status["waiting"] = True
            r.status["count"] = remaining_waiting
            r.status["additional"] = _(" Hurry: only %(num)d tickets available") % {"num": remaining_waiting} + "."
            return True

    # No waiting list spots available
    return False


def _available_filler(r, reg_counts) -> bool:
    """Check if filler tickets are available for the given registration.

    Args:
        r: Registration object with event and status attributes
        reg_counts: Dictionary containing registration counts including 'count_fill'

    Returns:
        bool: True if filler tickets are available, False otherwise

    Side Effects:
        Modifies r.status dictionary with filler availability information
    """
    # Handle infinite filler tickets case
    if r.event.max_filler == 0:
        r.status["filler"] = True
        r.status["count"] = None  # Infinite
        return True

    # Handle limited filler tickets case
    if r.event.max_filler > 0:
        # Calculate remaining filler tickets
        remaining_filler = r.event.max_filler - reg_counts["count_fill"]

        # Check if any filler tickets are still available
        if remaining_filler > 0:
            r.status["filler"] = True
            r.status["count"] = remaining_filler
            # Add urgency message for limited availability
            r.status["additional"] = _(" Hurry: only %(num)d tickets available") % {"num": remaining_filler} + "."
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
    ctx: dict | None = None,
) -> None:
    """
    Updates the registration status for a signed user based on membership and payment features.

    Args:
        run: The run object containing event and status information
        reg: The registration object with ticket and user details
        member: The member object for the registered user
        features: Dictionary of enabled features for the event
        register_url: URL for the registration page
        ctx: Optional context dictionary containing cached data:
            - character_rels_dict: Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects
            - payment_invoices_dict: Dictionary mapping registration IDs to lists of PaymentInvoice objects

    Returns:
        None: Updates run.status["text"] in place

    Raises:
        RewokedMembershipError: When membership status is revoked
    """
    # Extract values from context dictionary if provided
    if ctx is None:
        ctx = {}

    # Initialize character registration status for the run
    registration_status_characters(run, features, ctx)

    # Get user membership for the event's association
    mb = get_user_membership(member, run.event.assoc_id)

    # Build base registration message with ticket info if available
    register_msg = _("Registration confirmed")
    provisional = is_reg_provisional(reg, features=features, event=run.event, ctx=ctx)

    # Update message for provisional registrations
    if provisional:
        register_msg = _("Provisional registration")

    # Append ticket name if ticket exists
    if reg.ticket:
        register_msg += f" ({reg.ticket.name})"
    register_text = f"<a href='{register_url}'>{register_msg}</a>"

    # Handle membership feature requirements and status checks
    if "membership" in features:
        # Check for revoked membership status and raise error
        if mb.status in [MembershipStatus.REWOKED]:
            raise RewokedMembershipError()

        # Handle incomplete membership applications (empty, joined, uploaded)
        if mb.status in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
            membership_url = reverse("membership")
            mes = _("please upload your membership application to proceed") + "."
            text_url = f", <a href='{membership_url}'>{mes}</a>"
            run.status["text"] = register_text + text_url
            return

        # Handle pending membership approval (submitted but not approved)
        if mb.status in [MembershipStatus.SUBMITTED]:
            run.status["text"] = register_text + ", " + _("awaiting member approval to proceed with payment")
            return

    # Handle payment feature processing and related status updates
    if "payment" in features:
        # Process payment status and return if payment handling is complete
        if _status_payment(register_text, run, ctx):
            return

    # Check for incomplete user profile and prompt completion
    if not mb.compiled:
        profile_url = reverse("profile")
        mes = _("please fill in your profile") + "."
        text_url = f", <a href='{profile_url}'>{mes}</a>"
        run.status["text"] = register_text + text_url
        return

    # Handle provisional registration status (no further action needed)
    if provisional:
        run.status["text"] = register_text
        return

    # Set final confirmed registration status for completed registrations
    run.status["text"] = register_text

    # Add patron appreciation message for patron tier tickets
    if reg.ticket and reg.ticket.tier == TicketTier.PATRON:
        run.status["text"] += " " + _("Thanks for your support") + "!"


def _status_payment(register_text: str, run: Run, ctx: dict | None = None) -> bool:
    """Check payment status and update registration status text accordingly.

    Handles pending payments, wire transfers, and payment alerts with
    appropriate messaging and links to payment processing pages.

    Args:
        register_text: Base registration status text to append to
        run: Registration run object containing registration and status info
        ctx: Optional context dictionary containing cached data:
            - payment_invoices_dict: Dictionary mapping registration IDs to lists of PaymentInvoice objects

    Returns:
        True if payment status was processed and status text updated, False otherwise
    """
    # Extract values from context dictionary if provided
    if ctx is None:
        ctx = {}

    payment_invoices_dict = ctx.get("payment_invoices_dict")

    # Get payment invoices for this registration
    if payment_invoices_dict is not None:
        invoices = payment_invoices_dict.get(run.reg.id, [])
        # Filter for pending payments
        pending_invoices = [
            inv for inv in invoices if inv.status == PaymentStatus.SUBMITTED and inv.typ == PaymentType.REGISTRATION
        ]
        # Filter for wire transfer payments
        wire_created_invoices = [
            inv
            for inv in invoices
            if inv.status == PaymentStatus.CREATED
            and inv.typ == PaymentType.REGISTRATION
            and hasattr(inv, "method")
            and inv.method
            and inv.method.slug == "wire"
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
            pay_url = reverse("acc_reg", args=[run.reg.id])
            mes = _("to confirm it proceed with payment") + "."
            text_url = f", <a href='{pay_url}'>{mes}</a>"
            note = _("If you have made a transfer, please upload the receipt for it to be processed") + "!"
            run.status["text"] = f"{register_text}{text_url} ({note})"
            return True

        # Handle general payment alert with deadline warning
        pay_url = reverse("acc_reg", args=[run.reg.id])
        mes = _("to confirm it proceed with payment") + "."
        text_url = f", <a href='{pay_url}'>{mes}</a>"

        # Add cancellation warning if deadline passed
        if run.reg.deadline < 0:
            text_url += "<i> (" + _("If no payment is received, registration may be cancelled") + ")</i>"

        run.status["text"] = register_text + text_url
        return True

    return False


def registration_status(
    run: Run,
    user: User,
    ctx: dict | None = None,
) -> None:
    """Determine registration status and availability for users.

    Checks registration constraints, deadlines, and feature requirements
    to determine if a user can register for an event.

    Args:
        run: Event run object to check registration status for
        user: User object attempting registration
        ctx: Optional context dictionary containing cached data for efficiency:
            - my_regs: Pre-filtered user registrations
            - features_map: Cached features mapping
            - reg_counts: Pre-calculated registration counts dictionary
            - character_rels_dict: Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects
            - payment_invoices_dict: Dictionary mapping registration IDs to lists of PaymentInvoice objects
            - pre_registrations_dict: Dictionary mapping event IDs to PreRegistration objects
    """
    # Extract values from context dictionary if provided
    if ctx is None:
        ctx = {}

    run.status = {"open": True, "details": "", "text": "", "additional": ""}

    registration_find(run, user, ctx)

    features = _get_features_map(run, ctx)

    registration_available(run, features, ctx)
    register_url = reverse("register", args=[run.get_slug()])

    if user.is_authenticated:
        membership = get_user_membership(user.member, run.event.assoc_id)
        if membership.status in [MembershipStatus.REWOKED]:
            return

        if run.reg:
            registration_status_signed(run, run.reg, user.member, features, register_url, ctx)
            return

    if run.end and get_time_diff_today(run.end) < 0:
        return

    # check pre-register
    if get_event_config(run.event_id, "pre_register_active", False, ctx=ctx):
        _status_preregister(run, user, ctx)

    current_datetime = datetime.today()
    # check registration open
    if "registration_open" in features:
        if not run.registration_open:
            run.status["open"] = False
            run.status["text"] = run.status.get("text") or _("Registrations not open") + "!"
            return
        elif run.registration_open > current_datetime:
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


def _status_preregister(run, user, ctx: dict | None = None) -> None:
    """Update run status based on user's pre-registration state.

    Sets the run status text to either confirm existing pre-registration
    or provide a link to pre-register for the event.

    Args:
        run: Event run object to update status for
        user: User object to check pre-registration status
        ctx: Optional context dictionary containing cached pre-registration data
    """
    # Extract values from context dictionary if provided
    if ctx is None:
        ctx = {}

    # Get cached pre-registrations dictionary from context
    pre_registrations_dict = ctx.get("pre_registrations_dict")

    # Check if user already has a pre-registration for this event
    has_pre_registration = False
    if user.is_authenticated:
        # Use cached data if available, otherwise query database
        if pre_registrations_dict is not None:
            # Use cached data if available
            has_pre_registration = run.event_id in pre_registrations_dict
        else:
            # Fallback to database query if no cache provided
            has_pre_registration = PreRegistration.objects.filter(
                event_id=run.event_id, member=user.member, deleted__isnull=True
            ).exists()

    # Set status message based on pre-registration state
    if has_pre_registration:
        mes = _("Pre-registration confirmed") + "!"
        run.status["text"] = mes
    else:
        # Create pre-registration link for unauthenticated or non-pre-registered users
        mes = _("Pre-register to the event") + "!"
        preregister_url = reverse("pre_register", args=[run.event.slug])
        run.status["text"] = f"<a href='{preregister_url}'>{mes}</a>"


def _get_features_map(run: Run, ctx: dict):
    """Get features map from context or create it if not available.

    Args:
        run: Run object to get features for
        ctx: Context dictionary that may contain 'features_map'

    Returns:
        dict: Features dictionary for the run's event
    """
    if ctx is None:
        ctx = {}

    features_map = ctx.get("features_map")
    if features_map is None:
        features_map = {}
    if run.event_id not in features_map:
        features_map[run.event_id] = get_event_features(run.event_id)
    features = features_map[run.event_id]
    return features


def registration_find(run: Run, user: User, ctx: dict | None = None):
    """Find and attach registration for a user to a run.

    Searches for an active registration (non-cancelled, non-redeemed) for the given
    user and run. Sets run.reg to the found registration or None if not found.

    Args:
        run: The Run object to find registration for
        user: The User object to search registration for
        ctx: Optional context dictionary containing cached data:
            - my_regs: Pre-fetched registrations queryset for performance optimization

    Returns:
        None: Function modifies run.reg attribute in-place
    """
    # Extract values from context dictionary if provided
    if ctx is None:
        ctx = {}

    # Early return if user is not authenticated
    if not user.is_authenticated:
        run.reg = None
        return

    # Use pre-fetched registrations if provided
    my_regs = ctx.get("my_regs")
    if my_regs is not None:
        run.reg = my_regs.get(run.id)
        return

    # Query database for active registration (non-cancelled, non-redeemed)
    try:
        que = Registration.objects.select_related("ticket")
        run.reg = que.get(run=run, member=user.member, redeem_code__isnull=True, cancellation_date__isnull=True)
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
    # Count current characters for this member in the event
    current_character_count = event.get_elements(Character).filter(player=member).count()

    # Get the maximum allowed characters from event configuration
    maximum_characters_allowed = int(get_event_config(event.id, "user_character_max", 0))

    # Return whether limit is reached and the maximum allowed
    return current_character_count >= maximum_characters_allowed, maximum_characters_allowed


def registration_status_characters(run: Run, features: dict, ctx: dict | None = None) -> None:
    """Update registration status with character assignment information.

    Displays assigned characters with approval status and provides links
    for character creation or selection based on event configuration.

    Args:
        run: The run object containing registration information
        features: Dictionary of enabled event features
        ctx: Optional context dictionary containing cached data:
            - character_rels_dict: Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects

    Returns:
        None: Function modifies run.status["details"] in place
    """
    # Extract values from context dictionary if provided
    if ctx is None:
        ctx = {}

    character_rels_dict = ctx.get("character_rels_dict")

    # Get character relationships either from provided dict or database query
    if character_rels_dict is not None:
        rcrs = character_rels_dict.get(run.reg.id, [])
    else:
        que = RegistrationCharacterRel.objects.filter(reg_id=run.reg.id)
        rcrs = que.order_by("character__number").select_related("character")

    # Check if character approval is required for this event
    approval = get_event_config(run.event_id, "user_character_approval", False, ctx=ctx)

    # Build list of character links with names and approval status
    aux = []
    for el in rcrs:
        url = reverse("character", args=[run.get_slug(), el.character.number])
        name = el.character.name

        # Use custom name if provided
        if el.custom_name:
            name = el.custom_name

        # Add approval status if character approval is enabled and not approved
        if approval and el.character.status != CharacterStatus.APPROVED:
            name += f" ({_(el.character.get_status_display())})"

        # Create clickable link for character
        url = f"<a href='{url}'>{name}</a>"
        aux.append(url)

    # Add character information to status details based on number of characters
    if len(aux) == 1:
        run.status["details"] += _("Your character is") + " " + aux[0]
    elif len(aux) > 1:
        run.status["details"] += _("Your characters are") + ": " + ", ".join(aux)

    _status_approval(aux, features, run)


def _status_approval(aux: bool, features: dict, run: Any) -> None:
    """Add character creation/selection links to run status based on feature availability.

    This function checks if the user_character feature is enabled and the registration
    is not on a waiting list, then adds appropriate character creation or selection
    links to the run status details.

    Args:
        aux: Boolean indicating if character is already assigned
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
    check, max_chars = check_character_maximum(run.event, run.reg.member)

    # Show character creation link if user can create more characters
    if not check:
        url = reverse("character_create", args=[run.get_slug()])
        if run.status["details"]:
            run.status["details"] += " - "
        mes = _("Access character creation!")
        run.status["details"] += f"<a href='{url}'>{mes}</a>"

    # Show character selection link if no characters assigned but max chars available
    elif not aux and max_chars:
        url = reverse("character_list", args=[run.get_slug()])
        if run.status["details"]:
            run.status["details"] += " - "
        mes = _("Select your character!")
        run.status["details"] += f"<a href='{url}'>{mes}</a>"


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
    res = []
    rqs = []
    cache = []

    # Get event features and filter applicable questions
    features = get_event_features(instance.run.event_id)
    for q in RegistrationQuestion.get_instance_questions(instance.run.event, features):
        if q.skip(instance, features):
            continue
        rqs.append(q)
        cache.append(q.id)

    # Fetch text answers for all relevant questions
    answers = {}
    for el in RegistrationAnswer.objects.filter(question_id__in=cache, reg=instance):
        answers[el.question_id] = el.text

    # Fetch choice answers and group by question
    choices = {}
    for c in RegistrationChoice.objects.filter(question_id__in=cache, reg=instance).select_related("option"):
        if c.question_id not in choices:
            choices[c.question_id] = []
        choices[c.question_id].append(c.option)

    # Build result list with question names and formatted answers
    if len(rqs) > 0:
        for q in rqs:
            # Handle multiple choice questions
            if q.id in choices:
                txt = ",".join([opt.name for opt in choices[q.id]])
                res.append((q.name, txt))

            # Handle text answer questions
            if q.id in answers:
                res.append((q.name, answers[q.id]))

    return res


def get_player_characters(member, event):
    return event.get_elements(Character).filter(player=member).order_by("-updated")


def get_player_signup(request: HttpRequest, ctx: dict) -> Registration | None:
    """Get active registration for current user in the given run context."""
    # Filter registrations for current run and user, excluding cancelled ones
    regs = Registration.objects.filter(run=ctx["run"], member=request.user.member, cancellation_date__isnull=True)

    # Return first registration if exists
    if regs:
        return regs[0]

    return None


def check_signup(request: HttpRequest, ctx: dict) -> None:
    """Check if player signup is valid and not in waiting status.

    Args:
        request: HTTP request object
        ctx: Context dictionary containing run information

    Raises:
        SignupError: If no valid signup found
        WaitingError: If signup ticket is in waiting tier
    """
    # Get player registration for current run
    reg = get_player_signup(request, ctx)
    if not reg:
        raise SignupError(ctx["run"].get_slug())

    # Check if registration is in waiting list
    if reg.ticket and reg.ticket.tier == TicketTier.WAITING:
        raise WaitingError(ctx["run"].get_slug())


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
    characters = get_player_characters(request.user.member, context["event"])
    if not characters:
        return

    # Auto-assign the first character to the registration
    RegistrationCharacterRel.objects.create(character_id=characters[0].id, reg=registration)


def get_reduced_available_count(run) -> int:
    """Calculate remaining reduced ticket slots based on patron registrations and ratio.

    Args:
        run: Run object to calculate reduced tickets for

    Returns:
        Number of reduced tickets still available
    """
    # Get the ratio for reduced tickets per patron registrations
    ratio = int(get_event_config(run.event_id, "reduced_ratio", 10))

    # Count current reduced and patron registrations (excluding cancelled)
    red = Registration.objects.filter(run=run, ticket__tier=TicketTier.REDUCED, cancellation_date__isnull=True).count()
    pat = Registration.objects.filter(run=run, ticket__tier=TicketTier.PATRON, cancellation_date__isnull=True).count()
    # silv = Registration.objects.filter(run=run, ticket__tier=RegistrationTicket.SILVER).count()

    # Calculate available reduced slots: floor(patron_count * ratio / 10) - used_reduced
    return math.floor(pat * ratio / 10.0) - red


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
        prev = Registration.objects.get(pk=registration.pk)
    except ObjectDoesNotExist:
        return

    # Skip processing if the event hasn't actually changed
    if prev.run.event_id == registration.run.event_id:
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
    for choice in RegistrationChoice.objects.filter(reg=registration):
        question_name = choice.question.name
        option_name = choice.option.name

        try:
            # Find matching question and option in the new event
            choice.question = registration.run.event.get_elements(RegistrationQuestion).get(name__iexact=question_name)
            choice.option = registration.run.event.get_elements(RegistrationOption).get(
                question=choice.question, name__iexact=option_name
            )
            choice.save()
        except ObjectDoesNotExist:
            # Clear the choice if no matching question/option found
            choice.question = None
            choice.option = None

    # Process all registration answers (free-form question responses)
    # Attempt to preserve answers by finding matching questions
    for answer in RegistrationAnswer.objects.filter(reg=registration):
        question_name = answer.question.name

        try:
            # Find matching question in the new event to preserve the answer
            answer.question = registration.run.event.get_elements(RegistrationQuestion).get(name__iexact=question_name)
            answer.save()
        except ObjectDoesNotExist:
            # Clear the answer if no matching question found
            answer.question = None


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
    for char in instance.characters.all():
        check_character_ticket_options(instance, char)

    # Process ticket options for all characters owned by the member in this event
    for char in event.get_elements(Character).filter(player=instance.member):
        check_character_ticket_options(instance, char)
