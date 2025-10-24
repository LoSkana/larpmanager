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
import traceback
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Prefetch
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import clear_run_cache_and_media
from larpmanager.cache.run import get_cache_run
from larpmanager.forms.event import (
    OrgaAppearanceForm,
    OrgaConfigForm,
    OrgaEventButtonForm,
    OrgaEventForm,
    OrgaEventRoleForm,
    OrgaEventTextForm,
    OrgaFeatureForm,
    OrgaPreferencesForm,
    OrgaQuickSetupForm,
    OrgaRunForm,
)
from larpmanager.forms.writing import UploadElementsForm
from larpmanager.models.access import EventPermission, EventRole
from larpmanager.models.base import Feature
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event, EventButton, EventText, Run
from larpmanager.models.form import BaseQuestionType, QuestionApplicable, RegistrationQuestionType, WritingQuestionType
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Character, Faction, Plot
from larpmanager.utils.common import clear_messages, get_feature
from larpmanager.utils.deadlines import check_run_deadlines
from larpmanager.utils.download import (
    _get_column_names,
    export_abilities,
    export_character_form,
    export_data,
    export_event,
    export_registration_form,
    export_tickets,
    zip_exports,
)
from larpmanager.utils.edit import backend_edit, orga_edit
from larpmanager.utils.event import check_event_permission, get_index_event_permissions
from larpmanager.utils.upload import go_upload


@login_required
def orga_event(request, s):
    ctx = check_event_permission(request, s, "orga_event")
    return full_event_edit(ctx, request, ctx["event"], ctx["run"], exe=False)


def full_event_edit(ctx: dict, request: HttpRequest, event: Event, run: Run, exe: bool = False) -> HttpResponse:
    """Comprehensive event editing with validation.

    Handles both GET requests for displaying edit forms and POST requests for
    processing form submissions. Validates and saves both event and run forms
    when submitted.

    Args:
        ctx: Context dictionary for template rendering
        request: HTTP request object containing form data
        event: Event instance to edit
        run: Run instance associated with the event
        exe: Whether this is an executive-level edit, defaults to False

    Returns:
        HttpResponse: Either the edit form template for GET requests or a
        redirect response after successful form submission
    """
    # Disable numbering in the template context
    ctx["nonum"] = 1

    if request.method == "POST":
        # Create form instances with POST data and file uploads
        form_event = OrgaEventForm(request.POST, request.FILES, instance=event, ctx=ctx, prefix="form1")
        form_run = OrgaRunForm(request.POST, request.FILES, instance=run, ctx=ctx, prefix="form2")

        # Validate both forms before saving
        if form_event.is_valid() and form_run.is_valid():
            # Save both forms to database
            form_event.save()
            form_run.save()

            # Show success message and redirect based on access level
            messages.success(request, _("Operation completed") + "!")
            if exe:
                return redirect("manage")
            else:
                return redirect("manage", s=run.get_slug())
    else:
        # Create empty forms for GET requests
        form_event = OrgaEventForm(instance=event, ctx=ctx, prefix="form1")
        form_run = OrgaRunForm(instance=run, ctx=ctx, prefix="form2")

    # Add forms and metadata to template context
    ctx["form1"] = form_event
    ctx["form2"] = form_run
    ctx["num"] = event.id
    ctx["type"] = "event"

    return render(request, "larpmanager/orga/edit_multi.html", ctx)


@login_required
def orga_roles(request: HttpRequest, s: str) -> HttpResponse:
    """Handle organization roles management for an event."""
    # Check if user has permission to manage roles for this event
    ctx = check_event_permission(request, s, "orga_roles")

    def def_callback(ctx):
        # Create default "Organizer" role if none exist
        return EventRole.objects.create(event=ctx["event"], number=1, name="Organizer")

    # Prepare the roles list with permissions and existing roles
    prepare_roles_list(ctx, EventPermission, EventRole.objects.filter(event=ctx["event"]), def_callback)

    return render(request, "larpmanager/orga/roles.html", ctx)


def prepare_roles_list(ctx, permission_typ, role_query, def_callback):
    """Prepare role list with permissions organized by module for display.

    Builds a formatted list of roles with their members and grouped permissions,
    handling special formatting for administrator roles and module organization.
    """
    qs_perm = permission_typ.objects.select_related("feature", "feature__module").order_by(
        F("feature__module__order").asc(nulls_last=True),
        F("feature__order").asc(nulls_last=True),
        "feature__name",
        "name",
    )
    roles = role_query.order_by("number").prefetch_related(Prefetch("permissions", queryset=qs_perm))
    ctx["list"] = []
    if not roles:
        ctx["list"].append(def_callback(ctx))
    for role in roles:
        role.members_list = ", ".join([str(mb) for mb in role.members.all()])
        if role.number == "1":
            role.perms_list = "All"
        else:
            buckets = defaultdict(list)
            for p in role.permissions.all():
                buckets[p.feature.module].append(p)

            modules = sorted(
                buckets.keys(),
                key=lambda m: (
                    float("inf") if m is None else (m.order if m.order is not None else float("inf")),
                    "" if m is None else m.name,
                ),
            )

            aux = []
            for module in modules:
                perms_sorted = sorted(buckets[module], key=lambda p: p.number)
                perms = ", ".join([str(_(ep.name)) for ep in perms_sorted])
                aux.append(f"<b>{module}</b> ({perms})")
            role.perms_list = ", ".join(aux)

        ctx["list"].append(role)


@login_required
def orga_roles_edit(request, s, num):
    return orga_edit(request, s, "orga_roles", OrgaEventRoleForm, num)


@login_required
def orga_appearance(request, s):
    return orga_edit(request, s, "orga_appearance", OrgaAppearanceForm, None, "manage", add_ctx={"add_another": False})


@login_required
def orga_run(request, s):
    run = get_cache_run(request.assoc["id"], s)
    return orga_edit(request, s, "orga_event", OrgaRunForm, run, "manage", add_ctx={"add_another": False})


@login_required
def orga_texts(request: HttpRequest, s: str) -> HttpResponse:
    """Render event texts management page with texts ordered by type, default flag, and language."""
    ctx = check_event_permission(request, s, "orga_texts")
    ctx["list"] = EventText.objects.filter(event_id=ctx["event"].id).order_by("typ", "default", "language")
    return render(request, "larpmanager/orga/texts.html", ctx)


@login_required
def orga_texts_edit(request, s, num):
    return orga_edit(request, s, "orga_texts", OrgaEventTextForm, num)


@login_required
def orga_buttons(request: HttpRequest, s: str) -> HttpResponse:
    """Display event buttons management page for organizers."""
    ctx = check_event_permission(request, s, "orga_buttons")
    ctx["list"] = EventButton.objects.filter(event_id=ctx["event"].id).order_by("number")
    return render(request, "larpmanager/orga/buttons.html", ctx)


@login_required
def orga_buttons_edit(request, s, num):
    return orga_edit(request, s, "orga_buttons", OrgaEventButtonForm, num)


@login_required
def orga_config(
    request: HttpRequest,
    s: str,
    section: str | None = None,
) -> HttpResponse:
    """Configure organization settings with optional section navigation."""
    # Prepare context with optional section jump
    add_ctx = {"jump_section": section} if section else {}
    add_ctx["add_another"] = False

    # Delegate to orga_edit with config form
    return orga_edit(request, s, "orga_config", OrgaConfigForm, None, "manage", add_ctx=add_ctx)


@login_required
def orga_features(request, s):
    """Manage event features activation and configuration.

    Args:
        request: HTTP request object
        s: Event slug

    Returns:
        HttpResponse: Rendered features form or redirect after activation
    """
    ctx = check_event_permission(request, s, "orga_features")
    ctx["add_another"] = False
    if backend_edit(request, ctx, OrgaFeatureForm, None, afield=None, assoc=False):
        ctx["new_features"] = Feature.objects.filter(pk__in=ctx["form"].added_features, after_link__isnull=False)
        if not ctx["new_features"]:
            return redirect("manage", s=ctx["run"].get_slug())
        for el in ctx["new_features"]:
            el.follow_link = _orga_feature_after_link(el, s)
        if len(ctx["new_features"]) == 1:
            feature = ctx["new_features"][0]
            msg = _("Feature %(name)s activated") % {"name": feature.name} + "! " + feature.after_text
            clear_messages(request)
            messages.success(request, msg)
            return redirect(feature.follow_link)

        get_index_event_permissions(ctx, request, s)
        return render(request, "larpmanager/manage/features.html", ctx)
    return render(request, "larpmanager/orga/edit.html", ctx)


def orga_features_go(request: HttpRequest, ctx: dict, slug: str, on: bool = True) -> Feature:
    """Toggle a feature for an event.

    Args:
        request: The HTTP request object
        ctx: Context dictionary containing event and feature information
        slug: The feature slug to toggle
        on: Whether to activate (True) or deactivate (False) the feature

    Returns:
        The feature object that was toggled

    Raises:
        Http404: If the feature is an overall feature (not event-specific)
    """
    # Get the feature from context using the slug
    get_feature(ctx, slug)

    # Check if feature is overall - these cannot be toggled per event
    if ctx["feature"].overall:
        raise Http404("overall feature!")

    # Get current event features and target feature ID
    feat_id = list(ctx["event"].features.values_list("id", flat=True))
    f_id = ctx["feature"].id

    # Clear cache and media for the current run
    clear_run_cache_and_media(ctx["run"])

    # Handle feature activation/deactivation logic
    if on:
        if f_id not in feat_id:
            ctx["event"].features.add(f_id)
            msg = _("Feature %(name)s activated") + "!"
        else:
            msg = _("Feature %(name)s already activated") + "!"
    elif f_id not in feat_id:
        msg = _("Feature %(name)s already deactivated") + "!"
    else:
        ctx["event"].features.remove(f_id)
        msg = _("Feature %(name)s deactivated") + "!"

    # Save the event and update cached features for child events
    ctx["event"].save()
    for ev in Event.objects.filter(parent=ctx["event"]):
        ev.save()

    # Format and display the success message
    msg = msg % {"name": _(ctx["feature"].name)}
    if ctx["feature"].after_text:
        msg += " " + ctx["feature"].after_text
    messages.success(request, msg)

    return ctx["feature"]


def _orga_feature_after_link(feature: Feature, s: str) -> str:
    """Build redirect URL after feature interaction.

    Args:
        feature: Feature object with after_link attribute
        s: Event slug identifier

    Returns:
        Full URL path for redirect
    """
    after_link = feature.after_link

    # Use reverse if after_link is a named URL pattern starting with "orga"
    if after_link and after_link.startswith("orga"):
        return reverse(after_link, kwargs={"s": s})

    # Otherwise append after_link as fragment to manage URL
    return reverse("manage", kwargs={"s": s}) + (after_link or "")


@login_required
def orga_features_on(
    request: HttpRequest,
    s: str,
    slug: str,
) -> HttpResponseRedirect:
    """Toggle feature on for an event."""
    # Check user has permission to manage features
    ctx = check_event_permission(request, s, "orga_features")

    # Enable the feature
    feature = orga_features_go(request, ctx, slug, on=True)

    # Redirect to appropriate page
    return redirect(_orga_feature_after_link(feature, s))


@login_required
def orga_features_off(request: HttpRequest, s: str, slug: str) -> HttpResponse:
    """Disable a feature for an event."""
    ctx = check_event_permission(request, s, "orga_features")
    orga_features_go(request, ctx, slug, on=False)
    return redirect("manage", s=s)


@login_required
def orga_deadlines(request: HttpRequest, s: str) -> HttpResponse:
    """Display deadlines for a specific run."""
    # Check permissions and get event context
    ctx = check_event_permission(request, s, "orga_deadlines")

    # Get deadline status for the run
    ctx["res"] = check_run_deadlines([ctx["run"]])[0]

    return render(request, "larpmanager/orga/deadlines.html", ctx)


@login_required
def orga_quick(request, s):
    return orga_edit(request, s, "orga_quick", OrgaQuickSetupForm, None, "manage", add_ctx={"add_another": False})


@login_required
def orga_preferences(request, s):
    m_id = request.user.member.id
    return orga_edit(request, s, None, OrgaPreferencesForm, m_id, "manage", add_ctx={"add_another": False})


@login_required
def orga_backup(request: HttpRequest, s: str) -> HttpResponse:
    """Prepare event backup for download."""
    # Check user has event access
    ctx = check_event_permission(request, s, "orga_event")

    # Generate and return backup response
    return _prepare_backup(ctx)


def _prepare_backup(ctx: dict) -> HttpResponse:
    """
    Prepare comprehensive event data backup by exporting various components.

    Creates a ZIP file containing exported event data including registrations,
    characters, factions, plots, abilities, and quest builder components based
    on enabled features.

    Args:
        ctx: Context dictionary containing:
            - event: Event object to backup
            - features: Dict of enabled feature flags
            - Other context data required by export functions

    Returns:
        HttpResponse: ZIP file response containing all exported event data

    Raises:
        KeyError: If required context keys are missing
        Exception: If export or ZIP creation fails
    """
    exports = []

    # Export core event data
    exports.extend(export_event(ctx))

    # Export registration-related data
    exports.extend(export_data(ctx, Registration))
    exports.extend(export_registration_form(ctx))
    exports.extend(export_tickets(ctx))

    # Export character data if feature is enabled
    if "character" in ctx["features"]:
        exports.extend(export_data(ctx, Character))
        exports.extend(export_character_form(ctx))

    # Export faction data if feature is enabled
    if "faction" in ctx["features"]:
        exports.extend(export_data(ctx, Faction))

    # Export plot data if feature is enabled
    if "plot" in ctx["features"]:
        exports.extend(export_data(ctx, Plot))

    # Export experience/abilities data if feature is enabled
    if "px" in ctx["features"]:
        exports.extend(export_abilities(ctx))

    # Export quest builder data if feature is enabled
    if "questbuilder" in ctx["features"]:
        exports.extend(export_data(ctx, QuestType))
        exports.extend(export_data(ctx, Quest))
        exports.extend(export_data(ctx, Trait))

    # Create and return ZIP file with all exports
    return zip_exports(ctx, exports, "backup")


@login_required
def orga_upload(request: HttpRequest, s: str, typ: str) -> HttpResponse:
    """
    Handle file uploads for organizers with element processing.

    This function manages the upload process for various types of elements
    (characters, items, etc.) in LARP events. It validates permissions,
    processes uploaded files, and returns appropriate responses.

    Args:
        request: Django HTTP request object containing file data and POST parameters
        s: Event slug identifier for the specific event
        typ: Type of elements to upload (e.g., 'characters', 'items')

    Returns:
        HttpResponse: Either the upload form page or processing results page

    Raises:
        Exception: Any error during file processing is caught and displayed to user
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, f"orga_{typ}")
    ctx["typ"] = typ.rstrip("s")
    ctx["name"] = ctx["typ"]

    # Get column names for the upload template
    _get_column_names(ctx)

    # Handle POST request (file upload submission)
    if request.POST:
        form = UploadElementsForm(request.POST, request.FILES)

        # Prepare redirect URL for after processing
        redr = reverse(f"orga_{typ}", args=[ctx["run"].get_slug()])

        if form.is_valid():
            try:
                # Process the uploaded file and get processing logs
                ctx["logs"] = go_upload(request, ctx, form)
                ctx["redr"] = redr

                # Show success message and render results page
                messages.success(request, _("Elements uploaded") + "!")
                return render(request, "larpmanager/orga/uploads.html", ctx)

            except Exception as exp:
                # Log the full traceback and show error to user
                print(traceback.format_exc())
                messages.error(request, _("Unknow error on upload") + f": {exp}")

            # Redirect back to the main page on error or completion
            return HttpResponseRedirect(redr)
    else:
        # Handle GET request (show upload form)
        form = UploadElementsForm()

    # Add form to context and render upload page
    ctx["form"] = form
    return render(request, "larpmanager/orga/upload.html", ctx)


@login_required
def orga_upload_template(request, s: str, typ: str) -> HttpResponse:
    """Generate and download template files for data upload.

    Args:
        request: HTTP request object containing user session and metadata
        s: Event or run identifier string used to locate the specific event
        typ: Template type specifying which template to generate. Valid values:
            - 'writing': Character writing elements template
            - 'registration': Event registration template
            - 'px_abilitie': Player experience abilities template
            - 'form': Generic form template

    Returns:
        HttpResponse: ZIP file download response containing the generated template files

    Raises:
        PermissionDenied: If user lacks permission to access the specified event
        ValidationError: If template type is invalid or event not found
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s)
    ctx["typ"] = typ

    # Extract and set column names for template generation
    _get_column_names(ctx)

    # Define value mappings for different question types and their expected formats
    value_mapping = {
        BaseQuestionType.SINGLE: "option name",
        BaseQuestionType.MULTIPLE: "option names (comma separated)",
        BaseQuestionType.TEXT: "field text",
        BaseQuestionType.PARAGRAPH: "field long text",
        BaseQuestionType.EDITOR: "field html text",
        WritingQuestionType.NAME: "element name",
        WritingQuestionType.TEASER: "element presentation",
        WritingQuestionType.SHEET: "element text",
        WritingQuestionType.COVER: "element cover (utils path)",
        WritingQuestionType.FACTIONS: "faction names (comma separated)",
        WritingQuestionType.TITLE: "title short text",
        WritingQuestionType.MIRROR: "name of mirror character",
        WritingQuestionType.HIDE: "hide (true or false)",
        WritingQuestionType.PROGRESS: "name of progress step",
        WritingQuestionType.ASSIGNED: "name of assigned staff",
        RegistrationQuestionType.TICKET: "name of the ticket",
        RegistrationQuestionType.ADDITIONAL: "number of additional tickets",
        RegistrationQuestionType.PWYW: "amount of free donation",
        RegistrationQuestionType.QUOTA: "number of quotas to split the fee",
        RegistrationQuestionType.SURCHARGE: "surcharge applied",
    }

    # Generate appropriate template based on type
    if ctx.get("writing_typ"):
        # Generate writing elements template for character backgrounds
        exports = _writing_template(ctx, typ, value_mapping)
    elif typ == "registration":
        # Generate registration template for event signup data
        exports = _reg_template(ctx, typ, value_mapping)
    elif typ == "px_abilitie":
        # Generate abilities template for player experience tracking
        exports = _ability_template(ctx)
    else:
        # Generate generic form template for other data types
        exports = _form_template(ctx)

    # Package exports into ZIP file and return as download response
    return zip_exports(ctx, exports, "template")


def _ability_template(ctx):
    """Generate template for ability uploads with example data.

    Args:
        ctx: Context dictionary containing column definitions

    Returns:
        list: Export data containing ability template with example values
    """
    exports = []
    defs = {
        "name": "Ability name",
        "cost": "Ability cost",
        "typ": "Ability type",
        "descr": "Ability description",
        "prerequisites": "Ability prerequisite, comma-separated",
        "requirements": "Character options, comma-separated",
    }
    keys = list(ctx["columns"][0].keys())
    vals = []
    for field, value in defs.items():
        if field not in keys:
            continue
        vals.append(value)
    exports.append(("abilities", keys, [vals]))
    return exports


def _form_template(ctx: dict) -> list[tuple[str, list[str], list[list[str]]]]:
    """Generate template files for form questions and options upload.

    Creates sample data templates for both questions and options that can be used
    for bulk upload functionality. The templates include predefined values that
    serve as examples for users.

    Args:
        ctx: Context dictionary containing column definitions with the structure:
            - columns[0]: Dictionary with question field definitions
            - columns[1]: Dictionary with option field definitions

    Returns:
        List of tuples where each tuple contains:
            - str: Template type ("questions" or "options")
            - list[str]: Column headers/keys
            - list[list[str]]: Sample data rows
    """
    exports = []

    # Define sample data for questions template
    defs = {
        "name": "Question Name",
        "typ": "multi-choice",
        "description": "Question Description",
        "status": "optional",
        "applicable": "character",
        "visibility": "public",
        "max_length": "1",
    }

    # Extract available question fields from context
    keys = list(ctx["columns"][0].keys())
    vals = []

    # Build values list matching available fields
    for field, value in defs.items():
        if field not in keys:
            continue
        vals.append(value)

    # Add questions template to exports
    exports.append(("questions", keys, [vals]))

    # Define sample data for options template
    defs = {
        "question": "Question Name",
        "name": "Option Name",
        "description": "Option description",
        "max_available": "2",
        "price": "10",
    }

    # Extract available option fields from context
    keys = list(ctx["columns"][1].keys())
    vals = []

    # Build values list matching available fields
    for field, value in defs.items():
        if field not in keys:
            continue
        vals.append(value)

    # Add options template to exports
    exports.append(("options", keys, [vals]))

    return exports


def _reg_template(ctx: dict, typ: str, value_mapping: dict) -> list[tuple[str, list[str], list[list[str]]]]:
    """Generate registration template data for export.

    Creates a template with predefined default values and dynamic fields
    based on the provided context and value mapping.

    Args:
        ctx: Context dictionary containing columns and fields information
        typ: Template type identifier for naming
        value_mapping: Mapping of field types to their default values

    Returns:
        List of tuples containing template name, column keys, and row values
    """
    # Extract existing column keys from context
    keys = list(ctx["columns"][0].keys())
    vals = []

    # Define default values for common registration fields
    defs = {"email": "user@test.it", "ticket": "Standard", "characters": "Test Character", "donation": "5"}

    # Add default values for existing fields only
    for field, value in defs.items():
        if field not in keys:
            continue
        vals.append(value)

    # Extend keys with additional context fields
    keys.extend(ctx["fields"])

    # Add values for dynamic fields based on field type mapping
    for _field, field_typ in ctx["fields"].items():
        vals.append(value_mapping[field_typ])

    # Create export tuple with template name, keys, and values
    exports = [(f"{typ} - template", keys, [vals])]
    return exports


def _writing_template(ctx: dict, typ: str, value_mapping: dict) -> list[tuple[str, list[str], list[list[str]]]]:
    """Generate template data for writing export with field mappings.

    Creates export templates for different writing types including base templates
    and conditional templates for relationships and roles based on features.

    Args:
        ctx: Context dictionary containing:
            - fields: Dict mapping field names to field types
            - writing_typ: QuestionApplicable enum value for writing type
            - features: Set of enabled feature names
            - columns: Dict containing column definitions (when applicable)
        typ: Type string used as prefix for the template name
        value_mapping: Dictionary mapping field types to their example values

    Returns:
        List of tuples containing template data where each tuple is:
        (template_name, column_keys, row_values_list)
    """
    # Extract non-skipped fields and their corresponding example values
    keys = [k for k, v in ctx["fields"].items() if v != "skip"]
    vals = [value_mapping[field_typ] for _field, field_typ in ctx["fields"].items() if field_typ != "skip"]

    # Add type-specific prefix fields based on writing type
    if ctx["writing_typ"] == QuestionApplicable.QUEST:
        keys.insert(0, "typ")
        vals.insert(0, "name of quest type")
    elif ctx["writing_typ"] == QuestionApplicable.TRAIT:
        keys.insert(0, "quest")
        vals.insert(0, "name of quest")

    # Create base template export
    exports = [(f"{typ} - template", keys, [vals])]

    # Add relationships template for character writing when feature is enabled
    if ctx["writing_typ"] == QuestionApplicable.CHARACTER and "relationships" in ctx["features"]:
        exports.append(
            (
                "relationships - template",
                list(ctx["columns"][1].keys()),
                [["Test Character", "Another Character", "Super pals"]],
            )
        )

    # Add roles template for plot writing
    if ctx["writing_typ"] == QuestionApplicable.PLOT:
        exports.append(
            (
                "roles - template",
                list(ctx["columns"][1].keys()),
                [["Test Plot", "Test Character", "Gonna be a super star"]],
            )
        )
    return exports
