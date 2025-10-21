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
from larpmanager.cache.config import get_assoc_config, get_event_config
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
from larpmanager.utils.common import (
    get_char,
    get_discount,
    get_registration,
    get_time_diff,
)
from larpmanager.utils.download import _orga_registrations_acc, download
from larpmanager.utils.event import check_event_permission
from larpmanager.views.orga.member import member_field_correct


def check_time(times, step, start=None):
    """Record timing information for performance monitoring.

    Args:
        times: Dictionary to store timing data
        step: Current step name
        start: Start time reference

    Returns:
        float: Current time
    """
    if step not in times:
        times[step] = []
    now = time.time()
    times[step].append(now - start)
    return now


def _orga_registrations_traits(r, ctx):
    """Process and organize character traits for registration display.

    Args:
        r: Registration instance to process
        ctx: Context dictionary with traits and quest data
    """
    if "questbuilder" not in ctx["features"]:
        return

    r.traits = {}
    if not hasattr(r, "chars"):
        return
    for char in r.chars:
        if "traits" not in char:
            continue
        for tr_num in char["traits"]:
            trait = ctx["traits"][tr_num]
            quest = ctx["quests"][trait["quest"]]
            typ = ctx["quest_types"][quest["typ"]]
            typ_num = typ["number"]
            if typ_num not in r.traits:
                r.traits[typ_num] = []
            r.traits[typ_num].append(f"{quest['name']} - {trait['name']}")

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


def orga_registrations_membership(r, ctx):
    """Process membership status for registration display.

    Args:
        r: Registration instance
        ctx: Context dictionary with membership data
    """
    member = r.member
    if member.id in ctx["memberships"]:
        member.membership = ctx["memberships"][member.id]
    else:
        get_user_membership(member, ctx["a_id"])
    nm = member.membership.get_status_display()
    regs_list_add(ctx, "list_membership", nm, r.member)
    r.membership = member.membership.get_status_display


def regs_list_add(ctx, list, name, member):
    """Add member to categorized registration lists.

    Args:
        ctx: Context dictionary containing lists
        list: List key to add to
        name: Category name
        member: Member instance to add
    """
    key = slugify(name)
    if list not in ctx:
        ctx[list] = {}
    if key not in ctx[list]:
        ctx[list][key] = {"name": name, "emails": [], "players": []}
    if member.email not in ctx[list][key]["emails"]:
        ctx[list][key]["emails"].append(member.email)
        ctx[list][key]["players"].append(member.display_member())


def _orga_registrations_standard(reg, ctx):
    """Process standard registration data including characters and membership.

    Args:
        reg: Registration instance to process
        ctx: Context dictionary with event data
    """
    # skip if it is gift
    if reg.redeem_code:
        return

    regs_list_add(ctx, "list_all", "all", reg.member)

    _orga_registration_character(ctx, reg)

    # membership status
    if "membership" in ctx["features"]:
        orga_registrations_membership(reg, ctx)

    # age at run
    if ctx["registration_reg_que_age"]:
        if reg.member.birth_date and ctx["run"].start:
            reg.age = calculate_age(reg.member.birth_date, ctx["run"].start)


def _orga_registration_character(ctx, reg):
    """Process character data for registration including factions and customizations.

    Args:
        ctx: Context dictionary with character data
        reg: Registration instance to update
    """
    if reg.member_id not in ctx["reg_chars"]:
        return

    reg.factions = []
    reg.chars = ctx["reg_chars"][reg.member_id]
    for char in reg.chars:
        if "factions" in char:
            reg.factions.extend(char["factions"])
            for fnum in char["factions"]:
                if fnum in ctx["factions"]:
                    regs_list_add(ctx, "list_factions", ctx["factions"][fnum]["name"], reg.member)

        if "custom_character" in ctx["features"]:
            orga_registrations_custom(reg, ctx, char)

    if "custom_character" in ctx["features"] and reg.custom:
        for s in ctx["custom_info"]:
            if not reg.custom[s]:
                continue
            reg.custom[s] = ", ".join(reg.custom[s])


def orga_registrations_custom(r, ctx, char):
    """Process custom character information for registration.

    Args:
        r: Registration instance
        ctx: Context dictionary with custom field info
        char: Character data dictionary
    """
    if not hasattr(r, "custom"):
        r.custom = {}

    for s in ctx["custom_info"]:
        if s not in r.custom:
            r.custom[s] = []
        v = ""
        if s in char:
            v = char[s]
        if s == "profile" and v:
            v = f"<img src='{v}' class='reg_profile' />"
        if v:
            r.custom[s].append(v)


def registrations_popup(request, ctx):
    """Handle AJAX popup requests for registration details.

    Args:
        request: HTTP request with popup parameters
        ctx: Context dictionary with registration data

    Returns:
        dict: Response data for popup
    """
    idx = int(request.POST.get("idx", ""))
    tp = request.POST.get("tp", "")

    try:
        reg = Registration.objects.get(pk=idx, run=ctx["run"])
        question = RegistrationQuestion.objects.get(pk=tp, event=ctx["event"].get_class_parent(RegistrationQuestion))
        el = RegistrationAnswer.objects.get(reg=reg, question=question)
        tx = f"<h2>{reg} - {question.name}</h2>" + el.text
        return JsonResponse({"k": 1, "v": tx})
    except ObjectDoesNotExist:
        return JsonResponse({"k": 0})


def _orga_registrations_custom_character(ctx):
    """
    Prepare custom character information for registration display.

    Args:
        ctx: Context dictionary to populate with custom character info
    """
    if "custom_character" not in ctx["features"]:
        return
    ctx["custom_info"] = []
    for field in ["pronoun", "song", "public", "private", "profile"]:
        if not get_event_config(ctx["event"].id, "custom_character_" + field, False, ctx):
            continue
        ctx["custom_info"].append(field)


def _orga_registrations_prepare(ctx, request):
    """
    Prepare registration data including characters, tickets, and questions.

    Args:
        ctx: Context dictionary to populate with registration data
        request: HTTP request object
    """
    ctx["reg_chars"] = {}
    for _chnum, char in ctx["chars"].items():
        if "player_id" not in char:
            continue
        if char["player_id"] not in ctx["reg_chars"]:
            ctx["reg_chars"][char["player_id"]] = []
        ctx["reg_chars"][char["player_id"]].append(char)
    ctx["reg_tickets"] = {}
    for t in RegistrationTicket.objects.filter(event=ctx["event"]).order_by("-price"):
        t.emails = []
        ctx["reg_tickets"][t.id] = t
    ctx["reg_questions"] = _get_registration_fields(ctx, request.user.member)

    ctx["no_grouping"] = get_event_config(ctx["event"].id, "registration_no_grouping", False, ctx)


def _get_registration_fields(ctx: dict, member) -> dict:
    """Get registration questions available for a member in the given context.

    Filters registration questions based on event features and member permissions.
    If 'reg_que_allowed' feature is enabled, checks if the member has permission
    to see each question based on organizer status or explicit allowlist.

    Args:
        ctx: Context dictionary containing event, run, features, and all_runs data
        member: Member object to check permissions for

    Returns:
        Dictionary mapping question IDs to RegistrationQuestion objects that
        the member is allowed to see
    """
    reg_questions = {}

    # Get all registration questions for this event and feature set
    que = RegistrationQuestion.get_instance_questions(ctx["event"], ctx["features"])

    for q in que:
        # Check if question access control feature is enabled and question has restrictions
        if "reg_que_allowed" in ctx["features"] and q.allowed_map[0]:
            run_id = ctx["run"].id

            # Check if member is an organizer for this run
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


def _orga_registrations_text_fields(ctx):
    """Process editor-type registration questions and add them to context.

    Args:
        ctx: Context dictionary containing event and registration data
    """
    # add editor type questions
    text_fields = []
    que = RegistrationQuestion.objects.filter(event=ctx["event"])
    for que_id in que.filter(typ=BaseQuestionType.EDITOR).values_list("pk", flat=True):
        text_fields.append(str(que_id))

    gctf = get_cache_reg_field(ctx["run"])
    for el in ctx["reg_list"]:
        if el.id not in gctf:
            continue
        for f in text_fields:
            if f not in gctf[el.id]:
                continue
            (red, ln) = gctf[el.id][f]
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
    ctx["registration_reg_que_age"] = get_event_config(ctx["event"].id, "registration_reg_que_age", False, ctx)

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
    if get_event_config(ctx["event"].id, "show_export", False, ctx):
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
def orga_registrations_customization(request, s, num):
    """Handle organization customization of player registration character relationships.

    Args:
        request: HTTP request object
        s: Event slug string
        num: Character number identifier

    Returns:
        HttpResponse: Rendered edit form or redirect to registrations page
    """
    ctx = check_event_permission(request, s, "orga_registrations")
    get_event_cache_all(ctx)
    get_char(ctx, num)
    rcr = RegistrationCharacterRel.objects.get(
        character_id=ctx["character"].id, reg__run_id=ctx["run"].id, reg__cancellation_date__isnull=True
    )

    if request.method == "POST":
        form = RegistrationCharacterRelForm(request.POST, ctx=ctx, instance=rcr)
        if form.is_valid():
            form.save()
            messages.success(request, _("Player customisation updated") + "!")
            return redirect("orga_registrations", s=ctx["run"].get_slug())
    else:
        form = RegistrationCharacterRelForm(instance=rcr, ctx=ctx)

    ctx["form"] = form
    return render(request, "larpmanager/orga/edit.html", ctx)


@login_required
def orga_registrations_reload(request: HttpRequest, s: str) -> HttpResponseRedirect:
    """
    Reload registration data for an event by triggering background processing.

    Args:
        request: The HTTP request object containing user and session data
        s: The event slug identifier for permission checking and URL generation

    Returns:
        HTTP redirect to the organization registrations page for the event
    """
    # Check if user has permission to access organization registrations for this event
    ctx = check_event_permission(request, s, "orga_registrations")

    # Collect all registration IDs for the current event run
    reg_ids = []
    for reg in Registration.objects.filter(run=ctx["run"]):
        reg_ids.append(str(reg.id))

    # Trigger background processing for the collected registration IDs
    check_reg_bkg(reg_ids)

    # Redirect back to the organization registrations page
    return redirect("orga_registrations", s=ctx["run"].get_slug())


@login_required
def orga_registration_discounts(request: HttpRequest, s: str, num: int) -> HttpResponse:
    """
    Handle discount management for a specific registration in organization view.

    Args:
        request: The HTTP request object
        s: Event slug identifier
        num: Registration number identifier

    Returns:
        HttpResponse: Rendered template with discount context data
    """
    # Check user permissions for organization registration management
    ctx = check_event_permission(request, s, "orga_registrations")

    # Retrieve and validate the specific registration
    get_registration(ctx, num)

    # Get currently active discounts for this member and run
    ctx["active"] = AccountingItemDiscount.objects.filter(run=ctx["run"], member=ctx["registration"].member)

    # Get all available discounts for this run
    ctx["available"] = ctx["run"].discounts.all()

    # Render the discounts management template
    return render(request, "larpmanager/orga/registration/discounts.html", ctx)


@login_required
def orga_registration_discount_add(request, s, num, dis):
    """Add a discount to a member's registration.

    Args:
        request: HTTP request object
        s: Event slug
        num: Registration ID
        dis: Discount ID

    Returns:
        HttpResponseRedirect: Redirect to registration discounts page
    """
    ctx = check_event_permission(request, s, "orga_registrations")
    get_registration(ctx, num)
    get_discount(ctx, dis)
    AccountingItemDiscount.objects.create(
        value=ctx["discount"].value,
        member=ctx["registration"].member,
        disc=ctx["discount"],
        run=ctx["run"],
        assoc_id=ctx["a_id"],
    )
    ctx["registration"].save()
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


def get_pre_registration(event) -> dict[str, list | dict[str, int]]:
    """Get pre-registration data for an event.

    Args:
        event: The event object to get pre-registrations for.

    Returns:
        Dictionary containing:
            - 'list': All pre-registrations for the event
            - 'pred': Pre-registrations for members not yet signed up
            - preference counts: Count of pre-registrations by preference
    """
    dc = {"list": [], "pred": []}

    # Get set of member IDs who already have registrations for this event
    signed = set(Registration.objects.filter(run__event=event).values_list("member_id", flat=True))

    # Get all pre-registrations ordered by preference and creation date
    que = PreRegistration.objects.filter(event=event).order_by("pref", "created")

    # Process each pre-registration
    for p in que.select_related("member"):
        # Check if member hasn't signed up yet
        if p.member_id not in signed:
            dc["pred"].append(p)
        else:
            p.signed = True

        # Add to complete list and count preferences
        dc["list"].append(p)
        if p.pref not in dc:
            dc[p.pref] = 0
        dc[p.pref] += 1

    return dc


@login_required
def orga_pre_registrations(request: HttpRequest, s: str) -> HttpResponse:
    """
    Display pre-registrations for an event in the organization dashboard.

    This view handles the display of pre-registration data for event organizers,
    including user preferences for pre-registration management.

    Parameters
    ----------
    request : HttpRequest
        The HTTP request object containing user and session information
    s : str
        The event slug identifier used to identify the specific event

    Returns
    -------
    HttpResponse
        Rendered HTML response containing the pre-registrations template
        with event data and user preferences
    """
    # Check user permissions and get event context
    ctx = check_event_permission(request, s, "orga_pre_registrations")

    # Retrieve pre-registration data for the event
    ctx["dc"] = get_pre_registration(ctx["event"])

    # Get user preferences for pre-registration management
    ctx["preferences"] = get_assoc_config(request.assoc["id"], "pre_reg_preferences", False)

    # Render the pre-registrations template with context data
    return render(request, "larpmanager/orga/registration/pre_registrations.html", ctx)


@login_required
def orga_reload_cache(request: HttpRequest, s: str) -> HttpResponse:
    """Reset all cache entries for the specified event run.

    This function clears various cache layers including run-specific cache,
    media cache, event features cache, and registration counts cache to ensure
    data consistency after administrative changes.

    Args:
        request: The HTTP request object containing user session and metadata
        s: The event run slug identifier used for URL routing and cache keys

    Returns:
        HttpResponse: A redirect response to the event management page
    """
    # Verify user has permission to access this event and get context
    ctx = check_event_permission(request, s)

    # Clear run-specific cache and associated media files
    clear_run_cache_and_media(ctx["run"])
    reset_cache_run(ctx["event"].assoc_id, ctx["run"].get_slug())

    # Clear event-level cache entries for features and relationships
    clear_event_features_cache(ctx["event"].id)
    clear_run_event_links_cache(ctx["event"])

    # Clear registration and form field cache entries
    clear_registration_counts_cache(ctx["run"].id)
    clear_event_fields_cache(ctx["event"].id)
    clear_event_relationships_cache(ctx["event"].id)

    # Notify user of successful cache reset and redirect to management page
    messages.success(request, _("Cache reset!"))
    return redirect("manage", s=ctx["run"].get_slug())


def lottery_info(request, ctx: dict) -> None:
    """
    Populate context with lottery-related information for an event.

    This function enriches the provided context dictionary with lottery statistics
    including draw counts, ticket information, and registration numbers by tier.

    Args:
        request: The HTTP request object (unused but maintained for consistency)
        ctx: Context dictionary containing 'event' and 'run' keys that will be
            modified in-place with lottery information

    Returns:
        None: Modifies ctx dictionary in-place
    """
    # Get lottery configuration for number of draws and ticket type
    ctx["num_draws"] = int(get_event_config(ctx["event"].id, "lottery_num_draws", 0, ctx))
    ctx["ticket"] = get_event_config(ctx["event"].id, "lottery_ticket", "", ctx)

    # Count active lottery registrations (non-cancelled)
    ctx["num_lottery"] = Registration.objects.filter(
        run=ctx["run"],
        ticket__tier=TicketTier.LOTTERY,
        cancellation_date__isnull=True,
    ).count()

    # Count definitive registrations excluding special tiers
    ctx["num_def"] = (
        Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.LOTTERY, TicketTier.STAFF, TicketTier.NPC, TicketTier.WAITING])
        .count()
    )


@login_required
def orga_lottery(request: HttpRequest, s: str) -> HttpResponse:
    """Manage registration lottery system for event organizers.

    This function handles the lottery process for event registrations, allowing organizers
    to randomly select participants from lottery tier registrations and upgrade them to
    a specific ticket tier.

    Args:
        request: HTTP request object containing POST data for lottery execution
        s: Event slug identifier for the specific event

    Returns:
        HttpResponse: Rendered lottery template with either the lottery form or
                     results showing chosen registrations

    Raises:
        Http404: When lottery is already filled (no more spots available for upgrade)
    """
    # Check user permissions for lottery management
    ctx = check_event_permission(request, s, "orga_lottery")

    # Handle lottery execution when form is submitted
    if request.method == "POST" and request.POST.get("submit"):
        # Get current lottery statistics and context
        lottery_info(request, ctx)

        # Calculate how many registrations need to be upgraded
        to_upgrade = ctx["num_draws"] - ctx["num_def"]
        if to_upgrade <= 0:
            raise Http404("already filled!")

        # Fetch all lottery tier registrations for this event run
        regs = Registration.objects.filter(run=ctx["run"], ticket__tier=TicketTier.LOTTERY)
        regs = list(regs)

        # Randomly shuffle and select registrations for upgrade
        shuffle(regs)
        chosen = regs[0:to_upgrade]

        # Get the target ticket for upgrading selected registrations
        ticket = get_object_or_404(RegistrationTicket, event=ctx["run"].event, name=ctx["ticket"])

        # Upgrade chosen registrations to the target ticket tier
        for el in chosen:
            el.ticket = ticket
            el.save()
            # TODO: Consider sending notification email to selected participants

        # Store chosen registrations in context for template display
        ctx["chosen"] = chosen

    # Refresh lottery information for template rendering
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
