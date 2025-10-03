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
from django.http import HttpResponse
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
def exe_membership(request):
    """Executive view for managing association memberships.

    Displays membership statistics, fee collection status, and membership
    administration tools for association executives.
    """
    ctx = check_assoc_permission(request, "exe_membership")

    fees = set(
        AccountingItemMembership.objects.filter(assoc_id=ctx["a_id"], year=datetime.now().year).values_list(
            "member_id", flat=True
        )
    )

    next_runs = dict(
        Run.objects.filter(event__assoc_id=ctx["a_id"], end__gt=datetime.today()).values_list("pk", "search")
    )

    next_regs_qs = Registration.objects.filter(run__id__in=next_runs.keys()).values_list("run_id", "member_id")

    next_regs = defaultdict(list)
    for run_id, member_id in next_regs_qs:
        next_regs[member_id].append(run_id)

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
    values = ("member__id", "member__surname", "member__name", "member__email", "card_number", "status")
    ctx["list"] = []
    ctx["sum"] = {}
    for el in que.values(*values):
        status = el["status"]
        if status == MembershipStatus.ACCEPTED and el["member__id"] in fees:
            el["status"] = "p"
            el["status_display"] = _("Payed")
        else:
            el["status_display"] = MembershipStatus(el["status"]).label

        if el["status"] not in ctx["sum"]:
            ctx["sum"][el["status"]] = 0
        ctx["sum"][el["status"]] += 1

        if el["member__id"] in next_regs:
            el["run_names"] = ", ".join(
                [next_runs[run_id] for run_id in next_regs[el["member__id"]] if run_id in next_runs]
            )
        ctx["list"].append(el)

    return render(request, "larpmanager/exe/users/membership.html", ctx)


@login_required
def exe_membership_evaluation(request, num):
    """Executive interface for evaluating membership applications.

    Handles membership approval/rejection processes and status updates,
    including notifications, duplicate checking, and registration updates
    for approved members.
    """
    ctx = check_assoc_permission(request, "exe_membership")

    member = Member.objects.get(pk=num)
    get_user_membership(member, ctx["a_id"])

    if request.method == "POST":
        form = MembershipResponseForm(request.POST)
        if form.is_valid():
            resp = form.cleaned_data["response"]
            if form.cleaned_data["is_approved"]:
                member.membership.status = MembershipStatus.ACCEPTED
                member.membership.save()
                notify_membership_approved(member, resp)
                update_member_registrations(member)
                messages.success(request, _("Member approved!"))
            else:
                member.membership.status = MembershipStatus.EMPTY
                member.membership.save()
                notify_membership_reject(member, resp)
                messages.success(request, _("Member refused!"))
            return redirect("exe_membership")
    else:
        form = MembershipResponseForm()

    ctx["member"] = member
    ctx["form"] = form

    if member.membership.document:
        ctx["doc_path"] = member.membership.get_document_filepath().lower()

    if member.membership.request:
        ctx["req_path"] = member.membership.get_request_filepath().lower()

    normalized_name = normalize_string(member.name)
    normalized_surname = normalize_string(member.surname)

    ctx["member_exists"] = False
    que = Membership.objects.select_related("member").filter(assoc_id=ctx["a_id"])
    que = que.exclude(status__in=[MembershipStatus.EMPTY, MembershipStatus.JOINED]).exclude(member_id=member.id)
    for other in que.values_list("member__surname", "member__name"):
        if normalize_string(other[1]) == normalized_name:
            if normalize_string(other[0]) == normalized_surname:
                ctx["member_exists"] = True

    if "fiscal_code_check" in ctx["features"]:
        ctx.update(calculate_fiscal_code(member))

    return render(request, "larpmanager/exe/users/membership_evaluation.html", ctx)


@login_required
def exe_membership_request(request, num):
    ctx = check_assoc_permission(request, "exe_membership")
    ctx.update(get_member(num))
    return get_membership_request(ctx)


@login_required
def exe_membership_check(request):
    """Check and report membership status inconsistencies.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered membership check report
    """
    ctx = check_assoc_permission(request, "exe_membership_check")

    member_ids = set(
        Membership.objects.filter(assoc_id=ctx["a_id"])
        .select_related("member")
        .exclude(status__in=[MembershipStatus.EMPTY, MembershipStatus.JOINED])
        .values_list("member_id", flat=True)
    )

    if "fiscal_code_check" in ctx["features"]:
        ctx["cf"] = []
        for mb in Member.objects.filter(pk__in=member_ids):
            check = calculate_fiscal_code(mb)
            if not check:
                continue

            if not check["correct_cf"]:
                check["member"] = str(mb)
                check["member_id"] = mb.id
                check["email"] = mb.email
                check["membership"] = get_user_membership(mb, ctx["a_id"])
                ctx["cf"].append(check)

    return render(request, "larpmanager/exe/users/membership_check.html", ctx)


@login_required
def exe_member(request, num):
    """Display and edit member profile with accounting and membership data.

    Args:
        request: HTTP request object
        num: Member ID to edit

    Returns:
        Rendered member edit template with forms and member data
    """
    ctx = check_assoc_permission(request, "exe_membership")
    ctx.update(get_member(num))

    if request.method == "POST":
        form = ExeMemberForm(request.POST, request.FILES, instance=ctx["member"], request=request)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated"))
            return redirect(request.path)
    else:
        form = ExeMemberForm(instance=ctx["member"], request=request)
    ctx["form"] = form

    ctx["regs"] = Registration.objects.filter(
        member=ctx["member"], run__event__assoc=request.assoc["id"]
    ).select_related("run")

    member_add_accountingitempayment(ctx, request)

    member_add_accountingitemother(ctx, request)

    ctx["discounts"] = AccountingItemDiscount.objects.filter(
        member=ctx["member"], hide=False, assoc_id=request.assoc["id"]
    )

    member = ctx["member"]
    get_user_membership(member, ctx["a_id"])

    if member.membership.document:
        ctx["doc_path"] = member.membership.get_document_filepath().lower()

    if member.membership.request:
        ctx["req_path"] = member.membership.get_request_filepath().lower()

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
def exe_membership_status(request, num):
    """Edit membership status and details for a specific member.

    Args:
        request: Django HTTP request object
        num: Member number identifier

    Returns:
        Rendered membership editing form or redirect after successful update
    """
    ctx = check_assoc_permission(request, "exe_membership")
    ctx.update(get_member(num))
    ctx["membership"] = get_object_or_404(Membership, member_id=ctx["member"].id, assoc_id=request.assoc["id"])

    if request.method == "POST":
        form = ExeMembershipForm(request.POST, request.FILES, instance=ctx["membership"], request=request)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated"))
            return redirect(request.path)
    else:
        form = ExeMembershipForm(instance=ctx["membership"], request=request)
    ctx["form"] = form

    ctx["num"] = num

    ctx["form"].page_title = str(ctx["member"]) + " - " + _("Membership")

    return render(request, "larpmanager/exe/edit.html", ctx)


@login_required
def exe_membership_registry(request):
    """Generate membership registry with card numbers for association executives.

    Args:
        request: HTTP request object

    Returns:
        Rendered registry.html template with formatted member list
    """
    ctx = check_assoc_permission(request, "exe_membership_registry")
    split_two_names = 2

    ctx["list"] = []
    que = Membership.objects.filter(assoc_id=ctx["a_id"], card_number__isnull=False)
    for mb in que.select_related("member").order_by("card_number"):
        member = mb.member
        member.membership = mb

        if member.legal_name:
            splitted = member.legal_name.rsplit(" ", 1)
            if len(splitted) == split_two_names:
                member.name, member.surname = splitted
            else:
                member.name = splitted[0]

        member.name = member.name.capitalize()
        member.surname = member.surname.capitalize()

        ctx["list"].append(member)

    return render(request, "larpmanager/exe/users/registry.html", ctx)


@login_required
def exe_membership_fee(request):
    """
    Process membership fee payments for executives.

    Args:
        request: HTTP request object with form data

    Returns:
        HttpResponse: Form page or redirect after successful processing
    """
    ctx = check_assoc_permission(request, "exe_membership")

    if request.method == "POST":
        form = ExeMembershipFeeForm(request.POST, request.FILES, ctx=ctx)
        if form.is_valid():
            member = form.cleaned_data["member"]
            assoc_id = ctx["a_id"]
            fee = get_assoc_config(assoc_id, "membership_fee", "0")
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
            payment.status = PaymentStatus.CONFIRMED
            payment.save()
            messages.success(request, _("Operation completed") + "!")
            return redirect("exe_membership")
    else:
        form = ExeMembershipFeeForm(ctx=ctx)
    ctx["form"] = form

    return render(request, "larpmanager/exe/edit.html", ctx)


@login_required
def exe_membership_document(request):
    """Handle membership document upload and approval process.

    Args:
        request: Django HTTP request object

    Returns:
        Rendered form for document upload or redirect to membership list
    """
    ctx = check_assoc_permission(request, "exe_membership")

    if request.method == "POST":
        form = ExeMembershipDocumentForm(request.POST, request.FILES, ctx=ctx)
        if form.is_valid():
            member = form.cleaned_data["member"]
            membership = Membership.objects.get(assoc_id=ctx["a_id"], member=member)
            membership.document = form.cleaned_data["document"]
            membership.request = form.cleaned_data["request"]
            membership.card_number = form.cleaned_data["card_number"]
            membership.date = form.cleaned_data["date"]
            membership.status = MembershipStatus.ACCEPTED
            membership.save()
            messages.success(request, _("Operation completed") + "!")
            return redirect("exe_membership")
    else:
        form = ExeMembershipDocumentForm(ctx=ctx)
    ctx["form"] = form

    return render(request, "larpmanager/exe/edit.html", ctx)


@login_required
def exe_enrolment(request):
    """Display yearly enrollment list with membership card numbers.

    Args:
        request: HTTP request object

    Returns:
        Rendered template with enrolled members list for current year
    """
    ctx = check_assoc_permission(request, "exe_enrolment")
    split_two_names = 2

    ctx["year"] = datetime.today().year
    start = datetime(ctx["year"], 1, 1)
    cache = {}
    for el in AccountingItemMembership.objects.filter(assoc_id=ctx["a_id"], year=ctx["year"]).values_list(
        "member_id", "created"
    ):
        cache[el[0]] = el[1]

    ctx["list"] = []
    que = Membership.objects.filter(member_id__in=cache.keys(), assoc_id=ctx["a_id"], card_number__isnull=False)
    que = que.select_related("member").order_by("card_number")
    for mb in que:
        member = mb.member
        member.membership = mb
        member.last_enrolment = cache[member.id]
        member.order = (member.last_enrolment - start).days

        if member.legal_name:
            splitted = member.legal_name.rsplit(" ", 1)
            if len(splitted) == split_two_names:
                member.name, member.surname = splitted
            else:
                member.name = splitted[0]

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
def exe_volunteer_registry_print(request):
    ctx = check_assoc_permission(request, "exe_volunteer_registry")
    ctx["assoc"] = Association.objects.get(pk=ctx["a_id"])
    ctx["list"] = (
        VolunteerRegistry.objects.filter(assoc=ctx["assoc"])
        .select_related("member")
        .order_by("start", "member__surname")
    )
    ctx["date"] = datetime.today().strftime("%Y-%m-%d")
    fp = print_volunteer_registry(ctx)
    return return_pdf(fp, f"Registro_Volontari_{ctx['assoc'].name}_{ctx['date']}")


@login_required
def exe_vote(request):
    """
    Handle voting functionality for executives.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Voting interface or results page
    """
    ctx = check_assoc_permission(request, "exe_vote")
    ctx["year"] = datetime.today().year
    assoc_id = ctx["a_id"]

    idxs = []
    for el in get_assoc_config(assoc_id, "vote_candidates", "").split(","):
        if el.strip():
            idxs.append(el.strip())

    ctx["candidates"] = {}
    for mb in Member.objects.filter(pk__in=idxs):
        ctx["candidates"][mb.id] = mb

    votes = (
        Vote.objects.filter(year=ctx["year"], assoc_id=ctx["a_id"])
        .values("candidate_id")
        .annotate(total=Count("candidate_id"))
    )
    for el in votes:
        if el["candidate_id"] not in ctx["candidates"]:
            continue
        ctx["candidates"][el["candidate_id"]].votes = el["total"]

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
def exe_send_mail(request):
    ctx = check_assoc_permission(request, "exe_send_mail")
    if request.method == "POST":
        form = SendMailForm(request.POST)
        if form.is_valid():
            send_mail_batch(request, assoc_id=request.assoc["id"])
            messages.success(request, _("Mail added to queue!"))
            return redirect(request.path_info)
    else:
        form = SendMailForm()
    ctx["form"] = form
    return render(request, "larpmanager/exe/users/send_mail.html", ctx)


@login_required
def exe_archive_email(request):
    ctx = check_assoc_permission(request, "exe_archive_email")
    ctx["exe"] = True
    ctx.update(
        {
            "fields": [
                ("run", _("Run")),
                ("recipient", _("Recipient")),
                ("subj", _("Subject")),
                ("body", _("Body")),
                ("sent", _("Sent")),
            ],
            "callbacks": {
                "body": format_email_body,
                "sent": lambda el: el.sent.strftime("%d/%m/%Y %H:%M") if el.sent else "",
                "run": lambda el: str(el.run) if el.run else "",
            },
        }
    )
    return exe_paginate(request, ctx, Email, "larpmanager/exe/users/archive_mail.html", "exe_read_mail")


@login_required
def exe_read_mail(request, nm):
    ctx = check_assoc_permission(request, "exe_archive_email")
    ctx["exe"] = True
    ctx["email"] = get_mail(request, ctx, nm)
    return render(request, "larpmanager/exe/users/read_mail.html", ctx)


@login_required
def exe_questions(request):
    ctx = check_assoc_permission(request, "exe_questions")

    closed_q, open_q = _get_help_questions(ctx, request)

    if request.method == "POST":
        open_q.extend(closed_q)
        closed_q = []

    ctx["open"] = sorted(open_q, key=lambda x: x.created)
    ctx["closed"] = sorted(closed_q, key=lambda x: x.created, reverse=True)

    return render(request, "larpmanager/exe/users/questions.html", ctx)


@login_required
def exe_questions_answer(request, r):
    """
    Handle question answering for executives.

    Args:
        request: HTTP request object
        r: Member ID for question answering

    Returns:
        HttpResponse: Question answer form or redirect after submission
    """
    ctx = check_assoc_permission(request, "exe_questions")

    # Get last question by that user
    member = Member.objects.get(pk=r)
    ctx["member"] = member
    ctx["list"] = HelpQuestion.objects.filter(member=member, assoc_id=ctx["a_id"]).order_by("-created")

    last = ctx["list"].first()

    if request.method == "POST":
        form = OrgaHelpQuestionForm(request.POST, request.FILES)
        if form.is_valid():
            hp = form.save(commit=False)
            if last.run:
                hp.run = last.run
            hp.member = member
            hp.is_user = False
            hp.assoc_id = ctx["a_id"]
            hp.save()
            messages.success(request, _("Answer submitted!"))
            return redirect("exe_questions")
    else:
        form = OrgaHelpQuestionForm()

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
def exe_newsletter(request):
    """Display newsletter subscription management for association members.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered newsletter management page with subscriber lists by language
    """
    ctx = check_assoc_permission(request, "exe_newsletter")

    ctx["lst"] = {}
    for el in (
        Membership.objects.filter(assoc_id=ctx["a_id"])
        .select_related("member")
        .values_list("member__email", "member__language", "newsletter")
    ):
        m = el[0]
        language = el[1]
        if language not in ctx["lst"]:
            ctx["lst"][language] = {}
        newsletter = el[2]
        if newsletter not in ctx["lst"][language]:
            ctx["lst"][language][newsletter] = []
        ctx["lst"][language][newsletter].append(m)
    return render(request, "larpmanager/exe/users/newsletter.html", ctx)


@login_required
def exe_newsletter_csv(request, lang):
    """Export newsletter subscriber data as CSV for specific language.

    Args:
        request: HTTP request object
        lang: Language code to filter subscribers

    Returns:
        CSV file response with member email, number, name, surname
    """
    ctx = check_assoc_permission(request, "exe_newsletter")
    response = HttpResponse(
        content_type="text/csv", headers={"Content-Disposition": f'attachment; filename="Newsletter-{lang}.csv"'}
    )
    writer = csv.writer(response)
    for el in Membership.objects.filter(assoc_id=ctx["a_id"]):
        m = el.member
        if m.language != lang:
            continue

        lis = [m.email]

        if el.number:
            lis.append(el.number)
        else:
            lis.append("")

        lis.append(m.name)
        lis.append(m.surname)

        writer.writerow(lis)

    return response
