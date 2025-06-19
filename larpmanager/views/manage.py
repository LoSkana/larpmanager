from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.balance import assoc_accounting, get_run_accounting
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.registration import get_reg_counts
from larpmanager.cache.role import has_assoc_permission, has_event_permission
from larpmanager.models.access import AssocPermission, EventPermission
from larpmanager.models.accounting import (
    AccountingItemExpense,
    PaymentInvoice,
    PaymentStatus,
    RefundRequest,
    RefundStatus,
)
from larpmanager.models.association import Association
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.base import check_assoc_permission, def_user_ctx, get_index_assoc_permissions
from larpmanager.utils.common import format_datetime
from larpmanager.utils.edit import set_suggestion
from larpmanager.utils.event import check_event_permission, get_event_run, get_index_event_permissions
from larpmanager.utils.registration import registration_available


@login_required
def manage(request, s=None, n=None):
    if request.assoc["id"] == 0:
        return redirect("home")

    if s:
        return _orga_manage(request, s, n)
    else:
        return _exe_manage(request)


def _get_registration_status(run):
    features = get_event_features(run.event_id)
    if "register_link" in features and run.event.register_link:
        return _("Registrations on external link")

    # check pre-register
    if not run.registration_open and run.event.get_config("pre_register_active", False):
        return _("Pre-registration active")

    dt = datetime.today()
    # check registration open
    if "registration_open" in features:
        if not run.registration_open:
            return _("Registrations opening not set")

        elif run.registration_open > dt:
            return _("Registrations opening at: %(date)s") % {"date": run.registration_open.strftime(format_datetime)}

    run.status = {}
    registration_available(run, features)

    # signup open, not already signed in
    status = run.status
    messages = {
        "primary": _("Registrations open"),
        "filler": _("Filler registrations"),
        "waiting": _("Waiting list registrations"),
    }

    # pick the first matching message (or None)
    mes = next((msg for key, msg in messages.items() if key in status), None)
    if mes:
        return mes
    else:
        return _("Registration closed")


def _exe_manage(request):
    ctx = def_user_ctx(request)
    get_index_assoc_permissions(ctx, request, request.assoc["id"])
    ctx["exe_page"] = 1

    ctx["event_counts"] = Event.objects.filter(assoc_id=ctx["a_id"]).count()

    que = Run.objects.filter(event__assoc_id=ctx["a_id"], development__in=[DevelopStatus.START, DevelopStatus.SHOW])
    ctx["ongoing_runs"] = que.select_related("event").order_by("end")
    for run in ctx["ongoing_runs"]:
        run.registration_status = _get_registration_status(run)
        run.counts = get_reg_counts(run)

    if has_assoc_permission(request, "exe_accounting"):
        assoc_accounting(ctx)

    # if no event active, suggest to create one
    if not ctx["ongoing_runs"]:
        _add_suggestion(
            ctx,
            _("There are no active events, to create a new one access the events management page:"),
            "exe_events",
        )

    _exe_suggestions(ctx)

    _exe_actions(ctx)

    _compile(request, ctx)

    return render(request, "larpmanager/manage/exe.html", ctx)


def _exe_suggestions(ctx):
    suggestions = {
        "exe_payment_details": _(
            "To set up the gateway payment available to players, to let them pay the registration fee through the platform, "
            "access the payment settings management page:"
        ),
        "exe_profile": _(
            "To define which data will be asked in the profile form to the users once they sign up, "
            "access the profile management page:"
        ),
        "exe_roles": _(
            "To grant access to organization management for other users and define roles with specific permissions, "
            "access the roles management page:"
        ),
        "exe_appearance": _(
            "To customize the appearance of all organizational pages, including colors, fonts, and images, "
            "access the appearance management page:"
        ),
        "exe_features": _(
            "To activate new features and enhance the functionality of the platform, "
            "access the features management page:"
        ),
        "exe_config": _(
            "To set specific values for the interface configuration or features, "
            "access the configuration management page:"
        ),
    }

    assoc = Association.objects.get(pk=ctx["a_id"])
    for perm, text in suggestions.items():
        if assoc.get_config(f"{perm}_suggestion"):
            continue
        _add_suggestion(ctx, text, perm)


def _exe_actions(ctx):
    expenses_approve = AccountingItemExpense.objects.filter(run__event__assoc_id=ctx["a_id"], is_approved=False).count()
    if expenses_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> expenses to approve, access the expenses management panel:")
            % {"number": expenses_approve},
            "exe_expenses",
        )

    payments_approve = PaymentInvoice.objects.filter(assoc_id=ctx["a_id"], status=PaymentStatus.SUBMITTED).count()
    if payments_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> payments to approve, access the invoices management panel:")
            % {"number": payments_approve},
            "exe_invoices",
        )

    refund_approve = RefundRequest.objects.filter(assoc_id=ctx["a_id"], status=RefundStatus.REQUEST).count()
    if refund_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> refunds to deliver, access the refunds management panel:")
            % {"number": refund_approve},
            "exe_refunds",
        )

    members_approve = Membership.objects.filter(assoc_id=ctx["a_id"], status=MembershipStatus.SUBMITTED).count()
    if members_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> members to approve, access the membership management panel:")
            % {"number": members_approve},
            "exe_membership",
        )


def _orga_manage(request, s, n):
    ctx = get_event_run(request, s, n)
    get_index_event_permissions(ctx, request, s)
    assoc = Association.objects.get(pk=request.assoc["id"])
    if assoc.get_config("interface_admin_links", False):
        get_index_assoc_permissions(ctx, request, request.assoc["id"], check=False)

    ctx["registration_status"] = _get_registration_status(ctx["run"])

    if has_event_permission(ctx, request, s, "orga_registrations"):
        ctx["counts"] = get_reg_counts(ctx["run"])
        ctx["reg_counts"] = {}
        # TODO simplify
        for tier in ["player", "staff", "wait", "fill", "seller", "npc", "collaborator"]:
            key = f"count_{tier}"
            if key in ctx["counts"]:
                ctx["reg_counts"][_(tier.capitalize())] = ctx["counts"][key]

    if has_event_permission(ctx, request, s, "orga_accounting"):
        ctx["dc"] = get_run_accounting(ctx["run"], ctx)

    _orga_actions(ctx)

    _orga_suggestions(ctx)

    _compile(request, ctx)

    return render(request, "larpmanager/manage/orga.html", ctx)


def _orga_actions(ctx):
    char_proposed = ctx["event"].get_elements(Character).filter(status=CharacterStatus.PROPOSED).count()
    if char_proposed:
        _add_action(
            ctx,
            _(
                "There are <b>%(number)s</b> characters in proposed status, approve them in the character management panel:"
            )
            % {"number": char_proposed},
            "orga_characters",
        )

    expenses_approve = AccountingItemExpense.objects.filter(run=ctx["run"], is_approved=False).count()
    if expenses_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> expenses to approve, access the expenses management panel:")
            % {"number": expenses_approve},
            "orga_expenses",
        )

    payments_approve = PaymentInvoice.objects.filter(reg__run=ctx["run"], status=PaymentStatus.SUBMITTED).count()
    if payments_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> payments to approve, access the invoices management panel:")
            % {"number": payments_approve},
            "orga_invoices",
        )


def _orga_suggestions(ctx):
    suggestions = {
        "orga_registration_tickets": _(
            "To set the tickets that users can select during registration, access the tickets management page:"
        ),
        "orga_registration_form": _(
            "To define the registration form, and set up any number of registration questions and their options, "
            "access the registration form management page:"
        ),
        "orga_roles": _(
            "To grant access to event management for other users and define roles with specific permissions, "
            "access the roles management page:"
        ),
        "orga_appearance": _(
            "To customize the appearance of all event pages, including colors, fonts, and images, "
            "access the appearance management page:"
        ),
        "orga_features": _(
            "To activate new features and enhance the functionality of the event, access the features management page:"
        ),
        "orga_config": _(
            "To set specific values for configuration of features of the event, "
            "access the configuration management page:"
        ),
    }

    for perm, text in suggestions.items():
        if ctx["event"].get_config(f"{perm}_suggestion"):
            continue
        _add_suggestion(ctx, text, perm)


def _add_item(ctx, list_name, text, perm):
    if list_name not in ctx:
        ctx[list_name] = []

    ctx[list_name].append((text, perm))


def _add_action(ctx, text, perm):
    _add_item(ctx, "actions_list", text, perm)


def _add_suggestion(ctx, text, perm):
    _add_item(ctx, "suggestions_list", text, perm)


def _has_permission(request, ctx, perm):
    if perm.startswith("exe"):
        return has_assoc_permission(request, perm)
    return has_event_permission(ctx, request, ctx["event"].slug, perm)


def _get_href(ctx, perm):
    if perm.startswith("exe"):
        return reverse(perm)

    return reverse(perm, args=[ctx["event"].slug, ctx["run"].number])


def _compile(request, ctx):
    ctx["suggestions_header"] = _("Suggestions")
    ctx["actions_header"] = _("Actions")
    section_list = ["suggestions", "actions"]
    empty = True
    for section in section_list:
        ctx[section] = []
        if f"{section}_list" in ctx:
            empty = False

    if empty:
        return

    cache = {}
    perm_list = []
    for section in section_list:
        perm_list.extend([slug for _, slug in ctx[f"{section}_list"] if _has_permission(request, ctx, slug)])

    for model in (EventPermission, AssocPermission):
        queryset = model.objects.filter(slug__in=perm_list).select_related("feature")
        for slug, name, tutorial in queryset.values_list("slug", "name", "feature__tutorial"):
            cache[slug] = (name, tutorial)

    for section in section_list:
        for text, slug in ctx[f"{section}_list"]:
            if slug not in cache:
                continue

            (name, tutorial) = cache[slug]
            ctx[section].append(
                {"text": text, "link": _(name), "href": _get_href(ctx, slug), "tutorial": tutorial, "slug": slug}
            )


def exe_close_suggestion(request, perm):
    ctx = check_assoc_permission(request, perm)
    set_suggestion(ctx, perm)
    return redirect("manage")


def orga_close_suggestion(request, s, n, perm):
    ctx = check_event_permission(request, s, n, perm)
    set_suggestion(ctx, perm)
    return redirect("manage", s=s, n=n)
