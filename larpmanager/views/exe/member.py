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
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, Count, IntegerField, Value, When
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.payment import unique_invoice_cod
from larpmanager.accounting.registration import update_member_registrations
from larpmanager.cache.config import get_assoc_config
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
from larpmanager.utils.base import check_assoc_permission
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
    """Executive view for managing association memberships.

    Displays membership statistics, fee collection status, and membership
    administration tools for association executives. Shows pending memberships
    with priority sorting and includes upcoming event registrations.

    Args:
        request: The HTTP request object containing user and session data.

    Returns:
        HttpResponse: Rendered template with membership data and statistics.
    """
    # Check user permissions and get association context
    ctx = check_assoc_permission(request, "exe_membership")

    # Get set of member IDs who have paid membership fees for current year
    fees = set(
        AccountingItemMembership.objects.filter(assoc_id=ctx["a_id"], year=datetime.now().year).values_list(
            "member_id", flat=True
        )
    )

    # Build dictionary of upcoming runs (events that haven't ended yet)
    next_runs = dict(
        Run.objects.filter(event__assoc_id=ctx["a_id"], end__gt=datetime.today()).values_list("pk", "search")
    )

    # Get registrations for upcoming runs and group by member
    next_regs_qs = Registration.objects.filter(run__id__in=next_runs.keys()).values_list("run_id", "member_id")

    # Create member_id -> [run_ids] mapping for upcoming registrations
    next_regs = defaultdict(list)
    for run_id, member_id in next_regs_qs:
        next_regs[member_id].append(run_id)

    # Query memberships excluding certain statuses, with priority sorting
    que = (
        Membership.objects.filter(assoc_id=ctx["a_id"])
        .select_related("member")
        .exclude(status__in=[MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED])
        .annotate(
            sort_priority=Case(
                When(status=MembershipStatus.SUBMITTED, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("sort_priority", "-updated")
    )

    # Define fields to extract from membership query
    values = ("member__id", "member__surname", "member__name", "member__email", "card_number", "status")
    ctx["list"] = []
    ctx["sum"] = {}

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
        if el["status"] not in ctx["sum"]:
            ctx["sum"][el["status"]] = 0
        ctx["sum"][el["status"]] += 1

        # Add upcoming run names for members with registrations
        if el["member__id"] in next_regs:
            el["run_names"] = ", ".join(
                [next_runs[run_id] for run_id in next_regs[el["member__id"]] if run_id in next_runs]
            )
        ctx["list"].append(el)

    return render(request, "larpmanager/exe/users/membership.html", ctx)


@login_required
def exe_membership_evaluation(request: HttpRequest, num: int) -> HttpResponse:
    """Executive interface for evaluating membership applications.

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
    ctx = check_assoc_permission(request, "exe_membership")

    # Get member and their membership status
    member = Member.objects.get(pk=num)
    get_user_membership(member, ctx["a_id"])

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
    ctx["member"] = member
    ctx["form"] = form

    # Add document path if document exists
    if member.membership.document:
        ctx["doc_path"] = member.membership.get_document_filepath().lower()

    # Add request path if request exists
    if member.membership.request:
        ctx["req_path"] = member.membership.get_request_filepath().lower()

    # Normalize member name and surname for duplicate checking
    normalized_name = normalize_string(member.name)
    normalized_surname = normalize_string(member.surname)

    # Check for existing members with same normalized name/surname
    ctx["member_exists"] = False
    que = Membership.objects.select_related("member").filter(assoc_id=ctx["a_id"])
    que = que.exclude(status__in=[MembershipStatus.EMPTY, MembershipStatus.JOINED]).exclude(member_id=member.id)

    # Compare normalized names to detect potential duplicates
    for other in que.values_list("member__surname", "member__name"):
        if normalize_string(other[1]) == normalized_name:
            if normalize_string(other[0]) == normalized_surname:
                ctx["member_exists"] = True

    # Add fiscal code validation if feature is enabled
    if "fiscal_code_check" in ctx["features"]:
        ctx.update(calculate_fiscal_code(member))

    return render(request, "larpmanager/exe/users/membership_evaluation.html", ctx)


@login_required
def exe_membership_request(request, num):
    ctx = check_assoc_permission(request, "exe_membership")
    ctx.update(get_member(num))
    return get_membership_request(ctx)


@login_required
def exe_membership_check(request: HttpRequest) -> HttpResponse:
    """Check and report membership status inconsistencies.

    This function analyzes membership data to identify potential issues,
    particularly focusing on fiscal code validation when the feature is enabled.
    It excludes members with EMPTY or JOINED status from the analysis.

    Args:
        request (HttpRequest): The HTTP request object containing user session
            and authentication information.

    Returns:
        HttpResponse: Rendered HTML response containing the membership check
            report with any identified inconsistencies.

    Note:
        Requires 'exe_membership_check' permission. When 'fiscal_code_check'
        feature is enabled, validates fiscal codes for all eligible members.
    """
    # Check user permissions and get association context
    ctx = check_assoc_permission(request, "exe_membership_check")

    # Get member IDs for active memberships (excluding EMPTY and JOINED status)
    member_ids = set(
        Membership.objects.filter(assoc_id=ctx["a_id"])
        .select_related("member")
        .exclude(status__in=[MembershipStatus.EMPTY, MembershipStatus.JOINED])
        .values_list("member_id", flat=True)
    )

    # Process fiscal code validation if feature is enabled
    if "fiscal_code_check" in ctx["features"]:
        ctx["cf"] = []

        # Iterate through each member to validate fiscal codes
        for mb in Member.objects.filter(pk__in=member_ids):
            # Calculate and validate the fiscal code for current member
            check = calculate_fiscal_code(mb)
            if not check:
                continue

            # If fiscal code is incorrect, collect member details for report
            if not check["correct_cf"]:
                check["member"] = str(mb)
                check["member_id"] = mb.id
                check["email"] = mb.email
                # Get membership details for this association
                check["membership"] = get_user_membership(mb, ctx["a_id"])
                ctx["cf"].append(check)

    return render(request, "larpmanager/exe/users/membership_check.html", ctx)


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
    ctx = check_assoc_permission(request, "exe_membership")
    ctx.update(get_member(num))

    # Handle form submission for member profile updates
    if request.method == "POST":
        form = ExeMemberForm(request.POST, request.FILES, instance=ctx["member"], request=request)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated"))
            return redirect(request.path)
    else:
        # Initialize empty form for GET requests
        form = ExeMemberForm(instance=ctx["member"], request=request)
    ctx["form"] = form

    # Get member registrations for current association events
    ctx["regs"] = Registration.objects.filter(
        member=ctx["member"], run__event__assoc=request.assoc["id"]
    ).select_related("run")

    # Add accounting payment items to context
    member_add_accountingitempayment(ctx, request)

    # Add other accounting items to context
    member_add_accountingitemother(ctx, request)

    # Get member discounts for current association
    ctx["discounts"] = AccountingItemDiscount.objects.filter(
        member=ctx["member"], hide=False, assoc_id=request.assoc["id"]
    )

    # Process membership data and document paths
    member = ctx["member"]
    get_user_membership(member, ctx["a_id"])

    # Set document file paths if they exist
    if member.membership.document:
        ctx["doc_path"] = member.membership.get_document_filepath().lower()

    if member.membership.request:
        ctx["req_path"] = member.membership.get_request_filepath().lower()

    # Add fiscal code validation if feature is enabled
    if "fiscal_code_check" in ctx["features"]:
        ctx.update(calculate_fiscal_code(ctx["member"]))

    return render(request, "larpmanager/exe/users/member.html", ctx)


def member_add_accountingitempayment(ctx, request):
    ctx["pays"] = AccountingItemPayment.objects.filter(
        member=ctx["member"], hide=False, assoc_id=request.assoc["id"]
    ).select_related("reg")
    for el in ctx["pays"]:
        if el.pay == PaymentChoices.TOKEN:
            el.typ = ctx.get("token_name", _("Credits"))
        elif el.pay == PaymentChoices.CREDIT:
            el.typ = ctx.get("credit_name", _("Credits"))
        else:
            el.typ = el.get_pay_display()


def member_add_accountingitemother(ctx, request):
    ctx["others"] = AccountingItemOther.objects.filter(
        member=ctx["member"], hide=False, assoc_id=request.assoc["id"]
    ).select_related("run")
    for el in ctx["others"]:
        if el.oth == OtherChoices.TOKEN:
            el.typ = ctx.get("token_name", _("Credits"))
        elif el.oth == OtherChoices.CREDIT:
            el.typ = ctx.get("credit_name", _("Credits"))
        else:
            el.typ = el.get_oth_display()


@login_required
def exe_membership_status(request: HttpRequest, num: str) -> HttpResponse:
    """Edit membership status and details for a specific member.

    This function handles both GET and POST requests for editing a member's
    membership information within an organization. It validates permissions,
    retrieves the member and membership data, processes form submissions,
    and renders the appropriate response.

    Args:
        request: Django HTTP request object containing user session and form data
        num: Member number identifier used to lookup the specific member

    Returns:
        HttpResponse: Rendered membership editing form template for GET requests,
                     or redirect response after successful form submission for POST requests

    Raises:
        Http404: If the member or membership record is not found
        PermissionDenied: If user lacks required association permissions
    """
    # Check user permissions and get base context with association data
    ctx = check_assoc_permission(request, "exe_membership")

    # Retrieve member data and add to context
    ctx.update(get_member(num))

    # Get the membership record for this member in the current association
    ctx["membership"] = get_object_or_404(Membership, member_id=ctx["member"].id, assoc_id=request.assoc["id"])

    if request.method == "POST":
        # Process form submission with uploaded files and current membership instance
        form = ExeMembershipForm(request.POST, request.FILES, instance=ctx["membership"], request=request)

        # Validate and save form data, then redirect to prevent duplicate submissions
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated"))
            return redirect(request.path)
    else:
        # Initialize form with existing membership data for GET requests
        form = ExeMembershipForm(instance=ctx["membership"], request=request)

    # Add form to context and set additional template variables
    ctx["form"] = form
    ctx["num"] = num

    # Set dynamic page title combining member name and section title
    ctx["form"].page_title = str(ctx["member"]) + " - " + _("Membership")

    return render(request, "larpmanager/exe/edit.html", ctx)


@login_required
def exe_membership_registry(request: HttpRequest) -> HttpResponse:
    """Generate membership registry with card numbers for association executives.

    Creates a formatted list of association members who have card numbers,
    processes their names for proper capitalization, and renders them in
    a registry template for executive viewing.

    Args:
        request (HttpRequest): The HTTP request object containing user session
            and association context.

    Returns:
        HttpResponse: Rendered registry.html template containing the formatted
            member list with card numbers and processed names.

    Note:
        Only includes members with non-null card numbers, ordered by card number.
        Names are split and capitalized for consistent formatting.
    """
    # Check user permissions and get association context
    ctx = check_assoc_permission(request, "exe_membership_registry")
    split_two_names = 2

    # Initialize empty member list for template context
    ctx["list"] = []

    # Query memberships with card numbers for current association
    que = Membership.objects.filter(assoc_id=ctx["a_id"], card_number__isnull=False)

    # Process each membership and associated member data
    for mb in que.select_related("member").order_by("card_number"):
        member = mb.member
        member.membership = mb

        # Split legal name into name and surname components
        if member.legal_name:
            splitted = member.legal_name.rsplit(" ", 1)
            if len(splitted) == split_two_names:
                member.name, member.surname = splitted
            else:
                member.name = splitted[0]

        # Apply proper capitalization to name components
        member.name = member.name.capitalize()
        member.surname = member.surname.capitalize()

        # Add processed member to context list
        ctx["list"].append(member)

    return render(request, "larpmanager/exe/users/registry.html", ctx)


@login_required
def exe_membership_fee(request: HttpRequest) -> HttpResponse:
    """
    Process membership fee payments for executives.

    This view handles the creation and confirmation of membership fee payments
    for organization members. It displays a form for payment details and
    processes the payment upon form submission.

    Args:
        request (HttpRequest): The HTTP request object containing form data
            and user session information.

    Returns:
        HttpResponse: Either renders the membership fee form page or
            redirects to the membership list after successful payment processing.

    Raises:
        PermissionDenied: If user lacks exe_membership permission.
    """
    # Check user permissions for membership management
    ctx = check_assoc_permission(request, "exe_membership")

    if request.method == "POST":
        # Process form submission with uploaded files
        form = ExeMembershipFeeForm(request.POST, request.FILES, ctx=ctx)

        if form.is_valid():
            # Extract validated form data
            member = form.cleaned_data["member"]
            assoc_id = ctx["a_id"]

            # Get membership fee amount from association configuration
            fee = get_assoc_config(assoc_id, "membership_fee", "0")

            # Create payment invoice record with confirmed status
            payment = PaymentInvoice.objects.create(
                member=member,
                typ=PaymentType.MEMBERSHIP,
                invoice=form.cleaned_data["invoice"],
                method_id=form.cleaned_data["method"],
                mc_gross=fee,
                causal=_("Membership fee of") + f" {member}",
                assoc_id=assoc_id,
                cod=unique_invoice_cod(),
            )

            # Mark payment as confirmed and save changes
            payment.status = PaymentStatus.CONFIRMED
            payment.save()

            # Show success message and redirect to membership list
            messages.success(request, _("Operation completed") + "!")
            return redirect("exe_membership")
    else:
        # Initialize empty form for GET requests
        form = ExeMembershipFeeForm(ctx=ctx)

    # Add form to template context
    ctx["form"] = form

    return render(request, "larpmanager/exe/edit.html", ctx)


@login_required
def exe_membership_document(request: HttpRequest) -> HttpResponse:
    """Handle membership document upload and approval process.

    This function processes both GET and POST requests for uploading membership
    documents. On POST, it validates the form data and updates the membership
    with the provided document, request details, card number, and date, then
    sets the status to ACCEPTED.

    Args:
        request: Django HTTP request object containing form data and files

    Returns:
        HttpResponse: Rendered form template for document upload on GET requests,
                     or redirect to membership list on successful POST

    Raises:
        DoesNotExist: If the membership for the given association and member
                     does not exist
    """
    # Check user permissions for membership management
    ctx = check_assoc_permission(request, "exe_membership")

    if request.method == "POST":
        # Create form instance with submitted data and files
        form = ExeMembershipDocumentForm(request.POST, request.FILES, ctx=ctx)

        if form.is_valid():
            # Extract validated form data
            member = form.cleaned_data["member"]

            # Retrieve the membership record for this association and member
            membership = Membership.objects.get(assoc_id=ctx["a_id"], member=member)

            # Update membership with form data
            membership.document = form.cleaned_data["document"]
            membership.request = form.cleaned_data["request"]
            membership.card_number = form.cleaned_data["card_number"]
            membership.date = form.cleaned_data["date"]

            # Set membership status to accepted and save changes
            membership.status = MembershipStatus.ACCEPTED
            membership.save()

            # Display success message and redirect to membership list
            messages.success(request, _("Operation completed") + "!")
            return redirect("exe_membership")
    else:
        # Create empty form for GET requests
        form = ExeMembershipDocumentForm(ctx=ctx)

    # Add form to template context
    ctx["form"] = form

    return render(request, "larpmanager/exe/edit.html", ctx)


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
    ctx = check_assoc_permission(request, "exe_enrolment")
    split_two_names = 2

    # Set current year and calculate year start date
    ctx["year"] = datetime.today().year
    start = datetime(ctx["year"], 1, 1)

    # Build cache of member enrollment dates from accounting items
    cache = {}
    for el in AccountingItemMembership.objects.filter(assoc_id=ctx["a_id"], year=ctx["year"]).values_list(
        "member_id", "created"
    ):
        cache[el[0]] = el[1]

    # Query memberships with card numbers for enrolled members
    ctx["list"] = []
    que = Membership.objects.filter(member_id__in=cache.keys(), assoc_id=ctx["a_id"], card_number__isnull=False)
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

        ctx["list"].append(member)

    return render(request, "larpmanager/exe/users/enrolment.html", ctx)


@login_required
def exe_volunteer_registry(request):
    ctx = check_assoc_permission(request, "exe_volunteer_registry")
    ctx["list"] = (
        VolunteerRegistry.objects.filter(assoc_id=ctx["a_id"])
        .select_related("member")
        .order_by("start", "member__surname")
    )
    return render(request, "larpmanager/exe/users/volunteer_registry.html", ctx)


@login_required
def exe_volunteer_registry_edit(request, num):
    return exe_edit(request, ExeVolunteerRegistryForm, num, "exe_volunteer_registry")


@login_required
def exe_volunteer_registry_print(request: HttpRequest) -> HttpResponse:
    """Generate and return a PDF of the volunteer registry for an association.

    This function creates a printable PDF document containing all volunteer
    registry entries for the current association, ordered by start date and
    member surname.

    Args:
        request: The HTTP request object containing user and association context.

    Returns:
        HttpResponse: PDF file response with the volunteer registry report.

    Raises:
        PermissionDenied: If user lacks 'exe_volunteer_registry' permission.
        Association.DoesNotExist: If association ID is invalid.
    """
    # Check user permissions and get association context
    ctx = check_assoc_permission(request, "exe_volunteer_registry")

    # Retrieve the association object for the current context
    ctx["assoc"] = Association.objects.get(pk=ctx["a_id"])

    # Query volunteer registry entries with member data preloaded
    # Ordered by start date first, then by member surname
    ctx["list"] = (
        VolunteerRegistry.objects.filter(assoc=ctx["assoc"])
        .select_related("member")
        .order_by("start", "member__surname")
    )

    # Generate current date string for filename and document metadata
    ctx["date"] = datetime.today().strftime("%Y-%m-%d")

    # Generate the PDF file using the volunteer registry template
    fp = print_volunteer_registry(ctx)

    # Return the PDF as an HTTP response with descriptive filename
    return return_pdf(fp, f"Registro_Volontari_{ctx['assoc'].name}_{ctx['date']}")


@login_required
def exe_vote(request: HttpRequest) -> HttpResponse:
    """
    Handle voting functionality for executives.

    Displays the voting interface with candidate information and voting results
    for the current year. Shows vote counts per candidate and list of voters.

    Args:
        request: The HTTP request object containing user and session information

    Returns:
        HttpResponse: Rendered voting interface page with candidate data and results

    Note:
        Requires 'exe_vote' permission. Candidates are configured via association
        settings under 'vote_candidates' key.
    """
    # Check permissions and get association context
    ctx = check_assoc_permission(request, "exe_vote")
    ctx["year"] = datetime.today().year
    assoc_id = ctx["a_id"]

    # Parse candidate IDs from association configuration
    idxs = []
    for el in get_assoc_config(assoc_id, "vote_candidates", "").split(","):
        if el.strip():
            idxs.append(el.strip())

    # Fetch candidate member objects and create candidates dictionary
    ctx["candidates"] = {}
    for mb in Member.objects.filter(pk__in=idxs):
        ctx["candidates"][mb.id] = mb

    # Aggregate vote counts per candidate for current year
    votes = (
        Vote.objects.filter(year=ctx["year"], assoc_id=ctx["a_id"])
        .values("candidate_id")
        .annotate(total=Count("candidate_id"))
    )

    # Attach vote counts to candidate objects
    for el in votes:
        if el["candidate_id"] not in ctx["candidates"]:
            continue
        ctx["candidates"][el["candidate_id"]].votes = el["total"]

    # Get list of members who have voted this year
    ctx["voters"] = Member.objects.filter(votes_given__year=ctx["year"], votes_given__assoc_id=ctx["a_id"]).distinct()

    return render(request, "larpmanager/exe/users/vote.html", ctx)


@login_required
def exe_badges(request):
    ctx = check_assoc_permission(request, "exe_badges")
    ctx["list"] = Badge.objects.filter(assoc_id=request.assoc["id"]).prefetch_related("members")
    return render(request, "larpmanager/exe/users/badges.html", ctx)


@login_required
def exe_badges_edit(request, num):
    return exe_edit(request, ExeBadgeForm, num, "exe_badges")


@login_required
def exe_send_mail(request: HttpRequest) -> HttpResponse:
    """Handle sending bulk emails to association members.

    This view allows association executives to send batch emails to members.
    On GET requests, displays the email form. On POST requests, validates
    the form and queues the email for batch processing.

    Args:
        request: The HTTP request object containing user and association data.

    Returns:
        HttpResponse: Rendered template with form context or redirect response.
    """
    # Check if user has permission to send emails for this association
    ctx = check_assoc_permission(request, "exe_send_mail")

    if request.method == "POST":
        # Process form submission for sending emails
        form = SendMailForm(request.POST)

        if form.is_valid():
            # Queue the email batch for processing
            send_mail_batch(request, assoc_id=request.assoc["id"])

            # Show success message and redirect to prevent re-submission
            messages.success(request, _("Mail added to queue!"))
            return redirect(request.path_info)
    else:
        # Display empty form for GET requests
        form = SendMailForm()

    # Add form to template context and render the page
    ctx["form"] = form
    return render(request, "larpmanager/exe/users/send_mail.html", ctx)


@login_required
def exe_archive_email(request: HttpRequest) -> dict:
    """Archive email view for organization executives.

    Displays a paginated list of archived emails with formatted fields
    and custom callbacks for data presentation.

    Args:
        request: HTTP request object containing user and session data

    Returns:
        dict: Context dictionary containing pagination data and field definitions
    """
    # Check user permissions for email archive access
    ctx = check_assoc_permission(request, "exe_archive_email")
    ctx["exe"] = True

    # Define table field configuration with display names
    ctx.update(
        {
            "fields": [
                ("run", _("Run")),
                ("recipient", _("Recipient")),
                ("subj", _("Subject")),
                ("body", _("Body")),
                ("sent", _("Sent")),
            ],
            # Custom formatting callbacks for data display
            "callbacks": {
                "body": format_email_body,
                "sent": lambda el: el.sent.strftime("%d/%m/%Y %H:%M") if el.sent else "",
                "run": lambda el: str(el.run) if el.run else "",
            },
        }
    )

    # Return paginated email list with configured template
    return exe_paginate(request, ctx, Email, "larpmanager/exe/users/archive_mail.html", "exe_read_mail")


@login_required
def exe_read_mail(request, nm):
    ctx = check_assoc_permission(request, "exe_archive_email")
    ctx["exe"] = True
    ctx["email"] = get_mail(request, ctx, nm)
    return render(request, "larpmanager/exe/users/read_mail.html", ctx)


@login_required
def exe_questions(request: HttpRequest) -> HttpResponse:
    """Handle display and management of help questions for organization executives.

    This view allows organization executives to view and manage help questions,
    with the ability to show/hide closed questions via POST request.

    Args:
        request: The HTTP request object containing user authentication and method data

    Returns:
        HttpResponse: Rendered template with open and closed questions context
    """
    # Check user permissions for accessing executive questions functionality
    ctx = check_assoc_permission(request, "exe_questions")

    # Retrieve help questions categorized as closed and open
    closed_q, open_q = _get_help_questions(ctx, request)

    # Handle POST request to show all questions (merge closed into open)
    if request.method == "POST":
        open_q.extend(closed_q)
        closed_q = []

    # Sort open questions by creation date (oldest first)
    # Sort closed questions by creation date (newest first)
    ctx["open"] = sorted(open_q, key=lambda x: x.created)
    ctx["closed"] = sorted(closed_q, key=lambda x: x.created, reverse=True)

    return render(request, "larpmanager/exe/users/questions.html", ctx)


@login_required
def exe_questions_answer(request: HttpRequest, r: int) -> HttpResponse:
    """
    Handle question answering for executives.

    This view allows organization executives to answer help questions submitted by members.
    It displays the member's question history and provides a form to submit answers.

    Args:
        request: The HTTP request object containing user session and POST data
        r: The primary key (ID) of the Member who submitted the question

    Returns:
        HttpResponse: Rendered question answer form page or redirect to questions list
            after successful form submission

    Raises:
        Member.DoesNotExist: If the member with the given ID doesn't exist
    """
    # Check executive permissions for question management
    ctx = check_assoc_permission(request, "exe_questions")

    # Retrieve the member and their question history
    member = Member.objects.get(pk=r)
    ctx["member"] = member
    ctx["list"] = HelpQuestion.objects.filter(member=member, assoc_id=ctx["a_id"]).order_by("-created")

    # Get the most recent question from this member
    last = ctx["list"].first()

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
            hp.member = member
            hp.is_user = False
            hp.assoc_id = ctx["a_id"]
            hp.save()

            # Notify user of successful submission and redirect
            messages.success(request, _("Answer submitted!"))
            return redirect("exe_questions")
    else:
        # Initialize empty form for GET requests
        form = OrgaHelpQuestionForm()

    # Add form to context for template rendering
    ctx["form"] = form

    return render(request, "larpmanager/exe/users/questions_answer.html", ctx)


@login_required
def exe_questions_close(request, r):
    ctx = check_assoc_permission(request, "exe_questions")

    member = Member.objects.get(pk=r)
    h = HelpQuestion.objects.filter(member=member, assoc_id=ctx["a_id"]).order_by("-created").first()
    h.closed = True
    h.save()
    return redirect("exe_questions")


@login_required
def exe_newsletter(request: HttpRequest) -> HttpResponse:
    """Display newsletter subscription management for association members.

    This view provides a comprehensive interface for managing newsletter subscriptions
    across different languages within an association. It organizes members by their
    preferred language and newsletter subscription status.

    Args:
        request (HttpRequest): The HTTP request object containing user session
            and authentication information.

    Returns:
        HttpResponse: Rendered newsletter management page containing subscriber
            lists organized by language and subscription status.

    Note:
        Requires 'exe_newsletter' permission for the current association.
    """
    # Check user permissions for newsletter management
    ctx = check_assoc_permission(request, "exe_newsletter")

    # Initialize nested dictionary to organize subscribers by language and status
    ctx["lst"] = {}

    # Query memberships with related member data for current association
    for el in (
        Membership.objects.filter(assoc_id=ctx["a_id"])
        .select_related("member")
        .values_list("member__email", "member__language", "newsletter")
    ):
        # Extract member data from query result tuple
        m = el[0]  # member email
        language = el[1]  # member preferred language

        # Initialize language group if not exists
        if language not in ctx["lst"]:
            ctx["lst"][language] = {}

        # Extract newsletter subscription status
        newsletter = el[2]

        # Initialize newsletter status group if not exists
        if newsletter not in ctx["lst"][language]:
            ctx["lst"][language][newsletter] = []

        # Add member email to appropriate language/newsletter group
        ctx["lst"][language][newsletter].append(m)

    return render(request, "larpmanager/exe/users/newsletter.html", ctx)


@login_required
def exe_newsletter_csv(request: HttpRequest, lang: str) -> HttpResponse:
    """Export newsletter subscriber data as CSV for specific language.

    Exports member data filtered by language to a CSV file containing
    email, membership number, name, and surname.

    Args:
        request: HTTP request object containing user authentication
        lang: Language code to filter subscribers (e.g., 'en', 'it')

    Returns:
        HttpResponse: CSV file download response with member data

    Raises:
        PermissionDenied: If user lacks exe_newsletter permission
    """
    # Check user permissions for newsletter export functionality
    ctx = check_assoc_permission(request, "exe_newsletter")

    # Setup CSV response with appropriate headers and filename
    response = HttpResponse(
        content_type="text/csv", headers={"Content-Disposition": f'attachment; filename="Newsletter-{lang}.csv"'}
    )
    writer = csv.writer(response)

    # Iterate through all memberships for the current association
    for el in Membership.objects.filter(assoc_id=ctx["a_id"]):
        m = el.member

        # Skip members who don't match the requested language
        if m.language != lang:
            continue

        # Build row data starting with email
        lis = [m.email]

        # Add membership number or empty string if not available
        if el.number:
            lis.append(el.number)
        else:
            lis.append("")

        # Add member name and surname to complete the row
        lis.append(m.name)
        lis.append(m.surname)

        # Write the row to CSV output
        writer.writerow(lis)

    return response
