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
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.registration import get_reg_counts
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.models.form import RegistrationAnswer, RegistrationChoice, RegistrationOption, RegistrationQuestion
from larpmanager.models.member import MembershipStatus, get_user_membership
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.common import format_datetime, get_time_diff_today
from larpmanager.utils.exceptions import SignupError, WaitingError


def registration_available(r, features=None, reg_counts=None):
    # check advanced registration rules only if there is a max number of tickets
    if r.event.max_pg == 0:
        r.status["primary"] = True
        return

    if not reg_counts:
        reg_counts = get_reg_counts(r)

    remaining_pri = r.event.max_pg - reg_counts.get("count_player", 0)

    if not features:
        features = get_event_features(r.event_id)

    # check primary tickets available
    if remaining_pri > 0:
        r.status["primary"] = True
        perc_signed = 0.3
        max_signed = 10
        if remaining_pri < max_signed or remaining_pri * 1.0 / r.event.max_pg < perc_signed:
            r.status["additional"] = _(" Hurry: only %(num)d tickets available") % {"num": remaining_pri} + "."
        return

    # check if we manage filler
    if "filler" in features and _available_filler(r, reg_counts):
        return

    # check if we manage waiting
    if "waiting" in features and _available_waiting(r, reg_counts):
        return

    r.status["closed"] = True
    return


def _available_waiting(r, reg_counts):
    # infinite waitings
    if r.event.max_waiting == 0:
        r.status["waiting"] = True
        return True

    # if we manage waiting and there are available, say so
    if r.event.max_waiting > 0:
        remaining_waiting = r.event.max_waiting - reg_counts["count_wait"]
        if remaining_waiting > 0:
            r.status["additional"] = _(" Hurry: only %(num)d tickets available") % {"num": remaining_waiting} + "."
            r.status["waiting"] = True
            return True

    return False


def _available_filler(r, reg_counts):
    # infinite fillers
    if r.event.max_filler == 0:
        r.status["filler"] = True
        return True

        # if we manage filler and there are available, say so
    if r.event.max_filler > 0:
        remaining_filler = r.event.max_filler - reg_counts["count_fill"]
        if remaining_filler > 0:
            r.status["additional"] = _(" Hurry: only %(num)d tickets available") % {"num": remaining_filler} + "."
            r.status["filler"] = True
            return True

    return False


def get_match_reg(r, my_regs):
    for m in my_regs:
        if m and m.run_id == r.id:
            return m
    return None


def registration_status_signed(run, features, register_url):
    registration_status_characters(run, features)
    member = run.reg.member
    mb = get_user_membership(member, run.event.assoc_id)

    register_msg = _("Registration confirmed")
    provisional = is_reg_provisional(run.reg)
    if provisional:
        register_msg = _("Provisional registration")
    if run.reg.ticket:
        register_msg += f" ({run.reg.ticket.name})"
    register_text = f"<a href='{register_url}'>{register_msg}</a>"

    if "membership" in features:
        if mb.status in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
            membership_url = reverse("membership")
            mes = _("please upload your membership application to proceed") + "."
            text_url = f", <a href='{membership_url}'>{mes}</a>"
            run.status["text"] = register_text + text_url
            return

        if mb.status in [MembershipStatus.SUBMITTED]:
            run.status["text"] = register_text + ", " + _("awaiting member approval to proceed with payment")
            return

    if "payment" in features:
        if _status_payment(register_text, run):
            return

    if not mb.compiled:
        profile_url = reverse("profile")
        mes = _("please fill in your profile") + "."
        text_url = f", <a href='{profile_url}'>{mes}</a>"
        run.status["text"] = register_text + text_url
        return

    if provisional:
        run.status["text"] = register_text
        return

    run.status["text"] = register_text

    if run.reg.ticket and run.reg.ticket.tier == TicketTier.PATRON:
        run.status["text"] += " " + _("Thanks for your support") + "!"


def _status_payment(register_text, run):
    pending = PaymentInvoice.objects.filter(
        idx=run.reg.id,
        member_id=run.reg.member_id,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.REGISTRATION,
    )
    if pending.count() > 0:
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
        if wire_created.count() > 0:
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


def registration_status(run, user, my_regs=None, features_map=None, reg_count=None):
    run.status = {"open": True, "details": "", "text": "", "additional": ""}

    registration_find(run, user, my_regs)

    if not run.end:
        return

    features = _get_features_map(features_map, run)

    registration_available(run, features, reg_count)
    register_url = reverse("register", args=[run.event.slug, run.number])

    if run.reg:
        registration_status_signed(run, features, register_url)
        return

    if get_time_diff_today(run.end) < 0:
        return

    # check pre-register
    if not run.registration_open and run.event.get_config("pre_register_active", False):
        run.status["open"] = False
        mes = _("Pre-register to the event!")
        preregister_url = reverse("pre_register", args=[run.event.slug])
        run.status["text"] = f"<a href='{preregister_url}'>{mes}</a>"
        run.status["details"] = _("Registration not yet open!")
        return

    dt = datetime.today()
    # check registration open
    if "registration_open" in features:
        if not run.registration_open:
            run.status["open"] = False
            run.status["text"] = _("Registrations not open!")
            return
        elif run.registration_open > dt:
            run.status["open"] = False
            run.status["text"] = _("Registrations not open!")
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
    return current_chars >= max_chars


def registration_status_characters(run, features):
    que = RegistrationCharacterRel.objects.filter(reg_id=run.reg.id)
    approval = run.event.get_config("user_character_approval", False)
    rcrs = que.order_by("character__number").select_related("character")

    aux = []
    for el in rcrs:
        url = reverse("character", args=[run.event.slug, run.number, el.character.number])
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
        if not check_character_maximum(run.event, run.reg.member):
            url = reverse("character_create", args=[run.event.slug, run.number])
            if run.status["details"]:
                run.status["details"] += " - "
            mes = _("Access character creation!")
            run.status["details"] += f"<a href='{url}'>{mes}</a>"
        elif len(aux) == 0:
            url = reverse("character_list", args=[run.event.slug, run.number])
            if run.status["details"]:
                run.status["details"] += " - "
            mes = _("Select your character!")
            run.status["details"] += f"<a href='{url}'>{mes}</a>"


def get_registration_options(instance):
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
        raise SignupError(ctx["event"].slug, ctx["run"].number)

    if reg.ticket and reg.ticket.tier == TicketTier.WAITING:
        raise WaitingError(ctx["event"].slug, ctx["run"].number)


def check_assign_character(request, ctx):
    # if the player has a single character, then assign it to their signup
    reg = get_player_signup(request, ctx)
    if not reg:
        return

    if reg.rcrs.count() > 0:
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


@receiver(pre_save, sender=Registration)
def pre_save_registration_switch_event(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        prev = Registration.objects.get(pk=instance.pk)
    except ObjectDoesNotExist:
        return

    if prev.run.event_id == instance.run.event_id:
        return

    # look for similar ticket to update
    ticket_name = instance.ticket.name
    try:
        instance.ticket = instance.run.event.get_elements(RegistrationTicket).get(name__iexact=ticket_name)
    except ObjectDoesNotExist:
        instance.ticket = None

    # look for similar registration choice
    for choice in RegistrationChoice.objects.filter(reg=instance):
        question_name = choice.question.name
        option_name = choice.option.name
        try:
            choice.question = instance.run.event.get_elements(RegistrationQuestion).get(name__iexact=question_name)
            choice.option = instance.run.event.get_elements(RegistrationOption).get(
                question=choice.question, name__iexact=option_name
            )
            choice.save()
        except ObjectDoesNotExist:
            choice.question = None
            choice.option = None

    # look for similar registration answer
    for answer in RegistrationAnswer.objects.filter(reg=instance):
        question_name = answer.question.name
        try:
            answer.question = instance.run.event.get_elements(RegistrationQuestion).get(name__iexact=question_name)
            answer.save()
        except ObjectDoesNotExist:
            answer.question = None
