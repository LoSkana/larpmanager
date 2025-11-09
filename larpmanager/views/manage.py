from datetime import datetime
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.forms import ChoiceField, Form
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_select2.forms import Select2Widget
from slugify import slugify

from larpmanager.accounting.balance import association_accounting, get_run_accounting
from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.feature import get_association_features, get_event_features
from larpmanager.cache.registration import get_reg_counts
from larpmanager.cache.role import (
    get_index_association_permissions,
    get_index_event_permissions,
    has_association_permission,
    has_event_permission,
)
from larpmanager.cache.wwyltd import get_features_cache, get_guides_cache, get_tutorials_cache
from larpmanager.models.access import AssociationPermission, EventPermission
from larpmanager.models.accounting import (
    AccountingItemExpense,
    PaymentInvoice,
    PaymentStatus,
    RefundRequest,
    RefundStatus,
)
from larpmanager.models.association import AssociationTextType
from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.event import DevelopStatus, Event, Run
from larpmanager.models.experience import AbilityTypePx, DeliveryPx
from larpmanager.models.form import BaseQuestionType, RegistrationQuestion, WritingQuestion
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import RegistrationInstallment, RegistrationQuota, RegistrationTicket
from larpmanager.models.writing import Character, CharacterStatus
from larpmanager.utils.base import check_association_context, check_event_context, get_context, get_event_context
from larpmanager.utils.common import _get_help_questions, format_datetime
from larpmanager.utils.edit import set_suggestion
from larpmanager.utils.exceptions import RedirectError
from larpmanager.utils.registration import registration_available


@login_required
def manage(request, event_slug=None):
    """Route to the appropriate management dashboard.

    Routes to either executive management or organizer management
    based on whether an event slug is provided.

    Args:
        request: Django HTTP request object (must be authenticated)
        event_slug: Optional event slug for organizer management

    Returns:
        HttpResponse: Redirect to home or appropriate management view

    """
    if request.association["id"] == 0:
        return redirect("home")

    if event_slug:
        return _orga_manage(request, event_slug)
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
    current_datetime = datetime.today()
    if "registration_open" in features:
        if not run.registration_open:
            return "not_set", None
        if run.registration_open > current_datetime:
            return "future", run.registration_open

    # Check registration availability
    run.status = {}
    registration_available(run, features)
    registration_status = run.status

    # Determine status based on availability
    status_priority = ["primary", "filler", "waiting"]
    for status_type in status_priority:
        if status_type in registration_status:
            return status_type, registration_status.get("count")

    return "closed", None


def _get_registration_status(run_instance) -> str:
    """Get human-readable registration status for a run.

    This function retrieves the registration status code and returns a localized,
    user-friendly message describing the current registration state for the given run.

    Args:
        run_instance: Run instance to check status for. Expected to have registration-related
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
    status_code, opening_datetime = _get_registration_status_code(run_instance)

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
        if opening_datetime:
            formatted_opening_date = opening_datetime.strftime(format_datetime)
            return _("Registrations opening at: %(date)s") % {"date": formatted_opening_date}
        # Fallback when datetime is not available
        return _("Registrations opening not set")

    # Return the appropriate status message or default to closed
    return status_messages.get(status_code, _("Registration closed"))


def _exe_manage(request: HttpRequest) -> HttpResponse:
    """Display executive management dashboard.

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
    context = get_context(request)
    get_index_association_permissions(context, request, context["association_id"])
    context["exe_page"] = 1
    context["manage"] = 1

    # Check what would you like form
    what_would_you_like(context, request)

    # Get available features for this association
    features = get_association_features(context["association_id"])

    # Check if association has any events
    context["event_counts"] = Event.objects.filter(association_id=context["association_id"]).count()

    # Redirect to event creation if no events exist and feature is available
    if not context["event_counts"] and "exe_events" in features:
        welcome_message = (
            _("Welcome")
            + "! "
            + _("You don't have any events yet")
            + ". "
            + _("Please create your first event to get started")
            + "!"
        )
        messages.success(request, welcome_message)
        return redirect("exe_events_edit", num=0)

    # Redirect to quick setup if not completed
    if not get_association_config(context["association_id"], "exe_quick_suggestion", False, context=context):
        setup_message = _(
            "Before accessing the organization dashboard, please complete the quick setup by selecting "
            "the features most useful for your organization"
        )
        messages.success(request, setup_message)
        return redirect("exe_quick")

    # Get ongoing runs (events in START or SHOW development status)
    ongoing_runs_queryset = Run.objects.filter(
        event__association_id=context["association_id"], development__in=[DevelopStatus.START, DevelopStatus.SHOW]
    )
    context["ongoing_runs"] = ongoing_runs_queryset.select_related("event").order_by("end")

    # Add registration status and counts for each ongoing run
    for run in context["ongoing_runs"]:
        run.registration_status = _get_registration_status(run)
        run.counts = get_reg_counts(run)

    # Add accounting information if user has permission
    if has_association_permission(request, context, "exe_accounting"):
        association_accounting(context)

    # Suggest creating an event if no runs are active
    if not context["ongoing_runs"]:
        _add_priority(
            context,
            _("No events are present, create one"),
            "exe_events",
        )

    # Add dashboard actions and suggestions
    _exe_actions(request, context, features)
    _exe_suggestions(context)

    # Compile final context and check for intro driver
    _compile(request, context)
    _check_intro_driver(request, context)

    return render(request, "larpmanager/manage/exe.html", context)


def _exe_suggestions(context):
    """Add priority tasks and suggestions to the executive management context.

    Args:
        context: Context dictionary containing association ID and other data

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

    for permission_key, suggestion_text in suggestions.items():
        if get_association_config(context["association_id"], f"{permission_key}_suggestion", context=context):
            continue
        _add_suggestion(context, suggestion_text, permission_key)


def _exe_actions(request, context: dict, association_features: dict = None) -> None:
    """Determine available executive actions based on association features.

    Adds action items to the management dashboard based on user permissions
    and association configuration settings.

    Args:
        request: HTTP request object
        context: Context dictionary containing association ID and other data
        association_features: Dictionary of association features, defaults to None

    Returns:
        None: Modifies context in place by adding action items

    """
    # Get association features if not provided
    if not association_features:
        association_features = get_association_features(context["association_id"])

    # Check for runs that should be concluded
    runs_to_conclude = Run.objects.filter(
        event__association_id=context["association_id"],
        development__in=[DevelopStatus.START, DevelopStatus.SHOW],
        end__lt=datetime.today(),
    ).values_list("search", flat=True)

    # Add action for past runs still open
    if runs_to_conclude:
        _add_action(
            context,
            _(
                "There are past runs still open: <b>%(list)s</b>. Once all tasks (accounting, etc.) are finished, mark them as completed"
            )
            % {"list": ", ".join(runs_to_conclude)},
            "exe_events",
        )

    # Check for pending expense approvals
    pending_expenses_count = AccountingItemExpense.objects.filter(
        run__event__association_id=context["association_id"], is_approved=False
    ).count()
    if pending_expenses_count:
        _add_action(
            context,
            _("There are <b>%(number)s</b> expenses to approve") % {"number": pending_expenses_count},
            "exe_expenses",
        )

    # Check for pending payment approvals
    pending_payments_count = PaymentInvoice.objects.filter(
        association_id=context["association_id"], status=PaymentStatus.SUBMITTED
    ).count()
    if pending_payments_count:
        _add_action(
            context,
            _("There are <b>%(number)s</b> payments to approve") % {"number": pending_payments_count},
            "exe_invoices",
        )

    # Check for pending refund approvals
    pending_refunds_count = RefundRequest.objects.filter(
        association_id=context["association_id"], status=RefundStatus.REQUEST
    ).count()
    if pending_refunds_count:
        _add_action(
            context,
            _("There are <b>%(number)s</b> refunds to deliver") % {"number": pending_refunds_count},
            "exe_refunds",
        )

    # Check for pending member approvals
    pending_members_count = Membership.objects.filter(
        association_id=context["association_id"], status=MembershipStatus.SUBMITTED
    ).count()
    if pending_members_count:
        _add_action(
            context,
            _("There are <b>%(number)s</b> members to approve") % {"number": pending_members_count},
            "exe_membership",
        )

    # Process accounting-specific actions
    _exe_accounting_actions(request, context, association_features)

    # Process user-specific actions
    _exe_users_actions(request, context, association_features)


def _exe_users_actions(request, context, enabled_features):
    """Process user management actions and setup tasks for executives.

    Args:
        request: HTTP request object
        association: Association instance
        context: Context dictionary to populate with actions
        enabled_features: Set of enabled features

    """
    if "membership" in enabled_features:
        if not get_association_text(context["association_id"], AssociationTextType.MEMBERSHIP):
            _add_priority(context, _("Set up the membership request text"), "exe_membership", "texts")

        if len(get_association_config(context["association_id"], "membership_fee", "", context=context)) == 0:
            _add_priority(context, _("Set up the membership configuration"), "exe_membership", "config/membership")

    if "vote" in enabled_features:
        if not get_association_config(context["association_id"], "vote_candidates", "", context=context):
            _add_priority(
                context,
                _("Set up the voting configuration"),
                "exe_config",
            )

    if "help" in enabled_features:
        closed_questions, open_questions = _get_help_questions(context, request)
        if open_questions:
            _add_action(
                context,
                _("There are <b>%(number)s</b> questions to answer") % {"number": len(open_questions)},
                "exe_questions",
            )


def _exe_accounting_actions(request, context, enabled_features):
    """Process accounting-related setup actions for executives.

    Args:
        request: request instance
        context: Context dictionary to populate with priority actions
        enabled_features: Set of enabled features for the association

    """
    if "payment" in enabled_features:
        if not context.get("methods", ""):
            _add_priority(
                context,
                _("Set up payment methods"),
                "exe_methods",
            )

    if "organization_tax" in enabled_features:
        if not get_association_config(context["association_id"], "organization_tax_perc", "", context=context):
            _add_priority(
                context,
                _("Set up the organization tax configuration"),
                "exe_accounting",
                "config/organization_tax",
            )

    if "vat" in enabled_features:
        vat_ticket = get_association_config(context["association_id"], "vat_ticket", "", context=context)
        vat_options = get_association_config(context["association_id"], "vat_options", "", context=context)
        if not vat_ticket or not vat_options:
            _add_priority(
                context,
                _("Set up the taxes configuration"),
                "exe_accounting",
                "config/vat",
            )


def _orga_manage(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Event organizer management dashboard view.

    Args:
        request: HTTP request
        event_slug: Event slug

    Returns:
        Rendered dashboard

    """
    # Set page context
    context = get_event_context(request, event_slug)
    context["orga_page"] = 1
    context["manage"] = 1

    # Check what would you like form
    what_would_you_like(context, request)

    # Ensure run dates are set
    if not context["run"].start or not context["run"].end:
        message = _("Last step, please complete the event setup by adding the start and end dates")
        messages.success(request, message)
        return redirect("orga_run", event_slug=event_slug)

    # Ensure quick setup is complete
    if not get_event_config(context["event"].id, "orga_quick_suggestion", False, context=context):
        message = _(
            "Before accessing the event dashboard, please complete the quick setup by selecting "
            "the features most useful for your event"
        )
        messages.success(request, message)
        return redirect("orga_quick", event_slug=event_slug)

    # Load permissions and navigation
    get_index_event_permissions(request, context, event_slug)
    if get_association_config(context["association_id"], "interface_admin_links", False, context=context):
        get_index_association_permissions(context, request, context["association_id"], check=False)

    # Load registration status
    context["registration_status"] = _get_registration_status(context["run"])

    # Load registration counts if permitted
    if has_event_permission(request, context, event_slug, "orga_registrations"):
        context["counts"] = get_reg_counts(context["run"])
        context["reg_counts"] = {}
        for tier in ["player", "staff", "wait", "fill", "seller", "npc", "collaborator"]:
            count_key = f"count_{tier}"
            if count_key in context["counts"]:
                context["reg_counts"][_(tier.capitalize())] = context["counts"][count_key]

    # Load accounting if permitted
    if has_event_permission(request, context, event_slug, "orga_accounting"):
        context["dc"] = get_run_accounting(context["run"], context, perform_update=False)

    # Build action lists
    _exe_actions(request, context)
    if "actions_list" in context:
        del context["actions_list"]

    _orga_actions_priorities(request, context)
    _orga_suggestions(context)
    _compile(request, context)

    # Mobile shortcuts handling
    if get_event_config(context["event"].id, "show_shortcuts_mobile", False, context=context):
        origin_id = request.GET.get("origin", "")
        should_open_shortcuts = False
        if origin_id:
            should_open_shortcuts = str(context["run"].id) != origin_id
        context["open_shortcuts"] = should_open_shortcuts

    _check_intro_driver(request, context)

    return render(request, "larpmanager/manage/orga.html", context)


def _orga_actions_priorities(request: HttpRequest, context: dict) -> None:
    """Determine priority actions for event organizers based on event state.

    Analyzes event features and configuration to suggest next steps in
    event setup workflow, checking for missing required configurations.
    Populates context with priority actions and regular actions for the organizer dashboard.

    Args:
        request: Django HTTP request object
        context: Context dictionary containing 'event' and 'run' keys. Will be updated
             with priority and action lists

    Side effects:
        Modifies context by calling _add_priority() and _add_action() which populate
        action lists for the organizer dashboard

    """
    # Load feature flags to determine which checks to perform
    enabled_features = get_event_features(context["event"].id)

    # Check if character feature is properly configured
    if "character" in enabled_features:
        # Prompt to create first character if none exist
        if not Character.objects.filter(event=context["event"]).count():
            _add_priority(
                context,
                _("Create the first character of the event"),
                "orga_characters",
            )
    # Check for feature dependencies on character feature
    elif set(enabled_features) & {
        "faction",
        "plot",
        "casting",
        "user_character",
        "px",
        "custom_character",
        "questbuilder",
    }:
        _add_priority(
            context,
            _("Some activated features need the 'Character' feature, but it isn't active"),
            "orga_features",
        )

    # Check if user_character feature needs configuration
    if (
        "user_character" in enabled_features
        and get_event_config(context["event"].id, "user_character_max", "", context=context) == ""
    ):
        _add_priority(
            context,
            _("Set up the configuration for the creation or editing of characters by the participants"),
            "orga_character",
            "config/user_character",
        )

    # Check for features that depend on token_credit
    if "token_credit" not in enabled_features and set(enabled_features) & {"expense", "refund", "collection"}:
        _add_priority(
            context,
            _("Some activated features need the 'Token / Credit' feature, but it isn't active"),
            "orga_features",
        )

    # Check for pending character approvals
    proposed_characters_count = context["event"].get_elements(Character).filter(status=CharacterStatus.PROPOSED).count()
    if proposed_characters_count:
        _add_action(
            context,
            _("There are <b>%(number)s</b> characters to approve") % {"number": proposed_characters_count},
            "orga_characters",
        )

    # Check for pending expense approvals (if not disabled for organizers)
    if not get_association_config(context["event"].association_id, "expense_disable_orga", False, context=context):
        pending_expenses_count = AccountingItemExpense.objects.filter(run=context["run"], is_approved=False).count()
        if pending_expenses_count:
            _add_action(
                context,
                _("There are <b>%(number)s</b> expenses to approve") % {"number": pending_expenses_count},
                "orga_expenses",
            )

    # Check for pending payment approvals
    pending_payments_count = PaymentInvoice.objects.filter(
        reg__run=context["run"], status=PaymentStatus.SUBMITTED
    ).count()
    if pending_payments_count:
        _add_action(
            context,
            _("There are <b>%(number)s</b> payments to approve") % {"number": pending_payments_count},
            "orga_invoices",
        )

    # Check for incomplete registration form questions (missing options)
    registration_questions_without_options = (
        context["event"]
        .get_elements(RegistrationQuestion)
        .filter(typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE])
        .annotate(quest_count=Count("options"))
        .filter(quest_count=0)
    )
    if registration_questions_without_options.count():
        _add_priority(
            context,
            _("There are registration questions without options: %(list)s")
            % {"list": ", ".join([question.name for question in registration_questions_without_options])},
            "orga_registration_form",
        )

    # Check for incomplete writing form questions (missing options)
    writing_questions_without_options = (
        context["event"]
        .get_elements(WritingQuestion)
        .filter(typ__in=[BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE])
        .annotate(quest_count=Count("options"))
        .filter(quest_count=0)
    )
    if writing_questions_without_options.count():
        _add_priority(
            context,
            _("There are writing fields without options: %(list)s")
            % {"list": ", ".join([question.name for question in writing_questions_without_options])},
            "orga_character_form",
        )

    # Delegate to sub-functions for additional action checks
    _orga_user_actions(context, enabled_features, request)

    _orga_reg_acc_actions(context, enabled_features)

    _orga_reg_actions(context, enabled_features)

    _orga_px_actions(context, enabled_features)

    _orga_casting_actions(context, enabled_features)


def _orga_user_actions(
    context: dict[str, Any],
    features: list[str],
    request: HttpRequest,
) -> None:
    """Add action to context if there are unanswered help questions.

    Args:
        context: Template context dictionary to update with actions.
        features: List of enabled feature names for the organization.
        request: The current HTTP request object.

    """
    # Check if help feature is enabled
    if "help" in features:
        _closed_questions, open_questions = _get_help_questions(context, request)

        # Add action notification if there are open questions
        if open_questions:
            _add_action(
                context,
                _("There are <b>%(number)s</b> questions to answer") % {"number": len(open_questions)},
                "exe_questions",
            )


def _orga_casting_actions(context, enabled_features):
    """Add priority actions related to casting and quest builder setup.

    Checks for missing casting configurations and quest/trait relationships,
    adding appropriate priority suggestions for event organizers.
    """
    if "casting" in enabled_features:
        if not get_event_config(context["event"].id, "casting_min", 0, context=context):
            _add_priority(
                context,
                _("Set the casting options in the configuration panel"),
                "orga_casting",
                "config/casting",
            )

    if "questbuilder" in enabled_features:
        if not context["event"].get_elements(QuestType).count():
            _add_priority(
                context,
                _("Set up quest types"),
                "orga_quest_types",
            )

        unused_quest_types = (
            context["event"].get_elements(QuestType).annotate(quest_count=Count("quests")).filter(quest_count=0)
        )
        if unused_quest_types.count():
            _add_priority(
                context,
                _("There are quest types without quests: %(list)s")
                % {"list": ", ".join([quest_type.name for quest_type in unused_quest_types])},
                "orga_quests",
            )

        unused_quests = context["event"].get_elements(Quest).annotate(trait_count=Count("traits")).filter(trait_count=0)
        if unused_quests.count():
            _add_priority(
                context,
                _("There are quests without traits: %(list)s")
                % {"list": ", ".join([quest.name for quest in unused_quests])},
                "orga_traits",
            )


def _orga_px_actions(context: dict, enabled_features: dict) -> None:
    """Add priority actions for experience points system setup.

    Checks for missing PX configurations, ability types, and deliveries,
    adding appropriate priority suggestions for event organizers.

    Args:
        context: Context dictionary containing event and other relevant data
        enabled_features: Dictionary of enabled features for the current context

    Returns:
        None: Function modifies context in place by adding priority suggestions

    """
    # Early return if PX feature is not enabled
    if "px" not in enabled_features:
        return

    # Check if experience points configuration is missing
    if not get_event_config(context["event"].id, "px_start", 0, context=context):
        _add_priority(
            context,
            _("Set the experience points configuration"),
            "orga_px_abilities",
            "config/px",
        )

    # Verify that ability types have been set up
    if not context["event"].get_elements(AbilityTypePx).count():
        _add_priority(
            context,
            _("Set up ability types"),
            "orga_px_ability_types",
        )

    # Find ability types that don't have any associated abilities
    ability_types_without_abilities = (
        context["event"].get_elements(AbilityTypePx).annotate(ability_count=Count("abilities")).filter(ability_count=0)
    )
    # Add priority if there are unused ability types
    if ability_types_without_abilities.count():
        _add_priority(
            context,
            _("There are ability types without abilities: %(list)s")
            % {"list": ", ".join([ability_type.name for ability_type in ability_types_without_abilities])},
            "orga_px_abilities",
        )

    # Check if delivery methods for experience points are configured
    if not context["event"].get_elements(DeliveryPx).count():
        _add_priority(
            context,
            _("Set up delivery for experience points"),
            "orga_px_deliveries",
        )


def _orga_reg_acc_actions(context: dict, enabled_features: list[str]) -> None:
    """Add priority actions related to registration and accounting setup.

    Checks for required configurations when certain features are enabled,
    such as installments, quotas, and accounting systems for events.

    Args:
        context: Context dictionary containing event and other data
        enabled_features: List of enabled feature names

    Returns:
        None: Modifies context in place by adding priority actions

    """
    # Check for conflicting installment features
    if "reg_installments" in enabled_features and "reg_quotas" in enabled_features:
        _add_priority(
            context,
            _(
                "You have activated both fixed and dynamic installments; they are not meant to be used together, "
                "deactivate one of the two in the features management panel"
            ),
            "orga_features",
        )

    # Handle dynamic installments (quotas) setup
    if "reg_quotas" in enabled_features and not context["event"].get_elements(RegistrationQuota).count():
        _add_priority(
            context,
            _("Set up dynamic installments"),
            "orga_registration_quotas",
        )

    # Handle fixed installments feature
    if "reg_installments" in enabled_features:
        # Check if installments are configured
        if not context["event"].get_elements(RegistrationInstallment).count():
            _add_priority(
                context,
                _("Set up fixed installments"),
                "orga_registration_installments",
            )
        else:
            # Validate installment configuration - check for conflicting deadline settings
            installments_with_both_deadlines = (
                context["event"]
                .get_elements(RegistrationInstallment)
                .filter(date_deadline__isnull=False, days_deadline__isnull=False)
            )
            if installments_with_both_deadlines:
                _add_priority(
                    context,
                    _(
                        "You have some fixed installments with both date and days set, but those values cannot be set at the same time: %(list)s"
                    )
                    % {"list": ", ".join([str(installment) for installment in installments_with_both_deadlines])},
                    "orga_registration_installments",
                )

            # Check for missing final installments (amount = 0)
            tickets_missing_final_installment = (
                context["event"].get_elements(RegistrationTicket).exclude(installments__amount=0)
            )
            if tickets_missing_final_installment:
                _add_priority(
                    context,
                    _("You have some tickets without a final installment (with 0 amount): %(list)s")
                    % {"list": ", ".join([ticket.name for ticket in tickets_missing_final_installment])},
                    "orga_registration_installments",
                )

    # Handle reduced tickets feature configuration
    if "reduced" in enabled_features:
        if not get_event_config(context["event"].id, "reduced_ratio", 0, context=context):
            _add_priority(
                context,
                _("Set up configuration for Patron and Reduced tickets"),
                "orga_registration_tickets",
                "config/reduced",
            )


def _orga_reg_actions(context, enabled_features):
    """Add priority actions for registration management setup.

    Checks registration status, required tickets, and registration features
    to provide guidance for event organizers.
    """
    if "registration_open" in enabled_features and not context["run"].registration_open:
        _add_priority(
            context,
            _("Set up a value for registration opening date"),
            "orga_event",
        )

    if "registration_secret" in enabled_features and not context["run"].registration_secret:
        _add_priority(
            context,
            _("Set up a value for registration secret link"),
            "orga_event",
        )

    if "register_link" in enabled_features and not context["event"].register_link:
        _add_priority(
            context,
            _("Set up a value for registration external link"),
            "orga_event",
        )

    if "custom_character" in enabled_features:
        is_configured = False
        for field_name in ["pronoun", "song", "public", "private", "profile"]:
            if get_event_config(context["event"].id, "custom_character_" + field_name, False, context=context):
                is_configured = True

        if not is_configured:
            _add_priority(
                context,
                _("Set up character customization configuration"),
                "orga_characters",
                "config/custom_character",
            )


def _orga_suggestions(context):
    """Add priority suggestions for event organization.

    Args:
        context: Context dictionary to add suggestions to

    """
    priorities = {
        "orga_quick": _("Quickly configure your events's most important settings"),
        "orga_registration_tickets": _("Set up the tickets that users can select during registration"),
    }

    for permission_slug, suggestion_text in priorities.items():
        if get_event_config(context["event"].id, f"{permission_slug}_suggestion", False, context=context):
            continue
        _add_priority(context, suggestion_text, permission_slug)

    suggestions = {
        "orga_registration_form": _(
            "Define the registration form, and set up any number of registration questions and their options"
        ),
        "orga_roles": _("Grant access to event management for other users and define roles with specific permissions"),
        "orga_appearance": _("Customize the appearance of all event pages, including colors, fonts, and images"),
        "orga_features": _("Activate new features and enhance the functionality of the event"),
        "orga_config": _("Set specific values for configuration of features of the event"),
    }

    for permission_slug, suggestion_text in suggestions.items():
        if get_event_config(context["event"].id, f"{permission_slug}_suggestion", False, context=context):
            continue
        _add_suggestion(context, suggestion_text, permission_slug)


def _add_item(context, list_name, message_text, permission_key, custom_link):
    """Add item to specific list in management context.

    Args:
        context: Context dictionary to modify
        list_name: Name of list to add item to
        message_text: Item message text
        permission_key: Permission key
        custom_link: Optional custom link

    """
    if list_name not in context:
        context[list_name] = []

    context[list_name].append((message_text, permission_key, custom_link))


def _add_priority(context, priority_text, permission_key, custom_link=None):
    """Add priority item to management dashboard.

    Args:
        context: Context dictionary to modify
        priority_text: Priority message text
        permission_key: Permission key for the action
        custom_link: Optional custom link

    """
    _add_item(context, "priorities_list", priority_text, permission_key, custom_link)


def _add_action(context, action_text, permission_key, custom_link=None):
    """Add action item to management dashboard.

    Args:
        context: Context dictionary to modify
        action_text: Action message text
        permission_key: Permission key for the action
        custom_link: Optional custom link

    """
    _add_item(context, "actions_list", action_text, permission_key, custom_link)


def _add_suggestion(context, suggestion_text, permission_key, custom_link=None):
    """Add suggestion item to management dashboard.

    Args:
        context: Context dictionary to modify
        suggestion_text: Suggestion message text
        permission_key: Permission key for the action
        custom_link: Optional custom link

    """
    _add_item(context, "suggestions_list", suggestion_text, permission_key, custom_link)


def _has_permission(request, context, permission):
    """Check if user has required permission for action.

    Args:
        request: Django HTTP request object
        context: Context dictionary
        permission: Permission string to check

    Returns:
        bool: True if user has permission

    """
    if permission.startswith("exe"):
        return has_association_permission(request, context, permission)
    return has_event_permission(request, context, context["event"].slug, permission)


def _get_href(context, permission, display_name, custom_link_suffix):
    """Generate href and title for management dashboard links.

    Args:
        context: Context dictionary
        permission: Permission string
        display_name: Display name
        custom_link_suffix: Optional custom link suffix

    Returns:
        tuple: (title, href) for dashboard link

    """
    if custom_link_suffix:
        return _("Configuration"), _get_perm_link(context, permission, "manage") + custom_link_suffix

    return _(display_name), _get_perm_link(context, permission, permission)


def _get_perm_link(context: dict, permission: str, view_name: str) -> str:
    """Generate permission link URL based on permission type."""
    if permission.startswith("exe"):
        return reverse(view_name)
    return reverse(view_name, args=[context["run"].get_slug()])


def _compile(request, context):
    """Compile management dashboard with suggestions, actions, and priorities.

    Processes and organizes management content sections, handling empty states
    and providing appropriate user messaging.
    """
    section_names = ["suggestions", "actions", "priorities"]
    all_sections_empty = True
    for section_name in section_names:
        context[section_name] = []
        if f"{section_name}_list" in context:
            all_sections_empty = False

    if all_sections_empty:
        return

    permission_cache = {}
    permission_slug_list = []
    for section_name in section_names:
        if f"{section_name}_list" not in context:
            continue

        permission_slug_list.extend(
            [slug for _name, slug, _url in context[f"{section_name}_list"] if _has_permission(request, context, slug)]
        )

    for permission_model in (EventPermission, AssociationPermission):
        permission_queryset = permission_model.objects.filter(slug__in=permission_slug_list).select_related("feature")
        for slug, permission_name, tutorial in permission_queryset.values_list("slug", "name", "feature__tutorial"):
            permission_cache[slug] = (permission_name, tutorial)

    for section_name in section_names:
        if f"{section_name}_list" not in context:
            continue

        for text, slug, custom_link in context[f"{section_name}_list"]:
            if slug not in permission_cache:
                continue

            (permission_name, tutorial) = permission_cache[slug]
            link_name, link_url = _get_href(context, slug, permission_name, custom_link)
            context[section_name].append(
                {"text": text, "link": link_name, "href": link_url, "tutorial": tutorial, "slug": slug}
            )


def exe_close_suggestion(request: HttpRequest, perm: str) -> HttpResponseRedirect:
    """Close a suggestion and redirect to management page."""
    context = check_association_context(request, perm)
    set_suggestion(context, perm)
    return redirect("manage")


def orga_close_suggestion(request: HttpRequest, event_slug: str, perm: EventPermission) -> HttpResponseRedirect:
    """Close a suggestion by setting its status and redirect to manage page."""
    # Check user has permission to access this event
    context = check_event_context(request, event_slug, perm)

    # Update suggestion status to closed
    set_suggestion(context, perm)

    return redirect("manage", event_slug=event_slug)


def _check_intro_driver(request: HttpRequest, context: dict) -> None:
    """Check if intro driver should be shown and update context."""
    member = context["member"]
    config_key = "intro_driver"

    # Skip if user has already seen the intro driver
    if member.get_config(config_key, False):
        return

    # Enable intro driver in template context
    context["intro_driver"] = True


def orga_redirect(request, event_slug: str, run_number: int, path: str = None) -> HttpResponsePermanentRedirect:
    """Optimized redirect from /slug/number/path to /slug-number/path format.

    Redirects URLs like /event-slug/2/some/path to /event-slug-2/some/path.
    Uses permanent redirect (301) for better SEO and caching.

    Args:
        request: Django HTTP request object (not used in redirect logic)
        event_slug: Event slug identifier
        run_number: Run number for the event
        path: Additional path components, defaults to None

    Returns:
        HttpResponsePermanentRedirect: 301 redirect to normalized URL format

    """
    # Initialize path components list with base slug
    path_parts = [event_slug]

    # Only add suffix for run numbers > 1 to keep URLs clean
    if run_number > 1:
        path_parts.append(f"-{run_number}")

    # Join slug and number components, add trailing slash
    base_path = "".join(path_parts) + "/"

    # Append additional path if provided (path already includes leading slash if needed)
    if path:
        base_path += path

    # Return permanent redirect (301) for better caching and SEO
    return HttpResponsePermanentRedirect("/" + base_path)


class WhatWouldYouLikeForm(Form):
    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        """Initialize the form with context and populate choice field options.

        Args:
            *args: Variable length argument list passed to parent class.
            **kwargs: Arbitrary keyword arguments. Must contain 'context' key which
                     is extracted and stored as instance variable.

        """
        # Extract context from kwargs and call parent constructor
        self.context = kwargs.pop("context")
        super().__init__(*args, **kwargs)

        # Initialize empty choices list for dynamic population
        choices = []

        # Add function-related choices to the list
        self._add_function_choices(choices)

        # Add dashboard-related choices to the list
        self._add_dashboard_choices(choices)

        # Add feature-related choices to the list
        self._add_features_choices(choices)

        # Add tutorial-related choices to the list
        self._add_tutorials_choices(choices)

        # Add guide and tutorial choices to the list
        self._add_guides_tutorials(choices)

        # Create the choice field with populated options and Select2 widget
        self.fields["wwyltd"] = ChoiceField(choices=choices, widget=Select2Widget)

    def _add_guides_tutorials(self, content_choices: list[tuple[str, str]]) -> None:
        """Add guide entries to content choices list."""
        # Add guides with formatted titles and preview snippets
        for guide_data in get_guides_cache():
            content_choices.append(
                (f"guide|{guide_data['slug']}", f"{guide_data['title']} [GUIDE] - {guide_data['content_preview']}")
            )

    def _add_tutorials_choices(self, choices: list[tuple[str, str]]) -> None:
        """Add tutorial entries to choices list with formatted titles and previews."""
        # Add tutorials (including sections)
        for tutorial in get_tutorials_cache():
            # Build tutorial title with optional section
            tutorial_title = tutorial["title"]
            if tutorial["section_title"] and slugify(tutorial["section_title"]) != slugify(tutorial["title"]):
                tutorial_title += " - " + tutorial["section_title"]
                tutorial_choice_value = f"{tutorial['slug']}#{tutorial['section_slug']}"
            else:
                tutorial_choice_value = tutorial["slug"]

            # Append formatted choice with tutorial marker and content preview
            choices.append(
                (f"tutorial|{tutorial_choice_value}", f"{tutorial_title} [TUTORIAL] - {tutorial['content_preview']}")
            )

    def _add_features_choices(self, choices: list[tuple[str, str]]) -> None:
        """Add feature entries to tutorial choices list."""
        # Add features recap
        for feature in get_features_cache():
            # Build display text with feature name and optional module
            display_text = _(feature["name"])
            if feature["module_name"]:
                display_text += " - " + _(feature["module_name"])
            display_text += " [FEATURE] "

            # Append optional description
            if feature["descr"]:
                display_text += _(feature["descr"])

            choices.append((f"feature|{feature['tutorial']}", display_text))

    def _add_dashboard_choices(self, choices: list[tuple[str, str]]) -> None:
        """Add dashboard choices for runs and associations accessible by user."""
        # Combine open and past runs into single dictionary
        all_runs = {**self.context.get("open_runs", {}), **self.context.get("past_runs", {})}

        # Add run dashboard choices for each accessible run
        for _run_id, run_data in all_runs.items():
            choices.append((f"manage_orga|{run_data['slug']}", run_data["s"] + " - " + _("Dashboard")))

        # Add association dashboard choice if user has association role
        if self.context.get("association_role", None):
            choices.append(("manage_exe|", self.context.get("name") + " - " + _("Dashboard")))

    def _add_function_choices(self, choices: list[tuple[str, str]]) -> None:
        """Add function choices to the provided choices list.

        Processes event and association permissions from context and adds them
        as choice tuples to the choices list. Event-related permissions are
        prioritized and added first.

        Args:
            choices: List of choice tuples to extend with function choices.
                    Each tuple contains (value, display_name).

        """
        event_priority_choices = []
        regular_choices = []

        # Add to choices all links in the current interface
        for permission_type in ["event_pms", "association_pms"]:
            all_permissions = self.context.get(permission_type, {})

            # Iterate through modules and their permission lists
            for _module, permission_list in all_permissions.items():
                for permission in permission_list:
                    # Create choice tuple with translated name and description
                    choice_tuple = (
                        f"{permission_type}|{permission['slug']}",
                        _(permission["name"]) + " - " + _(permission["descr"]),
                    )

                    # Prioritize permissions with slug starting with "event"
                    if permission["slug"] in ["exe_events", "orga_event"]:
                        event_priority_choices.append(choice_tuple)
                    else:
                        regular_choices.append(choice_tuple)

        # Add prioritized event choices first, then regular choices
        choices.extend(event_priority_choices)
        choices.extend(regular_choices)


def what_would_you_like(context: dict, request: HttpRequest) -> None:
    """Handle "What would you like to do?" form submission and display.

    Processes POST requests to redirect users based on their selected choice,
    or displays the form for GET requests. Uses RedirectError for navigation.

    Args:
        context: Template context dictionary to store form data
        request: HTTP request object containing POST data or GET request

    Raises:
        RedirectError: Always raised for navigation (success or error cases)

    """
    if request.POST:
        # Process form submission with POST data
        form = WhatWouldYouLikeForm(request.POST, context=context)

        if form.is_valid():
            # Extract user's choice from validated form
            user_choice = form.cleaned_data["wwyltd"]

            try:
                # Get redirect URL based on user's choice
                redirect_url = _get_choice_redirect_url(user_choice, context)
                raise RedirectError(redirect_url)
            except ValueError as error:
                # Handle invalid choice with error message
                messages.error(request, str(error))
                raise RedirectError(request.path) from error
    else:
        # Display empty form for GET requests
        form = WhatWouldYouLikeForm(context=context)

    # Add form to template context
    context["form"] = form


def _get_choice_redirect_url(choice, context):
    """Get the appropriate redirect URL based on the user's choice.

    Args:
        choice: The choice value from the form (format: "type#value")
        context: Context dictionary containing association and event data

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
        "event_pms": lambda: _handle_event_pms_redirect(choice_value, context),
        "association_pms": lambda: reverse(choice_value),
        "manage_orga": lambda: reverse("manage", args=[choice_value]),
        "tutorial": lambda: _handle_tutorial_redirect(choice_value),
        "guide": lambda: reverse("guide", args=[choice_value]),
        "feature": lambda: _handle_tutorial_redirect(choice_value),
    }

    redirect_handler = redirect_handlers.get(choice_type)
    if not redirect_handler:
        raise ValueError(_("Unknown choice type: %(type)s") % {"type": choice_type})

    return redirect_handler()


def _handle_event_pms_redirect(choice_value, context):
    """Handle event permissions redirect."""
    if "run" not in context:
        raise ValueError(_("Event context not available"))
    return reverse(choice_value, args=[context["run"].get_slug()])


def _handle_tutorial_redirect(tutorial_choice_value):
    """Handle tutorial redirect with optional section anchor."""
    if "#" in tutorial_choice_value:
        tutorial_slug, section_slug = tutorial_choice_value.split("#", 1)
        # Remove forward slashes from both parts
        tutorial_slug = tutorial_slug.replace("/", "")
        section_slug = section_slug.replace("/", "")
        return reverse("tutorials", args=[tutorial_slug]) + f"#{section_slug}"

    # Remove forward slashes from tutorial_choice_value
    sanitized_tutorial_slug = tutorial_choice_value.replace("/", "")
    return reverse("tutorials", args=[sanitized_tutorial_slug])
