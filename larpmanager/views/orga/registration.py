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
from random import shuffle

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.functions import Substr
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from slugify import slugify

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.accounting.registration import (
    cancel_reg,
    check_reg_bkg,
    get_accounting_refund,
    get_reg_payments,
)
from larpmanager.cache.character import clear_run_cache_and_media, get_event_cache_all
from larpmanager.cache.config import get_assoc_config
from larpmanager.cache.feature import clear_event_features_cache
from larpmanager.cache.fields import clear_event_fields_cache
from larpmanager.cache.links import clear_run_event_links_cache
from larpmanager.cache.registration import clear_registration_counts_cache
from larpmanager.cache.rels import clear_event_relationships_cache
from larpmanager.cache.role import has_event_permission
from larpmanager.cache.run import reset_cache_run
from larpmanager.cache.text_fields import get_cache_reg_field
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
from larpmanager.models.casting import AssignmentTrait, QuestType
from larpmanager.models.event import Event, PreRegistration
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
from larpmanager.utils.common import (
    get_char,
    get_discount,
    get_registration,
    get_time_diff,
)
from larpmanager.utils.download import _orga_registrations_acc, download
from larpmanager.utils.event import check_event_permission
from larpmanager.views.orga.member import member_field_correct


def check_time(times: dict[str, list[float]], step: str, start: float | None = None) -> float:
    """Record timing information for performance monitoring.

    This function tracks execution times for different steps in a process by storing
    the elapsed time since a reference start time in a dictionary structure.

    Args:
        times (dict[str, list[float]]): Dictionary mapping step names to lists of timing measurements.
            Each step can have multiple timing records for statistical analysis.
        step (str): Name identifier for the current step being measured. Used as the key
            in the times dictionary.
        start (float | None, optional): Reference timestamp (from time.time()) to calculate
            elapsed time from. If None, timing calculation may produce unexpected results.
            Defaults to None.

    Returns:
        float: Current timestamp from time.time(), which can be used as the start
            parameter for subsequent timing measurements.

    Example:
        >>> times = {}
        >>> start_time = time.time()
        >>> current = check_time(times, "initialization", start_time)
        >>> check_time(times, "processing", current)
    """
    # Initialize step list if this is the first measurement for this step
    if step not in times:
        times[step] = []

    # Capture current timestamp for consistent timing
    now = time.time()

    # Calculate and store elapsed time since start reference
    times[step].append(now - start)

    # Return current time for use as next measurement's start reference
    return now


def _orga_registrations_traits(r: object, ctx: dict) -> None:
    """Process and organize character traits for registration display.

    Extracts character traits from registration data and organizes them by quest type
    for easier display in the registration interface. Only processes traits if the
    questbuilder feature is enabled.

    Args:
        r: Registration instance to process and modify with organized traits
        ctx: Context dictionary containing:
            - features: Available feature flags
            - traits: Dictionary mapping trait numbers to trait data
            - quests: Dictionary mapping quest numbers to quest data
            - quest_types: Dictionary mapping quest type numbers to type data

    Returns:
        None: Modifies the registration instance in-place by adding traits attribute
    """
    # Early return if questbuilder feature is not available
    if "questbuilder" not in ctx["features"]:
        return

    # Initialize traits dictionary for this registration
    r.traits = {}

    # Skip processing if registration has no character data
    if not hasattr(r, "chars"):
        return

    # Process each character in the registration
    for char in r.chars:
        # Skip characters without trait data
        if "traits" not in char:
            continue

        # Process each trait for the current character
        for tr_num in char["traits"]:
            # Get trait, quest, and quest type information from context
            trait = ctx["traits"][tr_num]
            quest = ctx["quests"][trait["quest"]]
            typ = ctx["quest_types"][quest["typ"]]
            typ_num = typ["number"]

            # Initialize trait list for this quest type if needed
            if typ_num not in r.traits:
                r.traits[typ_num] = []

            # Add formatted trait description to the appropriate type category
            r.traits[typ_num].append(f"{quest['name']} - {trait['name']}")

    # Convert trait lists to comma-separated strings for display
    for typ in r.traits:
        r.traits[typ] = ",".join(r.traits[typ])


def _orga_registrations_tickets(reg, ctx: dict) -> None:
    """Process registration ticket information and categorize by type.

    Analyzes a registration's ticket information and categorizes it based on ticket tier.
    Updates the context dictionary with registration counts and lists organized by type.
    Handles cases where tickets are missing or invalid, and respects grouping preferences.

    Args:
        reg: Registration instance to process, must have ticket_id and member attributes
        ctx: Context dictionary containing:
            - reg_tickets: Dictionary mapping ticket IDs to ticket objects
            - event: Event instance for provisional registration checks
            - features: Feature flags for registration validation
            - no_grouping: Boolean flag to disable ticket type grouping
            - reg_all: Dictionary to store categorized registration data
            - list_tickets: Dictionary for ticket name tracking

    Returns:
        None: Modifies ctx dictionary in-place
    """
    # Define default ticket type for participants
    default_typ = ("1", _("Participant"))

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
    typ = default_typ

    # Handle missing or invalid ticket references
    if not reg.ticket_id or reg.ticket_id not in ctx["reg_tickets"]:
        regs_list_add(ctx, "list_tickets", "e", reg.member)
    else:
        # Process valid ticket and determine registration type
        ticket = ctx["reg_tickets"][reg.ticket_id]
        regs_list_add(ctx, "list_tickets", ticket.name, reg.member)
        reg.ticket_show = ticket.name

        # Check for provisional status first, then map ticket tier to type
        if is_reg_provisional(reg, event=ctx["event"], features=ctx["features"]):
            typ = ("0", _("Provisional"))
        elif ticket.tier in ticket_types:
            typ = ticket_types[ticket.tier]

    # Ensure both default and current type categories exist in context
    for key in [default_typ, typ]:
        if key[0] not in ctx["reg_all"]:
            ctx["reg_all"][key[0]] = {"count": 0, "type": key[1], "list": []}

    # Increment count for the determined registration type
    ctx["reg_all"][typ[0]]["count"] += 1

    # Override grouping if disabled - all registrations go to default type
    if ctx["no_grouping"]:
        typ = default_typ

    # Add registration to the appropriate category list
    ctx["reg_all"][typ[0]]["list"].append(reg)


def orga_registrations_membership(r: Registration, ctx: dict) -> None:
    """Process membership status for registration display.

    Retrieves and processes membership information for a registration,
    adding the membership status to the context for display purposes.

    Args:
        r: Registration instance containing member information
        ctx: Context dictionary containing membership data and association ID
            Expected keys: 'memberships', 'a_id'

    Returns:
        None: Function modifies the registration object and context in-place
    """
    # Get the member associated with this registration
    member = r.member

    # Check if membership data is already cached in context
    if member.id in ctx["memberships"]:
        member.membership = ctx["memberships"][member.id]
    else:
        # Fetch membership data if not cached
        get_user_membership(member, ctx["a_id"])

    # Get the human-readable membership status
    nm = member.membership.get_status_display()

    # Add membership info to the context list for display
    regs_list_add(ctx, "list_membership", nm, r.member)

    # Store the membership status display method on the registration
    r.membership = member.membership.get_status_display


def regs_list_add(ctx: dict, list: str, name: str, member: Member) -> None:
    """Add member to categorized registration lists.

    Creates or updates a categorized list within the context dictionary,
    adding the member's email and display information if not already present.

    Args:
        ctx: Context dictionary containing categorized lists
        list: List key identifier to add the member to
        name: Category name for the registration list
        member: Member instance with email and display_member() method

    Returns:
        None: Modifies ctx dictionary in place
    """
    # Create slugified key for consistent categorization
    key = slugify(name)

    # Initialize list category if it doesn't exist
    if list not in ctx:
        ctx[list] = {}

    # Initialize specific category with empty structure
    if key not in ctx[list]:
        ctx[list][key] = {"name": name, "emails": [], "players": []}

    # Add member only if email not already present to avoid duplicates
    if member.email not in ctx[list][key]["emails"]:
        ctx[list][key]["emails"].append(member.email)
        ctx[list][key]["players"].append(member.display_member())


def _orga_registrations_standard(reg: Registration, ctx: dict) -> None:
    """Process standard registration data including characters and membership.

    Processes a registration instance by adding it to the appropriate lists,
    handling character data, membership status, and calculating age at run time.
    Gift registrations (with redeem codes) are skipped entirely.

    Args:
        reg: Registration instance to process
        ctx: Context dictionary containing event data, features, and configuration

    Returns:
        None
    """
    # Skip processing if this is a gift registration with a redeem code
    if reg.redeem_code:
        return

    # Add member to the main registration list for tracking
    regs_list_add(ctx, "list_all", "all", reg.member)

    # Process character-specific registration data
    _orga_registration_character(ctx, reg)

    # Handle membership status if membership feature is enabled
    if "membership" in ctx["features"]:
        orga_registrations_membership(reg, ctx)

    # Calculate member's age at the time of the run if age tracking is enabled
    if ctx["registration_reg_que_age"]:
        if reg.member.birth_date and ctx["run"].start:
            reg.age = calculate_age(reg.member.birth_date, ctx["run"].start)


def _orga_registration_character(ctx: dict, reg: Registration) -> None:
    """Process character data for registration including factions and customizations.

    Args:
        ctx: Context dictionary containing character data, features, factions,
             and custom_info configuration
        reg: Registration instance to update with character information

    Returns:
        None: Function modifies the registration instance in place
    """
    # Skip processing if member has no characters in context
    if reg.member_id not in ctx["reg_chars"]:
        return

    # Initialize factions list and get character data for this member
    reg.factions = []
    reg.chars = ctx["reg_chars"][reg.member_id]

    # Process each character for this registration
    for char in reg.chars:
        # Handle character faction assignments
        if "factions" in char:
            reg.factions.extend(char["factions"])
            for fnum in char["factions"]:
                if fnum in ctx["factions"]:
                    regs_list_add(ctx, "list_factions", ctx["factions"][fnum]["name"], reg.member)

        # Process custom character data if feature is enabled
        if "custom_character" in ctx["features"]:
            orga_registrations_custom(reg, ctx, char)

    # Finalize custom character information formatting
    if "custom_character" in ctx["features"] and reg.custom:
        for s in ctx["custom_info"]:
            # Skip empty custom fields
            if not reg.custom[s]:
                continue
            # Convert custom field lists to comma-separated strings
            reg.custom[s] = ", ".join(reg.custom[s])


def orga_registrations_custom(r: object, ctx: dict, char: dict) -> None:
    """Process custom character information for registration.

    Processes custom field information from character data and adds it to the
    registration's custom data structure. Handles special formatting for profile
    images by wrapping them in HTML img tags.

    Args:
        r: Registration instance that will store the custom data
        ctx: Context dictionary containing 'custom_info' list of field names
        char: Character data dictionary with field values to process

    Returns:
        None: Modifies the registration instance in-place
    """
    # Initialize custom data structure if it doesn't exist
    if not hasattr(r, "custom"):
        r.custom = {}

    # Process each custom field defined in the context
    for s in ctx["custom_info"]:
        # Initialize field list if not present
        if s not in r.custom:
            r.custom[s] = []

        # Extract value from character data, default to empty string
        v = ""
        if s in char:
            v = char[s]

        # Special handling for profile field - wrap in HTML img tag
        if s == "profile" and v:
            v = f"<img src='{v}' class='reg_profile' />"

        # Add non-empty values to the custom field list
        if v:
            r.custom[s].append(v)


def registrations_popup(request: HttpRequest, ctx: dict) -> JsonResponse:
    """Handle AJAX popup requests for registration details.

    Retrieves and formats registration answer data for display in a popup modal.
    Validates the registration belongs to the current run and the question belongs
    to the event before returning the formatted response.

    Args:
        request: HTTP request object containing POST data with 'idx' (registration ID)
                and 'tp' (question ID) parameters
        ctx: Context dictionary containing 'run' and 'event' objects for validation

    Returns:
        JsonResponse: Success response with formatted HTML content (k=1, v=html_string)
                     or error response (k=0) if objects don't exist or validation fails

    Raises:
        ValueError: If 'idx' parameter cannot be converted to integer
    """
    # Extract and validate request parameters
    idx = int(request.POST.get("idx", ""))
    tp = request.POST.get("tp", "")

    try:
        # Retrieve registration and validate it belongs to current run
        reg = Registration.objects.get(pk=idx, run=ctx["run"])

        # Retrieve question and validate it belongs to current event
        question = RegistrationQuestion.objects.get(pk=tp, event=ctx["event"].get_class_parent(RegistrationQuestion))

        # Get the specific answer for this registration and question
        el = RegistrationAnswer.objects.get(reg=reg, question=question)

        # Format response with registration info, question name, and answer text
        tx = f"<h2>{reg} - {question.name}</h2>" + el.text
        return JsonResponse({"k": 1, "v": tx})
    except ObjectDoesNotExist:
        # Return error response if any required object is not found
        return JsonResponse({"k": 0})


def _orga_registrations_custom_character(ctx: dict) -> None:
    """
    Prepare custom character information for registration display.

    Iterates through predefined character fields and adds those that are
    enabled in the event configuration to the context for template rendering.

    Args:
        ctx: Context dictionary containing event data and features.
             Will be modified to include 'custom_info' list if applicable.

    Returns:
        None: Modifies the ctx dictionary in place.
    """
    # Skip processing if custom character feature is not enabled
    if "custom_character" not in ctx["features"]:
        return

    # Initialize list to store enabled custom character fields
    ctx["custom_info"] = []

    # Check each predefined field and add to context if enabled in event config
    for field in ["pronoun", "song", "public", "private", "profile"]:
        # Skip field if not enabled in event configuration
        if not ctx["event"].get_config("custom_character_" + field, False):
            continue
        # Add enabled field to custom info list for template display
        ctx["custom_info"].append(field)


def _orga_registrations_prepare(ctx: dict, request: HttpRequest) -> None:
    """
    Prepare registration data including characters, tickets, and questions.

    This function populates the context dictionary with registration-related data
    needed for organizing event registrations, including character assignments,
    ticket information, and registration questions.

    Args:
        ctx (dict): Context dictionary to populate with registration data. Expected
                   to contain 'chars' and 'event' keys.
        request: HTTP request object containing user information and session data.

    Returns:
        None: Modifies the ctx dictionary in place.

    Side Effects:
        Modifies ctx dictionary by adding:
        - reg_chars: Dict mapping player IDs to their character lists
        - reg_tickets: Dict mapping ticket IDs to RegistrationTicket objects
        - reg_questions: Registration form fields for the current user
        - no_grouping: Boolean flag for registration grouping setting
    """
    # Initialize character mapping by player ID
    ctx["reg_chars"] = {}

    # Group characters by their associated player ID
    for _chnum, char in ctx["chars"].items():
        if "player_id" not in char:
            continue
        if char["player_id"] not in ctx["reg_chars"]:
            ctx["reg_chars"][char["player_id"]] = []
        ctx["reg_chars"][char["player_id"]].append(char)

    # Fetch and prepare registration tickets ordered by price (highest first)
    ctx["reg_tickets"] = {}
    for t in RegistrationTicket.objects.filter(event=ctx["event"]).order_by("-price"):
        # Initialize empty email list for each ticket
        t.emails = []
        ctx["reg_tickets"][t.id] = t

    # Get registration form fields specific to the current user
    ctx["reg_questions"] = _get_registration_fields(ctx, request.user.member)

    # Check if registration grouping is disabled for this event
    ctx["no_grouping"] = ctx["event"].get_config("registration_no_grouping", False)


def _get_registration_fields(ctx: dict, member: Member) -> dict:
    """Get registration questions available for a member in the current context.

    Args:
        ctx: Context dictionary containing event, features, run, and all_runs information
        member: Member object to check permissions for

    Returns:
        Dictionary mapping question IDs to RegistrationQuestion objects that the member
        can access based on feature flags and permission settings
    """
    reg_questions = {}

    # Get all questions for this event and feature set
    que = RegistrationQuestion.get_instance_questions(ctx["event"], ctx["features"])

    for q in que:
        # Check if question has restricted access and feature is enabled
        if "reg_que_allowed" in ctx["features"] and q.allowed_map[0]:
            run_id = ctx["run"].id

            # Check if user is an organizer for this run
            organizer = run_id in ctx["all_runs"] and 1 in ctx["all_runs"][run_id]

            # Skip question if member is not organizer and not in allowed list
            if not organizer and member.id not in q.allowed_map:
                continue

        # Add question to available questions
        reg_questions[q.id] = q

    return reg_questions


def _orga_registrations_discount(ctx):
    if "discount" not in ctx["features"]:
        return
    ctx["reg_discounts"] = {}
    que = AccountingItemDiscount.objects.filter(run=ctx["run"])
    for aid in que.select_related("member", "disc").exclude(hide=True):
        regs_list_add(ctx, "list_discount", aid.disc.name, aid.member)
        if aid.member_id not in ctx["reg_discounts"]:
            ctx["reg_discounts"][aid.member_id] = []
        ctx["reg_discounts"][aid.member_id].append(aid.disc.name)


def _orga_registrations_text_fields(ctx: dict) -> None:
    """Process editor-type registration questions and add them to context.

    Filters registration questions of type EDITOR for the event, retrieves cached
    field data, and dynamically adds reduced text and line count attributes to
    registration objects.

    Args:
        ctx: Context dictionary containing:
            - event: Event object to filter questions for
            - run: Run object for cache retrieval
            - reg_list: List of registration objects to process

    Returns:
        None: Modifies registration objects in ctx["reg_list"] in-place
    """
    # Collect editor-type question IDs as strings for field name matching
    text_fields = []
    que = RegistrationQuestion.objects.filter(event=ctx["event"])
    for que_id in que.filter(typ=BaseQuestionType.EDITOR).values_list("pk", flat=True):
        text_fields.append(str(que_id))

    # Get cached registration field data for this run
    gctf = get_cache_reg_field(ctx["run"])

    # Process each registration in the context list
    for el in ctx["reg_list"]:
        # Skip if registration has no cached field data
        if el.id not in gctf:
            continue

        # Add reduced text and line count attributes for each editor field
        for f in text_fields:
            if f not in gctf[el.id]:
                continue
            # Extract reduced text and line count from cache
            (red, ln) = gctf[el.id][f]
            # Dynamically set attributes: field_id + "_red" and field_id + "_ln"
            setattr(el, f + "_red", red)
            setattr(el, f + "_ln", ln)


@login_required
def orga_registrations(request: HttpRequest, s: str) -> HttpResponse:
    """Display and manage comprehensive event registration list for organizers.

    Provides detailed registration management interface with filtering, grouping,
    character assignments, ticket types, membership status, accounting info, and
    custom form responses. Supports CSV download and AJAX popup details.

    Args:
        request: HTTP request object with user authentication
        s: Event/run slug identifier

    Returns:
        HttpResponse: Rendered registrations table template
        JsonResponse: AJAX popup content or download file on POST

    Side effects:
        - Caches character and registration data
        - Processes membership statuses for batch operations
        - Calculates accounting totals and payment status
    """
    # Verify user has permission to view registrations
    ctx = check_event_permission(request, s, "orga_registrations")

    # Handle AJAX and download POST requests
    if request.method == "POST":
        # Return popup detail view for specific registration/question
        if request.POST.get("popup") == "1":
            return registrations_popup(request, ctx)

        # Generate and return CSV download of all registrations
        if request.POST.get("download") == "1":
            return download(ctx, Registration, "registration")

    # Load all cached character, faction, and event data
    get_event_cache_all(ctx)

    # Prepare registration context with characters, tickets, and questions
    _orga_registrations_prepare(ctx, request)

    # Load discount information for all registered members
    _orga_registrations_discount(ctx)

    # Configure custom character fields if feature enabled
    _orga_registrations_custom_character(ctx)

    # Check if age-based question filtering is enabled
    ctx["registration_reg_que_age"] = ctx["event"].get_config("registration_reg_que_age", False)

    # Initialize registration grouping dictionary
    ctx["reg_all"] = {}

    # Query active (non-cancelled) registrations ordered by last update
    que = Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True).order_by("-updated")
    ctx["reg_list"] = que.select_related("member")

    # Batch-load membership statuses for all registered members
    ctx["memberships"] = {}
    if "membership" in ctx["features"]:
        members_id = []
        for r in ctx["reg_list"]:
            members_id.append(r.member_id)
        # Create lookup dictionary for efficient membership access
        for el in Membership.objects.filter(assoc_id=ctx["a_id"], member_id__in=members_id):
            ctx["memberships"][el.member_id] = el

    # Process each registration to add computed fields
    for r in ctx["reg_list"]:
        # Add standard fields: characters, membership status, age
        _orga_registrations_standard(r, ctx)

        # Add discount information if available
        if "discount" in ctx["features"]:
            if r.member_id in ctx["reg_discounts"]:
                r.discounts = ctx["reg_discounts"][r.member_id]

        # Add questbuilder trait information
        _orga_registrations_traits(r, ctx)

        # Categorize by ticket type and add to appropriate group
        _orga_registrations_tickets(r, ctx)

    # Sort registration groups for consistent display
    ctx["reg_all"] = sorted(ctx["reg_all"].items())

    # Process editor-type question responses for popup display
    _orga_registrations_text_fields(ctx)

    # Enable bulk upload functionality
    ctx["upload"] = "registrations"
    ctx["download"] = 1
    # Enable export view if configured
    if ctx["event"].get_config("show_export", False):
        ctx["export"] = "registration"

    # Load user's saved column visibility preferences
    ctx["default_fields"] = request.user.member.get_config(f"open_registration_{ctx['event'].id}", "[]")

    return render(request, "larpmanager/orga/registration/registrations.html", ctx)


@login_required
def orga_registrations_accounting(request, s):
    ctx = check_event_permission(request, s, "orga_registrations")
    res = _orga_registrations_acc(ctx)
    return JsonResponse(res)


@login_required
def orga_registration_form_list(request, s):
    """Handle registration form list management for event organizers.

    Args:
        request: Django HTTP request object
        s: Event slug identifier

    Returns:
        JsonResponse: Registration form data for organizer interface
    """
    ctx = check_event_permission(request, s, "orga_registrations")

    eid = request.POST.get("num")

    q = RegistrationQuestion.objects
    if "reg_que_allowed" in ctx["features"]:
        q = q.annotate(allowed_map=ArrayAgg("allowed"))
    q = q.get(event=ctx["event"], pk=eid)

    if "reg_que_allowed" in ctx["features"] and q.allowed_map[0]:
        run_id = ctx["run"].id
        organizer = run_id in ctx["all_runs"] and 1 in ctx["all_runs"][run_id]
        if not organizer and request.user.member.id not in q.allowed_map:
            return

    res = {}
    popup = []

    max_length = 100

    if q.typ in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
        cho = {}
        for opt in RegistrationOption.objects.filter(question=q):
            cho[opt.id] = opt.get_form_text()

        for el in RegistrationChoice.objects.filter(question=q, reg__run=ctx["run"]):
            if el.reg_id not in res:
                res[el.reg_id] = []
            res[el.reg_id].append(cho[el.option_id])

    elif q.typ in [BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH]:
        que = RegistrationAnswer.objects.filter(question=q, reg__run=ctx["run"])
        que = que.annotate(short_text=Substr("text", 1, max_length))
        que = que.values("reg_id", "short_text")
        for el in que:
            answer = el["short_text"]
            if len(answer) == max_length:
                popup.append(el["reg_id"])
            res[el["reg_id"]] = answer

    return JsonResponse({"res": res, "popup": popup, "num": q.id})


@login_required
def orga_registration_form_email(request: HttpRequest, s: str) -> JsonResponse:
    """Generate email lists for registration question choices in JSON format.

    Returns email addresses and names of registrants grouped by their
    answers to single or multiple choice registration questions.

    Args:
        request: HTTP request object containing POST data with question ID
        s: Event slug identifier

    Returns:
        JsonResponse: Dictionary mapping choice names to lists of emails and names.
                     Format: {choice_name: {"emails": [...], "names": [...]}}
                     Returns empty response if question type is not single/multiple choice
                     or if user lacks permission.
    """
    # Check user permissions for accessing registration data
    ctx = check_event_permission(request, s, "orga_registrations")

    # Extract question ID from POST request
    eid = request.POST.get("num")

    # Query registration question with optional allowed users annotation
    q = RegistrationQuestion.objects
    if "reg_que_allowed" in ctx["features"]:
        q = q.annotate(allowed_map=ArrayAgg("allowed"))
    q = q.get(event=ctx["event"], pk=eid)

    # Check if user has permission to access this specific question
    if "reg_que_allowed" in ctx["features"] and q.allowed_map[0]:
        run_id = ctx["run"].id
        organizer = run_id in ctx["all_runs"] and 1 in ctx["all_runs"][run_id]
        if not organizer and request.user.member.id not in q.allowed_map:
            return

    res = {}

    # Only process single or multiple choice questions
    if q.typ not in [BaseQuestionType.SINGLE, BaseQuestionType.MULTIPLE]:
        return

    # Build mapping of option IDs to option names
    cho = {}
    for opt in RegistrationOption.objects.filter(question=q):
        cho[opt.id] = opt.name

    # Query all choices for this question from active registrations
    que = RegistrationChoice.objects.filter(question=q, reg__run=ctx["run"], reg__cancellation_date__isnull=True)

    # Group emails and names by selected option
    for el in que.select_related("reg", "reg__member"):
        if el.option_id not in res:
            res[el.option_id] = {"emails": [], "names": []}
        res[el.option_id]["emails"].append(el.reg.member.email)
        res[el.option_id]["names"].append(el.reg.member.display_member())

    # Convert option IDs to option names in final result
    n_res = {}
    for opt_id, value in res.items():
        n_res[cho[opt_id]] = value

    return JsonResponse(n_res)


@login_required
def orga_registrations_edit(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Edit or create a registration for an event.

    This function handles both creating new registrations (when num=0) and editing
    existing ones. It processes form submission, handles registration questions,
    and manages quest builder features if available.

    Args:
        request: The HTTP request object containing user data and form submission
        s: Event/run identifier used to locate the specific event
        num: Registration ID - use 0 for creating new registration,
             positive integer for editing existing registration

    Returns:
        HttpResponse: Rendered registration edit form template or redirect response
                     to registration list on successful form submission

    Raises:
        Http404: If the event or registration (when num > 0) is not found
        PermissionDenied: If user lacks required event permissions
    """
    # Check user permissions and initialize context with event data
    ctx = check_event_permission(request, s, "orga_registrations")
    get_event_cache_all(ctx)

    # Set additional context flags for template rendering
    ctx["orga_characters"] = has_event_permission(request, ctx, ctx["event"].slug, "orga_characters")
    ctx["continue_add"] = "continue" in request.POST

    # Load existing registration if editing (num != 0)
    if num != 0:
        get_registration(ctx, num)

    # Handle form submission (POST request)
    if request.method == "POST":
        # Initialize form with existing instance for editing or new instance for creation
        if num != 0:
            form = OrgaRegistrationForm(request.POST, instance=ctx["registration"], ctx=ctx, request=request)
        else:
            form = OrgaRegistrationForm(request.POST, ctx=ctx)

        # Process valid form submission
        if form.is_valid():
            reg = form.save()

            # Handle registration deletion if requested
            if "delete" in request.POST and request.POST["delete"] == "1":
                cancel_reg(reg)
                messages.success(request, _("Registration cancelled"))
                return redirect("orga_registrations", s=ctx["run"].get_slug())

            # Save registration-specific questions and answers
            form.save_reg_questions(reg)

            # Process quest builder data if feature is enabled
            if "questbuilder" in ctx["features"]:
                _save_questbuilder(ctx, form, reg)

            # Redirect based on user choice: continue adding or return to list
            if ctx["continue_add"]:
                return redirect("orga_registrations_edit", s=ctx["run"].get_slug(), num=0)

            return redirect("orga_registrations", s=ctx["run"].get_slug())

    # Handle GET request: initialize form for display
    elif num != 0:
        # Load form with existing registration data for editing
        form = OrgaRegistrationForm(instance=ctx["registration"], ctx=ctx)
    else:
        # Create empty form for new registration
        form = OrgaRegistrationForm(ctx=ctx)

    # Prepare final context for template rendering
    ctx["form"] = form
    ctx["add_another"] = 1

    return render(request, "larpmanager/orga/edit.html", ctx)


def _save_questbuilder(ctx, form, reg):
    """Save quest type assignments from questbuilder form.

    Args:
        ctx: Context dictionary containing event and run data
        form: Form containing quest type selections
        reg: Registration object for the member
    """
    for qt in QuestType.objects.filter(event=ctx["event"]):
        qt_id = f"qt_{qt.number}"
        tid = int(form.cleaned_data[qt_id])
        base_kwargs = {"run": ctx["run"], "member": reg.member, "typ": qt.number}

        if tid:
            ait = AssignmentTrait.objects.filter(**base_kwargs).first()

            if ait and ait.trait_id != tid:
                ait.delete()
                ait = None

            if not ait:
                AssignmentTrait.objects.create(**base_kwargs, trait_id=tid)
        else:
            AssignmentTrait.objects.filter(**base_kwargs).delete()


@login_required
def orga_registrations_customization(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """Handle organization customization of player registration character relationships.

    This view allows organization administrators to customize player registration
    character relationships for a specific event run. It provides a form interface
    for editing registration character relationship data.

    Args:
        request: The HTTP request object containing user data and method information
        s: The event slug string used to identify the specific event
        num: The character number identifier used to locate the specific character

    Returns:
        HttpResponse: Either a rendered edit form template for GET requests or
                     a redirect to the registrations page after successful POST

    Raises:
        Http404: If the character or registration relationship is not found
        PermissionDenied: If user lacks permission to access organization registrations
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_registrations")

    # Load event-related data into context
    get_event_cache_all(ctx)
    get_char(ctx, num)

    # Retrieve the registration character relationship for this character and run
    rcr = RegistrationCharacterRel.objects.get(
        character_id=ctx["character"].id, reg__run_id=ctx["run"].id, reg__cancellation_date__isnull=True
    )

    # Handle form submission for updating registration data
    if request.method == "POST":
        form = RegistrationCharacterRelForm(request.POST, ctx=ctx, instance=rcr)

        # Validate and save form data if valid
        if form.is_valid():
            form.save()
            messages.success(request, _("Player customisation updated") + "!")
            return redirect("orga_registrations", s=ctx["run"].get_slug())
    else:
        # Create form instance for GET requests
        form = RegistrationCharacterRelForm(instance=rcr, ctx=ctx)

    # Add form to context and render edit template
    ctx["form"] = form
    return render(request, "larpmanager/orga/edit.html", ctx)


@login_required
def orga_registrations_reload(request, s):
    ctx = check_event_permission(request, s, "orga_registrations")
    reg_ids = []
    for reg in Registration.objects.filter(run=ctx["run"]):
        reg_ids.append(str(reg.id))
    check_reg_bkg(reg_ids)
    # print(f"@@@@ orga_registrations_reload {request} {datetime.now()}")
    return redirect("orga_registrations", s=ctx["run"].get_slug())


@login_required
def orga_registration_discounts(request, s, num):
    ctx = check_event_permission(request, s, "orga_registrations")
    get_registration(ctx, num)
    # get active discounts
    ctx["active"] = AccountingItemDiscount.objects.filter(run=ctx["run"], member=ctx["registration"].member)
    # get available discounts
    ctx["available"] = ctx["run"].discounts.all()
    return render(request, "larpmanager/orga/registration/discounts.html", ctx)


@login_required
def orga_registration_discount_add(request: HttpRequest, s: str, num: int, dis: int) -> HttpResponseRedirect:
    """Add a discount to a member's registration.

    Applies a discount to a specific registration by creating an AccountingItemDiscount
    object with the discount value and associating it with the member and event run.

    Args:
        request: The HTTP request object containing user and session information.
        s: Event slug identifier used to locate the specific event.
        num: Registration ID to identify which registration receives the discount.
        dis: Discount ID to identify which discount to apply.

    Returns:
        HttpResponseRedirect: Redirects to the registration discounts management page
            for the specified registration.

    Raises:
        PermissionDenied: If user lacks 'orga_registrations' permission for the event.
        Http404: If registration or discount with given IDs don't exist.
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_registrations")

    # Retrieve and validate registration exists
    get_registration(ctx, num)

    # Retrieve and validate discount exists
    get_discount(ctx, dis)

    # Create the discount item linking member, discount, and event run
    AccountingItemDiscount.objects.create(
        value=ctx["discount"].value,
        member=ctx["registration"].member,
        disc=ctx["discount"],
        run=ctx["run"],
        assoc_id=ctx["a_id"],
    )

    # Save registration to trigger any model signals/updates
    ctx["registration"].save()

    # Redirect to registration discounts management page
    return redirect(
        "orga_registration_discounts",
        s=ctx["run"].get_slug(),
        num=ctx["registration"].id,
    )


@login_required
def orga_registration_discount_del(request, s, num, dis):
    ctx = check_event_permission(request, s, "orga_registrations")
    get_registration(ctx, num)
    AccountingItemDiscount.objects.get(pk=dis).delete()
    ctx["registration"].save()
    return redirect(
        "orga_registration_discounts",
        s=ctx["run"].get_slug(),
        num=ctx["registration"].id,
    )


@login_required
def orga_cancellations(request, s):
    """Display cancelled registrations for event organizers.

    Args:
        request: Django HTTP request object
        s: Event slug identifier

    Returns:
        HttpResponse: Rendered cancellations page with cancelled registration list
    """
    ctx = check_event_permission(request, s, "orga_cancellations")
    ctx["list"] = (
        Registration.objects.filter(run=ctx["run"])
        .exclude(cancellation_date__isnull=True)
        .order_by("-cancellation_date")
        .select_related("member")
    )
    regs_id = []
    members_map = {}
    for r in ctx["list"]:
        regs_id.append(r.id)
        members_map[r.member_id] = r.id

    payments = {}
    for el in AccountingItemPayment.objects.filter(member_id__in=members_map.keys(), reg__run=ctx["run"]):
        reg_id = members_map[el.member_id]
        if reg_id not in payments:
            payments[reg_id] = []
        payments[reg_id].append(el)

    refunds = {}
    for el in AccountingItemOther.objects.filter(run_id=ctx["run"].id, cancellation=True):
        reg_id = members_map[el.member_id]
        if reg_id not in refunds:
            refunds[reg_id] = []
        refunds[reg_id].append(el)

    # Check if payed, check if already approved reimburse
    for r in ctx["list"]:
        acc_payments = None
        if r.id in payments:
            acc_payments = payments[r.id]
        get_reg_payments(r, acc_payments)

        r.acc_refunds = None
        if r.id in refunds:
            r.acc_refunds = refunds[r.id]
        get_accounting_refund(r)

        r.days = get_time_diff(ctx["run"].end, r.cancellation_date.date())
    return render(request, "larpmanager/orga/accounting/cancellations.html", ctx)


@login_required
def orga_cancellation_refund(request, s: str, num: str) -> HttpResponse:
    """Handle cancellation refunds for tokens and credits.

    Processes refund requests for cancelled registrations, creating accounting
    entries for token and credit refunds and marking registration as refunded.

    Args:
        request: The HTTP request object containing user data and POST parameters
        s: The event slug identifier for the run
        num: The registration number to process refund for

    Returns:
        HttpResponse: Redirect to cancellations page on POST success,
                     or rendered refund form template on GET

    Note:
        Creates AccountingItemOther entries for both token and credit refunds
        when amounts are greater than zero, then marks registration as refunded.
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_cancellations")

    # Retrieve and validate the registration
    get_registration(ctx, num)

    # Process refund form submission
    if request.method == "POST":
        # Extract refund amounts from form data
        ref_token = int(request.POST["inp_token"])
        ref_credit = int(request.POST["inp_credit"])

        # Create token refund accounting entry if amount > 0
        if ref_token > 0:
            AccountingItemOther.objects.create(
                oth=OtherChoices.TOKEN,
                run=ctx["run"],
                descr="Refund",
                member=ctx["registration"].member,
                assoc_id=ctx["a_id"],
                value=ref_token,
                cancellation=True,
            )

        # Create credit refund accounting entry if amount > 0
        if ref_credit > 0:
            AccountingItemOther.objects.create(
                oth=OtherChoices.CREDIT,
                run=ctx["run"],
                descr="Refund",
                member=ctx["registration"].member,
                assoc_id=ctx["a_id"],
                value=ref_credit,
                cancellation=True,
            )

        # Mark registration as refunded and save changes
        ctx["registration"].refunded = True
        ctx["registration"].save()

        # Redirect back to cancellations overview
        return redirect("orga_cancellations", s=ctx["run"].get_slug())

    # Get payment history for display in template
    get_reg_payments(ctx["registration"])

    # Render the refund form template
    return render(request, "larpmanager/orga/accounting/cancellation_refund.html", ctx)


def get_pre_registration(event: Event) -> dict[str, list | int]:
    """Get pre-registration data with signed status and preference counts.

    Args:
        event: The event object to get pre-registrations for.

    Returns:
        Dictionary containing:
            - "list": All pre-registrations for the event
            - "pred": Pre-registrations for members not yet signed up
            - preference values: Count of pre-registrations per preference
    """
    # Initialize result dictionary with empty lists
    dc = {"list": [], "pred": []}

    # Get set of member IDs who have already registered for this event
    signed = set(Registration.objects.filter(run__event=event).values_list("member_id", flat=True))

    # Query pre-registrations ordered by preference and creation date
    que = PreRegistration.objects.filter(event=event).order_by("pref", "created")

    # Process each pre-registration with related member data
    for p in que.select_related("member"):
        # Check if member hasn't signed up yet and add to pred list
        if p.member_id not in signed:
            dc["pred"].append(p)
        else:
            # Mark as signed for template usage
            p.signed = True

        # Add to main list and count preferences
        dc["list"].append(p)
        if p.pref not in dc:
            dc[p.pref] = 0
        dc[p.pref] += 1

    return dc


@login_required
def orga_pre_registrations(request, s):
    ctx = check_event_permission(request, s, "orga_pre_registrations")
    ctx["dc"] = get_pre_registration(ctx["event"])

    ctx["preferences"] = get_assoc_config(request.assoc["id"], "pre_reg_preferences", False)

    return render(request, "larpmanager/orga/registration/pre_registrations.html", ctx)


@login_required
def orga_reload_cache(request: HttpRequest, s: str) -> HttpResponse:
    """Reset all cache entries for a specific event run.

    This function clears various cache layers including run cache, media cache,
    event features, registration counts, and relationship caches to ensure
    fresh data is loaded for the event management interface.

    Args:
        request: The HTTP request object containing user and session data.
        s: The event run slug identifier used to locate the specific run.

    Returns:
        HttpResponse: Redirect response to the manage page for the event run.

    Raises:
        PermissionDenied: If user lacks permission to access the event.
        Http404: If the event run with the given slug doesn't exist.
    """
    # Verify user permissions and get event context
    ctx = check_event_permission(request, s)

    # Clear run-specific cache and associated media files
    clear_run_cache_and_media(ctx["run"])
    reset_cache_run(ctx["event"].assoc_id, ctx["run"].get_slug())

    # Clear event-level cache entries for features and configuration
    clear_event_features_cache(ctx["event"].id)
    clear_run_event_links_cache(ctx["event"])

    # Clear registration and relationship cache data
    clear_registration_counts_cache(ctx["run"].id)
    clear_event_fields_cache(ctx["event"].id)
    clear_event_relationships_cache(ctx["event"].id)

    # Notify user of successful cache reset and redirect
    messages.success(request, _("Cache reset!"))
    return redirect("manage", s=ctx["run"].get_slug())


def lottery_info(request, ctx):
    ctx["num_draws"] = int(ctx["event"].get_config("lottery_num_draws", 0))
    ctx["ticket"] = ctx["event"].get_config("lottery_ticket", "")
    ctx["num_lottery"] = Registration.objects.filter(
        run=ctx["run"],
        ticket__tier=TicketTier.LOTTERY,
        cancellation_date__isnull=True,
    ).count()
    ctx["num_def"] = (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.LOTTERY, TicketTier.STAFF, TicketTier.NPC, TicketTier.WAITING])
        .count()
    )


@login_required
def orga_lottery(request: HttpRequest, s: str) -> HttpResponse:
    """Manage registration lottery system for event organizers.

    Handles the lottery process for event registrations, allowing organizers to
    randomly select participants from lottery ticket holders and upgrade them
    to definitive tickets.

    Args:
        request: HTTP request object containing POST data for lottery execution
        s: Event slug identifier for the target event

    Returns:
        HttpResponse: Rendered lottery template with chosen registrations or form

    Raises:
        Http404: When lottery slots are already filled (no upgrades needed)
    """
    # Check organizer permissions for lottery management
    ctx = check_event_permission(request, s, "orga_lottery")

    # Process lottery execution if form submitted
    if request.method == "POST" and request.POST.get("submit"):
        lottery_info(request, ctx)
        to_upgrade = ctx["num_draws"] - ctx["num_def"]

        # Validate lottery capacity - ensure slots available for upgrade
        if to_upgrade <= 0:
            raise Http404("already filled!")

        # Retrieve all lottery registrations for random selection
        regs = Registration.objects.filter(run=ctx["run"], ticket__tier=TicketTier.LOTTERY)
        regs = list(regs)

        # Perform random shuffle and select winners
        shuffle(regs)
        chosen = regs[0:to_upgrade]

        # Get target ticket for upgrades
        ticket = get_object_or_404(RegistrationTicket, event=ctx["run"].event, name=ctx["ticket"])

        # Upgrade chosen registrations to definitive tickets
        for el in chosen:
            el.ticket = ticket
            el.save()
            # send mail?

        # Store chosen registrations in context for display
        ctx["chosen"] = chosen

    # Refresh lottery information and render response
    lottery_info(request, ctx)
    return render(request, "larpmanager/orga/registration/lottery.html", ctx)


def calculate_age(born, today):
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


@require_POST
def orga_registration_member(request: HttpRequest, s: str) -> JsonResponse:
    """Handle member registration actions from organizer interface.

    Processes member assignment to events and manages registration status
    changes including validation and permission checks.

    Args:
        request: The HTTP request object containing POST data with member ID
        s: The event slug identifier

    Returns:
        JsonResponse: Contains success status and member details HTML if successful,
                     or error status if member/registration not found

    Raises:
        ObjectDoesNotExist: When member or registration cannot be found
    """
    # Check organizer permissions for registration management
    ctx = check_event_permission(request, s, "orga_registrations")
    member_id = request.POST.get("mid")

    # Validate member existence
    try:
        member = Member.objects.get(pk=member_id)
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})

    # Verify member has registration for this event
    try:
        Registration.objects.filter(member=member, run=ctx["run"]).first()
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
    if not has_event_permission(request, ctx, s, "orga_sensitive"):
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
            ]
        )

    # Process and display configured member fields
    member_cls: type[Member] = Member
    member_fields = sorted(request.assoc["members_fields"])
    member_field_correct(member, member_fields)

    # Iterate through each configured field and add to display
    for field_name in member_fields:
        if not field_name or field_name in exclude:
            continue

        # Get field metadata and value for display
        field_label = member_cls._meta.get_field(field_name).verbose_name
        value = getattr(member, field_name)

        # Only display fields with actual values
        if value:
            text += f"<p><b>{field_label}</b>: {value}</p>"

    return JsonResponse({"k": 1, "v": text})
