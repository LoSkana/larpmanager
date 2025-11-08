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

from larpmanager.cache.config import get_association_config
from larpmanager.cache.feature import get_event_features
from larpmanager.mail.base import notify_organization_exe
from larpmanager.models.access import get_event_organizers
from larpmanager.models.association import get_url, hdr
from larpmanager.models.member import Badge, Member
from larpmanager.utils.tasks import my_send_mail


def send_membership_confirm(request, membership) -> None:
    """Send confirmation email when membership application is submitted.

    Args:
        request: Django HTTP request object with user context
        membership: Membership instance that was submitted

    Side Effects:
        Sends confirmation email to member about application status

    """
    # Get user profile and set language context
    member_profile = request.user.member
    activate(member_profile.language)

    # Prepare email subject and initial body content
    email_subject = hdr(membership) + _("Request of membership to the Organization")
    email_body = _(
        "You have completed your application for association membership: therefore, your "
        "event registrations are temporarily confirmed."
    )

    # Add review process information
    email_body += "<br /><br />" + _(
        "As per the statutes, we will review your request at the next board meeting and "
        "send you an update e-mail as soon as possible (you should receive a reply within "
        "a few weeks at the latest)."
    )

    # Add payment information for approved membership
    email_body += "<br /><br />" + _(
        "Once your admission is approved, you will be able to pay for the tickets for the "
        "events you have registered for."
    )

    # Check if membership fee is required and add fee information
    membership_fee_amount = int(get_association_config(membership.association_id, "membership_fee", "0"))
    if membership_fee_amount:
        email_body += " " + _(
            "Please also note that payment of the annual membership fee (%(amount)d "
            "%(currency)s) is required to participate in events."
        ) % {"amount": membership_fee_amount, "currency": request.association["currency_symbol"]}

    # Add closing message and send email
    email_body += "<br /><br />" + _("Thank you for choosing to be part of our community") + "!"
    my_send_mail(email_subject, email_body, member_profile, membership)


def send_membership_payment_notification_email(membership_item):
    """Send notification when membership fee payment is received.

    Args:
        membership_item: AccountingItemMembership instance being saved

    Side effects:
        Sends payment confirmation email to member

    """
    if membership_item.hide:
        return
    if membership_item.pk:
        return
    # to user
    activate(membership_item.member.language)
    subject = hdr(membership_item) + _("Membership fee payment %(year)s") % {"year": membership_item.year}
    body = _("The payment of your membership fee for this year has been received") + "!"
    my_send_mail(subject, body, membership_item.member, membership_item)


def handle_badge_assignment_notifications(instance, pk_set):
    """Handle badge assignment notifications for a set of members.

    Args:
        instance: Badge instance that was assigned
        pk_set: Set of member IDs who received the badge

    Side effects:
        Sends badge achievement notification emails to members

    """
    for member_id in pk_set:
        member = Member.objects.get(pk=member_id)
        activate(member.language)
        badge = instance.show(member.language)
        subject = hdr(instance) + _("Achievement assignment: %(badge)s") % {"badge": badge["name"]}
        body = _("You have been awarded an achievement") + "!" + "<br /><br />"
        body += _("Description") + f": {badge['descr']}<br /><br />"
        profile_url = get_url(f"public/{member.id}/", instance)
        body += _("Display your achievements in your <a href= %(url)s'>public profile</a>") % {"url": profile_url} + "."
        my_send_mail(subject, body, member, instance)


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
    subject = hdr(member.membership) + _("Membership of the Organization accepted") + "!"
    body = _("We confirm that your membership has been accepted by the board. We welcome you to our community") + "!"

    # Add card number to notification
    body += (
        "<br /><br />" + _("Your card number is: <b>%(number)03d</b>") % {"number": member.membership.card_number} + "."
    )

    # Add additional response details if provided
    if resp:
        body += " " + _("More details") + f": {resp}"

    # Check for pending payments across member's registrations
    association_id = member.membership.association_id
    member_registrations = member.registrations.filter(
        run__event__association_id=association_id, run__start__gte=datetime.now().date()
    )
    requires_membership_fee = False
    unpaid_registration_links = []

    # Process each registration for payment requirements
    for registration in member_registrations:
        features = get_event_features(registration.run.event_id)
        run_starts_this_year = registration.run.start and registration.run.start.year == datetime.today().year

        # Check if membership fee is required for this event
        if run_starts_this_year and "laog" not in features:
            requires_membership_fee = True

        # Skip registrations with no payment due
        if not registration.tot_iscr:
            continue

        # Build payment link for unpaid registrations
        payment_url = get_url("accounting/pay", member.membership)
        payment_link = f"{payment_url}/{registration.run.get_slug()}"
        unpaid_registration_links.append(f" <a href='{payment_link}'><b>{registration.run.search}</b></a>")

    # Add registration payment instructions if needed
    if unpaid_registration_links:
        body += (
            "<br /><br />"
            + _("To confirm your event registration, please complete your payment within one week. You can do so here")
            + ": "
            + ", ".join(unpaid_registration_links)
        )

    # Add membership fee payment instructions if required
    if requires_membership_fee and get_association_config(association_id, "membership_fee", 0):
        membership_fee_url = get_url("accounting/membership", member.membership)
        body += "<br /><br />" + _(
            "In addition, you must be up to date with the payment of your membership fee in "
            "order to participate in events. Make your payment <a href='%(url)s'>on this "
            "page</a>."
        ) % {"url": membership_fee_url}

    # Send the notification email
    my_send_mail(subject, body, member, member.membership)


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
    subject = hdr(member.membership) + _("Membership of the Organization refused") + "!"
    body = _("We inform you that your membership of the Association has not been accepted by the board") + "."
    if resp:
        body += " " + _("Motivation") + f": {resp}"
    body += _("For more information, write to us") + "!"
    my_send_mail(subject, body, member, member.membership)


def send_help_question_notification_email(instance):
    """Send notifications for help questions and answers.

    Args:
        instance: HelpQuestion instance being saved

    Side effects:
        Sends notifications to organizers for questions or to users for answers

    """
    if instance.pk:
        return

    member = instance.member

    if instance.is_user:
        if instance.run:
            for organizer in get_event_organizers(instance.run.event):
                activate(organizer.language)
                subject, body = get_help_email(instance)
                subject += " " + _("for %(event)s") % {"event": instance.run}
                url = get_url(
                    f"{instance.run.get_slug()}/manage/questions/",
                    instance,
                )
                body += "<br /><br />" + _("(<a href='%(url)s'>answer here</a>)") % {"url": url}
                my_send_mail(subject, body, organizer, instance.run)

        elif instance.association:
            notify_organization_exe(get_help_email, instance.association, instance)
        else:
            subject, body = get_help_email(instance)
            for _name, email in conf_settings.ADMINS:
                my_send_mail(subject, body, email, instance)

    else:
        # new answer
        activate(member.language)
        subject = hdr(instance) + _("New answer") + "!"
        body = _("Your question has been answered") + f": {instance.text}"

        if instance.run:
            url = get_url(
                f"{instance.run.get_slug()}/help",
                instance,
            )
        else:
            url = get_url("help", instance)

        body += "<br /><br />" + _("(<a href='%(url)s'>answer here</a>)") % {"url": url}

        my_send_mail(subject, body, member, instance)


def get_help_email(help_question):
    """Generate subject and body for help question notification.

    Args:
        help_question: HelpQuestion instance

    Returns:
        tuple: (subject, body) for the notification email

    """
    subject = hdr(help_question) + _("New question by %(user)s") % {"user": help_question.member}
    email_body = _("A question was asked by: %(user)s") % {"user": help_question.member}
    email_body += "<br /><br />" + help_question.text
    return subject, email_body


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
    subject = hdr(instance) + _("New message from %(user)s") % {"user": instance.sender.display_member()}
    chat_url = get_url(f"chat/{instance.sender.id}/", instance)
    email_body = f"<br /><br />{instance.message} (<a href='{chat_url}'>" + _("reply here") + "</a>)"
    my_send_mail(subject, email_body, instance.receiver, instance)


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


def send_password_reset_remainder(membership):
    """Send password reset reminder to association executives and admins.

    Args:
        membership: Membership instance with pending password reset

    Side effects:
        Sends reminder emails to association executives and system admins

    """
    association = membership.association
    notify_organization_exe(get_password_reminder_email, association, membership)

    for _admin_name, admin_email in conf_settings.ADMINS:
        (subject, body) = get_password_reminder_email(membership)
        my_send_mail(subject, body, admin_email, association)


def get_password_reminder_email(membership):
    """Generate subject and body for password reset reminder.

    Args:
        membership: Membership instance with password reset request

    Returns:
        tuple: (subject, body) for the reminder email

    """
    association = membership.association
    member = membership.member
    reset_token_parts = membership.password_reset.split("#")
    reset_url = get_url(f"reset/{reset_token_parts[0]}/{reset_token_parts[1]}/", association)
    subject = _("Password reset of user %(user)s") % {"user": member}
    body = _("The user requested the password reset, but did not complete it. Give them this link: %(url)s") % {
        "url": reset_url
    }
    return subject, body
