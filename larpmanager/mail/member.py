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
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_assoc_config
from larpmanager.cache.feature import get_event_features
from larpmanager.mail.base import notify_organization_exe
from larpmanager.models.access import get_event_organizers
from larpmanager.models.association import get_url, hdr
from larpmanager.models.member import Badge, Member
from larpmanager.utils.tasks import my_send_mail


def send_membership_confirm(request, membership):
    """Send confirmation email when membership application is submitted.

    Args:
        request: Django HTTP request object with user context
        membership: Membership instance that was submitted

    Side effects:
        Sends confirmation email to member about application status
    """
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
    amount = int(get_assoc_config(membership.assoc_id, "membership_fee", "0"))
    if amount:
        body += " " + _(
            "Please also note that payment of the annual membership fee (%(amount)d "
            "%(currency)s) is required to participate in events."
        ) % {"amount": amount, "currency": request.assoc["currency_symbol"]}
    body += "<br /><br />" + _("Thank you for choosing to be part of our community") + "!"
    my_send_mail(subj, body, profile, membership)


def send_membership_payment_notification_email(instance):
    """Send notification when membership fee payment is received.

    Args:
        instance: AccountingItemMembership instance being saved

    Side effects:
        Sends payment confirmation email to member
    """
    if instance.hide:
        return
    if instance.pk:
        return
    # to user
    activate(instance.member.language)
    subj = hdr(instance) + _("Membership fee payment %(year)s") % {"year": instance.year}
    body = _("The payment of your membership fee for this year has been received") + "!"
    my_send_mail(subj, body, instance.member, instance)


def handle_badge_assignment_notifications(instance, pk_set):
    """Handle badge assignment notifications for a set of members.

    Args:
        instance: Badge instance that was assigned
        pk_set: Set of member IDs who received the badge

    Side effects:
        Sends badge achievement notification emails to members
    """
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


def on_member_badges_m2m_changed(sender, **kwargs):
    """Handle badge assignment notifications.

    Args:
        sender: Signal sender
        **kwargs: Signal arguments including action, instance, pk_set

    Side effects:
        Sends badge achievement notification emails to members
    """
    action = kwargs.pop("action", None)
    if action != "post_add":
        return
    instance: Optional[Badge] = kwargs.pop("instance", None)
    # model = kwargs.pop("model", None)
    pk_set: Optional[list[int]] = kwargs.pop("pk_set", None)

    handle_badge_assignment_notifications(instance, pk_set)


def notify_membership_approved(member: "Member", resp: str) -> None:
    """Send notification when membership application is approved.

    Args:
        member: Member instance whose membership was approved
        resp: Optional response message from board

    Side Effects:
        Sends approval email with payment instructions and card number
    """
    # Activate member's language for localized messages
    activate(member.language)

    # Build notification subject and body
    subj = hdr(member.membership) + _("Membership of the Organization accepted") + "!"
    body = _("We confirm that your membership has been accepted by the board. We welcome you to our community") + "!"

    # Add card number to notification
    body += (
        "<br /><br />" + _("Your card number is: <b>%(number)03d</b>") % {"number": member.membership.card_number} + "."
    )

    # Add additional response details if provided
    if resp:
        body += " " + _("More details") + f": {resp}"

    # Check for pending payments across member's registrations
    assoc_id = member.membership.assoc_id
    regs = member.registrations.filter(run__event__assoc_id=assoc_id, run__start__gte=datetime.now().date())
    membership_fee = False
    reg_list = []

    # Process each registration for payment requirements
    for registration in regs:
        features = get_event_features(registration.run.event_id)
        run_start = registration.run.start and registration.run.start.year == datetime.today().year

        # Check if membership fee is required for this event
        if run_start and "laog" not in features:
            membership_fee = True

        # Skip registrations with no payment due
        if not registration.tot_iscr:
            continue

        # Build payment link for unpaid registrations
        url = get_url("accounting/pay", member.membership)
        href = f"{url}/{registration.run.get_slug()}"
        reg_list.append(f" <a href='{href}'><b>{registration.run.search}</b></a>")

    # Add registration payment instructions if needed
    if reg_list:
        body += (
            "<br /><br />"
            + _("To confirm your event registration, please complete your payment within one week. You can do so here")
            + ": "
            + ", ".join(reg_list)
        )

    # Add membership fee payment instructions if required
    if membership_fee and get_assoc_config(assoc_id, "membership_fee", 0):
        url = get_url("accounting/membership", member.membership)
        body += "<br /><br />" + _(
            "In addition, you must be up to date with the payment of your membership fee in "
            "order to participate in events. Make your payment <a href='%(url)s'>on this "
            "page</a>."
        ) % {"url": url}

    # Send the notification email
    my_send_mail(subj, body, member, member.membership)


def notify_membership_reject(member, resp):
    """Send notification when membership application is rejected.

    Args:
        member: Member instance whose membership was rejected
        resp (str): Optional response message explaining rejection

    Side effects:
        Sends rejection notification email
    """
    # Manda Mail
    activate(member.language)
    subj = hdr(member.membership) + _("Membership of the Organization refused") + "!"
    body = _("We inform you that your membership of the Association has not been accepted by the board") + "."
    if resp:
        body += " " + _("Motivation") + f": {resp}"
    body += _("For more information, write to us") + "!"
    my_send_mail(subj, body, member, member.membership)


def send_help_question_notification_email(instance):
    """Send notifications for help questions and answers.

    Args:
        instance: HelpQuestion instance being saved

    Side effects:
        Sends notifications to organizers for questions or to users for answers
    """
    if instance.pk:
        return

    mb = instance.member

    if instance.is_user:
        if instance.run:
            for organizer in get_event_organizers(instance.run.event):
                activate(organizer.language)
                subj, body = get_help_email(instance)
                subj += " " + _("for %(event)s") % {"event": instance.run}
                url = get_url(
                    f"{instance.run.get_slug()}/manage/questions/",
                    instance,
                )
                body += "<br /><br />" + _("(<a href='%(url)s'>answer here</a>)") % {"url": url}
                my_send_mail(subj, body, organizer, instance.run)

        elif instance.assoc:
            notify_organization_exe(get_help_email, instance.assoc, instance)
        else:
            subj, body = get_help_email(instance)
            for _name, email in conf_settings.ADMINS:
                my_send_mail(subj, body, email, instance)

    else:
        # new answer
        activate(mb.language)
        subj = hdr(instance) + _("New answer") + "!"
        body = _("Your question has been answered") + f": {instance.text}"

        if instance.run:
            url = get_url(
                f"{instance.run.get_slug()}/help",
                instance,
            )
        else:
            url = get_url("help", instance)

        body += "<br /><br />" + _("(<a href='%(url)s'>answer here</a>)") % {"url": url}

        my_send_mail(subj, body, mb, instance)


def get_help_email(instance):
    """Generate subject and body for help question notification.

    Args:
        instance: HelpQuestion instance

    Returns:
        tuple: (subject, body) for the notification email
    """
    subj = hdr(instance) + _("New question by %(user)s") % {"user": instance.member}
    body = _("A question was asked by: %(user)s") % {"user": instance.member}
    body += "<br /><br />" + instance.text
    return subj, body


def send_chat_message_notification_email(instance):
    """Send notification for new chat messages.

    Args:
        instance: ChatMessage instance being saved

    Side effects:
        Sends notification email to message receiver
    """
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
    """Generate the activation key which will be emailed to the user.

    Args:
        user: User instance to generate key for

    Returns:
        str: Signed activation key for email verification
    """
    """
    Generate the activation key which will be emailed to the user.
    """
    return signing.dumps(obj=user.get_username(), salt=REGISTRATION_SALT)


def get_email_context(activation_key, request):
    """Build the template context used for the activation email.

    Args:
        activation_key (str): Generated activation key
        request: Django HTTP request object

    Returns:
        dict: Context dictionary for activation email template
    """
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
    """Send password reset reminder to association executives and admins.

    Args:
        mb: Membership instance with pending password reset

    Side effects:
        Sends reminder emails to association executives and system admins
    """
    assoc = mb.assoc
    notify_organization_exe(get_password_reminder_email, assoc, mb)

    for _name, email in conf_settings.ADMINS:
        (subject, body) = get_password_reminder_email(mb)
        my_send_mail(subject, body, email, assoc)


def get_password_reminder_email(mb):
    """Generate subject and body for password reset reminder.

    Args:
        mb: Membership instance with password reset request

    Returns:
        tuple: (subject, body) for the reminder email
    """
    assoc = mb.assoc
    memb = mb.member
    aux = mb.password_reset.split("#")
    url = get_url(f"reset/{aux[0]}/{aux[1]}/", assoc)
    subj = _("Password reset of user %(user)s") % {"user": memb}
    body = _("The user requested the password reset, but did not complete it. Give them this link: %(url)s") % {
        "url": url
    }
    return subj, body
