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

import ast
import json
import os
import time
from typing import Any, Optional, Union
from uuid import uuid4

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.forms import Form
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from PIL import Image

from larpmanager.cache.character import get_character_element_fields, get_event_cache_all
from larpmanager.cache.config import get_event_config, save_single_config
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
from larpmanager.utils.character import (
    check_missing_mandatory,
    get_char_check,
    get_character_relationships,
    get_character_sheet,
)
from larpmanager.utils.common import get_player_relationship
from larpmanager.utils.edit import user_edit
from larpmanager.utils.event import get_event_run
from larpmanager.utils.experience import get_available_ability_px, get_current_ability_px, remove_char_ability
from larpmanager.utils.registration import (
    check_assign_character,
    check_character_maximum,
    get_player_characters,
    registration_find,
)
from larpmanager.utils.text import get_event_text
from larpmanager.utils.writing import char_add_addit
from larpmanager.views.user.casting import casting_details, get_casting_preferences
from larpmanager.views.user.registration import init_form_submitted


def character(request, s, num):
    ctx = get_event_run(request, s, status=True)
    get_char_check(request, ctx, num)

    return _character_sheet(request, ctx)


def _character_sheet(request: HttpRequest, ctx: dict) -> HttpResponse:
    """Display character sheet with visibility and approval checks.

    This function handles the display of character sheets with proper visibility
    checks, approval validation, and contextual data preparation based on user
    permissions and character settings.

    Args:
        request: Django HTTP request object containing user session and metadata
        ctx: Context dictionary containing event, run, character data and permissions

    Returns:
        HttpResponse: Rendered character sheet template or redirect to gallery

    Raises:
        Redirect: When character visibility rules are violated or access is denied
    """
    # Enable screen mode for character sheet display
    ctx["screen"] = True

    # Check if characters are visible to regular users (non-staff)
    if "check" not in ctx and not ctx["show_character"]:
        messages.warning(request, _("Characters are not visible at the moment"))
        return redirect("gallery", s=ctx["run"].get_slug())

    # Verify individual character visibility settings
    if "check" not in ctx and ctx["char"]["hide"]:
        messages.warning(request, _("Character not visible"))
        return redirect("gallery", s=ctx["run"].get_slug())

    # Determine access level and load appropriate character data
    show_private = "check" in ctx
    if show_private:
        # Load full character data for staff/admin users
        get_character_sheet(ctx)
        get_character_relationships(ctx)
        ctx["intro"] = get_event_text(ctx["event"].id, EventTextType.INTRO)
        check_missing_mandatory(ctx)
    else:
        # Load only visible elements for regular users
        ctx["char"].update(get_character_element_fields(ctx, ctx["char"]["id"], only_visible=True))

    # Load casting details and preferences if applicable
    casting_details(ctx, 0)
    if ctx["casting_show_pref"] and not ctx["char"]["player_id"]:
        ctx["pref"] = get_casting_preferences(ctx["char"]["id"], ctx, 0)

    # Set character approval configuration for template rendering
    ctx["approval"] = get_event_config(ctx["event"].id, "user_character_approval", False, ctx)

    return render(request, "larpmanager/event/character.html", ctx)


def character_external(request: HttpRequest, s: str, code: str) -> HttpResponse:
    """Display character sheet via external access token.

    This function provides external access to character sheets when enabled for an event.
    It validates the access token and returns the character sheet view.

    Args:
        request: Django HTTP request object containing user session and metadata
        s: Event slug identifier used to locate the specific event
        code: External access token for character authentication

    Returns:
        HttpResponse: Character sheet view rendered for the authenticated character

    Raises:
        Http404: If external access is disabled for the event or if the provided
                access token is invalid or doesn't match any character
    """
    # Get event and run context from the provided slug
    ctx = get_event_run(request, s)

    # Check if external access feature is enabled for this event
    if not get_event_config(ctx["event"].id, "writing_external_access", False, ctx):
        raise Http404("external access not active")

    # Attempt to retrieve character using the provided access token
    try:
        char = ctx["event"].get_elements(Character).get(access_token=code)
    except ObjectDoesNotExist as err:
        raise Http404("invalid code") from err

    # Load all cached event data including characters
    get_event_cache_all(ctx)

    # Verify character exists in the cached character list
    if char.number not in ctx["chars"]:
        messages.warning(request, _("Character not found"))
        return redirect("/")

    # Populate context with character data for template rendering
    ctx["char"] = ctx["chars"][char.number]
    ctx["character"] = char
    ctx["check"] = 1

    return _character_sheet(request, ctx)


def character_your_link(ctx, char, p=None):
    url = reverse(
        "character",
        kwargs={
            "s": ctx["run"].get_slug(),
            "num": char.number,
        },
    )
    if p:
        url += p
    return url


@login_required
def character_your(request: HttpRequest, s: str, p: str = None) -> HttpResponse:
    """Display user's character information.

    Shows the character information page for the authenticated user. If the user has
    only one character, redirects directly to that character's page. If multiple
    characters exist, displays a selection list.

    Args:
        request: HTTP request object containing user authentication and session data
        s: Event slug identifier for the specific event
        p: Optional character parameter for additional filtering or display options

    Returns:
        HttpResponse: Rendered character template, character selection list, or
                     redirect response if no characters are found

    Raises:
        Redirect: To home page if user has no assigned characters for the event
    """
    # Get event and run context with signup and status validation
    ctx = get_event_run(request, s, signup=True, status=True)

    # Retrieve all registration character relationships for this run
    # Use select_related to optimize database queries for character data
    rcrs = list(ctx["run"].reg.rcrs.select_related("character").all())

    # Handle case where user has no characters assigned to this event
    if not rcrs:
        messages.error(request, _("You don't have a character assigned for this event") + "!")
        return redirect("home")

    # If user has exactly one character, redirect directly to character page
    if len(rcrs) == 1:
        char = rcrs[0].character
        url = character_your_link(ctx, char, p)
        return HttpResponseRedirect(url)

    # Build character selection list for multiple characters
    # Create URLs and display names for each character option
    ctx["urls"] = []
    for el in rcrs:
        url = character_your_link(ctx, el.character, p)
        # Use custom name if available, otherwise use character's default name
        char = el.character.name
        if el.custom_name:
            char = el.custom_name
        ctx["urls"].append((char, url))

    # Render character selection template with context data
    return render(request, "larpmanager/event/character/your.html", ctx)


def character_form(
    request: HttpRequest,
    ctx: dict[str, Any],
    s: str,
    instance: Optional[Union[Character, RegistrationCharacterRel]],
    form_class: type[Form],
) -> HttpResponse:
    """Handle character creation and editing form processing.

    Manages character form submission, validation, saving, and assignment
    with transaction safety and proper message handling.

    Args:
        request: The HTTP request object containing form data
        ctx: Template context dictionary with event and user data
        s: Event slug identifier
        instance: Existing character or registration relation to edit, None for new
        form_class: Django form class to use for character processing

    Returns:
        HttpResponse: Rendered form page or redirect to character detail

    Note:
        Uses atomic transactions to ensure data consistency during save operations.
        Handles both character creation and editing workflows.
    """
    # Initialize form dependencies and set element type for template context
    get_options_dependencies(ctx)
    ctx["elementTyp"] = Character

    if request.method == "POST":
        # Process form submission with uploaded files
        form = form_class(request.POST, request.FILES, instance=instance, ctx=ctx)
        if form.is_valid():
            # Set appropriate success message based on operation type
            if instance:
                mes = _("Informations saved") + "!"
            else:
                mes = _("New character created") + "!"

            # Save character data within atomic transaction
            with transaction.atomic():
                element = form.save(commit=False)
                # Update character with additional processing and context
                mes = _update_character(ctx, element, form, mes, request)
                element.save()

                # Handle character assignment logic
                check_assign_character(request, ctx)

            # Display success message to user
            if mes:
                messages.success(request, mes)

            # Determine character number for redirect
            number = None
            if isinstance(element, Character):
                number = element.number
            elif isinstance(element, RegistrationCharacterRel):
                number = element.character.number
            # Redirect to character detail page
            return redirect("character", s=s, num=number)
    else:
        # Initialize empty form for GET requests
        form = form_class(instance=instance, ctx=ctx)

    # Add form to template context and initialize form state
    ctx["form"] = form
    init_form_submitted(ctx, form, request)

    # Configure form display options from event settings
    ctx["hide_unavailable"] = get_event_config(ctx["event"].id, "character_form_hide_unavailable", False, ctx)

    return render(request, "larpmanager/event/character/edit.html", ctx)


def _update_character(ctx, element, form, mes, request):
    if not isinstance(element, Character):
        return

    if not element.player:
        element.player = request.user.member

    if get_event_config(ctx["event"].id, "user_character_approval", False, ctx):
        if element.status in [CharacterStatus.CREATION, CharacterStatus.REVIEW] and form.cleaned_data["propose"]:
            element.status = CharacterStatus.PROPOSED
            mes = _(
                "The character has been proposed to the staff, who will examine it and approve it "
                "or request changes if necessary."
            )
    return mes


@login_required
def character_customize(request, s, num):
    """
    Handle character customization form with profile and custom fields.

    Args:
        request: HTTP request object
        s: Event slug
        num: Character number

    Returns:
        HttpResponse: Character customization form

    Raises:
        Http404: If character doesn't belong to user
    """
    ctx = get_event_run(request, s, signup=True, status=True)

    get_char_check(request, ctx, num, True)

    try:
        rgr = RegistrationCharacterRel.objects.select_related("character", "reg", "reg__member").get(
            reg=ctx["run"].reg, character__number=num
        )
        if rgr.custom_profile:
            ctx["custom_profile"] = rgr.profile_thumb.url

        if get_event_config(ctx["event"].id, "custom_character_profile", False, ctx):
            ctx["avatar_form"] = AvatarForm()

        return character_form(request, ctx, s, rgr, RegistrationCharacterRelForm)
    except ObjectDoesNotExist as err:
        raise Http404("not your char!") from err


@login_required
def character_profile_upload(request: HttpRequest, s: str, num: int) -> JsonResponse:
    """
    Handle character profile image upload via AJAX.

    Processes an uploaded character profile image for a specific character in an event,
    validates the upload, and saves it to storage with a unique filename.

    Args:
        request: HTTP request object containing the uploaded file in POST data
        s: Event slug identifier for the target event
        num: Character number within the event registration

    Returns:
        JsonResponse containing:
            - "res": "ok" on success, "ko" on failure
            - "src": thumbnail URL of uploaded image (on success only)

    Raises:
        ObjectDoesNotExist: When character registration relationship is not found
    """
    # Validate request method is POST
    if not request.method == "POST":
        return JsonResponse({"res": "ko"})

    # Validate uploaded file using form
    form = AvatarForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"res": "ko"})

    # Get event context and validate user permissions
    ctx = get_event_run(request, s, signup=True)
    registration_find(ctx["run"], request.user, None)
    get_char_check(request, ctx, num, True)

    # Retrieve character registration relationship
    try:
        rgr = RegistrationCharacterRel.objects.select_related("character", "reg", "reg__member").get(
            reg=ctx["run"].reg, character__number=num
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
def character_profile_rotate(request: HttpRequest, s: str, num: int, r: int) -> JsonResponse:
    """
    Rotate character profile image by specified degrees.

    Args:
        request (HttpRequest): HTTP request object containing user session
        s (str): Event slug identifier
        num (int): Character number identifier
        r (int): Rotation direction (1 for 90°, else -90°)

    Returns:
        JsonResponse: Dictionary with 'res' status ('ok'/'ko') and 'src' URL if successful

    Raises:
        ObjectDoesNotExist: When character registration relationship not found
    """
    # Get event context and validate character access permissions
    ctx = get_event_run(request, s, signup=True, status=True)
    get_char_check(request, ctx, num, True)

    # Retrieve character registration relationship with related objects
    try:
        rgr = RegistrationCharacterRel.objects.select_related("character", "reg", "reg__member").get(
            reg=ctx["run"].reg, character__number=num
        )
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko"})

    # Validate that character has a custom profile image
    path = str(rgr.custom_profile)
    if not path:
        return JsonResponse({"res": "ko"})

    # Open and rotate the image based on direction parameter
    path = os.path.join(conf_settings.MEDIA_ROOT, path)
    im = Image.open(path)
    if r == 1:
        out = im.rotate(90)
    else:
        out = im.rotate(-90)

    # Generate unique filename and save rotated image
    ext = path.split(".")[-1]
    n_path = f"{os.path.dirname(path)}/{rgr.pk}_{uuid4().hex}.{ext}"
    out.save(n_path)

    # Update database with new image path atomically
    with transaction.atomic():
        rgr.custom_profile = n_path
        rgr.save()

    return JsonResponse({"res": "ok", "src": rgr.profile_thumb.url})


@login_required
def character_list(request, s):
    """
    Display list of player's characters for an event with customization fields.

    Args:
        request: HTTP request object
        s: Event slug

    Returns:
        HttpResponse: Rendered character list template
    """
    ctx = get_event_run(request, s, status=True, signup=True, slug="user_character")

    ctx["list"] = get_player_characters(request.user.member, ctx["event"])
    # add character configs
    char_add_addit(ctx)
    for el in ctx["list"]:
        if "character" in ctx["features"]:
            res = get_character_element_fields(ctx, el.id, only_visible=True)
            el.fields = res["fields"]
            ctx.update(res)

    check, _max_chars = check_character_maximum(ctx["event"], request.user.member)
    ctx["char_maximum"] = check
    ctx["approval"] = get_event_config(ctx["event"].id, "user_character_approval", False, ctx)
    ctx["assigned"] = RegistrationCharacterRel.objects.filter(reg_id=ctx["run"].reg.id).count()
    return render(request, "larpmanager/event/character/list.html", ctx)


@login_required
def character_create(request, s):
    """
    Handle character creation with maximum character validation.

    Args:
        request: HTTP request object
        s: Event slug

    Returns:
        HttpResponse: Character creation form or redirect
    """
    ctx = get_event_run(request, s, status=True, signup=True, slug="user_character")

    check, _max_chars = check_character_maximum(ctx["event"], request.user.member)
    if check:
        messages.success(request, _("You have reached the maximum number of characters that can be created"))
        return redirect("character_list", s=s)

    ctx["class_name"] = "character"
    return character_form(request, ctx, s, None, CharacterForm)


@login_required
def character_edit(request, s, num):
    """
    Handle character editing form for specific character.

    Args:
        request: HTTP request object
        s: Event slug
        num: Character number

    Returns:
        HttpResponse: Character editing form
    """
    ctx = get_event_run(request, s, status=True, signup=True)
    get_char_check(request, ctx, num, True)
    return character_form(request, ctx, s, ctx["character"], CharacterForm)


def get_options_dependencies(ctx):
    ctx["dependencies"] = {}
    if "character" not in ctx["features"]:
        return

    que = ctx["event"].get_elements(WritingQuestion).order_by("order")
    que = que.filter(applicable=QuestionApplicable.CHARACTER)
    question_idxs = que.values_list("id", flat=True)

    que = ctx["event"].get_elements(WritingOption).filter(question_id__in=question_idxs)
    for el in que.filter(requirements__isnull=False).distinct():
        ctx["dependencies"][el.id] = list(el.requirements.values_list("id", flat=True))


@login_required
def character_assign(request, s, num):
    """
    Assign character to user's registration if not already assigned.

    Args:
        request: HTTP request object
        s: Event slug
        num: Character number

    Returns:
        HttpResponse: Redirect to character list
    """
    ctx = get_event_run(request, s, signup=True, status=True)
    get_char_check(request, ctx, num, True)
    if RegistrationCharacterRel.objects.filter(reg_id=ctx["run"].reg.id).exists():
        messages.warning(request, _("You already have an assigned character"))
    else:
        RegistrationCharacterRel.objects.create(reg_id=ctx["run"].reg.id, character_id=ctx["character"].id)
        messages.success(request, _("Assigned character!"))

    return redirect("character_list", s=s)


@login_required
def character_abilities(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """
    Display character abilities with available and current abilities organized by type.

    This view handles both GET requests (displaying abilities) and POST requests
    (saving ability changes). It organizes abilities by type and provides undo
    functionality for ability modifications.

    Args:
        request: The HTTP request object containing user data and method info
        s: The event slug identifier for the current event
        num: The character number/ID to display abilities for

    Returns:
        HttpResponse: Rendered template with character abilities data, or redirect
                     after successful POST operation

    Raises:
        Http404: If character or event is not found (via check_char_abilities)
        PermissionDenied: If user lacks permission to view character abilities
    """
    # Initialize context with character and permission checks
    ctx = check_char_abilities(request, s, num)

    # Build available abilities dictionary organized by ability type
    ctx["available"] = {}
    for ability in get_available_ability_px(ctx["character"]):
        # Create type entry if it doesn't exist
        if ability.typ_id not in ctx["available"]:
            ctx["available"][ability.typ_id] = {"name": ability.typ.name, "order": ability.typ.id, "list": {}}
        # Add ability with name and cost to the type's list
        ctx["available"][ability.typ_id]["list"][ability.id] = f"{ability.name} - {ability.cost}"

    # Build current character abilities organized by type name
    ctx["sheet_abilities"] = {}
    for el in get_current_ability_px(ctx["character"]):
        # Create type list if it doesn't exist
        if el.typ.name not in ctx["sheet_abilities"]:
            ctx["sheet_abilities"][el.typ.name] = []
        # Add ability to the type's list
        ctx["sheet_abilities"][el.typ.name].append(el)

    # Handle POST request for saving ability changes
    if request.method == "POST":
        _save_character_abilities(ctx, request)
        # Redirect to prevent duplicate submissions
        return redirect(request.path_info)

    # Create ordered list of available types for template rendering
    ctx["type_available"] = {
        typ_id: data["name"] for typ_id, data in sorted(ctx["available"].items(), key=lambda x: x[1]["order"])
    }

    # Add undo functionality for recent ability changes
    ctx["undo_abilities"] = get_undo_abilities(request, ctx, ctx["character"])

    # Render the abilities template with all context data
    return render(request, "larpmanager/event/character/abilities.html", ctx)


def check_char_abilities(request, s, num):
    ctx = get_event_run(request, s, signup=True, status=True)

    # check the user can select abilities
    event_id = ctx["event"].parent_id or ctx["event"].id
    if not get_event_config(event_id, "px_user", False):
        raise Http404("ehm.")

    get_char_check(request, ctx, num, True)

    return ctx


@login_required
def character_abilities_del(request, s, num, id_del):
    """
    Remove character ability with validation and dependency handling.

    Args:
        request: HTTP request object
        s: Event slug
        num: Character number
        id_del: Ability ID to delete

    Returns:
        HttpResponse: Redirect to character abilities page

    Raises:
        Http404: If ability is outside undo window
    """
    ctx = check_char_abilities(request, s, num)
    undo_abilities = get_undo_abilities(request, ctx, ctx["character"])
    if id_del not in undo_abilities:
        raise Http404("ability out of undo window")

    with transaction.atomic():
        remove_char_ability(ctx["character"], id_del)
        ctx["character"].save()
    messages.success(request, _("Ability removed") + "!")

    return redirect("character_abilities", s=ctx["run"].get_slug(), num=ctx["character"].number)


def _save_character_abilities(ctx, request):
    """
    Process character ability selection and save to character.

    Args:
        ctx: Context dictionary with character and available abilities
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
    if selected_type not in ctx["available"] or selected_id not in ctx["available"][selected_type]["list"]:
        messages.error(request, _("Selezione non valida"))
        return

    with transaction.atomic():
        ctx["character"].px_ability_list.add(selected_id)
        ctx["character"].save()
    messages.success(request, _("Ability acquired") + "!")

    get_undo_abilities(request, ctx, ctx["character"], selected_id)


def get_undo_abilities(request, ctx, char, new_ability_id=None):
    """Get list of recently acquired abilities that can be undone.

    Args:
        request: HTTP request object
        ctx: Context dictionary containing event data
        char: Character object
        new_ability_id: ID of newly acquired ability to track (optional)

    Returns:
        list: List of ability IDs that can be undone
    """
    px_undo = int(get_event_config(ctx["event"].id, "px_undo", 0, ctx))
    config_name = f"added_px_{char.id}"
    val = char.get_config(config_name, "{}")
    added_map = ast.literal_eval(val)
    current_time = int(time.time())
    # clean from abilities out of the undo time windows
    for key in list(added_map.keys()):
        if added_map[key] < current_time - px_undo * 3600:
            del added_map[key]
    # add newly acquired ability and save it
    if px_undo and new_ability_id:
        added_map[str(new_ability_id)] = current_time
        save_single_config(char, config_name, json.dumps(added_map))

    # return map of abilities recently added, with int key
    return [int(k) for k in added_map.keys()]


@login_required
def character_relationships(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """
    Display character relationships with other characters in the event.

    This function retrieves and displays all relationships that a character has
    with other characters in the same event run. It handles missing characters
    gracefully and calculates font sizes based on relationship text length.

    Args:
        request: HTTP request object containing user session and data
        s: Event slug identifier for URL routing
        num: Character number to display relationships for

    Returns:
        HttpResponse: Rendered template showing character relationships with
                     relationship text and dynamically sized fonts

    Raises:
        Http404: If event, run, or character access is denied
        PermissionDenied: If user lacks permission to view character
    """
    # Get event context and validate user access to event and character
    ctx = get_event_run(request, s, status=True, signup=True)
    get_char_check(request, ctx, num, True)

    # Load all cached event data for performance
    get_event_cache_all(ctx)

    # Initialize relationships list in context
    ctx["rel"] = []

    # Query player relationships for the current character's player in this run
    que = PlayerRelationship.objects.select_related("target", "reg", "reg__member").filter(
        reg__member_id=ctx["char"]["player_id"], reg__run=ctx["run"]
    )

    # Process each relationship and build display data
    for tg_num, text in que.values_list("target__number", "text"):
        # Try to get character data from cache first for performance
        if "chars" in ctx and tg_num in ctx["chars"]:
            show = ctx["chars"][tg_num]
        else:
            # Fallback to database query if not in cache
            try:
                ch = Character.objects.select_related("event", "player").get(event=ctx["event"], number=tg_num)
                show = ch.show(ctx["run"])
            except ObjectDoesNotExist:
                # Skip relationships to non-existent characters
                continue

        # Add relationship text and calculate dynamic font size
        show["text"] = text
        # Font size decreases as text length increases (min ~80%, max 100%)
        show["font_size"] = int(100 - ((len(text) / 50) * 4))
        ctx["rel"].append(show)

    return render(request, "larpmanager/event/character/relationships.html", ctx)


@login_required
def character_relationships_edit(request, s, num, oth):
    """
    Handle editing of character relationship with another character.

    Args:
        request: HTTP request object
        s: Event slug
        num: Character number
        oth: Other character number for relationship

    Returns:
        HttpResponse: Relationship edit form or redirect
    """
    ctx = get_event_run(request, s, status=True, signup=True)
    get_char_check(request, ctx, num, True)

    ctx["relationship"] = None
    if oth != 0:
        get_player_relationship(ctx, oth)

    if user_edit(request, ctx, PlayerRelationshipForm, "relationship", oth):
        return redirect("character_relationships", s=ctx["run"].get_slug(), num=ctx["char"]["number"])
    return render(request, "larpmanager/orga/edit.html", ctx)


@require_POST
def show_char(request, s):
    ctx = get_event_run(request, s)
    get_event_cache_all(ctx)
    search = request.POST.get("text", "").strip()
    if not search.startswith(("#", "@", "^")):
        raise Http404(f"malformed request {search}")
    search = int(search[1:])
    if not search:
        raise Http404(f"not valid search {search}")
    if search not in ctx["chars"]:
        raise Http404(f"not present char number {search}")
    ch = ctx["chars"][search]
    tooltip = get_tooltip(ctx, ch)
    return JsonResponse({"content": f"<div class='show_char'>{tooltip}</div>"})
