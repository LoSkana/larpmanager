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

from larpmanager.cache.config import get_assoc_config
from larpmanager.cache.feature import get_assoc_features, get_event_features
from larpmanager.mail.base import notify_organization_exe
from larpmanager.models.access import get_event_organizers
from larpmanager.models.accounting import (
    AccountingItemExpense,
    OtherChoices,
    PaymentChoices,
    PaymentType,
)
from larpmanager.models.association import get_url, hdr
from larpmanager.models.member import Member
from larpmanager.utils.tasks import my_send_mail


def send_expense_notification_email(instance, created):
    """Handle post-save events for expense accounting items.

    Args:
        instance: AccountingItemExpense instance that was saved
        created: Boolean indicating if instance was created
    """
    if instance.hide:
        return
    # Send email when the expenditure item is created the first time
    if created and instance.run and instance.run.event:
        for orga in get_event_organizers(instance.run.event):
            activate(orga.language)
            subj, body = get_expense_mail(instance)
            my_send_mail(subj, body, orga, instance.run)


def get_expense_mail(instance):
    """Generate email subject and body for expense reimbursement requests.

    Args:
        instance: AccountingItemExpense instance

    Returns:
        Tuple of (subject, body) strings for expense notification email
    """
    subj = hdr(instance) + _("Reimbursement request for %(event)s") % {"event": instance.run}
    body = _("Staff member %(user)s added a new reimbursement request for %(event)s") % {
        "user": instance.member,
        "event": instance.run,
    }
    body += (
        "<br /><br />"
        + _("The sum is %(amount).2f, with reason '%(reason)s'")
        % {
            "amount": instance.value,
            "reason": instance.descr,
        }
        + "."
    )
    url = get_url(instance.download(), instance)
    body += f"<br /><br /><a href='{url}'>" + _("download document") + "</a>"
    body += "<br /><br />" + _("Did you check and is it correct") + "?"
    url = f"{instance.run.get_slug()}/manage/expenses/approve/{instance.pk}"
    body += f"<a href='{url}'>" + _("Confirmation of expenditure") + "</a>"
    return subj, body


def send_expense_approval_email(expense_item):
    """Handle expense item approval notifications.

    Args:
        expense_item: AccountingItemExpense instance being saved
    """
    if expense_item.hide:
        return
    if not expense_item.pk:
        return

    previous_appr = AccountingItemExpense.objects.get(pk=expense_item.pk).is_approved
    # Send email when the spending item is approved
    if not (expense_item.member and expense_item.is_approved and not previous_appr):
        return

    subj = hdr(expense_item) + _("Reimbursement approved")
    if expense_item.run:
        subj += " " + _("for") + f" {expense_item.run}"
    body = (
        _("Your request for reimbursement of %(amount).2f, with reason '%(reason)s', has been approved")
        % {
            "amount": expense_item.value,
            "reason": expense_item.descr,
        }
        + "!"
    )

    token_name, credit_name = get_token_credit_name(expense_item.assoc_id)

    if expense_item.run and "token_credit" in get_event_features(expense_item.run.event_id):
        body += "<br /><br /><i>" + _("The sum was assigned to you as %(credits)s") % {"credits": credit_name} + "."
        body += " " + _("This is automatically deducted from the registration of a future event") + "."
        body += (
            " "
            + _(
                "Alternatively, you can request to receive it with a formal request in the <a "
                "href='%(url)s'>your accounting.</a>."
            )
            % {"url": get_url("accounting", expense_item)}
            + "</i>"
        )
    my_send_mail(subj, body, expense_item.member, expense_item.run)


def get_token_credit_name(assoc_id):
    """Get token and credit names from association configuration.

    Args:
        assoc_id: id of Association

    Returns:
        Tuple of (token_name, credit_name) strings with defaults if not configured
    """
    token_name = get_assoc_config(assoc_id, "token_credit_token_name", None)
    credit_name = get_assoc_config(assoc_id, "token_credit_credit_name", None)
    if not token_name:
        token_name = _("Tokens")
    if not credit_name:
        credit_name = _("Credits")
    return token_name, credit_name


def send_payment_confirmation_email(payment_item):
    """Handle pre-save events for payment accounting items.

    Args:
        payment_item: AccountingItemPayment instance being saved
    """
    if payment_item.hide:
        return

    run = payment_item.reg.run
    member = payment_item.reg.member

    if not get_assoc_config(run.event.assoc_id, "mail_payment", False):
        return

    token_name, credit_name = get_token_credit_name(payment_item.assoc_id)

    curr_sym = run.event.assoc.get_currency_symbol()
    if not payment_item.pk:
        if payment_item.pay == PaymentChoices.MONEY:
            notify_pay_money(curr_sym, payment_item, member, run)
        elif payment_item.pay == PaymentChoices.CREDIT:
            notify_pay_credit(credit_name, payment_item, member, run)
        elif payment_item.pay == PaymentChoices.TOKEN:
            notify_pay_token(payment_item, member, run, token_name)


def notify_pay_token(instance, member, run, token_name):
    """Send token payment notifications to user and organizers.

    Args:
        instance: Payment accounting item instance
        member: Member who made the payment
        run: Event run object
        token_name: Name of the token currency
    """
    # to user
    activate(member.language)
    subj, body = get_pay_token_email(instance, run, token_name)
    my_send_mail(subj, body, member, run)
    # to orga
    for orga in get_event_organizers(run.event):
        activate(orga.language)
        subj, body = get_pay_token_email(instance, run, token_name)
        subj += _(" for %(user)s") % {"user": member}
        my_send_mail(subj, body, orga, run)


def get_pay_token_email(instance, run, token_name):
    """Generate email content for token payment notifications.

    Args:
        instance: Payment accounting item instance
        run: Event run object
        token_name: Name of the token currency

    Returns:
        Tuple of (subject, body) strings for token payment email
    """
    subj = hdr(instance) + _("Utilisation %(tokens)s per %(event)s") % {
        "tokens": token_name,
        "event": run,
    }
    body = (
        _("%(amount)d %(tokens)s were used to participate in this event")
        % {
            "amount": int(instance.value),
            "tokens": token_name,
        }
        + "!"
    )
    return subj, body


def notify_pay_credit(credit_name, instance, member, run):
    """Send credit payment notifications to user and organizers.

    Args:
        credit_name: Name of the credit currency
        instance: Payment accounting item instance
        member: Member who made the payment
        run: Event run object
    """
    # to user
    activate(member.language)
    subj, body = get_pay_credit_email(credit_name, instance, run)
    my_send_mail(subj, body, member, run)
    # to orga
    for orga in get_event_organizers(run.event):
        activate(orga.language)
        subj, body = get_pay_credit_email(credit_name, instance, run)
        subj += _(" for %(user)s") % {"user": member}
        my_send_mail(subj, body, orga, run)


def get_pay_credit_email(credit_name, instance, run):
    """Generate email content for credit payment notifications.

    Args:
        credit_name: Name of the credit currency
        instance: Payment accounting item instance
        run: Event run object

    Returns:
        Tuple of (subject, body) strings for credit payment email
    """
    subj = hdr(instance) + _("Utilisation %(credits)s per %(event)s") % {
        "credits": credit_name,
        "event": run,
    }
    body = (
        _("%(amount)d %(credits)s were used to participate in this event")
        % {
            "amount": int(instance.value),
            "credits": credit_name,
        }
        + "!"
    )
    return subj, body


def notify_pay_money(curr_sym, instance, member, run):
    """Send money payment notifications to user and organizers.

    Args:
        curr_sym: Currency symbol
        instance: Payment accounting item instance
        member: Member who made the payment
        run: Event run object
    """
    # to user
    activate(member.language)
    subj, body = get_pay_money_email(curr_sym, instance, run)
    my_send_mail(subj, body, member, run)
    # to orga
    for orga in get_event_organizers(run.event):
        activate(orga.language)
        subj, body = get_pay_money_email(curr_sym, instance, run)
        subj += _(" for %(user)s") % {"user": member}
        my_send_mail(subj, body, orga, run)


def get_pay_money_email(curr_sym, instance, run):
    """Generate email content for money payment notifications.

    Args:
        curr_sym: Currency symbol
        instance: Payment accounting item instance
        run: Event run object

    Returns:
        Tuple of (subject, body) strings for money payment email
    """
    subj = hdr(instance) + _("Payment for %(event)s") % {"event": run}
    body = (
        _("A payment of %(amount).2f %(currency)s was received for this event")
        % {
            "amount": instance.value,
            "currency": curr_sym,
        }
        + "!"
    )
    return subj, body


def send_token_credit_notification_email(instance):
    """Handle pre-save events for other accounting items.

    Args:
        instance: AccountingItemOther instance being saved
    """
    if instance.hide:
        return

    token_name, credit_name = get_token_credit_name(instance.assoc_id)

    if not instance.pk:
        if instance.oth == OtherChoices.TOKEN:
            notify_token(instance, token_name)
        elif instance.oth == OtherChoices.CREDIT:
            notify_credit(credit_name, instance)
        elif instance.oth == OtherChoices.REFUND:
            notify_refund(credit_name, instance)


def notify_refund(credit_name, instance):
    """Send refund notifications to user and organizers.

    Args:
        credit_name: Name of the credit currency
        instance: Accounting item instance for refund
    """
    # to user
    activate(instance.member.language)
    subj = hdr(instance) + _("Issued Reimbursement")
    body = (
        _(
            "A reimbursement for '%(reason)s' has been marked as issued. %(amount).2f %(elements)s have been marked as used"
        )
        % {
            "amount": instance.value,
            "elements": credit_name,
            "reason": instance.descr,
        }
        + "."
    )
    my_send_mail(subj, body, instance.member, instance)


def notify_credit(credit_name, instance):
    """Send credit notification emails to users.

    Args:
        credit_name: Name of the credit type being assigned
        instance: Credit instance with member and amount information

    Side effects:
        Sends email notifications to user and event organizers
    """
    # to user
    activate(instance.member.language)
    subj, body = get_credit_email(credit_name, instance)
    url = get_url("accounting", instance)
    add_body = (
        " <br /><br /><i>"
        + _("They will be used automatically when you sign up for a new event")
        + "!"
        + "<br /><br />"
        + _("Alternatively, you can request a reimbursement in <a href='%(url)s'>your accounting</a>.</i>")
        % {"url": url}
    )
    my_send_mail(subj, body + add_body, instance.member, instance)
    # to orga
    if instance.run:
        for orga in get_event_organizers(instance.run.event):
            activate(orga.language)
            subj, body = get_credit_email(credit_name, instance)
            subj += _(" for %(user)s") % {"user": instance.member}
            my_send_mail(subj, body, orga, instance)


def get_credit_email(credit_name, instance):
    """Generate email subject and body for credit assignment notification.

    Args:
        credit_name: Name of the credit type being assigned
        instance: AccountingItem instance containing credit details

    Returns:
        tuple: (subject, body) strings for the email
    """
    subj = hdr(instance) + _("Assignment %(elements)s") % {
        "elements": credit_name,
    }
    if instance.run:
        subj += " " + _("for") + " " + str(instance.run)
    body = (
        _("Assigned %(amount).2f %(elements)s for '%(reason)s'")
        % {
            "amount": instance.value,
            "elements": credit_name,
            "reason": instance.descr,
        }
        + "."
    )
    return subj, body


def notify_token(instance, token_name):
    # to user
    activate(instance.member.language)
    subj, body = get_token_email(instance, token_name)
    add_body = "<br /><br /><i>" + _("They will be used automatically when you sign up for a new event") + "!" + "</i>"
    my_send_mail(subj, body + add_body, instance.member, instance)
    # to orga
    if instance.run:
        for orga in get_event_organizers(instance.run.event):
            activate(orga.language)
            subj, body = get_token_email(instance, token_name)
            subj += _(" for %(user)s") % {"user": instance.member}
            my_send_mail(subj, body, orga, instance)


def get_token_email(instance, token_name):
    """Generate email subject and body for token assignment notification.

    Args:
        instance: AccountingItem instance containing token details
        token_name: Name of the token type being assigned

    Returns:
        tuple: (subject, body) strings for the email
    """
    subj = hdr(instance) + _("Assignment %(elements)s") % {
        "elements": token_name,
    }
    if instance.run:
        subj += " " + _("for") + " " + str(instance.run)
    body = (
        _("Assigned %(amount).2f %(elements)s for '%(reason)s'")
        % {
            "amount": int(instance.value),
            "elements": token_name,
            "reason": instance.descr,
        }
        + "."
    )
    return subj, body


def send_donation_confirmation_email(instance):
    """Handle pre-save events for donation accounting items.

    Args:
        instance: AccountingItemDonation instance being saved
    """
    if instance.hide:
        return
    if instance.pk:
        return

    activate(instance.member.language)
    subj = hdr(instance) + _("Donation given")
    body = _(
        "We confirm we received the donation of %(amount)d %(currency)s. We thank you for your "
        "support, and for believing in us!"
    ) % {"amount": instance.value, "currency": instance.assoc.get_currency_symbol()}
    my_send_mail(subj, body, instance.member, instance)


def send_collection_activation_email(instance, created):
    """Handle post-save events for collection instances.

    Args:
        instance: Collection instance that was saved
        created: Boolean indicating if instance was created
    """
    if not created:
        return

    context = {
        "recipient": instance.display_member(),
        "url": get_url(f"accounting/collection/{instance.contribute_code}/", instance),
    }

    activate(instance.organizer.language)
    subj = hdr(instance) + _("Activate collection for: %(recipient)s") % context
    body = (
        _(
            "We confirm that the collection for '%(recipient)s' has been activated. <a "
            "href='%(url)s'>Manage it here!</a>"
        )
        % context
    )
    my_send_mail(subj, body, instance.organizer, instance)


def send_gift_collection_notification_email(instance):
    """
    Send notification emails when gift collection participation is saved.

    Args:
        instance: Collection gift instance
    """
    if not instance.pk:
        activate(instance.member.language)
        subj = hdr(instance.collection) + _("Collection participation for: %(recipient)s") % {
            "recipient": instance.collection.display_member()
        }
        body = (
            _("We thank you for participating in the collection: we are sure they will live a terrific experience")
            + "!"
        )
        my_send_mail(subj, body, instance.member, instance.collection)

        activate(instance.collection.organizer.language)
        subj = hdr(instance.collection) + _("New participation in the collection for %(recipient)s by %(user)s") % {
            "recipient": instance.collection.display_member(),
            "user": instance.member.display_member(),
        }
        body = (
            _("The collection grows: we have no doubt, the fortunate will live soon an unprecedented experience") + "!"
        )
        my_send_mail(subj, body, instance.collection.organizer, instance.collection)


def notify_invoice_check(inv):
    """Send invoice check notifications to appropriate recipients.

    Args:
        inv: Invoice object to send notifications for
    """
    if not get_assoc_config(inv.assoc_id, "mail_payment", False):
        return

    # if there is treasurer features, send to them
    features = get_assoc_features(inv.assoc_id)
    if "treasurer" in features:
        for mb in get_assoc_config(inv.assoc_id, "treasurer_appointees", "").split(", "):
            idx = int(mb)
            orga = Member.objects.get(pk=idx)
            activate(orga.language)
            subj, body = get_invoice_email(inv)
            my_send_mail(subj, body, orga, inv)

    # if it is for a sign up, send the confirmation to the organizers
    elif inv.typ == PaymentType.REGISTRATION and inv.reg:
        for orga in get_event_organizers(inv.reg.run.event):
            activate(orga.language)
            subj, body = get_invoice_email(inv)
            my_send_mail(subj, body, orga, inv)

    # if nothing else applies, simply send to the main mail
    else:
        notify_organization_exe(get_invoice_email, inv.assoc, inv)


def notify_refund_request(p):
    notify_organization_exe(get_notify_refund_email, p.assoc, p)


def get_notify_refund_email(p):
    """Generate email subject and body for refund request notification.

    Args:
        p: Payment object containing refund request details

    Returns:
        Tuple of (subject, body) strings for refund notification email
    """
    subj = hdr(p) + _("Request refund from: %(user)s") % {"user": p.member}
    body = _("Details: %(details)s (<b>%(amount).2f</b>)") % {"details": p.details, "amount": p.value}
    return subj, body


def get_invoice_email(inv):
    """Generate email subject and body for invoice payment verification.

    Args:
        inv: Invoice object to generate email content for

    Returns:
        Tuple of (subject, body) strings for the payment verification email
    """
    body = _("Verify that the data are correct") + ":"
    body += "<br /><br />" + _("Reason for payment") + f": <b>{inv.causal}</b>"
    body += "<br /><br />" + _("Amount") + f": <b>{inv.mc_gross:.2f}</b>"
    if inv.invoice:
        url = get_url(inv.download(), inv)
        body += f"<br /><br /><a href='{url}'>" + _("Download document") + "</a>"
    elif inv.method and inv.method.slug == "any":
        body += f"<br /><br /><i>{inv.text}</i>"
    body += "<br /><br />" + _("Did you check and is it correct") + "?"
    url = get_url("accounting/confirm", inv)
    body += f" <a href='{url}/{inv.cod}'>" + _("Payment confirmation") + "</a>"
    causal = inv.causal
    if "-" in causal:
        causal = causal.split("-", 1)[1].strip()
    subj = hdr(inv) + _("Payment to check") + ": " + causal
    return subj, body
