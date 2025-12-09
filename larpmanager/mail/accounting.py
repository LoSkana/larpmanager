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

from larpmanager.cache.config import get_association_config
from larpmanager.cache.feature import get_association_features, get_event_features
from larpmanager.mail.base import notify_organization_exe
from larpmanager.models.access import get_event_organizers
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemOther,
    AccountingItemPayment,
    OtherChoices,
    PaymentChoices,
    PaymentInvoice,
    PaymentType,
)
from larpmanager.models.association import get_url, hdr
from larpmanager.models.event import Run
from larpmanager.models.member import Member
from larpmanager.utils.larpmanager.tasks import my_send_mail


def send_expense_notification_email(instance: AccountingItemExpense) -> None:
    """Send email notification to event organizers when an expense is created.

    This function handles post-save events for expense accounting items by sending
    notification emails to all event organizers when a new expense item is created.
    No notification is sent for hidden expenses or when updating existing expenses.

    Args:
        instance: The AccountingItemExpense instance that was saved

    Returns:
        None

    """
    # Skip notification if expense is marked as hidden
    if instance.hide:
        return

    # Only send email notifications for newly created expenses
    # that are associated with a run and event
    if instance.run and instance.run.event:
        # Iterate through all organizers for the event
        for organizer in get_event_organizers(instance.run.event):
            # Set the language context for the organizer
            activate(organizer.language)

            # Generate email subject and body content
            subject, body = get_expense_mail(instance)

            # Send the notification email to the organizer
            my_send_mail(subject, body, organizer, instance.run)


def get_expense_mail(instance: AccountingItemExpense) -> tuple[str, str]:
    """Generate email subject and body for expense reimbursement requests.

    Creates notification email content for staff expense reimbursement requests,
    including approval links and document download functionality.

    Args:
        instance: AccountingItemExpense instance containing expense details

    Returns:
        Tuple containing email subject and HTML body as strings

    """
    # Generate email subject with event context
    email_subject = hdr(instance) + _("Reimbursement request for %(event)s") % {"event": instance.run}

    # Create initial body with staff member and event information
    email_body = _("Staff member %(user)s added a new reimbursement request for %(event)s") % {
        "user": instance.member,
        "event": instance.run,
    }

    # Add expense amount and reason details
    email_body += (
        "<br /><br />"
        + _("The sum is %(amount).2f, with reason '%(reason)s'")
        % {
            "amount": instance.value,
            "reason": instance.descr,
        }
        + "."
    )

    # Add document download link if available
    document_download_url = get_url(instance.download(), instance)
    email_body += f"<br /><br /><a href='{document_download_url}'>" + _("download document") + "</a>"

    # Add approval prompt and confirmation link
    email_body += "<br /><br />" + _("Did you check and is it correct") + "?"
    approval_url = f"{instance.run.get_slug()}/manage/expenses/approve/{instance.pk}"
    email_body += f"<a href='{approval_url}'>" + _("Confirmation of expenditure") + "</a>"

    return email_subject, email_body


def send_expense_approval_email(expense_item: AccountingItemExpense) -> None:
    """Handle expense item approval notifications.

    Sends an email notification to the member when their expense reimbursement
    request is approved. The email includes approval details and information
    about credit assignment for future events if applicable.

    Args:
        expense_item: AccountingItemExpense instance being saved

    Returns:
        None

    """
    # Skip hidden or new expense items
    if expense_item.hide:
        return
    if not expense_item.pk:
        return

    # Get previous approval status to detect state change
    previous_approval_status = AccountingItemExpense.objects.get(pk=expense_item.pk).is_approved

    # Only send email when item is newly approved and has an associated member
    if not (expense_item.member and expense_item.is_approved and not previous_approval_status):
        return

    # Build email subject with optional run information
    email_subject = hdr(expense_item) + _("Reimbursement approved")
    if expense_item.run:
        email_subject += " " + _("for") + f" {expense_item.run}"

    # Create base email body with approval details
    email_body = (
        _("Your request for reimbursement of %(amount).2f, with reason '%(reason)s', has been approved")
        % {
            "amount": expense_item.value,
            "reason": expense_item.descr,
        }
        + "!"
    )

    # Get token and credit names for the association
    _token_name, credits_name = get_token_credit_name(expense_item.association_id)

    # Add credit information if run has credits feature enabled
    event_features = get_event_features(expense_item.run.event_id) if expense_item.run else {}
    if expense_item.run and "credits" in event_features:
        email_body += (
            "<br /><br /><i>" + _("The sum was assigned to you as %(credits)s") % {"credits": credits_name} + "."
        )
        email_body += " " + _("This is automatically deducted from the registration of a future event") + "."

        # Add link to accounting page for formal request option
        email_body += (
            " "
            + _(
                "Alternatively, you can request to receive it with a formal request in the <a "
                "href='%(url)s'>your accounting.</a>.",
            )
            % {"url": get_url("accounting", expense_item)}
            + "</i>"
        )

    # Send the notification email
    my_send_mail(email_subject, email_body, expense_item.member, expense_item.run)


def get_token_credit_name(association_id: int) -> tuple[str, str]:
    """Get token and credit names from association configuration.

    Retrieves custom token and credit names from the association's configuration,
    falling back to default translated names if not configured.

    Args:
        association_id: ID of the Association to get configuration from.

    Returns:
        A tuple containing (tokens_name, credits_name) as strings. Returns
        default translated values if custom names are not configured.

    """
    # Create configuration holder for caching retrieved values
    association_config_cache = {}

    # Retrieve custom token and credit names from association config
    tokens_name = get_association_config(
        association_id, "tokens_name", default_value=None, context=association_config_cache
    )
    credits_name = get_association_config(
        association_id, "credits_name", default_value=None, context=association_config_cache
    )

    # Apply default translated names if custom names not configured
    if not tokens_name:
        tokens_name = _("Tokens")
    if not credits_name:
        credits_name = _("Credits")

    return tokens_name, credits_name


def send_payment_confirmation_email(payment_item: AccountingItemPayment) -> None:
    """Send payment confirmation email to member after payment processing.

    Sends appropriate notification email based on payment type (money, credit, or token)
    if email notifications are enabled for the association and the payment item
    is not hidden.

    Args:
        payment_item: AccountingItemPayment instance being saved. Must have
            reg (registration), pay (payment type), and association_id attributes.

    Returns:
        None

    Note:
        Email is only sent if:
        - payment_item.hide is False
        - Association has mail_payment config enabled
        - payment_item is being created (no existing pk)

    """
    # Early return if payment should be hidden from notifications
    if payment_item.hide:
        return

    # Extract related objects for email context
    event_run = payment_item.reg.run
    registered_member = payment_item.reg.member

    # Check if payment notifications are enabled for this association
    if not get_association_config(event_run.event.association_id, "mail_payment", default_value=False):
        return

    # Get localized names for tokens and credits
    tokens_name, credits_name = get_token_credit_name(payment_item.association_id)

    # Get currency symbol for money payments
    currency_symbol = event_run.event.association.get_currency_symbol()

    # Only send notification for new payment items (not updates)
    if not payment_item.pk:
        # Send appropriate notification based on payment type
        if payment_item.pay == PaymentChoices.MONEY:
            notify_pay_money(currency_symbol, payment_item, registered_member, event_run)
        elif payment_item.pay == PaymentChoices.CREDIT:
            notify_pay_credit(credits_name, payment_item, registered_member, event_run)
        elif payment_item.pay == PaymentChoices.TOKEN:
            notify_pay_token(payment_item, registered_member, event_run, tokens_name)


def notify_pay_token(instance: AccountingItemPayment, member: Member, run: Run, tokens_name: str) -> None:
    """Send token payment notifications to user and organizers.

    Sends payment confirmation emails to both the paying member and all event
    organizers. Each recipient receives the email in their preferred language.

    Args:
        instance: Payment accounting item instance containing payment details
        member: Member who made the payment
        run: Event run object for the payment context
        tokens_name: Name of the token currency being paid

    Returns:
        None

    """
    # Send notification to the paying user
    activate(member.language)
    subject, body = get_pay_token_email(instance, run, tokens_name)
    my_send_mail(subject, body, member, run)

    # Send notifications to all event organizers
    for organizer in get_event_organizers(run.event):
        # Set organizer's preferred language for localized email
        activate(organizer.language)
        subject, body = get_pay_token_email(instance, run, tokens_name)

        # Add member identification to organizer's subject line
        subject += _(" for %(user)s") % {"user": member}
        my_send_mail(subject, body, organizer, run)


def get_pay_token_email(instance: AccountingItemPayment, run: Run, tokens_name: str) -> tuple[str, str]:
    """Generate email content for token payment notifications.

    Creates localized email subject and body text for notifications sent when
    tokens are used to pay for event participation.

    Args:
        instance: Payment accounting item instance containing token amount
        run: Event run object representing the event
        tokens_name: Name of the token currency being used

    Returns:
        Tuple containing:
            - subject (str): Localized email subject line
            - body (str): Localized email body content

    Example:
        >>> subject, body = get_pay_token_email(payment, event_run, "Credits")
        >>> print(subject)  # "Payment: Credit usage for Summer Event 2023"

    """
    # Generate localized subject line with event and token information
    subject = hdr(instance) + _("Utilisation %(tokens)s per %(event)s") % {
        "tokens": tokens_name,
        "event": run,
    }

    # Create localized body message with token amount and currency
    body = (
        _("%(amount)d %(tokens)s were used to participate in this event")
        % {
            "amount": int(instance.value),
            "tokens": tokens_name,
        }
        + "!"
    )

    return subject, body


def notify_pay_credit(credits_name: str, instance: AccountingItemPayment, member: Member, run: Run) -> None:
    """Send credit payment notifications to user and organizers.

    Sends payment confirmation emails to both the member who made the payment
    and all event organizers. Each recipient receives the email in their
    preferred language.

    Args:
        credits_name: Name of the credit currency being paid
        instance: Payment accounting item instance containing payment details
        member: Member object who made the payment
        run: Event run object associated with the payment

    Returns:
        None

    """
    # Send notification to the member who made the payment
    activate(member.language)
    email_subject, email_body = get_pay_credit_email(credits_name, instance, run)
    my_send_mail(email_subject, email_body, member, run)

    # Send notifications to all event organizers
    for organizer in get_event_organizers(run.event):
        # Activate organizer's preferred language for localized content
        activate(organizer.language)
        email_subject, email_body = get_pay_credit_email(credits_name, instance, run)

        # Add member identification to subject line for organizers
        email_subject += _(" for %(user)s") % {"user": member}
        my_send_mail(email_subject, email_body, organizer, run)


def get_pay_credit_email(credits_name: str, instance: AccountingItemPayment, run: Run) -> tuple[str, str]:
    """Generate email content for credit payment notifications.

    Creates subject and body text for emails sent when credits are used
    to pay for event participation.

    Args:
        credits_name: Name of the credit currency (e.g., "PX", "tokens")
        instance: Payment accounting item instance containing transaction details
        run: Event run object representing the specific event instance

    Returns:
        A tuple containing:
            - subject: Email subject line with event and credit information
            - body: Email body text describing the credit usage

    """
    # Generate email subject with event header and credit usage message
    email_subject = hdr(instance) + _("Utilisation %(credits)s per %(event)s") % {
        "credits": credits_name,
        "event": run,
    }

    # Create email body describing the credit transaction amount
    email_body = (
        _("%(amount)d %(credits)s were used to participate in this event")
        % {
            "amount": int(instance.value),
            "credits": credits_name,
        }
        + "!"
    )

    # Return both subject and body as tuple
    return email_subject, email_body


def notify_pay_money(
    currency_symbol: str,
    payment_instance: AccountingItemPayment,
    paying_member: Member,
    event_run: Run,
) -> None:
    """Send money payment notifications to user and organizers.

    Sends payment confirmation emails to both the member who made the payment
    and all event organizers. Each email is localized according to the
    recipient's language preference.

    Args:
        currency_symbol: Currency symbol to display in the notification
        payment_instance: Payment accounting item instance containing payment details
        paying_member: Member object who made the payment
        event_run: Event run object associated with the payment

    Returns:
        None

    """
    # Send notification email to the member who made the payment
    activate(paying_member.language)
    subject, body = get_pay_money_email(currency_symbol, payment_instance, event_run)
    my_send_mail(subject, body, paying_member, event_run)

    # Send notification emails to all event organizers
    for organizer in get_event_organizers(event_run.event):
        # Activate organizer's language for localized email content
        activate(organizer.language)
        subject, body = get_pay_money_email(currency_symbol, payment_instance, event_run)

        # Add member identification to subject line for organizers
        subject += _(" for %(user)s") % {"user": paying_member}
        my_send_mail(subject, body, organizer, event_run)


def get_pay_money_email(curr_sym: str, instance: AccountingItemPayment, run: Run) -> tuple[str, str]:
    """Generate email content for money payment notifications.

    Creates localized email subject and body for payment confirmation emails
    sent when a money payment is received for an event registration.

    Args:
        curr_sym: Currency symbol (e.g., '€', '$', '£')
        instance: Payment accounting item instance containing payment details
        run: Event run object representing the specific event occurrence

    Returns:
        A tuple containing:
            - subject (str): Localized email subject line with payment info
            - body (str): Localized email body with payment amount and currency

    Example:
        >>> subject, body = get_pay_money_email('€', payment_instance, event_run)
        >>> print(subject)  # "Payment for Event Name"
        >>> print(body)    # "A payment of 50.00 € was received for this event!"

    """
    # Generate email subject with event information
    subject = hdr(instance) + _("Payment for %(event)s") % {"event": run}

    # Create email body with payment amount and currency details
    body = (
        _("A payment of %(amount).2f %(currency)s was received for this event")
        % {
            "amount": instance.value,
            "currency": curr_sym,
        }
        + "!"
    )

    # Return subject and body as tuple for email composition
    return subject, body


def send_token_credit_notification_email(accounting_item: AccountingItemOther) -> None:
    """Send notification emails for token, credit, or refund accounting items.

    Handles email notifications when new accounting items are created (not updated).
    Skips hidden items and only processes tokens, credits, and refunds.

    Args:
        accounting_item: AccountingItemOther instance being saved. Must have attributes:
            - hide: Boolean indicating if item should be hidden
            - pk: Primary key (None for new instances)
            - oth: Type of accounting item (TOKEN, CREDIT, or REFUND)
            - association_id: Associated organization ID

    Returns:
        None

    """
    # Skip processing if item is marked as hidden
    if accounting_item.hide:
        return

    # Get organization-specific names for tokens and credits
    tokens_name, credits_name = get_token_credit_name(accounting_item.association_id)

    # Only send notifications for new items (pk is None)
    if not accounting_item.pk:
        # Send appropriate notification based on item type
        if accounting_item.oth == OtherChoices.TOKEN:
            notify_token(accounting_item, tokens_name)
        elif accounting_item.oth == OtherChoices.CREDIT:
            notify_credit(credits_name, accounting_item)
        elif accounting_item.oth == OtherChoices.REFUND:
            notify_refund(credits_name, accounting_item)


def notify_refund(credits_name: str, instance: AccountingItemOther) -> None:
    """Send refund notifications to user and organizers.

    Args:
        credits_name: Name of the credit currency
        instance: Accounting item instance for refund

    Returns:
        None

    """
    # Activate user's language for localized messages
    activate(instance.member.language)

    # Build email subject with header and refund notice
    email_subject = hdr(instance) + _("Issued Reimbursement")

    # Construct notification body with refund details
    email_body = (
        _(
            "A reimbursement for '%(reason)s' has been marked as issued. %(amount).2f %(elements)s have been marked as used",
        )
        % {
            "amount": instance.value,
            "elements": credits_name,
            "reason": instance.descr,
        }
        + "."
    )

    # Send notification email to the member
    my_send_mail(email_subject, email_body, instance.member, instance)


def notify_credit(credits_name: str, instance: AccountingItemOther) -> None:
    """Send credit notification emails to users.

    Sends email notifications about credit assignments to both the recipient
    user and event organizers. The email content is localized based on the
    recipient's language preference.

    Args:
        credits_name: Name of the credit type being assigned
        instance: Credit instance containing member and amount information.
                 Must have 'member' attribute and optional 'run' attribute.

    Returns:
        None

    Side Effects:
        - Sends localized email to the credit recipient
        - Sends localized emails to event organizers if credit is run-specific
        - Temporarily changes active language for each recipient

    """
    # Send notification email to the credit recipient
    activate(instance.member.language)
    email_subject, email_body = get_credit_email(credits_name, instance)

    # Build URL for user's accounting page and add usage instructions
    accounting_url = get_url("accounting", instance)
    additional_body_text = (
        " <br /><br /><i>"
        + _("They will be used automatically when you sign up for a new event")
        + "!"
        + "<br /><br />"
        + _("Alternatively, you can request a reimbursement in <a href='%(url)s'>your accounting</a>.</i>")
        % {"url": accounting_url}
    )

    # Send email to the member with additional instructions
    my_send_mail(email_subject, email_body + additional_body_text, instance.member, instance)

    # Send notification emails to event organizers if credit is run-specific
    if instance.run:
        for event_organizer in get_event_organizers(instance.run.event):
            # Localize email content for each organizer
            activate(event_organizer.language)
            email_subject, email_body = get_credit_email(credits_name, instance)

            # Add member information to subject for organizer context
            email_subject += _(" for %(user)s") % {"user": instance.member}
            my_send_mail(email_subject, email_body, event_organizer, instance)


def get_credit_email(credits_name: str, instance: AccountingItemOther) -> tuple[str, str]:
    """Generate email subject and body for credit assignment notification.

    Creates localized email content for notifying users about credit assignments,
    including the credit amount, type, and associated event run if applicable.

    Args:
        credits_name: Name of the credit type being assigned (e.g., "tokens", "points")
        instance: AccountingItem instance containing credit details including value,
                 description, and optional run information

    Returns:
        A tuple containing:
            - subject: Formatted email subject line with credit assignment info
            - body: Formatted email body with credit amount, type, and reason

    """
    # Build the base subject line with header and credit assignment text
    subject = hdr(instance) + _("Assignment %(elements)s") % {
        "elements": credits_name,
    }

    # Append run information to subject if available
    if instance.run:
        subject += " " + _("for") + " " + str(instance.run)

    # Create formatted body message with credit details
    body = (
        _("Assigned %(amount).2f %(elements)s for '%(reason)s'")
        % {
            "amount": instance.value,
            "elements": credits_name,
            "reason": instance.descr,
        }
        + "."
    )

    return subject, body


def notify_token(instance: Any, tokens_name: str) -> None:
    """Send token notification emails to user and event organizers."""
    # Send notification to the token recipient
    activate(instance.member.language)
    email_subject, email_body = get_token_email(instance, tokens_name)
    additional_body = (
        "<br /><br /><i>" + _("They will be used automatically when you sign up for a new event") + "!" + "</i>"
    )
    my_send_mail(email_subject, email_body + additional_body, instance.member, instance)

    # Send notification to event organizers if run exists
    if instance.run:
        for organizer in get_event_organizers(instance.run.event):
            activate(organizer.language)
            email_subject, email_body = get_token_email(instance, tokens_name)
            email_subject += _(" for %(user)s") % {"user": instance.member}
            my_send_mail(email_subject, email_body, organizer, instance)


def get_token_email(instance: AccountingItemOther, tokens_name: str) -> tuple[str, str]:
    """Generate email subject and body for token assignment notification.

    Creates a localized email subject and body for notifying users about
    token assignments, including run information when available.

    Args:
        instance: AccountingItem instance containing token details
        tokens_name: Name of the token type being assigned

    Returns:
        A tuple containing the email subject and body as strings

    Example:
        >>> subject, body = get_token_email(accounting_item, "Credits")
        >>> print(subject)
        "Assignment Credits for Event Run 2024"

    """
    # Generate base subject with header and token assignment message
    email_subject = hdr(instance) + _("Assignment %(elements)s") % {
        "elements": tokens_name,
    }

    # Append run information to subject if available
    if instance.run:
        email_subject += " " + _("for") + " " + str(instance.run)

    # Create detailed body message with amount, token type, and reason
    email_body = (
        _("Assigned %(amount).2f %(elements)s for '%(reason)s'")
        % {
            "amount": int(instance.value),
            "elements": tokens_name,
            "reason": instance.descr,
        }
        + "."
    )

    return email_subject, email_body


def send_donation_confirmation_email(instance: AccountingItemDonation) -> None:
    """Send confirmation email to member after donation is processed.

    This function handles pre-save events for donation accounting items by sending
    a confirmation email to the donor. The email is only sent for new donations
    that are not hidden.

    Args:
        instance: The AccountingItemDonation instance being saved

    Returns:
        None

    """
    # Skip email if donation is marked as hidden
    if instance.hide:
        return

    # Skip email if this is an existing donation (has primary key)
    if instance.pk:
        return

    # Set language context to member's preferred language
    activate(instance.member.language)

    # Construct email subject with donation header and confirmation text
    email_subject = hdr(instance) + _("Donation given")

    # Build email body with donation amount and currency information
    email_body = _(
        "We confirm we received the donation of %(amount)d %(currency)s. We thank you for your "
        "support, and for believing in us!",
    ) % {"amount": instance.value, "currency": instance.association.get_currency_symbol()}

    # Send the confirmation email to the donor
    my_send_mail(email_subject, email_body, instance.member, instance)


def send_collection_activation_email(instance: AccountingItemCollection) -> None:
    """Handle post-save events for collection instances.

    Sends an activation email to the organizer when a new collection instance
    is created. The email contains a link to manage the collection.

    Args:
        instance: Collection instance that was saved

    Returns:
        None

    """
    # Prepare email context with recipient and management URL
    email_context = {
        "recipient": instance.display_member(),
        "url": get_url(f"accounting/collection/{instance.contribute_code}/", instance),
    }

    # Set language to organizer's preference for localized content
    activate(instance.organizer.language)

    # Build localized email subject and body
    email_subject = hdr(instance) + _("Activate collection for: %(recipient)s") % email_context
    email_body = (
        _(
            "We confirm that the collection for '%(recipient)s' has been activated. <a "
            "href='%(url)s'>Manage it here!</a>",
        )
        % email_context
    )

    # Send the activation email to the organizer
    my_send_mail(email_subject, email_body, instance.organizer, instance)


def send_gift_collection_notification_email(instance: AccountingItemCollection) -> None:
    """Send notification emails when gift collection participation is saved.

    Args:
        instance: Collection gift instance

    """
    if not instance.pk:
        activate(instance.member.language)
        subject = hdr(instance.collection) + _("Collection participation for: %(recipient)s") % {
            "recipient": instance.collection.display_member(),
        }
        email_body = _("Thank you for participating") + "!"
        my_send_mail(subject, email_body, instance.member, instance.collection)

        activate(instance.collection.organizer.language)
        subject = hdr(instance.collection) + _("New participation in the collection for %(recipient)s by %(user)s") % {
            "recipient": instance.collection.display_member(),
            "user": instance.member.display_member(),
        }
        email_body = _("The collection grows") + "!"
        my_send_mail(subject, email_body, instance.collection.organizer, instance.collection)


def notify_invoice_check(inv: PaymentInvoice) -> None:
    """Send invoice check notifications to appropriate recipients.

    This function handles sending email notifications for invoice checks based on
    the organization's configuration and features. It follows a priority order:
    treasurer appointees, event organizers (for registrations), or main organization email.

    Args:
        inv: Invoice object to send notifications for. Must have association_id, typ, and reg attributes.

    Returns:
        None

    """
    # Check if payment notifications are enabled for this organization
    if not get_association_config(inv.association_id, "mail_payment", default_value=False):
        return

    # Get organization features to determine notification recipients
    features = get_association_features(inv.association_id)

    # If treasurer feature is enabled, send notifications to treasurer appointees
    if "treasurer" in features:
        # Parse comma-separated list of treasurer member IDs
        treasurer_list = get_association_config(inv.association_id, "treasurer_appointees", default_value="").split(
            ", "
        )
        for treasurer_member_id in treasurer_list:
            member_id = int(treasurer_member_id)
            organizer = Member.objects.get(pk=member_id)

            # Set language context and prepare email content
            activate(organizer.language)
            email_subject, email_body = get_invoice_email(inv)
            my_send_mail(email_subject, email_body, organizer, inv)

    # For registration invoices, notify event organizers when no treasurer feature
    elif inv.typ == PaymentType.REGISTRATION and inv.reg:
        # Get all organizers for the event associated with this registration
        for organizer in get_event_organizers(inv.reg.run.event):
            # Set language context and prepare email content
            activate(organizer.language)
            email_subject, email_body = get_invoice_email(inv)
            my_send_mail(email_subject, email_body, organizer, inv)

    # Fallback: send to main organization email for all other cases
    else:
        notify_organization_exe(get_invoice_email, inv.association, inv)


def notify_refund_request(payment: PaymentInvoice) -> None:
    """Notify organization executives about a refund request."""
    notify_organization_exe(get_notify_refund_email, payment.association, payment)


def get_notify_refund_email(p: AccountingItemOther) -> tuple[str, str]:
    """Generate email subject and body for refund request notification.

    Args:
        p: Payment object containing refund request details including member,
           details, and value attributes

    Returns:
        tuple[str, str]: A tuple containing:
            - subject (str): Email subject line with header and user info
            - body (str): Email body with payment details and amount

    """
    # Generate email subject with header prefix and requesting user
    subj = hdr(p) + _("Request refund from: %(user)s") % {"user": p.member}

    # Format email body with payment details and refund amount
    body = _("Details: %(details)s (<b>%(amount).2f</b>)") % {"details": p.details, "amount": p.value}

    return subj, body


def get_invoice_email(invoice: Any) -> tuple[str, str]:
    """Generate email subject and body for invoice payment verification.

    Args:
        invoice: Invoice object containing payment details and metadata

    Returns:
        tuple[str, str]: A tuple containing (subject, body) strings for the
            payment verification email. Subject includes payment description,
            body contains formatted payment details and action links.

    """
    # Start building the email body with verification prompt
    body = _("Verify that the data are correct") + ":"

    # Add payment reason and amount details
    body += "<br /><br />" + _("Reason for payment") + f": <b>{invoice.causal}</b>"
    body += "<br /><br />" + _("Amount") + f": <b>{invoice.mc_gross:.2f}</b>"

    # Include download link if invoice document exists
    if invoice.invoice:
        download_url = get_url(invoice.download(), invoice)
        body += f"<br /><br /><a href='{download_url}'>" + _("Download document") + "</a>"
    # Show additional text for 'any' payment method
    elif invoice.method and invoice.method.slug == "any":
        body += f"<br /><br /><i>{invoice.text}</i>"

    # Add confirmation prompt and link
    body += "<br /><br />" + _("Did you check and is it correct") + "?"
    confirmation_url = get_url("accounting/confirm", invoice)
    body += f" <a href='{confirmation_url}/{invoice.cod}'>" + _("Payment confirmation") + "</a>"

    # Process causal for subject line (remove prefix if hyphen present)
    subject_causal = invoice.causal
    if "-" in subject_causal:
        subject_causal = subject_causal.split("-", 1)[1].strip()

    # Generate final subject with header and payment description
    subject = hdr(invoice) + _("Payment to check") + ": " + subject_causal
    return subject, body
