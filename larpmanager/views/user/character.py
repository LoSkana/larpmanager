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

import ast
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from PIL import Image, UnidentifiedImageError

from larpmanager.cache.character import get_character_element_fields, get_event_cache_all
from larpmanager.cache.config import get_event_config, save_single_config
from larpmanager.cache.event_text import get_event_text
from larpmanager.forms.character import CharacterForm
from larpmanager.forms.member import AvatarForm
from larpmanager.forms.registration import RegistrationCharacterRelForm
from larpmanager.forms.writing import PlayerRelationshipForm
from larpmanager.models.event import EventTextType
from larpmanager.models.form import (
    QuestionApplicable,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.miscellanea import PlayerRelationship
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import (
    Character,
    CharacterStatus,
)
from larpmanager.templatetags.show_tags import get_tooltip
from larpmanager.utils.core.base import get_event_context
from larpmanager.utils.core.common import get_player_relationship
from larpmanager.utils.services.character import (
    check_missing_mandatory,
    get_char_check,
    get_character_relationships,
    get_character_sheet,
)
from larpmanager.utils.services.edit import user_edit
from larpmanager.utils.services.experience import get_available_ability_px, get_current_ability_px, remove_char_ability
from larpmanager.utils.services.writing import char_add_addit
from larpmanager.utils.users.registration import (
    check_assign_character,
    check_character_maximum,
    get_player_characters,
    registration_find,
)
from larpmanager.views.user.casting import casting_details, get_casting_preferences
from larpmanager.views.user.registration import init_form_submitted

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from larpmanager.forms.base import MyForm


def character_view(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Return character sheet for specified character in event run.

    Args:
        request: HTTP request object
        event_slug: Event run slug identifier
        num: Character number/ID

    Returns:
        Rendered character sheet response

    """
    # Get event run context and verify status
    context = get_event_context(request, event_slug, include_status=True)

    # Validate character access permissions
    get_char_check(request, context, num)

    return _character_sheet(request, context)


def _character_sheet(request: HttpRequest, context: dict) -> HttpResponse:
    """Display character sheet with visibility and approval checks.

    This function handles the display of character sheets with proper visibility
    checks, approval validation, and contextual data preparation based on user
    permissions and character settings.

    Args:
        request: Django HTTP request object containing user session and metadata
        context: Context dictionary containing event, run, character data and permissions

    Returns:
        HttpResponse: Rendered character sheet template or redirect to gallery

    Raises:
        Redirect: When character visibility rules are violated or access is denied

    """
    # Enable screen mode for character sheet display
    context["screen"] = True

    # Check if characters are visible to regular users (non-staff)
    if "check" not in context and not context["show_character"]:
        messages.warning(request, _("Characters are not visible at the moment"))
        return redirect("gallery", event_slug=context["run"].get_slug())

    # Verify individual character visibility settings
    if "check" not in context and context["char"]["hide"]:
        messages.warning(request, _("Character not visible"))
        return redirect("gallery", event_slug=context["run"].get_slug())

    # Determine access level and load appropriate character data
    is_staff_view = "check" in context
    if is_staff_view:
        # Load full character data for staff/admin users
        get_character_sheet(context)
        get_character_relationships(context)
        context["intro"] = get_event_text(context["event"].id, EventTextType.INTRO)
        check_missing_mandatory(context)
    else:
        # Load only visible elements for regular users
        context["char"].update(get_character_element_fields(context, context["char"]["id"], only_visible=True))

    # Load casting details and preferences if applicable
    casting_details(context, 0)
    if context["casting_show_pref"] and not context["char"]["player_id"]:
        context["pref"] = get_casting_preferences(context["char"]["id"], context, 0)

    # Set character approval configuration for template rendering
    context["approval"] = get_event_config(
        context["event"].id, "user_character_approval", default_value=False, context=context
    )

    try:
        char_model = Character.objects.prefetch_related("character_inventory").get(id=context["char"]["id"])
        context["char"]["character_inventory"] = char_model.character_inventory.all()
    except Character.DoesNotExist:
        context["char"]["character_inventory"] = []

    return render(request, "larpmanager/event/character.html", context)


def character_external(request: HttpRequest, event_slug: str, code: str) -> HttpResponse:
    """Display character sheet via external access token.

    This function provides external access to character sheets when enabled for an event.
    It validates the access token and returns the character sheet view.

    Args:
        request: Django HTTP request object containing user session and metadata
        event_slug: Event slug identifier used to locate the specific event
        code: External access token for character authentication

    Returns:
        HttpResponse: Character sheet view rendered for the authenticated character

    Raises:
        Http404: If external access is disabled for the event or if the provided
                access token is invalid or doesn't match any character

    """
    # Get event and run context from the provided slug
    context = get_event_context(request, event_slug)

    # Check if external access feature is enabled for this event
    if not get_event_config(context["event"].id, "writing_external_access", default_value=False, context=context):
        msg = "external access not active"
        raise Http404(msg)

    # Attempt to retrieve character using the provided access token
    try:
        char = context["event"].get_elements(Character).get(access_token=code)
    except ObjectDoesNotExist as err:
        msg = "invalid code"
        raise Http404(msg) from err

    # Load all cached event data including characters
    get_event_cache_all(context)

    # Verify character exists in the cached character list
    if char.number not in context["chars"]:
        messages.warning(request, _("Character not found"))
        return redirect("/")

    # Populate context with character data for template rendering
    context["char"] = context["chars"][char.number]
    context["character"] = char
    context["check"] = 1

    return _character_sheet(request, context)


def character_your_link(context: dict, character: Any, path: str | None = None) -> str:
    """Generate a URL link for a character page.

    Args:
        context: Context dictionary containing run information
        character: Character object with number attribute
        path: Optional path parameter to append to URL

    Returns:
        Complete URL string for the character page

    """
    # Build base URL using character number and run slug
    url = reverse(
        "character",
        kwargs={
            "event_slug": context["run"].get_slug(),
            "num": character.number,
        },
    )

    # Append optional path parameter if provided
    if path:
        url += path
    return url


@login_required
def character_your(request: HttpRequest, event_slug: str, path: str | None = None) -> HttpResponse:
    """Display user's character information.

    Shows the character information page for the authenticated user. If the user has
    only one character, redirects directly to that character's page. If multiple
    characters exist, displays a selection list.

    Args:
        request: HTTP request object containing user authentication and session data
        event_slug: Event slug identifier for the specific event
        path: Optional character parameter for additional filtering or display options

    Returns:
        HttpResponse: Rendered character template, character selection list, or
                     redirect response if no characters are found

    Raises:
        Redirect: To home page if user has no assigned characters for the event

    """
    # Get event and run context with signup and status validation
    context = get_event_context(request, event_slug, signup=True, include_status=True)

    # Retrieve all registration character relationships for this run
    # Use select_related to optimize database queries for character data
    rcrs = list(context["run"].reg.rcrs.select_related("character").all())

    # Handle case where user has no characters assigned to this event
    if not rcrs:
        messages.error(request, _("You don't have a character assigned for this event") + "!")
        return redirect("home")

    # If user has exactly one character, redirect directly to character page
    if len(rcrs) == 1:
        char = rcrs[0].character
        url = character_your_link(context, char, path)
        return HttpResponseRedirect(url)

    # Build character selection list for multiple characters
    # Create URLs and display names for each character option
    context["urls"] = []
    for el in rcrs:
        url = character_your_link(context, el.character, path)
        # Use custom name if available, otherwise use character's default name
        char = el.character.name
        if el.custom_name:
            char = el.custom_name
        context["urls"].append((char, url))

    # Render character selection template with context data
    return render(request, "larpmanager/event/character/your.html", context)


def character_form(
    request: HttpRequest,
    context: dict[str, Any],
    event_slug: str,
    instance: Character | RegistrationCharacterRel | None,
    form_class: type[MyForm],
) -> HttpResponse:
    """Handle character creation and editing form processing.

    Manages character form submission, validation, saving, and assignment
    with transaction safety and proper message handling.

    Args:
        request: The HTTP request object containing form data
        context: Template context dictionary with event and user data
        event_slug: Event slug identifier
        instance: Existing character or registration relation to edit, None for new
        form_class: Django form class to use for character processing

    Returns:
        HttpResponse: Rendered form page or redirect to character detail

    Note:
        Uses atomic transactions to ensure data consistency during save operations.
        Handles both character creation and editing workflows.

    """
    # Initialize form dependencies and set element type for template context
    get_options_dependencies(context)
    context["elementTyp"] = Character

    if request.method == "POST":
        # Process form submission with uploaded files
        form = form_class(request.POST, request.FILES, instance=instance, context=context)
        if form.is_valid():
            # Set appropriate success message based on operation type
            success_message = _("Informations saved") + "!" if instance else _("New character created") + "!"

            # Save character data within atomic transaction
            with transaction.atomic():
                character = form.save(commit=False)
                # Update character with additional processing and context
                success_message = _update_character(context, character, form, success_message)
                character.save()

                # Handle character assignment logic
                check_assign_character(context)

            # Display success message to user
            if success_message:
                messages.success(request, success_message)

            # Determine character number for redirect
            character_number = None
            if isinstance(character, Character):
                character_number = character.number
            elif isinstance(character, RegistrationCharacterRel):
                character_number = character.character.number
            # Redirect to character detail page
            return redirect("character", event_slug=event_slug, num=character_number)
    else:
        # Initialize empty form for GET requests
        form = form_class(instance=instance, context=context)

    # Add form to template context and initialize form state
    context["form"] = form
    init_form_submitted(context, form, request)

    # Configure form display options from event settings
    context["hide_unavailable"] = get_event_config(
        context["event"].id,
        "character_form_hide_unavailable",
        default_value=False,
        context=context,
    )

    return render(request, "larpmanager/event/character/edit.html", context)


def _update_character(context: dict, character: Any, form: MyForm, message: str) -> str:
    """Update character status based on form data and event configuration.

    Args:
        context: Context dictionary containing event information
        character: Character instance to update
        form: Form instance with cleaned data
        message: Initial message string

    Returns:
        Updated message string or original message if no changes

    """
    # Early return if character is not a Character instance
    if not isinstance(character, Character):
        return message

    # Assign player if not already set
    if not character.player:
        character.player = context["member"]

    # Check if character approval is enabled for this event
    # Update status to proposed if character is in creation/review and user clicked propose
    if (
        get_event_config(context["event"].id, "user_character_approval", default_value=False, context=context)
        and character.status in [CharacterStatus.CREATION, CharacterStatus.REVIEW]
        and form.cleaned_data["propose"]
    ):
        character.status = CharacterStatus.PROPOSED
        message = _(
            "The character has been proposed to the staff, who will examine it and approve it "
            "or request changes if necessary.",
        )

    return message


@login_required
def character_customize(request: HttpRequest, event_slug: str, num: Any) -> Any:
    """Handle character customization form with profile and custom fields.

    Args:
        request: HTTP request object
        event_slug: Event slug
        num: Character number

    Returns:
        HttpResponse: Character customization form

    Raises:
        Http404: If character doesn't belong to user

    """
    context = get_event_context(request, event_slug, signup=True, include_status=True)

    get_char_check(request, context, num, restrict_non_owners=True)

    try:
        rgr = RegistrationCharacterRel.objects.select_related("character", "reg", "reg__member").get(
            reg=context["run"].reg,
            character__number=num,
        )
        if rgr.custom_profile:
            context["custom_profile"] = rgr.profile_thumb.url

        if get_event_config(context["event"].id, "custom_character_profile", default_value=False, context=context):
            context["avatar_form"] = AvatarForm()

        return character_form(request, context, event_slug, rgr, RegistrationCharacterRelForm)
    except ObjectDoesNotExist as err:
        msg = "not your char!"
        raise Http404(msg) from err


@login_required
def character_profile_upload(request: HttpRequest, event_slug: str, num: int) -> JsonResponse:
    """Handle character profile image upload via AJAX.

    Processes an uploaded character profile image for a specific character in an event,
    validates the upload, and saves it to storage with a unique filename.

    Args:
        request: HTTP request object containing the uploaded file in POST data
        event_slug: Event slug identifier for the target event
        num: Character number within the event registration

    Returns:
        JsonResponse containing:
            - "res": "ok" on success, "ko" on failure
            - "src": thumbnail URL of uploaded image (on success only)

    Raises:
        ObjectDoesNotExist: When character registration relationship is not found

    """
    # Validate request method is POST
    if request.method != "POST":
        return JsonResponse({"res": "ko"})

    # Validate uploaded file using form
    form = AvatarForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"res": "ko"})

    # Get event context and validate user permissions
    context = get_event_context(request, event_slug, signup=True)
    registration_find(context["run"], context["member"], None)
    get_char_check(request, context, num, restrict_non_owners=True)

    # Retrieve character registration relationship
    try:
        rgr = RegistrationCharacterRel.objects.select_related("character", "reg", "reg__member").get(
            reg=context["run"].reg,
            character__number=num,
        )
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko"})

    # Process uploaded image and generate unique filename
    img = form.cleaned_data["image"]
    ext = img.name.split(".")[-1]

    # Create unique file path with registration ID and UUID
    n_path = f"registration/{rgr.pk}_{uuid4().hex}.{ext}"
    path = default_storage.save(n_path, ContentFile(img.read()))

    # Save profile path to database atomically
    with transaction.atomic():
        rgr.custom_profile = path
        rgr.save()

    return JsonResponse({"res": "ok", "src": rgr.profile_thumb.url})


@login_required
def character_profile_rotate(request: HttpRequest, event_slug: str, num: int, rotation_angle: int) -> JsonResponse:
    """Rotate character profile image by specified degrees.

    Args:
        request (HttpRequest): HTTP request object containing user session
        event_slug (str): Event slug identifier
        num (int): Character number identifier
        rotation_angle (int): Rotation direction (1 for 90°, else -90°)

    Returns:
        JsonResponse: Dictionary with 'res' status ('ok'/'ko') and 'src' URL if successful

    Raises:
        ObjectDoesNotExist: When character registration relationship not found

    """
    # Get event context and validate character access permissions
    context = get_event_context(request, event_slug, signup=True, include_status=True)
    get_char_check(request, context, num, restrict_non_owners=True)

    # Retrieve character registration relationship with related objects
    try:
        rgr = RegistrationCharacterRel.objects.select_related("character", "reg", "reg__member").get(
            reg=context["run"].reg,
            character__number=num,
        )
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko"})

    # Validate that character has a custom profile image
    path = str(rgr.custom_profile)
    if not path:
        return JsonResponse({"res": "ko"})

    # Open and rotate the image based on direction parameter
    path = str(Path(conf_settings.MEDIA_ROOT) / path)
    try:
        im = Image.open(path)
        out = im.rotate(90) if rotation_angle == 1 else im.rotate(-90)

        # Generate unique filename and save rotated image
        ext = path.split(".")[-1]
        n_path = f"{Path(path).parent}/{rgr.pk}_{uuid4().hex}.{ext}"
        out.save(n_path)

        # Update database with new image path atomically
        with transaction.atomic():
            rgr.custom_profile = n_path
            rgr.save()

        return JsonResponse({"res": "ok", "src": rgr.profile_thumb.url})
    except (OSError, UnidentifiedImageError):
        logger.exception("Failed to rotate character profile image")
        return JsonResponse({"res": "ko"})


@login_required
def character_list(request: HttpRequest, event_slug: str) -> Any:
    """Display list of player's characters for an event with customization fields.

    Args:
        request: HTTP request object
        event_slug: Event slug

    Returns:
        HttpResponse: Rendered character list template

    """
    context = get_event_context(request, event_slug, include_status=True, signup=True, feature_slug="user_character")

    context["list"] = get_player_characters(context["member"], context["event"])
    # add character configs
    char_add_addit(context)
    for el in context["list"]:
        res = get_character_element_fields(context, el.id, only_visible=True)
        el.fields = res["fields"]
        context.update(res)

    check, _max_chars = check_character_maximum(context["event"], context["member"])
    context["char_maximum"] = check
    context["approval"] = get_event_config(
        context["event"].id, "user_character_approval", default_value=False, context=context
    )
    context["assigned"] = RegistrationCharacterRel.objects.filter(reg_id=context["run"].reg.id).count()
    return render(request, "larpmanager/event/character/list.html", context)


@login_required
def character_create(request: HttpRequest, event_slug: str) -> Any:
    """Handle character creation with maximum character validation.

    Args:
        request: HTTP request object
        event_slug: Event slug

    Returns:
        HttpResponse: Character creation form or redirect

    """
    context = get_event_context(request, event_slug, include_status=True, signup=True, feature_slug="user_character")

    check, _max_chars = check_character_maximum(context["event"], context["member"])
    if check:
        messages.success(request, _("You have reached the maximum number of characters that can be created"))
        return redirect("character_list", event_slug=event_slug)

    context["class_name"] = "character"
    return character_form(request, context, event_slug, None, CharacterForm)


@login_required
def character_edit(request: HttpRequest, event_slug: str, num: Any) -> Any:
    """Handle character editing form for specific character.

    Args:
        request: HTTP request object
        event_slug: Event slug
        num: Character number

    Returns:
        HttpResponse: Character editing form

    """
    context = get_event_context(request, event_slug, include_status=True, signup=True)
    get_char_check(request, context, num, restrict_non_owners=True)
    return character_form(request, context, event_slug, context["character"], CharacterForm)


def get_options_dependencies(context: dict) -> None:
    """Populate context with writing option dependencies for character creation.

    Analyzes writing questions and options for the current event to build a
    dependency mapping that determines which options require other options
    to be selected first during character creation.

    Args:
        context: Context dictionary containing event, features, and other data.
             Will be modified to include 'dependencies' key with option mappings.

    """
    # Initialize empty dependencies dictionary in context
    context["dependencies"] = {}

    # Early return if character feature is not enabled for this event
    if "character" not in context["features"]:
        return

    # Get all character-applicable writing questions ordered by their sequence
    character_questions = context["event"].get_elements(WritingQuestion).order_by("order")
    character_questions = character_questions.filter(applicable=QuestionApplicable.CHARACTER)
    question_ids = character_questions.values_list("id", flat=True)

    # Find all writing options belonging to character questions
    writing_options = context["event"].get_elements(WritingOption).filter(question_id__in=question_ids)

    # Build dependency mapping for options that have requirements
    for option in writing_options.filter(requirements__isnull=False).distinct():
        context["dependencies"][option.id] = list(option.requirements.values_list("id", flat=True))


@login_required
def character_assign(request: HttpRequest, event_slug: str, num: Any) -> Any:
    """Assign character to user's registration if not already assigned.

    Args:
        request: HTTP request object
        event_slug: Event slug
        num: Character number

    Returns:
        HttpResponse: Redirect to character list

    """
    context = get_event_context(request, event_slug, signup=True, include_status=True)
    get_char_check(request, context, num, restrict_non_owners=True)
    if RegistrationCharacterRel.objects.filter(reg_id=context["run"].reg.id).exists():
        messages.warning(request, _("You already have an assigned character"))
    elif not context["character"].is_active:
        messages.error(request, _("This character is inactive and cannot be assigned to players"))
    else:
        RegistrationCharacterRel.objects.create(reg_id=context["run"].reg.id, character_id=context["character"].id)
        messages.success(request, _("Assigned character!"))

    return redirect("character_list", event_slug=event_slug)


@login_required
def character_abilities(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Display character abilities with available and current abilities organized by type.

    This view handles both GET requests (displaying abilities) and POST requests
    (saving ability changes). It organizes abilities by type and provides undo
    functionality for ability modifications.

    Args:
        request: The HTTP request object containing user data and method info
        event_slug: Event identifier string for the current event
        num: The character number/ID to display abilities for

    Returns:
        HttpResponse: Rendered template with character abilities data, or redirect
                     after successful POST operation

    Raises:
        Http404: If character or event is not found (via check_char_abilities)
        PermissionDenied: If user lacks permission to view character abilities

    """
    # Initialize context with character and permission checks
    context = check_char_abilities(request, event_slug, num)

    # Build available abilities dictionary organized by ability type
    context["available"] = {}
    for ability in get_available_ability_px(context["character"]):
        # Create type entry if it doesn't exist
        if ability.typ_id not in context["available"]:
            context["available"][ability.typ_id] = {"name": ability.typ.name, "order": ability.typ.id, "list": {}}
        # Add ability with name and cost to the type's list
        context["available"][ability.typ_id]["list"][ability.id] = f"{ability.name} - {ability.cost}"

    # Build current character abilities organized by type name
    context["sheet_abilities"] = {}
    for el in get_current_ability_px(context["character"]):
        # Create type list if it doesn't exist
        if el.typ.name not in context["sheet_abilities"]:
            context["sheet_abilities"][el.typ.name] = []
        # Add ability to the type's list
        context["sheet_abilities"][el.typ.name].append(el)

    # Handle POST request for saving ability changes
    if request.method == "POST":
        _save_character_abilities(context, request)
        # Redirect to prevent duplicate submissions
        return redirect(request.path_info)

    # Create ordered list of available types for template rendering
    context["type_available"] = {
        typ_id: data["name"] for typ_id, data in sorted(context["available"].items(), key=lambda x: x[1]["order"])
    }

    # Add undo functionality for recent ability changes
    context["undo_abilities"] = get_undo_abilities(context, context["character"])

    # Render the abilities template with all context data
    return render(request, "larpmanager/event/character/abilities.html", context)


def check_char_abilities(request: HttpRequest, event_slug: str, character_num: int) -> dict:
    """Check if user can select abilities for a character in an event.

    Args:
        request: The HTTP request object
        event_slug: Event slug identifier
        character_num: Character number

    Returns:
        Context dictionary containing event and run information

    Raises:
        Http404: If user is not allowed to select abilities for this event

    """
    # Get event context with signup and status validation
    context = get_event_context(request, event_slug, signup=True, include_status=True)

    # Determine the parent event ID for configuration lookup
    event_id = context["event"].parent_id or context["event"].id

    # Check if user ability selection is enabled for this event
    if not get_event_config(event_id, "px_user", default_value=False):
        msg = "ehm."
        raise Http404(msg)

    # Validate character access permissions
    get_char_check(request, context, character_num, restrict_non_owners=True)

    return context


@login_required
def character_abilities_del(request: HttpRequest, event_slug: str, num: Any, id_del: Any) -> Any:
    """Remove character ability with validation and dependency handling.

    Args:
        request: HTTP request object
        event_slug: Event slug
        num: Character number
        id_del: Ability ID to delete

    Returns:
        HttpResponse: Redirect to character abilities page

    Raises:
        Http404: If ability is outside undo window

    """
    context = check_char_abilities(request, event_slug, num)
    undo_abilities = get_undo_abilities(context, context["character"])
    if id_del not in undo_abilities:
        msg = "ability out of undo window"
        raise Http404(msg)

    with transaction.atomic():
        remove_char_ability(context["character"], id_del)
        context["character"].save()
    messages.success(request, _("Ability removed") + "!")

    return redirect("character_abilities", event_slug=context["run"].get_slug(), num=context["character"].number)


def _save_character_abilities(context: dict[str, Any], request: HttpRequest) -> None:
    """Process character ability selection and save to character.

    Args:
        context: Context dictionary with character and available abilities
        request: HTTP request object with POST data

    """
    selected_type = request.POST.get("ability_type")
    if not selected_type:
        messages.error(request, _("Ability type missing"))
        return

    selected_type = int(selected_type)
    selected_id = request.POST.get("ability_select")
    if not selected_id:
        messages.error(request, _("Ability missing"))
        return

    selected_id = int(selected_id)
    if selected_type not in context["available"] or selected_id not in context["available"][selected_type]["list"]:
        messages.error(request, _("Selezione non valida"))
        return

    with transaction.atomic():
        context["character"].px_ability_list.add(selected_id)
        context["character"].save()
    messages.success(request, _("Ability acquired") + "!")

    get_undo_abilities(context, context["character"], selected_id)


def get_undo_abilities(context: dict, char: Any, new_ability_id: Any = None) -> Any:
    """Get list of recently acquired abilities that can be undone.

    Args:
        context: Context dictionary containing event data
        char: Character object
        new_ability_id: ID of newly acquired ability to track (optional)

    Returns:
        list: List of ability IDs that can be undone

    """
    undo_window_hours = int(get_event_config(context["event"].id, "px_undo", default_value=0, context=context))
    config_key = f"added_px_{char.id}"
    stored_config_value = char.get_config(config_key, default_value="{}")
    ability_timestamp_map = ast.literal_eval(stored_config_value)
    current_timestamp = int(time.time())
    # clean from abilities out of the undo time windows
    for ability_id_key in list(ability_timestamp_map.keys()):
        if ability_timestamp_map[ability_id_key] < current_timestamp - undo_window_hours * 3600:
            del ability_timestamp_map[ability_id_key]
    # add newly acquired ability and save it
    if undo_window_hours and new_ability_id:
        ability_timestamp_map[str(new_ability_id)] = current_timestamp
        save_single_config(char, config_key, json.dumps(ability_timestamp_map))

    # return map of abilities recently added, with int key
    return [int(ability_id) for ability_id in ability_timestamp_map]


@login_required
def character_relationships(request: HttpRequest, event_slug: str, num: int) -> HttpResponse:
    """Display character relationships with other characters in the event.

    This function retrieves and displays all relationships that a character has
    with other characters in the same event run. It handles missing characters
    gracefully and calculates font sizes based on relationship text length.

    Args:
        request: HTTP request object containing user session and data
        event_slug: Event slug identifier for URL routing
        num: Character number to display relationships for

    Returns:
        HttpResponse: Rendered template showing character relationships with
                     relationship text and dynamically sized fonts

    Raises:
        Http404: If event, run, or character access is denied
        PermissionDenied: If user lacks permission to view character

    """
    # Get event context and validate user access to event and character
    context = get_event_context(request, event_slug, include_status=True, signup=True)
    get_char_check(request, context, num, restrict_non_owners=True)

    # Load all cached event data for performance
    get_event_cache_all(context)

    # Initialize relationships list in context
    context["rel"] = []

    # Query player relationships for the current character's player in this run
    que = PlayerRelationship.objects.select_related("target", "reg", "reg__member").filter(
        reg__member_id=context["char"]["player_id"],
        reg__run=context["run"],
    )

    # Process each relationship and build display data
    for tg_num, text in que.values_list("target__number", "text"):
        # Try to get character data from cache first for performance
        if "chars" in context and tg_num in context["chars"]:
            show = context["chars"][tg_num]
        else:
            # Fallback to database query if not in cache
            try:
                ch = Character.objects.select_related("event", "player").get(event=context["event"], number=tg_num)
                show = ch.show(context["run"])
            except ObjectDoesNotExist:
                # Skip relationships to non-existent characters
                continue

        # Add relationship text and calculate dynamic font size
        show["text"] = text
        # Font size decreases as text length increases (min ~80%, max 100%)
        show["font_size"] = int(100 - ((len(text) / 50) * 4))
        context["rel"].append(show)

    return render(request, "larpmanager/event/character/relationships.html", context)


@login_required
def character_relationships_edit(request: HttpRequest, event_slug: str, num: Any, other_character_id: Any) -> Any:
    """Handle editing of character relationship with another character.

    Args:
        request: HTTP request object
        event_slug: Event slug
        num: Character number
        other_character_id: Other character number for relationship

    Returns:
        HttpResponse: Relationship edit form or redirect

    """
    context = get_event_context(request, event_slug, include_status=True, signup=True)
    get_char_check(request, context, num, restrict_non_owners=True)

    context["relationship"] = None
    if other_character_id != 0:
        get_player_relationship(context, other_character_id)

    if user_edit(request, context, PlayerRelationshipForm, "relationship", other_character_id):
        return redirect("character_relationships", event_slug=context["run"].get_slug(), num=context["char"]["number"])
    return render(request, "larpmanager/orga/edit.html", context)


@require_POST
def show_char(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Show character information in a tooltip format.

    Retrieves character data based on a search parameter and returns
    a JSON response containing formatted character tooltip HTML.

    Args:
        request: The HTTP request object containing POST data
        event_slug: String identifier for the event/run context

    Returns:
        JsonResponse containing character tooltip HTML content

    Raises:
        Http404: If search parameter is malformed, invalid, or character not found

    """
    # Get event context and populate character cache
    context = get_event_context(request, event_slug)
    get_event_cache_all(context)

    # Extract and validate search parameter from POST data
    search_text = request.POST.get("text", "").strip()
    if not search_text.startswith(("#", "@", "^")):
        msg = f"malformed request {search_text}"
        raise Http404(msg)

    # Parse numeric character ID from search string
    character_id = int(search_text[1:])
    if not character_id:
        msg = f"not valid search {character_id}"
        raise Http404(msg)

    # Verify character exists in context
    if character_id not in context["chars"]:
        msg = f"not present char number {character_id}"
        raise Http404(msg)

    # Generate tooltip content and return JSON response
    character = context["chars"][character_id]
    tooltip_content = get_tooltip(context, character)
    return JsonResponse({"content": f"<div class='show_char'>{tooltip_content}</div>"})
