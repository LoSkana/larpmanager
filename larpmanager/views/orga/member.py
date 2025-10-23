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

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all
from larpmanager.forms.miscellanea import OrgaHelpQuestionForm, SendMailForm
from larpmanager.models.access import get_event_staffers
from larpmanager.models.event import PreRegistration
from larpmanager.models.member import FirstAidChoices, Member, Membership, MembershipStatus, NewsletterChoices
from larpmanager.models.miscellanea import Email, HelpQuestion
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.utils.common import _get_help_questions, format_email_body
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.member import get_mail
from larpmanager.utils.paginate import orga_paginate
from larpmanager.utils.tasks import send_mail_exec


@login_required
def orga_newsletter(request: HttpRequest, s: str) -> HttpResponse:
    """Get newsletter recipients for an event.

    Args:
        request: The HTTP request object
        s: Event slug identifier

    Returns:
        Rendered newsletter template with recipient list
    """
    # Check user permissions for newsletter feature
    ctx = check_event_permission(request, s, "orga_newsletter")

    # Get active registrations (non-cancelled, non-waiting)
    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
    que = que.exclude(ticket__tier=TicketTier.WAITING).select_related("member")

    # Extract member details for newsletter recipients
    ctx["list"] = que.values_list("member__id", "member__email", "member__name", "member__surname")

    return render(request, "larpmanager/orga/users/newsletter.html", ctx)


@login_required
def orga_safety(request: HttpRequest, s: str) -> HttpResponse:
    """Process safety-related member data forms.

    Retrieves and displays safety information for all registered members
    who have provided safety data longer than the minimum required length.
    Associates each member with their character information.

    Args:
        request: HTTP request object containing user session and form data
        s: Event slug identifier for the specific event

    Returns:
        HttpResponse: Rendered safety information template containing member
                     data and their associated characters

    Note:
        Only includes members with safety information longer than min_length
        and excludes cancelled registrations.
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_safety")
    get_event_cache_all(ctx)
    min_length = 3

    # Build mapping of member IDs to their character list
    member_chars = {}
    for _num, el in ctx["chars"].items():
        if "player_id" not in el:
            continue
        # Initialize member's character list if not exists
        if el["player_id"] not in member_chars:
            member_chars[el["player_id"]] = []
        # Add formatted character info to member's list
        member_chars[el["player_id"]].append(f"#{el['number']} {el['name']}")

    # Query registered members with safety information
    ctx["list"] = []
    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
    # Exclude members without safety data and optimize with select_related
    que = que.exclude(member__safety__isnull=True).select_related("member")

    # Filter members with sufficient safety information length
    for el in que:
        if len(el.member.safety) > min_length:
            # Attach character list to member if available
            if el.member_id in member_chars:
                el.member.chars = member_chars[el.member_id]
            ctx["list"].append(el.member)

    # Sort members alphabetically by display name
    ctx["list"] = sorted(ctx["list"], key=lambda x: x.display_member())

    return render(request, "larpmanager/orga/users/safety.html", ctx)


@login_required
def orga_diet(request: HttpRequest, s: str) -> HttpResponse:
    """Handle dietary preference management forms.

    This view collects and displays dietary preferences for all registered
    members of an event, along with their associated characters.

    Args:
        request: HTTP request object containing user session and form data
        s: Event slug identifier for the specific event

    Returns:
        HttpResponse: Rendered template displaying diet preferences with
                     member data and their associated characters

    Note:
        Only shows members with dietary preferences longer than min_length
        characters and excludes cancelled registrations.
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_diet")
    get_event_cache_all(ctx)
    min_length = 3

    # Build mapping of member IDs to their character names and numbers
    member_chars = {}
    for _num, el in ctx["chars"].items():
        if "player_id" not in el:
            continue
        if el["player_id"] not in member_chars:
            member_chars[el["player_id"]] = []
        member_chars[el["player_id"]].append(f"#{el['number']} {el['name']}")

    # Query all non-cancelled registrations with dietary preferences
    ctx["list"] = []
    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
    que = que.exclude(member__diet__isnull=True).select_related("member")

    # Filter members with substantial dietary info and attach character data
    for el in que:
        if len(el.member.diet) > min_length:
            if el.member_id in member_chars:
                el.member.chars = member_chars[el.member_id]
            ctx["list"].append(el.member)

    # Sort members alphabetically by display name
    ctx["list"] = sorted(ctx["list"], key=lambda x: x.display_member())

    return render(request, "larpmanager/orga/users/diet.html", ctx)


@login_required
def orga_spam(request: HttpRequest, s: str) -> HttpResponse:
    """Manage spam/newsletter preference settings for event organizers.

    This function retrieves members who have opted into newsletters, excludes those
    already registered for current/future event runs or are event staff, and groups
    the remaining members by language for targeted email campaigns.

    Args:
        request: The HTTP request object containing user session and data
        s: The event slug identifier used to look up the specific event

    Returns:
        HttpResponse: Rendered template with newsletter management interface
        containing email lists grouped by member language preferences
    """
    # Check user permissions for spam management feature
    ctx = check_event_permission(request, s, "orga_spam")

    # Get members already registered for current or future runs
    already = list(
        Registration.objects.filter(run__event=ctx["event"], run__end__gte=date.today()).values_list(
            "member_id", flat=True
        )
    )

    # Add event staff members to exclusion list
    already.extend([mb.id for mb in get_event_staffers(ctx["event"])])

    # Get all active association members (exclude empty memberships)
    members = Membership.objects.filter(assoc_id=ctx["a_id"])
    members = members.exclude(status=MembershipStatus.EMPTY).values_list("member_id", flat=True)

    # Build language-grouped email lists for newsletter subscribers
    lst = {}
    que = Member.objects.filter(newsletter=NewsletterChoices.ALL)
    que = que.filter(id__in=members)
    que = que.exclude(id__in=already)

    # Group email addresses by member language preference
    for m in que.values_list("language", "email"):
        language = m[0]
        if language not in lst:
            lst[language] = []
        lst[language].append(m[1])

    # Add grouped email lists to template context
    ctx["lst"] = lst
    return render(request, "larpmanager/orga/users/spam.html", ctx)


@login_required
def orga_persuade(request, s: str) -> HttpResponse:
    """Display members who can be persuaded to register for the event.

    Shows association members who haven't registered yet, excluding current
    registrants and staff, with pre-registration status and event history.

    Args:
        request: Django HTTP request object
        s: Event slug identifier

    Returns:
        HttpResponse: Rendered template with member persuasion data
    """
    # Check permissions and get event context
    ctx = check_event_permission(request, s, "orga_persuade")

    # Get list of members already registered for current/future runs
    already = list(
        Registration.objects.filter(run__event=ctx["event"], run__end__gte=date.today()).values_list(
            "member_id", flat=True
        )
    )

    # Add event staff members to exclusion list
    already.extend([mb.id for mb in get_event_staffers(ctx["event"])])

    # Get active association members
    members = Membership.objects.filter(assoc_id=ctx["a_id"])
    members = members.exclude(status=MembershipStatus.EMPTY).values_list("member_id", flat=True)

    # Filter out already registered/staff members
    que = Member.objects.filter(id__in=members)
    que = que.exclude(id__in=already)

    # Get pre-registration status for all members
    pre_regs = set(PreRegistration.objects.filter(event=ctx["event"]).values_list("member_id", flat=True))

    # Calculate registration counts for each member
    reg_counts = {}
    for el in (
        Registration.objects.filter(member_id__in=members, cancellation_date__isnull=True)
        .exclude(member_id__in=already)
        .values("member_id")
        .annotate(Count("member_id"))
    ):
        reg_counts[el["member_id"]] = el["member_id__count"]

    # Build final member list with pre-registration and count data
    ctx["lst"] = []
    for m in que.values_list("id", "name", "surname", "nickname"):
        pre_reg = m[0] in pre_regs
        reg_count = 0
        if m[0] in reg_counts:
            reg_count = reg_counts[m[0]]
        ctx["lst"].append((m[0], m[1], m[2], m[3], pre_reg, reg_count))

    return render(request, "larpmanager/orga/users/persuade.html", ctx)


@login_required
def orga_questions(request: HttpRequest, s: str) -> HttpResponse:
    """Render questions page for event organizers with open and closed questions sorted by creation date."""
    ctx = check_event_permission(request, s, "orga_questions")

    # Get help questions separated by status
    ctx["closed"], ctx["open"] = _get_help_questions(ctx, request)

    # Sort open questions by creation date (oldest first)
    ctx["open"].sort(key=lambda x: x.created)
    # Sort closed questions by creation date (newest first)
    ctx["closed"].sort(key=lambda x: x.created, reverse=True)

    return render(request, "larpmanager/orga/users/questions.html", ctx)


@login_required
def orga_questions_answer(request: HttpRequest, s: str, r: int) -> HttpResponse:
    """Handle organizer responses to member help questions.

    This view allows organizers to respond to help questions submitted by members
    for a specific event. It displays the member's information, their characters,
    and the conversation history of help questions.

    Args:
        request: HTTP request object containing POST data for form submission
        s: Event/run identifier (slug or ID)
        r: Member ID who submitted the question

    Returns:
        HttpResponse: Rendered template for answering help questions or redirect
            to questions list after successful submission

    Raises:
        Member.DoesNotExist: If the specified member ID doesn't exist
        PermissionDenied: If user lacks required event permissions
    """
    # Check organizer permissions for this event and get context
    ctx = check_event_permission(request, s, "orga_questions")

    # Get the member who submitted the question
    member = Member.objects.get(pk=r)

    # Handle form submission for organizer's answer
    if request.method == "POST":
        form = OrgaHelpQuestionForm(request.POST, request.FILES)
        if form.is_valid():
            # Create new help question entry as organizer response
            hp = form.save(commit=False)
            hp.member = member
            hp.is_user = False  # Mark as organizer response
            hp.assoc_id = ctx["a_id"]
            hp.run = ctx["run"]
            hp.save()

            # Show success message and redirect back to questions list
            messages.success(request, _("Answer submitted!"))
            return redirect("orga_questions", s=s)
    else:
        # Initialize empty form for GET requests
        form = OrgaHelpQuestionForm()

    # Add form and member to template context
    ctx["form"] = form
    ctx["member"] = member

    # Get cached event data (characters, factions, etc.)
    get_event_cache_all(ctx)

    # Find characters and factions associated with this member
    ctx["reg_characters"] = []
    ctx["reg_factions"] = []
    for _num, char in ctx["chars"].items():
        # Skip characters without assigned players
        if "player_id" not in char:
            continue

        # Add character if it belongs to the current member
        if char["player_id"] == member.id:
            ctx["reg_characters"].append(char)
            # Collect all factions for this member's characters
            for fnum in char["factions"]:
                ctx["reg_factions"].append(ctx["factions"][fnum])

    # Get all help questions for this member in this event, newest first
    ctx["list"] = HelpQuestion.objects.filter(member_id=r, assoc_id=ctx["a_id"], run_id=ctx["run"]).order_by("-created")

    return render(request, "larpmanager/orga/users/questions_answer.html", ctx)


@login_required
def orga_questions_close(request: HttpRequest, s: str, r: str) -> HttpResponse:
    """Close a help question for an organization event."""
    ctx = check_event_permission(request, s, "orga_questions")

    # Get the most recent help question for this member and run
    h = HelpQuestion.objects.filter(member_id=r, assoc_id=ctx["a_id"], run_id=ctx["run"]).order_by("-created").first()

    # Mark the question as closed and save
    h.closed = True
    h.save()

    return redirect("orga_questions", s=s)


def send_mail_batch(request: HttpRequest, assoc_id: int | None = None, run_id: int | None = None) -> None:
    """Send batch email to players with specified subject and body.

    Args:
        request: HTTP request containing POST data with email details
        assoc_id: Optional association ID for context
        run_id: Optional run ID for context
    """
    # Extract email parameters from POST data
    players = request.POST["players"]
    subj = request.POST["subject"]
    body = request.POST["body"]
    raw = request.POST["raw"]
    reply_to = request.POST["reply_to"]

    # Use raw body if provided, otherwise use formatted body
    if raw:
        body = raw

    # Execute the email sending operation
    send_mail_exec(players, subj, body, assoc_id, run_id, reply_to)


@login_required
def orga_send_mail(request: HttpRequest, s: str) -> HttpResponse:
    """Send mail to event participants.

    Handles both GET requests (displays form) and POST requests (processes form submission).
    On successful form submission, queues mail for batch sending and redirects to same page.

    Args:
        request: The HTTP request object containing form data and user session
        s: Event slug identifier for permission checking and context building

    Returns:
        HttpResponse: Rendered template with form or redirect response after successful submission
    """
    # Check user permissions and build event context
    ctx = check_event_permission(request, s, "orga_send_mail")

    if request.method == "POST":
        # Process form submission for mail sending
        form = SendMailForm(request.POST)
        if form.is_valid():
            # Queue mail for batch processing using current run
            send_mail_batch(request, run_id=ctx["run"].id)
            messages.success(request, _("Mail added to queue!"))
            return redirect(request.path_info)
    else:
        # Display empty form for GET requests
        form = SendMailForm()

    # Add form to context and render template
    ctx["form"] = form
    return render(request, "larpmanager/exe/users/send_mail.html", ctx)


@login_required
def orga_archive_email(request: HttpRequest, s: str) -> HttpResponse:
    """Archive email view for organization event management.

    Displays a paginated archive of emails sent for a specific event,
    with formatting callbacks for proper display of email data.

    Args:
        request: The HTTP request object containing user and session data
        s: The event slug identifier for permission checking

    Returns:
        HttpResponse: Rendered template with email archive data and pagination
    """
    # Check user permissions for accessing email archive
    ctx = check_event_permission(request, s, "orga_archive_email")

    # Define display fields for email archive table
    # Each tuple contains (field_name, display_label)
    ctx.update(
        {
            "fields": [
                ("recipient", _("Recipient")),
                ("subj", _("Subject")),
                ("body", _("Body")),
                ("sent", _("Sent")),
            ],
            # Define formatting callbacks for each field
            # These functions control how data is displayed in the template
            "callbacks": {
                "body": format_email_body,
                "sent": lambda el: el.sent.strftime("%d/%m/%Y %H:%M") if el.sent else "",
                "run": lambda el: str(el.run) if el.run else "",
                "recipient": lambda el: str(el.recipient),
                "subj": lambda el: str(el.subj),
            },
        }
    )

    # Return paginated email archive using the Email model
    return orga_paginate(request, ctx, Email, "larpmanager/exe/users/archive_mail.html", "orga_read_mail")


@login_required
def orga_read_mail(request, s, nm):
    ctx = check_event_permission(request, s, "orga_archive_email")
    ctx["email"] = get_mail(request, ctx, nm)
    return render(request, "larpmanager/exe/users/read_mail.html", ctx)


@login_required
def orga_sensitive(request: HttpRequest, s: str) -> HttpResponse:
    """Display sensitive member information for event organizers.

    This view allows event organizers to access sensitive member information
    for registered participants and staff members. It includes character
    assignments and configurable member fields.

    Args:
        request: HTTP request object containing user and association data
        s: Event/run identifier string used to locate the specific event

    Returns:
        HttpResponse: Rendered template with member sensitive data and character assignments

    Note:
        Requires 'orga_sensitive' permission for the specified event.
        Displays only non-cancelled registrations and event staff members.
    """
    # Check user permissions for accessing sensitive data
    ctx = check_event_permission(request, s, "orga_sensitive")

    # Load all event-related cache data
    get_event_cache_all(ctx)

    # Build mapping of member IDs to their character assignments
    member_chars = {}
    for _num, el in ctx["chars"].items():
        if "player_id" not in el:
            continue
        if el["player_id"] not in member_chars:
            member_chars[el["player_id"]] = []
        member_chars[el["player_id"]].append(f"#{el['number']} {el['name']}")

    # Collect all relevant member IDs (registered participants + staff)
    member_list = list(
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True).values_list("member_id", flat=True)
    )
    member_list.extend([mb.id for mb in get_event_staffers(ctx["run"].event)])

    # Define member model and fields to display
    member_cls: type[Member] = Member
    member_fields = ["name", "surname"] + sorted(request.assoc["members_fields"])

    # Query and process member data
    ctx["list"] = Member.objects.filter(id__in=member_list).order_by("created")
    for el in ctx["list"]:
        # Attach character assignments to each member
        if el.id in member_chars:
            el.chars = member_chars[el.id]

        # Apply field corrections/formatting
        member_field_correct(el, member_fields)

    # Build field metadata for template display
    ctx["fields"] = {}
    for field_name in member_fields:
        if not field_name:
            continue
        # Skip fields that shouldn't be displayed in sensitive view
        if field_name in ["diet", "safety", "profile", "newsletter", "language"]:
            continue
        # noinspection PyUnresolvedReferences, PyProtectedMember
        ctx["fields"][field_name] = member_cls._meta.get_field(field_name).verbose_name

    # Sort members by display name for consistent ordering
    ctx["list"] = sorted(ctx["list"], key=lambda x: x.display_member())

    return render(request, "larpmanager/orga/users/sensitive.html", ctx)


def member_field_correct(el: object, member_fields: list[str]) -> None:
    """Correct and format specific member fields for display purposes.

    Args:
        el: Member object to modify fields on
        member_fields: List of field names to process and format

    Returns:
        None: Modifies the member object in place
    """
    # Format residence address using the member's get_residence method
    if "residence_address" in member_fields:
        el.residence_address = el.get_residence()

    # Convert first aid boolean to checkmark icon or empty string
    if "first_aid" in member_fields:
        if el.first_aid == FirstAidChoices.YES:
            el.first_aid = mark_safe('<i class="fa-solid fa-check"></i>')
        else:
            el.first_aid = ""

    # Convert document type enum to human-readable display value
    if "document_type" in member_fields:
        el.document_type = el.get_document_type_display()

    # Convert gender enum to human-readable display value
    if "gender" in member_fields:
        el.gender = el.get_gender_display()
