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
from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import holidays
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_event_config
from larpmanager.cache.event_text import get_event_text
from larpmanager.cache.links import reset_event_links
from larpmanager.models.access import AssociationRole, EventRole, get_association_executives, get_event_organizers
from larpmanager.models.association import Association, get_association_maintainers, get_url, hdr
from larpmanager.models.casting import AssignmentTrait, Casting
from larpmanager.models.event import EventTextType
from larpmanager.models.member import Member
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.larpmanager.tasks import my_send_mail

if TYPE_CHECKING:
    from larpmanager.models.registration import Registration


def check_holiday() -> bool:
    """Check if today or adjacent days are holidays in major countries.

    This function checks if the current date, yesterday, or tomorrow falls on
    a public holiday in the United States, Italy, China, or United Kingdom.

    Returns:
        bool: True if today +/-1 day is a holiday in US, IT, CN, or UK,
              False otherwise.

    """
    # Get current date
    today = timezone.now().date()

    # Check holidays in major countries
    for country_code in ["US", "IT", "CN", "UK"]:
        # Check yesterday, today, and tomorrow
        for day_offset in [-1, 0, 1]:
            date_to_check = today + timedelta(days=day_offset)
            # Check if the date is a holiday in the current country
            if date_to_check in holidays.country_holidays(country_code):
                return True
    return False


def join_email(association: Any) -> None:
    """Send welcome emails to association executives when they join.

    Args:
        association: Association instance that was just created

    Side effects:
        Sends welcome and feedback request emails to association executives

    """
    for executive_member in get_association_executives(association):
        activate(executive_member.language)
        welcome_subject = _("Welcome to LarpManager") + "!"
        welcome_body = render_to_string(
            "mails/join_association.html",
            {"member": executive_member, "association": association},
        )
        my_send_mail(welcome_subject, welcome_body, executive_member)

        activate(executive_member.language)
        feedback_subject = "We'd love your feedback on LarpManager"
        feedback_body = render_to_string(
            "mails/help_association.html",
            {"member": executive_member, "association": association},
        )
        feedback_delay_seconds = 3600 * 24 * 2
        my_send_mail(feedback_subject, feedback_body, executive_member, schedule=feedback_delay_seconds)


def on_association_roles_m2m_changed(sender: Any, **kwargs: Any) -> None:  # noqa: ARG001
    """Handle association role changes and send notifications.

    This function is triggered when members are added or removed from association roles.
    It manages cache invalidation and sends notification emails to affected parties.

    Args:
        sender: The model class that sent the signal
        **kwargs: Signal arguments containing:
            - model: The model class involved in the m2m change
            - instance: The AssociationRole instance being modified
            - action: The type of change (post_add, post_remove, post_clear)
            - pk_set: Set of primary keys of affected Member instances

    Returns:
        None

    Side Effects:
        - Sends role change notification emails to affected members
        - Sends approval notifications to association executives
        - Invalidates permission cache for affected members
        - Triggers member association join process

    """
    # Extract signal parameters with type safety
    model = kwargs.pop("model", None)
    if model == Member:
        action = kwargs.pop("action", None)
        instance: AssociationRole | None = kwargs.pop("instance", None)
        if not instance:
            return
        pk_set: list[int] | None = kwargs.pop("pk_set", None)

        # Handle role removal or clear - invalidate cache immediately
        # This ensures permissions are updated when roles are removed
        if action in ("post_remove", "post_clear"):
            if pk_set:
                for mid in pk_set:
                    mb = Member.objects.get(pk=mid)
                    # Reset cached event links to reflect permission changes
                    reset_event_links(mb.id, instance.association_id)
            return

        # Only process role additions from this point forward
        if action != "post_add":
            return

        # Get association executives for notification purposes
        # Handle case where association might not have executives yet
        try:
            exes = get_association_executives(instance.association)
        except ObjectDoesNotExist:
            exes = []

        # Process each member being added to the role
        for mid in pk_set:
            _add_member_association_role(exes, instance, mid)


def _add_member_association_role(exes: list[Member], instance: AssociationRole, mid: int | str) -> None:
    """Add a member to an association role and send notifications.

    Processes a new association role assignment by adding the member to the association,
    invalidating cached permissions, and sending notification emails to both the new
    member and existing executives.

    Args:
        exes: List of executive members who should be notified of the role assignment
        instance: AssociationRole instance representing the role being assigned
        mid: Member ID (int or str) of the member receiving the role

    Side Effects:
        - Adds member to association via join() method
        - Invalidates cached permissions for the member
        - Sends email notification to the new role holder
        - Sends email notifications to all other executives about the assignment

    """
    mb = Member.objects.get(pk=mid)
    # Trigger member association join process
    mb.join(instance.association)
    # Invalidate cached permissions for this member
    reset_event_links(mb.id, instance.association_id)
    # Send role approval notification to the member
    # Set language context for proper localization
    activate(mb.language)
    subj = hdr(instance.association) + _("Role approval %(role)s") % {"role": instance.name}
    url = get_url("manage", instance.association)
    body = _("Access the management panel <a href= %(url)s'>from here</a>") % {"url": url} + "!"
    my_send_mail(subj, body, mb, instance.association)

    # Notify existing executives about the new role assignment
    # Skip notification to the member who just received the role
    for m in exes:
        if m.pk == int(mid):
            continue
        # Set language context for each executive
        activate(m.language)
        subj = hdr(instance.association) + _("Approval %(user)s as %(role)s") % {
            "user": mb,
            "role": instance.name,
        }
        body = _("The user has been assigned the specified role") + "."
        my_send_mail(subj, body, m, instance.association)


def on_event_roles_m2m_changed(sender: type, **kwargs: Any) -> None:  # noqa: ARG001
    """Handle event role changes and send notifications.

    Args:
        sender: Signal sender class
        **kwargs: Signal arguments containing:
            - instance: EventRole instance being modified
            - model: Related model (Member)
            - action: Type of m2m change (post_add, post_remove, post_clear)
            - pk_set: Set of primary keys of affected members

    Side Effects:
        - Sends role change notification emails to affected members and organizers
        - Invalidates permission cache for affected members
        - Automatically joins members to the association if not already joined

    Note:
        This function is typically connected to EventRole.members.through's
        m2m_changed signal to handle role assignment notifications.

    """
    # Extract signal parameters with type safety
    model = kwargs.pop("model", None)
    if model == Member:
        action = kwargs.pop("action", None)
        instance: EventRole | None = kwargs.pop("instance", None)
        pk_set: list[int] | None = kwargs.pop("pk_set", None)

        # Handle role removal or clear - invalidate cache immediately
        # Cache invalidation ensures permission changes take effect
        if action in ("post_remove", "post_clear"):
            if pk_set:
                for mid in pk_set:
                    mb = Member.objects.get(pk=mid)
                    reset_event_links(mb.id, instance.event.association_id)
            return

        # Only process role additions from this point
        if action != "post_add":
            return

        # Get event organizers for notification purposes
        # Gracefully handle cases where event has no organizers yet
        try:
            orgas = get_event_organizers(instance.event)
        except ObjectDoesNotExist:
            orgas = []

        # Process each member that was added to the role
        for mid in pk_set:
            mb = Member.objects.get(pk=mid)
            # Ensure member is part of the association
            mb.join(instance.event.association)
            # Invalidate cached permissions for the member
            reset_event_links(mb.id, instance.event.association_id)

            # Send approval notification to the member
            # Use member's preferred language for personalized communication
            activate(mb.language)
            subj = hdr(instance.event.association) + _("Role approval %(role)s per %(event)s") % {
                "role": instance.name,
                "event": instance.event,
            }
            url = get_url(f"{instance.event.slug}/manage/", instance.event.association)
            body = _("Access the management panel <a href= %(url)s'>from here</a>") % {"url": url} + "!"
            my_send_mail(subj, body, mb, instance.event)

            # Notify organizers about the new role assignment
            # Skip self-notification if the organizer assigned themselves
            for m in orgas:
                if m.pk == int(mid):
                    continue
                # Use organizer's preferred language for notification
                activate(m.language)
                subj = hdr(instance.event.association) + _("Approval %(user)s as %(role)s for %(event)s") % {
                    "user": mb,
                    "role": instance.name,
                    "event": instance.event,
                }
                body = _("The user has been assigned the specified role") + "."
                my_send_mail(subj, body, m, instance.event)


def bring_friend_instructions(registration: Registration, context: dict) -> None:
    """Send friend invitation instructions to registered user.

    This function generates and sends an email to a registered user containing
    their personal discount code and instructions on how to share it with friends
    to receive mutual discounts on event registration.

    Args:
        registration: Registration instance containing member and event information
        context: Context dictionary containing discount amounts and event details.
             Expected keys: 'bring_friend_discount_to', 'bring_friend_discount_from'

    Returns:
        None

    Side Effects:
        - Activates the user's preferred language for email localization
        - Sends an email with friend invitation instructions and discount code

    """
    # Activate user's language for proper email localization
    activate(registration.member.language)

    # Build email subject with event header and localized message
    email_subject = hdr(registration.run.event) + _("Bring a friend to %(event)s") % {"event": registration.run} + "!"

    # Start email body with the user's personal discount code
    email_body = _("Personal code: <b>%(cod)s</b>") % {"cod": registration.uuid}

    # Add instructions for sharing the code and friend's discount amount
    email_body += (
        "<br /><br />"
        + _("Copy this code and share it with friends!")
        + " "
        + _(
            "Every friend who signs up and uses this code in the 'Discounts' field will "
            "receive %(amount_to)s %(currency)s off the ticket",
        )
        % {
            "amount_to": context["bring_friend_discount_to"],
            "currency": registration.run.event.association.get_currency_symbol(),
        }
        + ". "
        # Add information about the user's own discount benefit
        + _("For each of them, you will receive %(amount_from)s %(currency)s off your own event registration")
        % {
            "amount_from": context["bring_friend_discount_from"],
            "currency": registration.run.event.association.get_currency_symbol(),
        }
        + "."
    )

    # Add link to check remaining discount availability
    email_body += (
        "<br /><br />"
        + _("Check the available number of discounts <a href='%(url)s'>on this page</a>")
        % {"url": f"{registration.run.get_slug()}/limitations/"}
        + "."
    )

    # Add closing message and send the email
    email_body += "<br /><br />" + _("See you soon") + "!"
    my_send_mail(email_subject, email_body, registration.member, registration.run)


def send_trait_assignment_email(instance: AssignmentTrait) -> None:
    """Notify member when a trait is assigned to them.

    Deactivates related casting preferences and sends assignment notification email
    to the member with trait and quest details.

    Args:
        instance: AssignmentTrait instance that was saved

    Returns:
        None

    Side Effects:
        - Deactivates related casting preferences for the member
        - Sends email notification to the assigned member
        - Sets language context to member's preferred language

    """
    # Deactivate related casting preferences for this member and run
    casting_preferences = Casting.objects.filter(member_id=instance.member_id, run_id=instance.run_id, typ=instance.typ)
    for casting in casting_preferences:
        casting.active = False
        casting.save()

    # Set language context to member's preferred language
    activate(instance.member.language)

    # Skip email if character mail is disabled for this event
    if get_event_config(instance.run.event_id, "mail_character", default_value=False):
        return

    # Get trait and quest display information for the current run
    trait_display = instance.trait.show(instance.run)
    quest_display = instance.trait.quest.show(instance.run)

    # Build email subject with event header and localized text
    subject = hdr(instance.run.event) + _("Trait assigned for %(event)s") % {"event": instance.run}

    # Create main email body with trait assignment details
    body = _(
        "In the event <b>%(event)s</b> to which you are enrolled, you have been assigned the "
        "trait: <b>%(trait)s</b> of quest: <b>%(quest)s</b>.",
    ) % {"event": instance.run, "trait": trait_display["name"], "quest": quest_display["name"]}

    # Add character access link to the email body
    character_url = get_url(
        f"{instance.run.get_slug()}/character/your",
        instance.run.event,
    )
    body += "<br/><br />" + _("Access your character <a href='%(url)s'>here</a>") % {"url": character_url} + "!"

    # Append custom assignment message if configured for this event
    custom_assignment_message = get_event_text(instance.run.event_id, EventTextType.ASSIGNMENT)
    if custom_assignment_message:
        body += "<br />" + custom_assignment_message

    # Send the notification email to the member
    my_send_mail(subject, body, instance.member, instance.run)


def mail_confirm_casting(
    member: Any,
    run: Any,
    preference_category_name: str,
    selected_preferences: list,
    elements_to_avoid: str,
) -> None:
    """Send casting preference confirmation email to member.

    Sends a confirmation email to a member after they submit their casting
    preferences for a specific event run. The email includes a summary of
    their selected preferences and any items they wish to avoid.

    Args:
        member: Member instance who submitted the casting preferences.
        run: Run instance for the event the preferences are for.
        preference_category_name: Category name for the casting preferences (e.g., "Character Type").
        selected_preferences: List of selected preference items chosen by the member.
        elements_to_avoid: Items or elements the member wants to avoid in their assignment.

    Returns:
        None

    Side Effects:
        - Activates the member's preferred language for email localization
        - Sends a confirmation email via my_send_mail function

    """
    # Activate member's preferred language for localized email content
    activate(member.language)

    # Build email subject with event header and casting confirmation message
    email_subject = hdr(run.event) + _("Casting preferences saved on '%(type)s' for %(event)s") % {
        "type": preference_category_name,
        "event": run,
    }

    # Start email body with confirmation message
    email_body = _("Your preferences have been saved in the system") + ":"

    # Add selected preferences list to email body
    email_body += "<br /><br />" + "<br />".join(selected_preferences)

    # Append avoidance preferences if any were specified
    if elements_to_avoid:
        email_body += "<br/><br />"
        email_body += _("Elements you wish to avoid in the assignment") + ":"
        email_body += f" {elements_to_avoid}"

    # Send the confirmation email to the member
    my_send_mail(email_subject, email_body, member, run)


def send_character_status_update_email(instance: Character) -> None:
    """Notify player when character approval status changes.

    Sends an email notification to the character's player when the character's
    approval status changes between PROPOSED, REVIEW, and APPROVED states.
    Only sends notifications if the event has character approval enabled.

    Args:
        instance (Character): Character instance being saved with potential
            status changes

    Returns:
        None

    Side Effects:
        - Activates the player's preferred language for email content
        - Sends status change notification email to character player
        - Does nothing if approval feature disabled or no status change

    """
    # Early return if character approval feature is disabled for this event
    if not get_event_config(instance.event_id, "user_character_approval", default_value=False):
        return

    # Only proceed if character exists in DB and has an assigned player
    if instance.pk and instance.player:
        # Set language context for email content localization
        activate(instance.player.language)

        # Fetch previous state to detect status changes
        previous_character = Character.objects.get(pk=instance.pk)
        if previous_character.status != instance.status:
            # Determine appropriate email body based on new status
            email_body = None
            if instance.status == CharacterStatus.PROPOSED:
                email_body = get_event_text(instance.event_id, EventTextType.CHARACTER_PROPOSED)
            if instance.status == CharacterStatus.REVIEW:
                email_body = get_event_text(instance.event_id, EventTextType.CHARACTER_REVIEW)
            if instance.status == CharacterStatus.APPROVED:
                email_body = get_event_text(instance.event_id, EventTextType.CHARACTER_APPROVED)

            # Skip email if no template content found for this status
            if not email_body:
                return

            # Construct email subject with event, character, and status info
            email_subject = f"{hdr(instance.event)} - {instance!s} - {instance.get_status_display()}"

            # Determine context for email
            email_context = instance.event
            if instance.event.runs.exists():
                # Use the last run if the event has any runs
                email_context = instance.event.runs.last()

            # Send the notification email to the player
            my_send_mail(email_subject, email_body, instance.player, email_context)


def notify_organization_exe(
    notification_generator: callable,
    association: Association,
    context_instance: object,
) -> None:
    """Send notification to association executives.

    Sends notification emails to either the association's main email address
    or to all individual executives, depending on configuration. The function
    activates the appropriate language for each recipient before generating
    and sending the notification.

    Args:
        notification_generator: Callable that generates (subject, body) tuple for the notification.
              Should accept context_instance as parameter and return (str, str).
        association: Association instance containing executive information and settings.
        context_instance: Context instance passed to notification_generator for generating notification content.

    Returns:
        None

    Side Effects:
        - Activates language settings for each recipient
        - Sends notification emails via my_send_mail
        - May send to main_mail or individual executive emails

    """
    # Check if association has a main email configured
    if association.main_mail:
        # Use executive language for main email notifications
        activate(get_exec_language(association))

        # Generate subject and body using provided function
        (subject, body) = notification_generator(context_instance)

        # Send notification to main email address
        my_send_mail(subject, body, association.main_mail, context_instance)
        return

    # Send individual notifications to each executive
    for executive in get_association_executives(association):
        # Activate recipient's preferred language
        activate(executive.language)

        # Generate localized subject and body for this recipient
        (subject, body) = notification_generator(context_instance)

        # Send personalized notification to executive
        my_send_mail(subject, body, executive.email, context_instance)


def get_exec_language(association: Association) -> str:
    """Determine the most common language among association executives.

    Analyzes the language preferences of all association executives and returns
    the most frequently used language code. If no executives are found or no
    language preferences are set, defaults to English.

    Args:
        association: Association instance containing executives to analyze

    Returns:
        str: The language code (e.g., 'en', 'it', 'fr') preferred by the majority
             of executives, or 'en' if no executives found or no preferences set

    """
    # Initialize dictionary to count language occurrences
    language_counts = {}

    # Iterate through all association executives
    for executive in get_association_executives(association):
        executive_language = executive.language

        # Count each language preference
        if executive_language not in language_counts:
            language_counts[executive_language] = 1
        else:
            language_counts[executive_language] += 1

    # Determine the most common language or default to English
    return max(language_counts, key=language_counts.get) if language_counts else "en"


def send_support_ticket_email(instance: Any) -> None:
    """Send ticket notification email to admins and association maintainers.

    Args:
        instance: LarpManagerTicket instance

    """
    # Build email subject
    subject = f"LarpManager ticket - {instance.association.name}"
    if instance.reason:
        subject += f" [{instance.reason}]"

    # Build email body
    body = f"Ticket ID: {instance.id}<br /><br />"
    body += f"Email: {instance.email} <br /><br />"
    if instance.member:
        body += f"User: {instance.member} ({instance.member.email}) <br /><br />"
    body += instance.content
    if instance.screenshot:
        body += f"<br /><br /><img src='http://larpmanager.com/{instance.screenshot_reduced.url}' />"

    # Send to association maintainers
    for maintainer in get_association_maintainers(instance.association):
        my_send_mail(subject, body, maintainer.email)

    # Send to admins
    for _admin_name, admin_email in conf_settings.ADMINS:
        my_send_mail(subject, body, admin_email)
