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

import logging
import time

from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.event_text import get_event_text
from larpmanager.cache.feature import get_event_features
from larpmanager.models.access import get_event_organizers
from larpmanager.models.association import AssociationTextType, get_url, hdr
from larpmanager.models.event import DevelopStatus, EventTextType
from larpmanager.models.member import get_user_membership
from larpmanager.models.registration import Registration, RegistrationCharacterRel
from larpmanager.utils.registration import get_registration_options
from larpmanager.utils.tasks import background_auto, my_send_mail
from typing import Any

logger = logging.getLogger(__name__)


@background_auto(queue="acc")
def update_registration_status_bkg(registration_id: Any) -> None:
    """Background task to update registration status with delay.

    Args:
        registration_id: ID of the registration to update

    """
    time.sleep(1)
    registration = Registration.objects.get(pk=registration_id)
    update_registration_status(registration)


def update_registration_status(instance: Any) -> None:
    """Send email notifications for registration status changes.

    Handles automated emails for registration confirmations and updates,
    sending notifications to both the registering member and event organizers
    based on association configuration settings.

    Args:
        instance: Registration instance with member, run, and modification status.
                 Expected to have attributes: modified, member, run.

    Returns:
        None

    Note:
        - Skips notifications for non-gifted registrations (modified == 0)
        - Skips notifications for provisional registrations
        - Sends different messages based on modification type (1=new, other=update)
        - Organizer notifications depend on association configuration settings

    """
    # Skip registration not gifted - no notifications needed
    if instance.modified == 0:
        return

    # Skip provisional registrations - wait for confirmation
    if is_reg_provisional(instance):
        return

    # Prepare common context for email templates
    email_context = {"event": instance.run, "user": instance.member}

    # Send notification to the registering user
    activate(instance.member.language)

    # Determine email subject and body based on modification type
    if instance.modified == 1:
        email_subject = hdr(instance.run.event) + _("Registration to %(event)s") % email_context
        email_body = _("Hello! Your registration at <b>%(event)s</b> has been confirmed") % email_context + "!"
    else:
        email_subject = hdr(instance.run.event) + _("Registration updated for %(event)s") % email_context
        email_body = _("Hi! Your registration to <b>%(event)s</b> has been updated") % email_context + "!"

    # Append registration details to email body
    email_body += registration_options(instance)

    # Add custom messages from event and association configurations
    for custom_message in [
        get_event_text(instance.run.event_id, EventTextType.SIGNUP),
        get_association_text(instance.run.event.association_id, AssociationTextType.SIGNUP),
    ]:
        if custom_message:
            email_body += "<br />" + custom_message

    # Send email to the user
    my_send_mail(email_subject, email_body, instance.member, instance.run)

    # Send notifications to event organizers based on configuration
    association_id = instance.run.event.association_id

    # Handle new registration notifications to organizers
    if instance.modified == 1 and get_association_config(association_id, "mail_signup_new", default_value=False):
        for organizer in get_event_organizers(instance.run.event):
            activate(organizer.language)
            email_subject = hdr(instance.run.event) + _("Registration to %(event)s by %(user)s") % email_context
            email_body = _("The user has confirmed its registration for this event") + "!"
            email_body += registration_options(instance)
            my_send_mail(email_subject, email_body, organizer, instance.run)

    # Handle registration update notifications to organizers
    elif get_association_config(association_id, "mail_signup_update", default_value=False):
        for organizer in get_event_organizers(instance.run.event):
            activate(organizer.language)
            email_subject = hdr(instance.run.event) + _("Registration updated to %(event)s by %(user)s") % email_context
            email_body = _("The user has updated their registration for this event") + "!"
            email_body += registration_options(instance)
            my_send_mail(email_subject, email_body, organizer, instance.run)


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


def send_character_assignment_email(instance: RegistrationCharacterRel) -> None:
    """Send character assignment email when registration-character relation is created.

    This function sends an email notification to a member when they are assigned
    a character for a LARP event. The email includes character details and a link
    to access the character information.

    Args:
        instance: RegistrationCharacterRel instance representing the assignment

    Returns:
        None

    """
    # Set the language context for email localization
    activate(instance.reg.member.language)

    # Early return if no character is assigned
    if not instance.character:
        return

    # Check if character assignment emails are disabled for this event
    if get_event_config(instance.reg.run.event_id, "mail_character", default_value=False):
        return

    # Prepare context data for email template
    email_context = {
        "event": instance.reg.run,
        "character": instance.character,
    }

    # Construct email subject with event header and localized text
    email_subject = hdr(instance.reg.run.event) + _("Character assigned for %(event)s") % email_context

    # Build the main email body with character assignment information
    email_body = (
        _("In the event <b>%(event)s</b> you were assigned the character: <b>%(character)s</b>") % email_context + "."
    )

    # Generate URL for character access page
    character_url = get_url(
        f"{instance.reg.run.get_slug()}/character/your",
        instance.reg.run.event,
    )

    # Add character access link to email body
    email_body += "<br/><br />" + _("Access your character <a href='%(url)s'>here</a>") % {"url": character_url} + "!"

    # Append custom assignment message if configured for the event
    custom_assignment_message = get_event_text(instance.reg.run.event_id, EventTextType.ASSIGNMENT)
    if custom_assignment_message:
        email_body += "<br />" + custom_assignment_message

    # Send the email to the registered member
    my_send_mail(email_subject, email_body, instance.reg.member, instance.reg.run)


def update_registration_cancellation(instance: Registration) -> None:
    """Send cancellation notification emails to user and organizers.

    Sends email notifications when a registration is cancelled:
    - Confirmation email to the user who cancelled
    - Optional notification emails to event organizers (if enabled in config)

    Args:
        instance: Registration instance that was cancelled. Must have attributes:
            - run: Event run the registration was for
            - member: User who had the registration

    Returns:
        None

    Note:
        Does nothing if the registration is provisional. Organizer notifications
        are only sent if 'mail_signup_del' config is enabled for the association.

    """
    # Skip processing for provisional registrations
    if is_reg_provisional(instance):
        return

    # Send confirmation email to the user who cancelled
    email_context = {"event": instance.run, "user": instance.member}
    activate(instance.member.language)
    email_subject = hdr(instance.run.event) + _("Registration cancellation for %(event)s") % email_context
    email_body = (
        _("We confirm that your registration for this event has been cancelled. We are sorry to see you go") + "!"
    )
    my_send_mail(email_subject, email_body, instance.member, instance.run)

    # Send notification emails to organizers if feature is enabled
    if get_association_config(instance.run.event.association_id, "mail_signup_del", default_value=False):
        # Iterate through all organizers for this event
        for organizer in get_event_organizers(instance.run.event):
            activate(organizer.language)
            email_subject = (
                hdr(instance.run.event) + _("Registration cancelled for %(event)s by %(user)s") % email_context
            )
            email_body = _("The registration for this event has been cancelled") + "."
            my_send_mail(email_subject, email_body, organizer, instance.run)


def send_registration_cancellation_email(instance: Registration) -> None:
    """Handle pre-save events for registration instances.

    Sends a cancellation email when a registration is cancelled for the first time.
    Skips processing if the event run is already completed.

    Args:
        instance: Registration instance being saved

    Returns:
        None

    """
    # Skip if run is completed/done
    if instance.run and instance.run.development == DevelopStatus.DONE:
        return

    # Retrieve previous state of the registration if it exists
    previous_registration = None
    if instance.pk:
        try:
            previous_registration = Registration.objects.get(pk=instance.pk)
        except Exception as e:
            logger.debug("Registration pk=%s not found in pre-save: %s", instance.pk, e)

    # Send cancellation email only when registration is newly cancelled
    if previous_registration and instance.cancellation_date and not previous_registration.cancellation_date:
        # Send email when canceled
        update_registration_cancellation(instance)


def send_registration_deletion_email(instance: Registration) -> None:
    """Handle registration deletion notifications.

    Sends email notifications to both the user and event organizers when a
    registration is cancelled. Skips notifications for provisional registrations
    or registrations that already have a cancellation date.

    Args:
        instance: Registration instance being deleted. Must have member, run,
                 and cancellation_date attributes.

    Returns:
        None

    """
    # Skip if registration already has a cancellation date
    if instance.cancellation_date:
        return

    # Skip notifications for provisional registrations
    if is_reg_provisional(instance):
        return

    # Prepare context for email templates
    context = {"event": instance.run, "user": instance.member}

    # Send cancellation notification to the registered user
    activate(instance.member.language)
    email_subject = hdr(instance.run.event) + _("Registration cancelled for %(event)s") % context
    email_body = _("We confirm that your registration for this event has been cancelled") + "."
    my_send_mail(email_subject, email_body, instance.member, instance.run)

    # Check if organization wants to receive deletion notifications
    if get_association_config(instance.run.event.association_id, "mail_signup_del", default_value=False):
        # Send notification to all event organizers
        for organizer in get_event_organizers(instance.run.event):
            activate(organizer.language)
            email_subject = hdr(instance.run.event) + _("Registration cancelled for %(event)s by %(user)s") % context
            email_body = _("The registration for this event has been cancelled") + "."
            my_send_mail(email_subject, email_body, organizer, instance.run)


def send_pre_registration_confirmation_email(pre_registration: Any) -> None:
    """Handle pre-registration pre-save notifications.

    Args:
        pre_registration: PreRegistration instance being saved

    """
    context = {"event": pre_registration.event}
    if not pre_registration.pk:
        subject = hdr(pre_registration.event) + _("Pre-registration at %(event)s") % context
        body_text = _("We confirm that you have successfully pre-registered for <b>%(event)s</b>") % context + "!"
        my_send_mail(subject, body_text, pre_registration.member, pre_registration.event)
