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
from typing import Any, Optional

from django.conf import settings as conf_settings
from django.contrib.sites.shortcuts import get_current_site
from django.core import signing
from django.http import HttpRequest
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_assoc_config
from larpmanager.cache.feature import get_event_features
from larpmanager.mail.base import notify_organization_exe
from larpmanager.models.access import get_event_organizers
from larpmanager.models.accounting import AccountingItemMembership
from larpmanager.models.association import get_url, hdr
from larpmanager.models.member import Badge, Member, Membership
from larpmanager.models.miscellanea import ChatMessage, HelpQuestion
from larpmanager.utils.tasks import my_send_mail


def send_membership_confirm(request: HttpRequest, membership: Membership) -> None:
    """Send confirmation email when membership application is submitted.

    Args:
        request: Django HTTP request object with user context and association data
        membership: Membership instance that was submitted for review

    Returns:
        None

    Side Effects:
        - Activates user's preferred language for email content
        - Sends confirmation email to member about application status
        - Includes membership fee information if applicable
    """
    # Get user profile and activate their preferred language
    profile = request.user.member
    activate(profile.language)

    # Build email subject with organization header
    subj = hdr(membership) + _("Request of membership to the Organization")

    # Start building email body with initial confirmation message
    body = _(
        "You have completed your application for association membership: therefore, your "
        "event registrations are temporarily confirmed."
    )

    # Add information about review process and timeline
    body += "<br /><br />" + _(
        "As per the statutes, we will review your request at the next board meeting and "
        "send you an update e-mail as soon as possible (you should receive a reply within "
        "a few weeks at the latest)."
    )

    # Explain next steps after approval
    body += "<br /><br />" + _(
        "Once your admission is approved, you will be able to pay for the tickets for the "
        "events you have registered for."
    )

    # Check if membership fee is required and add fee information
    amount = int(get_assoc_config(membership.assoc_id, "membership_fee", "0"))
    if amount:
        body += " " + _(
            "Please also note that payment of the annual membership fee (%(amount)d "
            "%(currency)s) is required to participate in events."
        ) % {"amount": amount, "currency": request.assoc["currency_symbol"]}

    # Add closing message and send the email
    body += "<br /><br />" + _("Thank you for choosing to be part of our community") + "!"
    my_send_mail(subj, body, profile, membership)


def send_membership_payment_notification_email(instance: AccountingItemMembership) -> None:
    """Send notification when membership fee payment is received.

    Args:
        instance: AccountingItemMembership instance being saved. Must have member
            attribute with language property and year attribute.

    Returns:
        None

    Side Effects:
        - Sends payment confirmation email to member if conditions are met
        - Activates member's language for localization
    """
    # Skip notification if item is marked as hidden
    if instance.hide:
        return

    # Skip notification if this is an update to existing record (has primary key)
    if instance.pk:
        return

    # Activate member's preferred language for email localization
    activate(instance.member.language)

    # Build localized email subject with year context
    subj = hdr(instance) + _("Membership fee payment %(year)s") % {"year": instance.year}

    # Create confirmation message body
    body = _("The payment of your membership fee for this year has been received") + "!"

    # Send email notification to member
    my_send_mail(subj, body, instance.member, instance)


def handle_badge_assignment_notifications(instance, pk_set: set[int]) -> None:
    """Handle badge assignment notifications for a set of members.

    Sends achievement notification emails to all members who received a badge assignment.
    The notification includes the badge name, description, and a link to the member's
    public profile where they can view their achievements.

    Args:
        instance: Badge instance that was assigned to the members
        pk_set: Set of member primary keys (IDs) who received the badge assignment

    Returns:
        None

    Side Effects:
        - Sends email notifications to all specified members
        - Activates each member's preferred language for localized content
    """
    # Iterate through each member who received the badge
    for pk in pk_set:
        # Retrieve the member object and activate their language preference
        m = Member.objects.get(pk=pk)
        activate(m.language)

        # Get localized badge information for the member's language
        badge = instance.show(m.language)

        # Construct the email subject with badge name
        subj = hdr(instance) + _("Achievement assignment: %(badge)s") % {"badge": badge["name"]}

        # Build the email body with achievement details
        body = _("You have been awarded an achievement") + "!" + "<br /><br />"
        body += _("Description") + f": {badge['descr']}<br /><br />"

        # Generate URL to member's public profile and add to email body
        url = get_url(f"public/{m.id}/", instance)
        body += _("Display your achievements in your <a href= %(url)s'>public profile</a>") % {"url": url} + "."

        # Send the notification email to the member
        my_send_mail(subj, body, m, instance)


def on_member_badges_m2m_changed(sender: type, **kwargs: Any) -> None:
    """Handle badge assignment notifications.

    This function is triggered when the many-to-many relationship between members
    and badges changes. It specifically handles the case where badges are added
    to members, sending notification emails for new badge achievements.

    Args:
        sender: The model class that sent the signal
        **kwargs: Signal arguments containing:
            - action (str): The type of m2m change operation
            - instance (Badge, optional): The badge instance being modified
            - pk_set (list[int], optional): Set of member primary keys affected

    Returns:
        None

    Side Effects:
        - Sends badge achievement notification emails to affected members
        - Only processes 'post_add' actions, ignoring other m2m operations
    """
    # Extract the action type from signal arguments
    action = kwargs.pop("action", None)

    # Only process badge additions, skip removals and other operations
    if action != "post_add":
        return

    # Get the badge instance that was modified
    instance: Optional[Badge] = kwargs.pop("instance", None)
    # model = kwargs.pop("model", None)  # Commented out as unused

    # Get the set of member primary keys that received the badge
    pk_set: Optional[list[int]] = kwargs.pop("pk_set", None)

    # Delegate the actual notification handling to specialized function
    handle_badge_assignment_notifications(instance, pk_set)


def notify_membership_approved(member: Member, resp: str) -> None:
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


def notify_membership_reject(member: Member, resp: str) -> None:
    """Send notification when membership application is rejected.

    Args:
        member: Member instance whose membership was rejected
        resp: Optional response message explaining rejection

    Side Effects:
        Sends rejection notification email to the member
    """
    # Activate member's preferred language for localization
    activate(member.language)

    # Build email subject with membership header and rejection message
    subj = hdr(member.membership) + _("Membership of the Organization refused") + "!"

    # Create base rejection message body
    body = _("We inform you that your membership of the Association has not been accepted by the board") + "."

    # Append optional rejection reason if provided
    if resp:
        body += " " + _("Motivation") + f": {resp}"

    # Add contact information footer and send notification
    body += _("For more information, write to us") + "!"
    my_send_mail(subj, body, member, member.membership)


def send_help_question_notification_email(instance: HelpQuestion) -> None:
    """Send notifications for help questions and answers.

    Sends email notifications to appropriate recipients based on the type of help question:
    - For new user questions: notifies organizers or admins
    - For new answers: notifies the original question author

    Args:
        instance: HelpQuestion instance being saved. Must have attributes:
            - pk: Primary key (None for new instances)
            - member: Member who created the question/answer
            - is_user: Boolean indicating if this is a user question (vs answer)
            - run: Optional Run instance for event-specific questions
            - assoc: Optional Association instance for org-level questions
            - text: The question/answer text content

    Returns:
        None

    Side Effects:
        - Sends email notifications via my_send_mail()
        - Activates language settings for recipients
        - May send multiple emails for multiple organizers
    """
    # Early return for existing instances (only process new records)
    if instance.pk:
        return

    # Get the member who created this question/answer
    mb = instance.member

    # Handle new user questions - notify appropriate organizers/admins
    if instance.is_user:
        # Event-specific question: notify event organizers
        if instance.run:
            for organizer in get_event_organizers(instance.run.event):
                # Set organizer's language for localized content
                activate(organizer.language)
                subj, body = get_help_email(instance)

                # Add event context to subject line
                subj += " " + _("for %(event)s") % {"event": instance.run}

                # Generate management URL for organizers to answer
                url = get_url(
                    f"{instance.run.get_slug()}/manage/questions/",
                    instance,
                )

                # Add answer link to email body
                body += "<br /><br />" + _("(<a href='%(url)s'>answer here</a>)") % {"url": url}
                my_send_mail(subj, body, organizer, instance.run)

        # Organization-level question: notify organization executives
        elif instance.assoc:
            notify_organization_exe(get_help_email, instance.assoc, instance)

        # General question: notify system administrators
        else:
            subj, body = get_help_email(instance)
            for _name, email in conf_settings.ADMINS:
                my_send_mail(subj, body, email, instance)

    # Handle new answers - notify the original question author
    else:
        # Set question author's language for localized content
        activate(mb.language)
        subj = hdr(instance) + _("New answer") + "!"
        body = _("Your question has been answered") + f": {instance.text}"

        # Generate appropriate URL based on question context
        if instance.run:
            # Event-specific help page
            url = get_url(
                f"{instance.run.get_slug()}/help",
                instance,
            )
        else:
            # General help page
            url = get_url("help", instance)

        # Add view answer link to email body
        body += "<br /><br />" + _("(<a href='%(url)s'>answer here</a>)") % {"url": url}

        # Send notification to question author
        my_send_mail(subj, body, mb, instance)


def get_help_email(instance: HelpQuestion) -> tuple[str, str]:
    """Generate subject and body for help question notification.

    Creates an email notification for new help questions submitted by users.
    The subject includes a header and the user who asked the question.
    The body contains the user information and the full question text.

    Args:
        instance: HelpQuestion instance containing the question details and member info

    Returns:
        tuple[str, str]: A tuple containing (subject, body) for the notification email
            - subject: Formatted email subject with header and user name
            - body: HTML-formatted email body with user info and question text

    Example:
        >>> question = HelpQuestion(member=user, text="How do I register?")
        >>> subject, body = get_help_email(question)
    """
    # Generate email subject with header and user identification
    subj = hdr(instance) + _("New question by %(user)s") % {"user": instance.member}

    # Create email body with user information
    body = _("A question was asked by: %(user)s") % {"user": instance.member}

    # Append the actual question text with HTML formatting
    body += "<br /><br />" + instance.text

    return subj, body


def send_chat_message_notification_email(instance: ChatMessage) -> None:
    """Send notification for new chat messages.

    Args:
        instance: ChatMessage instance being saved. Must have sender, receiver,
                 message attributes and pk property.

    Returns:
        None

    Side Effects:
        - Activates the receiver's language locale
        - Sends notification email to message receiver via my_send_mail
        - Does nothing if instance already has a primary key (existing record)
    """
    # Skip notification if this is an update to existing message
    if instance.pk:
        return

    # Activate receiver's preferred language for localized email content
    activate(instance.receiver.language)

    # Build localized subject line with sender display name
    subj = hdr(instance) + _("New message from %(user)s") % {"user": instance.sender.display_member()}

    # Generate URL for replying to the message
    url = get_url(f"chat/{instance.sender.id}/", instance)

    # Create email body with message content and reply link
    body = f"<br /><br />{instance.message} (<a href='{url}'>" + _("reply here") + "</a>)"

    # Send the notification email
    my_send_mail(subj, body, instance.receiver, instance)


# ACTIVATION ACCOUNT
REGISTRATION_SALT = getattr(conf_settings, "REGISTRATION_SALT", "registration")


def get_activation_key(user) -> str:
    """Generate the activation key which will be emailed to the user.

    Args:
        user: User instance to generate key for

    Returns:
        str: Signed activation key for email verification
    """
    # Generate signed activation key using username and registration salt
    return signing.dumps(obj=user.get_username(), salt=REGISTRATION_SALT)


def get_email_context(activation_key: str, request) -> dict:
    """Build the template context used for the activation email.

    Args:
        activation_key: Generated activation key for account activation
        request: Django HTTP request object containing site information

    Returns:
        Dictionary containing context variables for activation email template:
            - scheme: HTTP scheme (http/https) based on request security
            - activation_key: The provided activation key
            - expiration_days: Number of days before activation expires
            - site: Current site object from Django's sites framework
    """
    # Determine the appropriate URL scheme based on request security
    scheme = "https" if request.is_secure() else "http"

    # Build and return the email template context
    return {
        "scheme": scheme,
        "activation_key": activation_key,
        "expiration_days": conf_settings.ACCOUNT_ACTIVATION_DAYS,
        "site": get_current_site(request),
    }


def send_password_reset_remainder(mb: Member) -> None:
    """Send password reset reminder to association executives and admins.

    Notifies organization executives and system administrators when a member
    has a pending password reset request that requires attention.

    Args:
        mb: Member instance with pending password reset request.

    Returns:
        None

    Side Effects:
        - Sends reminder emails to association executives via notify_organization_exe
        - Sends individual emails to all configured system administrators
    """
    # Get the association from the member instance
    assoc = mb.assoc

    # Notify all organization executives about the password reset request
    notify_organization_exe(get_password_reminder_email, assoc, mb)

    # Send individual reminder emails to each system administrator
    for _name, email in conf_settings.ADMINS:
        # Generate email subject and body for the password reset reminder
        (subject, body) = get_password_reminder_email(mb)
        # Send the email to the current admin
        my_send_mail(subject, body, email, assoc)


def get_password_reminder_email(mb: Membership) -> tuple[str, str]:
    """Generate subject and body for password reset reminder email.

    Args:
        mb: Membership instance containing password reset request information.
            Must have 'assoc', 'member', and 'password_reset' attributes.

    Returns:
        tuple[str, str]: A tuple containing:
            - subject (str): Localized email subject line
            - body (str): Localized email body with reset link

    Note:
        The password_reset field is expected to contain a hash-separated
        string with reset token components.
    """
    # Extract association and member from membership
    assoc = mb.assoc
    memb = mb.member

    # Parse password reset token components
    aux = mb.password_reset.split("#")

    # Generate the password reset URL
    url = get_url(f"reset/{aux[0]}/{aux[1]}/", assoc)

    # Create localized subject line
    subj = _("Password reset of user %(user)s") % {"user": memb}

    # Create localized body with reset link
    body = _("The user requested the password reset, but did not complete it. Give them this link: %(url)s") % {
        "url": url
    }

    return subj, body
