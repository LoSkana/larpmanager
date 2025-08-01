from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.balance import assoc_accounting, get_run_accounting
from larpmanager.cache.config import save_single_config
from larpmanager.cache.feature import get_assoc_features, get_event_features
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
from larpmanager.models.association import Association, AssocTextType
from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.models.experience import AbilityTypePx, DeliveryPx
from larpmanager.models.form import QuestionType, RegistrationQuestion, WritingQuestion
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import RegistrationInstallment, RegistrationQuota, RegistrationTicket
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.base import check_assoc_permission, def_user_ctx, get_index_assoc_permissions
from larpmanager.utils.common import _get_help_questions, format_datetime
from larpmanager.utils.edit import set_suggestion
from larpmanager.utils.event import check_event_permission, get_event_run, get_index_event_permissions
from larpmanager.utils.registration import registration_available
from larpmanager.utils.text import get_assoc_text


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
    ctx["manage"] = 1

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
        _add_priority(
            ctx,
            _("No events are present, create one"),
            "exe_events",
        )

    _exe_actions(request, ctx)

    _exe_suggestions(ctx)

    _compile(request, ctx)

    _check_intro_driver(request, ctx)

    return render(request, "larpmanager/manage/exe.html", ctx)


def _exe_suggestions(ctx):
    assoc = Association.objects.get(pk=ctx["a_id"])

    priorities = {
        "exe_quick": _("Quickly configure your organization's most important settings"),
    }

    for perm, text in priorities.items():
        if assoc.get_config(f"{perm}_suggestion"):
            continue
        _add_priority(ctx, text, perm)

    suggestions = {
        "exe_payment_details": _("Set up the payment methods available to players"),
        "exe_profile": _("Define which data will be asked in the profile form to the users once they sign up"),
        "exe_roles": _(
            "Grant access to organization management for other users and define roles with specific permissions"
        ),
        "exe_appearance": _(
            "Customize the appearance of all organizational pages, including colors, fonts, and images"
        ),
        "exe_features": _("Activate new features and enhance the functionality of the platform"),
        "exe_config": _("Set up specific values for the interface configuration or features"),
    }

    assoc = Association.objects.get(pk=ctx["a_id"])
    for perm, text in suggestions.items():
        if assoc.get_config(f"{perm}_suggestion"):
            continue
        _add_suggestion(ctx, text, perm)


def _exe_actions(request, ctx):
    features = get_assoc_features(ctx["a_id"])
    assoc = Association.objects.get(pk=ctx["a_id"])

    runs_conclude = Run.objects.filter(
        event__assoc_id=ctx["a_id"], development__in=[DevelopStatus.START, DevelopStatus.SHOW], end__lt=datetime.today()
    ).values_list("search", flat=True)
    if runs_conclude:
        _add_action(
            ctx,
            _(
                "There are past runs still open: <b>%(list)s</b>. Once all tasks (accounting, etc.) are finished, mark them as completed"
            )
            % {"list": ", ".join(runs_conclude)},
            "exe_runs",
        )

    expenses_approve = AccountingItemExpense.objects.filter(run__event__assoc_id=ctx["a_id"], is_approved=False).count()
    if expenses_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> expenses to approve") % {"number": expenses_approve},
            "exe_expenses",
        )

    payments_approve = PaymentInvoice.objects.filter(assoc_id=ctx["a_id"], status=PaymentStatus.SUBMITTED).count()
    if payments_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> payments to approve") % {"number": payments_approve},
            "exe_invoices",
        )

    refund_approve = RefundRequest.objects.filter(assoc_id=ctx["a_id"], status=RefundStatus.REQUEST).count()
    if refund_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> refunds to deliver") % {"number": refund_approve},
            "exe_refunds",
        )

    members_approve = Membership.objects.filter(assoc_id=ctx["a_id"], status=MembershipStatus.SUBMITTED).count()
    if members_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> members to approve") % {"number": members_approve},
            "exe_membership",
        )

    _exe_accounting_actions(assoc, ctx, features)

    _exe_users_actions(request, assoc, ctx, features)


def _exe_users_actions(request, assoc, ctx, features):
    if "membership" in features:
        if not get_assoc_text(ctx["a_id"], AssocTextType.MEMBERSHIP):
            _add_priority(ctx, _("Set up the membership request text"), "exe_membership", "texts")

        if len(assoc.get_config("membership_fee", "")) == 0:
            _add_priority(ctx, _("Set up the membership configuration"), "exe_membership", "config/membership")

    if "vote" in features:
        if not assoc.get_config("vote_candidates", ""):
            _add_priority(
                ctx,
                _("Set up the voting configuration"),
                "exe_config",
            )

    if "help" in features:
        _closed_q, open_q = _get_help_questions(ctx, request)
        if open_q:
            _add_action(
                ctx,
                _("There are <b>%(number)s</b> questions to answer") % {"number": len(open_q)},
                "exe_questions",
            )


def _exe_accounting_actions(assoc, ctx, features):
    if "payment" in features:
        if not assoc.payment_methods.count():
            _add_priority(
                ctx,
                _("Set up payment methods"),
                "exe_payment_details",
            )

    if "organization_tax" in features:
        if not assoc.get_config("organization_tax_perc", ""):
            _add_priority(
                ctx,
                _("Set up the organization tax configuration"),
                "exe_accounting",
                "config/organization_tax",
            )

    if "vat" in features:
        if not assoc.get_config("vat_ticket", "") or not assoc.get_config("vat_options", ""):
            _add_priority(
                ctx,
                _("Set up the taxes configuration"),
                "exe_accounting",
                "config/vat",
            )


def _orga_manage(request, s, n):
    ctx = get_event_run(request, s, n)
    # if run is not set, redirect
    if not ctx["run"].start or not ctx["run"].end:
        return redirect("orga_run", s=s, n=n)

    ctx["orga_page"] = 1
    ctx["manage"] = 1

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

    _exe_actions(request, ctx)
    # keep only priorities
    if "actions_list" in ctx:
        del ctx["actions_list"]

    _orga_actions_priorities(request, ctx, assoc)

    _orga_suggestions(ctx)

    _compile(request, ctx)

    if ctx["event"].get_config("show_shortcuts_mobile", False):
        origin_id = request.GET.get("origin", "")
        should_open = False
        if origin_id:
            should_open = str(ctx["run"].id) != origin_id
        ctx["open_shortcuts"] = should_open

    _check_intro_driver(request, ctx)

    return render(request, "larpmanager/manage/orga.html", ctx)


def _orga_actions_priorities(request, ctx, assoc):
    # if there are no characters, suggest to do it
    features = get_event_features(ctx["event"].id)

    if "character" in features:
        if not Character.objects.filter(event=ctx["event"]).count():
            _add_priority(
                ctx,
                _("Create the first character of the event"),
                "orga_characters",
            )

    elif set(features) & {"faction", "plot", "casting", "user_character", "px", "custom_character", "questbuilder"}:
        _add_priority(
            ctx,
            _("Some activated features need the 'Character' feature, but it isn't active"),
            "orga_features",
        )

    if "user_character" in features:
        if ctx["event"].get_config("user_character_max", "") == "":
            _add_priority(
                ctx,
                _("Set up the configuration for the creation or editing of characters by the players"),
                "orga_character",
                "config/user_character",
            )

    if "token_credit" not in features:
        if set(features) & {"expense", "refund", "collection"}:
            _add_priority(
                ctx,
                _("Some activated features need the 'Token / Credit' feature, but it isn't active"),
                "orga_features",
            )

    char_proposed = ctx["event"].get_elements(Character).filter(status=CharacterStatus.PROPOSED).count()
    if char_proposed:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> characters to approve") % {"number": char_proposed},
            "orga_characters",
        )

    expenses_approve = AccountingItemExpense.objects.filter(run=ctx["run"], is_approved=False).count()
    if expenses_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> expenses to approve") % {"number": expenses_approve},
            "orga_expenses",
        )

    payments_approve = PaymentInvoice.objects.filter(reg__run=ctx["run"], status=PaymentStatus.SUBMITTED).count()
    if payments_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> payments to approve") % {"number": payments_approve},
            "orga_invoices",
        )

    # form
    empty_reg_questions = (
        ctx["event"]
        .get_elements(RegistrationQuestion)
        .filter(typ__in=[QuestionType.SINGLE, QuestionType.MULTIPLE])
        .annotate(quest_count=Count("options"))
        .filter(quest_count=0)
    )
    if empty_reg_questions.count():
        _add_priority(
            ctx,
            _("There are registration questions without options: %(list)s")
            % {"list": ", ".join([obj.display for obj in empty_reg_questions])},
            "orga_registration_form",
        )

    empty_char_questions = (
        ctx["event"]
        .get_elements(WritingQuestion)
        .filter(typ__in=[QuestionType.SINGLE, QuestionType.MULTIPLE])
        .annotate(quest_count=Count("options"))
        .filter(quest_count=0)
    )
    if empty_char_questions.count():
        _add_priority(
            ctx,
            _("There are writing fields without options: %(list)s")
            % {"list": ", ".join([obj.display for obj in empty_char_questions])},
            "orga_character_form",
        )

    _orga_user_actions(ctx, features, request, assoc)

    _orga_reg_acc_actions(ctx, features)

    _orga_reg_actions(ctx, features)

    _orga_px_actions(ctx, features)

    _orga_casting_actions(ctx, features)


def _orga_user_actions(ctx, features, request, assoc):
    if "help" in features:
        _closed_q, open_q = _get_help_questions(ctx, request)
        if open_q:
            _add_action(
                ctx,
                _("There are <b>%(number)s</b> questions to answer") % {"number": len(open_q)},
                "exe_questions",
            )


def _orga_casting_actions(ctx, features):
    if "casting" in features:
        if not ctx["event"].get_config("casting_min", 0):
            _add_priority(
                ctx,
                _("Set the casting options in the configuration panel"),
                "orga_casting",
                "config/casting",
            )

    if "questbuilder" in features:
        if not ctx["event"].get_elements(QuestType).count():
            _add_priority(
                ctx,
                _("Set up quest types"),
                "orga_quest_types",
            )

        unused_quest_types = (
            ctx["event"].get_elements(QuestType).annotate(quest_count=Count("quests")).filter(quest_count=0)
        )
        if unused_quest_types.count():
            _add_priority(
                ctx,
                _("There are quest types without quests: %(list)s")
                % {"list": ", ".join([obj.name for obj in unused_quest_types])},
                "orga_quests",
            )

        unused_quests = ctx["event"].get_elements(Quest).annotate(trait_count=Count("traits")).filter(trait_count=0)
        if unused_quests.count():
            _add_priority(
                ctx,
                _("There are quests without traits: %(list)s")
                % {"list": ", ".join([obj.name for obj in unused_quests])},
                "orga_traits",
            )


def _orga_px_actions(ctx, features):
    if "px" not in features:
        return

    if not ctx["event"].get_config("px_start", 0):
        _add_priority(
            ctx,
            _("Set the experience points configuration"),
            "orga_px_abilities",
            "config/px",
        )

    if not ctx["event"].get_elements(AbilityTypePx).count():
        _add_priority(
            ctx,
            _("Set up ability types"),
            "orga_px_ability_types",
        )

    unused_ability_types = (
        ctx["event"].get_elements(AbilityTypePx).annotate(ability_count=Count("abilities")).filter(ability_count=0)
    )
    if unused_ability_types.count():
        _add_priority(
            ctx,
            _("There are ability types without abilities: %(list)s")
            % {"list": ", ".join([ability.name for ability in unused_ability_types])},
            "orga_px_abilities",
        )

    if not ctx["event"].get_elements(DeliveryPx).count():
        _add_priority(
            ctx,
            _("Set up delivery for experience points"),
            "orga_px_deliveries",
        )


def _orga_reg_acc_actions(ctx, features):
    if "reg_installments" in features and "reg_quotas" in features:
        _add_priority(
            ctx,
            _(
                "You have activated both fixed and dynamic installments; they are not meant to be used together, "
                "deactivate one of the two in the features management panel"
            ),
            "orga_features",
        )

    if "reg_quotas" in features and not ctx["event"].get_elements(RegistrationQuota).count():
        _add_priority(
            ctx,
            _("Set up dynamic installments"),
            "orga_registration_quotas",
        )

    if "reg_installments" in features:
        if not ctx["event"].get_elements(RegistrationInstallment).count():
            _add_priority(
                ctx,
                _("Set up fixed installments"),
                "orga_registration_installments",
            )
        else:
            both_set = (
                ctx["event"]
                .get_elements(RegistrationInstallment)
                .filter(date_deadline__isnull=False, days_deadline__isnull=False)
            )
            if both_set:
                _add_priority(
                    ctx,
                    _(
                        "You have some fixed installments with both date and days set, but those values cannot be set at the same time: %(list)s"
                    )
                    % {"list": ", ".join([obj.name for obj in both_set])},
                    "orga_registration_installments",
                )

            missing_final = ctx["event"].get_elements(RegistrationTicket).exclude(installments__amount=0)
            if missing_final:
                _add_priority(
                    ctx,
                    _("You have some tickets without a final installment (with 0 amount): %(list)s")
                    % {"list": ", ".join([obj.name for obj in missing_final])},
                    "orga_registration_installments",
                )

    if "reduced" in features:
        if not ctx["event"].get_config("reduced_ratio", 0):
            _add_priority(
                ctx,
                _("Set up configuration for Patron and Reduced tickets"),
                "orga_registration_tickets",
                "config/reduced",
            )


def _orga_reg_actions(ctx, features):
    if "registration_open" in features and not ctx["run"].registration_open:
        _add_priority(
            ctx,
            _("Set up a value for registration opening date"),
            "orga_run",
        )

    if "registration_secret" in features and not ctx["run"].registration_secret:
        _add_priority(
            ctx,
            _("Set up a value for registration secret link"),
            "orga_run",
        )

    if "register_link" in features and not ctx["event"].register_link:
        _add_priority(
            ctx,
            _("Set up a value for registration external link"),
            "orga_event",
        )

    if "custom_character" in features:
        configured = False
        for field in ["pronoun", "song", "public", "private", "profile"]:
            if ctx["event"].get_config("custom_character_" + field, False):
                configured = True

        if not configured:
            _add_priority(
                ctx,
                _("Set up character customization configuration"),
                "orga_characters",
                "config/custom_character",
            )


def _orga_suggestions(ctx):
    priorities = {
        "orga_quick": _("Quickly configure your events's most important settings"),
        "orga_registration_tickets": _("Set up the tickets that users can select during registration"),
    }

    for perm, text in priorities.items():
        if ctx["event"].get_config(f"{perm}_suggestion"):
            continue
        _add_priority(ctx, text, perm)

    suggestions = {
        "orga_registration_form": _(
            "Define the registration form, and set up any number of registration questions and their options"
        ),
        "orga_roles": _("Grant access to event management for other users and define roles with specific permissions"),
        "orga_appearance": _("Customize the appearance of all event pages, including colors, fonts, and images"),
        "orga_features": _("Activate new features and enhance the functionality of the event"),
        "orga_config": _("Set specific values for configuration of features of the event"),
    }

    for perm, text in suggestions.items():
        if ctx["event"].get_config(f"{perm}_suggestion"):
            continue
        _add_suggestion(ctx, text, perm)


def _add_item(ctx, list_name, text, perm, link):
    if list_name not in ctx:
        ctx[list_name] = []

    ctx[list_name].append((text, perm, link))


def _add_priority(ctx, text, perm, link=None):
    _add_item(ctx, "priorities_list", text, perm, link)


def _add_action(ctx, text, perm, link=None):
    _add_item(ctx, "actions_list", text, perm, link)


def _add_suggestion(ctx, text, perm, link=None):
    _add_item(ctx, "suggestions_list", text, perm, link)


def _has_permission(request, ctx, perm):
    if perm.startswith("exe"):
        return has_assoc_permission(request, perm)
    return has_event_permission(ctx, request, ctx["event"].slug, perm)


def _get_href(ctx, perm, name, custom_link):
    if custom_link:
        return _("Configuration"), _get_perm_link(ctx, perm, "manage") + custom_link

    return _(name), _get_perm_link(ctx, perm, perm)


def _get_perm_link(ctx, perm, view):
    if perm.startswith("exe"):
        return reverse(view)
    return reverse(view, args=[ctx["event"].slug, ctx["run"].number])


def _compile(request, ctx):
    section_list = ["suggestions", "actions", "priorities"]
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
        if f"{section}_list" not in ctx:
            continue

        perm_list.extend([slug for _n, slug, _u in ctx[f"{section}_list"] if _has_permission(request, ctx, slug)])

    for model in (EventPermission, AssocPermission):
        queryset = model.objects.filter(slug__in=perm_list).select_related("feature")
        for slug, name, tutorial in queryset.values_list("slug", "name", "feature__tutorial"):
            cache[slug] = (name, tutorial)

    for section in section_list:
        if f"{section}_list" not in ctx:
            continue

        for text, slug, custom_link in ctx[f"{section}_list"]:
            if slug not in cache:
                continue

            (name, tutorial) = cache[slug]
            link_name, link_url = _get_href(ctx, slug, name, custom_link)
            ctx[section].append({"text": text, "link": link_name, "href": link_url, "tutorial": tutorial, "slug": slug})


def exe_close_suggestion(request, perm):
    ctx = check_assoc_permission(request, perm)
    set_suggestion(ctx, perm)
    return redirect("manage")


def orga_close_suggestion(request, s, n, perm):
    ctx = check_event_permission(request, s, n, perm)
    set_suggestion(ctx, perm)
    return redirect("manage", s=s, n=n)


def _check_intro_driver(request, ctx):
    if ctx["interface_old"]:
        return

    member = request.user.member
    config_name = "intro_driver"
    if member.get_config(config_name, False):
        return

    ctx["intro_driver"] = True
    save_single_config(member, config_name, True)
