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

import time
from typing import Any, Callable, Optional

from django.conf import settings as conf_settings
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Max
from django.forms import Form, ModelForm, forms
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.cache.config import _get_fkey_config, get_event_config
from larpmanager.forms.utils import EventCharacterS2Widget, EventTraitS2Widget
from larpmanager.models.association import Association
from larpmanager.models.casting import Trait
from larpmanager.models.form import QuestionApplicable, WritingAnswer, WritingChoice, WritingQuestion
from larpmanager.models.member import Log
from larpmanager.models.writing import Plot, PlotCharacterRel, Relationship, TextVersion
from larpmanager.utils.base import check_assoc_permission
from larpmanager.utils.common import html_clean
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.exceptions import NotFoundError


def save_log(member, cls, el, dl=False):
    Log.objects.create(member=member, cls=cls.__name__, eid=el.id, dl=dl, dct=el.as_dict())


def save_version(el, tp: str, mb, dl: bool = False) -> None:
    """Manage versioning of text content.

    Creates and saves new versions of editable text elements with author tracking,
    handling different content types including character relationships, plot
    character associations, and question-based text fields.

    Args:
        el: The element object to create a version for
        tp: Type identifier for the content being versioned
        mb: Member object representing the author of this version
        dl: Whether this version should be marked for deletion, defaults to False

    Returns:
        None
    """
    # Get the highest version number for this element and increment it
    n = TextVersion.objects.filter(tp=tp, eid=el.id).aggregate(Max("version"))["version__max"]
    if n is None:
        n = 1
    else:
        n += 1

    # Create new TextVersion instance with basic metadata
    tv = TextVersion()
    tv.eid = el.id
    tv.tp = tp
    tv.version = n
    tv.member = mb
    tv.dl = dl

    # Handle question-based content types by aggregating answers
    if tp in QuestionApplicable.values:
        texts = []
        query = el.event.get_elements(WritingQuestion)

        # Collect all applicable questions and their values
        for que in query.filter(applicable=tp).order_by("order"):
            value = _get_field_value(el, que)
            if not value:
                continue
            value = html_clean(value)
            texts.append(f"{que.name}: {value}")

        tv.text = "\n".join(texts)
    else:
        # For non-question types, use the element's text directly
        tv.text = el.text

    # Add character relationships if this is a character type
    if tp == QuestionApplicable.CHARACTER:
        rels = Relationship.objects.filter(source=el)
        if rels:
            tv.text += "\nRelationships\n"
            for rel in rels:
                tv.text += f"{rel.target}: {html_clean(rel.text)}\n"

    # Add plot character associations if this is a plot type
    if tp == QuestionApplicable.PLOT:
        chars = PlotCharacterRel.objects.filter(plot=el)
        if chars:
            tv.text += "\nCharacters\n"
            for rel in chars:
                tv.text += f"{rel.character}: {html_clean(rel.text)}\n"

    # Save the completed version to database
    tv.save()


def _get_field_value(el: Any, que: Any) -> str | None:
    """Get the field value for a given element and question.

    Args:
        el: The element object to get the value for
        que: The question object containing type and configuration

    Returns:
        The field value as a string, or None if no value found
    """
    # Get the mapping of question types to their value extraction functions
    mapping = _get_values_mapping(el)

    # Check if question type has a direct mapping function
    if que.typ in mapping:
        return mapping[que.typ]()

    # Handle text-based question types (paragraph, text, email)
    if que.typ in {"p", "t", "e"}:
        answers = WritingAnswer.objects.filter(question=que, element_id=el.id)
        if answers:
            return answers.first().text
        return ""

    # Handle selection-based question types (single, multiple choice)
    if que.typ in {"s", "m"}:
        return ", ".join(c.option.name for c in WritingChoice.objects.filter(question=que, element_id=el.id))

    return None


def _get_values_mapping(el) -> dict[str, callable]:
    """Returns a mapping of field names to their value extraction functions.

    Args:
        el: The element object to extract values from.

    Returns:
        Dictionary mapping field names to lambda functions that extract values.
    """
    # Basic text and content fields
    mapping = {
        "text": lambda: el.text,
        "teaser": lambda: el.teaser,
        "name": lambda: el.name,
        "title": lambda: el.title,
        # Related faction names joined by comma
        "faction": lambda: ", ".join([fac.name for fac in el.factions_list.all()]),
    }
    return mapping


def check_run(el, ctx, afield=None):
    """Validate that element belongs to the correct run and event.

    Args:
        el: Model instance to validate
        ctx: Context dictionary containing run and event information
        afield: Optional field name to access nested element

    Raises:
        Http404: If element doesn't belong to the expected run or event
    """
    if "run" not in ctx:
        return

    if afield:
        el = getattr(el, afield)

    if hasattr(el, "run") and el.run != ctx["run"]:
        raise Http404("not your run")

    if hasattr(el, "event"):
        is_child = ctx["event"].parent_id is not None
        event_matches = el.event_id == ctx["event"].id
        parent_matches = el.event_id == ctx["event"].parent_id

        if (not is_child and not event_matches) or (is_child and not event_matches and not parent_matches):
            raise Http404("not your event")


def check_assoc(el: object, ctx: dict, afield: str = None) -> None:
    """Check if object belongs to the correct association.

    Args:
        el: Object to check or container object
        ctx: Context dict containing association ID as 'a_id'
        afield: Optional field name to extract from el

    Raises:
        Http404: If object doesn't belong to the association
    """
    # Extract specific field if requested
    if afield:
        el = getattr(el, afield)

    # Skip check if object has no association
    if not hasattr(el, "assoc"):
        return

    # Verify object belongs to current association
    if el.assoc_id != ctx["a_id"]:
        raise Http404("not your association")


def user_edit(request: HttpRequest, ctx: dict, form_type: type, nm: str, eid: int) -> bool:
    """Generic user data editing with validation.

    Handles both GET and POST requests for editing user data. On POST, validates
    the form and saves the instance. Supports deletion functionality when
    'delete' parameter is set to '1' in POST data.

    Args:
        request: HTTP request object containing method and POST data
        ctx: Context dictionary containing model data and form instance
        form_type: Django form class to use for data validation and editing
        nm: Name key for accessing the model instance in context dictionary
        eid: Entity ID for editing, used for form numbering (0 for new instances)

    Returns:
        True if form was successfully processed and saved, False if form
        validation failed or GET request requires form display.

    Side Effects:
        - Adds success message to request on successful save
        - Logs the operation using save_log function
        - Deletes instance if delete flag is set
        - Updates ctx with 'saved', 'form', 'num', and optionally 'name' keys
    """
    if request.method == "POST":
        # Initialize form with POST data and files, bind to existing instance
        form = form_type(request.POST, request.FILES, instance=ctx[nm], ctx=ctx)

        if form.is_valid():
            # Save the form and get the updated instance
            p = form.save()
            messages.success(request, _("Operation completed") + "!")

            # Check if delete operation was requested
            dl = "delete" in request.POST and request.POST["delete"] == "1"

            # Log the operation (save or delete)
            save_log(request.user.member, form_type, p, dl)

            # Delete the instance if deletion was requested
            if dl:
                p.delete()

            # Store saved instance in context for template access
            ctx["saved"] = p

            return True
    else:
        # Initialize empty form for GET request, bind to existing instance
        form = form_type(instance=ctx[nm], ctx=ctx)

    # Add form and entity ID to context for template rendering
    ctx["form"] = form
    ctx["num"] = eid

    # Add string representation of instance name for existing entities
    if eid != 0:
        ctx["name"] = str(ctx[nm])

    return False


def backend_get(ctx: dict, typ: type, eid: int, afield: str = None) -> None:
    """Retrieve an object by ID and perform security checks.

    Args:
        ctx: Context dictionary to store the retrieved object
        typ: Model class to query
        eid: Primary key of the object to retrieve
        afield: Optional field name for additional checks

    Raises:
        NotFoundError: If object with given ID doesn't exist
    """
    # Retrieve object by primary key, handle any database exceptions
    try:
        el = typ.objects.get(pk=eid)
    except Exception as err:
        raise NotFoundError() from err

    # Store object in context and perform security validations
    ctx["el"] = el
    check_run(el, ctx, afield)
    check_assoc(el, ctx, afield)

    # Set display name for the object
    ctx["name"] = str(el)


def backend_edit(
    request: HttpRequest,
    ctx: dict[str, Any],
    form_type: type[ModelForm],
    element_id: Optional[int],
    additional_field: Optional[str] = None,
    is_association_based: bool = False,
    quiet: bool = False,
) -> bool:
    """Handle backend editing operations for various content types.

    Provides unified interface for editing different model types including
    form processing, validation, logging, and deletion handling for both
    event-based and association-based content management.

    Args:
        request: Django HTTP request object containing user and POST data
        ctx: Context dictionary for template rendering and data sharing
        form_type: Django ModelForm class for handling the specific model
        element_id: Element ID for editing existing objects, None for new objects
        additional_field: Optional additional field parameter for specialized handling
        is_association_based: Flag indicating association-based vs event-based operation
        quiet: Flag to suppress success messages when True

    Returns:
        bool: True if form was successfully processed and saved, False otherwise
    """
    # Extract model type and set up basic context variables
    model_type = form_type.Meta.model
    ctx["elementTyp"] = model_type
    ctx["request"] = request

    # Handle association-based operations vs event-based operations
    if is_association_based:
        ctx["exe"] = True
        if element_id is None:
            element_id = request.assoc["id"]
            ctx["nonum"] = True
    elif element_id is None:
        element_id = ctx["event"].id
        ctx["nonum"] = True

    # Load existing element or set as None for new objects
    if element_id != 0:
        backend_get(ctx, model_type, element_id, additional_field)
    else:
        ctx["el"] = None

    # Set up context for template rendering
    ctx["num"] = element_id
    ctx["type"] = ctx["elementTyp"].__name__.lower()

    # Process POST request - form submission and validation
    if request.method == "POST":
        ctx["form"] = form_type(request.POST, request.FILES, instance=ctx["el"], ctx=ctx)

        if ctx["form"].is_valid():
            # Save the form and show success message if not in quiet mode
            saved_object = ctx["form"].save()
            if not quiet:
                messages.success(request, _("Operation completed") + "!")

            # Handle deletion if delete flag is set in POST data
            should_delete = "delete" in request.POST and request.POST["delete"] == "1"
            save_log(request.user.member, form_type, saved_object, should_delete)
            if should_delete:
                saved_object.delete()

            # Store saved object in context and return success
            ctx["saved"] = saved_object
            return True
    else:
        # GET request - initialize form with existing instance
        ctx["form"] = form_type(instance=ctx["el"], ctx=ctx)

    # Set display name for existing objects
    if element_id != 0:
        ctx["name"] = str(ctx["el"])

    # Handle "add another" functionality for continuous adding
    ctx["add_another"] = "add_another" not in ctx or ctx["add_another"]
    if ctx["add_another"]:
        ctx["continue_add"] = "continue" in request.POST

    return False


def orga_edit(
    request: HttpRequest,
    event_slug: str,
    permission: str,
    form_type: str,
    entity_id: int,
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
    ctx = check_event_permission(request, event_slug, permission)

    # Merge any additional context provided by caller
    if additional_context:
        ctx.update(additional_context)

    # Process the edit operation using backend edit handler
    # Returns True if edit was successful and should redirect
    if backend_edit(request, ctx, form_type, entity_id, afield=None, assoc=False):
        # Set suggestion context for successful edit
        set_suggestion(ctx, permission)

        # Handle "continue editing" workflow - redirect to new object form
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, s=ctx["run"].get_slug(), num=0)

        # Determine redirect target - use provided or default to permission name
        if not redirect_view:
            redirect_view = permission

        # Redirect to success page with event slug
        return redirect(redirect_view, s=ctx["run"].get_slug())

    # Edit operation failed or is initial load - render edit form
    return render(request, "larpmanager/orga/edit.html", ctx)


def exe_edit(
    request: HttpRequest,
    form_type: str,
    entity_id: int,
    permission: str,
    redirect_target: str = None,
    additional_field: str = None,
    additional_context: dict = None,
) -> HttpResponse:
    """
    Handle editing operations for organization-level entities.

    Manages the edit workflow for various entity types at the organization level,
    including permission checking, form processing, and appropriate redirects.

    Args:
        request: HTTP request object containing form data and user information
        form_type: Type of form/entity being edited (e.g., 'member', 'event')
        entity_id: Entity ID for the object being edited
        permission: Permission string required to access this edit functionality
        redirect_target: Optional redirect target after successful edit (defaults to permission)
        additional_field: Optional additional field parameter for the backend edit
        additional_context: Optional additional context dictionary to merge with base context

    Returns:
        HttpResponse: Redirect response on successful edit, or rendered edit template
    """
    # Check user permissions and get base context
    ctx = check_assoc_permission(request, permission)

    # Merge additional context if provided
    if additional_context:
        ctx.update(additional_context)

    # Process the edit operation through backend handler
    if backend_edit(request, ctx, form_type, entity_id, afield=additional_field, assoc=True):
        # Set permission suggestion for UI feedback
        set_suggestion(ctx, permission)

        # Handle "continue editing" workflow
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, num=0)

        # Determine redirect target and perform redirect
        if not redirect_target:
            redirect_target = permission
        return redirect(redirect_target)

    # Render edit template if edit operation was not successful
    return render(request, "larpmanager/exe/edit.html", ctx)


def set_suggestion(ctx: dict, perm: str) -> None:
    """Set a suggestion flag for a given permission in the configuration.

    This function sets a boolean flag in the configuration to indicate that
    a suggestion has been made for a specific permission. It works with both
    event and association contexts.

    Args:
        ctx: Context dictionary containing either 'event' key with event object
             or 'a_id' key with association ID
        perm: Permission name to create suggestion flag for
    """
    # Determine the target object based on context
    if "event" in ctx:
        obj = ctx["event"]
    else:
        obj = Association.objects.get(pk=ctx["a_id"])

    # Build the configuration key for this permission's suggestion
    key = f"{perm}_suggestion"
    suggestion = obj.get_config(key, False)

    # Exit early if suggestion already exists
    if suggestion:
        return

    # Get the foreign key field name for the config model
    fk_field = _get_fkey_config(obj)

    # Create or retrieve the configuration entry
    (config, created) = obj.configs.model.objects.get_or_create(**{fk_field: obj, "name": key})

    # Set the suggestion flag to True and save
    config.value = True
    config.save()


def writing_edit(
    request: HttpRequest,
    ctx: dict[str, Any],
    form_type: type[forms.Form],
    element_name: str,
    element_type: str,
    redirect_url: Optional[str] = None,
) -> Optional[HttpResponse]:
    """
    Handle editing of writing elements with form processing.

    Manages the creation and editing of writing elements (characters, backgrounds, etc.)
    through a dynamic form system. Handles both GET requests for form display and
    POST requests for form submission and validation.

    Args:
        request: The HTTP request object containing method and form data
        ctx: Context dictionary containing element data and template variables
        form_type: Django form class to instantiate for editing the element
        element_name: Name key of the element in the context dictionary
        element_type: Type identifier for the writing element being edited
        redirect_url: Optional redirect URL to use after successful form save

    Returns:
        HttpResponse object for redirect after successful save, None otherwise
        to continue with template rendering

    Note:
        Function modifies the ctx dictionary in-place to add form and display data.
    """
    # Set up element type metadata for template rendering
    ctx["elementTyp"] = form_type.Meta.model

    # Configure element identification and naming
    if element_name in ctx:
        ctx["eid"] = ctx[element_name].id
        ctx["name"] = str(ctx[element_name])
    else:
        ctx[element_name] = None

    # Set type information for template display
    ctx["type"] = ctx["elementTyp"].__name__.lower()
    ctx["label_typ"] = ctx["type"]

    # Handle form submission (POST request)
    if request.method == "POST":
        form = form_type(request.POST, request.FILES, instance=ctx[element_name], ctx=ctx)

        # Process valid form data and potentially redirect
        if form.is_valid():
            return _writing_save(ctx, form, form_type, element_name, redirect_url, request, element_type)
    else:
        # Initialize form for GET request
        form = form_type(instance=ctx[element_name], ctx=ctx)

    # Configure template context for form rendering
    ctx["nm"] = element_name
    ctx["form"] = form
    ctx["add_another"] = True
    ctx["continue_add"] = "continue" in request.POST

    # Set auto-save behavior based on event configuration
    ctx["auto_save"] = not get_event_config(ctx["event"].id, "writing_disable_auto", False, ctx)
    ctx["download"] = 1

    # Set up character finder functionality for the element type
    _setup_char_finder(ctx, ctx["elementTyp"])

    return render(request, "larpmanager/orga/writing/writing.html", ctx)


def _setup_char_finder(ctx: dict, typ: type) -> None:
    """Set up character finder widget for the given context and type.

    Configures a character finder widget based on the event configuration and
    trait/character type. If character finder is disabled for the event, the
    function returns early without setting up the widget.

    Args:
        ctx: Context dictionary containing event and other template variables
        typ: Model class type (either Trait or Character) to determine widget type

    Returns:
        None: Modifies the context dictionary in place
    """
    # Check if character finder is disabled for this event
    if get_event_config(ctx["event"].id, "writing_disable_char_finder", False, ctx):
        return

    # Select appropriate widget class based on type
    if typ == Trait:
        widget_class = EventTraitS2Widget
    else:
        widget_class = EventCharacterS2Widget

    # Initialize widget with event configuration
    widget = widget_class(attrs={"id": "char_finder"})
    widget.set_event(ctx["event"])

    # Set up context variables for template rendering
    ctx["finder_typ"] = typ._meta.model_name
    ctx["char_finder"] = widget.render(name="char_finder", value="")
    ctx["char_finder_media"] = widget.media


def _writing_save(
    ctx: dict, form: Any, form_type: type, nm: str, redr: Optional[Callable], request: HttpRequest, tp: Optional[str]
) -> HttpResponse:
    """
    Save writing form data with AJAX and normal save handling.

    Handles both AJAX auto-save requests and normal form submissions. For normal saves,
    creates version history if type is provided, otherwise logs the operation. Supports
    deletion via POST parameter and various redirect behaviors.

    Args:
        ctx: Context dictionary containing element data and run information
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
        if nm in ctx:
            return writing_edit_save_ajax(form, request, ctx)
        else:
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
        save_version(p, tp, request.user.member, dl)
    else:
        save_log(request.user.member, form_type, p)

    # Execute deletion if requested after logging/versioning
    if dl:
        p.delete()

    # Display success message to user
    messages.success(request, _("Operation completed") + "!")

    # Handle continue editing request
    if "continue" in request.POST:
        return redirect(request.resolver_match.view_name, s=ctx["run"].get_slug(), num=0)

    # Handle custom redirect function if provided
    if redr:
        ctx["element"] = p
        return redr(ctx)

    # Default redirect to list view
    return redirect("orga_" + nm + "s", s=ctx["run"].get_slug())


def writing_edit_cache_key(eid, typ):
    return f"orga_edit_{eid}_{typ}"


def writing_edit_save_ajax(form: Form, request: HttpRequest, ctx: dict) -> "JsonResponse":
    """Handle AJAX save requests for writing elements with locking validation.

    This function processes AJAX requests to save writing elements while validating
    user permissions and checking for editing conflicts through a token-based
    locking mechanism.

    Args:
        form: Django form instance containing the data to save
        request: HTTP request object containing POST data and user information
        ctx: Context dictionary for additional data (currently unused)

    Returns:
        JsonResponse: JSON response containing either success status or warning message
            - On success: {"res": "ok"}
            - On warning: {"res": "ok", "warn": "warning message"}
    """
    # Initialize default success response
    res = {"res": "ok"}

    # Superusers bypass all validation checks
    if request.user.is_superuser:
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


def writing_edit_working_ticket(request, tp: str, eid: int, token: str) -> str:
    """
    Manage working tickets to prevent concurrent editing conflicts.

    This function implements a locking mechanism to prevent multiple users from
    editing the same content simultaneously, which could result in data loss.
    For plot objects, it recursively checks all related characters.

    Args:
        request: HTTP request object containing user information
        tp: Type of element being edited (e.g., 'plot', 'character')
        eid: Element ID being edited
        token: User's unique editing token for session identification

    Returns:
        Warning message if editing conflicts exist, empty string if safe to edit

    Note:
        Uses Redis cache with a 15-second timeout window to track active editors.
        Cache timeout is set to minimum of ticket_time and 1 day.
    """
    # Superusers bypass all validation checks
    if request.user.is_superuser:
        return ""

    # Handle plot objects by recursively checking all related characters
    # This prevents conflicts when editing plots that affect multiple characters
    if tp == "plot":
        char_ids = Plot.objects.filter(pk=eid).values_list("characters__pk", flat=True)
        for char_id in char_ids:
            if char_id is None:  # Skip if plot has no characters
                continue
            msg = writing_edit_working_ticket(request, "character", char_id, token)
            if msg:
                return msg

    # Get current timestamp and retrieve existing ticket from cache
    now = int(time.time())
    key = writing_edit_cache_key(eid, tp)
    ticket = cache.get(key)
    if not ticket:
        ticket = {}

    # Check for other active editors within the timeout window
    others = []
    ticket_time = 5  # 5 second timeout for editing conflicts
    for idx, el in ticket.items():
        (name, tm) = el
        # Only consider other users' tokens within the timeout period
        if idx != token and now - tm < ticket_time:
            others.append(name)

    # Generate warning message if other users are currently editing
    msg = ""
    if len(others) > 0:
        msg = _("Warning! Other users are editing this item") + "."
        msg += " " + _("You cannot work on it at the same time: the work of one of you would be lost") + "."
        msg += " " + _("List of other users") + ": " + ", ".join(others)

    # Update ticket with current user's information and timestamp
    ticket[token] = (str(request.user.member), now)
    # Cache the updated ticket with appropriate timeout
    cache.set(key, ticket, min(ticket_time, conf_settings.CACHE_TIMEOUT_1_DAY))

    return msg


@require_POST
def working_ticket(request):
    """Handle working ticket requests to prevent concurrent editing conflicts.

    Args:
        request: HTTP POST request with eid, type, and token parameters

    Returns:
        JsonResponse: Status response with optional warning if other users are editing
    """
    if not request.user.is_authenticated:
        return JsonResponse({"warn": "User not logged"})

    res = {"res": "ok"}
    if request.user.is_superuser:
        return JsonResponse(res)

    eid = request.POST.get("eid")
    type = request.POST.get("type")
    token = request.POST.get("token")

    msg = writing_edit_working_ticket(request, type, eid, token)
    if msg:
        res["warn"] = msg

    return JsonResponse(res)
