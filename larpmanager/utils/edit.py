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
from django.forms import ModelForm, forms
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.cache.config import _get_fkey_config
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


def _get_field_value(el, que) -> str | None:
    """Get the field value for a given element and question.

    Args:
        el: The element object to get the value for
        que: The question object containing type and configuration

    Returns:
        The field value as a string, or None if no value found

    Raises:
        None
    """
    # Get the mapping of question types to value extraction functions
    mapping = _get_values_mapping(el)

    # Use direct mapping if question type is available
    if que.typ in mapping:
        return mapping[que.typ]()

    # Handle text-based question types (paragraph, text, email)
    if que.typ in {"p", "t", "e"}:
        answers = WritingAnswer.objects.filter(question=que, element_id=el.id)
        if answers:
            return answers.first().text
        return ""

    # Handle choice-based question types (single, multiple)
    if que.typ in {"s", "m"}:
        return ", ".join(c.option.name for c in WritingChoice.objects.filter(question=que, element_id=el.id))

    # Return None for unhandled question types
    return None


def _get_values_mapping(el):
    mapping = {
        "text": lambda: el.text,
        "teaser": lambda: el.teaser,
        "name": lambda: el.name,
        "title": lambda: el.title,
        "faction": lambda: ", ".join([fac.name for fac in el.factions_list.all()]),
    }
    return mapping


def check_run(el: object, ctx: dict, afield: str = None) -> None:
    """Validate that element belongs to the correct run and event.

    This function ensures that a model instance belongs to the expected run and event
    based on the provided context. It handles both regular events and child events
    (events with a parent).

    Args:
        el: Model instance to validate against run and event context
        ctx: Context dictionary containing 'run' and 'event' keys with their
             respective model instances
        afield: Optional field name to access a nested element attribute from el

    Raises:
        Http404: If element doesn't belong to the expected run or event

    Returns:
        None
    """
    # Early return if no run context is provided
    if "run" not in ctx:
        return

    # Access nested element if field name is specified
    if afield:
        el = getattr(el, afield)

    # Validate run ownership if element has run attribute
    if hasattr(el, "run") and el.run != ctx["run"]:
        raise Http404("not your run")

    # Validate event ownership with support for parent-child event relationships
    if hasattr(el, "event"):
        # Determine if current event is a child event
        is_child = ctx["event"].parent_id is not None

        # Check direct event match and parent event match
        event_matches = el.event_id == ctx["event"].id
        parent_matches = el.event_id == ctx["event"].parent_id

        # Validate event ownership based on parent-child relationship
        if (not is_child and not event_matches) or (is_child and not event_matches and not parent_matches):
            raise Http404("not your event")


def check_assoc(el, ctx, afield=None):
    if afield:
        el = getattr(el, afield)

    if not hasattr(el, "assoc"):
        return

    if el.assoc.id != ctx["a_id"]:
        raise Http404("not your association")


def user_edit(request: HttpRequest, ctx: dict, form_type: type, nm: str, eid: int) -> bool:
    """Generic user data editing with validation.

    Handles both GET requests (displays form) and POST requests (processes form submission).
    Supports creation, editing, and deletion of model instances through a unified interface.

    Args:
        request: The HTTP request object containing method and data
        ctx: Context dictionary containing model data and additional context
        form_type: Django form class to instantiate for editing
        nm: String key to access the model instance in the context dictionary
        eid: Integer entity ID, used for editing existing instances (0 for new)

    Returns:
        True if form was successfully processed and saved, False if form needs to be displayed

    Note:
        - On successful save, adds 'saved' key to ctx with the saved instance
        - Supports soft deletion via 'delete' POST parameter
        - Logs all operations for audit trail
    """
    if request.method == "POST":
        # Initialize form with POST data and existing instance
        form = form_type(request.POST, request.FILES, instance=ctx[nm], ctx=ctx)

        if form.is_valid():
            # Save the form and get the model instance
            p = form.save()
            messages.success(request, _("Operation completed") + "!")

            # Check if deletion was requested via POST parameter
            dl = "delete" in request.POST and request.POST["delete"] == "1"

            # Log the operation before potential deletion
            save_log(request.user.member, form_type, p, dl)

            # Perform deletion if requested
            if dl:
                p.delete()

            # Store saved instance in context for further processing
            ctx["saved"] = p

            return True
    else:
        # GET request: initialize form with existing instance
        form = form_type(instance=ctx[nm], ctx=ctx)

    # Add form and metadata to context for template rendering
    ctx["form"] = form
    ctx["num"] = eid

    # Set display name for existing entities
    if eid != 0:
        ctx["name"] = str(ctx[nm])

    return False


def backend_get(ctx, typ, eid, afield=None):
    try:
        el = typ.objects.get(pk=eid)
    except Exception as err:
        raise NotFoundError() from err
    ctx["el"] = el
    check_run(el, ctx, afield)
    check_assoc(el, ctx, afield)
    ctx["name"] = str(el)


def backend_edit(
    request: HttpRequest,
    ctx: dict[str, Any],
    form_type: type[ModelForm],
    eid: Optional[int],
    afield: Optional[str] = None,
    assoc: bool = False,
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
        eid: Element ID for editing existing objects, None for new objects
        afield: Optional additional field parameter for specialized handling
        assoc: Flag indicating association-based vs event-based operation
        quiet: Flag to suppress success messages when True

    Returns:
        bool: True if form was successfully processed and saved, False otherwise
    """
    # Extract model type and set up basic context variables
    typ = form_type.Meta.model
    ctx["elementTyp"] = typ
    ctx["request"] = request

    # Handle association-based operations vs event-based operations
    if assoc:
        ctx["exe"] = True
        if eid is None:
            eid = request.assoc["id"]
            ctx["nonum"] = True
    elif eid is None:
        eid = ctx["event"].id
        ctx["nonum"] = True

    # Load existing element or set as None for new objects
    if eid != 0:
        backend_get(ctx, typ, eid, afield)
    else:
        ctx["el"] = None

    # Set up context for template rendering
    ctx["num"] = eid
    ctx["type"] = ctx["elementTyp"].__name__.lower()

    # Process POST request - form submission and validation
    if request.method == "POST":
        ctx["form"] = form_type(request.POST, request.FILES, instance=ctx["el"], ctx=ctx)

        if ctx["form"].is_valid():
            # Save the form and show success message if not in quiet mode
            p = ctx["form"].save()
            if not quiet:
                messages.success(request, _("Operation completed") + "!")

            # Handle deletion if delete flag is set in POST data
            dl = "delete" in request.POST and request.POST["delete"] == "1"
            save_log(request.user.member, form_type, p, dl)
            if dl:
                p.delete()

            # Store saved object in context and return success
            ctx["saved"] = p
            return True
    else:
        # GET request - initialize form with existing instance
        ctx["form"] = form_type(instance=ctx["el"], ctx=ctx)

    # Set display name for existing objects
    if eid != 0:
        ctx["name"] = str(ctx["el"])

    # Handle "add another" functionality for continuous adding
    ctx["add_another"] = "add_another" not in ctx or ctx["add_another"]
    if ctx["add_another"]:
        ctx["continue_add"] = "continue" in request.POST

    return False


def orga_edit(
    request: HttpRequest,
    s: str,
    perm: str,
    form_type: str,
    eid: int,
    red: Optional[str] = None,
    add_ctx: Optional[dict[str, Any]] = None,
) -> HttpResponse:
    """Edit organization event objects through a unified interface.

    Args:
        request: The HTTP request object
        s: The event slug identifier
        perm: Permission name for access control
        form_type: Type of form to render for editing
        eid: Entity ID to edit
        red: Optional redirect target after successful edit
        add_ctx: Optional additional context to merge

    Returns:
        HttpResponse: Rendered edit form or redirect response
    """
    # Check user permissions and get base context
    ctx = check_event_permission(request, s, perm)

    # Merge any additional context provided
    if add_ctx:
        ctx.update(add_ctx)

    # Process the edit operation using backend handler
    if backend_edit(request, ctx, form_type, eid, afield=None, assoc=False):
        # Set suggestion context for successful edit
        set_suggestion(ctx, perm)

        # Handle continue editing workflow
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, s=ctx["run"].get_slug(), num=0)

        # Determine redirect target and redirect to list view
        if not red:
            red = perm
        return redirect(red, s=ctx["run"].get_slug())

    # Render edit form template for GET requests or failed edits
    return render(request, "larpmanager/orga/edit.html", ctx)


def exe_edit(
    request: HttpRequest,
    form_type: str,
    eid: int,
    perm: str,
    red: Optional[str] = None,
    afield: Optional[str] = None,
    add_ctx: Optional[dict[str, Any]] = None,
) -> HttpResponse:
    """Edit an organization-level entity through a form.

    Args:
        request: The HTTP request object
        form_type: Type of form to use for editing
        eid: Entity ID to edit
        perm: Permission required to access this view
        red: Redirect target after successful edit (defaults to perm)
        afield: Additional field parameter for backend_edit
        add_ctx: Additional context to merge into template context

    Returns:
        HttpResponse: Either a redirect on success or rendered edit template
    """
    # Check user has required association permission and get base context
    ctx = check_assoc_permission(request, perm)

    # Merge any additional context provided by caller
    if add_ctx:
        ctx.update(add_ctx)

    # Process the edit form submission through backend
    if backend_edit(request, ctx, form_type, eid, afield=afield, assoc=True):
        # Set suggestion context for successful edit
        set_suggestion(ctx, perm)

        # Handle "Save and continue editing" button
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, num=0)

        # Determine redirect target (use provided or default to permission name)
        if not red:
            red = perm
        return redirect(red)

    # Render edit form template with context
    return render(request, "larpmanager/exe/edit.html", ctx)


def set_suggestion(ctx: dict, perm: str) -> None:
    """Set a suggestion flag for a specific permission in the given context.

    Args:
        ctx: Context dictionary containing either 'event' or 'a_id' key
        perm: Permission name to create suggestion for

    Returns:
        None
    """
    # Determine the target object from context - either event or association
    if "event" in ctx:
        obj = ctx["event"]
    else:
        obj = Association.objects.get(pk=ctx["a_id"])

    # Check if suggestion already exists for this permission
    key = f"{perm}_suggestion"
    suggestion = obj.get_config(key, False)
    if suggestion:
        return

    # Create new suggestion config entry
    fk_field = _get_fkey_config(obj)
    (config, created) = obj.configs.model.objects.get_or_create(**{fk_field: obj, "name": key})

    # Set suggestion flag to True and save
    config.value = True
    config.save()


def writing_edit(
    request: HttpRequest, ctx: dict[str, Any], form_type: type[forms.Form], nm: str, tp: str, redr: Optional[str] = None
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
        nm: Name key of the element in the context dictionary
        tp: Type identifier for the writing element being edited
        redr: Optional redirect URL to use after successful form save

    Returns:
        HttpResponse object for redirect after successful save, None otherwise
        to continue with template rendering

    Note:
        Function modifies the ctx dictionary in-place to add form and display data.
    """
    # Set up element type metadata for template rendering
    ctx["elementTyp"] = form_type.Meta.model

    # Configure element identification and naming
    if nm in ctx:
        ctx["eid"] = ctx[nm].id
        ctx["name"] = str(ctx[nm])
    else:
        ctx[nm] = None

    # Set type information for template display
    ctx["type"] = ctx["elementTyp"].__name__.lower()
    ctx["label_typ"] = ctx["type"]

    # Handle form submission (POST request)
    if request.method == "POST":
        form = form_type(request.POST, request.FILES, instance=ctx[nm], ctx=ctx)

        # Process valid form data and potentially redirect
        if form.is_valid():
            return _writing_save(ctx, form, form_type, nm, redr, request, tp)
    else:
        # Initialize form for GET request
        form = form_type(instance=ctx[nm], ctx=ctx)

    # Configure template context for form rendering
    ctx["nm"] = nm
    ctx["form"] = form
    ctx["add_another"] = True
    ctx["continue_add"] = "continue" in request.POST

    # Set auto-save behavior based on event configuration
    ctx["auto_save"] = not ctx["event"].get_config("writing_disable_auto", False)
    ctx["download"] = 1

    # Set up character finder functionality for the element type
    _setup_char_finder(ctx, ctx["elementTyp"])

    return render(request, "larpmanager/orga/writing/writing.html", ctx)


def _setup_char_finder(ctx: dict, typ: type) -> None:
    """Set up character finder widget for event forms.

    Args:
        ctx: Template context dictionary to populate with finder data
        typ: Model type (Trait or Character) to determine widget class

    Returns:
        None: Modifies ctx dictionary in place
    """
    # Check if character finder is disabled for this event
    if ctx["event"].get_config("writing_disable_char_finder", False):
        return

    # Select appropriate widget class based on model type
    if typ == Trait:
        widget_class = EventTraitS2Widget
    else:
        widget_class = EventCharacterS2Widget

    # Initialize widget with event context
    widget = widget_class(attrs={"id": "char_finder"})
    widget.set_event(ctx["event"])

    # Populate context with finder configuration
    ctx["finder_typ"] = typ._meta.model_name

    # Render widget and add to context
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


def writing_edit_save_ajax(form, request, ctx) -> JsonResponse:
    """Handle AJAX save requests for writing elements with locking validation.

    Processes form submissions for writing elements via AJAX, implementing
    user permission checks and element locking to prevent concurrent edits.
    Superusers bypass all validation checks.

    Args:
        form: Django form instance to save containing writing element data
        request: HTTP request object containing POST data and user info
        ctx: Context dictionary (currently unused but maintained for compatibility)

    Returns:
        JsonResponse: JSON response containing success status and optional warnings
            - {"res": "ok"} on success
            - {"res": "ok", "warn": "message"} on success with warnings
    """
    # Initialize successful response structure
    res = {"res": "ok"}

    # Superusers bypass all validation and locking mechanisms
    if request.user.is_superuser:
        return JsonResponse(res)

    # Extract and validate element ID from POST data
    eid = int(request.POST["eid"])
    if eid <= 0:
        return res

    # Extract element type and edit token for lock validation
    tp = request.POST["type"]
    token = request.POST["token"]

    # Check if element is locked by another user or session
    msg = writing_edit_working_ticket(request, tp, eid, token)
    if msg:
        res["warn"] = msg
        return JsonResponse(res)

    # Save form data as temporary version to preserve work
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
    ticket_time = 15  # 15-second timeout for editing conflicts
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
def working_ticket(request: HttpRequest) -> JsonResponse:
    """Handle working ticket requests to prevent concurrent editing conflicts.

    This function manages working tickets to prevent multiple users from editing
    the same content simultaneously. Superusers bypass all checks.

    Args:
        request: HTTP POST request containing editing session parameters
            - eid: Entity ID being edited
            - type: Type of entity being edited
            - token: Session token for the editing session

    Returns:
        JsonResponse: Response containing status and optional warning
            - res: "ok" if successful
            - warn: Warning message if conflicts detected or user not authenticated

    Note:
        Superusers are exempt from working ticket validation and always
        receive successful responses without conflict checking.
    """
    # Check user authentication status
    if not request.user.is_authenticated:
        return JsonResponse({"warn": "User not logged"})

    # Initialize default success response
    res = {"res": "ok"}

    # Superusers bypass all working ticket checks
    if request.user.is_superuser:
        return JsonResponse(res)

    # Extract POST parameters for working ticket validation
    eid = request.POST.get("eid")
    type = request.POST.get("type")
    token = request.POST.get("token")

    # Check for editing conflicts and get warning message if any
    msg = writing_edit_working_ticket(request, type, eid, token)
    if msg:
        res["warn"] = msg

    return JsonResponse(res)
