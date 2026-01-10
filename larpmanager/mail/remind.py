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

from typing import Any

from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_registration_provisional
from larpmanager.cache.association_text import get_association_text
from larpmanager.models.access import get_event_organizers
from larpmanager.models.association import AssociationTextType, get_url, hdr
from larpmanager.models.registration import Registration
from larpmanager.utils.larpmanager.tasks import my_send_mail
from larpmanager.utils.users.deadlines import check_run_deadlines


def remember_membership(registration: Any) -> None:
    """Send membership reminder email to registered user.

    Args:
        registration: Registration instance needing membership confirmation

    Side effects:
        Sends email reminder about membership requirement

    """
    activate(registration.member.language)

    subject = hdr(registration.run.event) + _("Confirmation of registration for %(event)s") % {
        "event": registration.run,
    }

    body = get_association_text(
        registration.run.event.association_id,
        AssociationTextType.REMINDER_MEMBERSHIP,
        registration.member.language,
    ) or get_remember_membership_body(registration)

    my_send_mail(subject, body, registration.member, registration.run)


def get_remember_membership_body(registration: Any) -> str:
    """Generate default membership reminder email body text.

    Creates an HTML-formatted email body for reminding users to complete their
    membership application to confirm their provisional event registration.

    Args:
        registration: Registration instance containing event and user information

    Returns:
        HTML formatted email body text for membership reminder notification

    Note:
        The generated email includes:
        - Instructions to apply for membership
        - Link to membership application
        - Offer for assistance
        - Warning about registration cancellation

    """
    # Generate main instruction message with event name and membership link
    email_body = (
        _(
            "Hello! To confirm your provisional registration for %(event)s, "
            "you must apply for membership in the association",
        )
        % {"event": registration.run}
        + ". "
        + _("To complete the process, simply <a href='%(url)s'>click here</a>") % {"url": get_url("membership")}
        + ". "
    )

    # Add helpful support message for users who need assistance
    email_body += (
        "<br /><br />("
        + _("If you need a hand, feel free to let us know")
        + ". "
        + _("We'll try to help as best we can")
        + "!)"
    )

    # Include warning about registration cancellation for inactive users
    email_body += (
        "<br /><br />"
        + _("If we don't hear from you, we'll assume you're no longer interested in the event")
        + ". "
        + _("Your registration will be cancelled to allow other participants to take your spot")
        + "."
    )

    return email_body


def remember_pay(registration: Any) -> None:
    """Send payment reminder email to registered user.

    Args:
        registration: Registration instance with pending payment

    Side effects:
        Sends email reminder about payment requirement

    """
    activate(registration.member.language)

    is_provisional = is_registration_provisional(registration)
    email_context = {"event": registration.run}

    if is_provisional:
        email_subject = hdr(registration.run.event) + _("Confirm registration to %(event)s") % email_context
    else:
        email_subject = hdr(registration.run.event) + _("Complete payment for %(event)s") % email_context

    email_body = get_association_text(
        registration.run.event.association_id,
        AssociationTextType.REMINDER_PAY,
        registration.member.language,
    ) or get_remember_pay_body(email_context, registration, is_provisional=is_provisional)

    my_send_mail(email_subject, email_body, registration.member, registration.run)


def get_remember_pay_body(context: dict, registration: Registration, *, is_provisional: bool) -> str:
    """Generate default payment reminder email body text.

    Creates an HTML-formatted email body for payment reminders, handling both
    provisional and confirmed registrations with appropriate messaging based
    on payment deadlines.

    Args:
        context: Email context dictionary containing event information
        registration: Registration instance containing payment details and run information
        is_provisional: Whether the registration is provisional or confirmed

    Returns:
        HTML formatted string containing the complete email body for payment reminder

    Example:
        >>> context = {'event': 'Summer LARP 2024'}
        >>> body = get_remember_pay_body(context, registration, is_provisional=True)
        >>> print(body)  # Returns formatted HTML email body

    """
    # Extract payment information and build payment URL
    currency_symbol = registration.run.event.association.get_currency_symbol()
    amount_to_pay = f"{registration.quota:.2f}{currency_symbol}"
    days_until_deadline = registration.deadline
    base_payment_url = get_url("accounting/pay", registration.run.event)
    payment_url = f"{base_payment_url}/{registration.run.event.slug}/{registration.id}"

    # Generate appropriate greeting based on registration type
    if is_provisional:
        intro_message = _("Hello! We are reaching out regarding your provisional registration for <b>%(event)s</b>")
    else:
        intro_message = _("Hello! We are reaching out regarding your registration for <b>%(event)s</b>")

    email_body = intro_message % context + "."

    # Add payment instruction based on deadline status
    if days_until_deadline <= 0:
        payment_instruction = _("To confirm it, please pay the following amount as soon as possible: %(amount)s")
    else:
        payment_instruction = _("To confirm it, please pay %(amount)s within %(days)s days")

    email_body += "<br /><br />" + payment_instruction % {"amount": amount_to_pay, "days": days_until_deadline} + "."

    # Add disclaimer for existing agreements
    email_body += "<br /><br />(" + _("If you have a separate agreement with us, you may disregard this email") + ")"

    # Include payment link and support contact information
    email_body += (
        "<br /><br />"
        + _("You can make the payment <a href='%(url)s'>on this page</a>") % {"url": payment_url}
        + ". "
        + _("If you encounter any issues, contact us and we will assist you")
        + "!"
    )

    # Add cancellation warning for non-responsive registrants
    email_body += (
        "<br /><br />"
        + _(
            "If we don't hear from you, we'll assume you're no longer interested in the event and "
            "will cancel your registration to make room for other participants",
        )
        + "."
    )

    return email_body


def remember_profile(registration: Any) -> None:
    """Send profile completion reminder email to registered user.

    Args:
        registration: Registration instance with incomplete profile

    Side effects:
        Sends email reminder about profile completion requirement

    """
    activate(registration.member.language)
    context = {"event": registration.run, "url": get_url("profile", registration.run.event)}

    subject = hdr(registration.run.event) + _("Profile compilation reminder for %(event)s") % context

    body = get_association_text(
        registration.run.event.association_id,
        AssociationTextType.REMINDER_PROFILE,
        registration.member.language,
    ) or get_remember_profile_body(context)

    my_send_mail(subject, body, registration.member, registration.run)


def get_remember_profile_body(email_context: Any) -> Any:
    """Generate default profile completion reminder email body text.

    Args:
        email_context (dict): Email context with event and URL information

    Returns:
        str: HTML formatted email body for profile reminder

    """
    return (
        _("Hello! You signed up for %(event)s but haven't completed your profile yet") % email_context
        + ". "
        + _("It only takes 5 minutes - just <a href='%(url)s'>click here</a> to fill out the form") % email_context
        + "."
    )


def remember_membership_fee(registration: Any) -> None:
    """Send membership fee reminder email to registered user.

    Args:
        registration: Registration instance needing membership fee payment

    Side effects:
        Sends email reminder about annual membership fee requirement

    """
    activate(registration.member.language)
    context = {"event": registration.run}

    subject = hdr(registration.run.event) + _("Reminder payment of membership fees for %(event)s") % context

    body = get_association_text(
        registration.run.event.association_id,
        AssociationTextType.REMINDER_MEMBERSHIP_FEE,
        registration.member.language,
    ) or get_remember_membership_fee_body(context, registration)

    my_send_mail(subject, body, registration.member, registration.run)


def get_remember_membership_fee_body(context: dict, registration: Any) -> str:
    """Generate default membership fee reminder email body text.

    Creates an HTML-formatted email body for reminding users about unpaid
    annual membership fees required for event participation.

    Args:
        context: Email context containing event information and template variables
        registration: Registration instance containing fee payment details and event data

    Returns:
        HTML formatted string containing the complete email body with membership
        fee reminder message and payment link

    """
    # Create main greeting and issue description
    email_body = (
        _("Hello! You have registered for %(event)s, but we have not yet received your annual membership payment")
        % context
        + "."
    )

    # Add explanation about membership fee purpose
    email_body += (
        "<br /><br />"
        + _("It is required for participation in all our live events, as it also covers the insurance fee")
        + "."
    )

    # Emphasize participation requirements
    email_body += (
        "<br /><br />"
        + _("Unfortunately, without full payment of the fee, participation in the event is not permitted")
        + "."
    )

    # Provide payment link and support information
    email_body += (
        "<br /><br />"
        + _("You can complete the payment in just a few minutes <a href='%(url)s'>here</a>")
        % {"url": get_url("accounting", registration.run.event)}
        + ". "
        + _("Let us know if you encounter any issues or need assistance")
        + "!"
    )
    return email_body


def notify_deadlines(run: Any) -> None:
    """Send deadline notification emails to event organizers.

    Args:
        run: Run instance with approaching deadlines

    Side effects:
        Sends deadline reminder emails to all event organizers

    """
    deadline_results = check_run_deadlines([run])
    if not deadline_results:
        return
    run_deadlines = deadline_results[0]
    if all(not value for key, value in run_deadlines.items() if key != "run"):
        return

    deadline_elements = {
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

    for organizer in get_event_organizers(run.event):
        activate(organizer.language)
        subject = hdr(run.event) + _("Deadlines") + f" {run}"
        body = _("Review the users that are missing the event's deadlines")
        for deadline_key, description in deadline_elements.items():
            if deadline_key not in run_deadlines or not run_deadlines[deadline_key]:
                continue

            # add description
            body += "<br /><br /><h2>" + _(description) + "</h2>"
            # Add names
            body += f"<p>{', '.join([user_data[0] for user_data in run_deadlines[deadline_key]])}</p>"
            # Add emails
            body += f"<p>{', '.join([user_data[1] for user_data in run_deadlines[deadline_key]])}</p>"

        my_send_mail(subject, body, organizer, run)
