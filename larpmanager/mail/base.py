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
from datetime import datetime, timedelta
from typing import Optional

import holidays
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.template.loader import render_to_string
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.links import reset_event_links
from larpmanager.models.access import AssocRole, EventRole, get_assoc_executives, get_event_organizers
from larpmanager.models.association import get_url, hdr
from larpmanager.models.casting import Casting
from larpmanager.models.event import EventTextType
from larpmanager.models.member import Member
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.tasks import my_send_mail
from larpmanager.utils.text import get_event_text


def check_holiday():
    """Check if today or adjacent days are holidays in major countries.

    Returns:
        bool: True if today +/-1 day is a holiday in US, IT, CN, or UK
    """
    td = datetime.now().date()
    for s in ["US", "IT", "CN", "UK"]:
        for md in [-1, 0, 1]:
            tdd = td + timedelta(days=md)
            if tdd in holidays.country_holidays(s):
                return True
    return False


def join_email(assoc):
    """Send welcome emails to association executives when they join.

    Args:
        assoc: Association instance that was just created

    Side effects:
        Sends welcome and feedback request emails to association executives
    """
    for member in get_assoc_executives(assoc):
        activate(member.language)
        subj = _("Welcome to LarpManager") + "!"
        body = render_to_string("mails/join_assoc.html", {"member": member, "assoc": assoc})
        my_send_mail(subj, body, member)

        activate(member.language)
        subj = "We'd love your feedback on LarpManager"
        body = render_to_string("mails/help_assoc.html", {"member": member, "assoc": assoc})
        my_send_mail(subj, body, member, schedule=3600 * 24 * 2)


def on_association_roles_m2m_changed(sender, **kwargs):
    """Handle association role changes and send notifications.

    Args:
        sender: Signal sender
        **kwargs: Signal arguments including instance, model, action, pk_set

    Side effects:
        Sends role change notification emails to affected members
        Invalidates permission cache for affected members
    """
    model = kwargs.pop("model", None)
    if model == Member:
        action = kwargs.pop("action", None)
        instance: Optional[AssocRole] = kwargs.pop("instance", None)
        if not instance:
            return
        pk_set: Optional[list[int]] = kwargs.pop("pk_set", None)

        # Handle role removal or clear - invalidate cache immediately
        if action in ("post_remove", "post_clear"):
            if pk_set:
                for mid in pk_set:
                    mb = Member.objects.get(pk=mid)
                    reset_event_links(mb.user.id, instance.assoc.id)
            return

        # Handle role addition
        if action != "post_add":
            return

        try:
            exes = get_assoc_executives(instance.assoc)
        except ObjectDoesNotExist:
            exes = []

        for mid in pk_set:
            mb = Member.objects.get(pk=mid)
            mb.join(instance.assoc)
            reset_event_links(mb.user.id, instance.assoc.id)

            activate(mb.language)
            subj = hdr(instance.assoc) + _("Role approval %(role)s") % {"role": instance.name}
            url = get_url("manage", instance.assoc)
            body = _("Access the management panel <a href= %(url)s'>from here</a>") % {"url": url} + "!"
            my_send_mail(subj, body, mb, instance.assoc)

            # notify organizers
            for m in exes:
                if m.pk == int(mid):
                    continue
                activate(m.language)
                subj = hdr(instance.assoc) + _("Approval %(user)s as %(role)s") % {
                    "user": mb,
                    "role": instance.name,
                }
                body = _("The user has been assigned the specified role") + "."
                my_send_mail(subj, body, m, instance.assoc)


def on_event_roles_m2m_changed(sender, **kwargs):
    """Handle event role changes and send notifications.

    Args:
        sender: Signal sender
        **kwargs: Signal arguments including instance, model, action, pk_set

    Side effects:
        Sends role change notification emails to affected members and organizers
        Invalidates permission cache for affected members
    """
    model = kwargs.pop("model", None)
    if model == Member:
        action = kwargs.pop("action", None)
        instance: Optional[EventRole] = kwargs.pop("instance", None)
        pk_set: Optional[list[int]] = kwargs.pop("pk_set", None)

        # Handle role removal or clear - invalidate cache immediately
        if action in ("post_remove", "post_clear"):
            if pk_set:
                for mid in pk_set:
                    mb = Member.objects.get(pk=mid)
                    reset_event_links(mb.user.id, instance.event.assoc_id)
            return

        # Handle role addition
        if action != "post_add":
            return

        try:
            orgas = get_event_organizers(instance.event)
        except ObjectDoesNotExist:
            orgas = []

        for mid in pk_set:
            mb = Member.objects.get(pk=mid)
            mb.join(instance.event.assoc)
            reset_event_links(mb.user.id, instance.event.assoc_id)

            activate(mb.language)
            subj = hdr(instance.event.assoc) + _("Role approval %(role)s per %(event)s") % {
                "role": instance.name,
                "event": instance.event,
            }
            url = get_url(f"{instance.event.slug}/1/manage/", instance.event.assoc)
            body = _("Access the management panel <a href= %(url)s'>from here</a>") % {"url": url} + "!"
            my_send_mail(subj, body, mb, instance.event)

            # notify organizers
            for m in orgas:
                if m.pk == int(mid):
                    continue
                activate(m.language)
                subj = hdr(instance.event.assoc) + _("Approval %(user)s as %(role)s for %(event)s") % {
                    "user": mb,
                    "role": instance.name,
                    "event": instance.event,
                }
                body = _("The user has been assigned the specified role") + "."
                my_send_mail(subj, body, m, instance.event)


def bring_friend_instructions(reg, ctx):
    """Send friend invitation instructions to registered user.

    Args:
        reg: Registration instance
        ctx: Context dictionary with event and discount information

    Side effects:
        Sends email with friend invitation instructions and discount code
    """
    activate(reg.member.language)
    subj = hdr(reg.run.event) + _("Bring a friend to %(event)s") % {"event": reg.run} + "!"
    body = _("Personal code: <b>%(cod)s</b>") % {"cod": reg.special_cod}
    body += (
        "<br /><br />"
        + _("Copy this code and share it with friends!")
        + " "
        + _(
            "Every friend who signs up and uses this code in the 'Discounts' field will "
            "receive %(amount_to)s %(currency)s off the ticket"
        )
        % {
            "amount_to": ctx["bring_friend_discount_to"],
            "currency": reg.run.event.assoc.get_currency_symbol(),
        }
        + ". "
        + _("For each of them, you will receive %(amount_from)s %(currency)s off your own event registration")
        % {
            "amount_from": ctx["bring_friend_discount_from"],
            "currency": reg.run.event.assoc.get_currency_symbol(),
        }
        + "."
    )

    body += (
        "<br /><br />"
        + _("Check the available number of discounts <a href='%(url)s'>on this page</a>")
        % {"url": f"{reg.run.get_slug()}/limitations/"}
        + "."
    )

    body += "<br /><br />" + _("See you soon") + "!"

    my_send_mail(subj, body, reg.member, reg.run)


def send_trait_assignment_email(instance, created):
    """Notify member when a trait is assigned to them.

    Args:
        instance: AssignmentTrait instance that was saved
        created (bool): Whether this is a new assignment

    Side effects:
        Deactivates related casting preferences and sends assignment notification
    """
    if not instance.member or not created:
        return

    que = Casting.objects.filter(member_id=instance.member_id, run_id=instance.run_id, typ=instance.typ)
    for c in que:
        c.active = False
        c.save()

    activate(instance.member.language)
    if instance.run.event.get_config("mail_character", False):
        return
    t = instance.trait.show(instance.run)
    q = instance.trait.quest.show(instance.run)
    subj = hdr(instance.run.event) + _("Trait assigned for %(event)s") % {"event": instance.run}
    body = _(
        "In the event <b>%(event)s</b> to which you are enrolled, you have been assigned the "
        "trait: <b>%(trait)s</b> of quest: <b>%(quest)s</b>."
    ) % {"event": instance.run, "trait": t["name"], "quest": q["name"]}
    url = get_url(
        f"{instance.run.get_slug()}/character/your",
        instance.run.event,
    )
    body += "<br/><br />" + _("Access your character <a href='%(url)s'>here</a>") % {"url": url} + "!"

    custom_message_ass = get_event_text(instance.run.event_id, EventTextType.ASSIGNMENT)
    if custom_message_ass:
        body += "<br />" + custom_message_ass
    my_send_mail(subj, body, instance.member, instance.run)


def mail_confirm_casting(member, run, gl_name, lst, avoid):
    """Send casting preference confirmation email to member.

    Args:
        member: Member instance who submitted preferences
        run: Run instance for the event
        gl_name (str): Category name for the casting preferences
        lst (list): List of selected preference items
        avoid (str): Items the member wants to avoid

    Side effects:
        Sends confirmation email with preference summary
    """
    activate(member.language)
    subj = hdr(run.event) + _("Casting preferences saved on '%(type)s' for %(event)s") % {
        "type": gl_name,
        "event": run,
    }
    body = _("Your preferences have been saved in the system") + ":"
    body += "<br /><br />" + "<br />".join(lst)
    if avoid:
        body += "<br/><br />"
        body += _("Elements you wish to avoid in the assignment") + ":"
        body += f" {avoid}"
    my_send_mail(subj, body, member, run)


def send_character_status_update_email(instance):
    """Notify player when character approval status changes.

    Args:
        instance: Character instance being saved

    Side effects:
        Sends status change notification email to character player
    """
    if not instance.event.get_config("user_character_approval", False):
        return

    if instance.pk and instance.player:
        activate(instance.player.language)
        prev = Character.objects.get(pk=instance.pk)
        if prev.status != instance.status:
            body = None
            if instance.status == CharacterStatus.PROPOSED:
                body = get_event_text(instance.event_id, EventTextType.CHARACTER_PROPOSED)
            if instance.status == CharacterStatus.REVIEW:
                body = get_event_text(instance.event_id, EventTextType.CHARACTER_REVIEW)
            if instance.status == CharacterStatus.APPROVED:
                body = get_event_text(instance.event_id, EventTextType.CHARACTER_APPROVED)

            if not body:
                return

            subj = f"{hdr(instance.event)} - {str(instance)} - {instance.get_status_display()}"

            my_send_mail(subj, body, instance.player, instance.event)


def notify_organization_exe(func, assoc, instance):
    """Send notification to association executives.

    Args:
        func: Function that generates subject and body for the notification
        assoc: Association instance
        instance: Context instance for the notification

    Side effects:
        Sends notification emails to association executives or main email
    """
    if assoc.main_mail:
        activate(get_exec_language(assoc))
        (subj, body) = func(instance)
        my_send_mail(subj, body, assoc.main_mail, instance)
        return

    for orga in get_assoc_executives(assoc):
        activate(orga.language)
        (subj, body) = func(instance)
        my_send_mail(subj, body, orga.email, instance)


def get_exec_language(assoc):
    """Determine the most common language among association executives.

    Args:
        assoc: Association instance

    Returns:
        str: Language code preferred by most executives, defaults to 'en'
    """
    # get most common language between organizers
    langs = {}
    for orga in get_assoc_executives(assoc):
        lang = orga.language
        if lang not in langs:
            langs[lang] = 1
        else:
            langs[lang] += 1
    if langs:
        max_lang = max(langs, key=langs.get)
    else:
        max_lang = "en"
    return max_lang


def send_support_ticket_email(instance):
    for _name, email in conf_settings.ADMINS:
        subj = f"LarpManager ticket - {instance.assoc.name}"
        if instance.reason:
            subj += f" [{instance.reason}]"
        body = f"Email: {instance.email} <br /><br />"
        if instance.member:
            body += f"User: {instance.member} ({instance.member.email}) <br /><br />"
        body += instance.content
        if instance.screenshot:
            body += f"<br /><br /><img src='http://larpmanager.com/{instance.screenshot_reduced.url}' />"
        my_send_mail(subj, body, email)
