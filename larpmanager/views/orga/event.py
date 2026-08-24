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

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Prefetch, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import clear_run_cache_and_media
from larpmanager.cache.config import get_event_config, save_single_config
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.run import get_cache_run
from larpmanager.forms.event import (
    ExeEventForm,
    OrgaEventForm,
    OrgaFeatureForm,
    OrgaRunDatesForm,
    OrgaRunDevelopmentForm,
    OrgaRunForm,
    OrgaRunRegistrationForm,
)
from larpmanager.forms.miscellanea import OrgaCopyForm
from larpmanager.forms.writing import UploadElementsForm
from larpmanager.mail.base import send_role_invite_email
from larpmanager.models.access import AssociationPermission, AssociationRole, EventPermission, EventRole, RoleInvite
from larpmanager.models.base import Feature
from larpmanager.models.event import Event, EventButton, EventText, Run
from larpmanager.utils.auth.permission import get_event_roles, get_index_event_permissions
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import clear_messages, get_feature, is_rate_limited
from larpmanager.utils.core.copy import copy, get_copy_sections, read_copy_picks
from larpmanager.utils.core.exceptions import RedirectError, UserPermissionError
from larpmanager.utils.edit.backend import backend_edit, save_log
from larpmanager.utils.edit.orga import OrgaAction, orga_delete, orga_edit, orga_new
from larpmanager.utils.io.download import _get_column_names, prepare_backup, zip_exports
from larpmanager.utils.io.restore import execute_restore, load_restore_temp, preview_restore, save_restore_temp
from larpmanager.utils.io.template import build_upload_template
from larpmanager.utils.io.upload import go_upload
from larpmanager.utils.services.event import reset_all_run
from larpmanager.utils.users.deadlines import check_run_deadlines

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


@login_required
def orga_event(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Event management view for organizers."""
    context = check_event_context(request, event_slug, "orga_event")
    return full_event_edit(context, request, context["event"], context["run"], is_executive=False)


def _save_event_run(
    context: dict,
    run: Run | None,
    run_form: OrgaRunForm,
    saved_event: Event,
    on_created_callback: callable | None,
) -> Run:
    """Save the run for a created or edited event, returning the saved run."""
    if context["is_creation"]:
        # Get the run created automatically, and update it with form data
        saved_run = saved_event.runs.first()
        for field in run_form.cleaned_data:
            setattr(saved_run, field, run_form.cleaned_data[field])
        saved_run.save()
        save_log(context, Run, saved_run, None)
        if on_created_callback:
            on_created_callback(saved_event)
    else:
        # For editing, just save the run form normally
        saved_run = run_form.save()
        save_log(context, Run, saved_run, run.uuid)
    return saved_run


def _full_event_edit_success_response(
    request: HttpRequest,
    context: dict,
    saved_run: Run,
    is_frame: bool,  # noqa: FBT001
    *,
    is_executive: bool,
) -> HttpResponse:
    """Return the response for a successful full_event_edit save."""
    if is_frame:
        if context.get("is_creation"):
            context["redirect_url"] = reverse("manage", kwargs={"event_slug": saved_run.get_slug()})
        return render(request, "elements/dashboard/form_success.html", context)

    if is_executive and not context.get("is_creation"):
        return redirect("manage")

    return redirect("manage", event_slug=saved_run.get_slug())


def full_event_edit(
    context: dict,
    request: HttpRequest,
    event: Event | None,
    run: Run | None,
    *,
    is_executive: bool = False,
    on_created_callback: callable | None = None,
) -> HttpResponse:
    """Comprehensive event editing with validation.

    Handles both GET requests for displaying edit forms and POST requests for
    processing form submissions. Validates and saves both event and run forms
    when submitted. Supports both creation (event=None, run=None) and editing.

    Args:
        context: Context dictionary for template rendering
        request: HTTP request object containing form data
        event: Event instance to edit, or None for creation
        run: Run instance associated with the event, or None for creation
        is_executive: Whether this is an executive-level edit, defaults to False
        on_created_callback: Optional callback(event, run) called after creation

    Returns:
        HttpResponse: Either the edit form template for GET requests or a
        redirect response after successful form submission

    """
    is_frame = request.GET.get("frame") == "1" or request.POST.get("frame") == "1"
    context["frame"] = is_frame

    if event:
        context["is_creation"] = False
        context["num"] = event.uuid
        context["name"] = event.name
    else:
        context["is_creation"] = True

    if is_executive:
        event_form_class = ExeEventForm
    else:
        event_form_class = OrgaEventForm
        context["nonum"] = 1

    if request.method == "POST":
        # Create form instances with POST data and file uploads
        event_form = event_form_class(request.POST, request.FILES, instance=event, context=context, prefix="form1")
        run_form = OrgaRunForm(request.POST, request.FILES, instance=run, context=context, prefix="form2")

        # Validate both forms before saving
        if event_form.is_valid() and run_form.is_valid():
            # Save event first
            saved_event = event_form.save()
            save_log(context, Event, saved_event, event.uuid if event else None)

            saved_run = _save_event_run(context, run, run_form, saved_event, on_created_callback)

            # Show success message and redirect based on access level
            messages.success(request, _("Operation completed!"))
            return _full_event_edit_success_response(request, context, saved_run, is_frame, is_executive=is_executive)
    else:
        # Create empty forms for GET requests
        event_form = event_form_class(instance=event, context=context, prefix="form1")
        run_form = OrgaRunForm(instance=run, context=context, prefix="form2")

    # Add forms and metadata to template context
    context["form1"] = event_form
    context["form2"] = run_form
    context["num"] = event.uuid if event else "0"
    context["type"] = "event"

    return render(request, "larpmanager/orga/edit_multi.html", context)


@login_required
def orga_roles(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle organization roles management for an event."""
    # Check if user has permission to manage roles for this event
    context = check_event_context(request, event_slug, "orga_roles")

    def def_callback(event_context: dict) -> EventRole:
        """Create default 'Organizer' role for event."""
        return EventRole.objects.create(event=event_context["event"], number=1, name="Organizer")

    # Prepare the roles list with permissions and existing roles
    prepare_roles_list(context, EventPermission, EventRole.objects.filter(event=context["event"]), def_callback)

    # Attach pending (unredeemed) invites to each role for display
    for role in context["list"]:
        role.pending_invites = RoleInvite.objects.filter(
            event_role=role, redeemed_by__isnull=True, deleted__isnull=True
        )

    return render(request, "larpmanager/orga/roles.html", context)


def prepare_roles_list(
    context: dict,
    permission_type: type[EventPermission | AssociationPermission],
    role_queryset: QuerySet[EventRole] | QuerySet[AssociationRole],
    default_callback: Callable[[dict], EventRole | AssociationRole],
) -> None:
    """Prepare role list with permissions organized by module for display.

    Builds a formatted list of roles with their members and grouped permissions,
    handling special formatting for administrator roles and module organization.
    """
    permissions_queryset = permission_type.objects.select_related("feature", "feature__module").order_by(
        F("feature__module__order").asc(nulls_last=True),
        F("feature__order").asc(nulls_last=True),
        "feature__name",
        "name",
    )
    roles = role_queryset.order_by("number").prefetch_related(
        Prefetch("permissions", queryset=permissions_queryset),
        "members",
    )
    context["list"] = []
    if not roles:
        context["list"].append(default_callback(context))
    for role in roles:
        role.members_list = ", ".join([str(member) for member in role.members.all()])
        if role.number == "1":
            role.perms_list = "All"
        else:
            permissions_by_module = defaultdict(list)
            for permission in role.permissions.all():
                # Check active_if config for event permissions
                if permission.active_if and context.get("event"):
                    config_value = get_event_config(context["event"].id, permission.active_if, context=context)
                    if not config_value:
                        continue

                permissions_by_module[permission.feature.module].append(permission)

            sorted_modules = sorted(
                permissions_by_module.keys(),
                key=lambda module: (
                    float("inf") if module is None else (module.order if module.order is not None else float("inf")),
                    "" if module is None else module.name,
                ),
            )

            formatted_permissions = []
            for module in sorted_modules:
                permissions_sorted = sorted(permissions_by_module[module], key=lambda permission: permission.number)
                permissions_names = ", ".join(
                    [str(_(event_permission.name)) for event_permission in permissions_sorted],
                )
                formatted_permissions.append(f"<b>{module}</b> ({permissions_names})")
            role.perms_list = ", ".join(formatted_permissions)

        context["list"].append(role)


@login_required
def orga_roles_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Edit organization event role."""
    return orga_new(request, event_slug, OrgaAction.ROLES)


@login_required
def orga_roles_edit(request: HttpRequest, event_slug: str, role_uuid: str) -> HttpResponse:
    """Edit organization event role."""
    return orga_edit(request, event_slug, OrgaAction.ROLES, role_uuid)


@login_required
def orga_roles_delete(request: HttpRequest, event_slug: str, role_uuid: str) -> HttpResponse:
    """Delete organization event role."""
    return orga_delete(
        request,
        event_slug,
        OrgaAction.ROLES,
        role_uuid,
    )


@login_required
def orga_roles_invite(request: HttpRequest, event_slug: str, role_uuid: str) -> HttpResponse:
    """Send email invitation to join an event role."""
    context = check_event_context(request, event_slug, "orga_roles")
    role = get_object_or_404(EventRole, uuid=role_uuid, event=context["event"])
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        if email:
            invite = RoleInvite.objects.create(
                email=email,
                association_id=context["association_id"],
                event=context["event"],
                event_role=role,
                invited_by=request.user.member,
            )
            send_role_invite_email(invite)
            messages.success(request, _("Invitation sent to %(email)s") % {"email": email})
        return redirect("orga_roles", event_slug=event_slug)
    context["role"] = role
    context["back_url"] = reverse("orga_roles", kwargs={"event_slug": event_slug})
    return render(request, "larpmanager/manage/roles_invite.html", context)


@login_required
def orga_appearance(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle appearance configuration for an event."""
    return orga_edit(request, event_slug, OrgaAction.APPEARANCE)


@login_required
def orga_run(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render the event run edit form with cached run data."""
    # Retrieve cached run data and render edit form
    run_uuid = get_cache_run(request.association["id"], event_slug)
    return orga_edit(request, event_slug, OrgaAction.EVENT, run_uuid)


@login_required
def orga_texts(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render event texts management page with texts ordered by type, default flag, and language."""
    context = check_event_context(request, event_slug, "orga_texts")
    context["list"] = EventText.objects.filter(event_id=context["event"].id).order_by("typ", "default", "language")
    return render(request, "larpmanager/orga/texts.html", context)


@login_required
def orga_texts_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create an organization event text entry."""
    return orga_new(request, event_slug, OrgaAction.TEXTS)


@login_required
def orga_texts_edit(request: HttpRequest, event_slug: str, text_uuid: str) -> HttpResponse:
    """Edit an organization event text entry."""
    return orga_edit(request, event_slug, OrgaAction.TEXTS, text_uuid)


@login_required
def orga_texts_delete(request: HttpRequest, event_slug: str, text_uuid: str) -> HttpResponse:
    """Delete text for event."""
    return orga_delete(request, event_slug, OrgaAction.TEXTS, text_uuid)


@login_required
def orga_buttons(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display event buttons management page for organizers."""
    context = check_event_context(request, event_slug, "orga_buttons")
    context["list"] = EventButton.objects.filter(event_id=context["event"].id).order_by("order")
    return render(request, "larpmanager/orga/buttons.html", context)


@login_required
def orga_buttons_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a specific button configuration for an event."""
    return orga_new(request, event_slug, OrgaAction.BUTTONS)


@login_required
def orga_buttons_edit(request: HttpRequest, event_slug: str, button_uuid: str) -> HttpResponse:
    """Edit a specific button configuration for an event."""
    return orga_edit(request, event_slug, OrgaAction.BUTTONS, button_uuid)


@login_required
def orga_buttons_delete(request: HttpRequest, event_slug: str, button_uuid: str) -> HttpResponse:
    """Delete button for event."""
    return orga_delete(request, event_slug, OrgaAction.BUTTONS, button_uuid)


@login_required
def orga_config(
    request: HttpRequest,
    event_slug: str,
    section: str | None = None,  # noqa: ARG001
) -> HttpResponse:
    """Configure organization settings with optional section navigation."""
    return orga_edit(request, event_slug, OrgaAction.CONFIG)


@login_required
def orga_publication(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Manage external promotion metadata for an event."""
    return orga_edit(request, event_slug, OrgaAction.PROMOTION)


@login_required
def orga_features(request: HttpRequest, event_slug: str) -> Any:
    """Manage event features activation and configuration.

    Args:
        request: HTTP request object
        event_slug: Event slug

    Returns:
        HttpResponse: Rendered features form or redirect after activation

    """
    context = check_event_context(request, event_slug, "orga_features")
    context["event_form"] = True
    context["add_another"] = False
    if backend_edit(request, context, OrgaFeatureForm):
        context["new_features"] = Feature.objects.filter(
            pk__in=context["form"].added_features,
            after_link__isnull=False,
        )
        if not context["new_features"]:
            return redirect("manage", event_slug=context["run"].get_slug())
        for el in context["new_features"]:
            el.follow_link = _orga_feature_after_link(el, event_slug)
        if len(context["new_features"]) == 1:
            feature = context["new_features"][0]
            msg = _("Feature %(name)s activated!") % {"name": feature.name} + " " + feature.after_text
            clear_messages(request)
            messages.success(request, msg)
            return redirect(feature.follow_link)

        context["features"] = get_event_features(context["event"].id)
        get_index_event_permissions(request, context, event_slug)
        return render(request, "larpmanager/manage/features.html", context)
    return render(request, "larpmanager/orga/edit.html", context)


def orga_features_go(request: HttpRequest, event_slug: str, slug: str, *, to_active: bool = True) -> Feature:
    """Toggle a feature for an event.

    Args:
        request: The HTTP request object
        event_slug: The event slug identifier
        slug: The feature slug to toggle
        to_active: Whether to activate (True) or deactivate (False) the feature

    Returns:
        The feature object that was toggled

    Raises:
        Http404: If the feature is an overall feature (not event-specific)
        RedirectError: If the association is in lite/demo mode and activation is attempted

    """
    context = check_event_context(request, event_slug, "orga_features")

    # Block feature activation in lite/demo mode
    if to_active and context.get("lite_mode"):
        messages.error(request, _("Features cannot be activated in lite mode, complete the activation checklist first"))
        msg = "manage"
        raise RedirectError(msg, kwargs={"event_slug": event_slug})

    # Get the feature from context using the slug
    get_feature(context, slug)

    # Check if feature is overall - these cannot be toggled per event
    if context["feature"].overall:
        msg = "overall feature!"
        raise Http404(msg)

    # Get current event features and target feature ID
    current_event_feature_ids = list(context["event"].features.values_list("id", flat=True))
    target_feature_id = context["feature"].id

    # Clear cache and media for the current run
    clear_run_cache_and_media(context["run"].id)

    # Handle feature activation/deactivation logic
    if to_active:
        if target_feature_id not in current_event_feature_ids:
            for dep_id in Feature.get_all_dependencies([target_feature_id]):
                context["event"].features.add(dep_id)
            message = _("Feature %(name)s activated!")
        else:
            message = _("Feature %(name)s already activated!")
    elif target_feature_id not in current_event_feature_ids:
        message = _("Feature %(name)s already deactivated!")
    else:
        context["event"].features.remove(target_feature_id)
        message = _("Feature %(name)s deactivated!")

    # Save the event and update cached features for child events
    context["event"].save()
    for child_event in Event.objects.filter(parent=context["event"]):
        child_event.save()

    # Format and display the success message
    message = message % {"name": _(context["feature"].name)}
    if context["feature"].after_text:
        message += " " + context["feature"].after_text
    messages.success(request, message)

    return context["feature"]


def _orga_feature_after_link(feature: Feature, event_slug: str) -> str:
    """Build redirect URL after feature interaction."""
    after_link = feature.after_link

    # Use reverse if after_link is a named URL pattern starting with "orga"
    if after_link and after_link.startswith("orga"):
        return reverse(after_link, kwargs={"event_slug": event_slug})

    # Otherwise append after_link as fragment to manage URL
    return reverse("manage", kwargs={"event_slug": event_slug}) + (after_link or "")


@login_required
def orga_features_on(
    request: HttpRequest,
    event_slug: str,
    slug: str,
) -> HttpResponseRedirect:
    """Toggle feature on for an event."""
    feature = orga_features_go(request, event_slug, slug, to_active=True)
    return redirect(_orga_feature_after_link(feature, event_slug))


@login_required
def orga_features_off(request: HttpRequest, event_slug: str, slug: str) -> HttpResponse:
    """Disable a feature for an event."""
    orga_features_go(request, event_slug, slug, to_active=False)
    return redirect("manage", event_slug=event_slug)


def _orga_config_after_link(event_slug: str) -> str:
    """Build the configuration page URL, jumping to the section of the toggled option."""
    kwargs = {"event_slug": event_slug}
    return reverse("orga_config", kwargs=kwargs)


def orga_config_go(request: HttpRequest, event_slug: str, slug: str, *, to_active: bool = True) -> None:
    """Toggle a boolean configuration option for an event.

    Args:
        request: The HTTP request object
        event_slug: The event slug identifier
        slug: The name of the configuration option to toggle
        to_active: Whether to activate (True) or deactivate (False) the option

    """
    context = check_event_context(request, event_slug, "orga_config")
    context["request"] = request

    # Configs of campaign children are held by the parent event
    event = context["event"]
    config_target = event.parent if event.parent_id else event

    # Skip the update if the option already has the requested value
    if get_event_config(config_target.id, slug) == to_active:
        message = _("Option %(name)s already activated!") if to_active else _("Option %(name)s already deactivated!")
    else:
        save_single_config(config_target, slug, str(to_active))
        config_target.save()
        clear_run_cache_and_media(context["run"].id)
        message = _("Option %(name)s activated!") if to_active else _("Option %(name)s deactivated!")

    messages.success(request, message % {"name": slug})


@login_required
def orga_config_on(request: HttpRequest, event_slug: str, slug: str) -> HttpResponseRedirect:
    """Activate a configuration option and redirect to the configuration page."""
    orga_config_go(request, event_slug, slug, to_active=True)
    return redirect(_orga_config_after_link(event_slug))


@login_required
def orga_config_off(request: HttpRequest, event_slug: str, slug: str) -> HttpResponseRedirect:
    """Deactivate a configuration option and redirect to the configuration page."""
    orga_config_go(request, event_slug, slug, to_active=False)
    return redirect(_orga_config_after_link(event_slug))


@login_required
def orga_deadlines(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display deadlines for a specific run."""
    # Check permissions and get event context
    context = check_event_context(request, event_slug, "orga_deadlines")

    # Get deadline status for the run
    context["res"] = check_run_deadlines([context["run"]])[0]

    return render(request, "larpmanager/orga/deadlines.html", context)


@login_required
def orga_quick(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle quick event setup form."""
    return orga_edit(request, event_slug, OrgaAction.QUICK)


@login_required
def orga_preferences(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle organizer preferences editing form."""
    return orga_edit(request, event_slug, OrgaAction.PREFERENCES)


def _check_organizer(request: HttpRequest, context: dict, event_slug: str) -> None:
    is_organizer, _perms, _roles = get_event_roles(request, context, event_slug)
    if not is_organizer and 1 not in context.get("association_role", {}):
        raise UserPermissionError


@login_required
def orga_backup(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Prepare event backup for download."""
    context = check_event_context(request, event_slug, "orga_event")
    _check_organizer(request, context, event_slug)
    if is_rate_limited(f"orga_backup_{context['event'].id}"):
        messages.error(request, _("Please wait before retrying."))
        return redirect("manage", event_slug=event_slug)
    return prepare_backup(context)


@login_required
def orga_restore(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Restore event data from a previously exported backup ZIP."""
    context = check_event_context(request, event_slug, "orga_event")
    _check_organizer(request, context, event_slug)

    if request.method == "POST":
        if "confirm" in request.POST:
            if is_rate_limited(f"orga_restore_{context['event'].id}"):
                messages.error(request, _("Please wait before retrying."))
                return render(request, "larpmanager/orga/restore.html", context)
            temp_key = request.POST.get("temp_key", "")
            zip_bytes = load_restore_temp(temp_key)
            if zip_bytes is None:
                messages.error(request, _("Session expired, please upload the file again."))
                return render(request, "larpmanager/orga/restore.html", context)
            try:
                context["logs"] = execute_restore(context, zip_bytes)
                messages.success(request, _("Completed!"))
                return render(request, "larpmanager/orga/uploads.html", context)
            except Exception as exc:
                logger.exception("Restore execute error")
                messages.error(request, _("Error") + f": {exc}")
                return render(request, "larpmanager/orga/restore.html", context)

        elif "zip_file" in request.FILES:
            zip_bytes = request.FILES["zip_file"].read()
            try:
                sections, unknown_files = preview_restore(context, zip_bytes)
                temp_key = save_restore_temp(zip_bytes)
                context["sections"] = sections
                context["unknown_files"] = unknown_files
                context["temp_key"] = temp_key
                return render(request, "larpmanager/orga/restore_preview.html", context)
            except Exception as exc:
                logger.exception("Restore preview error")
                messages.error(request, _("Error reading backup file") + f": {exc}")

    return render(request, "larpmanager/orga/restore.html", context)


@login_required
def orga_upload(request: HttpRequest, event_slug: str, upload_type: str) -> HttpResponse:
    """Handle file uploads for organizers with element processing.

    This function manages the upload process for various types of elements
    (characters, items, etc.) in LARP events. It validates permissions,
    processes uploaded files, and returns appropriate responses.

    Args:
        request: Django HTTP request object containing file data and POST parameters
        event_slug: Event slug identifier for the specific event
        upload_type: Type of elements to upload (e.g., 'characters', 'items')

    Returns:
        HttpResponse: Either the upload form page or processing results page

    Raises:
        Exception: Any error during file processing is caught and displayed to user

    """
    # Check user permissions and get event context. The matchmaker form reuses the
    # registration form's permission, since matchmaker questions are RegistrationQuestion
    # rows managed through the same "orga_registration_form" screen.
    permission_type = "registration_form" if upload_type == "matchmaker_form" else upload_type
    context = check_event_context(request, event_slug, f"orga_{permission_type}")
    context["typ"] = upload_type.rstrip("s")
    context["name"] = context["typ"]

    # Get column names for the upload template
    _get_column_names(context)

    # Handle POST request (file upload submission)
    if request.POST:
        form = UploadElementsForm(request.POST, request.FILES)

        # Prepare redirect URL for after processing
        if upload_type == "matchmaker_form":
            redr = reverse("orga_registration_form", args=[context["run"].get_slug(), "matchmaker"])
        else:
            redr = reverse(f"orga_{upload_type}", args=[context["run"].get_slug()])

        if form.is_valid():
            try:
                # Process the uploaded file and get processing logs
                context["logs"] = go_upload(context, form)
                context["redr"] = redr

                # Show success message and render results page
                messages.success(request, _("Elements uploaded!"))
                return render(request, "larpmanager/orga/uploads.html", context)

            except Exception as exp:
                # Log the full traceback and show error to user
                logger.exception("Upload error")
                messages.error(request, _("Unknown error while uploading.") + f": {exp}")

            # Redirect back to the main page on error or completion
            return HttpResponseRedirect(redr)
    else:
        # Handle GET request (show upload form)
        form = UploadElementsForm()

    # Add form to context and render upload page
    context["form"] = form
    return render(request, "larpmanager/orga/upload.html", context)


@login_required
def orga_upload_template(request: HttpRequest, event_slug: str, upload_type: str) -> HttpResponse:
    """Generate and download template files for data upload.

    Args:
        request: HTTP request object containing user session and metadata
        event_slug: Event identifier string used to locate the specific event
        upload_type: Template type specifying which template to generate. Valid values:
            - 'writing': Character writing elements template
            - 'registration': Event registration template
            - 'exp_abilitie': Player experience abilities template
            - 'form': Generic form template

    Returns:
        HttpResponse: ZIP file download response containing the generated template files

    Raises:
        PermissionDenied: If user lacks permission to access the specified event
        ValidationError: If template type is invalid or event not found

    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug)
    context["typ"] = upload_type

    # Package exports into ZIP file and return as download response
    return zip_exports(context, build_upload_template(context, upload_type), "template")


@login_required
def orga_reload_cache(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Reset all cache entries for the specified event run."""
    # Verify user permissions and get event context
    context = check_event_context(request, event_slug)

    # Check it's an organizer
    _check_organizer(request, context, event_slug)

    if is_rate_limited(f"orga_reload_cache_{context['event'].id}"):
        messages.error(request, _("Please wait before retrying."))
        return redirect("manage", event_slug=context["run"].get_slug())

    # Reset everything
    reset_all_run(context["run"].id)

    # Notify user of successful cache reset
    messages.success(request, _("Cache reset!"))
    return redirect("manage", event_slug=context["run"].get_slug())


def _orga_run_quick_edit(
    request: HttpRequest,
    event_slug: str,
    form_class: type[OrgaRunForm],
    success_message: str,
) -> HttpResponse:
    """Generic quick edit handler for run fields in a modal.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier
        form_class: Form class to use for editing
        success_message: Message to display on successful save

    Returns:
        HttpResponse: Rendered form or redirect after save

    """
    context = check_event_context(request, event_slug, "orga_event")
    context["is_modal"] = request.GET.get("frame") == "1" or request.POST.get("frame") == "1"

    if request.method == "POST":
        form = form_class(request.POST, instance=context["run"], context=context)
        if form.is_valid():
            saved_run = form.save()
            save_log(context, Run, saved_run, context["run"].uuid)
            messages.success(request, success_message)
            if context["is_modal"]:
                return render(request, "elements/dashboard/form_success.html", context)
            return redirect("manage", event_slug=event_slug)
    else:
        form = form_class(instance=context["run"], context=context)

    context["form"] = form
    if context["is_modal"]:
        return render(request, "elements/dashboard/form_frame.html", context)
    return render(request, "larpmanager/orga/edit.html", context)


@login_required
def orga_run_quick_edit_dates(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Quick edit for run dates in a modal."""
    return _orga_run_quick_edit(request, event_slug, OrgaRunDatesForm, _("Dates updated!"))


@login_required
def orga_run_quick_edit_development(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Quick edit for run development status in a modal."""
    return _orga_run_quick_edit(request, event_slug, OrgaRunDevelopmentForm, _("Status updated!"))


@login_required
def orga_run_quick_edit_registration(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Quick edit for run registration status in a modal."""
    return _orga_run_quick_edit(request, event_slug, OrgaRunRegistrationForm, _("Registration settings updated!"))


@login_required
def orga_copy(request: HttpRequest, event_slug: str) -> Any:
    """Handle event copying functionality for organizers.

    The copy is done in two steps: first the source event and the types of elements are
    chosen, then the single elements of each type.

    Args:
        request: HTTP request object
        event_slug: Event slug identifier

    Returns:
        HttpResponse: Rendered copy form template or redirect after successful copy

    """
    context = check_event_context(request, event_slug, "orga_copy")

    if request.method == "POST":
        form = OrgaCopyForm(request.POST, request.FILES, context=context)
        if form.is_valid():
            response = _process_copy_form(request, context, form)
            if response:
                return response

    else:
        form = OrgaCopyForm(context=context)

    context["form"] = form

    return render(request, "larpmanager/orga/copy.html", context)


def _process_copy_form(request: HttpRequest, context: dict, form: OrgaCopyForm) -> Any:
    """Run the copy, or show the selection of single elements when it is still missing."""
    parent = Event.objects.get(pk=form.cleaned_data["parent"], association_id=context["association_id"])
    targets = form.cleaned_data["target"]

    if request.POST.get("step") != "elements":
        sections = get_copy_sections(parent.id, targets)
        if sections:
            context["copy_sections"] = sections
            context["copy_parent"] = parent.id
            context["copy_targets"] = targets
            return render(request, "larpmanager/orga/copy_elements.html", context)

    picks = read_copy_picks(request, targets)
    # Skip the types for which no element has been selected
    targets = [key for key in targets if key not in picks or picks[key]]

    copy(request, context, parent, context["event"], targets, picks)
    return None
