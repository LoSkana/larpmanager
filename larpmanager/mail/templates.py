from typing import Any

from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_association_config
from larpmanager.cache.feature import get_event_features
from larpmanager.models.accounting import AccountingItemExpense, AccountingItemOther, AccountingItemPayment
from larpmanager.models.association import get_url, hdr
from larpmanager.models.event import Run
from larpmanager.models.member import get_user_membership
from larpmanager.models.registration import Registration
from larpmanager.utils.users.registration import get_registration_options


def format_decimal_amount(value: float) -> str:
    """Format decimal value for display: integers without decimals, decimals with max 2 places."""
    if value % 1 == 0:
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def get_token_credit_name(association_id: int) -> tuple[str, str]:
    """Get token and credit names from association configuration."""
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


def get_registration_new_organizer_email(instance: Registration, email_context: dict) -> tuple[str, str]:
    """Generate email subject and body for new registration organizer notification."""
    email_subject = hdr(instance.run.event) + _("Registration to %(event)s by %(user)s") % email_context
    email_body = _("The user has confirmed its registration for this event") + "!"
    email_body += registration_options(instance)
    return email_subject, email_body


def get_registration_update_organizer_email(instance: Registration, email_context: dict) -> tuple[str, str]:
    """Generate email subject and body for registration update organizer notification."""
    email_subject = hdr(instance.run.event) + _("Registration updated to %(event)s by %(user)s") % email_context
    email_body = _("The user has updated their registration for this event") + "!"
    email_body += registration_options(instance)
    return email_subject, email_body


def get_registration_cancel_organizer_email(instance: Registration, email_context: dict) -> tuple[str, str]:
    """Generate email subject and body for registration cancellation organizer notification."""
    email_subject = hdr(instance.run.event) + _("Registration cancelled for %(event)s by %(user)s") % email_context
    email_body = _("The registration for this event has been cancelled") + "."
    return email_subject, email_body


def get_expense_mail(instance: AccountingItemExpense) -> tuple[str, str]:
    """Generate email subject and body for expense reimbursement requests."""
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
    if instance.invoice:
        document_download_url = get_url(instance.download(), instance)
        email_body += f"<br /><br /><a href='{document_download_url}'>" + _("download document") + "</a>"

    # Add approval prompt and confirmation link
    email_body += "<br /><br />" + _("Did you check and is it correct") + "?"
    approval_url = f"{instance.run.get_slug()}/manage/expenses/approve/{instance.pk}"
    email_body += f"<a href='{approval_url}'>" + _("Confirmation of expenditure") + "</a>"

    return email_subject, email_body


def get_pay_token_email(instance: AccountingItemPayment, run: Run, tokens_name: str) -> tuple[str, str]:
    """Generate email content for token payment notifications."""
    # Generate localized subject line with event and token information
    subject = hdr(instance) + _("Utilisation %(tokens)s per %(event)s") % {
        "tokens": tokens_name,
        "event": run,
    }

    # Create localized body message with token amount and currency
    body = (
        _("%(amount)s %(tokens)s were used to participate in this event")
        % {
            "amount": format_decimal_amount(instance.value),
            "tokens": tokens_name,
        }
        + "!"
    )

    return subject, body


def get_pay_credit_email(credits_name: str, instance: AccountingItemPayment, run: Run) -> tuple[str, str]:
    """Generate email content for credit payment notifications."""
    # Generate email subject with event header and credit usage message
    email_subject = hdr(instance) + _("Utilisation %(credits)s per %(event)s") % {
        "credits": credits_name,
        "event": run,
    }

    # Create email body describing the credit transaction amount
    email_body = (
        _("%(amount)s %(credits)s were used to participate in this event")
        % {
            "amount": format_decimal_amount(instance.value),
            "credits": credits_name,
        }
        + "!"
    )

    # Return both subject and body as tuple
    return email_subject, email_body


def get_pay_money_email(curr_sym: str, instance: AccountingItemPayment, run: Run) -> tuple[str, str]:
    """Generate email content for money payment notifications."""
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


def get_credit_email(credits_name: str, instance: AccountingItemOther) -> tuple[str, str]:
    """Generate email subject and body for credit assignment notification."""
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


def get_token_email(instance: AccountingItemOther, tokens_name: str) -> tuple[str, str]:
    """Generate email subject and body for token assignment notification."""
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


def get_notify_refund_email(p: AccountingItemOther) -> tuple[str, str]:
    """Generate email subject and body for refund request notification."""
    # Generate email subject with header prefix and requesting user
    subj = hdr(p) + _("Request refund from: %(user)s") % {"user": p.member}

    # Format email body with payment details and refund amount
    body = _("Details: %(details)s (<b>%(amount).2f</b>)") % {"details": p.details, "amount": p.value}

    return subj, body


def get_invoice_email(invoice: Any) -> tuple[str, str]:
    """Generate email subject and body for invoice payment verification."""
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


def registration_options(registration_instance: Any) -> str:
    """Generate email content for registration options.

    Creates formatted text showing selected tickets and registration choices,
    including payment information, totals, and selected registration options
    for email notifications.

    Args:
        registration_instance: Registration instance containing ticket, member, and payment data

    Returns:
        str: HTML formatted string with registration details for email content

    """
    email_body = ""

    # Add ticket information if selected
    if registration_instance.ticket:
        email_body += "<br /><br />" + _("Ticket selected") + f": <b>{registration_instance.ticket.name}</b>"
        if registration_instance.ticket.description:
            email_body += f" - {registration_instance.ticket.description}"

    # Get user membership and event features for permission checks
    get_user_membership(registration_instance.member, registration_instance.run.event.association_id)
    event_features = get_event_features(registration_instance.run.event_id)

    # Get currency symbol for formatting monetary amounts
    currency_symbol = registration_instance.run.event.association.get_currency_symbol()

    # Display total registration fee if greater than zero
    if registration_instance.tot_iscr > 0:
        email_body += (
            "<br /><br />"
            + _("Total of your signup fee: <b>%(amount).2f %(currency)s</b>")
            % {
                "amount": registration_instance.tot_iscr,
                "currency": currency_symbol,
            }
            + "."
        )

    # Display payments already received if any
    if registration_instance.tot_payed > 0:
        email_body += (
            "<br /><br />"
            + _("Payments already received: <b>%(amount).2f %(currency)s</b>")
            % {
                "amount": registration_instance.tot_payed,
                "currency": currency_symbol,
            }
            + "."
        )

    # Add payment information if payment feature enabled and quota/alert conditions met
    if "payment" in event_features and registration_instance.quota > 0 and registration_instance.alert:
        email_body += registration_payments(registration_instance, currency_symbol)

    # Add selected registration options if any exist
    selected_options = get_registration_options(registration_instance)
    if selected_options:
        email_body += "<br /><br />" + _("Selected options") + ":"
        for option_name, option_value in selected_options:
            email_body += f"<br />{option_name} - {option_value}"

    return email_body


def registration_payments(instance: Registration, currency: str) -> str:
    """Generate payment information HTML for registration emails.

    This function creates localized HTML content for registration payment notifications,
    including payment amounts, deadlines, and payment links. The content varies based
    on whether a payment deadline is set.

    Args:
        instance: Registration instance containing payment details and associated run/event data.
                 Must have attributes: quota, deadline, run (with event and get_slug method).
        currency: Currency symbol or code to display with the payment amount (e.g., '€', 'USD').

    Returns:
        Localized HTML string containing payment information with formatted amount,
        deadline details, and a link to the payment page. Format depends on deadline value.

    Note:
        - If deadline > 0: Shows specific deadline in days with warning about cancellation
        - If deadline <= 0: Shows immediate payment required message

    """
    # Build the payment URL using the event and run slug
    full_payment_url = get_url("accounting/pay", instance.run.event)
    payment_url = f"{full_payment_url}/{instance.run.get_slug()}"

    # Prepare template data for localization
    template_data = {
        "url": payment_url,
        "amount": instance.quota,
        "currency": currency,
        "deadline": instance.deadline,
    }

    # Handle case where payment has a specific deadline in days
    if instance.deadline > 0:
        return (
            "<br /><br />"
            + _(
                "You must pay at least <b>%(amount).2f %(currency)s</b> by %(deadline)d days. "
                "Make your payment <a href='%(url)s'>on this page</a>. If we do not receive "
                "payment by the deadline, your registration may be cancelled.",
            )
            % template_data
        )

    # Handle immediate payment requirement (no specific deadline)
    return (
        "<br /><br />"
        + _(
            "<i>Payment due</i> - You must pay <b>%(amount).2f %(currency)s</b> as soon as "
            "possible. Make your payment <a href='%(url)s'>on this page</a>. If we do not "
            "receive payment, your registration may be cancelled.",
        )
        % template_data
    )
