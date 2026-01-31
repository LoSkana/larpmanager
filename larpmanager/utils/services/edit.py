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

import time
from typing import TYPE_CHECKING, Any

from django.conf import settings as conf_settings
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Max
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.cache.config import _get_fkey_config, get_event_config
from larpmanager.forms.utils import EventCharacterS2Widget, EventTraitS2Widget
from larpmanager.models.association import Association
from larpmanager.models.casting import Trait
from larpmanager.models.form import BaseQuestionType, QuestionApplicable, WritingAnswer, WritingChoice, WritingQuestion
from larpmanager.models.member import Log, Member
from larpmanager.models.writing import Plot, PlotCharacterRel, Relationship, TextVersion
from larpmanager.utils.auth.admin import is_lm_admin
from larpmanager.utils.core.base import check_association_context, check_event_context, get_context
from larpmanager.utils.core.common import get_element, get_object_uuid, html_clean

if TYPE_CHECKING:
    from collections.abc import Callable

    from larpmanager.forms.base import BaseModelForm
    from larpmanager.models.base import BaseModel


def save_log(member: Member, cls: type, element: Any, *, to_delete: bool = False) -> None:
    """Create a log entry for model instance changes."""
    Log.objects.create(member=member, cls=cls.__name__, eid=element.id, dl=to_delete, dct=element.as_dict())


def save_version(element: Any, model_type: str, member: Member, *, to_delete: bool = False) -> None:  # noqa: C901 - Complex versioning logic with multiple model types
    """Manage versioning of text content.

    Creates and saves new versions of editable text elements with author tracking,
    handling different content types including character relationships, plot
    character associations, and question-based text fields.

    Args:
        element: The element object to create a version for
        model_type: Type identifier for the content being versioned
        member: Member object representing the author of this version
        to_delete: Whether this version should be marked for deletion, defaults to False

    Returns:
        None

    """
    # Get the highest version number for this element and increment it
    n = TextVersion.objects.filter(tp=model_type, eid=element.id).aggregate(Max("version"))["version__max"]
    if n is None:
        n = 1
    else:
        n += 1

    # Create new TextVersion instance with basic metadata
    tv = TextVersion()
    tv.eid = element.id
    tv.tp = model_type
    tv.version = n
    tv.member = member
    tv.dl = to_delete

    # Handle question-based content types by aggregating answers
    if model_type in QuestionApplicable.values:
        texts = []
        query = element.event.get_elements(WritingQuestion)

        # Collect all applicable questions and their values
        for que in query.filter(applicable=model_type).order_by("order"):
            value = _get_field_value(element, que)
            if not value:
                continue
            value = html_clean(value)
            texts.append(f"{que.name}: {value}")

        tv.text = "\n".join(texts)
    else:
        # For non-question types, use the element's text directly
        tv.text = element.text

    # Add character relationships if this is a character type
    if model_type == QuestionApplicable.CHARACTER:
        rels = Relationship.objects.filter(source=element)
        if rels:
            tv.text += "\nRelationships\n"
            for rel in rels:
                tv.text += f"{rel.target}: {html_clean(rel.text)}\n"

    # Add plot character associations if this is a plot type
    if model_type == QuestionApplicable.PLOT:
        chars = PlotCharacterRel.objects.filter(plot=element)
        if chars:
            tv.text += "\nCharacters\n"
            for rel in chars:
                tv.text += f"{rel.character}: {html_clean(rel.text)}\n"

    # Save the completed version to database
    tv.save()


def _get_field_value(element: Any, question: Any) -> str | None:
    """Get the field value for a given element and question.

    Args:
        element: The element object to get the value for
        question: The question object containing type and configuration

    Returns:
        The field value as a string, or None if no value found

    """
    # Get the mapping of question types to their value extraction functions
    mapping = _get_values_mapping(element)

    # Check if question type has a direct mapping function
    if question.typ in mapping:
        return mapping[question.typ]()

    # Handle text-based question types (paragraph, text, email)
    if question.typ in {"p", "t", "e"}:
        answers = WritingAnswer.objects.filter(question=question, element_id=element.id)
        if answers:
            return answers.first().text
        return ""

    # Handle selection-based question types (single, multiple choice)
    if question.typ in {"s", "m"}:
        return ", ".join(
            choice.option.name for choice in WritingChoice.objects.filter(question=question, element_id=element.id)
        )

    return None


def _get_values_mapping(element: Any) -> dict[str, callable]:
    """Return a mapping of field names to their value extraction functions.

    Args:
        element: The element object to extract values from.

    Returns:
        Dictionary mapping field names to lambda functions that extract values.

    """
    # Basic text and content fields
    return {
        "text": lambda: element.text,
        "teaser": lambda: element.teaser,
        "name": lambda: element.name,
        "title": lambda: element.title,
        # Related faction names joined by comma
        "faction": lambda: ", ".join([faction.name for faction in element.factions_list.all()]),
    }


def check_run(element: Any, context: Any, accessor_field: Any = None) -> None:
    """Validate that element belongs to the correct run and event.

    Args:
        element: Model instance to validate
        context: Context dictionary containing run and event information
        accessor_field: Optional field name to access nested element

    Raises:
        Http404: If element doesn't belong to the expected run or event

    """
    if "run" not in context:
        return

    if accessor_field:
        element = getattr(element, accessor_field)

    if hasattr(element, "run") and element.run != context["run"]:
        msg = "not your run"
        raise Http404(msg)

    if hasattr(element, "event"):
        is_child_event = context["event"].parent_id is not None
        event_matches = element.event_id == context["event"].id
        parent_event_matches = element.event_id == context["event"].parent_id

        if (not is_child_event and not event_matches) or (
            is_child_event and not event_matches and not parent_event_matches
        ):
            msg = "not your event"
            raise Http404(msg)


def check_association(element: object, context: dict, attribute_field: str | None = None) -> None:
    """Check if object belongs to the correct association.

    Args:
        element: Object to check or container object
        context: Context dict containing association ID as 'association_id'
        attribute_field: Optional field name to extract from element

    Raises:
        Http404: If object doesn't belong to the association

    """
    # Extract specific field if requested
    if attribute_field:
        element = getattr(element, attribute_field)

    # Skip check if object has no association
    if not hasattr(element, "association"):
        return

    # Verify object belongs to current association
    if element.association_id != context["association_id"]:
        msg = "not your association"
        raise Http404(msg)


def user_edit(
    request: HttpRequest, context: dict, form_type: type, model_name: str, entity_uuid: str | None = None
) -> bool:
    """Edit user data with validation.

    Handle both GET and POST requests for editing user data. On POST, validate
    the form and save the instance. Support deletion functionality when
    'delete' parameter is set to '1' in POST data.

    Args:
        request: HTTP request object containing method and POST data
        context: Context dictionary containing model data and form instance
        form_type: Django form class to use for data validation and editing
        model_name: Name key for accessing the model instance in context dictionary
        entity_uuid: Entity ID for editing, used for form numbering (0 for new instances)

    Returns:
        True if form was successfully processed and saved, False if form
        validation failed or GET request requires form display.

    Side Effects:
        - Adds success message to request on successful save
        - Logs the operation using save_log function
        - Deletes instance if delete flag is set
        - Updates context with 'saved', 'form', 'num', and optionally 'name' keys

    """
    if request.method == "POST":
        # Initialize form with POST data and files, bind to existing instance
        form = form_type(request.POST, request.FILES, instance=context[model_name], context=context)

        if form.is_valid():
            # Save the form and get the updated instance
            saved_instance = form.save()
            messages.success(request, _("Operation completed") + "!")

            # Check if delete operation was requested
            should_delete = "delete" in request.POST and request.POST["delete"] == "1"

            # Log the operation (save or delete)
            save_log(context["member"], form_type, saved_instance, to_delete=should_delete)

            # Delete the instance if deletion was requested
            if should_delete:
                saved_instance.delete()

            # Store saved instance in context for template access
            context["saved"] = saved_instance

            return True
    else:
        # Initialize empty form for GET request, bind to existing instance
        form = form_type(instance=context[model_name], context=context)

    # Add form and entity ID to context for template rendering
    context["form"] = form
    context["num"] = entity_uuid

    if entity_uuid:
        context["name"] = set_form_name(context[model_name])

    return False


def set_form_name(el: BaseModel) -> str:
    """Get the name to show on the form."""
    if hasattr(el, "name"):
        return el.name
    if hasattr(el, "title"):
        return el.title
    return str(el)


def backend_get(context: dict, model_type: type, entity_uuid: str, association_field: str | None = None) -> None:
    """Retrieve an object by ID and perform security checks.

    Args:
        context: Context dictionary to store the retrieved object
        model_type: Model class to query
        entity_uuid: UUID of the object to retrieve
        association_field: Optional field name for additional checks

    Raises:
        Http404: If object with given ID doesn't exist

    """
    # Retrieve object by UUID
    element = get_object_uuid(model_type, entity_uuid)

    # Store object in context and perform security validations
    context["el"] = element
    check_run(element, context, association_field)
    check_association(element, context, association_field)

    # Set display name for the object
    context["name"] = str(element)


def _resolve_element_uuid(
    context: dict,
    element_uuid: str | None,
    *,
    is_association: bool,
) -> str:
    """Resolve element UUID from context if None."""
    if element_uuid is not None:
        return element_uuid

    if is_association:
        context["exe"] = True
        context["nonum"] = True
        return context["uuid"]

    context["nonum"] = True
    return context["event"].uuid


def _handle_form_submission(
    request: HttpRequest,
    context: dict,
    form_type: type[BaseModelForm],
    *,
    quiet: bool,
) -> bool:
    """Handle form submission and return True if saved successfully."""
    context["form"] = form_type(request.POST, request.FILES, instance=context["el"], context=context)

    if not context["form"].is_valid():
        return False

    # Save the form and show success message if not in quiet mode
    saved_object = context["form"].save()
    if not quiet:
        messages.success(request, _("Operation completed") + "!")

    # Handle deletion if delete flag is set in POST data
    should_delete = request.POST.get("delete") == "1"
    save_log(context["member"], form_type, saved_object, to_delete=should_delete)
    if should_delete:
        saved_object.delete()
        context["deleted"] = True

    # Store saved object in context and return success
    context["saved"] = saved_object
    return True


def backend_edit(
    request: HttpRequest,
    context: dict,
    form_type: type[BaseModelForm],
    element_uuid: str | None,
    additional_field: str | None = None,
    *,
    is_association: bool = False,
    quiet: bool = False,
) -> bool:
    """Handle backend editing operations for various content types.

    Provides unified interface for editing different model types including
    form processing, validation, logging, and deletion handling for both
    event-based and association-based content management.

    Args:
        request: Django HTTP request object containing user and POST data
        context: Context dictionary for template rendering and data sharing
        form_type: Django ModelForm class for handling the specific model
        element_uuid: Element UUID for editing existing objects, None for new objects
        additional_field: Optional additional field parameter for specialized handling
        is_association: Flag indicating association-based vs event-based operation
        quiet: Flag to suppress success messages when True

    Returns:
        bool: True if form was successfully processed and saved, False otherwise

    """
    # Extract model type and set up basic context variables
    model_type = form_type.Meta.model
    context["elementTyp"] = model_type
    context["request"] = request

    # Resolve element UUID from context if needed
    element_uuid = _resolve_element_uuid(context, element_uuid, is_association=is_association)

    # Load existing element or set as None for new objects
    if element_uuid:
        backend_get(context, model_type, element_uuid, additional_field)
        context["name"] = set_form_name(context["el"])
    else:
        context["el"] = None

    # Set up context for template rendering
    context["num"] = element_uuid
    context["type"] = context["elementTyp"].__name__.lower()

    # Process form submission
    if request.method == "POST":
        if _handle_form_submission(request, context, form_type, quiet=quiet):
            return True
    else:
        # GET request - initialize form with existing instance
        context["form"] = form_type(instance=context["el"], context=context)

    # Handle "add another" functionality for continuous adding
    should_add_another = context.get("add_another", True)
    context["add_another"] = should_add_another
    if should_add_another:
        context["continue_add"] = "continue" in request.POST

    return False


def orga_edit(
    request: HttpRequest,
    event_slug: str,
    permission: str | None,
    form_type: type[BaseModelForm],
    entity_uuid: str | None = None,
    redirect_view: str | None = None,
    additional_context: dict | None = None,
) -> HttpResponse:
    """Edit organization event objects through a unified interface.

    Handles the editing workflow for various organization event objects,
    including permission checking, form processing, and redirects.

    Args:
        request: The HTTP request object
        event_slug: Event slug identifier
        permission: Permission string to check for access control
        form_type: Type of form/object to edit
        entity_uuid: Entity UUID to edit
        redirect_view: Optional redirect view name after successful edit
        additional_context: Optional additional context to merge into template context

    Returns:
        HttpResponse: Redirect response on successful edit, or rendered edit template

    """
    # Check user permissions and get base context for the event
    context = check_event_context(request, event_slug, permission)

    # Merge any additional context provided by caller
    if additional_context:
        context.update(additional_context)

    # Check if this is an iframe request
    is_frame = request.GET.get("frame") == "1" or request.POST.get("frame") == "1"

    # Process the edit operation using backend edit handler
    # Returns True if edit was successful and should redirect
    if backend_edit(request, context, form_type, entity_uuid, additional_field=None, is_association=False):
        # Set suggestion context for successful edit
        set_suggestion(context, permission)

        # Return success template for iframe mode
        if is_frame:
            return render(request, "elements/dashboard/form_success.html", context)

        # Handle "continue editing" workflow - redirect to new object form
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, context["run"].get_slug(), "")

        # Determine redirect target - use provided or default to permission name
        if not redirect_view:
            redirect_view = permission

        # Redirect to success page with event slug
        return redirect(redirect_view, event_slug=context["run"].get_slug())

    # Edit operation failed or is initial load - render edit form
    if is_frame:
        return render(request, "elements/dashboard/form_frame.html", context)
    return render(request, "larpmanager/orga/edit.html", context)


def backend_delete(
    request: HttpRequest,
    context: dict,
    form_type: type[BaseModelForm],
    entity_uuid: str,
    can_delete: Callable | None = None,
) -> None:
    """Delete element from the system."""
    model_type = form_type.Meta.model
    backend_get(context, model_type, entity_uuid, None)

    element = context["el"]

    if can_delete is not None and not can_delete(context, element):
        messages.error(request, _("Operation not allowed"))
        return

    save_log(context["member"], form_type, element, to_delete=True)

    element.delete()

    messages.success(request, _("Operation completed") + "!")


def exe_edit(
    request: HttpRequest,
    form_type: type[BaseModelForm],
    entity_uuid: str | None,
    permission: str,
    redirect_view: str | None = None,
    additional_field: str | None = None,
    additional_context: dict | None = None,
) -> HttpResponse:
    """Handle editing operations for organization-level entities.

    Manages the edit workflow for various entity types at the organization level,
    including permission checking, form processing, and appropriate redirects.

    Args:
        request: HTTP request object containing form data and user information
        form_type: Type of form/entity being edited (e.g., 'member', 'event')
        entity_uuid: Entity UUID for the object being edited
        permission: Permission string required to access this edit functionality
        redirect_view: Optional redirect target after successful edit (defaults to permission)
        additional_field: Optional additional field parameter for the backend edit
        additional_context: Optional additional context dictionary to merge with base context

    Returns:
        HttpResponse: Redirect response on successful edit, or rendered edit template

    """
    # Check user permissions and get base context
    context = check_association_context(request, permission)

    # Merge additional context if provided
    if additional_context:
        context.update(additional_context)

    # Check if this is an iframe request
    is_frame = request.GET.get("frame") == "1" or request.POST.get("frame") == "1"

    # Process the edit operation through backend handler
    if backend_edit(
        request,
        context,
        form_type,
        entity_uuid,
        additional_field=additional_field,
        is_association=True,
    ):
        # Set permission suggestion for UI feedback
        set_suggestion(context, permission)

        # Return success template for iframe mode
        if is_frame:
            return render(request, "elements/dashboard/form_success.html", context)

        # Handle "continue editing" workflow
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, "")

        # Determine redirect target and perform redirect
        if not redirect_view:
            redirect_view = permission
        return redirect(redirect_view)

    # Render appropriate template based on mode
    if is_frame:
        return render(request, "elements/dashboard/form_frame.html", context)
    return render(request, "larpmanager/exe/edit.html", context)


def exe_delete(
    request: HttpRequest,
    form_type: type[BaseModelForm],
    entity_uuid: str,
    permission: str,
    redirect_view: str | None = None,
    can_delete: Callable | None = None,
) -> HttpResponse:
    """Delete organization-level entities through a unified interface.

    Handles the deletion workflow for various organization-level entities,
    including permission checking, logging, and redirects.

    Args:
        request: HTTP request object containing form data and user information
        form_type: Type of form/entity being deleted
        entity_uuid: Entity UUID for the object being deleted
        permission: Permission string required to access this delete functionality
        redirect_view: Optional redirect target after successful deletion (defaults to permission)
        can_delete: Callback to check if deletion can be done

    Returns:
        HttpResponse: Redirect response on successful deletion

    """
    # Check user permissions and get base context
    context = check_association_context(request, permission)

    backend_delete(request, context, form_type, entity_uuid, can_delete)

    if not redirect_view:
        redirect_view = permission

    return redirect(redirect_view)


def set_suggestion(context: dict, permission: str) -> None:
    """Set a suggestion flag for a given permission in the configuration.

    This function sets a boolean flag in the configuration to indicate that
    a suggestion has been made for a specific permission. It works with both
    event and association contexts.

    Args:
        context: Context dictionary containing either 'event' key with event object
                 or 'association_id' key with association ID
        permission: Permission name to create suggestion flag for

    """
    # Determine the target object based on context
    target_object = context["event"] if "event" in context else Association.objects.get(pk=context["association_id"])

    # Build the configuration key for this permission's suggestion
    config_key = f"{permission}_suggestion"
    existing_suggestion = target_object.get_config(config_key, default_value=False)

    # Exit early if suggestion already exists
    if existing_suggestion:
        return

    # Get the foreign key field name for the config model
    foreign_key_field = _get_fkey_config(target_object)

    # Create or retrieve the configuration entry
    (config, _created) = target_object.configs.model.objects.get_or_create(
        **{foreign_key_field: target_object, "name": config_key},
    )

    # Set the suggestion flag to True and save
    config.value = True
    config.save()


def writing_edit(
    request: HttpRequest,
    context: dict,
    form_type: type[BaseModelForm],
    element_uuid: str | None,
    element_type: str | None,
    redirect_url: str | None = None,
) -> HttpResponse | None:
    """Handle editing of writing elements with form processing.

    Manages the creation and editing of writing elements (characters, backgrounds, etc.)
    through a dynamic form system. Handles both GET requests for form display and
    POST requests for form submission and validation.

    Args:
        request: The HTTP request object containing method and form data
        context: Context dictionary containing element data and template variables
        form_type: Django form class to instantiate for editing the element
        element_uuid: UUID of the element to be edited (null if new)
        element_type: Type identifier for the writing element being edited
        redirect_url: Optional redirect URL to use after successful form save

    Returns:
        HttpResponse object for redirect after successful save, None otherwise
        to continue with template rendering

    Note:
        Function modifies the context dictionary in-place to add form and display data.

    """
    # Set up element type metadata for template rendering
    context["elementTyp"] = form_type.Meta.model
    element_name = context["elementTyp"].__name__.lower()

    if element_uuid:
        get_element(context, element_uuid, "el", context["elementTyp"])
        context["edit_uuid"] = element_uuid
        context["name"] = set_form_name(context["el"])
    else:
        context["el"] = None

    # Set type information for template display
    context["type"] = element_name
    context["label_typ"] = context["type"]

    # Handle form submission (POST request)
    if request.method == "POST":
        form = form_type(request.POST, request.FILES, instance=context["el"], context=context)

        # Process valid form data and potentially redirect
        if form.is_valid():
            return _writing_save(context, form, form_type, element_name, redirect_url, request, element_type)
    else:
        # Initialize form for GET request
        form = form_type(instance=context["el"], context=context)

    # Configure template context for form rendering
    context["nm"] = context["type"]
    context["form"] = form
    context["add_another"] = True
    context["continue_add"] = "continue" in request.POST

    # Set auto-save behavior based on event configuration
    context["auto_save"] = not get_event_config(
        context["event"].id, "writing_disable_auto", default_value=False, context=context
    )
    context["download"] = 1

    # Set up character finder functionality for the element type
    _setup_char_finder(context, context["elementTyp"])

    return render(request, "larpmanager/orga/writing/writing.html", context)


def _setup_char_finder(context: dict, model_type: type) -> None:
    """Set up character finder widget for the given context and type.

    Configures a character finder widget based on the event configuration and
    trait/character type. If character finder is disabled for the event, the
    function returns early without setting up the widget.

    Args:
        context: Context dictionary containing event and other template variables
        model_type: Model class type (either Trait or Character) to determine widget type

    Returns:
        None: Modifies the context dictionary in place

    """
    # Check if character finder is disabled for this event
    if get_event_config(context["event"].id, "writing_disable_char_finder", default_value=False, context=context):
        return

    # Select appropriate widget class based on type
    widget_class = EventTraitS2Widget if model_type == Trait else EventCharacterS2Widget

    # Initialize widget with event configuration
    widget = widget_class(attrs={"id": "char_finder"})
    widget.set_event(context["event"])

    # Set up context variables for template rendering
    context["finder_typ"] = model_type._meta.model_name  # noqa: SLF001  # Django model metadata
    context["char_finder"] = widget.render(name="char_finder", value="")
    context["char_finder_media"] = widget.media


def _writing_save(
    context: dict,
    form: BaseModelForm,
    form_type: type,
    type_name: str,
    redirect_func: Callable | None,
    request: HttpRequest,
    tp: str | None,
) -> HttpResponse:
    """Save writing form data with AJAX and normal save handling.

    Handles both AJAX auto-save requests and normal form submissions. For normal saves,
    creates version history if type is provided, otherwise logs the operation. Supports
    deletion via POST parameter and various redirect behaviors.

    Args:
        context: Context dictionary containing element data and run information
        form: Validated form instance ready for saving
        form_type: Form class type used for logging operations
        type_name: Name of the element in context (used for redirects)
        redirect_func: Optional redirect callable that takes context as parameter
        request: HTTP request object containing POST data and user info
        tp: Type of writing element for version tracking (None disables versioning)

    Returns:
        HttpResponse: AJAX JSON response for auto-save or HTTP redirect after normal save

    """
    # Handle AJAX auto-save requests
    if "ajax" in request.POST:
        # Check if element exists in context before processing
        if context["el"]:
            return writing_edit_save_ajax(form, request)
        return JsonResponse({"res": "ko"})

    # Process normal form submission
    # Save form data but keep as temporary until processing complete
    p = form.save(commit=False)
    p.temp = False
    p.save()

    # Check if deletion was requested via POST parameter
    dl = "delete" in request.POST and request.POST["delete"] == "1"

    # Create version history or log operation based on type parameter
    if tp:
        save_version(p, tp, context["member"], to_delete=dl)
    else:
        save_log(context["member"], form_type, p)

    # Execute deletion if requested after logging/versioning
    if dl:
        p.delete()

    # Display success message to user
    messages.success(request, _("Operation completed") + "!")

    # Handle continue editing request
    if "continue" in request.POST:
        return redirect(request.resolver_match.view_name, context["run"].get_slug(), "")

    # Handle custom redirect function if provided
    if redirect_func:
        context["element"] = p
        return redirect_func(context)

    # Default redirect to list view
    return redirect("orga_" + type_name + "s", event_slug=context["run"].get_slug())


def writing_edit_cache_key(element_uuid: str, writing_type: str, association_id: int) -> str:
    """Generate cache key for writing edit operations."""
    return f"orga_edit_{association_id}_{element_uuid}_{writing_type}"


def writing_edit_save_ajax(form: BaseModelForm, request: HttpRequest) -> JsonResponse:
    """Handle AJAX save requests for writing elements with locking validation.

    This function processes AJAX requests to save writing elements while validating
    user permissions and checking for editing conflicts through a token-based
    locking mechanism.

    Args:
        form: Django form instance containing the data to save
        request: HTTP request object containing POST data and user information

    Returns:
        JsonResponse: JSON response containing either success status or warning message
            - On success: {"res": "ok"}
            - On warning: {"res": "ok", "warn": "warning message"}

    """
    # Initialize default success response
    res = {"res": "ok"}

    # Superusers bypass all validation checks
    if is_lm_admin(request):
        return JsonResponse(res)

    # Extract and validate element ID from POST data
    edit_uuid = request.POST["edit_uuid"]
    if not edit_uuid:
        return JsonResponse(res)

    # Get element type and editing token for conflict detection
    tp = request.POST["type"]
    token = request.POST["token"]

    # Check for editing conflicts using token-based locking
    msg = writing_edit_working_ticket(request, tp, edit_uuid, token)
    if msg:
        res["warn"] = msg
        return JsonResponse(res)

    # Save form data as temporary version
    p = form.save(commit=False)
    p.temp = True
    p.save()

    return JsonResponse(res)


def writing_edit_working_ticket(request: HttpRequest, element_type: str, edit_uuid: str, user_token: str) -> str:
    """Manage working tickets to prevent concurrent editing conflicts.

    This function implements a locking mechanism to prevent multiple users from
    editing the same content simultaneously, which could result in data loss.
    For plot objects, it recursively checks all related characters.

    Args:
        request: HTTP request object containing user information and association context
        element_type: Type of element being edited (e.g., 'plot', 'character')
        edit_uuid: Element UUID being edited
        user_token: User's unique editing token for session identification

    Returns:
        Warning message if editing conflicts exist, empty string if safe to edit

    Note:
        Uses Redis cache with a 5-second timeout window to track active editors.
        Cache timeout is set to minimum of ticket_time and 1 day.
        Each association has its own isolated cache space.

    """
    # Superusers bypass all validation checks
    if is_lm_admin(request):
        return ""

    context = get_context(request)
    association_id = context["association_id"]

    # Handle plot objects by recursively checking all related characters
    # This prevents conflicts when editing plots that affect multiple characters
    if element_type == "plot":
        character_uuids = Plot.objects.filter(uuid=edit_uuid).values_list("characters__uuid", flat=True)
        for character_uuid in character_uuids:
            if character_uuid is None:  # Skip if plot has no characters
                continue
            warning_message = writing_edit_working_ticket(request, "character", character_uuid, user_token)
            if warning_message:
                return warning_message

    # Get current timestamp and retrieve existing ticket from cache
    current_timestamp = int(time.time())
    cache_key = writing_edit_cache_key(edit_uuid, element_type, association_id)
    active_tickets = cache.get(cache_key)
    if not active_tickets:
        active_tickets = {}

    # Check for other active editors within the timeout window
    other_editors = []
    ticket_timeout_seconds = 5  # 5 second timeout for editing conflicts
    for token_id, editor_info in active_tickets.items():
        (editor_name, last_edit_timestamp) = editor_info
        # Only consider other users' tokens within the timeout period
        if token_id != user_token and current_timestamp - last_edit_timestamp < ticket_timeout_seconds:
            other_editors.append(editor_name)

    # Generate warning message if other users are currently editing
    warning_message = ""
    if len(other_editors) > 0:
        warning_message = _("Warning! Other users are editing this item") + "."
        warning_message += " " + _("You cannot work on it at the same time: the work of one of you would be lost") + "."
        warning_message += " " + _("List of other users") + ": " + ", ".join(other_editors)

    # Update ticket with current user's information and timestamp
    active_tickets[user_token] = (str(request.user.member), current_timestamp)
    # Cache the updated ticket with appropriate timeout
    cache.set(cache_key, active_tickets, min(ticket_timeout_seconds, conf_settings.CACHE_TIMEOUT_1_DAY))

    return warning_message


def form_edit_handler(  # noqa: PLR0913
    request: HttpRequest,
    context: dict,
    question_uuid: str | None,
    perm: str,
    option_model: type[BaseModel],
    form_class: type[BaseModelForm],
    redirect_view_name: str,
    redirect_list_view_name: str,
    template_name: str,
    extra_redirect_kwargs: dict | None = None,
) -> HttpResponse:
    """Generic handler for question form editing (registration and writing).

    Args:
        request: HTTP request object
        context: Event context from check_event_context
        question_uuid: Question UUID to edit (0 for new questions)
        perm: Permission name for set_suggestion
        option_model: Option model class (RegistrationOption or WritingOption)
        form_class: Form class (OrgaRegistrationQuestionForm or OrgaWritingQuestionForm)
        redirect_view_name: View name for redirect when options needed
        redirect_list_view_name: View name for redirect to list
        template_name: Template to render
        extra_redirect_kwargs: Extra kwargs for redirect URL (e.g., {"writing_type": writing_type})

    Returns:
        HttpResponse: Rendered template or redirect
    """
    # Check if this is an AJAX request
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    # Process form submission using backend edit utility
    if backend_edit(request, context, form_class, question_uuid, is_association=False, quiet=True):
        # Set permission suggestion for future operations
        set_suggestion(context, perm)

        # If item was deleted, redirect to list view
        if request.POST.get("delete") == "1":
            messages.success(request, _("Operation completed") + "!")
            redirect_kwargs = {"event_slug": context["run"].get_slug(), **(extra_redirect_kwargs or {})}
            return redirect(redirect_list_view_name, **redirect_kwargs)

        # If AJAX request, return JSON with question UUID
        if is_ajax:
            return JsonResponse(
                {
                    "success": True,
                    "question_uuid": str(context["saved"].uuid),
                    "message": str(_("Question saved successfully")),
                }
            )

        # Handle "continue editing" button - redirect to new question form
        if "continue" in request.POST:
            messages.success(request, _("Operation completed") + "!")
            if extra_redirect_kwargs:  # writing form
                redirect_kwargs = {
                    "event_slug": context["run"].get_slug(),
                    "question_uuid": "",
                    **extra_redirect_kwargs,
                }
            else:  # registration form
                redirect_kwargs = {"event_slug": context["run"].get_slug(), "question_uuid": ""}
            return redirect(request.resolver_match.view_name, **redirect_kwargs)

        # Check if question is single/multiple choice and needs options
        is_choice = context["saved"].typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]
        if is_choice and not option_model.objects.filter(question_id=context["saved"].id).exists():
            messages.warning(
                request,
                _("You must define at least one option before saving a single-choice or multiple-choice question"),
            )

            # Redirect to question page
            redirect_kwargs = {
                "event_slug": context["run"].get_slug(),
                "question_uuid": context["saved"].uuid,
                **(extra_redirect_kwargs or {}),
            }
            return redirect(redirect_view_name, **redirect_kwargs)

        messages.success(request, _("Operation completed") + "!")
        redirect_kwargs = {"event_slug": context["run"].get_slug(), **(extra_redirect_kwargs or {})}
        return redirect(redirect_list_view_name, **redirect_kwargs)

    return render(request, template_name, context)


def options_edit_handler(
    request: HttpRequest,
    context: dict,
    option_uuid: str | None,
    question_model: type[BaseModel],
    option_model: type[BaseModel],
    form_class: type[BaseModelForm],
    extra_context: dict | None = None,
) -> HttpResponse:
    """Handler for option form submission (iframe mode).

    Args:
        request: HTTP request object
        context: Event context from check_event_context
        option_uuid: Option UUID to edit (0 for new options)
        question_model: Question model class (RegistrationQuestion or WritingQuestion)
        option_model: Option model class (RegistrationOption or WritingOption)
        form_class: Form class (OrgaRegistrationOptionForm or OrgaWritingOptionForm)
        extra_context: Additional context to add to form_context (e.g., {"typ": writing_type})

    Returns:
        HttpResponse with form page (iframe mode)
    """
    # For new options, get the question_uuid from request
    if not option_uuid:
        question_uuid = request.GET.get("question_uuid") or request.POST.get("question_uuid")
        if question_uuid:
            get_element(context, question_uuid, "question", question_model)
    else:
        # For editing existing option, load the option instance
        get_element(context, option_uuid, "el", option_model)
        context["question"] = context["el"].question

    # Try saving it
    if backend_edit(request, context, form_class, option_uuid, is_association=False):
        return render(request, "elements/options/form_success.html", context)

    # If form validation failed, return form with errors
    form_context = {
        **context,
        "num": option_uuid,
        **(extra_context or {}),
    }

    return render(request, "elements/options/form_frame.html", form_context)


@require_POST
def working_ticket(request: HttpRequest) -> Any:
    """Handle working ticket requests to prevent concurrent editing conflicts."""
    if not request.user.is_authenticated:
        return JsonResponse({"warn": "User not logged"})

    res = {"res": "ok"}
    if is_lm_admin(request):
        return JsonResponse(res)

    edit_uuid = str(request.POST.get("edit_uuid"))
    element_type = request.POST.get("type")
    token = request.POST.get("token")

    msg = writing_edit_working_ticket(request, element_type, edit_uuid, token)
    if msg:
        res["warn"] = msg

    return JsonResponse(res)
