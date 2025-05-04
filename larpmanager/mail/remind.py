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

from larpmanager.models.access import get_event_organizers
from larpmanager.models.association import AssocTextType, get_url, hdr
from larpmanager.utils.deadlines import check_run_deadlines
from larpmanager.utils.registration import is_reg_provisional
from larpmanager.utils.tasks import my_send_mail
from larpmanager.utils.text import get_assoc_text


def remember_membership(reg):
    activate(reg.member.language)

    subj = hdr(reg.run.event) + _("Confirmation of registration for %(event)s") % {"event": reg.run}

    body = get_assoc_text(reg.run.event.assoc_id, AssocTextType.REMINDER_MEMBERSHIP) or get_remember_membership_body(
        reg
    )

    my_send_mail(subj, body, reg.member, reg.run)


def get_remember_membership_body(reg):
    body = _(
        "Hello! We would like to remind you that in order to confirm your provisional "
        "registration of %(event)s you need to apply for admission as a member of the "
        "association. You are very close, just <a href='%(url)s'>click here</a> and "
        "complete the form."
    ) % {"event": reg.run, "url": get_url("membership")}

    body += "<br /><br />" + _("(If you need a hand feel free to let us know, we'll try to help as best we can!)")

    body += "<br /><br />" + _(
        "If we don't hear from you, we'll understand that you're no longer interested at "
        "the event and we will cancel your registration, so that other players can signup "
        "to your place."
    )
    return body


def remember_pay(reg):
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


def get_remember_pay_body(context, provisional, reg):
    symbol = reg.run.event.assoc.get_currency_symbol()
    amount = f"{reg.quota:.2f}{symbol}"
    deadline = reg.deadline
    url = get_url("accounting/pay", reg.run.event)
    payment_url = f"{url}/{reg.run.event.slug}/{reg.id}"

    if provisional:
        body = _("Hello! We are contacting you regarding your provisional registration at <b>%(event)s</b>.") % context
    else:
        body = _("Hello! We are contacting you regarding your registration at <b>%(event)s</b>.") % context

    if deadline <= 0:
        body += "<br /><br />" + _("To confirm it, we ask you to pay this amount as soon as possible: %(amount)s.") % {
            "amount": amount
        }

    else:
        body += "<br /><br />" + _(
            "To confirm it, we ask you to pay this amount: %(amount)s, within this number of days: %(days)s."
        ) % {"amount": amount, "days": deadline}

    body += "<br /><br />" + _(
        "(Please note that if you have with us a different agreement, you can safely ignore this email!)"
    )

    body += "<br /><br />" + _(
        "You can make the payment <a href= %(url)s'>on this page</a>. If you encounter "
        "any kind of problem, let us know, we will help you solve it!"
    ) % {"url": payment_url}

    body += "<br /><br />" + _(
        "If we don't hear from you, we'll understand that you're no longer interested at "
        "the event and we will cancel your registration, so that other players can signup "
        "to your place."
    )

    return body


def remember_profile(reg):
    activate(reg.member.language)
    context = {"event": reg.run, "url": get_url("profile", reg.run.event)}

    subj = hdr(reg.run.event) + _("Profile compilation reminder for %(event)s") % context

    body = get_assoc_text(reg.run.event.assoc_id, AssocTextType.REMINDER_PROFILE) or get_remember_profile_body(context)

    my_send_mail(subj, body, reg.member, reg.run)


def get_remember_profile_body(context):
    return (
        _(
            "Hello! You have signed up for %(event)s, but have not yet completed your "
            "profile. It takes 5 minutes, just <a href='%(url)s'>click here</a> and complete "
            "the form!"
        )
        % context
    )


def remember_membership_fee(reg):
    activate(reg.member.language)
    context = {"event": reg.run}

    subj = hdr(reg.run.event) + _("Reminder payment of membership fees for %(event)s") % context

    body = get_assoc_text(
        reg.run.event.assoc_id, AssocTextType.REMINDER_MEMBERSHIP_FEE
    ) or get_remember_membership_fee_body(context, reg)

    my_send_mail(subj, body, reg.member, reg.run)


def get_remember_membership_fee_body(context, reg):
    body = (
        _("Hello! You have registered for %(event)s, but we have not yet received your annual membership fee payment.")
        % context
    )
    body += "<br /><br />" + _(
        "It is compulsory to take part in all our live events, as it also includes the insurance fee."
    )
    body += "<br /><br />" + _(
        "Unfortunately, without the balance of the fee, it is NOT possible for us to let you participate at the event."
    )
    body += "<br /><br />" + _(
        "You can make the payment in just a few minutes <a href= %(url)s'>here</a>. Let "
        "us know if you encounter any problems, or if we can help in any way!"
    ) % {"url": get_url("accounting", reg.run.event)}
    return body


def notify_deadlines(run):
    result = check_run_deadlines([run])
    if not result:
        return
    res = result[0]
    if not any(res.values()):
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
