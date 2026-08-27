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
"""Priority/action/suggestion list building for the management dashboard and sidebar badges.

Split out of views.manage so that utils.core.base (which needs set_sidebar_badges
to compute pending-work counts for the sidebar) does not have to import the whole,
view-heavy views.manage module, which itself imports utils.core.base.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.config import (
    get_association_config,
    get_event_config,
    is_association_config_set,
    is_event_config_set,
)
from larpmanager.cache.feature import get_association_features, get_event_features
from larpmanager.cache.widget import get_exe_widget_cache, get_orga_widget_cache
from larpmanager.models.access import AssociationPermission, EventPermission
from larpmanager.models.association import AssociationTextType
from larpmanager.models.event import RegistrationStatus
from larpmanager.utils.auth.permission import has_association_permission, has_event_permission

if TYPE_CHECKING:
    from django.http import HttpRequest


def _exe_suggestions(context: dict) -> None:
    """Add priority tasks and suggestions to the executive management context.

    Args:
        context: Context dictionary containing association ID and other data

    """
    suggestions = {
        "exe_roles": _("Define roles to grant organization management access"),
    }

    if not context.get("lite_mode"):
        suggestions.update(
            {
                "exe_appearance": _("Customize organization pages appearance"),
                "exe_features": _("Activate new platform features"),
                "exe_config": _("Configure organization feature settings"),
            }
        )

    for permission_key, suggestion_text in suggestions.items():
        if get_association_config(context["association_id"], f"{permission_key}_suggestion", context=context):
            continue
        _add_suggestion(context, suggestion_text, permission_key)


def _exe_pending_approval_actions(context: dict, actions_data: dict) -> None:
    """Add actions for the various pending-approval queues (runs, expenses, invoices, refunds, members)."""
    if actions_data.get("past_runs", {}).get("count", 0) > 0:
        runs_to_conclude = actions_data["past_runs"]["runs"]
        _add_action(
            context,
            _("Mark as completed: <b>%(list)s</b>.") % {"list": ", ".join(runs_to_conclude)},
            "exe_events",
        )

    if actions_data.get("pending_expenses", {}).get("count", 0) > 0:
        _add_action(
            context,
            _("<b>%(number)s</b> expenses to approve") % {"number": actions_data["pending_expenses"]["count"]},
            "exe_expenses",
            count=actions_data["pending_expenses"]["count"],
        )

    for key, url, label in [
        ("pending_invoices_registration", "exe_payments", _("payments")),
        ("pending_invoices_donation", "exe_donations", _("donations")),
        ("pending_invoices_collection", "exe_collections", _("collections")),
        ("pending_invoices_membership", "exe_membership", _("membership fees")),
    ]:
        if actions_data.get(key, {}).get("count", 0) > 0:
            _add_action(
                context,
                _("<b>%(number)s</b> %(label)s to approve") % {"number": actions_data[key]["count"], "label": label},
                url,
                count=actions_data[key]["count"],
            )

    if actions_data.get("pending_refunds", {}).get("count", 0) > 0:
        _add_action(
            context,
            _("<b>%(number)s</b> refunds to deliver") % {"number": actions_data["pending_refunds"]["count"]},
            "exe_refunds",
            count=actions_data["pending_refunds"]["count"],
        )

    if actions_data.get("pending_members", {}).get("count", 0) > 0:
        _add_action(
            context,
            _("<b>%(number)s</b> members to approve") % {"number": actions_data["pending_members"]["count"]},
            "exe_membership",
            count=actions_data["pending_members"]["count"],
        )


def _exe_actions(request: HttpRequest, context: dict, association_features: dict | None = None) -> None:
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

    # Add prompt to complete checklist and activate advanced mode when in demo/lite mode.
    # Deferred: services.association transitively imports this module (via base, which
    # this module is imported by), so a module-level import here would be circular.
    if context.get("lite_mode"):
        from larpmanager.utils.services.association import get_activation_checklist  # noqa: PLC0415

        _checklist, context["progress"] = get_activation_checklist(context["association_id"])

    # Check if currency configuration suggestion has been dismissed
    _check_currency_priority(request, context, association_features)

    # Get cached actions data
    actions_data = get_exe_widget_cache(context["association_id"], "actions")

    _exe_pending_approval_actions(context, actions_data)

    if "publisher" in association_features:
        _exe_publisher_actions(context, actions_data)

    # Process accounting-specific actions
    _exe_accounting_actions(context, association_features)

    # Process user-specific actions
    _exe_users_actions(context, association_features, actions_data)

    actions = {
        "exe_methods": _("Set up payment methods for participants"),
        "exe_profile": _("Define the data collected in the user profile form"),
    }
    if not context.get("lite_mode"):
        actions["exe_quick"] = _("Select and activate key features")

    for permission_key, suggestion_text in actions.items():
        if get_association_config(context["association_id"], f"{permission_key}_suggestion", context=context):
            continue
        _add_action(context, suggestion_text, permission_key)


def _exe_publisher_actions(context: dict, actions_data: dict) -> None:
    """Add publisher-related actions to the executive dashboard."""
    if actions_data.get("ildb_unpublished_runs", {}).get("count", 0) > 0:
        _add_action(
            context,
            _("Publish to ILDB: <b>%(list)s</b>.") % {"list": ", ".join(actions_data["ildb_unpublished_runs"]["runs"])},
            "exe_events",
        )
    if actions_data.get("ildb_token_expired"):
        _add_action(context, _("Generate a new ILDB token"), "exe_config")


def _exe_users_actions(context: dict, enabled_features: dict[str, Any], actions_data: dict) -> None:
    """Process user management actions and setup tasks for executives.

    Args:
        context: Context dictionary to populate with actions
        enabled_features: Set of enabled features
        actions_data: Cached actions data dictionary

    """
    if "membership" in enabled_features:
        if not get_association_text(context["association_id"], AssociationTextType.MEMBERSHIP):
            _add_priority(context, _("Set up the membership request text"), "exe_membership", "texts")

        if not is_association_config_set(context["association_id"], "membership_fee", context=context):
            _add_priority(context, _("Set up the membership configuration"), "exe_membership", "config/membership")

    if "vote" in enabled_features and not is_association_config_set(
        context["association_id"], "vote_candidates", context=context
    ):
        _add_priority(
            context,
            _("Set up the voting configuration"),
            "exe_config",
        )

    if "help" in enabled_features and actions_data.get("open_help_questions", {}).get("count", 0) > 0:
        _add_action(
            context,
            _("<b>%(number)s</b> questions to answer") % {"number": actions_data["open_help_questions"]["count"]},
            "exe_questions",
            count=actions_data["open_help_questions"]["count"],
        )


def _exe_accounting_actions(context: dict, enabled_features: dict[str, Any]) -> None:
    """Process accounting-related setup actions for executives.

    Args:
        context: Context dictionary to populate with priority actions
        enabled_features: Set of enabled features for the association

    """
    if context.get("lite_mode"):
        return

    if "payment" in enabled_features and not context.get("methods", ""):
        _add_priority(
            context,
            _("Set up payment methods"),
            "exe_methods",
        )

    if "organization_tax" in enabled_features and not is_association_config_set(
        context["association_id"], "organization_tax_perc", context=context
    ):
        _add_priority(
            context,
            _("Configure the association infrastructure fee"),
            "exe_accounting",
            "config/organization_tax",
        )

    if "vat" in enabled_features:
        vat_ticket_set = is_association_config_set(context["association_id"], "vat_ticket", context=context)
        vat_options_set = is_association_config_set(context["association_id"], "vat_options", context=context)
        if not vat_ticket_set or not vat_options_set:
            _add_priority(
                context,
                _("Set up the taxes configuration"),
                "exe_accounting",
                "config/vat",
            )


def _orga_actions_priorities(context: dict, features: dict) -> None:  # noqa: C901 - Complex priority determination logic
    """Determine priority actions for event organizers based on event state.

    Analyzes event features and configuration to suggest next steps in
    event setup workflow, checking for missing required configurations.
    Populates context with priority actions and regular actions for the organizer dashboard.

    Args:
        context: Context dictionary containing 'event' and 'run' keys. Will be updated
             with priority and action lists
        features: Activated features dictionary

    Side effects:
        Modifies context by calling _add_priority() and _add_action() which populate
        action lists for the organizer dashboard

    """
    if context.get("lite_mode"):
        return

    # Get cached actions data
    actions_data = get_orga_widget_cache(context["run"], "actions")

    # Check if character feature is properly configured
    if "character" in features:
        # Prompt to create first character if none exist
        if not actions_data.get("has_characters", False):
            _add_priority(
                context,
                _("Create the first character of the event"),
                "orga_characters",
            )
    # Check for feature dependencies on character feature
    elif set(features) & {
        "faction",
        "plot",
        "casting",
        "user_character",
        "experience",
        "custom_character",
        "questbuilder",
    }:
        _add_priority(
            context,
            _("Some features require 'Character', which is not active"),
            "orga_features",
        )

    # Check for features that depend on credits
    if "credits" not in features and set(features) & {"expense", "refund", "collection"}:
        _add_priority(
            context,
            _("Some features require 'Credits', which is not active"),
            "orga_features",
        )

    # Check for pending character approvals
    if actions_data.get("proposed_characters", {}).get("count", 0) > 0:
        _add_action(
            context,
            _("<b>%(number)s</b> characters to approve") % {"number": actions_data["proposed_characters"]["count"]},
            "orga_characters",
            count=actions_data["proposed_characters"]["count"],
        )

    # Check for pending expense approvals (if not disabled for organizers)
    if (
        not get_association_config(context["event"].association_id, "expense_disable_orga", context=context)
        and actions_data.get("pending_expenses", {}).get("count", 0) > 0
    ):
        _add_action(
            context,
            _("<b>%(number)s</b> expenses to approve") % {"number": actions_data["pending_expenses"]["count"]},
            "orga_expenses",
            count=actions_data["pending_expenses"]["count"],
        )

    # Check for pending signup requests awaiting approval
    if actions_data.get("pending_registration_requests", {}).get("count", 0) > 0:
        _add_action(
            context,
            _("<b>%(number)s</b> signup requests to approve")
            % {"number": actions_data["pending_registration_requests"]["count"]},
            "orga_registration_requests",
            count=actions_data["pending_registration_requests"]["count"],
        )

    # Check for pending registration invoice approvals
    if actions_data.get("pending_invoices_registration", {}).get("count", 0) > 0:
        _add_action(
            context,
            _("<b>%(number)s</b> %(label)s to approve")
            % {"number": actions_data["pending_invoices_registration"]["count"], "label": _("payments")},
            "orga_payments",
            count=actions_data["pending_invoices_registration"]["count"],
        )

    # Check for incomplete registration form questions (missing options)
    if actions_data.get("registration_questions_incomplete", {}).get("count", 0) > 0:
        registration_questions_without_options = actions_data["registration_questions_incomplete"]["names"]
        _add_priority(
            context,
            _("Registration questions without options: %(list)s")
            % {"list": ", ".join(registration_questions_without_options)},
            "orga_registration_form",
        )

    # Check for incomplete writing form questions (missing options)
    if actions_data.get("writing_questions_incomplete", {}).get("count", 0) > 0:
        writing_questions_without_options = actions_data["writing_questions_incomplete"]["names"]
        _add_priority(
            context,
            _("Writing fields without options: %(list)s") % {"list": ", ".join(writing_questions_without_options)},
            "orga_character_form",
        )

    # Delegate to sub-functions for additional action checks
    _orga_user_actions(context, features, actions_data)

    _orga_registration_accounting_actions(context, features, actions_data)

    _orga_registration_actions(context, features)

    _orga_exp_actions(context, features, actions_data)

    _orga_casting_actions(context, features, actions_data)


def _orga_user_actions(
    context: dict,
    features: dict[str, int],
    actions_data: dict,
) -> None:
    """Add action to context if there are unanswered help questions.

    Args:
        context: Template context dictionary to update with actions.
        features: List of enabled feature names for the organization.
        actions_data: Cached actions data from get_orga_widget_cache.

    """
    # Check if help feature is enabled
    if "help" in features and actions_data.get("open_help_questions", {}).get("count", 0) > 0:
        _add_action(
            context,
            _("<b>%(number)s</b> questions to answer") % {"number": actions_data["open_help_questions"]["count"]},
            "exe_questions",
            count=actions_data["open_help_questions"]["count"],
        )


def _orga_casting_actions(context: dict, enabled_features: dict[str, Any], actions_data: dict) -> None:
    """Add priority actions related to casting and quest builder setup.

    Checks for missing casting configurations and quest/trait relationships,
    adding appropriate priority suggestions for event organizers.

    Args:
        context: Context dictionary containing event and other data.
        enabled_features: Dictionary of enabled features.
        actions_data: Cached actions data from get_orga_widget_cache.
    """
    if "casting" in enabled_features and not is_event_config_set(context["event"].id, "casting_min", context=context):
        _add_priority(
            context,
            _("Set casting options in the configuration"),
            "orga_casting",
            "config/casting",
        )

    if "questbuilder" in enabled_features:
        if not actions_data.get("has_quest_types", False):
            _add_priority(
                context,
                _("Set up quest types"),
                "orga_quest_types",
            )

        if actions_data.get("quest_types_without_quests", {}).get("count", 0) > 0:
            quest_type_names = actions_data["quest_types_without_quests"]["names"]
            _add_priority(
                context,
                _("Quest types without quests: %(list)s") % {"list": ", ".join(quest_type_names)},
                "orga_quests",
            )

        if actions_data.get("quests_without_traits", {}).get("count", 0) > 0:
            quest_names = actions_data["quests_without_traits"]["names"]
            _add_priority(
                context,
                _("Quests without traits: %(list)s") % {"list": ", ".join(quest_names)},
                "orga_traits",
            )


def _orga_exp_actions(context: dict, enabled_features: dict, actions_data: dict) -> None:
    """Add priority actions for experience points system setup.

    Checks for missing EXP configurations, ability types, and deliveries,
    adding appropriate priority suggestions for event organizers.

    Args:
        context: Context dictionary containing event and other relevant data
        enabled_features: Dictionary of enabled features for the current context
        actions_data: Cached actions data from get_orga_widget_cache

    Returns:
        None: Function modifies context in place by adding priority suggestions

    """
    # Early return if EXP feature is not enabled
    if "experience" not in enabled_features:
        return

    # Check if experience points configuration is missing
    if not is_event_config_set(context["event"].id, "exp_start", context=context):
        _add_priority(
            context,
            _("Set the experience points configuration"),
            "orga_exp_abilities",
            "config/experience",
        )

    # Verify that ability types have been set up
    if not actions_data.get("has_ability_types", False):
        _add_priority(
            context,
            _("Set up ability types"),
            "orga_exp_ability_types",
        )

    # Find ability types that don't have any associated abilities
    if actions_data.get("ability_types_without_abilities", {}).get("count", 0) > 0:
        ability_type_names = actions_data["ability_types_without_abilities"]["names"]
        _add_priority(
            context,
            _("Ability types without abilities: %(list)s") % {"list": ", ".join(ability_type_names)},
            "orga_exp_abilities",
        )

    # Check if delivery methods for experience points are configured
    if not actions_data.get("has_delivery_px", False):
        _add_priority(
            context,
            _("Set up award for experience points"),
            "orga_exp_deliveries",
        )


def _orga_registration_accounting_actions(context: dict, enabled_features: dict[str, int], actions_data: dict) -> None:
    """Add priority actions related to registration and accounting setup.

    Checks for required configurations when certain features are enabled,
    such as installments, quotas, and accounting systems for events.

    Args:
        context: Context dictionary containing event and other data
        enabled_features: List of enabled feature names
        actions_data: Cached actions data from get_orga_widget_cache

    Returns:
        None: Modifies context in place by adding priority actions

    """
    # Check for conflicting installment features
    if "reg_installments" in enabled_features and "reg_quotas" in enabled_features:
        _add_priority(
            context,
            _("Fixed and dynamic installments cannot be used together; deactivate one"),
            "orga_features",
        )

    # Handle dynamic installments (quotas) setup
    if "reg_quotas" in enabled_features and not actions_data.get("has_registration_quotas", False):
        _add_priority(
            context,
            _("Set up dynamic installments"),
            "orga_registration_quotas",
        )

    # Handle fixed installments feature
    if "reg_installments" in enabled_features:
        # Check if installments are configured
        if not actions_data.get("has_registration_installments", False):
            _add_priority(
                context,
                _("Set up fixed installments"),
                "orga_registration_installments",
            )
        else:
            # Validate installment configuration - check for conflicting deadline settings
            if actions_data.get("installments_both_deadlines", {}).get("count", 0) > 0:
                installments_names = actions_data["installments_both_deadlines"]["names"]
                _add_priority(
                    context,
                    _("Some installments have both date and days set (mutually exclusive): %(list)s")
                    % {"list": ", ".join(installments_names)},
                    "orga_registration_installments",
                )

            # Check for missing final installments (amount = 0)
            if actions_data.get("tickets_missing_final_installment", {}).get("count", 0) > 0:
                tickets_names = actions_data["tickets_missing_final_installment"]["names"]
                _add_priority(
                    context,
                    _("Some tickets are missing a final installment (0 amount): %(list)s")
                    % {"list": ", ".join(tickets_names)},
                    "orga_registration_installments",
                )

    # Handle reduced tickets feature configuration
    if "reduced" in enabled_features and not is_event_config_set(context["event"].id, "reduced_ratio", context=context):
        _add_priority(
            context,
            _("Set up Patron and Reduced ticket configuration"),
            "orga_registration_tickets",
            "config/reduced",
        )


def _check_currency_priority(request: HttpRequest, context: dict, features: dict) -> Any:
    """Check if currency has been already set / checked."""
    if (
        "payment" in features
        and not get_association_config(context["association_id"], "exe_association_suggestion", context=context)
        and has_association_permission(request, context, "exe_association")
    ):
        _add_priority(
            context,
            _("Set the organization payment currency"),
            "exe_association",
        )


def _orga_registration_actions(context: dict, enabled_features: dict[str, Any]) -> None:
    """Add priority actions for registration management setup.

    Checks registration status, required tickets, and registration features
    to provide guidance for event organizers.
    """
    if context["run"].registration_status == RegistrationStatus.FUTURE and not context["run"].registration_open:
        _add_priority(
            context,
            _("Set the registration opening date"),
            "orga_event",
        )

    if "registration_secret" in enabled_features and not context["run"].registration_secret:
        _add_priority(
            context,
            _("Set the registration secret link"),
            "orga_event",
        )

    if context["run"].registration_status == RegistrationStatus.EXTERNAL and not context["run"].register_link:
        _add_priority(
            context,
            _("Set the registration external link"),
            "orga_event",
        )

    if "custom_character" in enabled_features:
        is_configured = False
        for field_name in ["pronoun", "song", "public", "private", "profile"]:
            if get_event_config(context["event"].id, "custom_character_" + field_name, context=context):
                is_configured = True

        if not is_configured:
            _add_priority(
                context,
                _("Set up character customization configuration"),
                "orga_characters",
                "config/custom_character",
            )


def _orga_suggestions(context: dict) -> None:
    """Add priority suggestions for event organization.

    Args:
        context: Context dictionary to add suggestions to

    """
    actions = {
        "orga_registration_tickets": _("Set up registration tickets"),
    }
    if not context.get("lite_mode"):
        actions["orga_quick"] = _("Select and activate key features")

    for permission_slug, suggestion_text in actions.items():
        if get_event_config(context["event"].id, f"{permission_slug}_suggestion", context=context):
            continue
        _add_action(context, suggestion_text, permission_slug)

    suggestions = {
        "orga_registration_form": _("Define the registration form"),
        "orga_roles": _("Define roles to grant event management access"),
    }

    if not context.get("lite_mode"):
        suggestions.update(
            {
                "orga_appearance": _("Customize event pages appearance"),
                "orga_features": _("Activate new event features"),
                "orga_config": _("Configure event feature settings"),
            }
        )

    for permission_slug, suggestion_text in suggestions.items():
        if get_event_config(context["event"].id, f"{permission_slug}_suggestion", context=context):
            continue
        _add_suggestion(context, suggestion_text, permission_slug)


def _exe_build_lists(request: HttpRequest, context: dict, features: dict) -> None:
    """Populate priorities, actions and suggestions lists for the executive dashboard."""
    if context.get("demo"):
        return

    if "ongoing_runs" not in context:
        actions_data_exe = get_exe_widget_cache(context["association_id"], "actions")
        context["ongoing_runs"] = actions_data_exe.get("ongoing_runs", [])

    # Suggest creating an event if no runs are active
    if not context["ongoing_runs"]:
        _add_priority(
            context,
            _("No events are present, create one"),
            "exe_events",
        )

    # Notify if a newer platform version is available
    if context.get("assoc_version", 0) < context.get("latest_available_version", 0):
        _add_priority(
            context,
            _("A new version of the platform is available"),
            "exe_version_upgrade",
        )

    _exe_actions(request, context, features)
    _exe_suggestions(context)


def _orga_build_lists(request: HttpRequest, context: dict, features: dict) -> None:
    """Populate priorities, actions and suggestions lists for the organizer dashboard."""
    if context.get("demo"):
        return

    # Reuse the executive checks for association-level priorities, but drop the
    # executive actions which are not relevant on the organizer dashboard
    _exe_actions(request, context)
    context.pop("actions_list", None)

    _orga_actions_priorities(context, features)
    _orga_suggestions(context)


def set_sidebar_badges(request: HttpRequest, context: dict) -> None:
    """Compute the sidebar badge totals for the management sidebar.

    Builds the same priorities/actions the dashboard would show and stores an
    aggregated {permission_slug: pending_count} mapping in context["sidebar_badges"],
    so every management page can display pending-work counts next to sidebar links.
    """
    # Only relevant for the management sidebar of an authenticated staff member
    if not context.get("manage") or not context.get("member"):
        return

    # The dashboard views already build the lists and _compile the badges themselves
    if "sidebar_badges" in context:
        return

    if context.get("run"):
        features = context.get("features") or get_event_features(context["event"].id)
        _orga_build_lists(request, context, features)
    else:
        features = context.get("features") or get_association_features(context["association_id"])
        _exe_build_lists(request, context, features)

    _compile(request, context)


def _add_item(
    context: dict,
    list_name: str,
    message_text: str,
    permission_key: str,
    custom_link: str | None,
    count: int | None = None,
) -> None:
    """Add item to specific list in management context.

    The count represents how many pending elements the item stands for and is
    used to build the sidebar badge totals. Items without an explicit count
    (e.g. setup suggestions) do not contribute to the badges.
    """
    if list_name not in context:
        context[list_name] = []

    context[list_name].append((message_text, permission_key, custom_link, count))


def _add_priority(
    context: dict, priority_text: str, permission_key: str, custom_link: str | None = None, count: int | None = None
) -> None:
    """Add priority item to management dashboard."""
    _add_item(context, "priorities_list", priority_text, permission_key, custom_link, count)


def _add_action(
    context: dict, action_text: str, permission_key: str, custom_link: str | None = None, count: int | None = None
) -> None:
    """Add action item to management dashboard."""
    _add_item(context, "actions_list", action_text, permission_key, custom_link, count)


def _add_suggestion(
    context: dict, suggestion_text: str, permission_key: str, custom_link: str | None = None, count: int | None = None
) -> None:
    """Add suggestion item to management dashboard."""
    _add_item(context, "suggestions_list", suggestion_text, permission_key, custom_link, count)


def _has_permission(request: HttpRequest, context: dict, permission: str) -> bool:
    """Check if user has required permission for action."""
    if permission.startswith("exe"):
        return has_association_permission(request, context, permission)
    return has_event_permission(request, context, context["event"].slug, permission)


def _get_href(context: dict, permission: str, display_name: str, custom_link_suffix: str | None) -> tuple[str, str]:
    """Generate href and title for management dashboard links."""
    if custom_link_suffix:
        return _("Configuration"), _get_perm_link(context, permission, "manage") + custom_link_suffix

    return _(display_name), _get_perm_link(context, permission, permission)


def _get_perm_link(context: dict, permission: str, view_name: str) -> str:
    """Generate permission link URL based on permission type."""
    if permission.startswith("exe"):
        return reverse(view_name)
    return reverse(view_name, args=[context["run"].get_slug()])


def _compile(request: HttpRequest, context: dict) -> None:  # noqa: C901, PLR0912 - Complex dashboard compilation with feature-dependent sections
    """Compile management dashboard with suggestions, actions, and priorities."""
    section_names = ["priorities"]
    if not context.get("lite_mode"):
        section_names.extend(["suggestions", "actions"])
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
            [
                slug
                for _name, slug, _url, _count in context[f"{section_name}_list"]
                if _has_permission(request, context, slug)
            ],
        )

    for permission_model in (EventPermission, AssociationPermission):
        permission_queryset = permission_model.objects.filter(slug__in=permission_slug_list).select_related("feature")
        for slug, permission_name, tutorial, icon in permission_queryset.values_list(
            "slug", "name", "feature__tutorial", "icon"
        ):
            permission_cache[slug] = (permission_name, tutorial, icon)

    # Aggregate pending element counts per permission slug for the sidebar badges
    sidebar_badges = context.setdefault("sidebar_badges", {})

    for section_name in section_names:
        if f"{section_name}_list" not in context:
            continue

        for text, slug, custom_link, count in context[f"{section_name}_list"]:
            if slug not in permission_cache:
                continue

            (permission_name, tutorial, icon) = permission_cache[slug]
            link_name, link_url = _get_href(context, slug, permission_name, custom_link)
            context[section_name].append(
                {"text": text, "link": link_name, "href": link_url, "tutorial": tutorial, "slug": slug, "icon": icon},
            )

            # Only items with an explicit count contribute to the badges; suggestions
            # (informational hints) and setup priorities without a count are excluded
            if count and section_name in ("priorities", "actions"):
                sidebar_badges[slug] = sidebar_badges.get(slug, 0) + count
