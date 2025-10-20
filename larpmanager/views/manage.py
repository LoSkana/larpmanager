from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.balance import assoc_accounting, get_run_accounting
from larpmanager.cache.config import get_assoc_config
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
from larpmanager.utils.registration import registration_available
from larpmanager.utils.text import get_assoc_text


@login_required
def manage(request: HttpRequest, s: str | None = None) -> HttpResponse:
    """Main management dashboard routing.

    Routes to either executive management or organizer management
    based on whether an event slug is provided.

    Args:
        request: Django HTTP request object (must be authenticated)
        s: Optional event slug for organizer management

    Returns:
        HttpResponse: Redirect to home or appropriate management view
    """
    # Check if user has access to any association
    if request.assoc["id"] == 0:
        return redirect("home")

    # Route based on presence of event slug
    if s:
        # Event-specific organizer management
        return _orga_manage(request, s)
    else:
        # Executive management for entire association
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
    if not run.registration_open and run.event.get_config("pre_register_active", False):
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


def _exe_suggestions(ctx: dict) -> None:
    """Add priority tasks and suggestions to the executive management context.

    This function provides contextual suggestions for executive management tasks
    that haven't been completed yet, helping guide administrators through
    platform setup and configuration.

    Args:
        ctx: Context dictionary containing association ID ('a_id') and other data
            used for rendering the executive dashboard.

    Returns:
        None: Modifies the context dictionary in-place by adding suggestions.
    """
    # Define mapping of permission keys to their descriptive suggestion texts
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

    # Iterate through each suggestion and check if it should be displayed
    for perm, text in suggestions.items():
        # Skip suggestions that have already been completed/dismissed
        if get_assoc_config(ctx["a_id"], f"{perm}_suggestion"):
            continue

        # Add the suggestion to the context for display
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


def _exe_users_actions(request: object, ctx: dict, features: set) -> None:
    """
    Process user management actions and setup tasks for executives.

    Analyzes available features and adds priority tasks or actions to the context
    based on missing configurations or pending items that require executive attention.

    Args:
        request: HTTP request object containing association data
        ctx: Context dictionary to populate with actions and priorities
        features: Set of enabled feature names for the association

    Returns:
        None: Modifies ctx dictionary in-place
    """
    # Handle membership feature configuration
    if "membership" in features:
        # Check if membership request text is configured
        if not get_assoc_text(ctx["a_id"], AssocTextType.MEMBERSHIP):
            _add_priority(ctx, _("Set up the membership request text"), "exe_membership", "texts")

        # Verify membership fee configuration exists
        if len(get_assoc_config(request.assoc["id"], "membership_fee", "")) == 0:
            _add_priority(ctx, _("Set up the membership configuration"), "exe_membership", "config/membership")

    # Handle voting feature configuration
    if "vote" in features:
        # Check if voting candidates are configured
        if not get_assoc_config(request.assoc["id"], "vote_candidates", ""):
            _add_priority(
                ctx,
                _("Set up the voting configuration"),
                "exe_config",
            )

    # Handle help/questions feature
    if "help" in features:
        # Get help questions status and check for pending items
        _closed_q, open_q = _get_help_questions(ctx, request)
        if open_q:
            # Add action for unanswered questions
            _add_action(
                ctx,
                _("There are <b>%(number)s</b> questions to answer") % {"number": len(open_q)},
                "exe_questions",
            )


def _exe_accounting_actions(request: HttpRequest, ctx: dict, features: set) -> None:
    """
    Process accounting-related setup actions for executives.

    Checks for required configurations in payment methods, organization tax,
    and VAT settings. Adds priority actions to the context when configurations
    are missing or incomplete.

    Args:
        request: HTTP request instance containing association data
        ctx: Context dictionary to populate with priority actions
        features: Set of enabled features for the association

    Returns:
        None: Function modifies ctx dictionary in-place
    """
    # Check if payment methods are configured when payment feature is enabled
    if "payment" in features:
        if not request.assoc.get("methods", ""):
            _add_priority(
                ctx,
                _("Set up payment methods"),
                "exe_methods",
            )

    # Verify organization tax configuration is set up
    if "organization_tax" in features:
        if not get_assoc_config(request.assoc["id"], "organization_tax_perc", ""):
            _add_priority(
                ctx,
                _("Set up the organization tax configuration"),
                "exe_accounting",
                "config/organization_tax",
            )

    # Check VAT configuration completeness (both ticket and options required)
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
    ctx = get_event_run(request, s)

    # Ensure run dates are set
    if not ctx["run"].start or not ctx["run"].end:
        msg = _("Last step, please complete the event setup by adding the start and end dates")
        messages.success(request, msg)
        return redirect("orga_run", s=s)

    # Ensure quick setup is complete
    if not ctx["event"].get_config("orga_quick_suggestion", False):
        msg = _(
            "Before accessing the event dashboard, please complete the quick setup by selecting "
            "the features most useful for your event"
        )
        messages.success(request, msg)
        return redirect("orga_quick", s=s)

    # Set page context
    ctx["orga_page"] = 1
    ctx["manage"] = 1

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
    if ctx["event"].get_config("show_shortcuts_mobile", False):
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
    if "user_character" in features and ctx["event"].get_config("user_character_max", "") == "":
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


def _orga_casting_actions(ctx: dict, features: list[str]) -> None:
    """Add priority actions related to casting and quest builder setup.

    Checks for missing casting configurations and quest/trait relationships,
    adding appropriate priority suggestions for event organizers.

    Args:
        ctx: Context dictionary containing event data and other view context
        features: List of feature names enabled for the current event

    Returns:
        None: Function modifies ctx in place by adding priority actions
    """
    # Check if casting feature is enabled and needs configuration
    if "casting" in features:
        if not ctx["event"].get_config("casting_min", 0):
            _add_priority(
                ctx,
                _("Set the casting options in the configuration panel"),
                "orga_casting",
                "config/casting",
            )

    # Check if questbuilder feature is enabled and needs setup
    if "questbuilder" in features:
        # Verify quest types exist for the event
        if not ctx["event"].get_elements(QuestType).count():
            _add_priority(
                ctx,
                _("Set up quest types"),
                "orga_quest_types",
            )

        # Find quest types that don't have any associated quests
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

        # Find quests that don't have any associated traits
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
        ctx: Context dictionary containing event and other data
        features: Dictionary of available features for the event

    Returns:
        None: Function modifies ctx in place by adding priority actions
    """
    # Early return if PX feature is not enabled
    if "px" not in features:
        return

    # Check if experience points are configured for the event
    if not ctx["event"].get_config("px_start", 0):
        _add_priority(
            ctx,
            _("Set the experience points configuration"),
            "orga_px_abilities",
            "config/px",
        )

    # Verify that ability types exist for the event
    if not ctx["event"].get_elements(AbilityTypePx).count():
        _add_priority(
            ctx,
            _("Set up ability types"),
            "orga_px_ability_types",
        )

    # Find ability types that have no associated abilities
    unused_ability_types = (
        ctx["event"].get_elements(AbilityTypePx).annotate(ability_count=Count("abilities")).filter(ability_count=0)
    )
    # Alert if there are unused ability types
    if unused_ability_types.count():
        _add_priority(
            ctx,
            _("There are ability types without abilities: %(list)s")
            % {"list": ", ".join([ability.name for ability in unused_ability_types])},
            "orga_px_abilities",
        )

    # Check if delivery methods are configured for experience points
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
        if not ctx["event"].get_config("reduced_ratio", 0):
            _add_priority(
                ctx,
                _("Set up configuration for Patron and Reduced tickets"),
                "orga_registration_tickets",
                "config/reduced",
            )


def _orga_reg_actions(ctx: dict, features: list[str]) -> None:
    """Add priority actions for registration management setup.

    Checks registration status, required tickets, and registration features
    to provide guidance for event organizers.

    Args:
        ctx: Context dictionary containing event and run data
        features: List of feature names enabled for the organization

    Returns:
        None: Modifies ctx in place by adding priority actions
    """
    # Check if registration opening date needs to be configured
    if "registration_open" in features and not ctx["run"].registration_open:
        _add_priority(
            ctx,
            _("Set up a value for registration opening date"),
            "orga_event",
        )

    # Check if registration secret link needs to be configured
    if "registration_secret" in features and not ctx["run"].registration_secret:
        _add_priority(
            ctx,
            _("Set up a value for registration secret link"),
            "orga_event",
        )

    # Check if external registration link needs to be configured
    if "register_link" in features and not ctx["event"].register_link:
        _add_priority(
            ctx,
            _("Set up a value for registration external link"),
            "orga_event",
        )

    # Check custom character configuration if feature is enabled
    if "custom_character" in features:
        configured = False
        # Check if any custom character fields are configured
        for field in ["pronoun", "song", "public", "private", "profile"]:
            if ctx["event"].get_config("custom_character_" + field, False):
                configured = True

        # Add priority action if no custom character fields are configured
        if not configured:
            _add_priority(
                ctx,
                _("Set up character customization configuration"),
                "orga_characters",
                "config/custom_character",
            )


def _orga_suggestions(ctx: dict) -> None:
    """Add priority suggestions for event organization.

    This function adds both priority and regular suggestions to the context based on
    event configuration settings. Priority suggestions are shown first and include
    the most important organizational tasks.

    Args:
        ctx: Context dictionary containing event information and suggestions list.
             Must contain an 'event' key with an object that has get_config method.

    Returns:
        None: Modifies the ctx dictionary in place by adding suggestions.
    """
    # Define high-priority suggestions for critical event setup tasks
    priorities = {
        "orga_quick": _("Quickly configure your events's most important settings"),
        "orga_registration_tickets": _("Set up the tickets that users can select during registration"),
    }

    # Add priority suggestions if they haven't been dismissed
    for perm, text in priorities.items():
        if ctx["event"].get_config(f"{perm}_suggestion"):
            continue
        _add_priority(ctx, text, perm)

    # Define regular suggestions for additional event configuration
    suggestions = {
        "orga_registration_form": _(
            "Define the registration form, and set up any number of registration questions and their options"
        ),
        "orga_roles": _("Grant access to event management for other users and define roles with specific permissions"),
        "orga_appearance": _("Customize the appearance of all event pages, including colors, fonts, and images"),
        "orga_features": _("Activate new features and enhance the functionality of the event"),
        "orga_config": _("Set specific values for configuration of features of the event"),
    }

    # Add regular suggestions if they haven't been dismissed
    for perm, text in suggestions.items():
        if ctx["event"].get_config(f"{perm}_suggestion"):
            continue
        _add_suggestion(ctx, text, perm)


def _add_item(ctx: dict, list_name: str, text: str, perm: str, link: str | None) -> None:
    """Add item to specific list in management context.

    Args:
        ctx: Context dictionary to modify in-place
        list_name: Name of the list to add the item to
        text: Display text for the item
        perm: Permission key required for the item
        link: Optional custom link URL for the item

    Returns:
        None: Modifies the context dictionary in-place
    """
    # Initialize list if it doesn't exist in context
    if list_name not in ctx:
        ctx[list_name] = []

    # Append new item tuple to the specified list
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


def _has_permission(request: HttpRequest, ctx: dict, perm: str) -> bool:
    """Check if user has required permission for action.

    This function determines whether a user has the necessary permissions
    to perform a specific action by checking either association-level or
    event-level permissions based on the permission string prefix.

    Args:
        request: Django HTTP request object containing user information
        ctx: Context dictionary containing event and other relevant data
        perm: Permission string to check (e.g., 'exe_view' or 'orga_edit')

    Returns:
        True if user has the required permission, False otherwise

    Note:
        Permissions starting with "exe" are checked at association level,
        all other permissions are checked at event level.
    """
    # Check if this is an association-level permission (exe prefix)
    if perm.startswith("exe"):
        return has_assoc_permission(request, ctx, perm)

    # Otherwise, check event-level permission using event slug from context
    return has_event_permission(request, ctx, ctx["event"].slug, perm)


def _get_href(ctx: dict, perm: str, name: str, custom_link: str | None) -> tuple[str, str]:
    """Generate href and title for management dashboard links.

    Creates appropriate URL links and display titles for dashboard navigation
    based on permissions and optional custom link suffixes.

    Args:
        ctx: Context dictionary containing request and navigation data
        perm: Permission string identifier for the dashboard section
        name: Display name to be used as the link title
        custom_link: Optional custom link suffix to append to base URL

    Returns:
        A tuple containing:
            - title (str): Translated display title for the link
            - href (str): Complete URL for the dashboard link
    """
    # Handle custom link configuration with standardized title
    if custom_link:
        return _("Configuration"), _get_perm_link(ctx, perm, "manage") + custom_link

    # Default case: use permission name for both title and link generation
    return _(name), _get_perm_link(ctx, perm, perm)


def _get_perm_link(ctx, perm, view):
    if perm.startswith("exe"):
        return reverse(view)
    return reverse(view, args=[ctx["run"].get_slug()])


def _compile(request: HttpRequest, ctx: dict) -> None:
    """Compile management dashboard with suggestions, actions, and priorities.

    Processes and organizes management content sections, handling empty states
    and providing appropriate user messaging. Populates context with formatted
    dashboard items including links, tutorials, and permissions.

    Args:
        request: Django HTTP request object containing user and session data
        ctx: Context dictionary to populate with dashboard sections and items

    Returns:
        None: Modifies ctx dictionary in-place, returns early if no content
    """
    # Define the main dashboard sections to process
    section_list = ["suggestions", "actions", "priorities"]
    empty = True

    # Initialize empty lists for each section and check if any content exists
    for section in section_list:
        ctx[section] = []
        if f"{section}_list" in ctx:
            empty = False

    # Early return if no content is available for any section
    if empty:
        return

    # Build cache of permission data and collect all slugs that need permission checks
    cache = {}
    perm_list = []
    for section in section_list:
        if f"{section}_list" not in ctx:
            continue

        # Extract slugs from section items and filter by permissions
        perm_list.extend([slug for _n, slug, _u in ctx[f"{section}_list"] if _has_permission(request, ctx, slug)])

    # Query both permission models to build cache of names and tutorials
    for model in (EventPermission, AssocPermission):
        queryset = model.objects.filter(slug__in=perm_list).select_related("feature")
        for slug, name, tutorial in queryset.values_list("slug", "name", "feature__tutorial"):
            cache[slug] = (name, tutorial)

    # Process each section and build final dashboard items with links and metadata
    for section in section_list:
        if f"{section}_list" not in ctx:
            continue

        # Transform raw section data into formatted dashboard items
        for text, slug, custom_link in ctx[f"{section}_list"]:
            if slug not in cache:
                continue

            # Extract cached permission data and generate appropriate links
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


def orga_redirect(request: HttpRequest, s: str, n: int, p: str = None) -> HttpResponsePermanentRedirect:
    """
    Optimized redirect from /slug/number/path to /slug-number/path format.

    Redirects URLs like /event-slug/2/some/path to /event-slug-2/some/path.
    Uses permanent redirect (301) for better SEO and caching.

    Args:
        request: Django HTTP request object (not used in redirect logic)
        s: Event slug
        n: Run number
        p: Additional path components

    Returns:
        301 redirect to normalized URL format
    """

    # Build path components efficiently starting with event slug
    path_parts = [s]

    # Only add suffix for run numbers > 1 to avoid redundant "-1" suffix
    if n > 1:
        path_parts.append(f"-{n}")

    # Join slug and number components, add trailing slash for consistency
    base_path = "".join(path_parts) + "/"

    # Append additional path if provided (p already includes leading slash if needed)
    if p:
        base_path += p

    # Use permanent redirect (301) for better caching and SEO optimization
    return HttpResponsePermanentRedirect("/" + base_path)
