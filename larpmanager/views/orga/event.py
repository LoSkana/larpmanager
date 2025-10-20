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
from django.db.models import F, Prefetch, QuerySet
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

    Handles both GET and POST requests for editing event and run data.
    Validates both forms and saves changes on successful submission.

    Args:
        ctx: Context dictionary for template rendering
        request: HTTP request object containing form data
        event: Event instance to edit
        run: Run instance associated with the event
        exe: Whether this is an executive-level edit, defaults to False

    Returns:
        HttpResponse: Edit form template or redirect after successful save

    Raises:
        ValidationError: If form validation fails
    """
    # Disable automatic numbering in template
    ctx["nonum"] = 1

    if request.method == "POST":
        # Create forms with POST data and file uploads
        form_event = OrgaEventForm(request.POST, request.FILES, instance=event, ctx=ctx, prefix="form1")
        form_run = OrgaRunForm(request.POST, request.FILES, instance=run, ctx=ctx, prefix="form2")

        # Validate both forms before saving
        if form_event.is_valid() and form_run.is_valid():
            # Save both forms atomically
            form_event.save()
            form_run.save()

            # Show success message and redirect based on user level
            messages.success(request, _("Operation completed") + "!")
            if exe:
                return redirect("manage")
            else:
                return redirect("manage", s=run.get_slug())
    else:
        # Create forms with existing instance data for GET requests
        form_event = OrgaEventForm(instance=event, ctx=ctx, prefix="form1")
        form_run = OrgaRunForm(instance=run, ctx=ctx, prefix="form2")

    # Add forms and metadata to template context
    ctx["form1"] = form_event
    ctx["form2"] = form_run
    ctx["num"] = event.id
    ctx["type"] = "event"

    # Render the multi-form edit template
    return render(request, "larpmanager/orga/edit_multi.html", ctx)


@login_required
def orga_roles(request, s):
    ctx = check_event_permission(request, s, "orga_roles")

    def def_callback(ctx):
        return EventRole.objects.create(event=ctx["event"], number=1, name="Organizer")

    prepare_roles_list(ctx, EventPermission, EventRole.objects.filter(event=ctx["event"]), def_callback)

    return render(request, "larpmanager/orga/roles.html", ctx)


def prepare_roles_list(ctx: dict, permission_typ: type, role_query: QuerySet, def_callback: callable) -> None:
    """Prepare role list with permissions organized by module for display.

    Builds a formatted list of roles with their members and grouped permissions,
    handling special formatting for administrator roles and module organization.

    Args:
        ctx: Context dictionary to store the prepared role list
        permission_typ: Permission model class for querying permissions
        role_query: QuerySet of roles to process
        def_callback: Callback function to generate default role when no roles exist

    Returns:
        None: Modifies ctx dictionary in-place by adding 'list' key
    """
    # Build optimized queryset for permissions with related data and proper ordering
    qs_perm = permission_typ.objects.select_related("feature", "feature__module").order_by(
        F("feature__module__order").asc(nulls_last=True),
        F("feature__order").asc(nulls_last=True),
        "feature__name",
        "name",
    )

    # Fetch roles with prefetched permissions to avoid N+1 queries
    roles = role_query.order_by("number").prefetch_related(Prefetch("permissions", queryset=qs_perm))

    # Initialize the context list
    ctx["list"] = []

    # Handle case when no roles exist - use default callback
    if not roles:
        ctx["list"].append(def_callback(ctx))

    # Process each role to format members and permissions
    for role in roles:
        # Format members list as comma-separated string
        role.members_list = ", ".join([str(mb) for mb in role.members.all()])

        # Special handling for administrator role (number "1")
        if role.number == "1":
            role.perms_list = "All"
        else:
            # Group permissions by their feature module
            buckets = defaultdict(list)
            for p in role.permissions.all():
                buckets[p.feature.module].append(p)

            # Sort modules by order (nulls last) then by name
            modules = sorted(
                buckets.keys(),
                key=lambda m: (
                    float("inf") if m is None else (m.order if m.order is not None else float("inf")),
                    "" if m is None else m.name,
                ),
            )

            # Build formatted permission list grouped by module
            aux = []
            for module in modules:
                # Sort permissions within each module by number
                perms_sorted = sorted(buckets[module], key=lambda p: p.number)
                # Create comma-separated list of translated permission names
                perms = ", ".join([str(_(ep.name)) for ep in perms_sorted])
                # Format as "Module (perm1, perm2, ...)"
                aux.append(f"<b>{module}</b> ({perms})")

            # Join all module groups with commas
            role.perms_list = ", ".join(aux)

        # Add processed role to the context list
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
def orga_texts(request, s):
    ctx = check_event_permission(request, s, "orga_texts")
    ctx["list"] = EventText.objects.filter(event_id=ctx["event"].id).order_by("typ", "default", "language")
    return render(request, "larpmanager/orga/texts.html", ctx)


@login_required
def orga_texts_edit(request, s, num):
    return orga_edit(request, s, "orga_texts", OrgaEventTextForm, num)


@login_required
def orga_buttons(request, s):
    ctx = check_event_permission(request, s, "orga_buttons")
    ctx["list"] = EventButton.objects.filter(event_id=ctx["event"].id).order_by("number")
    return render(request, "larpmanager/orga/buttons.html", ctx)


@login_required
def orga_buttons_edit(request, s, num):
    return orga_edit(request, s, "orga_buttons", OrgaEventButtonForm, num)


@login_required
def orga_config(request, s, section=None):
    add_ctx = {"jump_section": section} if section else {}
    add_ctx["add_another"] = False
    return orga_edit(request, s, "orga_config", OrgaConfigForm, None, "manage", add_ctx=add_ctx)


@login_required
def orga_features(request: HttpRequest, s: str) -> HttpResponse:
    """Manage event features activation and configuration.

    This view handles the activation and configuration of event features. When features
    are successfully activated, it may redirect to post-activation pages or show a
    confirmation page for multiple features.

    Args:
        request: The HTTP request object containing user data and form submission
        s: The event slug identifier used to locate the specific event

    Returns:
        HttpResponse: Either a rendered features form page, redirect to event management,
                     or redirect to post-activation feature configuration pages

    Raises:
        PermissionDenied: If user lacks 'orga_features' permission for this event
    """
    # Check user permissions and initialize context
    ctx = check_event_permission(request, s, "orga_features")
    ctx["add_another"] = False

    # Process form submission using backend edit helper
    if backend_edit(request, ctx, OrgaFeatureForm, None, afield=None, assoc=False):
        # Get newly activated features that have post-activation links
        ctx["new_features"] = Feature.objects.filter(pk__in=ctx["form"].added_features, after_link__isnull=False)

        # If no features need post-activation setup, redirect to event management
        if not ctx["new_features"]:
            return redirect("manage", s=ctx["run"].get_slug())

        # Generate follow-up links for each activated feature
        for el in ctx["new_features"]:
            el.follow_link = _orga_feature_after_link(el, s)

        # Handle single feature activation - show success message and redirect
        if len(ctx["new_features"]) == 1:
            feature = ctx["new_features"][0]
            msg = _("Feature %(name)s activated") % {"name": feature.name} + "! " + feature.after_text
            clear_messages(request)
            messages.success(request, msg)
            return redirect(feature.follow_link)

        # Handle multiple features - show features page with options
        get_index_event_permissions(ctx, request, s)
        return render(request, "larpmanager/manage/features.html", ctx)

    # Render initial form or form with validation errors
    return render(request, "larpmanager/orga/edit.html", ctx)


def orga_features_go(request: HttpRequest, ctx: dict, slug: str, on: bool = True) -> object:
    """Toggle a feature on/off for an event.

    Args:
        request: The HTTP request object
        ctx: Context dictionary containing event and feature information
        slug: The feature slug identifier
        on: Whether to turn the feature on (True) or off (False)

    Returns:
        The feature object that was toggled

    Raises:
        Http404: If the feature is an overall feature (not event-specific)
    """
    # Get the feature from context using the slug
    get_feature(ctx, slug)

    # Raise 404 if this is an overall feature (not event-specific)
    if ctx["feature"].overall:
        raise Http404("overall feature!")

    # Get list of current feature IDs for this event
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

    # Save the event to persist changes
    ctx["event"].save()

    # Update cached event features for parent-child event relationships
    for ev in Event.objects.filter(parent=ctx["event"]):
        ev.save()

    # Format the success message with feature name and optional after_text
    msg = msg % {"name": _(ctx["feature"].name)}
    if ctx["feature"].after_text:
        msg += " " + ctx["feature"].after_text
    messages.success(request, msg)

    return ctx["feature"]


def _orga_feature_after_link(feature, s):
    after_link = feature.after_link
    if after_link and after_link.startswith("orga"):
        return reverse(after_link, kwargs={"s": s})
    return reverse("manage", kwargs={"s": s}) + (after_link or "")


@login_required
def orga_features_on(request, s, slug):
    ctx = check_event_permission(request, s, "orga_features")
    feature = orga_features_go(request, ctx, slug, on=True)
    return redirect(_orga_feature_after_link(feature, s))


@login_required
def orga_features_off(request, s, slug):
    ctx = check_event_permission(request, s, "orga_features")
    orga_features_go(request, ctx, slug, on=False)
    return redirect("manage", s=s)


@login_required
def orga_deadlines(request, s):
    ctx = check_event_permission(request, s, "orga_deadlines")
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
def orga_backup(request, s):
    ctx = check_event_permission(request, s, "orga_event")

    return _prepare_backup(ctx)


def _prepare_backup(ctx: dict) -> HttpResponse:
    """
    Prepare comprehensive event data backup by exporting various components.

    Creates a ZIP file containing exported event data including registrations,
    characters, factions, plots, and other feature-specific data based on
    enabled features in the event context.

    Args:
        ctx: Context dictionary containing event information and enabled features.
             Must include 'features' key with list of enabled feature names.

    Returns:
        HttpResponse containing a ZIP file with all exported event data.

    Note:
        The function conditionally exports data based on enabled features:
        - character: Character data and forms
        - faction: Faction data
        - plot: Plot data
        - px: Abilities data
        - questbuilder: Quest types, quests, and traits
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

    # Export abilities data if px feature is enabled
    if "px" in ctx["features"]:
        exports.extend(export_abilities(ctx))

    # Export quest-related data if questbuilder feature is enabled
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

    This function manages the upload workflow for various element types in LARP events,
    including form validation, file processing, and user feedback.

    Args:
        request: HTTP request object containing file data and form information
        s: Event slug identifier for the specific event
        typ: Type of elements to upload (e.g., 'characters', 'items')

    Returns:
        HttpResponse: Either the upload form page or processing results page

    Raises:
        Exception: Any error during file processing is caught and displayed to user
    """
    # Check user permissions and initialize context for the event
    ctx = check_event_permission(request, s, f"orga_{typ}")
    ctx["typ"] = typ.rstrip("s")
    ctx["name"] = ctx["typ"]

    # Get column names for the upload template
    _get_column_names(ctx)

    # Handle POST request (file upload submission)
    if request.POST:
        form = UploadElementsForm(request.POST, request.FILES)
        redr = reverse(f"orga_{typ}", args=[ctx["run"].get_slug()])

        # Validate form and process upload
        if form.is_valid():
            try:
                # Process the uploaded file and generate logs
                # print(request.FILES)
                ctx["logs"] = go_upload(request, ctx, form)
                ctx["redr"] = redr

                # Show success message and render results page
                messages.success(request, _("Elements uploaded") + "!")
                return render(request, "larpmanager/orga/uploads.html", ctx)

            except Exception as exp:
                # Log error details and show user-friendly message
                print(traceback.format_exc())
                messages.error(request, _("Unknow error on upload") + f": {exp}")

            # Redirect back to main page on error
            return HttpResponseRedirect(redr)
    else:
        # Initialize empty form for GET request
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


def _ability_template(ctx: dict) -> list[tuple[str, list[str], list[list[str]]]]:
    """Generate template for ability uploads with example data.

    Creates a template structure for ability data import containing predefined
    example values that demonstrate the expected format for each field.

    Args:
        ctx: Context dictionary containing column definitions with structure:
            - columns: List of dictionaries with ability field names as keys

    Returns:
        List containing a single tuple with format:
            - ("abilities", field_names, [example_values])
        Where field_names are the column headers and example_values are
        sample data for each corresponding field.

    Example:
        >>> ctx = {"columns": [{"name": "", "cost": "", "typ": ""}]}
        >>> result = _ability_template(ctx)
        >>> result[0][0]  # Returns "abilities"
    """
    exports = []

    # Define example values for each ability field
    defs = {
        "name": "Ability name",
        "cost": "Ability cost",
        "typ": "Ability type",
        "descr": "Ability description",
        "prerequisites": "Ability prerequisite, comma-separated",
        "requirements": "Character options, comma-separated",
    }

    # Extract column keys from context
    keys = list(ctx["columns"][0].keys())
    vals = []

    # Build example values list matching available columns
    for field, value in defs.items():
        if field not in keys:
            continue
        vals.append(value)

    # Create export structure with template data
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

    Args:
        ctx: Context dictionary containing columns and fields data
        typ: Template type identifier string
        value_mapping: Mapping of field types to default values

    Returns:
        List of tuples containing template name, column headers, and sample data rows
    """
    # Extract available column keys from context
    keys = list(ctx["columns"][0].keys())
    vals = []

    # Define default values for standard registration fields
    defs = {"email": "user@test.it", "ticket": "Standard", "characters": "Test Character", "donation": "5"}

    # Add default values for existing standard fields
    for field, value in defs.items():
        if field not in keys:
            continue
        vals.append(value)

    # Extend headers with custom field names
    keys.extend(ctx["fields"])

    # Add mapped values for each custom field type
    for _field, field_typ in ctx["fields"].items():
        vals.append(value_mapping[field_typ])

    # Return formatted export data structure
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
