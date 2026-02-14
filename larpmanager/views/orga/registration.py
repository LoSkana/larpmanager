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

import json
import logging
import time
from random import shuffle
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models.functions import Substr
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from slugify import slugify

from larpmanager.accounting.base import is_registration_provisional
from larpmanager.accounting.registration import (
    cancel_reg,
    check_registration_background,
    get_accounting_refund,
    get_registration_payments,
)
from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.config import get_association_config, get_event_config
from larpmanager.cache.question import get_cached_registration_questions
from larpmanager.cache.text_fields import get_cache_registration_field
from larpmanager.forms.registration import (
    OrgaRegistrationForm,
    RegistrationCharacterRelForm,
)
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemOther,
    AccountingItemPayment,
    OtherChoices,
)
from larpmanager.models.casting import AssignmentTrait, QuestType, Trait
from larpmanager.models.event import PreRegistration
from larpmanager.models.form import (
    BaseQuestionType,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
)
from larpmanager.models.member import Member, Membership, get_user_membership
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.writing import Character
from larpmanager.utils.auth.permission import has_event_permission
from larpmanager.utils.core.base import check_event_context
from larpmanager.utils.core.common import (
    get_discount,
    get_element_event,
    get_registration,
    get_time_diff,
)
from larpmanager.utils.io.download import _orga_registrations_acc, download
from larpmanager.views.orga.member import member_field_correct

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)


def check_time(times: Any, step: Any, start: Any = None) -> Any:
    """Record timing information for performance monitoring."""
    if step not in times:
        times[step] = []
    now = time.time()
    times[step].append(now - start)
    return now


def _orga_registrations_traits(registration: Any, context: dict) -> None:
    """Process and organize character traits for registration display.

    Args:
        registration: Registration instance to process
        context: Context dictionary with traits and quest data

    """
    if "questbuilder" not in context["features"]:
        return

    registration.traits = {}
    if not hasattr(registration, "chars"):
        return
    for character in registration.chars:
        if "traits" not in character:
            continue
        for trait_number in character["traits"]:
            trait = context["traits"][trait_number]
            quest = context["quests"][trait["quest"]]
            quest_type = context["quest_types"][quest["typ"]]
            quest_type_uuid = quest_type["uuid"]
            if quest_type_uuid not in registration.traits:
                registration.traits[quest_type_uuid] = []
            registration.traits[quest_type_uuid].append(f"{quest['name']} - {trait['name']}")

    for quest_type_uuid in registration.traits:
        registration.traits[quest_type_uuid] = ",".join(registration.traits[quest_type_uuid])


def _orga_registrations_tickets(registration: Any, context: dict) -> None:
    """Process registration ticket information and categorize by type.

    Analyzes a registration's ticket information and categorizes it based on ticket tier.
    Updates the context dictionary with registration counts and lists organized by type.
    Handles cases where tickets are missing or invalid, and respects grouping preferences.

    Args:
        registration: Registration instance to process, must have ticket_id and member attributes
        context: Context dictionary containing:
            - reg_tickets: Dictionary mapping ticket IDs to ticket objects
            - event: Event instance for provisional registration checks
            - features: Feature flags for registration validation
            - no_grouping: Boolean flag to disable ticket type grouping
            - reg_all: Dictionary to store categorized registration data
            - list_tickets: Dictionary for ticket name tracking

    Returns:
        None: Modifies context dictionary in-place

    """
    # Define default ticket type for participants
    default_ticket_type = ("1", _("Participant"))

    # Map ticket tiers to their display types and sort order
    ticket_types = {
        TicketTier.FILLER: ("2", _("Filler")),
        TicketTier.WAITING: ("3", _("Waiting")),
        TicketTier.LOTTERY: ("4", _("Lottery")),
        TicketTier.NPC: ("5", _("NPC")),
        TicketTier.COLLABORATOR: ("6", _("Collaborator")),
        TicketTier.STAFF: ("7", _("Staff")),
        TicketTier.SELLER: ("8", _("Seller")),
    }

    # Start with default type, will be overridden if specific ticket found
    registration_type = default_ticket_type

    # Handle missing or invalid ticket references
    if not registration.ticket_id or registration.ticket_id not in context["reg_tickets"]:
        regs_list_add(context, "list_tickets", "e", registration.member)
    else:
        # Process valid ticket and determine registration type
        ticket = context["reg_tickets"][registration.ticket_id]
        regs_list_add(context, "list_tickets", ticket.name, registration.member)
        registration.ticket_show = ticket.name

        # Check for provisional status first, then map ticket tier to type
        if is_registration_provisional(
            registration, event=context["event"], features=context["features"], context=context
        ):
            registration_type = ("0", _("Provisional"))
        elif ticket.tier in ticket_types:
            registration_type = ticket_types[ticket.tier]

    # Ensure both default and current type categories exist in context
    for type_key in [default_ticket_type, registration_type]:
        if type_key[0] not in context["reg_all"]:
            context["reg_all"][type_key[0]] = {"count": 0, "type": type_key[1], "list": []}

    # Increment count for the determined registration type
    context["reg_all"][registration_type[0]]["count"] += 1

    # Override grouping if disabled - all registrations go to default type
    if context["no_grouping"]:
        registration_type = default_ticket_type

    # Add registration to the appropriate category list
    context["reg_all"][registration_type[0]]["list"].append(registration)


def orga_registrations_membership(registration: Any, context: dict) -> None:
    """Process membership status for registration display.

    Args:
        registration: Registration instance
        context: Context dictionary with membership data

    """
    member = registration.member
    if member.id in context["memberships"]:
        member.membership = context["memberships"][member.id]
    else:
        get_user_membership(member, context["association_id"])
    membership_status_display = member.membership.get_status_display()
    regs_list_add(context, "list_membership", membership_status_display, registration.member)
    registration.membership = member.membership.get_status_display


def regs_list_add(context_dict: Any, category_list_key: Any, category_name: Any, member: Any) -> None:
    """Add member to categorized registration lists."""
    slugified_key = slugify(category_name)
    if category_list_key not in context_dict:
        context_dict[category_list_key] = {}
    if slugified_key not in context_dict[category_list_key]:
        context_dict[category_list_key][slugified_key] = {"name": category_name, "emails": [], "players": []}
    if member.email not in context_dict[category_list_key][slugified_key]["emails"]:
        context_dict[category_list_key][slugified_key]["emails"].append(member.email)
        context_dict[category_list_key][slugified_key]["players"].append(member.display_member())


def _orga_registrations_standard(registration: Any, context: dict) -> None:
    """Process standard registration data including characters and membership.

    Args:
        registration: Registration instance to process
        context: Context dictionary with event data

    """
    # skip if it is gift
    if registration.redeem_code:
        return

    regs_list_add(context, "list_all", "all", registration.member)

    _orga_registration_character(context, registration)

    # membership status
    if "membership" in context["features"]:
        orga_registrations_membership(registration, context)

    # age at run
    if context["registration_reg_que_age"] and registration.member.birth_date and context["run"].start:
        registration.age = calculate_age(registration.member.birth_date, context["run"].start)


def _orga_registration_character(context: dict, registration: Any) -> None:
    """Process character data for registration including factions and customizations.

    Args:
        context: Context dictionary with character data
        registration: Registration instance to update

    """
    if registration.member.uuid not in context["reg_chars"]:
        return

    registration.factions = []
    registration.chars = context["reg_chars"][registration.member.uuid]
    for character in registration.chars:
        if "factions" in character:
            registration.factions.extend(character["factions"])
            for faction_number in character["factions"]:
                if faction_number in context["factions"]:
                    regs_list_add(
                        context,
                        "list_factions",
                        context["factions"][faction_number]["name"],
                        registration.member,
                    )

        if "custom_character" in context["features"]:
            orga_registrations_custom(registration, context, character)

    if "custom_character" in context["features"] and registration.custom:
        for section in context["custom_info"]:
            if not registration.custom[section]:
                continue
            registration.custom[section] = ", ".join(registration.custom[section])


def orga_registrations_custom(registration: Any, context: dict, character_data: Any) -> None:
    """Process custom character information for registration.

    Args:
        registration: Registration instance
        context: Context dictionary with custom field info
        character_data: Character data dictionary

    """
    if not hasattr(registration, "custom"):
        registration.custom = {}

    for custom_field_slug in context["custom_info"]:
        if custom_field_slug not in registration.custom:
            registration.custom[custom_field_slug] = []
        field_value = ""
        if custom_field_slug in character_data:
            field_value = character_data[custom_field_slug]
        if custom_field_slug == "profile" and field_value:
            field_value = f"<img src='{escape(field_value)}' class='reg_profile' />"
        if field_value:
            registration.custom[custom_field_slug].append(field_value)


def registrations_popup(request: HttpRequest, context: dict) -> Any:
    """Handle AJAX popup requests for registration details.

    Args:
        request: HTTP request with popup parameters
        context: Context dictionary with registration data

    Returns:
        dict: Response data for popup

    """
    registration_uuid = request.POST.get("idx", "")
    question_uuid = request.POST.get("tp", "")

    try:
        registration = Registration.objects.get(uuid=registration_uuid, run=context["run"])
        question = RegistrationQuestion.objects.get(
            uuid=question_uuid,
            event=context["event"].get_class_parent(RegistrationQuestion),
        )
        answer = RegistrationAnswer.objects.get(registration=registration, question=question)
        html_text = f"<h2>{registration} - {question.name}</h2>" + answer.text
        return JsonResponse({"k": 1, "v": html_text})
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})


def _orga_registrations_custom_character(context: dict) -> None:
    """Prepare custom character information for registration display.

    Args:
        context: Context dictionary to populate with custom character info

    """
    if "custom_character" not in context["features"]:
        return
    context["custom_info"] = []
    for field_name in ["pronoun", "song", "public", "private", "profile"]:
        if not get_event_config(
            context["event"].id, "custom_character_" + field_name, default_value=False, context=context
        ):
            continue
        context["custom_info"].append(field_name)


def _orga_registrations_prepare(context: dict) -> None:
    """Prepare registration data including characters, tickets, and questions.

    Args:
        context: Context dictionary to populate with registration data

    """
    context["reg_chars"] = {}
    for character in context["chars"].values():
        if "player_uuid" not in character:
            continue
        if character["player_uuid"] not in context["reg_chars"]:
            context["reg_chars"][character["player_uuid"]] = []
        context["reg_chars"][character["player_uuid"]].append(character)
    context["reg_tickets"] = {}
    for ticket in RegistrationTicket.objects.filter(event=context["event"]).order_by("-price"):
        ticket.emails = []
        context["reg_tickets"][ticket.id] = ticket
    context["reg_questions"] = _get_registration_fields(context, context["member"])

    context["no_grouping"] = get_event_config(
        context["event"].id, "registration_no_grouping", default_value=False, context=context
    )


def _get_registration_fields(context: dict, member: Any) -> dict:
    """Get registration questions that are accessible to the given member.

    Args:
        context: Context dictionary containing event, features, run, and all_runs information
        member: Member object to check question access permissions for

    Returns:
        Dictionary mapping question IDs to RegistrationQuestion objects that the member can access

    """
    registration_questions = {}

    # Get all registration questions for the event
    event_questions = get_cached_registration_questions(context["event"])

    for question in event_questions:
        # Check if question has access restrictions enabled
        if "reg_que_allowed" in context["features"] and question.allowed_map and question.allowed_map[0]:
            current_run_id = context["run"].id

            # Check if user is an organizer for this run
            is_organizer = current_run_id in context["all_runs"] and 1 in context["all_runs"][current_run_id]

            # Skip question if user is not organizer and not in allowed list
            if not is_organizer and member.id not in question.allowed_map:
                continue

        # Add accessible question to results
        registration_questions[question.uuid] = question

    return registration_questions


def _orga_registrations_discount(context: dict) -> None:
    """Populate context with registration discounts for members if discount feature is enabled."""
    if "discount" not in context["features"]:
        return

    # Initialize discount tracking structures
    context["reg_discounts"] = {}
    discount_items_query = AccountingItemDiscount.objects.filter(run=context["run"])

    # Process each discount item and organize by member
    for accounting_item_discount in discount_items_query.select_related("member", "disc").exclude(hide=True):
        regs_list_add(context, "list_discount", accounting_item_discount.disc.name, accounting_item_discount.member)
        if accounting_item_discount.member_id not in context["reg_discounts"]:
            context["reg_discounts"][accounting_item_discount.member_id] = []
        context["reg_discounts"][accounting_item_discount.member_id].append(accounting_item_discount.disc.name)


def _orga_registrations_text_fields(context: dict) -> None:
    """Process editor-type registration questions and add them to context.

    Args:
        context: Context dictionary containing event and registration data

    """
    # add editor type questions using cached version
    questions = get_cached_registration_questions(context["event"])
    text_field_uuids = [str(q.uuid) for q in questions if q.typ == BaseQuestionType.EDITOR]

    cached_registration_fields = get_cache_registration_field(context["run"])
    for registration in context["registration_list"]:
        registration_uuid = str(registration.uuid)
        if registration_uuid not in cached_registration_fields:
            continue
        for field_uuid in text_field_uuids:
            if field_uuid not in cached_registration_fields[registration_uuid]:
                continue
            (is_redacted, line_number) = cached_registration_fields[registration_uuid][field_uuid]
            setattr(registration, field_uuid + "_red", is_redacted)
            setattr(registration, field_uuid + "_ln", line_number)


@login_required
def orga_registrations(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display and manage comprehensive event registration list for organizers.

    Provides detailed registration management interface with filtering, grouping,
    character assignments, ticket types, membership status, accounting info, and
    custom form responses. Supports CSV download and AJAX popup details.

    Args:
        request: HTTP request object with user authentication
        event_slug: Event/run slug identifier

    Returns:
        HttpResponse: Rendered registrations table template
        JsonResponse: AJAX popup content or download file on POST

    Side effects:
        - Caches character and registration data
        - Processes membership statuses for batch operations
        - Calculates accounting totals and payment status

    """
    # Verify user has permission to view registrations
    context = check_event_context(request, event_slug, "orga_registrations")

    # Handle AJAX and download POST requests
    if request.method == "POST":
        # Return popup detail view for specific registration/question
        if request.POST.get("popup") == "1":
            return registrations_popup(request, context)

        # Generate and return CSV download of all registrations
        if request.POST.get("download") == "1":
            return download(context, Registration, "registration")

    # Load all cached character, faction, and event data
    get_event_cache_all(context)

    # Prepare registration context with characters, tickets, and questions
    _orga_registrations_prepare(context)

    # Load discount information for all registered members
    _orga_registrations_discount(context)

    # Configure custom character fields if feature enabled
    _orga_registrations_custom_character(context)

    # Check if age-based question filtering is enabled
    context["registration_reg_que_age"] = get_event_config(
        context["event"].id,
        "registration_reg_que_age",
        default_value=False,
        context=context,
    )

    # Initialize registration grouping and list dictionaries
    context["reg_all"] = {}
    context["list_factions"] = {}

    # Query active (non-cancelled) registrations ordered by last update
    que = Registration.objects.filter(run=context["run"], cancellation_date__isnull=True).order_by("-updated")
    context["registration_list"] = que.select_related("member")

    # Batch-load membership statuses for all registered members
    context["memberships"] = {}
    if "membership" in context["features"]:
        members_id = [r.member_id for r in context["registration_list"]]
        # Create lookup dictionary for efficient membership access
        for el in Membership.objects.filter(association_id=context["association_id"], member_id__in=members_id):
            context["memberships"][el.member_id] = el

    # Process each registration to add computed fields
    for r in context["registration_list"]:
        # Add standard fields: characters, membership status, age
        _orga_registrations_standard(r, context)

        # Add discount information if available
        if "discount" in context["features"] and r.member_id in context["reg_discounts"]:
            r.discounts = context["reg_discounts"][r.member_id]

        # Add questbuilder trait information
        _orga_registrations_traits(r, context)

        # Categorize by ticket type and add to appropriate group
        _orga_registrations_tickets(r, context)

    # Sort registration groups for consistent display
    context["reg_all"] = sorted(context["reg_all"].items())

    # Process editor-type question responses for popup display
    _orga_registrations_text_fields(context)

    # Enable bulk upload functionality
    context["upload"] = "registrations"
    context["download"] = 1

    # Enable export view if configured
    if get_event_config(context["event"].id, "show_export", default_value=False, context=context):
        context["export"] = "registration"

    _load_preferences_columns(context)

    return render(request, "larpmanager/orga/registration/registrations.html", context)


def _load_preferences_columns(context: dict) -> None:
    """Load and configure column visibility preferences for registration list.

    Loads user's saved column visibility preferences from member configuration.
    If no preferences are set, automatically enables the ticket column by default.

    Args:
        context: Context dictionary containing member, event, and reg_questions data

    Side effects:
        Updates context["default_fields"] with JSON string of visible column selectors

    """
    # Load user's saved column visibility preferences
    default_fields_str = context["member"].get_config(f"open_registration_{context['event'].id}", default_value="[]")

    # Parse default fields, handling empty or invalid JSON
    # Replace single quotes with double quotes for valid JSON
    try:
        if default_fields_str and default_fields_str.strip():
            default_fields_str = default_fields_str.replace("'", '"')
            default_fields = json.loads(default_fields_str)
        else:
            default_fields = []
    except (json.JSONDecodeError, ValueError):
        default_fields = []

    # If user hasn't set preferences, automatically open ticket column by default
    if not default_fields:
        # Find the ticket question ID to add to default fields
        for question_uuid, question in context["reg_questions"].items():
            if question.typ == "ticket":
                default_fields.append(f".lq_{question_uuid}")
                break

    context["default_fields"] = json.dumps(default_fields)


@login_required
def orga_registrations_accounting(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Retrieve accounting data for event registrations."""
    context = check_event_context(request, event_slug, "orga_registrations")
    res = _orga_registrations_acc(context)
    return JsonResponse(res)


@login_required
def orga_registration_form_list(request: HttpRequest, event_slug: str) -> Any:  # noqa: C901 - Complex form list management with POST handling
    """Handle registration form list management for event organizers.

    Args:
        request: Django HTTP request object
        event_slug: Event slug identifier

    Returns:
        JsonResponse: Registration form data for organizer interface

    """
    context = check_event_context(request, event_slug, "orga_registrations")

    q_uuid = request.POST.get("q_uuid")

    q = RegistrationQuestion.objects
    if "reg_que_allowed" in context["features"]:
        q = q.annotate(allowed_map=ArrayAgg("allowed__id"))
    q = q.get(event=context["event"], uuid=q_uuid)

    if "reg_que_allowed" in context["features"] and q.allowed_map and q.allowed_map[0]:
        run_id = context["run"].id
        organizer = run_id in context["all_runs"] and 1 in context["all_runs"][run_id]
        if not organizer and context["member"].id not in q.allowed_map:
            return None

    res = {}
    popup = []

    max_length = 100

    if q.typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
        cho = {}
        for opt in RegistrationOption.objects.filter(question=q):
            cho[opt.id] = opt.get_form_text()

        for el in RegistrationChoice.objects.filter(question=q, registration__run=context["run"]).select_related(
            "registration"
        ):
            reg_uuid = str(el.registration.uuid)
            if reg_uuid not in res:
                res[reg_uuid] = []
            res[reg_uuid].append(cho[el.option_id])

    elif q.typ in [BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH]:
        que = RegistrationAnswer.objects.filter(question=q, registration__run=context["run"])
        que = que.annotate(short_text=Substr("text", 1, max_length))
        que = que.values("registration_id", "short_text", "registration__uuid")
        for el in que:
            answer = el["short_text"]
            if len(answer) == max_length:
                popup.append(el["registration__uuid"])
            res[el["registration__uuid"]] = answer

    return JsonResponse({"res": res, "popup": popup, "q_uuid": str(q.uuid)})


@login_required
def orga_registration_form_email(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Generate email lists for registration question choices in JSON format.

    Returns email addresses and names of registrants grouped by their
    answers to single or multiple choice registration questions.

    Args:
        request: HTTP request object containing POST data with question ID
        event_slug: Event slug identifier

    Returns:
        JsonResponse: Dictionary mapping choice names to lists of emails and names.
                     Format: {choice_name: {"emails": [...], "names": [...]}}
                     Returns empty response if question type is not single/multiple choice
                     or if user lacks permission.

    """
    # Check user permissions for accessing registration data
    context = check_event_context(request, event_slug, "orga_registrations")

    # Extract question ID from POST request
    q_uuid = request.POST.get("q_uuid")

    # Query registration question with optional allowed users annotation
    q = RegistrationQuestion.objects
    if "reg_que_allowed" in context["features"]:
        q = q.annotate(allowed_map=ArrayAgg("allowed__id"))
    q = q.get(event=context["event"], uuid=q_uuid)

    # Check if user has permission to access this specific question
    if "reg_que_allowed" in context["features"] and q.allowed_map and q.allowed_map[0]:
        run_id = context["run"].id
        organizer = run_id in context["all_runs"] and 1 in context["all_runs"][run_id]
        if not organizer and context["member"].id not in q.allowed_map:
            return None

    res = {}

    # Only process single or multiple choice questions
    if q.typ not in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
        return None

    # Build mapping of option IDs to option names
    cho = {}
    for opt in RegistrationOption.objects.filter(question=q):
        cho[opt.id] = opt.name

    # Query all choices for this question from active registrations
    que = RegistrationChoice.objects.filter(
        question=q, registration__run=context["run"], registration__cancellation_date__isnull=True
    )

    # Group emails and names by selected option
    for el in que.select_related("registration", "registration__member"):
        if el.option_id not in res:
            res[el.option_id] = {"emails": [], "names": []}
        res[el.option_id]["emails"].append(el.registration.member.email)
        res[el.option_id]["names"].append(el.registration.member.display_member())

    # Convert option IDs to option names in final result
    n_res = {}
    for opt_id, value in res.items():
        n_res[cho[opt_id]] = value

    return JsonResponse(n_res)


@login_required
def orga_registrations_new(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new registration for an event."""
    return orga_registrations_edit(request, event_slug, None)


@login_required
def orga_registrations_edit(request: HttpRequest, event_slug: str, registration_uuid: str) -> HttpResponse:
    """Edit or create a registration for an event.

    This function handles both creating new registrations (when num=0) and editing
    existing ones. It processes form submission, handles registration questions,
    and manages quest builder features if available.

    Args:
        request: The HTTP request object containing user data and form submission
        event_slug: Event/run identifier used to locate the specific event
        registration_uuid: Registration UUID - use "0" for creating new registration

    Returns:
        HttpResponse: Rendered registration edit form template or redirect response
                     to registration list on successful form submission

    Raises:
        Http404: If the event or registration (when num > 0) is not found
        PermissionDenied: If user lacks required event permissions

    """
    # Check user permissions and initialize context with event data
    context = check_event_context(request, event_slug, "orga_registrations")
    get_event_cache_all(context)

    # Set additional context flags for template rendering
    context["orga_characters"] = has_event_permission(request, context, context["event"].slug, "orga_characters")
    context["continue_add"] = "continue" in request.POST

    # Load existing registration if editing (num != 0)
    if registration_uuid:
        get_registration(context, registration_uuid)

    # Handle form submission (POST request)
    if request.method == "POST":
        # Initialize form with existing instance for editing or new instance for creation
        if registration_uuid:
            form = OrgaRegistrationForm(
                request.POST,
                instance=context["registration"],
                context=context,
                request=request,
            )
        else:
            form = OrgaRegistrationForm(request.POST, context=context)

        # Process valid form submission
        if form.is_valid():
            registration = form.save()

            # Handle registration deletion if requested
            if "delete" in request.POST and request.POST["delete"] == "1":
                cancel_reg(registration)
                messages.success(request, _("Registration cancelled"))
                return redirect("orga_registrations", event_slug=context["run"].get_slug())

            # Save registration-specific questions and answers
            form.save_registration_questions(registration)

            # Process quest builder data if feature is enabled
            if "questbuilder" in context["features"]:
                _save_questbuilder(context, form, registration)

            # Redirect based on user choice: continue adding or return to list
            if context["continue_add"]:
                return redirect("orga_registrations_new", context["run"].get_slug())

            return redirect("orga_registrations", event_slug=context["run"].get_slug())

    # Handle GET request: initialize form for display
    elif registration_uuid:
        # Load form with existing registration data for editing
        form = OrgaRegistrationForm(instance=context["registration"], context=context)
    else:
        # Create empty form for new registration
        form = OrgaRegistrationForm(context=context)

    # Prepare final context for template rendering
    context["form"] = form
    context["add_another"] = 1
    context["num"] = registration_uuid
    if registration_uuid:
        context["name"] = str(context["registration"].member)

    return render(request, "larpmanager/orga/edit.html", context)


@login_required
def orga_registrations_delete(request: HttpRequest, event_slug: str, registration_uuid: str) -> HttpResponse:
    """Delete registration for event - Handle as cancellation."""
    context = check_event_context(request, event_slug, "orga_registrations")

    get_registration(context, registration_uuid)

    cancel_reg(context["registration"])

    messages.success(request, _("Registration cancelled"))

    return redirect("orga_registrations", event_slug=context["run"].get_slug())


def _save_questbuilder(context: dict, form: object, registration: Any) -> None:
    """Save quest type assignments from questbuilder form.

    Args:
        context: Context dictionary containing event and run data
        form: Form containing quest type selections
        registration: Registration object for the member

    """
    for qt in QuestType.objects.filter(event=context["event"]):
        trait_uuid = form.cleaned_data.get(f"qt_{qt.uuid}")
        base_kwargs = {
            "run": context["run"],
            "member": registration.member,
            "typ": qt.number,
        }

        if not trait_uuid or trait_uuid == "0":
            AssignmentTrait.objects.filter(**base_kwargs).delete()
            continue

        trait = get_element_event(context, trait_uuid, Trait)
        AssignmentTrait.objects.update_or_create(
            **base_kwargs,
            defaults={"trait": trait},
        )


@login_required
def orga_registrations_customization(request: HttpRequest, event_slug: str, character_uuid: str) -> HttpResponse:
    """Handle organization customization of player registration character relationships.

    Args:
        request: HTTP request object
        event_slug: Event slug string
        character_uuid: Character uuid

    Returns:
        HttpResponse: Rendered edit form or redirect to registrations page

    """
    context = check_event_context(request, event_slug, "orga_registrations")
    get_event_cache_all(context)
    character = get_element_event(context, character_uuid, Character)
    rcr = RegistrationCharacterRel.objects.get(
        character_id=character.id,
        registration__run_id=context["run"].id,
        registration__cancellation_date__isnull=True,
    )

    if request.method == "POST":
        form = RegistrationCharacterRelForm(request.POST, context=context, instance=rcr)
        if form.is_valid():
            form.save()
            messages.success(request, _("Player customisation updated") + "!")
            return redirect("orga_registrations", event_slug=context["run"].get_slug())
    else:
        form = RegistrationCharacterRelForm(instance=rcr, context=context)

    context["form"] = form
    context["num"] = character_uuid
    context["name"] = character.name
    return render(request, "larpmanager/orga/edit.html", context)


@login_required
def orga_registrations_reload(request: HttpRequest, event_slug: str) -> HttpResponseRedirect:
    """Reload registrations for an event run by triggering background checks."""
    # Check user permissions for the event
    context = check_event_context(request, event_slug, "orga_registrations")

    # Collect all registration IDs for the current run
    registration_ids = [str(registration.id) for registration in Registration.objects.filter(run=context["run"])]

    # Trigger background registration checks
    check_registration_background(registration_ids)
    return redirect("orga_registrations", event_slug=context["run"].get_slug())


@login_required
def orga_registration_discounts(request: HttpRequest, event_slug: str, registration_uuid: str) -> HttpResponse:
    """Handle registration discounts management for organizers."""
    context = check_event_context(request, event_slug, "orga_registrations")
    get_registration(context, registration_uuid)

    # Get active discounts for this registration's member
    context["active"] = AccountingItemDiscount.objects.filter(run=context["run"], member=context["registration"].member)

    # Get all available discounts for this run
    context["available"] = context["run"].discounts.all()

    return render(request, "larpmanager/orga/registration/discounts.html", context)


@login_required
def orga_registration_discount_add(
    request: HttpRequest, event_slug: str, registration_uuid: str, discount_uuid: str
) -> Any:
    """Add a discount to a member's registration.

    Args:
        request: HTTP request object
        event_slug: Event slug
        registration_uuid: Registration UUID
        discount_uuid: Discount UUID

    Returns:
        HttpResponseRedirect: Redirect to registration discounts page

    """
    context = check_event_context(request, event_slug, "orga_registrations")
    get_registration(context, registration_uuid)
    get_discount(context, discount_uuid)
    AccountingItemDiscount.objects.create(
        value=context["discount"].value,
        member=context["registration"].member,
        disc=context["discount"],
        run=context["run"],
        association_id=context["association_id"],
    )
    context["registration"].save()
    return redirect(
        "orga_registration_discounts",
        event_slug=context["run"].get_slug(),
        registration_uuid=context["registration"].uuid,
    )


@login_required
def orga_registration_discount_del(
    request: HttpRequest, event_slug: str, registration_uuid: str, discount_uuid: str
) -> HttpResponse:
    """Delete a discount from a registration and redirect to discounts page."""
    # Check event permissions and get context
    context = check_event_context(request, event_slug, "orga_registrations")

    # Get the registration object
    get_registration(context, registration_uuid)
    get_discount(context, discount_uuid)

    # Delete the discount and save registration
    AccountingItemDiscount.objects.get(pk=context["discount"].id).delete()
    context["registration"].save()

    # Redirect to registration discounts page
    return redirect(
        "orga_registration_discounts",
        event_slug=context["run"].get_slug(),
        registration_uuid=context["registration"].uuid,
    )


@login_required
def orga_cancellations(request: HttpRequest, event_slug: str) -> Any:
    """Display cancelled registrations for event organizers.

    Args:
        request: Django HTTP request object
        event_slug: Event slug identifier

    Returns:
        HttpResponse: Rendered cancellations page with cancelled registration list

    """
    context = check_event_context(request, event_slug, "orga_cancellations")
    context["list"] = (
        Registration.objects.filter(run=context["run"])
        .exclude(cancellation_date__isnull=True)
        .order_by("-cancellation_date")
        .select_related("member")
    )
    regs_id = []
    members_map = {}
    for r in context["list"]:
        regs_id.append(r.id)
        members_map[r.member_id] = r.id

    payments = {}
    for el in AccountingItemPayment.objects.filter(member_id__in=members_map.keys(), registration__run=context["run"]):
        registration_id = members_map[el.member_id]
        if registration_id not in payments:
            payments[registration_id] = []
        payments[registration_id].append(el)

    refunds = {}
    for el in AccountingItemOther.objects.filter(run_id=context["run"].id, cancellation=True):
        registration_id = members_map[el.member_id]
        if registration_id not in refunds:
            refunds[registration_id] = []
        refunds[registration_id].append(el)

    # Check if payed, check if already approved reimburse
    for r in context["list"]:
        accounting_payments = None
        if r.id in payments:
            accounting_payments = payments[r.id]
        get_registration_payments(r, accounting_payments)

        r.accounting_refunds = None
        if r.id in refunds:
            r.accounting_refunds = refunds[r.id]
        get_accounting_refund(r)

        r.days = get_time_diff(context["run"].end, r.cancellation_date.date())
    return render(request, "larpmanager/orga/accounting/cancellations.html", context)


@login_required
def orga_cancellation_refund(request: HttpRequest, event_slug: str, registration_uuid: str) -> HttpResponse:
    """Handle cancellation refunds for tokens and credits.

    Processes refund requests for cancelled registrations, creating accounting
    entries for token and credit refunds and marking registration as refunded.

    Args:
        request: The HTTP request object containing user data and POST parameters
        event_slug: Event identifier string for the run
        registration_uuid: The registration uuid to process refund for

    Returns:
        HttpResponse: Redirect to cancellations page on POST success,
                     or rendered refund form template on GET

    Note:
        Creates AccountingItemOther entries for both token and credit refunds
        when amounts are greater than zero, then marks registration as refunded.

    """
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_cancellations")

    # Retrieve and validate the registration
    get_registration(context, registration_uuid)

    # Process refund form submission
    if request.method == "POST":
        # Extract refund amounts from form data
        try:
            ref_token = int(request.POST.get("inp_token", 0) or 0)
            ref_credit = int(request.POST.get("inp_credit", 0) or 0)
        except (ValueError, TypeError):
            ref_token = 0
            ref_credit = 0

        # Wrap refund operations in atomic transaction to prevent partial refunds
        with transaction.atomic():
            # Check if already refunded to prevent duplicate refunds
            if context["registration"].refunded:
                # Create token refund accounting entry if amount > 0
                if ref_token > 0:
                    AccountingItemOther.objects.get_or_create(
                        oth=OtherChoices.TOKEN,
                        run=context["run"],
                        descr="Refund",
                        member=context["registration"].member,
                        association_id=context["association_id"],
                        value=ref_token,
                        cancellation=True,
                        defaults={},
                    )

                # Create credit refund accounting entry if amount > 0
                if ref_credit > 0:
                    AccountingItemOther.objects.get_or_create(
                        oth=OtherChoices.CREDIT,
                        run=context["run"],
                        descr="Refund",
                        member=context["registration"].member,
                        association_id=context["association_id"],
                        value=ref_credit,
                        cancellation=True,
                        defaults={},
                    )

                # Mark registration as refunded and save changes
                context["registration"].refunded = True
                context["registration"].save()

        # Redirect back to cancellations overview
        return redirect("orga_cancellations", event_slug=context["run"].get_slug())

    # Get payment history for display in template
    get_registration_payments(context["registration"])

    # Render the refund form template
    return render(request, "larpmanager/orga/accounting/cancellation_refund.html", context)


def get_pre_registration(event: Any) -> dict[str, list | dict[int, int]]:
    """Get pre-registration data for an event.

    Args:
        event: The event to get pre-registration data for.

    Returns:
        Dictionary containing:
        - 'list': All pre-registrations for the event
        - 'pred': Pre-registrations from members who haven't signed up yet
        - Additional keys with preference counts

    """
    # Initialize result dictionary with empty lists
    result_data = {"list": [], "pred": []}

    # Get set of member IDs who have already registered for this event
    signed_member_ids = set(Registration.objects.filter(run__event=event).values_list("member_id", flat=True))

    # Get all pre-registrations ordered by preference and creation date
    pre_registrations = PreRegistration.objects.filter(event=event).order_by("pref", "created")

    # Process each pre-registration
    for pre_registration in pre_registrations.select_related("member"):
        # Check if member hasn't signed up yet
        if pre_registration.member_id not in signed_member_ids:
            result_data["pred"].append(pre_registration)
        else:
            # Mark as already signed up
            pre_registration.signed = True

        # Add to main list and count preferences
        result_data["list"].append(pre_registration)
        if pre_registration.pref not in result_data:
            result_data[pre_registration.pref] = 0
        result_data[pre_registration.pref] += 1

    return result_data


@login_required
def orga_pre_registrations(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Handle pre-registrations view for organization users."""
    # Check user permissions and get event context
    context = check_event_context(request, event_slug, "orga_pre_registrations")

    # Get pre-registration data for the event
    context["dc"] = get_pre_registration(context["event"])

    # Retrieve pre-registration preferences from association config
    context["preferences"] = get_association_config(
        context["association_id"], "pre_reg_preferences", default_value=False
    )

    return render(request, "larpmanager/orga/registration/pre_registrations.html", context)


def lottery_info(request: HttpRequest, context: dict) -> None:  # noqa: ARG001
    """Add lottery-related information to the context dictionary.

    Args:
        request: HTTP request object
        context: Context dictionary to update with lottery info

    """
    # Get number of lottery draws from event configuration
    context["num_draws"] = int(
        get_event_config(context["event"].id, "lottery_num_draws", default_value=0, context=context)
    )

    # Get lottery ticket configuration
    context["ticket"] = get_event_config(context["event"].id, "lottery_ticket", default_value="", context=context)

    # Count active lottery registrations
    context["num_lottery"] = Registration.objects.filter(
        run=context["run"],
        ticket__tier=TicketTier.LOTTERY,
        cancellation_date__isnull=True,
    ).count()

    # Count definitive (confirmed) registrations excluding special tiers
    context["num_def"] = (
        Registration.objects.filter(run=context["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.LOTTERY, TicketTier.STAFF, TicketTier.NPC, TicketTier.WAITING])
        .count()
    )


@login_required
def orga_lottery(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Manage registration lottery system for event organizers.

    This function handles the lottery process for event registrations, allowing organizers
    to randomly select participants from lottery tier registrations and upgrade them to
    a specific ticket tier.

    Args:
        request: HTTP request object containing POST data for lottery execution
        event_slug: Event slug identifier for the specific event

    Returns:
        HttpResponse: Rendered lottery template with either the lottery form or
                     results showing chosen registrations

    Raises:
        Http404: When lottery is already filled (no more spots available for upgrade)

    """
    # Check user permissions for lottery management
    context = check_event_context(request, event_slug, "orga_lottery")

    # Handle lottery execution when form is submitted
    if request.method == "POST" and request.POST.get("submit"):
        # Get current lottery statistics and context
        lottery_info(request, context)

        # Calculate how many registrations need to be upgraded
        to_upgrade = context["num_draws"] - context["num_def"]
        if to_upgrade <= 0:
            msg = "already filled!"
            raise Http404(msg)

        # Fetch all lottery tier registrations for this event run
        regs = Registration.objects.filter(run=context["run"], ticket__tier=TicketTier.LOTTERY)
        regs = list(regs)

        # Randomly shuffle and select registrations for upgrade
        shuffle(regs)
        chosen = regs[0:to_upgrade]

        # Get the target ticket for upgrading selected registrations
        ticket = get_object_or_404(RegistrationTicket, event=context["run"].event, name=context["ticket"])

        # Upgrade chosen registrations to the target ticket tier
        for el in chosen:
            el.ticket = ticket
            el.save()
            # TODO: Consider sending notification email to selected participants

        # Store chosen registrations in context for template display
        context["chosen"] = chosen

    # Refresh lottery information for template rendering
    lottery_info(request, context)
    return render(request, "larpmanager/orga/registration/lottery.html", context)


def calculate_age(date_of_birth: date, reference_date: date) -> int:
    """Calculate age in years between two dates."""
    return (
        reference_date.year
        - date_of_birth.year
        - ((reference_date.month, reference_date.day) < (date_of_birth.month, date_of_birth.day))
    )


@require_POST
def orga_registration_member(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Handle member registration actions from organizer interface.

    Processes member assignment to events and manages registration status
    changes including validation and permission checks.

    Args:
        request: The HTTP request object containing POST data with member ID
        event_slug: Event identifier string

    Returns:
        JsonResponse: Contains success status and member details HTML if successful,
                     or error status if member/registration not found

    Raises:
        ObjectDoesNotExist: When member or registration cannot be found

    """
    # Check organizer permissions for registration management
    context = check_event_context(request, event_slug, "orga_registrations")
    member_uuid = request.POST.get("mid")

    # Validate member existence
    try:
        member = Member.objects.get(uuid=member_uuid)
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    # Verify member has registration for this event
    try:
        Registration.objects.filter(member=member, run=context["run"]).first()
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    # Build member information HTML starting with name and profile
    text = f"<h2>{member.display_real()}</h2>"

    # Add profile image if available
    if member.profile:
        text += f"<img src='{member.profile_thumb.url}' style='width: 15em; margin: 1em; border-radius: 5%;' />"

    # Always include email address
    text += f"<p><b>Email</b>: {member.email}</p>"

    # Define fields to exclude from display based on permissions
    exclude = ["profile", "newsletter", "language", "presentation"]

    # Add sensitive data to exclusion list if user lacks permission
    if not has_event_permission(request, context, event_slug, "orga_sensitive"):
        exclude.extend(
            [
                "diet",
                "safety",
                "legal_name",
                "birth_date",
                "birth_place",
                "fiscal_code",
                "document_type",
                "document",
                "document_issued",
                "document_expiration",
                "accessibility",
                "residence_address",
            ],
        )

    # Process and display configured member fields
    member_cls: type[Member] = Member
    member_fields = sorted(context["members_fields"])
    member_field_correct(member, member_fields)

    # Iterate through each configured field and add to display
    for field_name in member_fields:
        if not field_name or field_name in exclude:
            continue

        # Get field metadata and value for display
        field_label = member_cls._meta.get_field(field_name).verbose_name  # noqa: SLF001  # Django model metadata
        value = getattr(member, field_name)

        # Only display fields with actual values
        if value:
            text += f"<p><b>{field_label}</b>: {value}</p>"

    return JsonResponse({"k": 1, "v": text})
