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
from larpmanager.utils.deadlines import check_run_deadlines
from larpmanager.utils.tasks import my_send_mail
from larpmanager.utils.text import get_assoc_text


def remember_membership(reg):
    """Send membership reminder email to registered user.

    Args:
        reg: Registration instance needing membership confirmation

    Side effects:
        Sends email reminder about membership requirement
    """
    activate(reg.member.language)

    subj = hdr(reg.run.event) + _("Confirmation of registration for %(event)s") % {"event": reg.run}

    body = get_assoc_text(reg.run.event.assoc_id, AssocTextType.REMINDER_MEMBERSHIP) or get_remember_membership_body(
        reg
    )

    my_send_mail(subj, body, reg.member, reg.run)


def get_remember_membership_body(reg):
    """Generate default membership reminder email body text.

    Args:
        reg: Registration instance

    Returns:
        str: HTML formatted email body for membership reminder
    """
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

    body += (
        "<br /><br />("
        + _("If you need a hand, feel free to let us know")
        + ". "
        + _("We'll try to help as best we can")
        + "!)"
    )

    body += (
        "<br /><br />"
        + _("If we don't hear from you, we'll assume you're no longer interested in the event")
        + ". "
        + _("Your registration will be cancelled to allow other participants to take your spot")
        + "."
    )

    return body


def remember_pay(reg):
    """Send payment reminder email to registered user.

    Args:
        reg: Registration instance with pending payment

    Side effects:
        Sends email reminder about payment requirement
    """
    activate(reg.member.language)

    provisional = is_reg_provisional(reg)
    context = {"event": reg.run}

    if provisional:
        subj = hdr(reg.run.event) + _("Confirm registration to %(event)s") % context
    else:
        subj = hdr(reg.run.event) + _("Complete payment for %(event)s") % context

    body = get_assoc_text(reg.run.event.assoc_id, AssocTextType.REMINDER_PAY) or get_remember_pay_body(
        context, provisional, reg
    )

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


def remember_profile(reg):
    """Send profile completion reminder email to registered user.

    Args:
        reg: Registration instance with incomplete profile

    Side effects:
        Sends email reminder about profile completion requirement
    """
    activate(reg.member.language)
    context = {"event": reg.run, "url": get_url("profile", reg.run.event)}

    subj = hdr(reg.run.event) + _("Profile compilation reminder for %(event)s") % context

    body = get_assoc_text(reg.run.event.assoc_id, AssocTextType.REMINDER_PROFILE) or get_remember_profile_body(context)

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


def remember_membership_fee(reg):
    """Send membership fee reminder email to registered user.

    Args:
        reg: Registration instance needing membership fee payment

    Side effects:
        Sends email reminder about annual membership fee requirement
    """
    activate(reg.member.language)
    context = {"event": reg.run}

    subj = hdr(reg.run.event) + _("Reminder payment of membership fees for %(event)s") % context

    body = get_assoc_text(
        reg.run.event.assoc_id, AssocTextType.REMINDER_MEMBERSHIP_FEE
    ) or get_remember_membership_fee_body(context, reg)

    my_send_mail(subj, body, reg.member, reg.run)


def get_remember_membership_fee_body(context, reg):
    """Generate default membership fee reminder email body text.

    Args:
        context (dict): Email context with event information
        reg: Registration instance with fee payment details

    Returns:
        str: HTML formatted email body for membership fee reminder
    """
    body = (
        _("Hello! You have registered for %(event)s, but we have not yet received your annual membership payment")
        % context
        + "."
    )

    body += (
        "<br /><br />"
        + _("It is required for participation in all our live events, as it also covers the insurance fee")
        + "."
    )

    body += (
        "<br /><br />"
        + _("Unfortunately, without full payment of the fee, participation in the event is not permitted")
        + "."
    )

    body += (
        "<br /><br />"
        + _("You can complete the payment in just a few minutes <a href='%(url)s'>here</a>")
        % {"url": get_url("accounting", reg.run.event)}
        + ". "
        + _("Let us know if you encounter any issues or need assistance")
        + "!"
    )
    return body


def notify_deadlines(run):
    """Send deadline notification emails to event organizers.

    Args:
        run: Run instance with approaching deadlines

    Side effects:
        Sends deadline reminder emails to all event organizers
    """
    result = check_run_deadlines([run])
    if not result:
        return
    res = result[0]
    if all(not v for k, v in res.items() if k != "run"):
        return

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

    for orga in get_event_organizers(run.event):
        activate(orga.language)
        subj = hdr(run.event) + _("Deadlines") + f" {run}"
        body = _("Review the users that are missing the event's deadlines")
        for key, descr in elements.items():
            if key not in res or not res[key]:
                continue

            # add description
            body += "<br /><br /><h2>" + _(descr) + "</h2>"
            # Add names
            body += f"<p>{', '.join([el[0] for el in res[key]])}</p>"
            # Add emails
            body += f"<p>{', '.join([el[1] for el in res[key]])}</p>"

        my_send_mail(subj, body, orga, run)
