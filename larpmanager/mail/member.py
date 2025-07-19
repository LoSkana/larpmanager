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

from datetime import datetime
from typing import Optional

from django.conf import settings as conf_settings
from django.contrib.sites.shortcuts import get_current_site
from django.core import signing
from django.db.models.signals import m2m_changed, pre_save
from django.dispatch import receiver
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_event_features
from larpmanager.mail.base import notify_organization_exe
from larpmanager.models.access import get_event_organizers
from larpmanager.models.accounting import AccountingItemMembership
from larpmanager.models.association import get_url, hdr
from larpmanager.models.member import Badge, Member
from larpmanager.models.miscellanea import ChatMessage, HelpQuestion
from larpmanager.utils.tasks import my_send_mail


def send_membership_confirm(request, membership):
    profile = request.user.member
    # Send email when it is completed
    activate(profile.language)
    subj = hdr(membership) + _("Request of membership to the Organization")
    body = _(
        "You have completed your application for association membership: therefore, your "
        "event registrations are temporarily confirmed."
    )
    body += "<br /><br />" + _(
        "As per the statutes, we will review your request at the next board meeting and "
        "send you an update e-mail as soon as possible (you should receive a reply within "
        "a few weeks at the latest)."
    )
    body += "<br /><br />" + _(
        "Once your admission is approved, you will be able to pay for the tickets for the "
        "events you have registered for."
    )
    amount = int(membership.assoc.get_config("membership_fee", "0"))
    if amount:
        body += " " + _(
            "Please also note that payment of the annual membership fee (%(amount)d "
            "%(currency)s) is required to participate in events."
        ) % {"amount": amount, "currency": request.assoc["currency_symbol"]}
    body += "<br /><br />" + _("Thank you for choosing to be part of our community") + "!"
    my_send_mail(subj, body, profile, membership)


@receiver(pre_save, sender=AccountingItemMembership)
def save_accounting_item_membership(sender, instance, *args, **kwargs):
    if instance.hide:
        return
    if instance.pk:
        return
    # to user
    activate(instance.member.language)
    subj = hdr(instance) + _("Membership fee payment %(year)s") % {"year": instance.year}
    body = _("The payment of your membership fee for this year has been received") + "!"
    my_send_mail(subj, body, instance.member, instance)


def badges_changed(sender, **kwargs):
    action = kwargs.pop("action", None)
    if action != "post_add":
        return
    instance: Optional[Badge] = kwargs.pop("instance", None)
    # model = kwargs.pop("model", None)
    pk_set: Optional[list[int]] = kwargs.pop("pk_set", None)

    for pk in pk_set:
        m = Member.objects.get(pk=pk)
        activate(m.language)
        badge = instance.show(m.language)
        subj = hdr(instance) + _("Achievement assignment: %(badge)s") % {"badge": badge["name"]}
        body = _("You have been awarded an achievement") + "!" + "<br /><br />"
        body += _("Description") + f": {badge['descr']}<br /><br />"
        url = get_url(f"public/{m.id}/", instance)
        body += _("Display your achievements in your <a href= %(url)s'>public profile</a>") % {"url": url} + "."
        my_send_mail(subj, body, m, instance)


m2m_changed.connect(badges_changed, sender=Badge.members.through)


def notify_membership_approved(member, resp):
    # Manda Mail
    activate(member.language)
    subj = hdr(member.membership) + _("Membership of the Organization accepted") + "!"
    body = _("We confirm that your membership has been accepted by the board. We welcome you to our community") + "!"
    body += (
        "<br /><br />" + _("Your card number is: <b>%(number)03d</b>") % {"number": member.membership.card_number} + "."
    )
    if resp:
        body += " " + _("More details") + f": {resp}"

        # Check if you have payments to make
    regs = member.registrations.filter(run__start__gte=datetime.now().date())

    membership_fee = False
    if regs:
        body += (
            "<br /><br />"
            + _("To confirm your event registration, please complete your payment within one week. You can do so here")
            + ": "
        )
        first = True
        for r in regs:
            if first:
                first = False
            else:
                body += ","
            url = get_url("accounting/pay", member.membership)
            href = f"{url}/{r.run.event.slug}/{r.run.number}"
            body += f" <a href='{href}'><b>{r.run.search}</b></a>"

            features = get_event_features(r.run.event_id)
            run_start = r.run.start and r.run.start.year == datetime.today().year
            if run_start and "laog" not in features:
                membership_fee = True

    if membership_fee:
        url = get_url("accounting/membership", member.membership)
        body += "<br /><br />" + _(
            "In addition, you must be up to date with the payment of your membership fee in "
            "order to participate in events. Make your payment <a href='%(url)s'>on this "
            "page</a>."
        ) % {"url": url}

    my_send_mail(subj, body, member, member.membership)


def notify_membership_reject(member, resp):
    # Manda Mail
    activate(member.language)
    subj = hdr(member.membership) + _("Membership of the Organization refused") + "!"
    body = _("We inform you that your membership of the Association has not been accepted by the board") + "."
    if resp:
        body += " " + _("Motivation") + f": {resp}"
    body += _("For more information, write to us") + "!"
    my_send_mail(subj, body, member, member.membership)


@receiver(pre_save, sender=HelpQuestion)
def notify_help_question(sender, instance, **kwargs):
    if instance.pk:
        return

    mb = instance.member

    if instance.is_user:
        if instance.run:
            for organizer in get_event_organizers(instance.run.event):
                activate(organizer.language)
                body, subj = get_help_email(instance, mb)
                subj += " " + _("for %(event)s") % {"event": instance.run}
                url = get_url(
                    f"{instance.run.event.slug}/{instance.run.number}/manage/questions/",
                    instance,
                )
                body += "<br /><br />" + _("(<a href='%(url)s'>answer here</a>)") % {"url": url}
                my_send_mail(subj, body, organizer, instance.run)

        elif instance.assoc:
            body, subj = get_help_email(instance, mb)
            notify_organization_exe(subj, body, instance.assoc, instance)
        else:
            body, subj = get_help_email(instance, mb)
            for _name, email in conf_settings.ADMINS:
                my_send_mail(subj, body, email, instance)

    else:
        # new answer
        activate(mb.language)
        subj = hdr(instance) + _("New answer") + "!"
        body = _("Your question has been answered") + f": {instance.text}"

        if instance.run:
            url = get_url(
                f"{instance.run.event.slug}/{instance.run.number}/help",
                instance,
            )
        else:
            url = get_url("help", instance)

        body += "<br /><br />" + _("(<a href='%(url)s'>answer here</a>)") % {"url": url}

        my_send_mail(subj, body, mb, instance)


def get_help_email(instance, mb):
    subj = hdr(instance) + _("New question by %(user)s") % {"user": mb}
    body = _("A question was asked by: %(user)s") % {"user": mb}
    body += "<br /><br />" + instance.text
    return body, subj


@receiver(pre_save, sender=ChatMessage)
def notify_chat_message(sender, instance, **kwargs):
    if instance.pk:
        return
    activate(instance.receiver.language)
    subj = hdr(instance) + _("New message from %(user)s") % {"user": instance.sender.display_member()}
    url = get_url(f"chat/{instance.sender.id}/", instance)
    body = f"<br /><br />{instance.message} (<a href='{url}'>" + _("reply here") + "</a>)"
    my_send_mail(subj, body, instance.receiver, instance)


# ACTIVATION ACCOUNT
REGISTRATION_SALT = getattr(conf_settings, "REGISTRATION_SALT", "registration")


def get_activation_key(user):
    """
    Generate the activation key which will be emailed to the user.
    """
    return signing.dumps(obj=user.get_username(), salt=REGISTRATION_SALT)


def get_email_context(activation_key, request):
    """
    Build the template context used for the activation email.
    """
    scheme = "https" if request.is_secure() else "http"
    return {
        "scheme": scheme,
        "activation_key": activation_key,
        "expiration_days": conf_settings.ACCOUNT_ACTIVATION_DAYS,
        "site": get_current_site(request),
    }


def send_password_reset_remainder(mb):
    assoc = mb.assoc
    memb = mb.member
    aux = mb.password_reset.split("#")
    url = get_url(f"reset/{aux[0]}/{aux[1]}/", assoc)
    subject = _("Password reset of user %(user)s") % {"user": memb}
    body = _("The user requested the password reset, but did not complete it. Give them this link: %(url)s") % {
        "url": url
    }

    notify_organization_exe(subject, body, assoc, assoc)

    for _name, email in conf_settings.ADMINS:
        my_send_mail(subject, body, email, assoc)
