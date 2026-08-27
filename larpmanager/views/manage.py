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

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms import ChoiceField, Form
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponsePermanentRedirect,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_select2.forms import Select2Widget
from slugify import slugify

from larpmanager.cache.config import (
    get_association_config,
    get_event_config,
)
from larpmanager.cache.feature import get_association_features, get_event_features
from larpmanager.cache.registration_counts import get_registration_counts
from larpmanager.cache.widget import get_exe_widget_cache, get_orga_widget_cache
from larpmanager.cache.wwyltd import (
    get_exe_configs_cache,
    get_features_cache,
    get_guides_cache,
    get_orga_configs_cache,
    get_tutorials_cache,
)
from larpmanager.models.event import RegistrationStatus, Run
from larpmanager.utils.auth.permission import (
    get_event_roles,
    get_index_association_permissions,
    get_index_event_permissions,
    has_association_permission,
    has_event_permission,
)
from larpmanager.utils.core.base import check_association_context, check_event_context, get_context, get_event_context
from larpmanager.utils.core.common import format_datetime
from larpmanager.utils.core.dashboard import _compile, _exe_build_lists, _orga_build_lists
from larpmanager.utils.core.sticky import dismiss_sticky, get_sticky_messages
from larpmanager.utils.edit.backend import set_suggestion
from larpmanager.utils.registrations.availability import registration_available


@login_required
def manage(request: HttpRequest, event_slug: str | None = None) -> HttpResponse | HttpResponseRedirect:
    """Route to the appropriate management dashboard."""
    if request.association["id"] == 0:
        return redirect("home")

    if event_slug:
        return _orga_manage(request, event_slug)
    return _exe_manage(request)


def _get_registration_status_code(run: Run) -> tuple[str, Any]:
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

    # Use the registration_status field
    status = run.registration_status

    # Check external registration link
    if status == RegistrationStatus.EXTERNAL:
        return "external", run.register_link

    # Check pre-registration
    if status == RegistrationStatus.PRE:
        return "preregister", None

    # Check closed status
    if status == RegistrationStatus.CLOSED:
        return "closed", None

    # Check registration opening time (future status)
    if status == RegistrationStatus.FUTURE:
        if not run.registration_open:
            return "not_set", None
        current_datetime = timezone.now()
        if run.registration_open and run.registration_open > current_datetime:
            return "future", run.registration_open

    # Check registration closing time (closing status)
    if status == RegistrationStatus.CLOSING:
        if not run.registration_open:
            return "not_set", None
        current_datetime = timezone.now()
        if run.registration_open <= current_datetime:
            return "closed", None

    # For OPEN status, FUTURE with past opening time, or CLOSING before closing time, check registration availability
    run_status = {}
    registration_available(run, features, run_status)

    # Determine status based on availability
    status_priority = ["primary", "filler", "waiting"]
    for status_type in status_priority:
        if status_type in run_status:
            return status_type, run_status.get("count")

    return "closed", None


def _get_registration_status(run: Run) -> str:
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
    status_code, opening_datetime = _get_registration_status_code(run)

    # Define mapping of status codes to localized human-readable messages
    status_messages = {
        "external": _("Registrations on external link"),
        "preregister": _("Pre-registration active"),
        "not_set": _("Registrations opening not set"),
        "primary": _("Registrations open"),
        "filler": _("Reserve registrations"),
        "waiting": _("Waiting list registrations"),
        "closed": _("Registration closed"),
    }

    # Special handling for future registrations with datetime formatting
    if status_code == "future":
        # Check if we have a valid datetime to format
        if opening_datetime:
            formatted_opening_date = opening_datetime.strftime(format_datetime)
            return _("Registrations opening on: %(date)s") % {"date": formatted_opening_date}
        # Fallback when datetime is not available
        return _("Registrations opening not set")

    # Return the appropriate status message or default to closed
    return status_messages.get(status_code, _("Registration closed"))


def _get_registration_counts(run: Run) -> dict:
    """Prepares run registration ticket counts ordered by ticket order field."""
    counts = get_registration_counts(run.id, run.event_id)

    # Create a list of ticket data with name, order, and count
    ticket_data = []
    for ticket_id, ticket_name in counts.get("tickets_map", {}).items():
        count_key = f"count_ticket_{ticket_id}"
        if counts.get(count_key):
            ticket_order = counts.get("tickets_order", {}).get(ticket_id, 0)
            ticket_data.append({"name": ticket_name, "order": ticket_order, "count": counts[count_key]})

    # Sort by order field, then by name
    sorted_tickets = sorted(ticket_data, key=lambda x: (x["order"], x["name"]))

    # Return as a dict with ticket name as key and count as value
    return {ticket["name"]: ticket["count"] for ticket in sorted_tickets}


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
    get_index_association_permissions(request, context, context["association_id"])
    context["exe_page"] = 1
    context["manage"] = 1

    # Get available features for this association
    features = get_association_features(context["association_id"])

    # Get ongoing runs directly from cache (already contains all data needed by template)
    actions_data_exe = get_exe_widget_cache(context["association_id"], "actions")
    context["ongoing_runs"] = actions_data_exe.get("ongoing_runs", [])

    # Load widgets
    _exe_widgets(request, context, features)

    # Add dashboard priorities, actions and suggestions
    _exe_build_lists(request, context, features)

    # Add sticky messages for the current user
    context["sticky_messages"] = get_sticky_messages(context, context["member"])

    # Compile final context
    _compile(request, context)

    return render(request, "larpmanager/manage/exe.html", context)


def _exe_widgets(request: HttpRequest, context: dict, features: dict) -> None:
    """Loads widget data into context for executive dashboard."""
    permissions = [
        ("exe_accounting", "accounting", False),
        ("exe_deadlines", "deadlines", True),
        ("exe_log", "logs", True),
    ]

    widgets_available = [
        widget
        for perm, widget, require_feature in permissions
        if has_association_permission(request, context, perm) and (not require_feature or widget in features)
    ]

    context["widgets"] = {
        widget: get_exe_widget_cache(context["association_id"], widget) for widget in widgets_available
    }



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
    features = get_event_features(context["event"].id)

    # Ensure run dates are set
    if not context["run"].start or not context["run"].end:
        message = _("Last step, please complete the event setup by adding the start and end dates")
        messages.success(request, message)
        return redirect("orga_run", event_slug=event_slug)

    # Load permissions and navigation
    get_index_event_permissions(request, context, event_slug)
    is_organizer, _perms, _roles = get_event_roles(request, context, event_slug)
    context["is_organizer"] = is_organizer or 1 in context.get("association_role", {})
    if get_association_config(context["association_id"], "interface_admin_links", context=context):
        get_index_association_permissions(request, context, context["association_id"], enforce_check=False)

    # Load registration status
    context["registration_status"] = _get_registration_status(context["run"])
    status_code, __ = _get_registration_status_code(context["run"])
    context["registrations_open"] = status_code in ["primary", "filler", "waiting"]

    # Load registration counts if permitted
    if has_event_permission(request, context, event_slug, "orga_registrations"):
        context["registration_counts"] = _get_registration_counts(context["run"])

    # Build action lists
    _orga_build_lists(request, context, features)
    _compile(request, context)

    # Add sticky messages for the current user (filtered by event UUID)
    context["sticky_messages"] = get_sticky_messages(
        context, context["member"], element_uuid=str(context["event"].uuid)
    )

    # Mobile shortcuts handling
    if get_event_config(context["event"].id, "show_shortcuts_mobile", context=context):
        origin_id = request.GET.get("origin", "")
        should_open_shortcuts = False
        if origin_id:
            should_open_shortcuts = str(context["run"].id) != origin_id
        context["open_shortcuts"] = should_open_shortcuts

    # Loads widget data
    _orga_widgets(request, context, features)

    return render(request, "larpmanager/manage/orga.html", context)


def _orga_widgets(request: HttpRequest, context: dict, features: dict):
    """Loads widget data into context."""
    permissions = [
        ("orga_accounting", "accounting", False),
        ("orga_deadlines", "deadlines", True),
        ("orga_casting", "casting", True),
        ("orga_log", "logs", True),
    ]

    event_slug = context["event"].slug
    widgets_available = [
        widget
        for perm, widget, require_feature in permissions
        if has_event_permission(request, context, event_slug, perm)
        and (not require_feature or widget in context["features"])
    ]

    if "user_character" in features and get_event_config(
        context["event"].id, "user_character_approval", context=context
    ):
        widgets_available.append("user_character")

    if "progress" in features and has_event_permission(request, context, event_slug, "orga_characters"):
        widgets_available.append("progress")

    if "milestones" in features and has_event_permission(request, context, event_slug, "orga_milestones"):
        widgets_available.append("milestones")

    context["widgets"] = {widget: get_orga_widget_cache(context["run"], widget) for widget in widgets_available}


def exe_close_suggestion(request: HttpRequest, perm: str) -> HttpResponseRedirect:
    """Close a suggestion and redirect to management page."""
    context = check_association_context(request, perm)
    set_suggestion(context, perm)
    return redirect("manage")


def orga_close_suggestion(request: HttpRequest, event_slug: str, perm: str) -> HttpResponseRedirect:
    """Close a suggestion by setting its status and redirect to manage page."""
    # Check user has permission to access this event
    context = check_event_context(request, event_slug, perm)

    # Update suggestion status to closed
    set_suggestion(context, perm)

    return redirect("manage", event_slug=event_slug)


@login_required
def dismiss_sticky_message(request: HttpRequest, message_uuid: str) -> JsonResponse:
    """Dismiss a sticky message via AJAX."""
    success = dismiss_sticky(request.user.member, message_uuid)

    if success:
        return JsonResponse({"status": "ok"})
    return JsonResponse({"status": "error", "message": "Message not found"}, status=404)


def orga_redirect(
    request: HttpRequest,  # noqa: ARG001
    event_slug: str,
    run_number: int,
    path: str | None = None,
) -> HttpResponsePermanentRedirect:
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
    """Form for WhatWouldYouLike."""

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

        # Add config choices to the list
        self._add_configs_choices(choices)

        # Create the choice field with populated options and Select2 widget
        self.fields["wwyltd"] = ChoiceField(
            choices=[("", _("What would you like to do?"))] + choices,
            required=False,
            widget=Select2Widget(attrs={"data-placeholder": _("What would you like to do?")}),
        )

    @staticmethod
    def _add_guides_tutorials(content_choices: list[tuple[str, str]]) -> None:
        """Add guide entries to content choices list."""
        # Add guides with formatted titles and preview snippets
        content_choices.extend(
            [
                (f"guide|{guide_data['slug']}", f"{guide_data['title']} [GUIDE] - {guide_data['content_preview']}")
                for guide_data in get_guides_cache()
            ]
        )

    @staticmethod
    def _add_tutorials_choices(choices: list[tuple[str, str]]) -> None:
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
                (f"tutorial|{tutorial_choice_value}", f"{tutorial_title} [TUTORIAL] - {tutorial['content_preview']}"),
            )

    @staticmethod
    def _add_features_choices(choices: list[tuple[str, str]]) -> None:
        """Add feature entries to tutorial choices list."""
        # Add features recap
        for feature in get_features_cache():
            if not feature["tutorial"]:
                continue

            # Build display text with feature name and optional module
            display_text = _(feature["name"])
            if feature["module_name"]:
                display_text += " - " + _(feature["module_name"])
            display_text += " [FEATURE] "

            # Append optional description
            if feature["descr"]:
                display_text += _(feature["descr"])

            choices.append((f"feature|{feature['tutorial']}", display_text))

    def _add_configs_choices(self, choices: list[tuple[str, str]]) -> None:
        """Add config field entries to choices list, scoped to the current context."""
        features = self.context.get("features", set())
        if self.context.get("orga_page"):
            event = self.context.get("event")
            if not event:
                return
            config_list = get_orga_configs_cache(event.id, features)
            prefix = "config_orga"
        elif self.context.get("exe_page"):
            association_id = self.context.get("association_id")
            if not association_id:
                return
            config_list = get_exe_configs_cache(association_id, features)
            prefix = "config_exe"
        else:
            return

        for config in config_list:
            display = f"{config['label']} [CONFIG]"
            if config["help_text"]:
                display += f" - {config['help_text']}"
            choices.append((f"{prefix}|{config['section_slug']}", display))

    def _add_dashboard_choices(self, choices: list[tuple[str, str]]) -> None:
        """Add dashboard choices for runs and associations accessible by user."""
        # Combine open and past runs into single dictionary
        all_runs = {**self.context.get("open_runs", {}), **self.context.get("past_runs", {})}

        # Add run dashboard choices for each accessible run
        choices.extend(
            [
                (f"manage_orga|{run_data['slug']}", run_data["label"] + " - " + _("Dashboard"))
                for run_data in all_runs.values()
            ]
        )

        # Add association dashboard choice if user has association role
        if self.context.get("association_role", None):
            choices.append(("manage_exe|", self.context.get("name") + " - " + _("Dashboard")))

    def _add_function_choices(self, choices: list[tuple[str, str]]) -> None:
        """Add function choices to the provided choices list.

        Processes event and association permissions from context and adds them
        as choice tuples to the choices list. Event-related permissions are
        prioritized and added first.

        In orga context (event-specific), only event_pms are added.
        In exe context (organization-wide), only association_pms are added.

        Args:
            choices: List of choice tuples to extend with function choices.
                    Each tuple contains (value, display_name).

        """
        event_priority_choices = []
        regular_choices = []

        # Determine which permission types to include based on context
        if self.context.get("orga_page"):
            permission_types = ["event_pms"]
        elif self.context.get("exe_page"):
            permission_types = ["association_pms"]
        else:
            permission_types = []

        # Add to choices all links in the current interface
        for permission_type in permission_types:
            all_permissions = self.context.get(permission_type, {})

            # Iterate through modules and their permission lists
            for permission_list in all_permissions.values():
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
    """Handle "What would you like to do?" form display."""
    # Display form
    form = WhatWouldYouLikeForm(context=context)

    # Add form to template context
    context["form"] = form


@login_required
def wwyltd_choices_ajax(request: HttpRequest, event_slug: str = None) -> JsonResponse:
    """AJAX endpoint that returns wwyltd choices matching a search query.

    Args:
        request: HTTP request object
        event_slug: Optional event slug (for event-specific context)

    Returns:
        JsonResponse: {"results": [{"id": "...", "text": "..."}, ...]}

    """
    if request.association.get("main_domain") != "larpmanager.com":
        raise Http404

    context = get_context(request)
    if event_slug:
        context = get_event_context(request, event_slug)
        get_index_event_permissions(request, context, event_slug)
        context["orga_page"] = 1
    else:
        get_index_association_permissions(request, context, context["association_id"])
        context["exe_page"] = 1

    query = request.GET.get("q", "").strip().lower()

    form = WhatWouldYouLikeForm(context=context)
    results = [
        {"id": value, "text": label}
        for value, label in form.fields["wwyltd"].choices
        if value and query in label.lower()
    ]
    return JsonResponse({"results": results[:30]})


@login_required
def wwyltd_ajax(request: HttpRequest, event_slug: str = None) -> JsonResponse:
    """AJAX endpoint for "What would you like to do?" form submission.

    Processes POST requests and returns JSON with redirect URL to open in new tab.

    Args:
        request: HTTP request object containing POST data
        event_slug: Optional event slug from URL pattern (for event-specific requests)

    Returns:
        JsonResponse: {"success": True, "url": "..."} or {"success": False, "error": "..."}

    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": _("Invalid request method")}, status=405)

    if request.association.get("main_domain") != "larpmanager.com":
        raise Http404

    # Get context based on request path
    context = get_context(request)

    # Check if this is an event-specific or organization-wide request
    if event_slug:
        context = get_event_context(request, event_slug)
        get_index_event_permissions(request, context, event_slug)
        context["orga_page"] = 1
    else:
        get_index_association_permissions(request, context, context["association_id"])
        context["exe_page"] = 1

    # Process form submission
    form = WhatWouldYouLikeForm(request.POST, context=context)

    if form.is_valid():
        # Extract user's choice from validated form
        user_choice = form.cleaned_data["wwyltd"]

        try:
            # Get redirect URL based on user's choice
            redirect_url = _get_choice_redirect_url(user_choice, context)
            return JsonResponse({"success": True, "url": redirect_url})
        except ValueError as error:
            return JsonResponse({"success": False, "error": str(error)}, status=400)

    # Form validation failed
    errors = form.errors.as_json()
    return JsonResponse({"success": False, "error": errors}, status=400)


def _get_choice_redirect_url(choice: str, context: dict) -> str:
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
        "config_orga": lambda: _handle_config_orga_redirect(choice_value, context),
        "config_exe": lambda: _handle_config_exe_redirect(choice_value),
    }

    redirect_handler = redirect_handlers.get(choice_type)
    if not redirect_handler:
        raise ValueError(_("Unknown choice type: %(type)s") % {"type": choice_type})

    return redirect_handler()


def _handle_event_pms_redirect(choice_value: str, context: dict) -> str:
    """Handle event permissions redirect."""
    if "run" not in context:
        raise ValueError(_("Event context not available"))
    return reverse(choice_value, args=[context["run"].get_slug()])


def _handle_tutorial_redirect(tutorial_choice_value: str) -> str:
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


def _handle_config_orga_redirect(section_slug: str, context: dict) -> str:
    """Handle redirect to event config page, optionally at a specific section."""
    if "run" not in context:
        raise ValueError(_("Event context not available"))
    event_slug = context["run"].get_slug()
    return reverse("orga_config", args=[event_slug, section_slug])


def _handle_config_exe_redirect(section_slug: str) -> str:
    """Handle redirect to association config page at a specific section."""
    return reverse("exe_config", args=[section_slug])
