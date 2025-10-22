from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.forms import ChoiceField, Form
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_select2.forms import Select2Widget
from slugify import slugify

from larpmanager.accounting.balance import assoc_accounting, get_run_accounting
from larpmanager.cache.config import get_assoc_config, get_event_config
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
from larpmanager.models.association import AssocTextType
from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.models.experience import AbilityTypePx, DeliveryPx
from larpmanager.models.form import BaseQuestionType, RegistrationQuestion, WritingQuestion
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import RegistrationInstallment, RegistrationQuota, RegistrationTicket
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.base import check_assoc_permission, def_user_ctx, get_index_assoc_permissions
from larpmanager.utils.common import _get_help_questions, format_datetime
from larpmanager.utils.edit import set_suggestion
from larpmanager.utils.event import check_event_permission, get_event_run, get_index_event_permissions
from larpmanager.utils.exceptions import RedirectError
from larpmanager.utils.registration import registration_available
from larpmanager.utils.text import get_assoc_text
from larpmanager.utils.tutorial_query import GUIDE_INDEX, TUTORIAL_INDEX, get_or_create_index_tutorial


@login_required
def manage(request, s=None):
    """Main management dashboard routing.

    Routes to either executive management or organizer management
    based on whether an event slug is provided.

    Args:
        request: Django HTTP request object (must be authenticated)
        s: Optional event slug for organizer management

    Returns:
        HttpResponse: Redirect to home or appropriate management view
    """
    if request.assoc["id"] == 0:
        return redirect("home")

    if s:
        return _orga_manage(request, s)
    else:
        return _exe_manage(request)


def _get_registration_status_code(run):
    """Get registration status code for a run with additional value.

    Args:
        run: Run instance to check status for

    Returns:
        tuple: (status_code, additional_value) where:
            - external: (code, register_link)
            - future: (code, registration_open)
            - primary/filler/waiting: (code, remaining_count)
            - others: (code, None)
    """
    features = get_event_features(run.event_id)

    # Check external registration link
    if "register_link" in features and run.event.register_link:
        return "external", run.event.register_link

    # Check pre-registration
    if not run.registration_open and get_event_config(run.event_id, "pre_register_active", False):
        return "preregister", None

    # Check registration opening time
    dt = datetime.today()
    if "registration_open" in features:
        if not run.registration_open:
            return "not_set", None
        if run.registration_open > dt:
            return "future", run.registration_open

    # Check registration availability
    run.status = {}
    registration_available(run, features)
    status = run.status

    # Determine status based on availability
    status_priority = ["primary", "filler", "waiting"]
    for status_type in status_priority:
        if status_type in status:
            return status_type, status.get("count")

    return "closed", None


def _get_registration_status(run) -> str:
    """Get human-readable registration status for a run.

    This function retrieves the registration status code and returns a localized,
    user-friendly message describing the current registration state for the given run.

    Args:
        run: Run instance to check status for. Expected to have registration-related
             attributes that can be processed by _get_registration_status_code().

    Returns:
        str: Localized status message describing registration state. Returns one of
             several predefined messages or a formatted datetime string for future
             registrations.

    Note:
        Depends on _get_registration_status_code() to provide the status code and
        any additional values (like datetime for future registrations).
    """
    # Get the current status code and any additional data from the run
    status_code, additional_value = _get_registration_status_code(run)

    # Define mapping of status codes to localized human-readable messages
    status_messages = {
        "external": _("Registrations on external link"),
        "preregister": _("Pre-registration active"),
        "not_set": _("Registrations opening not set"),
        "primary": _("Registrations open"),
        "filler": _("Filler registrations"),
        "waiting": _("Waiting list registrations"),
        "closed": _("Registration closed"),
    }

    # Special handling for future registrations with datetime formatting
    if status_code == "future":
        # Check if we have a valid datetime to format
        if additional_value:
            formatted_date = additional_value.strftime(format_datetime)
            return _("Registrations opening at: %(date)s") % {"date": formatted_date}
        else:
            # Fallback when datetime is not available
            return _("Registrations opening not set")

    # Return the appropriate status message or default to closed
    return status_messages.get(status_code, _("Registration closed"))


def _exe_manage(request: HttpRequest) -> HttpResponse:
    """Executive management dashboard view.

    Displays association-level management interface with events,
    suggestions, actions, and accounting information.

    Args:
        request: Django HTTP request object containing user and association data

    Returns:
        HttpResponse: Rendered executive management dashboard template or redirect response

    Redirects:
        - To event creation if no events exist and exe_events feature is available
        - To quick setup if not completed
    """
    # Initialize context and permissions for the current user and association
    ctx = def_user_ctx(request)
    get_index_assoc_permissions(ctx, request, request.assoc["id"])
    ctx["exe_page"] = 1
    ctx["manage"] = 1

    # Check what would you like form
    what_would_you_like(ctx, request)

    # Get available features for this association
    features = get_assoc_features(ctx["a_id"])

    # Check if association has any events
    ctx["event_counts"] = Event.objects.filter(assoc_id=ctx["a_id"]).count()

    # Redirect to event creation if no events exist and feature is available
    if not ctx["event_counts"] and "exe_events" in features:
        msg = (
            _("Welcome")
            + "! "
            + _("You don't have any events yet")
            + ". "
            + _("Please create your first event to get started")
            + "!"
        )
        messages.success(request, msg)
        return redirect("exe_events_edit", num=0)

    # Redirect to quick setup if not completed
    if not get_assoc_config(ctx["a_id"], "exe_quick_suggestion", False):
        msg = _(
            "Before accessing the organization dashboard, please complete the quick setup by selecting "
            "the features most useful for your organization"
        )
        messages.success(request, msg)
        return redirect("exe_quick")

    # Get ongoing runs (events in START or SHOW development status)
    que = Run.objects.filter(event__assoc_id=ctx["a_id"], development__in=[DevelopStatus.START, DevelopStatus.SHOW])
    ctx["ongoing_runs"] = que.select_related("event").order_by("end")

    # Add registration status and counts for each ongoing run
    for run in ctx["ongoing_runs"]:
        run.registration_status = _get_registration_status(run)
        run.counts = get_reg_counts(run)

    # Add accounting information if user has permission
    if has_assoc_permission(request, ctx, "exe_accounting"):
        assoc_accounting(ctx)

    # Suggest creating an event if no runs are active
    if not ctx["ongoing_runs"]:
        _add_priority(
            ctx,
            _("No events are present, create one"),
            "exe_events",
        )

    # Add dashboard actions and suggestions
    _exe_actions(request, ctx, features)
    _exe_suggestions(ctx)

    # Compile final context and check for intro driver
    _compile(request, ctx)
    _check_intro_driver(request, ctx)

    return render(request, "larpmanager/manage/exe.html", ctx)


def _exe_suggestions(ctx):
    """Add priority tasks and suggestions to the executive management context.

    Args:
        ctx: Context dictionary containing association ID and other data
    """
    suggestions = {
        "exe_methods": _("Set up the payment methods available to participants"),
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

    for perm, text in suggestions.items():
        if get_assoc_config(ctx["a_id"], f"{perm}_suggestion"):
            continue
        _add_suggestion(ctx, text, perm)


def _exe_actions(request, ctx: dict, features: dict = None) -> None:
    """Determine available executive actions based on association features.

    Adds action items to the management dashboard based on user permissions
    and association configuration settings.

    Args:
        request: HTTP request object
        ctx: Context dictionary containing association ID and other data
        features: Dictionary of association features, defaults to None

    Returns:
        None: Modifies ctx in place by adding action items
    """
    # Get association features if not provided
    if not features:
        features = get_assoc_features(ctx["a_id"])

    # Check for runs that should be concluded
    runs_conclude = Run.objects.filter(
        event__assoc_id=ctx["a_id"], development__in=[DevelopStatus.START, DevelopStatus.SHOW], end__lt=datetime.today()
    ).values_list("search", flat=True)

    # Add action for past runs still open
    if runs_conclude:
        _add_action(
            ctx,
            _(
                "There are past runs still open: <b>%(list)s</b>. Once all tasks (accounting, etc.) are finished, mark them as completed"
            )
            % {"list": ", ".join(runs_conclude)},
            "exe_events",
        )

    # Check for pending expense approvals
    expenses_approve = AccountingItemExpense.objects.filter(run__event__assoc_id=ctx["a_id"], is_approved=False).count()
    if expenses_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> expenses to approve") % {"number": expenses_approve},
            "exe_expenses",
        )

    # Check for pending payment approvals
    payments_approve = PaymentInvoice.objects.filter(assoc_id=ctx["a_id"], status=PaymentStatus.SUBMITTED).count()
    if payments_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> payments to approve") % {"number": payments_approve},
            "exe_invoices",
        )

    # Check for pending refund approvals
    refund_approve = RefundRequest.objects.filter(assoc_id=ctx["a_id"], status=RefundStatus.REQUEST).count()
    if refund_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> refunds to deliver") % {"number": refund_approve},
            "exe_refunds",
        )

    # Check for pending member approvals
    members_approve = Membership.objects.filter(assoc_id=ctx["a_id"], status=MembershipStatus.SUBMITTED).count()
    if members_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> members to approve") % {"number": members_approve},
            "exe_membership",
        )

    # Process accounting-specific actions
    _exe_accounting_actions(request, ctx, features)

    # Process user-specific actions
    _exe_users_actions(request, ctx, features)


def _exe_users_actions(request, ctx, features):
    """
    Process user management actions and setup tasks for executives.

    Args:
        request: HTTP request object
        assoc: Association instance
        ctx: Context dictionary to populate with actions
        features: Set of enabled features
    """
    if "membership" in features:
        if not get_assoc_text(ctx["a_id"], AssocTextType.MEMBERSHIP):
            _add_priority(ctx, _("Set up the membership request text"), "exe_membership", "texts")

        if len(get_assoc_config(request.assoc["id"], "membership_fee", "")) == 0:
            _add_priority(ctx, _("Set up the membership configuration"), "exe_membership", "config/membership")

    if "vote" in features:
        if not get_assoc_config(request.assoc["id"], "vote_candidates", ""):
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


def _exe_accounting_actions(request, ctx, features):
    """
    Process accounting-related setup actions for executives.

    Args:
        request: request instance
        ctx: Context dictionary to populate with priority actions
        features: Set of enabled features for the association
    """
    if "payment" in features:
        if not request.assoc.get("methods", ""):
            _add_priority(
                ctx,
                _("Set up payment methods"),
                "exe_methods",
            )

    if "organization_tax" in features:
        if not get_assoc_config(request.assoc["id"], "organization_tax_perc", ""):
            _add_priority(
                ctx,
                _("Set up the organization tax configuration"),
                "exe_accounting",
                "config/organization_tax",
            )

    if "vat" in features:
        if not get_assoc_config(request.assoc["id"], "vat_ticket", "") or not get_assoc_config(
            request.assoc["id"], "vat_options", ""
        ):
            _add_priority(
                ctx,
                _("Set up the taxes configuration"),
                "exe_accounting",
                "config/vat",
            )


def _orga_manage(request: HttpRequest, s: str) -> HttpResponse:
    """Event organizer management dashboard view.

    Args:
        request: HTTP request
        s: Event slug

    Returns:
        Rendered dashboard
    """

    # Set page context
    ctx = get_event_run(request, s)
    ctx["orga_page"] = 1
    ctx["manage"] = 1

    # Check what would you like form
    what_would_you_like(ctx, request)

    # Ensure run dates are set
    if not ctx["run"].start or not ctx["run"].end:
        msg = _("Last step, please complete the event setup by adding the start and end dates")
        messages.success(request, msg)
        return redirect("orga_run", s=s)

    # Ensure quick setup is complete
    if not get_event_config(ctx["event"].id, "orga_quick_suggestion", False, ctx):
        msg = _(
            "Before accessing the event dashboard, please complete the quick setup by selecting "
            "the features most useful for your event"
        )
        messages.success(request, msg)
        return redirect("orga_quick", s=s)

    # Load permissions and navigation
    get_index_event_permissions(ctx, request, s)
    if get_assoc_config(request.assoc["id"], "interface_admin_links", False):
        get_index_assoc_permissions(ctx, request, request.assoc["id"], check=False)

    # Load registration status
    ctx["registration_status"] = _get_registration_status(ctx["run"])

    # Load registration counts if permitted
    if has_event_permission(request, ctx, s, "orga_registrations"):
        ctx["counts"] = get_reg_counts(ctx["run"])
        ctx["reg_counts"] = {}
        for tier in ["player", "staff", "wait", "fill", "seller", "npc", "collaborator"]:
            key = f"count_{tier}"
            if key in ctx["counts"]:
                ctx["reg_counts"][_(tier.capitalize())] = ctx["counts"][key]

    # Load accounting if permitted
    if has_event_permission(request, ctx, s, "orga_accounting"):
        ctx["dc"] = get_run_accounting(ctx["run"], ctx, perform_update=False)

    # Build action lists
    _exe_actions(request, ctx)
    if "actions_list" in ctx:
        del ctx["actions_list"]

    _orga_actions_priorities(request, ctx)
    _orga_suggestions(ctx)
    _compile(request, ctx)

    # Mobile shortcuts handling
    if get_event_config(ctx["event"].id, "show_shortcuts_mobile", False, ctx):
        origin_id = request.GET.get("origin", "")
        should_open = False
        if origin_id:
            should_open = str(ctx["run"].id) != origin_id
        ctx["open_shortcuts"] = should_open

    _check_intro_driver(request, ctx)

    return render(request, "larpmanager/manage/orga.html", ctx)


def _orga_actions_priorities(request: HttpRequest, ctx: dict) -> None:
    """Determine priority actions for event organizers based on event state.

    Analyzes event features and configuration to suggest next steps in
    event setup workflow, checking for missing required configurations.
    Populates ctx with priority actions and regular actions for the organizer dashboard.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary containing 'event' and 'run' keys. Will be updated
             with priority and action lists

    Side effects:
        Modifies ctx by calling _add_priority() and _add_action() which populate
        action lists for the organizer dashboard
    """
    # Load feature flags to determine which checks to perform
    features = get_event_features(ctx["event"].id)

    # Check if character feature is properly configured
    if "character" in features:
        # Prompt to create first character if none exist
        if not Character.objects.filter(event=ctx["event"]).count():
            _add_priority(
                ctx,
                _("Create the first character of the event"),
                "orga_characters",
            )
    # Check for feature dependencies on character feature
    elif set(features) & {"faction", "plot", "casting", "user_character", "px", "custom_character", "questbuilder"}:
        _add_priority(
            ctx,
            _("Some activated features need the 'Character' feature, but it isn't active"),
            "orga_features",
        )

    # Check if user_character feature needs configuration
    if "user_character" in features and get_event_config(ctx["event"].id, "user_character_max", "", ctx) == "":
        _add_priority(
            ctx,
            _("Set up the configuration for the creation or editing of characters by the participants"),
            "orga_character",
            "config/user_character",
        )

    # Check for features that depend on token_credit
    if "token_credit" not in features and set(features) & {"expense", "refund", "collection"}:
        _add_priority(
            ctx,
            _("Some activated features need the 'Token / Credit' feature, but it isn't active"),
            "orga_features",
        )

    # Check for pending character approvals
    char_proposed = ctx["event"].get_elements(Character).filter(status=CharacterStatus.PROPOSED).count()
    if char_proposed:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> characters to approve") % {"number": char_proposed},
            "orga_characters",
        )

    # Check for pending expense approvals (if not disabled for organizers)
    if not get_assoc_config(ctx["event"].assoc_id, "expense_disable_orga", False):
        expenses_approve = AccountingItemExpense.objects.filter(run=ctx["run"], is_approved=False).count()
        if expenses_approve:
            _add_action(
                ctx,
                _("There are <b>%(number)s</b> expenses to approve") % {"number": expenses_approve},
                "orga_expenses",
            )

    # Check for pending payment approvals
    payments_approve = PaymentInvoice.objects.filter(reg__run=ctx["run"], status=PaymentStatus.SUBMITTED).count()
    if payments_approve:
        _add_action(
            ctx,
            _("There are <b>%(number)s</b> payments to approve") % {"number": payments_approve},
            "orga_invoices",
        )

    # Check for incomplete registration form questions (missing options)
    empty_reg_questions = (
        ctx["event"]
        .get_elements(RegistrationQuestion)
        .filter(typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE])
        .annotate(quest_count=Count("options"))
        .filter(quest_count=0)
    )
    if empty_reg_questions.count():
        _add_priority(
            ctx,
            _("There are registration questions without options: %(list)s")
            % {"list": ", ".join([obj.name for obj in empty_reg_questions])},
            "orga_registration_form",
        )

    # Check for incomplete writing form questions (missing options)
    empty_char_questions = (
        ctx["event"]
        .get_elements(WritingQuestion)
        .filter(typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE])
        .annotate(quest_count=Count("options"))
        .filter(quest_count=0)
    )
    if empty_char_questions.count():
        _add_priority(
            ctx,
            _("There are writing fields without options: %(list)s")
            % {"list": ", ".join([obj.name for obj in empty_char_questions])},
            "orga_character_form",
        )

    # Delegate to sub-functions for additional action checks
    _orga_user_actions(ctx, features, request)

    _orga_reg_acc_actions(ctx, features)

    _orga_reg_actions(ctx, features)

    _orga_px_actions(ctx, features)

    _orga_casting_actions(ctx, features)


def _orga_user_actions(ctx, features, request):
    if "help" in features:
        _closed_q, open_q = _get_help_questions(ctx, request)
        if open_q:
            _add_action(
                ctx,
                _("There are <b>%(number)s</b> questions to answer") % {"number": len(open_q)},
                "exe_questions",
            )


def _orga_casting_actions(ctx, features):
    """Add priority actions related to casting and quest builder setup.

    Checks for missing casting configurations and quest/trait relationships,
    adding appropriate priority suggestions for event organizers.
    """
    if "casting" in features:
        if not get_event_config(ctx["event"].id, "casting_min", 0, ctx):
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


def _orga_px_actions(ctx: dict, features: dict) -> None:
    """Add priority actions for experience points system setup.

    Checks for missing PX configurations, ability types, and deliveries,
    adding appropriate priority suggestions for event organizers.

    Args:
        ctx: Context dictionary containing event and other relevant data
        features: Dictionary of enabled features for the current context

    Returns:
        None: Function modifies ctx in place by adding priority suggestions
    """
    # Early return if PX feature is not enabled
    if "px" not in features:
        return

    # Check if experience points configuration is missing
    if not get_event_config(ctx["event"].id, "px_start", 0, ctx):
        _add_priority(
            ctx,
            _("Set the experience points configuration"),
            "orga_px_abilities",
            "config/px",
        )

    # Verify that ability types have been set up
    if not ctx["event"].get_elements(AbilityTypePx).count():
        _add_priority(
            ctx,
            _("Set up ability types"),
            "orga_px_ability_types",
        )

    # Find ability types that don't have any associated abilities
    unused_ability_types = (
        ctx["event"].get_elements(AbilityTypePx).annotate(ability_count=Count("abilities")).filter(ability_count=0)
    )
    # Add priority if there are unused ability types
    if unused_ability_types.count():
        _add_priority(
            ctx,
            _("There are ability types without abilities: %(list)s")
            % {"list": ", ".join([ability.name for ability in unused_ability_types])},
            "orga_px_abilities",
        )

    # Check if delivery methods for experience points are configured
    if not ctx["event"].get_elements(DeliveryPx).count():
        _add_priority(
            ctx,
            _("Set up delivery for experience points"),
            "orga_px_deliveries",
        )


def _orga_reg_acc_actions(ctx: dict, features: list[str]) -> None:
    """Add priority actions related to registration and accounting setup.

    Checks for required configurations when certain features are enabled,
    such as installments, quotas, and accounting systems for events.

    Args:
        ctx: Context dictionary containing event and other data
        features: List of enabled feature names

    Returns:
        None: Modifies ctx in place by adding priority actions
    """
    # Check for conflicting installment features
    if "reg_installments" in features and "reg_quotas" in features:
        _add_priority(
            ctx,
            _(
                "You have activated both fixed and dynamic installments; they are not meant to be used together, "
                "deactivate one of the two in the features management panel"
            ),
            "orga_features",
        )

    # Handle dynamic installments (quotas) setup
    if "reg_quotas" in features and not ctx["event"].get_elements(RegistrationQuota).count():
        _add_priority(
            ctx,
            _("Set up dynamic installments"),
            "orga_registration_quotas",
        )

    # Handle fixed installments feature
    if "reg_installments" in features:
        # Check if installments are configured
        if not ctx["event"].get_elements(RegistrationInstallment).count():
            _add_priority(
                ctx,
                _("Set up fixed installments"),
                "orga_registration_installments",
            )
        else:
            # Validate installment configuration - check for conflicting deadline settings
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
                    % {"list": ", ".join([str(obj) for obj in both_set])},
                    "orga_registration_installments",
                )

            # Check for missing final installments (amount = 0)
            missing_final = ctx["event"].get_elements(RegistrationTicket).exclude(installments__amount=0)
            if missing_final:
                _add_priority(
                    ctx,
                    _("You have some tickets without a final installment (with 0 amount): %(list)s")
                    % {"list": ", ".join([obj.name for obj in missing_final])},
                    "orga_registration_installments",
                )

    # Handle reduced tickets feature configuration
    if "reduced" in features:
        if not get_event_config(ctx["event"].id, "reduced_ratio", 0, ctx):
            _add_priority(
                ctx,
                _("Set up configuration for Patron and Reduced tickets"),
                "orga_registration_tickets",
                "config/reduced",
            )


def _orga_reg_actions(ctx, features):
    """Add priority actions for registration management setup.

    Checks registration status, required tickets, and registration features
    to provide guidance for event organizers.
    """
    if "registration_open" in features and not ctx["run"].registration_open:
        _add_priority(
            ctx,
            _("Set up a value for registration opening date"),
            "orga_event",
        )

    if "registration_secret" in features and not ctx["run"].registration_secret:
        _add_priority(
            ctx,
            _("Set up a value for registration secret link"),
            "orga_event",
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
            if get_event_config(ctx["event"].id, "custom_character_" + field, False, ctx):
                configured = True

        if not configured:
            _add_priority(
                ctx,
                _("Set up character customization configuration"),
                "orga_characters",
                "config/custom_character",
            )


def _orga_suggestions(ctx):
    """Add priority suggestions for event organization.

    Args:
        ctx: Context dictionary to add suggestions to
    """
    priorities = {
        "orga_quick": _("Quickly configure your events's most important settings"),
        "orga_registration_tickets": _("Set up the tickets that users can select during registration"),
    }

    for perm, text in priorities.items():
        if get_event_config(ctx["event"].id, f"{perm}_suggestion", False, ctx):
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
        if get_event_config(ctx["event"].id, f"{perm}_suggestion", False, ctx):
            continue
        _add_suggestion(ctx, text, perm)


def _add_item(ctx, list_name, text, perm, link):
    """Add item to specific list in management context.

    Args:
        ctx: Context dictionary to modify
        list_name: Name of list to add item to
        text: Item message text
        perm: Permission key
        link: Optional custom link
    """
    if list_name not in ctx:
        ctx[list_name] = []

    ctx[list_name].append((text, perm, link))


def _add_priority(ctx, text, perm, link=None):
    """Add priority item to management dashboard.

    Args:
        ctx: Context dictionary to modify
        text: Priority message text
        perm: Permission key for the action
        link: Optional custom link
    """
    _add_item(ctx, "priorities_list", text, perm, link)


def _add_action(ctx, text, perm, link=None):
    """Add action item to management dashboard.

    Args:
        ctx: Context dictionary to modify
        text: Action message text
        perm: Permission key for the action
        link: Optional custom link
    """
    _add_item(ctx, "actions_list", text, perm, link)


def _add_suggestion(ctx, text, perm, link=None):
    """Add suggestion item to management dashboard.

    Args:
        ctx: Context dictionary to modify
        text: Suggestion message text
        perm: Permission key for the action
        link: Optional custom link
    """
    _add_item(ctx, "suggestions_list", text, perm, link)


def _has_permission(request, ctx, perm):
    """Check if user has required permission for action.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary
        perm: Permission string to check

    Returns:
        bool: True if user has permission
    """
    if perm.startswith("exe"):
        return has_assoc_permission(request, ctx, perm)
    return has_event_permission(request, ctx, ctx["event"].slug, perm)


def _get_href(ctx, perm, name, custom_link):
    """Generate href and title for management dashboard links.

    Args:
        ctx: Context dictionary
        perm: Permission string
        name: Display name
        custom_link: Optional custom link suffix

    Returns:
        tuple: (title, href) for dashboard link
    """
    if custom_link:
        return _("Configuration"), _get_perm_link(ctx, perm, "manage") + custom_link

    return _(name), _get_perm_link(ctx, perm, perm)


def _get_perm_link(ctx, perm, view):
    if perm.startswith("exe"):
        return reverse(view)
    return reverse(view, args=[ctx["run"].get_slug()])


def _compile(request, ctx):
    """Compile management dashboard with suggestions, actions, and priorities.

    Processes and organizes management content sections, handling empty states
    and providing appropriate user messaging.
    """
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


def orga_close_suggestion(request, s, perm):
    ctx = check_event_permission(request, s, perm)
    set_suggestion(ctx, perm)
    return redirect("manage", s=s)


def _check_intro_driver(request, ctx):
    member = request.user.member
    config_name = "intro_driver"
    if member.get_config(config_name, False):
        return

    ctx["intro_driver"] = True


def orga_redirect(request, s: str, n: int, p: str = None) -> HttpResponsePermanentRedirect:
    """
    Optimized redirect from /slug/number/path to /slug-number/path format.

    Redirects URLs like /event-slug/2/some/path to /event-slug-2/some/path.
    Uses permanent redirect (301) for better SEO and caching.

    Args:
        request: Django HTTP request object (not used in redirect logic)
        s: Event slug identifier
        n: Run number for the event
        p: Additional path components, defaults to None

    Returns:
        HttpResponsePermanentRedirect: 301 redirect to normalized URL format
    """
    # Initialize path components list with base slug
    path_parts = [s]

    # Only add suffix for run numbers > 1 to keep URLs clean
    if n > 1:
        path_parts.append(f"-{n}")

    # Join slug and number components, add trailing slash
    base_path = "".join(path_parts) + "/"

    # Append additional path if provided (p already includes leading slash if needed)
    if p:
        base_path += p

    # Return permanent redirect (301) for better caching and SEO
    return HttpResponsePermanentRedirect("/" + base_path)


class WhatWouldYouLikeForm(Form):
    def __init__(self, *args, **kwargs):
        self.ctx = kwargs.pop("ctx")
        super().__init__(*args, **kwargs)

        choices = []
        event_priority_choices = []
        regular_choices = []

        # Add to choices all links in the current interface
        for type_pms in ["event_pms", "assoc_pms"]:
            all_pms = self.ctx.get(type_pms, {})
            for _mod, list in all_pms.items():
                for pms in list:
                    choice_tuple = (f"{type_pms}|{pms['slug']}", _(pms["name"]) + " - " + _(pms["descr"]))
                    # Prioritize permissions with slug starting with "event"
                    if pms["slug"].startswith("event"):
                        event_priority_choices.append(choice_tuple)
                    else:
                        regular_choices.append(choice_tuple)

        # Add prioritized event choices first
        choices.extend(event_priority_choices)
        choices.extend(regular_choices)

        # Add to choices all dashboard that can be accessed by this user
        all_runs = self.ctx.get("open_runs", {})
        all_runs.update(self.ctx.get("past_runs", {}))
        for _rid, run in all_runs.items():
            choices.append((f"manage_orga|{run['slug']}", run["s"] + " - " + _("Dashboard")))

        if self.ctx.get("assoc_role", None):
            choices.append(("manage_exe|", self.ctx.get("name") + " - " + _("Dashboard")))

        # Add to choices all tutorials
        ix = get_or_create_index_tutorial(TUTORIAL_INDEX)
        with ix.searcher() as searcher:
            for doc in searcher.all_stored_fields():
                slug = doc.get("slug", "")
                title = doc.get("title", "")
                section_title = doc.get("section_title", "")
                content = doc.get("content", "")

                if slugify(title) != slugify(section_title):
                    title += " - " + section_title
                choices.append((f"tutorial|{slug}#{slugify(section_title)}", f"{title} [TUTORIAL] - {content[:50]}"))

        # Add to choices all guides
        ix = get_or_create_index_tutorial(GUIDE_INDEX)
        with ix.searcher() as searcher:
            for doc in searcher.all_stored_fields():
                slug = doc.get("slug", "")
                title = doc.get("title", "")
                content = doc.get("content", "")
                choices.append((f"guide|{slug}", f"{title} [GUIDE] - {content[:50]}"))

        self.fields["wwyltd"] = ChoiceField(choices=choices, widget=Select2Widget)


def what_would_you_like(ctx, request):
    if request.POST:
        form = WhatWouldYouLikeForm(request.POST, ctx=ctx)
        if form.is_valid():
            choice = form.cleaned_data["wwyltd"]
            try:
                redirect_url = _get_choice_redirect_url(choice, ctx)
                raise RedirectError(redirect_url)
            except ValueError as err:
                messages.error(request, str(err))
                raise RedirectError(request.path) from err
    else:
        form = WhatWouldYouLikeForm(ctx=ctx)
    ctx["form"] = form


def _get_choice_redirect_url(choice, ctx):
    """Get the appropriate redirect URL based on the user's choice.

    Args:
        choice: The choice value from the form (format: "type#value")
        ctx: Context dictionary containing association and event data

    Returns:
        str: URL to redirect to

    Raises:
        ValueError: If the choice format is invalid or redirect cannot be determined
    """
    if not choice or "|" not in choice:
        raise ValueError(_("Invalid choice format"))

    choice_type, choice_value = choice.split("|", 1)

    # Handle executive dashboard (no value needed)
    if choice_type == "manage_exe":
        return reverse("manage")

    # Validate choice_value for all other types
    if not choice_value:
        raise ValueError(_("choice value not provided"))

    # Define redirect mapping
    redirect_handlers = {
        "event_pms": lambda: _handle_event_pms_redirect(choice_value, ctx),
        "assoc_pms": lambda: reverse(choice_value),
        "manage_orga": lambda: reverse("manage", args=[choice_value]),
        "tutorial": lambda: _handle_tutorial_redirect(choice_value),
        "guide": lambda: reverse("guide", args=[choice_value]),
    }

    handler = redirect_handlers.get(choice_type)
    if not handler:
        raise ValueError(_("Unknown choice type: %(type)s") % {"type": choice_type})

    return handler()


def _handle_event_pms_redirect(choice_value, ctx):
    """Handle event permissions redirect."""
    if "run" not in ctx:
        raise ValueError(_("Event context not available"))
    return reverse(choice_value, args=[ctx["run"].get_slug()])


def _handle_tutorial_redirect(choice_value):
    """Handle tutorial redirect with optional section anchor."""
    if "#" in choice_value:
        tutorial_slug, section_slug = choice_value.split("#", 1)
        return reverse("tutorial", args=[tutorial_slug]) + f"#{section_slug}"
    return reverse("tutorial", args=[choice_value])
