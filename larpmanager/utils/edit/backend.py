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

import re
import time
from typing import TYPE_CHECKING, Any

from django.conf import settings as conf_settings
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Max
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.cache.config import _get_fkey_config, get_event_config
from larpmanager.forms.utils import EventCharacterS2Widget, EventTraitS2Widget
from larpmanager.models.association import Association
from larpmanager.models.casting import Trait
from larpmanager.models.event import Run
from larpmanager.models.form import QuestionApplicable, WritingAnswer, WritingChoice, WritingQuestion
from larpmanager.models.member import LogOperationType, Member
from larpmanager.models.miscellanea import Log
from larpmanager.models.writing import Plot, PlotCharacterRel, Relationship, TextVersion
from larpmanager.utils.auth.admin import is_lm_admin
from larpmanager.utils.core.base import get_context
from larpmanager.utils.core.common import get_element, get_object_uuid, html_clean

if TYPE_CHECKING:
    from collections.abc import Callable

    from larpmanager.forms.base import BaseModelForm
    from larpmanager.models.base import BaseModel


def save_log(
    context: dict,
    cls: BaseModel,
    element: Any,
    element_uuid: str | None = None,
    *,
    operation_type: str | None = None,
    info: str | None = None,
) -> None:
    """Create a log entry for model instance changes.

    Args:
        context: Dict context
        cls: Model class of the element
        element: The element being logged
        element_uuid: UUID of element (None = new, non-None = update)
        operation_type: Type of operation (NEW/UPDATE/DELETE/BULK). If None, auto-detect from element_uuid
        info: Additional informations

    """
    # Auto-detect operation type if not specified
    if operation_type is None:
        operation_type = LogOperationType.NEW if element_uuid is None else LogOperationType.UPDATE

    # Extract element name
    element_name = ""
    if hasattr(element, "name") and element.name:
        element_name = str(element.name)
    elif hasattr(element, "title") and element.title:
        element_name = str(element.title)
    else:
        element_name = str(element)

    instance = context.get("run", context["association_id"])
    if isinstance(instance, Run):
        run_id = instance.id
        association_id = instance.event.association_id
    else:
        run_id = None
        association_id = instance

    if info:
        info = info[:500]

    Log.objects.create(
        member=context["member"],
        cls=cls.__name__,
        eid=element.id,
        dct=element.as_dict(),
        operation_type=operation_type,
        element_name=element_name[:500],
        info=info,
        run_id=run_id,
        association_id=association_id,
    )


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
    request: HttpRequest,
    context: dict,
    form_type: type,
    model_name: str,
    entity_uuid: str | None = None,
    save_callback: Callable[[Any, dict], Any] | None = None,
    delete_callback: Callable[[Any], None] | None = None,
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
        save_callback: Optional custom save function (form, context) -> instance
        delete_callback: Optional custom delete function (instance) -> None

    Returns:
        True if form was successfully processed and saved, False if form
        validation failed or GET request requires form display.

    Side Effects:
        - Adds success message to request on successful save
        - Logs the operation using save_log function (unless custom callbacks used)
        - Deletes instance if delete flag is set
        - Updates context with 'saved', 'form', 'num', and optionally 'name' keys

    """
    if request.method == "POST":
        # Initialize form with POST data and files, bind to existing instance
        form = form_type(request.POST, request.FILES, instance=context[model_name], context=context)

        info = re.sub(r"^(Exe|Orga)|Form$", "", form_type.__name__)

        if form.is_valid():
            # Check if delete operation was requested
            should_delete = "delete" in request.POST and request.POST["delete"] == "1"

            if should_delete:
                # Use delete callback if provided
                if delete_callback:
                    delete_callback(context[model_name])
                else:
                    # Default delete behavior
                    model_type = form_type.Meta.model
                    save_log(
                        context, model_type, context[model_name], operation_type=LogOperationType.DELETE, info=info
                    )
                    context[model_name].delete()

                messages.success(request, _("Operation completed") + "!")
                context["saved"] = context[model_name]
                return True

            # Use save callback if provided
            if save_callback:
                saved_instance = save_callback(form, context)
            else:
                # Default save behavior
                saved_instance = form.save()
                model_type = form_type.Meta.model
                save_log(context, model_type, saved_instance, entity_uuid, info=info)

            messages.success(request, _("Operation completed") + "!")
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


def backend_get(
    context: dict,
    model_type: BaseModel,
    entity_uuid: str,
    association_field: str | None = None,
    *,
    is_writing: bool = False,
) -> None:
    """Retrieve an object by ID and perform security checks.

    Args:
        context: Context dictionary to store the retrieved object
        model_type: Model class to query
        entity_uuid: UUID of the object to retrieve
        association_field: Optional field name for additional checks
        is_writing: If True, use writing-specific loading and naming

    Raises:
        Http404: If object with given ID doesn't exist

    """
    # Retrieve object by UUID using appropriate method
    if is_writing:
        # For writing elements, use get_element with proper checks
        get_element(context, entity_uuid, "el", model_type)
        context["edit_uuid"] = entity_uuid
    else:
        # Standard retrieval
        element = get_object_uuid(model_type, entity_uuid)
        context["el"] = element
        # Perform security validations
        check_run(element, context, association_field)
        check_association(element, context, association_field)

    # Set display name for the object
    context["name"] = set_form_name(context["el"])


def _resolve_element_uuid(
    context: dict,
    element_uuid: str | None,
) -> str | None:
    """Resolve element UUID from context if None."""
    if element_uuid is not None:
        return element_uuid

    if context.get("member_form"):
        return context["member"].id

    if context.get("assoc_form"):
        context["exe"] = True
        context["nonum"] = True
        return context["uuid"]

    if context.get("event_form"):
        context["nonum"] = True
        return context["event"].uuid

    return None


def _backend_save(
    request: HttpRequest,
    context: dict,
    form_type: type[BaseModelForm],
    *,
    quiet: bool,
    writing_type: str | None = None,
) -> bool | HttpResponse:
    """Handle form submission and return True if saved successfully, or HttpResponse for AJAX."""
    context["form"] = form_type(request.POST, request.FILES, instance=context["el"], context=context)

    if not context["form"].is_valid():
        return False

    # Handle AJAX auto-save for writing elements
    if writing_type and "ajax" in request.POST:
        if context["el"]:
            return backend_save_ajax(context["form"], request)
        return JsonResponse({"res": "ko"})

    # Save the form
    saved_object = context["form"].save()

    # For writing elements, manage temp flag
    if writing_type:
        saved_object.temp = False
        saved_object.save(update_fields=["temp"])

    model_type = form_type.Meta.model

    # Show success message if not in quiet mode
    if not quiet:
        messages.success(request, _("Operation completed") + "!")

    # Handle deletion if delete flag is set in POST data
    should_delete = request.POST.get("delete") == "1"

    # Use versioning for writing elements, logging for others
    if writing_type:
        save_version(saved_object, writing_type, context["member"], to_delete=should_delete)

    # Log with appropriate operation type
    log_info = re.sub(r"^(Exe|Orga)|Form$", "", form_type.__name__)
    if should_delete:
        save_log(context, model_type, saved_object, operation_type=LogOperationType.DELETE, info=log_info)
    else:
        # Detect NEW vs UPDATE based on whether element existed before
        element_uuid = None if context["el"] is None else context["el"].uuid
        save_log(context, model_type, saved_object, element_uuid=element_uuid, info=log_info)

    if should_delete:
        saved_object.delete()
        context["deleted"] = True

    # Store saved object in context and return success
    context["saved"] = saved_object
    return True


def backend_save_ajax(form: BaseModelForm, request: HttpRequest) -> JsonResponse:
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
    edit_uuid = request.POST.get("edit_uuid", "")
    if not edit_uuid:
        return JsonResponse(res)

    # Get element type and editing token for conflict detection
    tp = request.POST.get("type", "")
    token = request.POST.get("token", "")

    # Check for editing conflicts using token-based locking
    msg = _process_working_ticket(request, tp, edit_uuid, token)
    if msg:
        res["warn"] = msg
        return JsonResponse(res)

    # Save form data as temporary version
    saved_object = form.save()
    saved_object.temp = True
    saved_object.save(update_fields=["temp"])

    return JsonResponse(res)


def backend_edit(
    request: HttpRequest,
    context: dict,
    form_type: type[BaseModelForm],
    element_uuid: str | None = None,
    additional_field: str | None = None,
    *,
    quiet: bool = False,
    writing_type: str | None = None,
) -> bool | HttpResponse:
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
        quiet: Flag to suppress success messages when True
        writing_type: Optional writing type for versioning (enables writing-specific features)

    Returns:
        bool | HttpResponse: True if form was successfully processed and saved,
                            False otherwise, or HttpResponse for AJAX requests

    """
    # Extract model type and set up basic context variables
    model_type = form_type.Meta.model
    context["elementTyp"] = model_type
    context["request"] = request

    # Resolve element UUID from context if needed
    element_uuid = _resolve_element_uuid(context, element_uuid)

    # Load existing element or set as None for new objects
    if element_uuid:
        backend_get(context, model_type, element_uuid, additional_field, is_writing=bool(writing_type))
    else:
        context["el"] = None

    # Set up context for template rendering
    context["num"] = element_uuid
    context["type"] = context["elementTyp"].__name__.lower()

    is_ajax_save = request.method == "POST" and request.POST.get("ajax") == "1"

    # Configure writing-specific context if this is a writing element
    if writing_type and not is_ajax_save:
        context["label_typ"] = context["type"]
        context["nm"] = context["type"]
        context["is_writing"] = True  # Flag to indicate writing element

        # Set auto-save behavior based on event configuration
        if "event" in context:
            context["auto_save"] = not get_event_config(
                context["event"].id, "writing_disable_auto", default_value=False, context=context
            )
            context["download"] = 1

            # Set up character finder functionality
            _setup_char_finder(context, model_type)

    # Process form submission
    if request.method == "POST":
        result = _backend_save(request, context, form_type, quiet=quiet, writing_type=writing_type)
        # If it's an HttpResponse (AJAX), return it directly
        if isinstance(result, HttpResponse):
            return result
        if result:
            return True
    else:
        # Initialize form with existing instance
        context["form"] = form_type(instance=context["el"], context=context)

    # Handle "add another" functionality for continuous adding
    should_add_another = context.get("add_another", True)
    context["add_another"] = should_add_another
    if should_add_another:
        context["continue_add"] = "continue" in request.POST

    return False


def backend_delete(
    request: HttpRequest,
    context: dict,
    model_type: BaseModel,
    entity_uuid: str,
    can_delete: Callable | None = None,
) -> None:
    """Delete element from the system."""
    backend_get(context, model_type, entity_uuid, None)

    element = context["el"]

    if can_delete is not None and not can_delete(context, element):
        messages.error(request, _("Operation not allowed"))
        return

    save_log(context, model_type, element, operation_type=LogOperationType.DELETE)

    element.delete()

    messages.success(request, _("Operation completed") + "!")


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


def working_ticket_cache_key(element_uuid: str, writing_type: str, association_id: int) -> str:
    """Generate cache key for writing edit operations."""
    return f"orga_edit_{association_id}_{element_uuid}_{writing_type}"


def _process_working_ticket(request: HttpRequest, element_type: str, edit_uuid: str, user_token: str) -> str:
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
            warning_message = _process_working_ticket(request, "character", character_uuid, user_token)
            if warning_message:
                return warning_message

    # Get current timestamp and retrieve existing ticket from cache
    current_timestamp = int(time.time())
    cache_key = working_ticket_cache_key(edit_uuid, element_type, association_id)
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
    """Handle working ticket requests to prevent concurrent editing conflicts."""
    if not request.user.is_authenticated:
        return JsonResponse({"warn": "User not logged"})

    res = {"res": "ok"}
    if is_lm_admin(request):
        return JsonResponse(res)

    edit_uuid = str(request.POST.get("edit_uuid"))
    element_type = request.POST.get("type")
    token = request.POST.get("token")

    msg = _process_working_ticket(request, element_type, edit_uuid, token)
    if msg:
        res["warn"] = msg

    return JsonResponse(res)


def backend_order(
    context: dict, model_class: type, element_uuid: str, move_up: int, elements: object | None = None
) -> None:
    """Exchange ordering positions between two elements in a sequence.

    This function moves an element up or down in the ordering sequence by swapping
    its order value with an adjacent element. If no adjacent element exists,
    it simply increments or decrements the order value.

    Args:
        context: Context dictionary to store the current element after operation.
        model_class: Model class of elements to reorder.
        element_uuid: UUID of the element to move.
        move_up: Direction to move - 1 for up (increase order), 0 for down (decrease order).
        elements: Optional queryset of elements. Defaults to event elements if None.

    Returns:
        None: Function modifies elements in-place and updates context['current'].

    Note:
        The function handles edge cases where elements have the same order value
        by adjusting one of them to maintain proper ordering.

    """
    # Get elements queryset, defaulting to event elements if not provided
    elements = elements or context["event"].get_elements(model_class)
    current_element = elements.get(uuid=element_uuid)

    # Determine direction: move_up=True means move up (increase order), False means down
    queryset = (
        elements.filter(order__gt=current_element.order)
        if move_up
        else elements.filter(order__lt=current_element.order)
    )
    queryset = queryset.order_by("order" if move_up else "-order")

    # Apply additional filters based on current element's attributes
    # This ensures we only swap within the same logical group
    for attribute_name in ("question", "section", "applicable"):
        if hasattr(current_element, attribute_name):
            queryset = queryset.filter(**{attribute_name: getattr(current_element, attribute_name)})

    # Get the next element in the desired direction
    adjacent_element = queryset.first()

    # If no adjacent element found, just increment/decrement order
    if not adjacent_element:
        current_element.order += 1 if move_up else -1
        current_element.save()
        context["current"] = current_element
        return

    # Exchange ordering values between current and adjacent element
    current_element.order, adjacent_element.order = adjacent_element.order, current_element.order

    # Handle edge case where both elements have same order (data inconsistency)
    if current_element.order == adjacent_element.order:
        adjacent_element.order += -1 if move_up else 1

    # Save both elements and update context
    current_element.save()
    adjacent_element.save()
    context["current"] = current_element
