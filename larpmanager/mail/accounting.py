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
from larpmanager.utils.tasks import my_send_mail


def send_expense_notification_email(instance: AccountingItemExpense, created: bool) -> None:
    """Send email notification to event organizers when an expense is created.

    This function handles post-save events for expense accounting items by sending
    notification emails to all event organizers when a new expense item is created.
    No notification is sent for hidden expenses or when updating existing expenses.

    Args:
        instance: The AccountingItemExpense instance that was saved
        created: Boolean indicating if the instance was newly created (True) or updated (False)

    Returns:
        None
    """
    # Skip notification if expense is marked as hidden
    if instance.hide:
        return

    # Only send email notifications for newly created expenses
    # that are associated with a run and event
    if created and instance.run and instance.run.event:
        # Iterate through all organizers for the event
        for orga in get_event_organizers(instance.run.event):
            # Set the language context for the organizer
            activate(orga.language)

            # Generate email subject and body content
            subj, body = get_expense_mail(instance)

            # Send the notification email to the organizer
            my_send_mail(subj, body, orga, instance.run)


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
    subj = hdr(instance) + _("Reimbursement request for %(event)s") % {"event": instance.run}

    # Create initial body with staff member and event information
    body = _("Staff member %(user)s added a new reimbursement request for %(event)s") % {
        "user": instance.member,
        "event": instance.run,
    }

    # Add expense amount and reason details
    body += (
        "<br /><br />"
        + _("The sum is %(amount).2f, with reason '%(reason)s'")
        % {
            "amount": instance.value,
            "reason": instance.descr,
        }
        + "."
    )

    # Add document download link if available
    url = get_url(instance.download(), instance)
    body += f"<br /><br /><a href='{url}'>" + _("download document") + "</a>"

    # Add approval prompt and confirmation link
    body += "<br /><br />" + _("Did you check and is it correct") + "?"
    url = f"{instance.run.get_slug()}/manage/expenses/approve/{instance.pk}"
    body += f"<a href='{url}'>" + _("Confirmation of expenditure") + "</a>"

    return subj, body


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
    previous_appr = AccountingItemExpense.objects.get(pk=expense_item.pk).is_approved

    # Only send email when item is newly approved and has an associated member
    if not (expense_item.member and expense_item.is_approved and not previous_appr):
        return

    # Build email subject with optional run information
    subj = hdr(expense_item) + _("Reimbursement approved")
    if expense_item.run:
        subj += " " + _("for") + f" {expense_item.run}"

    # Create base email body with approval details
    body = (
        _("Your request for reimbursement of %(amount).2f, with reason '%(reason)s', has been approved")
        % {
            "amount": expense_item.value,
            "reason": expense_item.descr,
        }
        + "!"
    )

    # Get token and credit names for the association
    token_name, credit_name = get_token_credit_name(expense_item.assoc_id)

    # Add credit information if run has token_credit feature enabled
    if expense_item.run and "token_credit" in get_event_features(expense_item.run.event_id):
        body += "<br /><br /><i>" + _("The sum was assigned to you as %(credits)s") % {"credits": credit_name} + "."
        body += " " + _("This is automatically deducted from the registration of a future event") + "."

        # Add link to accounting page for formal request option
        body += (
            " "
            + _(
                "Alternatively, you can request to receive it with a formal request in the <a "
                "href='%(url)s'>your accounting.</a>."
            )
            % {"url": get_url("accounting", expense_item)}
            + "</i>"
        )

    # Send the notification email
    my_send_mail(subj, body, expense_item.member, expense_item.run)


def get_token_credit_name(assoc_id: int) -> tuple[str, str]:
    """Get token and credit names from association configuration.

    Retrieves custom token and credit names from the association's configuration,
    falling back to default translated names if not configured.

    Args:
        assoc_id: ID of the Association to get configuration from.

    Returns:
        A tuple containing (token_name, credit_name) as strings. Returns
        default translated values if custom names are not configured.
    """
    # Create configuration holder for caching retrieved values
    config_holder = {}

    # Retrieve custom token and credit names from association config
    token_name = get_assoc_config(assoc_id, "token_credit_token_name", None, config_holder)
    credit_name = get_assoc_config(assoc_id, "token_credit_credit_name", None, config_holder)

    # Apply default translated names if custom names not configured
    if not token_name:
        token_name = _("Tokens")
    if not credit_name:
        credit_name = _("Credits")

    return token_name, credit_name


def send_payment_confirmation_email(payment_item: AccountingItemPayment) -> None:
    """Send payment confirmation email to member after payment processing.

    Sends appropriate notification email based on payment type (money, credit, or token)
    if email notifications are enabled for the association and the payment item
    is not hidden.

    Args:
        payment_item: AccountingItemPayment instance being saved. Must have
            reg (registration), pay (payment type), and assoc_id attributes.

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
    run = payment_item.reg.run
    member = payment_item.reg.member

    # Check if payment notifications are enabled for this association
    if not get_assoc_config(run.event.assoc_id, "mail_payment", False):
        return

    # Get localized names for tokens and credits
    token_name, credit_name = get_token_credit_name(payment_item.assoc_id)

    # Get currency symbol for money payments
    curr_sym = run.event.assoc.get_currency_symbol()

    # Only send notification for new payment items (not updates)
    if not payment_item.pk:
        # Send appropriate notification based on payment type
        if payment_item.pay == PaymentChoices.MONEY:
            notify_pay_money(curr_sym, payment_item, member, run)
        elif payment_item.pay == PaymentChoices.CREDIT:
            notify_pay_credit(credit_name, payment_item, member, run)
        elif payment_item.pay == PaymentChoices.TOKEN:
            notify_pay_token(payment_item, member, run, token_name)


def notify_pay_token(instance: AccountingItemPayment, member: Member, run: Run, token_name: str) -> None:
    """Send token payment notifications to user and organizers.

    Sends payment confirmation emails to both the paying member and all event
    organizers. Each recipient receives the email in their preferred language.

    Args:
        instance: Payment accounting item instance containing payment details
        member: Member who made the payment
        run: Event run object for the payment context
        token_name: Name of the token currency being paid

    Returns:
        None
    """
    # Send notification to the paying user
    activate(member.language)
    subj, body = get_pay_token_email(instance, run, token_name)
    my_send_mail(subj, body, member, run)

    # Send notifications to all event organizers
    for orga in get_event_organizers(run.event):
        # Set organizer's preferred language for localized email
        activate(orga.language)
        subj, body = get_pay_token_email(instance, run, token_name)

        # Add member identification to organizer's subject line
        subj += _(" for %(user)s") % {"user": member}
        my_send_mail(subj, body, orga, run)


def get_pay_token_email(instance: AccountingItemPayment, run: Run, token_name: str) -> tuple[str, str]:
    """Generate email content for token payment notifications.

    Creates localized email subject and body text for notifications sent when
    tokens are used to pay for event participation.

    Args:
        instance: Payment accounting item instance containing token amount
        run: Event run object representing the event
        token_name: Name of the token currency being used

    Returns:
        Tuple containing:
            - subject (str): Localized email subject line
            - body (str): Localized email body content

    Example:
        >>> subject, body = get_pay_token_email(payment, event_run, "Credits")
        >>> print(subject)  # "Payment: Credit usage for Summer Event 2023"
    """
    # Generate localized subject line with event and token information
    subj = hdr(instance) + _("Utilisation %(tokens)s per %(event)s") % {
        "tokens": token_name,
        "event": run,
    }

    # Create localized body message with token amount and currency
    body = (
        _("%(amount)d %(tokens)s were used to participate in this event")
        % {
            "amount": int(instance.value),
            "tokens": token_name,
        }
        + "!"
    )

    return subj, body


def notify_pay_credit(credit_name: str, instance: AccountingItemPayment, member: Member, run: Run) -> None:
    """Send credit payment notifications to user and organizers.

    Sends payment confirmation emails to both the member who made the payment
    and all event organizers. Each recipient receives the email in their
    preferred language.

    Args:
        credit_name: Name of the credit currency being paid
        instance: Payment accounting item instance containing payment details
        member: Member object who made the payment
        run: Event run object associated with the payment

    Returns:
        None
    """
    # Send notification to the member who made the payment
    activate(member.language)
    subj, body = get_pay_credit_email(credit_name, instance, run)
    my_send_mail(subj, body, member, run)

    # Send notifications to all event organizers
    for orga in get_event_organizers(run.event):
        # Activate organizer's preferred language for localized content
        activate(orga.language)
        subj, body = get_pay_credit_email(credit_name, instance, run)

        # Add member identification to subject line for organizers
        subj += _(" for %(user)s") % {"user": member}
        my_send_mail(subj, body, orga, run)


def get_pay_credit_email(credit_name: str, instance: AccountingItemPayment, run: Run) -> tuple[str, str]:
    """Generate email content for credit payment notifications.

    Creates subject and body text for emails sent when credits are used
    to pay for event participation.

    Args:
        credit_name: Name of the credit currency (e.g., "PX", "tokens")
        instance: Payment accounting item instance containing transaction details
        run: Event run object representing the specific event instance

    Returns:
        A tuple containing:
            - subject: Email subject line with event and credit information
            - body: Email body text describing the credit usage
    """
    # Generate email subject with event header and credit usage message
    subj = hdr(instance) + _("Utilisation %(credits)s per %(event)s") % {
        "credits": credit_name,
        "event": run,
    }

    # Create email body describing the credit transaction amount
    body = (
        _("%(amount)d %(credits)s were used to participate in this event")
        % {
            "amount": int(instance.value),
            "credits": credit_name,
        }
        + "!"
    )

    # Return both subject and body as tuple
    return subj, body


def notify_pay_money(curr_sym: str, instance: AccountingItemPayment, member: Member, run: Run) -> None:
    """Send money payment notifications to user and organizers.

    Sends payment confirmation emails to both the member who made the payment
    and all event organizers. Each email is localized according to the
    recipient's language preference.

    Args:
        curr_sym: Currency symbol to display in the notification
        instance: Payment accounting item instance containing payment details
        member: Member object who made the payment
        run: Event run object associated with the payment

    Returns:
        None
    """
    # Send notification email to the member who made the payment
    activate(member.language)
    subj, body = get_pay_money_email(curr_sym, instance, run)
    my_send_mail(subj, body, member, run)

    # Send notification emails to all event organizers
    for orga in get_event_organizers(run.event):
        # Activate organizer's language for localized email content
        activate(orga.language)
        subj, body = get_pay_money_email(curr_sym, instance, run)

        # Add member identification to subject line for organizers
        subj += _(" for %(user)s") % {"user": member}
        my_send_mail(subj, body, orga, run)


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
    subj = hdr(instance) + _("Payment for %(event)s") % {"event": run}

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
    return subj, body


def send_token_credit_notification_email(instance: AccountingItemOther) -> None:
    """Send notification emails for token, credit, or refund accounting items.

    Handles email notifications when new accounting items are created (not updated).
    Skips hidden items and only processes tokens, credits, and refunds.

    Args:
        instance: AccountingItemOther instance being saved. Must have attributes:
            - hide: Boolean indicating if item should be hidden
            - pk: Primary key (None for new instances)
            - oth: Type of accounting item (TOKEN, CREDIT, or REFUND)
            - assoc_id: Associated organization ID

    Returns:
        None
    """
    # Skip processing if item is marked as hidden
    if instance.hide:
        return

    # Get organization-specific names for tokens and credits
    token_name, credit_name = get_token_credit_name(instance.assoc_id)

    # Only send notifications for new items (pk is None)
    if not instance.pk:
        # Send appropriate notification based on item type
        if instance.oth == OtherChoices.TOKEN:
            notify_token(instance, token_name)
        elif instance.oth == OtherChoices.CREDIT:
            notify_credit(credit_name, instance)
        elif instance.oth == OtherChoices.REFUND:
            notify_refund(credit_name, instance)


def notify_refund(credit_name: str, instance: AccountingItemOther) -> None:
    """Send refund notifications to user and organizers.

    Parameters
    ----------
    credit_name : str
        Name of the credit currency
    instance : AccountingItemOther
        Accounting item instance for refund

    Returns
    -------
    None
    """
    # Activate user's language for localized messages
    activate(instance.member.language)

    # Build email subject with header and refund notice
    subj = hdr(instance) + _("Issued Reimbursement")

    # Construct notification body with refund details
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

    # Send notification email to the member
    my_send_mail(subj, body, instance.member, instance)


def notify_credit(credit_name: str, instance: AccountingItemOther) -> None:
    """Send credit notification emails to users.

    Sends email notifications about credit assignments to both the recipient
    user and event organizers. The email content is localized based on the
    recipient's language preference.

    Args:
        credit_name: Name of the credit type being assigned
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
    subj, body = get_credit_email(credit_name, instance)

    # Build URL for user's accounting page and add usage instructions
    url = get_url("accounting", instance)
    add_body = (
        " <br /><br /><i>"
        + _("They will be used automatically when you sign up for a new event")
        + "!"
        + "<br /><br />"
        + _("Alternatively, you can request a reimbursement in <a href='%(url)s'>your accounting</a>.</i>")
        % {"url": url}
    )

    # Send email to the member with additional instructions
    my_send_mail(subj, body + add_body, instance.member, instance)

    # Send notification emails to event organizers if credit is run-specific
    if instance.run:
        for orga in get_event_organizers(instance.run.event):
            # Localize email content for each organizer
            activate(orga.language)
            subj, body = get_credit_email(credit_name, instance)

            # Add member information to subject for organizer context
            subj += _(" for %(user)s") % {"user": instance.member}
            my_send_mail(subj, body, orga, instance)


def get_credit_email(credit_name: str, instance: AccountingItemOther) -> tuple[str, str]:
    """Generate email subject and body for credit assignment notification.

    Creates localized email content for notifying users about credit assignments,
    including the credit amount, type, and associated event run if applicable.

    Args:
        credit_name: Name of the credit type being assigned (e.g., "tokens", "points")
        instance: AccountingItem instance containing credit details including value,
                 description, and optional run information

    Returns:
        A tuple containing:
            - subject: Formatted email subject line with credit assignment info
            - body: Formatted email body with credit amount, type, and reason
    """
    # Build the base subject line with header and credit assignment text
    subj = hdr(instance) + _("Assignment %(elements)s") % {
        "elements": credit_name,
    }

    # Append run information to subject if available
    if instance.run:
        subj += " " + _("for") + " " + str(instance.run)

    # Create formatted body message with credit details
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


def get_token_email(instance: AccountingItemOther, token_name: str) -> tuple[str, str]:
    """Generate email subject and body for token assignment notification.

    Creates a localized email subject and body for notifying users about
    token assignments, including run information when available.

    Args:
        instance: AccountingItem instance containing token details
        token_name: Name of the token type being assigned

    Returns:
        A tuple containing the email subject and body as strings

    Example:
        >>> subject, body = get_token_email(accounting_item, "Credits")
        >>> print(subject)
        "Assignment Credits for Event Run 2024"
    """
    # Generate base subject with header and token assignment message
    subj = hdr(instance) + _("Assignment %(elements)s") % {
        "elements": token_name,
    }

    # Append run information to subject if available
    if instance.run:
        subj += " " + _("for") + " " + str(instance.run)

    # Create detailed body message with amount, token type, and reason
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
    subj = hdr(instance) + _("Donation given")

    # Build email body with donation amount and currency information
    body = _(
        "We confirm we received the donation of %(amount)d %(currency)s. We thank you for your "
        "support, and for believing in us!"
    ) % {"amount": instance.value, "currency": instance.assoc.get_currency_symbol()}

    # Send the confirmation email to the donor
    my_send_mail(subj, body, instance.member, instance)


def send_collection_activation_email(instance: AccountingItemCollection, created: bool) -> None:
    """Handle post-save events for collection instances.

    Sends an activation email to the organizer when a new collection instance
    is created. The email contains a link to manage the collection.

    Args:
        instance: Collection instance that was saved
        created: Boolean indicating if instance was created (True for new instances)

    Returns:
        None
    """
    # Early return if this is an update, not a creation
    if not created:
        return

    # Prepare email context with recipient and management URL
    context = {
        "recipient": instance.display_member(),
        "url": get_url(f"accounting/collection/{instance.contribute_code}/", instance),
    }

    # Set language to organizer's preference for localized content
    activate(instance.organizer.language)

    # Build localized email subject and body
    subj = hdr(instance) + _("Activate collection for: %(recipient)s") % context
    body = (
        _(
            "We confirm that the collection for '%(recipient)s' has been activated. <a "
            "href='%(url)s'>Manage it here!</a>"
        )
        % context
    )

    # Send the activation email to the organizer
    my_send_mail(subj, body, instance.organizer, instance)


def send_gift_collection_notification_email(instance: AccountingItemCollection):
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


def notify_invoice_check(inv: PaymentInvoice) -> None:
    """Send invoice check notifications to appropriate recipients.

    This function handles sending email notifications for invoice checks based on
    the organization's configuration and features. It follows a priority order:
    treasurer appointees, event organizers (for registrations), or main organization email.

    Args:
        inv: Invoice object to send notifications for. Must have assoc_id, typ, and reg attributes.

    Returns:
        None
    """
    # Check if payment notifications are enabled for this organization
    if not get_assoc_config(inv.assoc_id, "mail_payment", False):
        return

    # Get organization features to determine notification recipients
    features = get_assoc_features(inv.assoc_id)

    # If treasurer feature is enabled, send notifications to treasurer appointees
    if "treasurer" in features:
        # Parse comma-separated list of treasurer member IDs
        treasurer_list = get_assoc_config(inv.assoc_id, "treasurer_appointees", "").split(", ")
        for mb in treasurer_list:
            idx = int(mb)
            orga = Member.objects.get(pk=idx)

            # Set language context and prepare email content
            activate(orga.language)
            subj, body = get_invoice_email(inv)
            my_send_mail(subj, body, orga, inv)

    # For registration invoices, notify event organizers when no treasurer feature
    elif inv.typ == PaymentType.REGISTRATION and inv.reg:
        # Get all organizers for the event associated with this registration
        for orga in get_event_organizers(inv.reg.run.event):
            # Set language context and prepare email content
            activate(orga.language)
            subj, body = get_invoice_email(inv)
            my_send_mail(subj, body, orga, inv)

    # Fallback: send to main organization email for all other cases
    else:
        notify_organization_exe(get_invoice_email, inv.assoc, inv)


def notify_refund_request(p):
    notify_organization_exe(get_notify_refund_email, p.assoc, p)


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


def get_invoice_email(inv) -> tuple[str, str]:
    """Generate email subject and body for invoice payment verification.

    Args:
        inv: Invoice object containing payment details and metadata

    Returns:
        tuple[str, str]: A tuple containing (subject, body) strings for the
            payment verification email. Subject includes payment description,
            body contains formatted payment details and action links.
    """
    # Start building the email body with verification prompt
    body = _("Verify that the data are correct") + ":"

    # Add payment reason and amount details
    body += "<br /><br />" + _("Reason for payment") + f": <b>{inv.causal}</b>"
    body += "<br /><br />" + _("Amount") + f": <b>{inv.mc_gross:.2f}</b>"

    # Include download link if invoice document exists
    if inv.invoice:
        url = get_url(inv.download(), inv)
        body += f"<br /><br /><a href='{url}'>" + _("Download document") + "</a>"
    # Show additional text for 'any' payment method
    elif inv.method and inv.method.slug == "any":
        body += f"<br /><br /><i>{inv.text}</i>"

    # Add confirmation prompt and link
    body += "<br /><br />" + _("Did you check and is it correct") + "?"
    url = get_url("accounting/confirm", inv)
    body += f" <a href='{url}/{inv.cod}'>" + _("Payment confirmation") + "</a>"

    # Process causal for subject line (remove prefix if hyphen present)
    causal = inv.causal
    if "-" in causal:
        causal = causal.split("-", 1)[1].strip()

    # Generate final subject with header and payment description
    subj = hdr(inv) + _("Payment to check") + ": " + causal
    return subj, body
