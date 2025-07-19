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

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_assoc_features, get_event_features
from larpmanager.mail.base import notify_organization_exe
from larpmanager.models.access import get_event_organizers
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemOther,
    AccountingItemPayment,
    Collection,
    PaymentType,
)
from larpmanager.models.association import get_url, hdr
from larpmanager.models.member import Member
from larpmanager.utils.tasks import my_send_mail


@receiver(post_save, sender=AccountingItemExpense)
def update_accounting_item_expense_post(sender, instance, created, **kwargs):
    if instance.hide:
        return
    # Send email when the expenditure item is created the first time
    if created and instance.run and instance.run.event:
        for orga in get_event_organizers(instance.run.event):
            activate(orga.language)
            body, subj = get_expense_mail(instance)
            my_send_mail(subj, body, orga, instance.run)


def get_expense_mail(instance):
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
    url = f"{instance.run.event.slug}/{instance.run.number}/manage/expenses/approve/{instance.pk}"
    body += f"<a href='{url}'>" + _("Confirmation of expenditure") + "</a>"
    return body, subj


@receiver(pre_save, sender=AccountingItemExpense)
def update_accounting_item_expense_pre(sender, instance, **kwargs):
    if instance.hide:
        return
    if not instance.pk:
        return

    previous_appr = AccountingItemExpense.objects.get(pk=instance.pk).is_approved
    # Send email when the spending item is approved
    if not (instance.member and instance.is_approved and not previous_appr):
        return

    subj = hdr(instance) + _("Reimbursement approved")
    if instance.run:
        subj += " " + _("for") + f" {instance.run}"
    body = (
        _("Your request for reimbursement of %(amount).2f, with reason '%(reason)s', has been approved")
        % {
            "amount": instance.value,
            "reason": instance.descr,
        }
        + "!"
    )

    token_name, credit_name = get_token_credit_name(instance.assoc)

    if instance.run and "token_credit" in get_event_features(instance.run.event_id):
        body += "<br /><br /><i>" + _("The sum was assigned to you as %(credits)s") % {"credits": credit_name} + "."
        body += " " + _("This is automatically deducted from the registration of a future event") + "."
        body += (
            " "
            + _(
                "Alternatively, you can request to receive it with a formal request in the <a "
                "href='%(url)s'>your accounting.</a>."
            )
            % {"url": get_url("accounting", instance)}
            + "</i>"
        )
    my_send_mail(subj, body, instance.member, instance.run)


def get_token_credit_name(assoc):
    token_name = assoc.get_config("token_credit_token_name", None)
    credit_name = assoc.get_config("token_credit_credit_name", None)
    if not token_name:
        token_name = _("Tokens")
    if not credit_name:
        credit_name = _("Credits")
    return token_name, credit_name


@receiver(pre_save, sender=AccountingItemPayment)
def update_accounting_item_payment(sender, instance, **kwargs):
    if instance.hide:
        return

    run = instance.reg.run
    member = instance.reg.member

    if not run.event.assoc.get_config("mail_payment", False):
        return

    token_name, credit_name = get_token_credit_name(instance.assoc)

    curr_sym = run.event.assoc.get_currency_symbol()
    if not instance.pk:
        if instance.pay == AccountingItemPayment.MONEY:
            notify_pay_money(curr_sym, instance, member, run)
        elif instance.pay == AccountingItemPayment.CREDIT:
            notify_pay_credit(credit_name, instance, member, run)
        elif instance.pay == AccountingItemPayment.TOKEN:
            notify_pay_token(instance, member, run, token_name)


def notify_pay_token(instance, member, run, token_name):
    # to user
    activate(member.language)
    body, subj = get_pay_token_email(instance, run, token_name)
    my_send_mail(subj, body, member, run)
    # to orga
    for orga in get_event_organizers(run.event):
        activate(orga.language)
        body, subj = get_pay_token_email(instance, run, token_name)
        subj += _(" for %(user)s") % {"user": member}
        my_send_mail(subj, body, orga, run)


def get_pay_token_email(instance, run, token_name):
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
    return body, subj


def notify_pay_credit(credit_name, instance, member, run):
    # to user
    activate(member.language)
    body, subj = get_pay_credit_email(credit_name, instance, run)
    my_send_mail(subj, body, member, run)
    # to orga
    for orga in get_event_organizers(run.event):
        activate(orga.language)
        body, subj = get_pay_credit_email(credit_name, instance, run)
        subj += _(" for %(user)s") % {"user": member}
        my_send_mail(subj, body, orga, run)


def get_pay_credit_email(credit_name, instance, run):
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
    return body, subj


def notify_pay_money(curr_sym, instance, member, run):
    # to user
    activate(member.language)
    body, subj = get_pay_money_email(curr_sym, instance, run)
    my_send_mail(subj, body, member, run)
    # to orga
    for orga in get_event_organizers(run.event):
        activate(orga.language)
        body, subj = get_pay_money_email(curr_sym, instance, run)
        subj += _(" for %(user)s") % {"user": member}
        my_send_mail(subj, body, orga, run)


def get_pay_money_email(curr_sym, instance, run):
    subj = hdr(instance) + _("Payment per %(event)s") % {"event": run}
    body = (
        _("A payment of %(amount).2f %(currency)s was received for this event")
        % {
            "amount": instance.value,
            "currency": curr_sym,
        }
        + "!"
    )
    return body, subj


@receiver(pre_save, sender=AccountingItemOther)
def update_accounting_item_other(sender, instance, **kwargs):
    if instance.hide:
        return

    token_name, credit_name = get_token_credit_name(instance.assoc)

    if not instance.pk:
        if instance.oth == AccountingItemOther.TOKEN:
            notify_token(instance, token_name)
        elif instance.oth == AccountingItemOther.CREDIT:
            notify_credit(credit_name, instance)
        elif instance.oth == AccountingItemOther.REFUND:
            notify_refund(credit_name, instance)


def notify_refund(credit_name, instance):
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


@receiver(pre_save, sender=AccountingItemDonation)
def save_accounting_item_donation(sender, instance, *args, **kwargs):
    if instance.hide:
        return
    if instance.pk:
        return
        # to user
    activate(instance.member.language)
    subj = hdr(instance) + _("Donation given")
    body = _(
        "We confirm we received the donation of %(amount)d %(currency)s. We thank you for your "
        "support, and for believing in us!"
    ) % {"amount": instance.value, "currency": instance.assoc.get_currency_symbol()}
    my_send_mail(subj, body, instance.member, instance)


@receiver(post_save, sender=Collection)
def send_collection_activation_email(sender, instance, created, **kwargs):
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
    return


@receiver(pre_save, sender=AccountingItemCollection)
def save_collection_gift(sender, instance, **kwargs):
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
        return


def notify_invoice_check(inv):
    if not inv.assoc.get_config("mail_payment", False):
        return

    # if there is treasurer features, send to them
    features = get_assoc_features(inv.assoc_id)
    if "treasurer" in features:
        for mb in inv.assoc.get_config("treasurer_appointees", "").split(", "):
            idx = int(mb)
            orga = Member.objects.get(pk=idx)
            activate(orga.language)
            body, subj = get_invoice_email(inv)
            my_send_mail(subj, body, orga, inv)

    # if it is for a sign up, send the confirmation to the organizers
    elif inv.typ == PaymentType.REGISTRATION and inv.reg:
        for orga in get_event_organizers(inv.reg.run.event):
            activate(orga.language)
            body, subj = get_invoice_email(inv)
            my_send_mail(subj, body, orga, inv)

    # if nothing else applies, simply send to the main mail
    else:
        body, subj = get_invoice_email(inv)
        notify_organization_exe(subj, body, inv.assoc, inv)


def notify_refund_request(p):
    subj = hdr(p) + _("Request refund from: %(user)s") % {"user": p.member}
    body = _("Details: %(details)s (<b>%(amount).2f</b>)") % {"details": p.details, "amount": p.value}
    # print(subj)
    notify_organization_exe(subj, body, p.assoc, p.assoc)


def get_invoice_email(inv):
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
    return body, subj
