from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.balance import assoc_accounting, get_run_accounting
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
            _("There are no active events, to create a new one access the events management page"),
            "exe_events",
        )

    _exe_suggestions(ctx)

    features = get_assoc_features(ctx["a_id"])
    assoc = Association.objects.get(pk=ctx["a_id"])

    _exe_actions(ctx)

    _exe_accounting_actions(assoc, ctx, features)

    _exe_users_actions(request, assoc, ctx, features)

    _compile(request, ctx)

    return render(request, "larpmanager/manage/exe.html", ctx)


def _exe_suggestions(ctx):
    suggestions = {
        "exe_payment_details": _(
            "To set up the gateway payment available to players, to let them pay the registration fee through the platform, "
            "access the payment settings management page"
        ),
        "exe_profile": _(
            "To define which data will be asked in the profile form to the users once they sign up, "
            "access the profile management page"
        ),
        "exe_roles": _(
            "To grant access to organization management for other users and define roles with specific permissions, "
            "access the roles management page"
        ),
        "exe_appearance": _(
            "To customize the appearance of all organizational pages, including colors, fonts, and images, "
            "access the appearance management page"
        ),
        "exe_features": _(
            "To activate new features and enhance the functionality of the platform, "
            "access the features management page"
        ),
        "exe_config": _(
            "To set specific values for the interface configuration or features, "
            "access the configuration management page"
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
            _("There are <b>%(number)s</b> expenses to approve, access the expenses management panel")
            % {"number": expenses_approve},
            "exe_expenses",
        )

    payments_approve = PaymentInvoice.objects.filter(assoc_id=ctx["a_id"], status=PaymentStatus.SUBMITTED).count()
    if payments_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> payments to approve, access the invoices management panel")
            % {"number": payments_approve},
            "exe_invoices",
        )

    refund_approve = RefundRequest.objects.filter(assoc_id=ctx["a_id"], status=RefundStatus.REQUEST).count()
    if refund_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> refunds to deliver, access the refunds management panel")
            % {"number": refund_approve},
            "exe_refunds",
        )

    members_approve = Membership.objects.filter(assoc_id=ctx["a_id"], status=MembershipStatus.SUBMITTED).count()
    if members_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> members to approve, access the membership management panel")
            % {"number": members_approve},
            "exe_membership",
        )


def _exe_users_actions(request, assoc, ctx, features):
    if "membership" in features:
        if not get_assoc_text(ctx["a_id"], AssocTextType.MEMBERSHIP):
            _add_action(
                ctx,
                _("The membership request text is missing, create it in the texts management panel"),
                "exe_membership",
            )

    if "vote" in features:
        if not assoc.get_config("vote_candidates", ""):
            _add_action(
                ctx,
                _("There are no candidates for the voting, set them in the configuration panel"),
                "exe_config",
            )

    if "help" in features:
        _closed_q, open_q = _get_help_questions(ctx, request)
        if open_q:
            _add_action(
                ctx,
                _("There are <b>%(number)s</b> questions to answer, access the users questions management panel")
                % {"number": len(open_q)},
                "exe_questions",
            )


def _exe_accounting_actions(assoc, ctx, features):
    if "payment" in features:
        if not assoc.payment_methods.count():
            _add_action(
                ctx,
                _("There are no payment gateway active, configure them in the payment settings panel"),
                "exe_payment_details",
            )

    if "organization_tax" in features:
        if not assoc.get_config("organization_tax_perc", ""):
            _add_action(
                ctx,
                _("The organization tax configuration is missing, set them in the configuration panel"),
                "exe_accounting",
                "config/organization_tax",
            )

    if "vat" in features:
        if not assoc.get_config("vat_ticket", "") or not assoc.get_config("vat_options", ""):
            _add_action(
                ctx,
                _("The taxes configuration is missing, set them in the configuration panel"),
                "exe_accounting",
                "config/vat",
            )


def _orga_manage(request, s, n):
    ctx = get_event_run(request, s, n)
    # if run is not set, redirect
    if not ctx["run"].start or not ctx["run"].end:
        return redirect("orga_run", s=s, n=n)

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

    _orga_actions(request, ctx, assoc)

    _orga_suggestions(ctx)

    _compile(request, ctx)

    if ctx["event"].get_config("show_shortcuts_mobile", False):
        origin_id = request.GET.get("origin", "")
        should_open = False
        if origin_id:
            should_open = str(ctx["run"].id) != origin_id
        ctx["open_shortcuts"] = should_open

    return render(request, "larpmanager/manage/orga.html", ctx)


def _orga_actions(request, ctx, assoc):
    # if there are no characters, suggest to do it
    features = get_event_features(ctx["event"].id)

    if "character" in features:
        if not Character.objects.filter(event=ctx["event"]).count():
            _add_action(
                ctx,
                _("Create the first character of the event in the character management panel"),
                "orga_characters",
            )

    elif set(features) & {"faction", "plot", "casting", "user_character", "px", "custom_character", "questbuilder"}:
        _add_action(
            ctx,
            _("Some activated features need the 'Character' feature, it isn't active: access the feature panel"),
            "orga_features",
        )

    if "token_credit" not in features:
        if set(features) & {"expense", "refund", "collection"}:
            _add_action(
                ctx,
                _(
                    "Some activated features need the 'Token / Credit' feature, it isn't active: access the feature panel"
                ),
                "orga_features",
            )

    char_proposed = ctx["event"].get_elements(Character).filter(status=CharacterStatus.PROPOSED).count()
    if char_proposed:
        _add_action(
            ctx,
            _(
                "There are <b>%(number)s</b> characters in proposed status, approve them in the character management panel"
            )
            % {"number": char_proposed},
            "orga_characters",
        )

    expenses_approve = AccountingItemExpense.objects.filter(run=ctx["run"], is_approved=False).count()
    if expenses_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> expenses to approve, access the expenses management panel")
            % {"number": expenses_approve},
            "orga_expenses",
        )

    payments_approve = PaymentInvoice.objects.filter(reg__run=ctx["run"], status=PaymentStatus.SUBMITTED).count()
    if payments_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> payments to approve, access the invoices management panel")
            % {"number": payments_approve},
            "orga_invoices",
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
                _("There are <b>%(number)s</b> questions to answer, access the users questions management panel")
                % {"number": len(open_q)},
                "exe_questions",
            )


def _orga_casting_actions(ctx, features):
    if "casting" in features:
        if not ctx["event"].get_config("casting_min", 0):
            _add_action(
                ctx,
                _("Set the casting options in the configuration panel"),
                "orga_casting",
                "config/casting",
            )

    if "questbuilder" in features:
        if not ctx["event"].get_elements(QuestType).count():
            _add_action(
                ctx,
                _("No quest types have been created; use the quest type management panel to define them"),
                "orga_quest_types",
            )

        unused_quest_types = (
            ctx["event"].get_elements(QuestType).annotate(quest_count=Count("quests")).filter(quest_count=0)
        )
        if unused_quest_types.count():
            _add_action(
                ctx,
                _("There are quest types without quests: %(list)s. Create them in the quests management panel")
                % {"list": ", ".join([obj.name for obj in unused_quest_types])},
                "orga_quests",
            )

        unused_quests = ctx["event"].get_elements(Quest).annotate(trait_count=Count("traits")).filter(trait_count=0)
        if unused_quests.count():
            _add_action(
                ctx,
                _("There are quests without traits: %(list)s. Create them in the trait management panel")
                % {"list": ", ".join([obj.name for obj in unused_quests])},
                "orga_traits",
            )


def _orga_px_actions(ctx, features):
    if "px" not in features:
        return

    if not ctx["event"].get_config("px_start", 0):
        _add_action(
            ctx,
            _("Set the initial amount of experience points in the configuration panel"),
            "orga_px_abilities",
            "config/px",
        )

    if not ctx["event"].get_elements(AbilityTypePx).count():
        _add_action(
            ctx,
            _("No ability types have been created; use the ability type management panel to define them"),
            "orga_px_ability_types",
        )

    unused_ability_types = (
        ctx["event"].get_elements(AbilityTypePx).annotate(ability_count=Count("abilities")).filter(ability_count=0)
    )
    if unused_ability_types.count():
        _add_action(
            ctx,
            _(
                "There are ability types without abilities: %(list)s. Create abilities for them in the ability management panel"
            )
            % {"list": ", ".join([ability.name for ability in unused_ability_types])},
            "orga_px_abilities",
        )

    if not ctx["event"].get_elements(DeliveryPx).count():
        _add_action(
            ctx,
            _("No delivery for experience points have been created; create one in the delivery management panel"),
            "orga_px_deliveries",
        )


def _orga_reg_acc_actions(ctx, features):
    if "reg_installments" in features and "reg_quotas" in features:
        _add_action(
            ctx,
            _(
                "You have activated both fixed and dynamic installments; they are not meant to be used together, "
                "deactivate one of the two in the features management panel"
            ),
            "orga_features",
        )

    if "reg_quotas" in features and not ctx["event"].get_elements(RegistrationQuota).count():
        _add_action(
            ctx,
            _(
                "You have activated dynamic installments, but none have been yet created; "
                "access the dynamic installments management panel"
            ),
            "orga_registration_quotas",
        )

    if "reg_installments" in features:
        if not ctx["event"].get_elements(RegistrationInstallment).count():
            _add_action(
                ctx,
                _(
                    "You have activated fixed installments, but none have been yet created; "
                    "access the fixed installments management panel"
                ),
                "orga_registration_installments",
            )
        else:
            both_set = (
                ctx["event"]
                .get_elements(RegistrationInstallment)
                .filter(date_deadline__isnull=False, days_deadline__isnull=False)
            )
            if both_set:
                _add_action(
                    ctx,
                    _(
                        "You have some fixed installments with both date and days set, but those values cannot be set at the same time: %(list)s; "
                        "access the fixed installments management panel"
                    )
                    % {"list": ", ".join([obj.name for obj in both_set])},
                    "orga_registration_installments",
                )

            missing_final = ctx["event"].get_elements(RegistrationTicket).exclude(installments__amount=0)
            if missing_final:
                _add_action(
                    ctx,
                    _(
                        "You have some tickets without a final installment (with 0 amount): %(list)s; "
                        "access the fixed installments management panel"
                    )
                    % {"list": ", ".join([obj.name for obj in missing_final])},
                    "orga_registration_installments",
                )


def _orga_reg_actions(ctx, features):
    if "registration_open" in features and not ctx["run"].registration_open:
        _add_action(
            ctx,
            _(
                "You have activated registration opening date, but no value has been set; "
                "access the run management panel"
            ),
            "orga_run",
        )

    if "registration_secret" in features and not ctx["run"].registration_secret:
        _add_action(
            ctx,
            _(
                "You have activated registration secret link, but no value has been set; "
                "access the run management panel"
            ),
            "orga_run",
        )

    if "register_link" in features and not ctx["event"].register_link:
        _add_action(
            ctx,
            _(
                "You have activated registration external link, but no value has been set; "
                "access the event management panel"
            ),
            "orga_event",
        )

    if "custom_character" in features:
        configured = False
        for field in ["pronoun", "song", "public", "private", "profile"]:
            if ctx["event"].get_config("custom_character_" + field, False):
                configured = True

        if not configured:
            _add_action(
                ctx,
                _(
                    "You have activated character customization, but no fields has been set; "
                    "access the configuration panel"
                ),
                "orga_characters",
                "config/custom_character",
            )


def _orga_suggestions(ctx):
    suggestions = {
        "orga_registration_tickets": _(
            "To set the tickets that users can select during registration, access the tickets management page"
        ),
        "orga_registration_form": _(
            "To define the registration form, and set up any number of registration questions and their options, "
            "access the registration form management page"
        ),
        "orga_roles": _(
            "To grant access to event management for other users and define roles with specific permissions, "
            "access the roles management page"
        ),
        "orga_appearance": _(
            "To customize the appearance of all event pages, including colors, fonts, and images, "
            "access the appearance management page"
        ),
        "orga_features": _(
            "To activate new features and enhance the functionality of the event, access the features management page"
        ),
        "orga_config": _(
            "To set specific values for configuration of features of the event, "
            "access the configuration management page"
        ),
    }

    for perm, text in suggestions.items():
        if ctx["event"].get_config(f"{perm}_suggestion"):
            continue
        _add_suggestion(ctx, text, perm)


def _add_item(ctx, list_name, text, perm, link):
    if list_name not in ctx:
        ctx[list_name] = []

    ctx[list_name].append((text, perm, link))


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
