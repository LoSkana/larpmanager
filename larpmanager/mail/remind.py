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

from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.models.access import get_event_organizers
from larpmanager.models.association import AssocTextType, get_url, hdr
from larpmanager.models.event import Run
from larpmanager.models.registration import Registration
from larpmanager.utils.deadlines import check_run_deadlines
from larpmanager.utils.tasks import my_send_mail
from larpmanager.utils.text import get_assoc_text


def remember_membership(reg: Registration) -> None:
    """Send membership reminder email to registered user.

    Activates the user's language, constructs a localized subject line,
    retrieves the appropriate reminder text, and sends the email.

    Args:
        reg: Registration instance needing membership confirmation.
            Must have valid member and run attributes.

    Returns:
        None

    Side Effects:
        - Activates the user's language for localization
        - Sends email reminder about membership requirement
    """
    # Activate user's preferred language for localized content
    activate(reg.member.language)

    # Construct localized subject line with event header and confirmation text
    subj = hdr(reg.run.event) + _("Confirmation of registration for %(event)s") % {"event": reg.run}

    # Get custom association reminder text or fallback to default template
    body = get_assoc_text(reg.run.event.assoc_id, AssocTextType.REMINDER_MEMBERSHIP) or get_remember_membership_body(
        reg
    )

    # Send the membership reminder email to the registered member
    my_send_mail(subj, body, reg.member, reg.run)


def get_remember_membership_body(reg: Registration) -> str:
    """Generate default membership reminder email body text.

    Creates an HTML-formatted email body for reminding users to complete
    their membership application to confirm their provisional event registration.

    Args:
        reg: Registration instance containing event and user information

    Returns:
        HTML formatted email body string for membership reminder
    """
    # Generate main reminder message with event name and membership link
    body = (
        _(
            "Hello! To confirm your provisional registration for %(event)s, "
            "you must apply for membership in the association"
        )
        % {"event": reg.run}
        + ". "
        + _("To complete the process, simply <a href='%(url)s'>click here</a>") % {"url": get_url("membership")}
        + ". "
    )

    # Add helpful support message
    body += (
        "<br /><br />("
        + _("If you need a hand, feel free to let us know")
        + ". "
        + _("We'll try to help as best we can")
        + "!)"
    )

    # Add warning about registration cancellation for unresponsive users
    body += (
        "<br /><br />"
        + _("If we don't hear from you, we'll assume you're no longer interested in the event")
        + ". "
        + _("Your registration will be cancelled to allow other participants to take your spot")
        + "."
    )

    return body


def remember_pay(reg: Registration) -> None:
    """Send payment reminder email to registered user.

    Sends a localized email reminder to users who have pending payments
    for their event registration. The email content varies based on
    whether the registration is provisional or confirmed.

    Args:
        reg: Registration instance with pending payment that needs reminder

    Returns:
        None

    Side Effects:
        - Activates user's preferred language for email localization
        - Sends email reminder about payment requirement via my_send_mail
    """
    # Activate user's preferred language for localized email content
    activate(reg.member.language)

    # Check if registration is in provisional state (awaiting confirmation)
    provisional = is_reg_provisional(reg)
    context = {"event": reg.run}

    # Set appropriate email subject based on registration status
    if provisional:
        subj = hdr(reg.run.event) + _("Confirm registration to %(event)s") % context
    else:
        subj = hdr(reg.run.event) + _("Complete payment for %(event)s") % context

    # Get custom association text or fallback to default payment reminder body
    body = get_assoc_text(reg.run.event.assoc_id, AssocTextType.REMINDER_PAY) or get_remember_pay_body(
        context, provisional, reg
    )

    # Send the payment reminder email to the registered member
    my_send_mail(subj, body, reg.member, reg.run)


def get_remember_pay_body(context: dict, provisional: bool, reg) -> str:
    """Generate default payment reminder email body text.

    Creates an HTML-formatted email body for payment reminders, handling both
    provisional and confirmed registrations with appropriate messaging based
    on payment deadlines.

    Args:
        context: Email context dictionary containing event information
        provisional: Whether the registration is provisional or confirmed
        reg: Registration instance containing payment details and run information

    Returns:
        HTML formatted string containing the complete email body for payment reminder

    Example:
        >>> context = {'event': 'Summer LARP 2024'}
        >>> body = get_remember_pay_body(context, False, registration_obj)
        >>> print(body)  # Returns formatted HTML email body
    """
    # Extract payment information and build payment URL
    symbol = reg.run.event.assoc.get_currency_symbol()
    amount = f"{reg.quota:.2f}{symbol}"
    deadline = reg.deadline
    url = get_url("accounting/pay", reg.run.event)
    payment_url = f"{url}/{reg.run.event.slug}/{reg.id}"

    # Generate appropriate greeting based on registration type
    if provisional:
        intro = _("Hello! We are reaching out regarding your provisional registration for <b>%(event)s</b>")
    else:
        intro = _("Hello! We are reaching out regarding your registration for <b>%(event)s</b>")

    body = intro % context + "."

    # Add payment instruction based on deadline status
    if deadline <= 0:
        middle = _("To confirm it, please pay the following amount as soon as possible: %(amount)s")
    else:
        middle = _("To confirm it, please pay %(amount)s within %(days)s days")

    body += "<br /><br />" + middle % {"amount": amount, "days": deadline} + "."

    # Add disclaimer for existing agreements
    body += "<br /><br />(" + _("If you have a separate agreement with us, you may disregard this email") + ")"

    # Include payment link and support contact information
    body += (
        "<br /><br />"
        + _("You can make the payment <a href='%(url)s'>on this page</a>") % {"url": payment_url}
        + ". "
        + _("If you encounter any issues, contact us and we will assist you")
        + "!"
    )

    # Add cancellation warning for non-responsive registrants
    body += (
        "<br /><br />"
        + _(
            "If we don't hear from you, we'll assume you're no longer interested in the event and "
            "will cancel your registration to make room for other participants"
        )
        + "."
    )

    return body


def remember_profile(reg: Registration) -> None:
    """Send profile completion reminder email to registered user.

    Activates the user's preferred language and sends a customized email reminder
    about completing their profile for the event registration.

    Args:
        reg: Registration instance with incomplete profile that needs reminder

    Returns:
        None

    Side Effects:
        - Activates user's language for localization
        - Sends email reminder to registered member
    """
    # Activate user's preferred language for localized content
    activate(reg.member.language)

    # Prepare context data for email template
    context = {"event": reg.run, "url": get_url("profile", reg.run.event)}

    # Generate localized email subject with event header
    subj = hdr(reg.run.event) + _("Profile compilation reminder for %(event)s") % context

    # Get custom reminder text or fallback to default template
    body = get_assoc_text(reg.run.event.assoc_id, AssocTextType.REMINDER_PROFILE) or get_remember_profile_body(context)

    # Send the reminder email to the member
    my_send_mail(subj, body, reg.member, reg.run)


def get_remember_profile_body(context):
    """Generate default profile completion reminder email body text.

    Args:
        context (dict): Email context with event and URL information

    Returns:
        str: HTML formatted email body for profile reminder
    """
    return (
        _("Hello! You signed up for %(event)s but haven't completed your profile yet") % context
        + ". "
        + _("It only takes 5 minutes - just <a href='%(url)s'>click here</a> to fill out the form") % context
        + "."
    )


def remember_membership_fee(reg: Registration) -> None:
    """Send membership fee reminder email to registered user.

    Args:
        reg: Registration instance needing membership fee payment. Must have
            a member with language preference and a run with associated event.

    Returns:
        None

    Side Effects:
        - Activates the member's preferred language for email localization
        - Sends an email reminder about annual membership fee requirement
    """
    # Activate member's preferred language for email localization
    activate(reg.member.language)

    # Prepare context data for email template rendering
    context = {"event": reg.run}

    # Build email subject with event header and localized message
    subj = hdr(reg.run.event) + _("Reminder payment of membership fees for %(event)s") % context

    # Get custom reminder text from association settings or use default template
    body = get_assoc_text(
        reg.run.event.assoc_id, AssocTextType.REMINDER_MEMBERSHIP_FEE
    ) or get_remember_membership_fee_body(context, reg)

    # Send the membership fee reminder email to the registered member
    my_send_mail(subj, body, reg.member, reg.run)


def get_remember_membership_fee_body(context: dict, reg: Registration) -> str:
    """Generate default membership fee reminder email body text.

    Creates an HTML-formatted email body for reminding users about unpaid
    annual membership fees required for event participation.

    Args:
        context: Email context dictionary containing event information
        reg: Registration instance with fee payment details and event data

    Returns:
        HTML formatted string containing the complete email body with
        membership fee reminder text and payment link
    """
    # Initial greeting and notification about missing membership payment
    body = (
        _("Hello! You have registered for %(event)s, but we have not yet received your annual membership payment")
        % context
        + "."
    )

    # Explain the importance of membership fee for insurance coverage
    body += (
        "<br /><br />"
        + _("It is required for participation in all our live events, as it also covers the insurance fee")
        + "."
    )

    # Clarify the consequences of non-payment
    body += (
        "<br /><br />"
        + _("Unfortunately, without full payment of the fee, participation in the event is not permitted")
        + "."
    )

    # Provide payment link and offer assistance
    body += (
        "<br /><br />"
        + _("You can complete the payment in just a few minutes <a href='%(url)s'>here</a>")
        % {"url": get_url("accounting", reg.run.event)}
        + ". "
        + _("Let us know if you encounter any issues or need assistance")
        + "!"
    )
    return body


def notify_deadlines(run: Run) -> None:
    """Send deadline notification emails to event organizers.

    Checks for approaching deadlines in the given run and sends notification
    emails to all event organizers with details about users who are missing
    various requirements (registration, payments, profiles, etc.).

    Args:
        run: Run instance with approaching deadlines to check

    Returns:
        None

    Side Effects:
        Sends deadline reminder emails to all event organizers via my_send_mail()
    """
    # Check for any approaching deadlines in this run
    result = check_run_deadlines([run])
    if not result:
        return

    # Extract deadline results for this run
    res = result[0]

    # Skip if no actual deadline issues found (only run key present)
    if all(not v for k, v in res.items() if k != "run"):
        return

    # Define human-readable descriptions for each deadline type
    elements = {
        "memb_del": "Cancellation for missing organization registration",
        "fee_del": "Cancellation for missing yearly membership fee",
        "pay_del": "Cancellation for missing payment",
        "profile_del": "Cancellation for missing profile",
        "memb": "Delay in organization registration",
        "fee": "Delay in yearly membership fee",
        "pay": "Delay in payment",
        "profile": "Delay in profile",
        "cast": "Missing casting preferences",
    }

    # Send notification email to each event organizer
    for orga in get_event_organizers(run.event):
        # Activate organizer's preferred language for translations
        activate(orga.language)

        # Compose email subject with event header and run info
        subj = hdr(run.event) + _("Deadlines") + f" {run}"

        # Start email body with general instruction
        body = _("Review the users that are missing the event's deadlines")

        # Add section for each deadline type that has issues
        for key, descr in elements.items():
            if key not in res or not res[key]:
                continue

            # Add translated description as section header
            body += "<br /><br /><h2>" + _(descr) + "</h2>"

            # Add comma-separated list of user names
            body += f"<p>{', '.join([el[0] for el in res[key]])}</p>"

            # Add comma-separated list of user emails
            body += f"<p>{', '.join([el[1] for el in res[key]])}</p>"

        # Send the composed notification email
        my_send_mail(subj, body, orga, run)
