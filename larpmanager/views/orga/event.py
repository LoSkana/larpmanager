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
def orga_event(request, event_slug):
    context = check_event_permission(request, event_slug, "orga_event")
    return full_event_edit(context, request, context["event"], context["run"], is_executive=False)


def full_event_edit(
    context: dict, request: HttpRequest, event: Event, run: Run, is_executive: bool = False
) -> HttpResponse:
    """Comprehensive event editing with validation.

    Handles both GET requests for displaying edit forms and POST requests for
    processing form submissions. Validates and saves both event and run forms
    when submitted.

    Args:
        context: Context dictionary for template rendering
        request: HTTP request object containing form data
        event: Event instance to edit
        run: Run instance associated with the event
        is_executive: Whether this is an executive-level edit, defaults to False

    Returns:
        HttpResponse: Either the edit form template for GET requests or a
        redirect response after successful form submission
    """
    # Disable numbering in the template context
    context["nonum"] = 1

    if request.method == "POST":
        # Create form instances with POST data and file uploads
        event_form = OrgaEventForm(request.POST, request.FILES, instance=event, context=context, prefix="form1")
        run_form = OrgaRunForm(request.POST, request.FILES, instance=run, context=context, prefix="form2")

        # Validate both forms before saving
        if event_form.is_valid() and run_form.is_valid():
            # Save both forms to database
            event_form.save()
            run_form.save()

            # Show success message and redirect based on access level
            messages.success(request, _("Operation completed") + "!")
            if is_executive:
                return redirect("manage")
            else:
                return redirect("manage", event_slug=run.get_slug())
    else:
        # Create empty forms for GET requests
        event_form = OrgaEventForm(instance=event, context=context, prefix="form1")
        run_form = OrgaRunForm(instance=run, context=context, prefix="form2")

    # Add forms and metadata to template context
    context["form1"] = event_form
    context["form2"] = run_form
    context["num"] = event.id
    context["type"] = "event"

    return render(request, "larpmanager/orga/edit_multi.html", context)


@login_required
def orga_roles(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle organization roles management for an event."""
    # Check if user has permission to manage roles for this event
    context = check_event_permission(request, event_slug, "orga_roles")

    def def_callback(event_context):
        # Create default "Organizer" role if none exist
        return EventRole.objects.create(event=event_context["event"], number=1, name="Organizer")

    # Prepare the roles list with permissions and existing roles
    prepare_roles_list(context, EventPermission, EventRole.objects.filter(event=context["event"]), def_callback)

    return render(request, "larpmanager/orga/roles.html", context)


def prepare_roles_list(context, permission_type, role_queryset, default_callback):
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
    roles = role_queryset.order_by("number").prefetch_related(Prefetch("permissions", queryset=permissions_queryset))
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
                    [str(_(event_permission.name)) for event_permission in permissions_sorted]
                )
                formatted_permissions.append(f"<b>{module}</b> ({permissions_names})")
            role.perms_list = ", ".join(formatted_permissions)

        context["list"].append(role)


@login_required
def orga_roles_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_roles", OrgaEventRoleForm, num)


@login_required
def orga_appearance(request, event_slug):
    return orga_edit(
        request,
        event_slug,
        "orga_appearance",
        OrgaAppearanceForm,
        None,
        "manage",
        additional_context={"add_another": False},
    )


@login_required
def orga_run(request, event_slug):
    run = get_cache_run(request.assoc["id"], event_slug)
    return orga_edit(
        request, event_slug, "orga_event", OrgaRunForm, run, "manage", additional_context={"add_another": False}
    )


@login_required
def orga_texts(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render event texts management page with texts ordered by type, default flag, and language."""
    context = check_event_permission(request, event_slug, "orga_texts")
    context["list"] = EventText.objects.filter(event_id=context["event"].id).order_by("typ", "default", "language")
    return render(request, "larpmanager/orga/texts.html", context)


@login_required
def orga_texts_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_texts", OrgaEventTextForm, num)


@login_required
def orga_buttons(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display event buttons management page for organizers."""
    context = check_event_permission(request, event_slug, "orga_buttons")
    context["list"] = EventButton.objects.filter(event_id=context["event"].id).order_by("number")
    return render(request, "larpmanager/orga/buttons.html", context)


@login_required
def orga_buttons_edit(request, event_slug, num):
    return orga_edit(request, event_slug, "orga_buttons", OrgaEventButtonForm, num)


@login_required
def orga_config(
    request: HttpRequest,
    event_slug: str,
    section: str | None = None,
) -> HttpResponse:
    """Configure organization settings with optional section navigation."""
    # Prepare context with optional section jump
    add_ctx = {"jump_section": section} if section else {}
    add_ctx["add_another"] = False

    # Delegate to orga_edit with config form
    return orga_edit(request, event_slug, "orga_config", OrgaConfigForm, None, "manage", additional_context=add_ctx)


@login_required
def orga_features(request, event_slug):
    """Manage event features activation and configuration.

    Args:
        request: HTTP request object
        event_slug: Event slug

    Returns:
        HttpResponse: Rendered features form or redirect after activation
    """
    context = check_event_permission(request, event_slug, "orga_features")
    context["add_another"] = False
    if backend_edit(request, context, OrgaFeatureForm, None, additional_field=None, is_association_based=False):
        context["new_features"] = Feature.objects.filter(
            pk__in=context["form"].added_features, after_link__isnull=False
        )
        if not context["new_features"]:
            return redirect("manage", event_slug=context["run"].get_slug())
        for el in context["new_features"]:
            el.follow_link = _orga_feature_after_link(el, event_slug)
        if len(context["new_features"]) == 1:
            feature = context["new_features"][0]
            msg = _("Feature %(name)s activated") % {"name": feature.name} + "! " + feature.after_text
            clear_messages(request)
            messages.success(request, msg)
            return redirect(feature.follow_link)

        get_index_event_permissions(context, request, event_slug)
        return render(request, "larpmanager/manage/features.html", context)
    return render(request, "larpmanager/orga/edit.html", context)


def orga_features_go(request: HttpRequest, context: dict, slug: str, on: bool = True) -> Feature:
    """Toggle a feature for an event.

    Args:
        request: The HTTP request object
        context: Context dictionary containing event and feature information
        slug: The feature slug to toggle
        on: Whether to activate (True) or deactivate (False) the feature

    Returns:
        The feature object that was toggled

    Raises:
        Http404: If the feature is an overall feature (not event-specific)
    """
    # Get the feature from context using the slug
    get_feature(context, slug)

    # Check if feature is overall - these cannot be toggled per event
    if context["feature"].overall:
        raise Http404("overall feature!")

    # Get current event features and target feature ID
    current_event_feature_ids = list(context["event"].features.values_list("id", flat=True))
    target_feature_id = context["feature"].id

    # Clear cache and media for the current run
    clear_run_cache_and_media(context["run"])

    # Handle feature activation/deactivation logic
    if on:
        if target_feature_id not in current_event_feature_ids:
            context["event"].features.add(target_feature_id)
            message = _("Feature %(name)s activated") + "!"
        else:
            message = _("Feature %(name)s already activated") + "!"
    elif target_feature_id not in current_event_feature_ids:
        message = _("Feature %(name)s already deactivated") + "!"
    else:
        context["event"].features.remove(target_feature_id)
        message = _("Feature %(name)s deactivated") + "!"

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
    """Build redirect URL after feature interaction.

    Args:
        feature: Feature object with after_link attribute
        event_slug: Event slug identifier

    Returns:
        Full URL path for redirect
    """
    after_link = feature.after_link

    # Use reverse if after_link is a named URL pattern starting with "orga"
    if after_link and after_link.startswith("orga"):
        return reverse(after_link, kwargs={"s": event_slug})

    # Otherwise append after_link as fragment to manage URL
    return reverse("manage", kwargs={"s": event_slug}) + (after_link or "")


@login_required
def orga_features_on(
    request: HttpRequest,
    event_slug: str,
    slug: str,
) -> HttpResponseRedirect:
    """Toggle feature on for an event."""
    # Check user has permission to manage features
    context = check_event_permission(request, event_slug, "orga_features")

    # Enable the feature
    feature = orga_features_go(request, context, slug, on=True)

    # Redirect to appropriate page
    return redirect(_orga_feature_after_link(feature, event_slug))


@login_required
def orga_features_off(request: HttpRequest, event_slug: str, slug: str) -> HttpResponse:
    """Disable a feature for an event."""
    context = check_event_permission(request, event_slug, "orga_features")
    orga_features_go(request, context, slug, on=False)
    return redirect("manage", event_slug=event_slug)


@login_required
def orga_deadlines(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display deadlines for a specific run."""
    # Check permissions and get event context
    context = check_event_permission(request, event_slug, "orga_deadlines")

    # Get deadline status for the run
    context["res"] = check_run_deadlines([context["run"]])[0]

    return render(request, "larpmanager/orga/deadlines.html", context)


@login_required
def orga_quick(request, event_slug):
    return orga_edit(
        request, event_slug, "orga_quick", OrgaQuickSetupForm, None, "manage", additional_context={"add_another": False}
    )


@login_required
def orga_preferences(request, event_slug):
    m_id = request.user.member.id
    return orga_edit(
        request, event_slug, None, OrgaPreferencesForm, m_id, "manage", additional_context={"add_another": False}
    )


@login_required
def orga_backup(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Prepare event backup for download."""
    # Check user has event access
    context = check_event_permission(request, event_slug, "orga_event")

    # Generate and return backup response
    return _prepare_backup(context)


def _prepare_backup(context: dict) -> HttpResponse:
    """
    Prepare comprehensive event data backup by exporting various components.

    Creates a ZIP file containing exported event data including registrations,
    characters, factions, plots, abilities, and quest builder components based
    on enabled features.

    Args:
        context: Context dictionary containing:
            - event: Event object to backup
            - features: Dict of enabled feature flags
            - Other context data required by export functions

    Returns:
        HttpResponse: ZIP file response containing all exported event data

    Raises:
        KeyError: If required context keys are missing
        Exception: If export or ZIP creation fails
    """
    export_files = []

    # Export core event data
    export_files.extend(export_event(context))

    # Export registration-related data
    export_files.extend(export_data(context, Registration))
    export_files.extend(export_registration_form(context))
    export_files.extend(export_tickets(context))

    # Export character data if feature is enabled
    if "character" in context["features"]:
        export_files.extend(export_data(context, Character))
        export_files.extend(export_character_form(context))

    # Export faction data if feature is enabled
    if "faction" in context["features"]:
        export_files.extend(export_data(context, Faction))

    # Export plot data if feature is enabled
    if "plot" in context["features"]:
        export_files.extend(export_data(context, Plot))

    # Export experience/abilities data if feature is enabled
    if "px" in context["features"]:
        export_files.extend(export_abilities(context))

    # Export quest builder data if feature is enabled
    if "questbuilder" in context["features"]:
        export_files.extend(export_data(context, QuestType))
        export_files.extend(export_data(context, Quest))
        export_files.extend(export_data(context, Trait))

    # Create and return ZIP file with all exports
    return zip_exports(context, export_files, "backup")


@login_required
def orga_upload(request: HttpRequest, event_slug: str, typ: str) -> HttpResponse:
    """
    Handle file uploads for organizers with element processing.

    This function manages the upload process for various types of elements
    (characters, items, etc.) in LARP events. It validates permissions,
    processes uploaded files, and returns appropriate responses.

    Args:
        request: Django HTTP request object containing file data and POST parameters
        event_slug: Event slug identifier for the specific event
        typ: Type of elements to upload (e.g., 'characters', 'items')

    Returns:
        HttpResponse: Either the upload form page or processing results page

    Raises:
        Exception: Any error during file processing is caught and displayed to user
    """
    # Check user permissions and get event context
    context = check_event_permission(request, event_slug, f"orga_{typ}")
    context["typ"] = typ.rstrip("s")
    context["name"] = context["typ"]

    # Get column names for the upload template
    _get_column_names(context)

    # Handle POST request (file upload submission)
    if request.POST:
        form = UploadElementsForm(request.POST, request.FILES)

        # Prepare redirect URL for after processing
        redr = reverse(f"orga_{typ}", args=[context["run"].get_slug()])

        if form.is_valid():
            try:
                # Process the uploaded file and get processing logs
                context["logs"] = go_upload(request, context, form)
                context["redr"] = redr

                # Show success message and render results page
                messages.success(request, _("Elements uploaded") + "!")
                return render(request, "larpmanager/orga/uploads.html", context)

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
    context["form"] = form
    return render(request, "larpmanager/orga/upload.html", context)


@login_required
def orga_upload_template(request, event_slug: str, typ: str) -> HttpResponse:
    """Generate and download template files for data upload.

    Args:
        request: HTTP request object containing user session and metadata
        event_slug: Event identifier string used to locate the specific event
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
    context = check_event_permission(request, event_slug)
    context["typ"] = typ

    # Extract and set column names for template generation
    _get_column_names(context)

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
    if context.get("writing_typ"):
        # Generate writing elements template for character backgrounds
        exports = _writing_template(context, typ, value_mapping)
    elif typ == "registration":
        # Generate registration template for event signup data
        exports = _reg_template(context, typ, value_mapping)
    elif typ == "px_abilitie":
        # Generate abilities template for player experience tracking
        exports = _ability_template(context)
    else:
        # Generate generic form template for other data types
        exports = _form_template(context)

    # Package exports into ZIP file and return as download response
    return zip_exports(context, exports, "template")


def _ability_template(context):
    """Generate template for ability uploads with example data.

    Args:
        context: Context dictionary containing column definitions

    Returns:
        list: Export data containing ability template with example values
    """
    export_data = []
    field_example_values = {
        "name": "Ability name",
        "cost": "Ability cost",
        "typ": "Ability type",
        "descr": "Ability description",
        "prerequisites": "Ability prerequisite, comma-separated",
        "requirements": "Character options, comma-separated",
    }
    column_names = list(context["columns"][0].keys())
    example_row_values = []
    for field_name, example_value in field_example_values.items():
        if field_name not in column_names:
            continue
        example_row_values.append(example_value)
    export_data.append(("abilities", column_names, [example_row_values]))
    return export_data


def _form_template(context: dict) -> list[tuple[str, list[str], list[list[str]]]]:
    """Generate template files for form questions and options upload.

    Creates sample data templates for both questions and options that can be used
    for bulk upload functionality. The templates include predefined values that
    serve as examples for users.

    Args:
        context: Context dictionary containing column definitions with the structure:
            - columns[0]: Dictionary with question field definitions
            - columns[1]: Dictionary with option field definitions

    Returns:
        List of tuples where each tuple contains:
            - str: Template type ("questions" or "options")
            - list[str]: Column headers/keys
            - list[list[str]]: Sample data rows
    """
    template_exports = []

    # Define sample data for questions template
    sample_question_data = {
        "name": "Question Name",
        "typ": "multi-choice",
        "description": "Question Description",
        "status": "optional",
        "applicable": "character",
        "visibility": "public",
        "max_length": "1",
    }

    # Extract available question fields from context
    question_column_keys = list(context["columns"][0].keys())
    question_sample_values = []

    # Build values list matching available fields
    for field_name, sample_value in sample_question_data.items():
        if field_name not in question_column_keys:
            continue
        question_sample_values.append(sample_value)

    # Add questions template to exports
    template_exports.append(("questions", question_column_keys, [question_sample_values]))

    # Define sample data for options template
    sample_option_data = {
        "question": "Question Name",
        "name": "Option Name",
        "description": "Option description",
        "max_available": "2",
        "price": "10",
    }

    # Extract available option fields from context
    option_column_keys = list(context["columns"][1].keys())
    option_sample_values = []

    # Build values list matching available fields
    for field_name, sample_value in sample_option_data.items():
        if field_name not in option_column_keys:
            continue
        option_sample_values.append(sample_value)

    # Add options template to exports
    template_exports.append(("options", option_column_keys, [option_sample_values]))

    return template_exports


def _reg_template(
    context: dict, template_type: str, value_mapping: dict
) -> list[tuple[str, list[str], list[list[str]]]]:
    """Generate registration template data for export.

    Creates a template with predefined default values and dynamic fields
    based on the provided context and value mapping.

    Args:
        context: Context dictionary containing columns and fields information
        template_type: Template type identifier for naming
        value_mapping: Mapping of field types to their default values

    Returns:
        List of tuples containing template name, column keys, and row values
    """
    # Extract existing column keys from context
    column_keys = list(context["columns"][0].keys())
    row_values = []

    # Define default values for common registration fields
    default_values = {"email": "user@test.it", "ticket": "Standard", "characters": "Test Character", "donation": "5"}

    # Add default values for existing fields only
    for field_name, default_value in default_values.items():
        if field_name not in column_keys:
            continue
        row_values.append(default_value)

    # Extend keys with additional context fields
    column_keys.extend(context["fields"])

    # Add values for dynamic fields based on field type mapping
    for _field_name, field_type in context["fields"].items():
        row_values.append(value_mapping[field_type])

    # Create export tuple with template name, keys, and values
    exports = [(f"{template_type} - template", column_keys, [row_values])]
    return exports


def _writing_template(
    context: dict, type_prefix: str, value_mapping: dict
) -> list[tuple[str, list[str], list[list[str]]]]:
    """Generate template data for writing export with field mappings.

    Creates export templates for different writing types including base templates
    and conditional templates for relationships and roles based on features.

    Args:
        context: Context dictionary containing:
            - fields: Dict mapping field names to field types
            - writing_typ: QuestionApplicable enum value for writing type
            - features: Set of enabled feature names
            - columns: Dict containing column definitions (when applicable)
        type_prefix: Type string used as prefix for the template name
        value_mapping: Dictionary mapping field types to their example values

    Returns:
        List of tuples containing template data where each tuple is:
        (template_name, column_keys, row_values_list)
    """
    # Extract non-skipped fields and their corresponding example values
    column_keys = [key for key, field_type in context["fields"].items() if field_type != "skip"]
    example_values = [
        value_mapping[field_type] for _field, field_type in context["fields"].items() if field_type != "skip"
    ]

    # Add type-specific prefix fields based on writing type
    if context["writing_typ"] == QuestionApplicable.QUEST:
        column_keys.insert(0, "typ")
        example_values.insert(0, "name of quest type")
    elif context["writing_typ"] == QuestionApplicable.TRAIT:
        column_keys.insert(0, "quest")
        example_values.insert(0, "name of quest")

    # Create base template export
    template_exports = [(f"{type_prefix} - template", column_keys, [example_values])]

    # Add relationships template for character writing when feature is enabled
    if context["writing_typ"] == QuestionApplicable.CHARACTER and "relationships" in context["features"]:
        template_exports.append(
            (
                "relationships - template",
                list(context["columns"][1].keys()),
                [["Test Character", "Another Character", "Super pals"]],
            )
        )

    # Add roles template for plot writing
    if context["writing_typ"] == QuestionApplicable.PLOT:
        template_exports.append(
            (
                "roles - template",
                list(context["columns"][1].keys()),
                [["Test Plot", "Test Character", "Gonna be a super star"]],
            )
        )
    return template_exports
