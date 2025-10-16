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

import time

from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.config import get_assoc_config
from larpmanager.cache.feature import get_event_features
from larpmanager.models.access import get_event_organizers
from larpmanager.models.association import AssocTextType, get_url, hdr
from larpmanager.models.event import DevelopStatus, EventTextType
from larpmanager.models.member import get_user_membership
from larpmanager.models.registration import Registration
from larpmanager.utils.registration import get_registration_options
from larpmanager.utils.tasks import background_auto, my_send_mail
from larpmanager.utils.text import get_assoc_text, get_event_text


@background_auto(queue="acc")
def update_registration_status_bkg(reg_id):
    """Background task to update registration status with delay.

    Args:
        reg_id: ID of the registration to update
    """
    time.sleep(1)
    instance = Registration.objects.get(pk=reg_id)
    update_registration_status(instance)


def update_registration_status(instance) -> None:
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
    context = {"event": instance.run, "user": instance.member}

    # Send notification to the registering user
    activate(instance.member.language)

    # Determine email subject and body based on modification type
    if instance.modified == 1:
        subj = hdr(instance.run.event) + _("Registration to %(event)s") % context
        body = _("Hello! Your registration at <b>%(event)s</b> has been confirmed") % context + "!"
    else:
        subj = hdr(instance.run.event) + _("Registration updated for %(event)s") % context
        body = _("Hi! Your registration to <b>%(event)s</b> has been updated") % context + "!"

    # Append registration details to email body
    body += registration_options(instance)

    # Add custom messages from event and association configurations
    for custom_mesg in [
        get_event_text(instance.run.event_id, EventTextType.SIGNUP),
        get_assoc_text(instance.run.event.assoc_id, AssocTextType.SIGNUP),
    ]:
        if custom_mesg:
            body += "<br />" + custom_mesg

    # Send email to the user
    my_send_mail(subj, body, instance.member, instance.run)

    # Send notifications to event organizers based on configuration
    assoc_id = instance.run.event.assoc_id

    # Handle new registration notifications to organizers
    if instance.modified == 1 and get_assoc_config(assoc_id, "mail_signup_new", False):
        for orga in get_event_organizers(instance.run.event):
            activate(orga.language)
            subj = hdr(instance.run.event) + _("Registration to %(event)s by %(user)s") % context
            body = _("The user has confirmed its registration for this event") + "!"
            body += registration_options(instance)
            my_send_mail(subj, body, orga, instance.run)

    # Handle registration update notifications to organizers
    elif get_assoc_config(assoc_id, "mail_signup_update", False):
        for orga in get_event_organizers(instance.run.event):
            activate(orga.language)
            subj = hdr(instance.run.event) + _("Registration updated to %(event)s by %(user)s") % context
            body = _("The user has updated their registration for this event") + "!"
            body += registration_options(instance)
            my_send_mail(subj, body, orga, instance.run)


def registration_options(instance) -> str:
    """Generate email content for registration options.

    Creates formatted text showing selected tickets and registration choices,
    including payment information, totals, and selected registration options
    for email notifications.

    Args:
        instance: Registration instance containing ticket, member, and payment data

    Returns:
        str: HTML formatted string with registration details for email content
    """
    body = ""

    # Add ticket information if selected
    if instance.ticket:
        body += "<br /><br />" + _("Ticket selected") + f": <b>{instance.ticket.name}</b>"
        if instance.ticket.description:
            body += f" - {instance.ticket.description}"

    # Get user membership and event features for permission checks
    get_user_membership(instance.member, instance.run.event.assoc.id)
    features = get_event_features(instance.run.event_id)

    # Get currency symbol for formatting monetary amounts
    currency = instance.run.event.assoc.get_currency_symbol()

    # Display total registration fee if greater than zero
    if instance.tot_iscr > 0:
        body += (
            "<br /><br />"
            + _("Total of your signup fee: <b>%(amount).2f %(currency)s</b>")
            % {
                "amount": instance.tot_iscr,
                "currency": currency,
            }
            + "."
        )

    # Display payments already received if any
    if instance.tot_payed > 0:
        body += (
            "<br /><br />"
            + _("Payments already received: <b>%(amount).2f %(currency)s</b>")
            % {
                "amount": instance.tot_payed,
                "currency": currency,
            }
            + "."
        )

    # Add payment information if payment feature enabled and quota/alert conditions met
    if "payment" in features and instance.quota > 0 and instance.alert:
        body += registration_payments(instance, currency)

    # Add selected registration options if any exist
    res = get_registration_options(instance)
    if res:
        body += "<br /><br />" + _("Selected options") + ":"
        for el in res:
            body += f"<br />{el[0]} - {el[1]}"

    return body


def registration_payments(instance, currency):
    """
    Generate payment information HTML for registration emails.

    Args:
        instance: Registration instance with payment details
        currency: Currency symbol/code for payment display

    Returns:
        str: HTML formatted payment information with links and deadlines
    """
    f_url = get_url("accounting/pay", instance.run.event)
    url = f"{f_url}/{instance.run.get_slug()}"
    data = {"url": url, "amount": instance.quota, "currency": currency, "deadline": instance.deadline}

    if instance.deadline > 0:
        return (
            "<br /><br />"
            + _(
                "You must pay at least <b>%(amount).2f %(currency)s</b> by %(deadline)d days. "
                "Make your payment <a href='%(url)s'>on this page</a>. If we do not receive "
                "payment by the deadline, your registration may be cancelled."
            )
            % data
        )

    return (
        "<br /><br />"
        + _(
            "<i>Payment due</i> - You must pay <b>%(amount).2f %(currency)s</b> as soon as "
            "possible. Make your payment <a href='%(url)s'>on this page</a>. If we do not "
            "receive payment, your registration may be cancelled."
        )
        % data
    )


def send_character_assignment_email(instance, created: bool) -> None:
    """
    Send character assignment email when registration-character relation is created.

    This function sends an email notification to a member when they are assigned
    a character for a LARP event. The email includes character details and a link
    to access the character information.

    Args:
        instance: RegistrationCharacterRel instance representing the assignment
        created: Whether the instance was just created (True) or updated (False)

    Returns:
        None
    """
    # Early return if this is an update, not a creation
    if not created:
        return

    # Set the language context for email localization
    activate(instance.reg.member.language)

    # Early return if no character is assigned
    if not instance.character:
        return

    # Check if character assignment emails are disabled for this event
    if instance.reg.run.event.get_config("mail_character", False):
        return

    # Prepare context data for email template
    context = {
        "event": instance.reg.run,
        "character": instance.character,
    }

    # Construct email subject with event header and localized text
    subj = hdr(instance.reg.run.event) + _("Character assigned for %(event)s") % context

    # Build the main email body with character assignment information
    body = _("In the event <b>%(event)s</b> you were assigned the character: <b>%(character)s</b>") % context + "."

    # Generate URL for character access page
    char_url = get_url(
        f"{instance.reg.run.get_slug()}/character/your",
        instance.reg.run.event,
    )

    # Add character access link to email body
    body += "<br/><br />" + _("Access your character <a href='%(url)s'>here</a>") % {"url": char_url} + "!"

    # Append custom assignment message if configured for the event
    custom_message_ass = get_event_text(instance.reg.run.event_id, EventTextType.ASSIGNMENT)
    if custom_message_ass:
        body += "<br />" + custom_message_ass

    # Send the email to the registered member
    my_send_mail(subj, body, instance.reg.member, instance.reg.run)


def update_registration_cancellation(instance):
    """Send cancellation notification emails to user and organizers.

    Args:
        instance: Registration instance that was cancelled
    """
    if is_reg_provisional(instance):
        return

    # to user
    context = {"event": instance.run, "user": instance.member}
    activate(instance.member.language)
    subj = hdr(instance.run.event) + _("Registration cancellation for %(event)s") % context
    body = _("We confirm that your registration for this event has been cancelled. We are sorry to see you go") + "!"
    my_send_mail(subj, body, instance.member, instance.run)

    # to orga
    if get_assoc_config(instance.run.event.assoc_id, "mail_signup_del", False):
        for orga in get_event_organizers(instance.run.event):
            activate(orga.language)
            subj = hdr(instance.run.event) + _("Registration cancelled for %(event)s by %(user)s") % context
            body = _("The registration for this event has been cancelled") + "."
            my_send_mail(subj, body, orga, instance.run)


def send_registration_cancellation_email(instance):
    """Handle pre-save events for registration instances.

    Args:
        instance: Registration instance being saved
    """
    if instance.run and instance.run.development == DevelopStatus.DONE:
        return

    prev = None
    if instance.pk:
        try:
            prev = Registration.objects.get(pk=instance.pk)
        except Exception:
            pass

    if prev and instance.cancellation_date and not prev.cancellation_date:
        # Send email when canceled
        update_registration_cancellation(instance)


def send_registration_deletion_email(instance):
    """Handle registration deletion notifications.

    Args:
        instance: Registration instance being deleted
    """
    if instance.cancellation_date:
        return

    if is_reg_provisional(instance):
        return

    context = {"event": instance.run, "user": instance.member}

    # to user
    activate(instance.member.language)
    subj = hdr(instance.run.event) + _("Registration cancelled for %(event)s") % context
    body = _("We confirm that your registration for this event has been cancelled") + "."
    my_send_mail(subj, body, instance.member, instance.run)

    if get_assoc_config(instance.run.event.assoc_id, "mail_signup_del", False):
        # to orga
        for orga in get_event_organizers(instance.run.event):
            activate(orga.language)
            subj = hdr(instance.run.event) + _("Registration cancelled for %(event)s by %(user)s") % context
            body = _("The registration for this event has been cancelled") + "."
            my_send_mail(subj, body, orga, instance.run)


def send_pre_registration_confirmation_email(instance):
    """Handle pre-registration pre-save notifications.

    Args:
        instance: PreRegistration instance being saved
    """
    context = {"event": instance.event}
    if not instance.pk:
        subj = hdr(instance.event) + _("Pre-registration at %(event)s") % context
        body = _("We confirm that you have successfully pre-registered for <b>%(event)s</b>") % context + "!"
        my_send_mail(subj, body, instance.member, instance.event)
