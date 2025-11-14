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
from larpmanager.models.form import QuestionApplicable, WritingAnswer, WritingChoice, WritingQuestion
from larpmanager.models.member import Log, Member
from larpmanager.models.writing import Plot, PlotCharacterRel, Relationship, TextVersion
from larpmanager.utils.auth import is_lm_admin
from larpmanager.utils.base import check_association_context, check_event_context
from larpmanager.utils.common import html_clean
from larpmanager.utils.exceptions import NotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.forms import Form, ModelForm, forms

    from larpmanager.forms.base import MyForm


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


def user_edit(request: HttpRequest, context: dict, form_type: type, model_name: str, entity_id: int) -> bool:
    """Edit user data with validation.

    Handle both GET and POST requests for editing user data. On POST, validate
    the form and save the instance. Support deletion functionality when
    'delete' parameter is set to '1' in POST data.

    Args:
        request: HTTP request object containing method and POST data
        context: Context dictionary containing model data and form instance
        form_type: Django form class to use for data validation and editing
        model_name: Name key for accessing the model instance in context dictionary
        entity_id: Entity ID for editing, used for form numbering (0 for new instances)

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
    context["num"] = entity_id

    # Add string representation of instance name for existing entities
    if entity_id != 0:
        context["name"] = str(context[model_name])

    return False


def backend_get(context: dict, model_type: type, entity_id: int, association_field: str | None = None) -> None:
    """Retrieve an object by ID and perform security checks.

    Args:
        context: Context dictionary to store the retrieved object
        model_type: Model class to query
        entity_id: Primary key of the object to retrieve
        association_field: Optional field name for additional checks

    Raises:
        NotFoundError: If object with given ID doesn't exist

    """
    # Retrieve object by primary key, handle any database exceptions
    try:
        element = model_type.objects.get(pk=entity_id)
    except Exception as err:
        raise NotFoundError from err

    # Store object in context and perform security validations
    context["el"] = element
    check_run(element, context, association_field)
    check_association(element, context, association_field)

    # Set display name for the object
    context["name"] = str(element)


def backend_edit(  # noqa: C901 - Complex editing logic with form validation and POST processing
    request: HttpRequest,
    context: dict[str, Any],
    form_type: type[ModelForm],
    element_id: int | None,
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
        element_id: Element ID for editing existing objects, None for new objects
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

    # Handle association-based operations vs event-based operations
    if is_association:
        context["exe"] = True
        if element_id is None:
            element_id = context["association_id"]
            context["nonum"] = True
    elif element_id is None:
        element_id = context["event"].id
        context["nonum"] = True

    # Load existing element or set as None for new objects
    if element_id != 0:
        backend_get(context, model_type, element_id, additional_field)
    else:
        context["el"] = None

    # Set up context for template rendering
    context["num"] = element_id
    context["type"] = context["elementTyp"].__name__.lower()

    # Process POST request - form submission and validation
    if request.method == "POST":
        context["form"] = form_type(request.POST, request.FILES, instance=context["el"], context=context)

        if context["form"].is_valid():
            # Save the form and show success message if not in quiet mode
            saved_object = context["form"].save()
            if not quiet:
                messages.success(request, _("Operation completed") + "!")

            # Handle deletion if delete flag is set in POST data
            to_delete = "delete" in request.POST and request.POST["delete"] == "1"
            save_log(context["member"], form_type, saved_object, to_delete=to_delete)
            if to_delete:
                saved_object.delete()

            # Store saved object in context and return success
            context["saved"] = saved_object
            return True
    else:
        # GET request - initialize form with existing instance
        context["form"] = form_type(instance=context["el"], context=context)

    # Set display name for existing objects
    if element_id != 0:
        context["name"] = str(context["el"])

    # Handle "add another" functionality for continuous adding
    context["add_another"] = "add_another" not in context or context["add_another"]
    if context["add_another"]:
        context["continue_add"] = "continue" in request.POST

    return False


def orga_edit(
    request: HttpRequest,
    event_slug: str,
    permission: str | None,
    form_type: type[MyForm],
    entity_id: int | None = None,
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
        entity_id: Entity ID to edit
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

    # Process the edit operation using backend edit handler
    # Returns True if edit was successful and should redirect
    if backend_edit(request, context, form_type, entity_id, additional_field=None, is_association=False):
        # Set suggestion context for successful edit
        set_suggestion(context, permission)

        # Handle "continue editing" workflow - redirect to new object form
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, event_slug=context["run"].get_slug(), num=0)

        # Determine redirect target - use provided or default to permission name
        if not redirect_view:
            redirect_view = permission

        # Redirect to success page with event slug
        return redirect(redirect_view, event_slug=context["run"].get_slug())

    # Edit operation failed or is initial load - render edit form
    return render(request, "larpmanager/orga/edit.html", context)


def exe_edit(
    request: HttpRequest,
    form_type: type[MyForm],
    entity_id: int,
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
        entity_id: Entity ID for the object being edited
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

    # Process the edit operation through backend handler
    if backend_edit(
        request,
        context,
        form_type,
        entity_id,
        additional_field=additional_field,
        is_association=True,
    ):
        # Set permission suggestion for UI feedback
        set_suggestion(context, permission)

        # Handle "continue editing" workflow
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, num=0)

        # Determine redirect target and perform redirect
        if not redirect_view:
            redirect_view = permission
        return redirect(redirect_view)

    # Render edit template if edit operation was not successful
    return render(request, "larpmanager/exe/edit.html", context)


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
    context: dict[str, Any],
    form_type: type[forms.Form],
    element_name: str,
    element_type: str,
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
        element_name: Name key of the element in the context dictionary
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

    # Configure element identification and naming
    if element_name in context:
        context["eid"] = context[element_name].id
        context["name"] = str(context[element_name])
    else:
        context[element_name] = None

    # Set type information for template display
    context["type"] = context["elementTyp"].__name__.lower()
    context["label_typ"] = context["type"]

    # Handle form submission (POST request)
    if request.method == "POST":
        form = form_type(request.POST, request.FILES, instance=context[element_name], context=context)

        # Process valid form data and potentially redirect
        if form.is_valid():
            return _writing_save(context, form, form_type, element_name, redirect_url, request, element_type)
    else:
        # Initialize form for GET request
        form = form_type(instance=context[element_name], context=context)

    # Configure template context for form rendering
    context["nm"] = element_name
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
    form: Form,
    form_type: type,
    nm: str,
    redr: Callable | None,
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
        nm: Name of the element in context (used for redirects)
        redr: Optional redirect callable that takes context as parameter
        request: HTTP request object containing POST data and user info
        tp: Type of writing element for version tracking (None disables versioning)

    Returns:
        HttpResponse: AJAX JSON response for auto-save or HTTP redirect after normal save

    """
    # Handle AJAX auto-save requests
    if "ajax" in request.POST:
        # Check if element exists in context before processing
        if nm in context:
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
        return redirect(request.resolver_match.view_name, event_slug=context["run"].get_slug(), num=0)

    # Handle custom redirect function if provided
    if redr:
        context["element"] = p
        return redr(context)

    # Default redirect to list view
    return redirect("orga_" + nm + "s", event_slug=context["run"].get_slug())


def writing_edit_cache_key(event_id: int, writing_type: str) -> str:
    """Generate cache key for writing edit operations."""
    return f"orga_edit_{event_id}_{writing_type}"


def writing_edit_save_ajax(form: Form, request: HttpRequest) -> JsonResponse:
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
    eid = int(request.POST["eid"])
    if eid <= 0:
        return res

    # Get element type and editing token for conflict detection
    tp = request.POST["type"]
    token = request.POST["token"]

    # Check for editing conflicts using token-based locking
    msg = writing_edit_working_ticket(request, tp, eid, token)
    if msg:
        res["warn"] = msg
        return JsonResponse(res)

    # Save form data as temporary version
    p = form.save(commit=False)
    p.temp = True
    p.save()

    return JsonResponse(res)


def writing_edit_working_ticket(request: HttpRequest, element_type: str, element_id: int, user_token: str) -> str:
    """Manage working tickets to prevent concurrent editing conflicts.

    This function implements a locking mechanism to prevent multiple users from
    editing the same content simultaneously, which could result in data loss.
    For plot objects, it recursively checks all related characters.

    Args:
        request: HTTP request object containing user information
        element_type: Type of element being edited (e.g., 'plot', 'character')
        element_id: Element ID being edited
        user_token: User's unique editing token for session identification

    Returns:
        Warning message if editing conflicts exist, empty string if safe to edit

    Note:
        Uses Redis cache with a 15-second timeout window to track active editors.
        Cache timeout is set to minimum of ticket_time and 1 day.

    """
    # Superusers bypass all validation checks
    if is_lm_admin(request):
        return ""

    # Handle plot objects by recursively checking all related characters
    # This prevents conflicts when editing plots that affect multiple characters
    if element_type == "plot":
        character_ids = Plot.objects.filter(pk=element_id).values_list("characters__pk", flat=True)
        for character_id in character_ids:
            if character_id is None:  # Skip if plot has no characters
                continue
            warning_message = writing_edit_working_ticket(request, "character", character_id, user_token)
            if warning_message:
                return warning_message

    # Get current timestamp and retrieve existing ticket from cache
    current_timestamp = int(time.time())
    cache_key = writing_edit_cache_key(element_id, element_type)
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


@require_POST
def working_ticket(request: HttpRequest) -> Any:
    """Handle working ticket requests to prevent concurrent editing conflicts.

    Args:
        request: HTTP POST request with eid, type, and token parameters

    Returns:
        JsonResponse: Status response with optional warning if other users are editing

    """
    if not request.user.is_authenticated:
        return JsonResponse({"warn": "User not logged"})

    res = {"res": "ok"}
    if is_lm_admin(request):
        return JsonResponse(res)

    eid = request.POST.get("eid")
    element_type = request.POST.get("type")
    token = request.POST.get("token")

    msg = writing_edit_working_ticket(request, element_type, eid, token)
    if msg:
        res["warn"] = msg

    return JsonResponse(res)
