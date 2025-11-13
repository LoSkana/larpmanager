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

import csv
from collections import defaultdict
from datetime import datetime, timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, Count, IntegerField, Value, When
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.payment import unique_invoice_cod
from larpmanager.accounting.registration import update_member_registrations
from larpmanager.cache.config import get_association_config
from larpmanager.forms.member import (
    ExeBadgeForm,
    ExeMemberForm,
    ExeMembershipDocumentForm,
    ExeMembershipFeeForm,
    ExeMembershipForm,
    ExeVolunteerRegistryForm,
    MembershipResponseForm,
)
from larpmanager.forms.miscellanea import (
    OrgaHelpQuestionForm,
    SendMailForm,
)
from larpmanager.mail.member import notify_membership_approved, notify_membership_reject
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemPayment,
    OtherChoices,
    PaymentChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.association import Association
from larpmanager.models.event import Run
from larpmanager.models.member import (
    Badge,
    Member,
    Membership,
    MembershipStatus,
    VolunteerRegistry,
    Vote,
    get_user_membership,
)
from larpmanager.models.miscellanea import (
    Email,
    HelpQuestion,
)
from larpmanager.models.registration import Registration
from larpmanager.utils.base import check_association_context
from larpmanager.utils.common import (
    _get_help_questions,
    format_email_body,
    get_member,
    normalize_string,
)
from larpmanager.utils.edit import exe_edit
from larpmanager.utils.fiscal_code import calculate_fiscal_code
from larpmanager.utils.member import get_mail
from larpmanager.utils.paginate import exe_paginate
from larpmanager.utils.pdf import (
    get_membership_request,
    print_volunteer_registry,
    return_pdf,
)
from larpmanager.views.orga.member import send_mail_batch


@login_required
def exe_membership(request: HttpRequest) -> HttpResponse:
    """Manage association memberships.

    Displays membership statistics, fee collection status, and membership
    administration tools for association executives. Shows pending memberships
    with priority sorting and includes upcoming event registrations.

    Args:
        request: The HTTP request object containing user and session data.

    Returns:
        HttpResponse: Rendered template with membership data and statistics.

    """
    # Check user permissions and get association context
    context = check_association_context(request, "exe_membership")

    # Get set of member IDs who have paid membership fees for current year
    fees = set(
        AccountingItemMembership.objects.filter(
            association_id=context["association_id"],
            year=datetime.now().year,
        ).values_list("member_id", flat=True),
    )

    # Build dictionary of upcoming runs (events that haven't ended yet)
    next_runs = dict(
        Run.objects.filter(event__association_id=context["association_id"], end__gt=datetime.today()).values_list(
            "pk",
            "search",
        ),
    )

    # Get registrations for upcoming runs and group by member
    next_regs_qs = Registration.objects.filter(run__id__in=next_runs.keys()).values_list("run_id", "member_id")

    # Create member_id -> [run_ids] mapping for upcoming registrations
    next_regs = defaultdict(list)
    for run_id, member_id in next_regs_qs:
        next_regs[member_id].append(run_id)

    # Query memberships excluding certain statuses, with priority sorting
    que = (
        Membership.objects.filter(association_id=context["association_id"])
        .select_related("member")
        .exclude(status__in=[MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED])
        .annotate(
            sort_priority=Case(
                When(status=MembershipStatus.SUBMITTED, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        .order_by("sort_priority", "-updated")
    )

    # Define fields to extract from membership query
    values = ("member__id", "member__surname", "member__name", "member__email", "card_number", "status")
    context["list"] = []
    context["sum"] = {}

    # Process each membership record
    for el in que.values(*values):
        status = el["status"]

        # Mark accepted members with paid fees as "paid" status
        if status == MembershipStatus.ACCEPTED and el["member__id"] in fees:
            el["status"] = "p"
            el["status_display"] = _("Payed")
        else:
            el["status_display"] = MembershipStatus(el["status"]).label

        # Count memberships by status for summary statistics
        if el["status"] not in context["sum"]:
            context["sum"][el["status"]] = 0
        context["sum"][el["status"]] += 1

        # Add upcoming run names for members with registrations
        if el["member__id"] in next_regs:
            el["run_names"] = ", ".join(
                [next_runs[run_id] for run_id in next_regs[el["member__id"]] if run_id in next_runs],
            )
        context["list"].append(el)

    return render(request, "larpmanager/exe/users/membership.html", context)


@login_required
def exe_membership_evaluation(request: HttpRequest, num: int) -> HttpResponse:
    """Evaluate membership applications.

    Handles membership approval/rejection processes and status updates,
    including notifications, duplicate checking, and registration updates
    for approved members.

    Args:
        request: The HTTP request object
        num: Primary key of the member to evaluate

    Returns:
        HttpResponse: Rendered template with membership evaluation form

    """
    # Check user permissions and get association context
    context = check_association_context(request, "exe_membership")

    # Get member and their membership status
    member = Member.objects.get(pk=num)
    get_user_membership(member, context["association_id"])

    if request.method == "POST":
        # Process membership evaluation form submission
        form = MembershipResponseForm(request.POST)
        if form.is_valid():
            resp = form.cleaned_data["response"]

            # Handle approval or rejection based on form data
            if form.cleaned_data["is_approved"]:
                # Approve member and send notifications
                member.membership.status = MembershipStatus.ACCEPTED
                member.membership.save()
                notify_membership_approved(member, resp)
                update_member_registrations(member)
                messages.success(request, _("Member approved!"))
            else:
                # Reject member and send notifications
                member.membership.status = MembershipStatus.EMPTY
                member.membership.save()
                notify_membership_reject(member, resp)
                messages.success(request, _("Member refused!"))

            return redirect("exe_membership")
    else:
        # Initialize empty form for GET requests
        form = MembershipResponseForm()

    # Add member and form to context
    context["member"] = member
    context["form"] = form

    # Add document path if document exists
    if member.membership.document:
        context["doc_path"] = member.membership.get_document_filepath().lower()

    # Add request path if request exists
    if member.membership.request:
        context["req_path"] = member.membership.get_request_filepath().lower()

    # Normalize member name and surname for duplicate checking
    normalized_name = normalize_string(member.name)
    normalized_surname = normalize_string(member.surname)

    # Check for existing members with same normalized name/surname
    context["member_exists"] = False
    que = Membership.objects.select_related("member").filter(association_id=context["association_id"])
    que = que.exclude(status__in=[MembershipStatus.EMPTY, MembershipStatus.JOINED]).exclude(member_id=member.id)

    # Compare normalized names to detect potential duplicates
    for other in que.values_list("member__surname", "member__name"):
        if normalize_string(other[1]) == normalized_name and normalize_string(other[0]) == normalized_surname:
            context["member_exists"] = True

    # Add fiscal code validation if feature is enabled
    if "fiscal_code_check" in context["features"]:
        context.update(calculate_fiscal_code(member))

    return render(request, "larpmanager/exe/users/membership_evaluation.html", context)


@login_required
def exe_membership_request(request: HttpRequest, num: int) -> HttpResponse:
    """Handle membership request display for organization executives."""
    context = check_association_context(request, "exe_membership")
    member_request = get_member(num)
    return get_membership_request(context, member_request)


@login_required
def exe_membership_check(request: HttpRequest) -> HttpResponse:
    """Check and report membership status inconsistencies.

    Analyzes membership data to identify and report various inconsistencies,
    including fiscal code validation when the feature is enabled.

    Args:
        request: The HTTP request object containing user and session data.

    Returns:
        HttpResponse: Rendered template with membership check report data.

    """
    # Check user permissions and get association context
    context = check_association_context(request, "exe_membership_check")

    # Get all members with active memberships (excluding empty/joined status)
    member_ids = set(
        Membership.objects.filter(association_id=context["association_id"])
        .select_related("member")
        .exclude(status__in=[MembershipStatus.EMPTY, MembershipStatus.JOINED])
        .values_list("member_id", flat=True),
    )

    # Perform fiscal code validation if feature is enabled
    if "fiscal_code_check" in context["features"]:
        context["cf"] = []

        # Check each member's fiscal code for correctness
        for mb in Member.objects.filter(pk__in=member_ids):
            check = calculate_fiscal_code(mb)
            if not check:
                continue

            # Add members with incorrect fiscal codes to report
            if not check["correct_cf"]:
                check["member"] = str(mb)
                check["member_id"] = mb.id
                check["email"] = mb.email
                check["membership"] = get_user_membership(mb, context["association_id"])
                context["cf"].append(check)

    return render(request, "larpmanager/exe/users/membership_check.html", context)


@login_required
def exe_member(request: HttpRequest, num: int) -> HttpResponse:
    """Display and edit member profile with accounting and membership data.

    This view handles both GET requests for displaying member information and POST
    requests for updating member profiles. It includes accounting data, registrations,
    discounts, and membership documents.

    Args:
        request: The HTTP request object containing user session and form data
        num: The unique identifier (ID) of the member to display/edit

    Returns:
        HttpResponse: Rendered template with member edit form and associated data

    Raises:
        Http404: If member with given ID doesn't exist or user lacks permissions

    """
    # Check user permissions and get association context
    context = check_association_context(request, "exe_membership")
    context["member_edit"] = get_member(num)

    # Handle form submission for member profile updates
    if request.method == "POST":
        form = ExeMemberForm(request.POST, request.FILES, instance=context["member_edit"], context=context)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated"))
            return redirect(request.path)
    else:
        # Initialize empty form for GET requests
        form = ExeMemberForm(instance=context["member_edit"], context=context)
    context["form"] = form

    # Get member registrations for current association events
    context["regs"] = Registration.objects.filter(
        member=context["member_edit"],
        run__event__association=context["association_id"],
    ).select_related("run")

    # Add accounting payment items to context
    member_add_accountingitempayment(context, context["member_edit"])

    # Add other accounting items to context
    member_add_accountingitemother(context, context["member_edit"])

    # Get member discounts for current association
    context["discounts"] = AccountingItemDiscount.objects.filter(
        member=context["member_edit"],
        hide=False,
        association_id=context["association_id"],
    )

    # Process membership data and document paths
    get_user_membership(context["member_edit"], context["association_id"])

    # Set document file paths if they exist
    if context["member_edit"].membership.document:
        context["doc_path"] = context["member_edit"].membership.get_document_filepath().lower()

    if context["member_edit"].membership.request:
        context["req_path"] = context["member_edit"].membership.get_request_filepath().lower()

    # Add fiscal code validation if feature is enabled
    if "fiscal_code_check" in context["features"]:
        context.update(calculate_fiscal_code(context["member_edit"]))

    return render(request, "larpmanager/exe/users/member.html", context)


def member_add_accountingitempayment(context: dict, member: Member) -> dict:
    """Add accounting item payment information to context for a member.

    Retrieves non-hidden payments for the member and sets display type based on payment method.
    """
    # Fetch visible payments for the member in the current association
    context["pays"] = AccountingItemPayment.objects.filter(
        member=member,
        hide=False,
        association_id=context["association_id"],
    ).select_related("reg")

    # Set display type based on payment method
    for payment in context["pays"]:
        if payment.pay == PaymentChoices.TOKEN:
            payment.typ = context.get("token_name", _("Credits"))
        elif payment.pay == PaymentChoices.CREDIT:
            payment.typ = context.get("credit_name", _("Credits"))
        else:
            payment.typ = payment.get_pay_display()


def member_add_accountingitemother(context: dict, member: Member) -> None:
    """Add accounting other items to member context with localized type labels."""
    # Query non-hidden accounting items for the member in current association
    context["others"] = AccountingItemOther.objects.filter(
        member=member,
        hide=False,
        association_id=context["association_id"],
    ).select_related("run")

    # Set localized type labels based on item category
    for accounting_item in context["others"]:
        if accounting_item.oth == OtherChoices.TOKEN:
            accounting_item.typ = context.get("token_name", _("Credits"))
        elif accounting_item.oth == OtherChoices.CREDIT:
            accounting_item.typ = context.get("credit_name", _("Credits"))
        else:
            accounting_item.typ = accounting_item.get_oth_display()


@login_required
def exe_membership_status(request: HttpRequest, num):
    """Edit membership status and details for a specific member.

    Args:
        request: Django HTTP request object
        num: Member number identifier

    Returns:
        Rendered membership editing form or redirect after successful update

    """
    context = check_association_context(request, "exe_membership")
    context["member_edit"] = get_member(num)
    context["membership_edit"] = get_object_or_404(
        Membership,
        member_id=context["member_edit"].id,
        association_id=context["association_id"],
    )

    if request.method == "POST":
        form = ExeMembershipForm(request.POST, request.FILES, instance=context["membership_edit"], request=request)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated"))
            return redirect(request.path)
    else:
        form = ExeMembershipForm(instance=context["membership_edit"], request=request)
    context["form"] = form

    context["num"] = num

    context["form"].page_title = str(context["member_edit"]) + " - " + _("Membership")

    return render(request, "larpmanager/exe/edit.html", context)


@login_required
def exe_membership_registry(request: HttpRequest) -> HttpResponse:
    """Generate membership registry with card numbers for association executives.

    Creates a formatted list of association members who have card numbers,
    with properly capitalized names split into first and last name components.

    Args:
        request: Django HTTP request object containing user session and context

    Returns:
        HttpResponse: Rendered registry.html template with formatted member list
        containing members with card numbers, ordered by card number

    """
    # Check user permissions for accessing membership registry
    context = check_association_context(request, "exe_membership_registry")
    split_two_names = 2

    # Initialize empty list for processed members
    context["list"] = []

    # Query memberships with card numbers for current association
    que = Membership.objects.filter(association_id=context["association_id"], card_number__isnull=False)

    # Process each membership and format member data
    for mb in que.select_related("member").order_by("card_number"):
        member = mb.member
        member.membership = mb

        # Split legal name into first and last name components
        if member.legal_name:
            splitted = member.legal_name.rsplit(" ", 1)
            if len(splitted) == split_two_names:
                member.name, member.surname = splitted
            else:
                member.name = splitted[0]

        # Capitalize name components for consistent formatting
        member.name = member.name.capitalize()
        member.surname = member.surname.capitalize()

        # Add processed member to context list
        context["list"].append(member)

    # Render template with processed member data
    return render(request, "larpmanager/exe/users/registry.html", context)


@login_required
def exe_membership_fee(request: HttpRequest) -> HttpResponse:
    """Process membership fee payments for executives.

    This function handles both GET and POST requests for processing membership fee
    payments. It validates the form data, creates a payment invoice, and confirms
    the payment automatically.

    Args:
        request (HttpRequest): The HTTP request object containing form data for POST
                              requests or empty for GET requests to display the form.

    Returns:
        HttpResponse: For GET requests, returns the membership fee form page.
                     For successful POST requests, redirects to the membership page.
                     For invalid POST requests, returns the form with validation errors.

    Raises:
        PermissionDenied: If user lacks 'exe_membership' permission (handled by decorator).

    """
    # Check user permissions and get association context
    context = check_association_context(request, "exe_membership")

    if request.method == "POST":
        # Initialize form with POST data and context
        form = ExeMembershipFeeForm(request.POST, request.FILES, context=context)

        if form.is_valid():
            # Extract validated form data
            member = form.cleaned_data["member"]
            association_id = context["association_id"]

            # Get membership fee amount from association configuration
            fee = get_association_config(association_id, "membership_fee", default_value="0")

            # Create payment invoice record with confirmed status
            payment = PaymentInvoice.objects.create(
                member=member,
                typ=PaymentType.MEMBERSHIP,
                invoice=form.cleaned_data["invoice"],
                method_id=form.cleaned_data["method"],
                mc_gross=fee,
                causal=_("Membership fee of") + f" {member}",
                association_id=association_id,
                cod=unique_invoice_cod(),
            )

            # Automatically confirm the payment and save
            payment.status = PaymentStatus.CONFIRMED
            payment.save()

            # Show success message and redirect to membership page
            messages.success(request, _("Operation completed") + "!")
            return redirect("exe_membership")
    else:
        # Initialize empty form for GET requests
        form = ExeMembershipFeeForm(context=context)

    # Add form to context and render the edit template
    context["form"] = form
    return render(request, "larpmanager/exe/edit.html", context)


@login_required
def exe_membership_document(request: HttpRequest):
    """Handle membership document upload and approval process.

    Args:
        request: Django HTTP request object

    Returns:
        Rendered form for document upload or redirect to membership list

    """
    context = check_association_context(request, "exe_membership")

    if request.method == "POST":
        form = ExeMembershipDocumentForm(request.POST, request.FILES, context=context)
        if form.is_valid():
            member = form.cleaned_data["member"]
            membership = Membership.objects.get(association_id=context["association_id"], member=member)
            membership.document = form.cleaned_data["document"]
            membership.request = form.cleaned_data["request"]
            membership.card_number = form.cleaned_data["card_number"]
            membership.date = form.cleaned_data["date"]
            membership.status = MembershipStatus.ACCEPTED
            membership.save()
            messages.success(request, _("Operation completed") + "!")
            return redirect("exe_membership")
    else:
        form = ExeMembershipDocumentForm(context=context)
    context["form"] = form

    return render(request, "larpmanager/exe/edit.html", context)


@login_required
def exe_enrolment(request: HttpRequest) -> HttpResponse:
    """Display yearly enrollment list with membership card numbers.

    Generates a list of enrolled members for the current year, including their
    membership card numbers and enrollment dates. Members are ordered by their
    card numbers and include calculated enrollment order based on days from
    year start.

    Args:
        request (HttpRequest): The HTTP request object containing user and
            association context.

    Returns:
        HttpResponse: Rendered template with context containing:
            - year: Current year
            - list: List of members with membership details, enrollment dates,
              and formatted names

    """
    # Check user permissions and get association context
    context = check_association_context(request, "exe_enrolment")
    split_two_names = 2

    # Set current year and calculate year start date
    context["year"] = datetime.now(timezone.utc).year
    start = datetime(context["year"], 1, 1, tzinfo=timezone.utc)

    # Build cache of member enrollment dates from accounting items
    cache = {}
    for el in AccountingItemMembership.objects.filter(
        association_id=context["association_id"],
        year=context["year"],
    ).values_list("member_id", "created"):
        cache[el[0]] = el[1]

    # Query memberships with card numbers for enrolled members
    context["list"] = []
    que = Membership.objects.filter(
        member_id__in=cache.keys(),
        association_id=context["association_id"],
        card_number__isnull=False,
    )
    que = que.select_related("member").order_by("card_number")

    # Process each membership and prepare member data
    for mb in que:
        member = mb.member
        member.membership = mb
        member.last_enrolment = cache[member.id]

        # Calculate enrollment order based on days from year start
        member.order = (member.last_enrolment - start).days

        # Parse and format member legal name if available
        if member.legal_name:
            splitted = member.legal_name.rsplit(" ", 1)
            if len(splitted) == split_two_names:
                member.name, member.surname = splitted
            else:
                member.name = splitted[0]

        # Capitalize name components for display
        member.name = member.name.capitalize()
        member.surname = member.surname.capitalize()

        context["list"].append(member)

    return render(request, "larpmanager/exe/users/enrolment.html", context)


@login_required
def exe_volunteer_registry(request: HttpRequest) -> HttpResponse:
    """Display volunteer registry for organization.

    Args:
        request: HTTP request object

    Returns:
        Rendered volunteer registry template

    """
    # Check user permissions and get association context
    context = check_association_context(request, "exe_volunteer_registry")

    # Fetch volunteer registries with member info, ordered by start date and surname
    context["list"] = (
        VolunteerRegistry.objects.filter(association_id=context["association_id"])
        .select_related("member")
        .order_by("start", "member__surname")
    )

    return render(request, "larpmanager/exe/users/volunteer_registry.html", context)


@login_required
def exe_volunteer_registry_edit(request: HttpRequest, num: int) -> HttpResponse:
    """Edit volunteer registry entry using standard exe form handling."""
    return exe_edit(request, ExeVolunteerRegistryForm, num, "exe_volunteer_registry")


@login_required
def exe_volunteer_registry_print(request: HttpRequest) -> HttpResponse:
    """Generate and return a PDF of the volunteer registry for an association.

    Args:
        request: The HTTP request object containing user and permission data.

    Returns:
        HttpResponse containing the PDF file with volunteer registry data.

    Raises:
        PermissionDenied: If user lacks exe_volunteer_registry permission.
        Association.DoesNotExist: If association not found.

    """
    # Check user permissions and get association context
    context = check_association_context(request, "exe_volunteer_registry")

    # Retrieve the association object for the current context
    context["association"] = Association.objects.get(pk=context["association_id"])

    # Query volunteer registry entries with member data, ordered by start date and surname
    context["list"] = (
        VolunteerRegistry.objects.filter(association=context["association"])
        .select_related("member")
        .order_by("start", "member__surname")
    )

    # Generate current date string for filename
    context["date"] = datetime.today().strftime("%Y-%m-%d")

    # Generate the PDF file using the context data
    fp = print_volunteer_registry(context)

    # Return the PDF as an HTTP response with descriptive filename
    return return_pdf(fp, f"Registro_Volontari_{context['association'].name}_{context['date']}")


@login_required
def exe_vote(request: HttpRequest) -> HttpResponse:
    """Handle voting functionality for executives.

    Displays voting interface with candidates and current vote counts for the current year.
    Shows list of voters who have already participated in the voting process.

    Args:
        request (HttpRequest): HTTP request object containing user session and data

    Returns:
        HttpResponse: Rendered voting interface page with candidates, vote counts, and voter list

    Note:
        Requires 'exe_vote' permission for the associated organization.
        Candidates are configured via 'vote_candidates' association config.

    """
    # Check user permissions and get association context
    context = check_association_context(request, "exe_vote")
    context["year"] = datetime.today().year
    association_id = context["association_id"]

    # Parse candidate IDs from association configuration
    idxs = [el.strip() for el in get_association_config(association_id, "vote_candidates", default_value="").split(",") if el.strip()]

    # Fetch candidate member objects and build candidates dictionary
    context["candidates"] = {}
    for mb in Member.objects.filter(pk__in=idxs):
        context["candidates"][mb.id] = mb

    # Query vote counts grouped by candidate for current year and association
    votes = (
        Vote.objects.filter(year=context["year"], association_id=context["association_id"])
        .values("candidate_id")
        .annotate(total=Count("candidate_id"))
    )

    # Attach vote counts to candidate objects
    for el in votes:
        if el["candidate_id"] not in context["candidates"]:
            continue
        context["candidates"][el["candidate_id"]].votes = el["total"]

    # Get list of members who have already voted this year
    context["voters"] = Member.objects.filter(
        votes_given__year=context["year"],
        votes_given__association_id=context["association_id"],
    ).distinct()

    return render(request, "larpmanager/exe/users/vote.html", context)


@login_required
def exe_badges(request: HttpRequest) -> HttpResponse:
    """Display and manage association badges."""
    # Check user permissions for badge management
    context = check_association_context(request, "exe_badges")

    # Load all badges for the association with member relationships
    context["list"] = Badge.objects.filter(association_id=context["association_id"]).prefetch_related("members")

    return render(request, "larpmanager/exe/users/badges.html", context)


@login_required
def exe_badges_edit(request: HttpRequest, num: int) -> HttpResponse:
    """Delegate to generic edit view for badge editing."""
    return exe_edit(request, ExeBadgeForm, num, "exe_badges")


@login_required
def exe_send_mail(request: HttpRequest) -> HttpResponse:
    """Handle sending mail to association members.

    This view allows association administrators to send bulk emails to members.
    On GET requests, displays the mail sending form. On POST requests with valid
    form data, queues the mail for batch sending.

    Args:
        request: The HTTP request object containing user data and form submission.

    Returns:
        HttpResponse: Rendered template with form or redirect after successful submission.

    """
    # Check if user has permission to send mail for this association
    context = check_association_context(request, "exe_send_mail")

    if request.method == "POST":
        # Process form submission for mail sending
        form = SendMailForm(request.POST)
        if form.is_valid():
            # Queue mail for batch processing
            send_mail_batch(request, association_id=context["association_id"])
            messages.success(request, _("Mail added to queue!"))
            return redirect(request.path_info)
    else:
        # Display empty form for GET requests
        form = SendMailForm()

    # Add form to context and render template
    context["form"] = form
    return render(request, "larpmanager/exe/users/send_mail.html", context)


@login_required
def exe_archive_email(request: HttpRequest) -> HttpResponse:
    """Display archived emails for the organization with pagination and formatting.

    This view shows a paginated list of all emails sent through the system,
    with formatted display of email content and metadata.

    Args:
        request: The HTTP request object containing user session and parameters

    Returns:
        HttpResponse: Rendered template with paginated email archive

    """
    # Check user permissions for accessing email archive
    context = check_association_context(request, "exe_archive_email")
    context["exe"] = True

    # Define table columns for the email archive display
    context.update(
        {
            "fields": [
                ("run", _("Run")),
                ("recipient", _("Recipient")),
                ("subj", _("Subject")),
                ("body", _("Body")),
                ("sent", _("Sent")),
            ],
            # Define formatting callbacks for each field
            "callbacks": {
                "body": format_email_body,
                "sent": lambda el: el.sent.strftime("%d/%m/%Y %H:%M") if el.sent else "",
                "run": lambda el: str(el.run) if el.run else "",
                "recipient": lambda el: str(el.recipient),
                "subj": lambda el: str(el.subj),
            },
        },
    )

    # Return paginated view of Email objects
    return exe_paginate(request, context, Email, "larpmanager/exe/users/archive_mail.html", "exe_read_mail")


@login_required
def exe_read_mail(request: HttpRequest, mail_id: str) -> HttpResponse:
    """Display archived email details for organization executives."""
    # Verify user has email archive access permissions
    context = check_association_context(request, "exe_archive_email")
    context["exe"] = True

    # Retrieve and add email data to context
    context["email"] = get_mail(request, context, mail_id)

    return render(request, "larpmanager/exe/users/read_mail.html", context)


@login_required
def exe_questions(request: HttpRequest) -> HttpResponse:
    """Handle display and management of help questions for organization executives.

    Retrieves open and closed help questions for the organization. When POST method
    is used, moves all questions to open status by combining open and closed lists.

    Args:
        request: The HTTP request object containing user and method information.

    Returns:
        Rendered template response with question lists and context data.

    """
    # Check user permissions for accessing executive questions feature
    context = check_association_context(request, "exe_questions")

    # Retrieve categorized help questions for the organization
    closed_q, open_q = _get_help_questions(context, request)

    # Handle POST request to reopen all closed questions
    if request.method == "POST":
        # Move all closed questions to open list
        open_q.extend(closed_q)
        closed_q = []

    # Sort questions by creation date for display
    # Open questions: oldest first, closed questions: newest first
    context["open"] = sorted(open_q, key=lambda x: x.created)
    context["closed"] = sorted(closed_q, key=lambda x: x.created, reverse=True)

    return render(request, "larpmanager/exe/users/questions.html", context)


@login_required
def exe_questions_answer(request: HttpRequest, member_id: int) -> HttpResponse:
    """Handle question answering for executives.

    This view allows organization executives to answer help questions submitted by members.
    It displays the member's question history and provides a form to submit answers.

    Args:
        request: The HTTP request object containing user session and POST data
        member_id: The id of the Member who submitted the question

    Returns:
        HttpResponse: Rendered question answer form page or redirect to questions list
            after successful form submission

    Raises:
        Member.DoesNotExist: If the member with the given ID doesn't exist

    """
    # Check executive permissions for question management
    context = check_association_context(request, "exe_questions")

    # Retrieve the member and their question history
    context["member_edit"] = get_member(member_id)
    context["list"] = HelpQuestion.objects.filter(
        member=context["member_edit"],
        association_id=context["association_id"],
    ).order_by("-created")

    # Get the most recent question from this member
    last = context["list"].first()

    # Handle form submission for new answers
    if request.method == "POST":
        form = OrgaHelpQuestionForm(request.POST, request.FILES)
        if form.is_valid():
            # Create answer object without saving to database yet
            hp = form.save(commit=False)

            # Associate answer with the same run as the original question if applicable
            if last.run:
                hp.run = last.run

            # Set answer metadata and save to database
            hp.member = context["member_edit"]
            hp.is_user = False
            hp.association_id = context["association_id"]
            hp.save()

            # Notify user of successful submission and redirect
            messages.success(request, _("Answer submitted!"))
            return redirect("exe_questions")
    else:
        # Initialize empty form for GET requests
        form = OrgaHelpQuestionForm()

    # Add form to context for template rendering
    context["form"] = form

    return render(request, "larpmanager/exe/users/questions_answer.html", context)


@login_required
def exe_questions_close(request: HttpRequest, member_id: int) -> HttpResponse:
    """Close a help question for a member."""
    context = check_association_context(request, "exe_questions")

    # Get the member and their most recent help question
    member = Member.objects.get(pk=member_id)
    h = (
        HelpQuestion.objects.filter(member=member, association_id=context["association_id"])
        .order_by("-created")
        .first()
    )

    # Mark the question as closed and save
    h.closed = True
    h.save()

    return redirect("exe_questions")


@login_required
def exe_newsletter(request: HttpRequest):
    """Display newsletter subscription management for association members.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered newsletter management page with subscriber lists by language

    """
    context = check_association_context(request, "exe_newsletter")

    context["lst"] = {}
    for el in (
        Membership.objects.filter(association_id=context["association_id"])
        .select_related("member")
        .values_list("member__email", "member__language", "newsletter")
    ):
        m = el[0]
        language = el[1]
        if language not in context["lst"]:
            context["lst"][language] = {}
        newsletter = el[2]
        if newsletter not in context["lst"][language]:
            context["lst"][language][newsletter] = []
        context["lst"][language][newsletter].append(m)
    return render(request, "larpmanager/exe/users/newsletter.html", context)


@login_required
def exe_newsletter_csv(request: HttpRequest, lang: str) -> HttpResponse:
    """Export newsletter subscriber data as CSV for specific language.

    Exports member information (email, membership number, name, surname) for all
    members of an association who have the specified language preference.

    Args:
        request: HTTP request object containing user authentication and session data
        lang: Language code to filter subscribers (e.g., 'en', 'it', 'fr')

    Returns:
        HttpResponse: CSV file download response with member data, formatted as
                     email, membership_number, name, surname per row

    Raises:
        PermissionDenied: If user lacks exe_newsletter permission for the association

    """
    # Check user permissions for newsletter export functionality
    context = check_association_context(request, "exe_newsletter")

    # Set up CSV response with appropriate headers for file download
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="Newsletter-{lang}.csv"'},
    )
    writer = csv.writer(response)

    # Iterate through all memberships for the current association
    for el in Membership.objects.filter(association_id=context["association_id"]):
        m = el.member

        # Skip members who don't match the requested language
        if m.language != lang:
            continue

        # Build row data starting with member email
        lis = [m.email]

        # Add membership number or empty string if not available
        if el.number:
            lis.append(el.number)
        else:
            lis.append("")

        # Add member's personal information
        lis.append(m.name)
        lis.append(m.surname)

        # Write the complete row to CSV
        writer.writerow(lis)

    return response
