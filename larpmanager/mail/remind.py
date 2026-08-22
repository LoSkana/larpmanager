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

from django.utils.translation import activate, gettext_lazy as _

from larpmanager.accounting.base import is_registration_provisional
from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.basic import get_run_association_id, get_run_basic_cache
from larpmanager.mail.templates import get_payment_info
from larpmanager.models.access import get_event_organizers_by_event
from larpmanager.models.association import AssociationTextType, get_association_url, get_url, hdr_run
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

    subject = hdr_run(registration.run_id) + _("Registration confirmation for %(event)s") % {
        "event": registration.run,
    }

    body = get_association_text(
        get_run_association_id(registration.run_id),
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
            "Hello! To confirm your provisional registration for %(event)s, you must apply for association membership.",
        )
        % {"event": registration.run}
        + " "
        + _("To complete the process, <a href='%(url)s'>click here</a>.")
        % {"url": get_association_url("membership", get_run_association_id(registration.run_id))}
    )

    # Add helpful support message for users who need assistance
    email_body += "<br /><br />(" + _("If you need assistance, please contact us. We are happy to help!")

    # Include warning about registration cancellation for inactive users
    email_body += "<br /><br />" + _(
        "If we do not hear from you, we will assume you are no longer interested in attending. "
        "Your registration will be cancelled to make room for other participants."
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
        email_subject = hdr_run(registration.run_id) + _("Confirm registration for %(event)s") % email_context
    else:
        email_subject = hdr_run(registration.run_id) + _("Complete payment for %(event)s") % email_context

    email_body = get_association_text(
        get_run_association_id(registration.run_id),
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
    basic_cache: dict = {}
    currency_symbol = get_run_basic_cache(registration.run_id, context=basic_cache)["currency_symbol"]
    amount_to_pay = f"{registration.quota:.2f}{currency_symbol}"
    days_until_deadline = registration.deadline
    base_payment_url = get_association_url(
        "accounting/pay", get_run_association_id(registration.run_id, context=basic_cache)
    )
    payment_url = f"{base_payment_url}/{registration.run.get_slug()}"

    # Generate appropriate greeting based on registration type
    if is_provisional:
        intro_message = _("Hello! We are contacting you regarding your provisional registration for <b>%(event)s</b>.")
    else:
        intro_message = _("Hello! We are contacting you regarding your registration for <b>%(event)s</b>.")

    email_body = intro_message % context

    # Add payment instruction based on deadline status
    if days_until_deadline <= 0:
        payment_instruction = _("To confirm your spot, please pay %(amount)s as soon as possible.")
    else:
        payment_instruction = _("To confirm your spot, please pay %(amount)s within %(days)s days.")

    email_body += "<br /><br />" + payment_instruction % {"amount": amount_to_pay, "days": days_until_deadline}

    # Add disclaimer for existing agreements
    email_body += (
        "<br /><br />("
        + _("If you have already arranged a separate payment agreement with us, please disregard this email.")
        + ")"
    )

    # Include payment link and support contact information
    email_body += (
        "<br /><br />"
        + _("You can submit your payment <a href='%(url)s'>on this page</a>.") % {"url": payment_url}
        + " "
        + _("If you encounter any issues, please contact us for assistance.")
    )

    # Add wire transfer details if active for this association
    email_body += get_payment_info(get_run_association_id(registration.run_id, context=basic_cache), payment_url)

    # Add cancellation warning for non-responsive registrants
    email_body += "<br /><br />" + _(
        "If we do not receive a response, we will assume you are no longer interested and "
        "will cancel your registration to free up space for other participants.",
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
    basic_cache: dict = {}
    context = {
        "event": registration.run,
        "url": get_association_url("profile", get_run_association_id(registration.run_id, context=basic_cache)),
    }

    subject = hdr_run(registration.run_id) + _("Profile completion reminder for %(event)s") % context

    body = get_association_text(
        get_run_association_id(registration.run_id, context=basic_cache),
        AssociationTextType.REMINDER_PROFILE,
        registration.member.language,
    ) or get_remember_profile_body(context)

    my_send_mail(subject, body, registration.member, registration.run)


def get_remember_profile_body(email_context: Any) -> Any:
    """Generate default profile completion reminder email body text."""
    return (
        _(
            "Hello! You registered for %(event)s but have not completed your profile yet. "
            "It takes only 5 minutes, <a href='%(url)s'>click here</a> to complete the form."
        )
        % email_context
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

    subject = hdr_run(registration.run_id) + _("Membership fee payment reminder for %(event)s") % context

    body = get_association_text(
        get_run_association_id(registration.run_id),
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
        _("Hello! You are registered for %(event)s, but we have not yet received your annual membership fee.") % context
    )

    # Add explanation about membership fee purpose
    email_body += "<br /><br />" + _(
        "Annual membership is mandatory for participation in all our live events, as it covers required liability insurance."
    )

    # Emphasize participation requirements
    email_body += "<br /><br />" + _("Without payment of this fee, event participation is not permitted.")

    # Provide payment link and support information
    membership_url = get_url("accounting_membership")
    email_body += get_payment_info(get_run_association_id(registration.run_id), membership_url)

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
        "memb_del": "Cancellation: Missing organization registration",
        "fee_del": "Cancellation: Missing annual membership fee",
        "pay_del": "Cancellation: Missing payment",
        "profile_del": "Cancellation: Missing profile",
        "memb": "Overdue: Organization registration",
        "fee": "Overdue: Annual membership fee",
        "pay": "Overdue: Payment",
        "profile": "Overdue: Profile completion",
        "cast": "Missing casting preferences",
    }

    for organizer in get_event_organizers_by_event(run.event_id):
        activate(organizer.language)
        subject = hdr_run(run.id) + _("Deadlines") + f" {run}"
        body = _("Review users with pending event deadlines:")
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
