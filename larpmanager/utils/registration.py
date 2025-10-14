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


def registration_available(run, features=None, reg_counts=None):
    """Check if registration is available based on capacity and rules.

    Validates registration availability considering maximum participants,
    ticket quotas, and advanced registration constraints.
    """
    # check advanced registration rules only if there is a max number of tickets
    if run.event.max_pg == 0:
        run.status["primary"] = True
        return

    if not reg_counts:
        reg_counts = get_reg_counts(run)

    remaining_pri = run.event.max_pg - reg_counts.get("count_player", 0)

    if not features:
        features = get_event_features(run.event_id)

    # check primary tickets available
    if remaining_pri > 0:
        run.status["primary"] = True
        perc_signed = 0.3
        max_signed = 10
        if remaining_pri < max_signed or remaining_pri * 1.0 / run.event.max_pg < perc_signed:
            run.status["count"] = remaining_pri
            run.status["additional"] = _(" Hurry: only %(num)d tickets available") % {"num": remaining_pri} + "."
        return

    # check if we manage filler
    if "filler" in features and _available_filler(run, reg_counts):
        return

    # check if we manage waiting
    if "waiting" in features and _available_waiting(run, reg_counts):
        return

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


def registration_status_signed(
    run,  # type: Run
    features: dict,
    register_url: str,
) -> None:
    """Generate registration status information for signed up users.

    This function processes the registration status for users who have already
    signed up for an event run, handling various states like provisional
    registrations, membership requirements, payment status, and profile completion.

    Args:
        run: Run instance for the registered user containing registration details
        features: Dictionary of available features configuration (e.g., 'membership', 'payment')
        register_url: URL string for registration management page

    Returns:
        None: Modifies run.status['text'] in place with appropriate status message

    Raises:
        RewokedMembershipError: When user's membership has been revoked
    """
    # Initialize character registration status
    registration_status_characters(run, features)
    member = run.reg.member
    mb = get_user_membership(member, run.event.assoc_id)

    # Build base registration message with ticket info if available
    register_msg = _("Registration confirmed")
    provisional = is_reg_provisional(run.reg)
    if provisional:
        register_msg = _("Provisional registration")
    if run.reg.ticket:
        register_msg += f" ({run.reg.ticket.name})"
    register_text = f"<a href='{register_url}'>{register_msg}</a>"

    # Handle membership feature requirements
    if "membership" in features:
        # Check for revoked membership status
        if mb.status in [MembershipStatus.REWOKED]:
            raise RewokedMembershipError()

        # Handle incomplete membership applications
        if mb.status in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
            membership_url = reverse("membership")
            mes = _("please upload your membership application to proceed") + "."
            text_url = f", <a href='{membership_url}'>{mes}</a>"
            run.status["text"] = register_text + text_url
            return

        # Handle pending membership approval
        if mb.status in [MembershipStatus.SUBMITTED]:
            run.status["text"] = register_text + ", " + _("awaiting member approval to proceed with payment")
            return

    # Handle payment feature processing
    if "payment" in features:
        if _status_payment(register_text, run):
            return

    # Check for incomplete user profile
    if not mb.compiled:
        profile_url = reverse("profile")
        mes = _("please fill in your profile") + "."
        text_url = f", <a href='{profile_url}'>{mes}</a>"
        run.status["text"] = register_text + text_url
        return

    # Handle provisional registration status
    if provisional:
        run.status["text"] = register_text
        return

    # Set final confirmed registration status
    run.status["text"] = register_text

    # Add patron appreciation message if applicable
    if run.reg.ticket and run.reg.ticket.tier == TicketTier.PATRON:
        run.status["text"] += " " + _("Thanks for your support") + "!"


def _status_payment(register_text, run):
    """Check payment status and update registration status text accordingly.

    Handles pending payments, wire transfers, and payment alerts with
    appropriate messaging and links to payment processing pages.
    """
    pending = PaymentInvoice.objects.filter(
        idx=run.reg.id,
        member_id=run.reg.member_id,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.REGISTRATION,
    )
    if pending.exists():
        run.status["text"] = register_text + ", " + _("payment pending confirmation")
        return True

    if run.reg.alert:
        wire_created = PaymentInvoice.objects.filter(
            idx=run.reg.id,
            member_id=run.reg.member_id,
            status=PaymentStatus.CREATED,
            typ=PaymentType.REGISTRATION,
            method__slug="wire",
        )
        if wire_created.exists():
            pay_url = reverse("acc_reg", args=[run.reg.id])
            mes = _("to confirm it proceed with payment") + "."
            text_url = f", <a href='{pay_url}'>{mes}</a>"
            note = _("If you have made a transfer, please upload the receipt for it to be processed") + "!"
            run.status["text"] = f"{register_text}{text_url} ({note})"
            return True

        pay_url = reverse("acc_reg", args=[run.reg.id])
        mes = _("to confirm it proceed with payment") + "."
        text_url = f", <a href='{pay_url}'>{mes}</a>"
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
        registration_status_signed(run, features, register_url)
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


def get_registration_options(instance):
    """Get formatted list of registration options and answers for display.

    Args:
        instance: Registration instance

    Returns:
        List of tuples containing (question_name, answer_text) pairs
    """
    res = []
    rqs = []
    cache = []
    features = get_event_features(instance.run.event_id)
    for q in RegistrationQuestion.get_instance_questions(instance.run.event, features):
        if q.skip(instance, features):
            continue
        rqs.append(q)
        cache.append(q.id)

    answers = {}
    for el in RegistrationAnswer.objects.filter(question_id__in=cache, reg=instance):
        answers[el.question_id] = el.text

    choices = {}
    for c in RegistrationChoice.objects.filter(question_id__in=cache, reg=instance).select_related("option"):
        if c.question_id not in choices:
            choices[c.question_id] = []
        choices[c.question_id].append(c.option)

    if len(rqs) > 0:
        for q in rqs:
            if q.id in choices:
                txt = ",".join([opt.name for opt in choices[q.id]])
                res.append((q.name, txt))

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


def process_registration_event_change(registration):
    """Handle registration updates when switching between events.

    Args:
        registration: The Registration instance being saved
    """
    if not registration.pk:
        return

    try:
        prev = Registration.objects.get(pk=registration.pk)
    except ObjectDoesNotExist:
        return

    if prev.run.event_id == registration.run.event_id:
        return

    # look for similar ticket to update
    ticket_name = registration.ticket.name
    try:
        registration.ticket = registration.run.event.get_elements(RegistrationTicket).get(name__iexact=ticket_name)
    except ObjectDoesNotExist:
        registration.ticket = None

    # look for similar registration choice
    for choice in RegistrationChoice.objects.filter(reg=registration):
        question_name = choice.question.name
        option_name = choice.option.name
        try:
            choice.question = registration.run.event.get_elements(RegistrationQuestion).get(name__iexact=question_name)
            choice.option = registration.run.event.get_elements(RegistrationOption).get(
                question=choice.question, name__iexact=option_name
            )
            choice.save()
        except ObjectDoesNotExist:
            choice.question = None
            choice.option = None

    # look for similar registration answer
    for answer in RegistrationAnswer.objects.filter(reg=registration):
        question_name = answer.question.name
        try:
            answer.question = registration.run.event.get_elements(RegistrationQuestion).get(name__iexact=question_name)
            answer.save()
        except ObjectDoesNotExist:
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
