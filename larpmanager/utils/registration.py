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
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.registration import get_reg_counts
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.models.form import (
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingChoice,
)
from larpmanager.models.member import MembershipStatus, get_user_membership
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.common import format_datetime, get_time_diff_today
from larpmanager.utils.exceptions import RewokedMembershipError, SignupError, WaitingError


def registration_available(run, features: dict | None = None, reg_counts: dict | None = None) -> None:
    """Check if registration is available based on capacity and rules.

    Validates registration availability considering maximum participants,
    ticket quotas, and advanced registration constraints. Updates the run's
    status dictionary with availability information.

    Args:
        run: The run object containing event and status information
        features: Optional dictionary of event features. If None, will be
            fetched using get_event_features()
        reg_counts: Optional dictionary of registration counts. If None,
            will be fetched using get_reg_counts()

    Returns:
        None: Function modifies run.status in-place
    """
    # Skip advanced registration rules if no maximum participant limit is set
    if run.event.max_pg == 0:
        run.status["primary"] = True
        return

    # Get registration counts if not provided
    if not reg_counts:
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


def _available_waiting(r, reg_counts):
    # infinite waitings
    if r.event.max_waiting == 0:
        r.status["waiting"] = True
        r.status["count"] = None  # Infinite
        return True

    # if we manage waiting and there are available, say so
    if r.event.max_waiting > 0:
        remaining_waiting = r.event.max_waiting - reg_counts["count_wait"]
        if remaining_waiting > 0:
            r.status["waiting"] = True
            r.status["count"] = remaining_waiting
            r.status["additional"] = _(" Hurry: only %(num)d tickets available") % {"num": remaining_waiting} + "."
            return True

    return False


def _available_filler(r, reg_counts):
    # infinite fillers
    if r.event.max_filler == 0:
        r.status["filler"] = True
        r.status["count"] = None  # Infinite
        return True

        # if we manage filler and there are available, say so
    if r.event.max_filler > 0:
        remaining_filler = r.event.max_filler - reg_counts["count_fill"]
        if remaining_filler > 0:
            r.status["filler"] = True
            r.status["count"] = remaining_filler
            r.status["additional"] = _(" Hurry: only %(num)d tickets available") % {"num": remaining_filler} + "."
            return True

    return False


def get_match_reg(r, my_regs):
    for m in my_regs:
        if m and m.run_id == r.id:
            return m
    return None


def registration_status_signed(run: Any, reg: Any, member: Any, features: dict[str, Any], register_url: str) -> None:
    """
    Updates the registration status for a signed user based on membership and payment features.

    Args:
        run: The run object containing event and status information
        reg: The registration object with ticket and user details
        member: The member object for the registered user
        features: Dictionary of enabled features for the event
        register_url: URL for the registration page

    Returns:
        None: Updates run.status["text"] in place

    Raises:
        RewokedMembershipError: When membership status is revoked
    """
    # Initialize character registration status for the run
    registration_status_characters(run, features)

    # Get user membership for the event's association
    mb = get_user_membership(member, run.event.assoc_id)

    # Build base registration message with ticket info if available
    register_msg = _("Registration confirmed")
    provisional = is_reg_provisional(reg, event=run.event)

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
        if _status_payment(register_text, run):
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


def _status_payment(register_text: str, run) -> bool:
    """Check payment status and update registration status text accordingly.

    Handles pending payments, wire transfers, and payment alerts with
    appropriate messaging and links to payment processing pages.

    Args:
        register_text: Base registration status text to append to
        run: Registration run object containing registration and status info

    Returns:
        True if payment status was processed and status text updated, False otherwise
    """
    # Check for pending payment confirmations
    pending = PaymentInvoice.objects.filter(
        idx=run.reg.id,
        member_id=run.reg.member_id,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.REGISTRATION,
    )

    # Handle pending payment status
    if pending.exists():
        run.status["text"] = register_text + ", " + _("payment pending confirmation")
        return True

    # Process payment alerts for unpaid registrations
    if run.reg.alert:
        # Check for created wire transfer payments
        wire_created = PaymentInvoice.objects.filter(
            idx=run.reg.id,
            member_id=run.reg.member_id,
            status=PaymentStatus.CREATED,
            typ=PaymentType.REGISTRATION,
            method__slug="wire",
        )

        # Handle wire transfer specific messaging
        if wire_created.exists():
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
    run, user, my_regs=None, features_map: dict | None = None, reg_count: int | None = None
) -> None:
    """Determine registration status and availability for users.

    Checks registration constraints, deadlines, and feature requirements
    to determine if a user can register for an event.

    Args:
        run: Event run object to check registration status for
        user: User object attempting registration
        my_regs (QuerySet, optional): Pre-filtered user registrations. Defaults to None.
        features_map (dict, optional): Cached features mapping. Defaults to None.
        reg_count (int, optional): Pre-calculated registration count. Defaults to None.
    """
    run.status = {"open": True, "details": "", "text": "", "additional": ""}

    registration_find(run, user, my_regs)

    features = _get_features_map(features_map, run)

    registration_available(run, features, reg_count)
    register_url = reverse("register", args=[run.get_slug()])

    if user.is_authenticated:
        mb = get_user_membership(user.member, run.event.assoc_id)
        if mb.status in [MembershipStatus.REWOKED]:
            return

        if run.reg:
            registration_status_signed(run, run.reg, user.member, features, register_url)
            return

    if run.end and get_time_diff_today(run.end) < 0:
        return

    # check pre-register
    if run.event.get_config("pre_register_active", False):
        mes = _("Pre-register to the event!")
        preregister_url = reverse("pre_register", args=[run.event.slug])
        run.status["text"] = f"<a href='{preregister_url}'>{mes}</a>"

    dt = datetime.today()
    # check registration open
    if "registration_open" in features:
        if not run.registration_open:
            run.status["open"] = False
            run.status["text"] = run.status.get("text") or _("Registrations not open") + "!"
            return
        elif run.registration_open > dt:
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
    mes = next((msg for key, msg in messages.items() if key in status), None)

    # if it's a primary/filler, copy over the additional details
    if mes and any(key in status for key in ("primary", "filler")):
        status["details"] = status["additional"]

    # wrap in a link if we have a message, otherwise show closed
    status["text"] = f"<a href='{register_url}'>{mes}</a>" if mes else _("Registration closed") + "."


def _get_features_map(features_map, run):
    if features_map is None:
        features_map = {}
    if run.event.slug not in features_map:
        features_map[run.event.slug] = get_event_features(run.event.id)
    features = features_map[run.event.slug]
    return features


def registration_find(run, user, my_regs=None):
    if not user.is_authenticated:
        run.reg = None
        return

    if my_regs is not None:
        run.reg = get_match_reg(run, my_regs)
        return

    try:
        que = Registration.objects.select_related("ticket")
        run.reg = que.get(run=run, member=user.member, redeem_code__isnull=True, cancellation_date__isnull=True)
    except ObjectDoesNotExist:
        run.reg = None


def check_character_maximum(event, member):
    # check the amount of characters of the character
    current_chars = event.get_elements(Character).filter(player=member).count()
    max_chars = int(event.get_config("user_character_max", 0))
    return current_chars >= max_chars, max_chars


def registration_status_characters(run, features):
    """Update registration status with character assignment information.

    Displays assigned characters with approval status and provides links
    for character creation or selection based on event configuration.
    """
    que = RegistrationCharacterRel.objects.filter(reg_id=run.reg.id)
    approval = run.event.get_config("user_character_approval", False)
    rcrs = que.order_by("character__number").select_related("character")

    aux = []
    for el in rcrs:
        url = reverse("character", args=[run.get_slug(), el.character.number])
        name = el.character.name
        if el.custom_name:
            name = el.custom_name
        if approval and el.character.status != CharacterStatus.APPROVED:
            name += f" ({_(el.character.get_status_display())})"
        url = f"<a href='{url}'>{name}</a>"
        aux.append(url)

    if len(aux) == 1:
        run.status["details"] += _("Your character is") + " " + aux[0]
    elif len(aux) > 1:
        run.status["details"] += _("Your characters are") + ": " + ", ".join(aux)

    reg_waiting = run.reg.ticket and run.reg.ticket.tier == TicketTier.WAITING

    if "user_character" in features and not reg_waiting:
        check, max_chars = check_character_maximum(run.event, run.reg.member)
        if not check:
            url = reverse("character_create", args=[run.get_slug()])
            if run.status["details"]:
                run.status["details"] += " - "
            mes = _("Access character creation!")
            run.status["details"] += f"<a href='{url}'>{mes}</a>"
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


def get_player_signup(request, ctx):
    regs = Registration.objects.filter(run=ctx["run"], member=request.user.member, cancellation_date__isnull=True)

    if regs:
        return regs[0]

    return None


def check_signup(request, ctx):
    reg = get_player_signup(request, ctx)
    if not reg:
        raise SignupError(ctx["run"].get_slug())

    if reg.ticket and reg.ticket.tier == TicketTier.WAITING:
        raise WaitingError(ctx["run"].get_slug())


def check_assign_character(request, ctx):
    # if the player has a single character, then assign it to their signup
    reg = get_player_signup(request, ctx)
    if not reg:
        return

    if reg.rcrs.exists():
        return

    chars = get_player_characters(request.user.member, ctx["event"])
    if not chars:
        return

    RegistrationCharacterRel.objects.create(character_id=chars[0].id, reg=reg)


def get_reduced_available_count(run):
    ratio = int(run.event.get_config("reduced_ratio", 10))
    red = Registration.objects.filter(run=run, ticket__tier=TicketTier.REDUCED, cancellation_date__isnull=True).count()
    pat = Registration.objects.filter(run=run, ticket__tier=TicketTier.PATRON, cancellation_date__isnull=True).count()
    # silv = Registration.objects.filter(run=run, ticket__tier=RegistrationTicket.SILVER).count()
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


def check_character_ticket_options(reg, char):
    ticket_id = reg.ticket.id

    to_delete = []

    # get options
    for choice in WritingChoice.objects.filter(element_id=char.id):
        tickets_map = choice.option.tickets.values_list("pk", flat=True)
        if tickets_map and ticket_id not in tickets_map:
            to_delete.append(choice.id)

    WritingChoice.objects.filter(pk__in=to_delete).delete()


def process_character_ticket_options(instance):
    if not instance.member:
        return

    if not instance.ticket:
        return

    event = instance.run.event

    for char in instance.characters.all():
        check_character_ticket_options(instance, char)

    for char in event.get_elements(Character).filter(player=instance.member):
        check_character_ticket_options(instance, char)
