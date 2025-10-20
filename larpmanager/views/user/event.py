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

import json
from datetime import datetime, timedelta
from typing import Union

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.character import (
    get_event_cache_all,
    get_writing_element_fields,
)
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.fields import visible_writing_fields
from larpmanager.cache.registration import get_reg_counts
from larpmanager.models.accounting import PaymentInvoice, PaymentType
from larpmanager.models.association import AssocTextType
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import (
    DevelopStatus,
    Event,
    EventTextType,
    PreRegistration,
    Run,
)
from larpmanager.models.form import (
    QuestionApplicable,
    RegistrationOption,
    _get_writing_mapping,
)
from larpmanager.models.member import MembershipStatus, get_user_membership
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.writing import (
    Character,
    CharacterStatus,
    Faction,
    FactionType,
)
from larpmanager.utils.auth import is_lm_admin
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.common import get_element
from larpmanager.utils.event import get_event, get_event_run
from larpmanager.utils.exceptions import HiddenError
from larpmanager.utils.registration import registration_status
from larpmanager.utils.text import get_assoc_text, get_event_text


def calendar(request: HttpRequest, lang: str) -> HttpResponse:
    """Display the event calendar with open and future runs for an association.

    This function retrieves upcoming runs for an association, checks user registration status,
    and categorizes runs into 'open' (available for registration) and 'future' (not yet open).
    It also filters runs based on development status and user permissions.

    Args:
        request: HTTP request object containing user and association data. Must include
                'assoc' key with association information and authenticated user data.
        lang: Language code for filtering events by language preference.

    Returns:
        HttpResponse: Rendered calendar template containing:
            - open: List of runs open for registration
            - future: List of future runs not yet open
            - langs: Available language options
            - custom_text: Association-specific homepage text
            - my_reg: User's registration status for each run (if authenticated)

    Note:
        Authenticated users see runs they're registered for even if in START development status.
        Anonymous users cannot see START status runs at all.
    """
    # Extract association ID from request context
    aid = request.assoc["id"]

    # Get upcoming runs with optimized queries using select_related and prefetch_related
    runs = get_coming_runs(aid)

    # Initialize user registration tracking
    my_regs_dict = {}
    character_rels_dict = {}
    payment_invoices_dict = {}
    pre_registrations_dict = {}

    if request.user.is_authenticated:
        # Define cutoff date (3 days ago) for filtering relevant registrations
        ref = datetime.now() - timedelta(days=3)

        # Fetch user's active registrations for upcoming runs
        my_regs = Registration.objects.filter(
            run__event__assoc_id=aid,
            cancellation_date__isnull=True,  # Exclude cancelled registrations
            redeem_code__isnull=True,  # Exclude redeemed registrations
            member=request.user.member,
            run__end__gte=ref.date(),  # Only future/recent runs
        ).select_related("ticket", "run")

        # Create lookup dictionary for O(1) access to user registrations
        my_regs_dict = {reg.run_id: reg for reg in my_regs}
        my_runs_list = list(my_regs_dict.keys())

        # Filter runs: authenticated users can see START development runs they're registered for
        runs = runs.exclude(Q(development=DevelopStatus.START) & ~Q(id__in=my_runs_list))

        # Precompute character rels, payment invoices, and pre-registrations objects
        character_rels_dict = get_character_rels_dict(my_regs_dict, request.user.member)
        payment_invoices_dict = get_payment_invoices_dict(my_regs_dict, request.user.member)
        pre_registrations_dict = get_pre_registrations_dict(aid, request.user.member)
    else:
        # Anonymous users cannot see runs in START development status
        runs = runs.exclude(development=DevelopStatus.START)
        my_regs = None

    # Initialize context with default user context and empty collections
    ctx = def_user_ctx(request)
    ctx.update({"open": [], "future": [], "langs": [], "page": "calendar"})

    # Add language filter to context if specified
    if lang:
        ctx["lang"] = lang

    # Process each run to determine registration status and categorize
    for run in runs:
        # Attach user's registration to run object for template access
        run.my_reg = my_regs_dict.get(run.id) if my_regs_dict else None

        # Calculate registration status (open, closed, full, etc.)
        registration_status(
            run,
            request.user,
            my_regs=my_regs,
            character_rels_dict=character_rels_dict,
            payment_invoices_dict=payment_invoices_dict,
            pre_registrations_dict=pre_registrations_dict,
        )

        # Categorize runs based on registration availability
        if run.status["open"]:
            ctx["open"].append(run)  # Available for registration
        elif "already" not in run.status:
            ctx["future"].append(run)  # Future runs (not yet open, not already registered)

    # Add association-specific homepage text to context
    ctx["custom_text"] = get_assoc_text(request.assoc["id"], AssocTextType.HOME)

    return render(request, "larpmanager/general/calendar.html", ctx)


def get_character_rels_dict(my_regs_dict, member):
    # Precalculate RegistrationCharacterRel data for all runs to optimize queries
    character_rels_dict = {}
    if my_regs_dict:
        # Get all RegistrationCharacterRel objects for user's registrations in one query
        reg_ids = [reg.id for reg in my_regs_dict.values()]
        character_rels = (
            RegistrationCharacterRel.objects.filter(reg_id__in=reg_ids, reg__member=member)
            .select_related("character")
            .order_by("character__number")
        )

        # Group character relations by registration ID
        for rel in character_rels:
            if rel.reg_id not in character_rels_dict:
                character_rels_dict[rel.reg_id] = []
            character_rels_dict[rel.reg_id].append(rel)
    return character_rels_dict


def get_payment_invoices_dict(my_regs_dict, member):
    # Precalculate PaymentInvoice data for all registrations to optimize queries
    payment_invoices_dict = {}
    if my_regs_dict:
        reg_ids = [reg.id for reg in my_regs_dict.values()]

        # Get all payment invoices for user's registrations in one query
        payment_invoices = PaymentInvoice.objects.filter(
            reg_id__in=reg_ids, member=member, typ=PaymentType.REGISTRATION
        ).select_related("method")

        # Group payment invoices by registration ID (idx field)
        for invoice in payment_invoices:
            if invoice.idx not in payment_invoices_dict:
                payment_invoices_dict[invoice.idx] = []
            payment_invoices_dict[invoice.idx].append(invoice)
    return payment_invoices_dict


def get_pre_registrations_dict(assoc_id, member):
    # Precalculate PreRegistration data for all events to optimize queries
    pre_registrations_dict = {}
    if member:
        # Get all pre-registrations for user's events in one query
        pre_registrations = PreRegistration.objects.filter(
            event__assoc_id=assoc_id, member=member, deleted__isnull=True
        ).select_related("event")

        # Group pre-registrations by event ID
        for pre_reg in pre_registrations:
            pre_registrations_dict[pre_reg.event_id] = pre_reg
    return pre_registrations_dict


def get_coming_runs(assoc_id: int | None, future: bool = True) -> QuerySet[Run]:
    """Get upcoming or past runs for an association with optimized queries.

    Args:
        assoc_id: Association ID to filter by. If None, returns runs for all associations.
        future: If True, get future runs; if False, get past runs. Defaults to True.

    Returns:
        QuerySet of Run objects with optimized select_related, ordered by end date.
        Future runs are ordered ascending, past runs descending.
    """
    # Base queryset: exclude cancelled runs and invisible events, optimize with select_related
    runs = Run.objects.exclude(development=DevelopStatus.CANC).exclude(event__visible=False).select_related("event")

    # Filter by association if specified
    if assoc_id:
        runs = runs.filter(event__assoc_id=assoc_id)

    # Apply date filtering and ordering based on future/past requirement
    if future:
        # Get runs ending 3+ days from now, ordered by end date (earliest first)
        ref = datetime.now() - timedelta(days=3)
        runs = runs.filter(end__gte=ref.date()).order_by("end")
    else:
        # Get runs that ended 3+ days ago, ordered by end date (latest first)
        ref = datetime.now() + timedelta(days=3)
        runs = runs.filter(end__lte=ref.date()).order_by("-end")

    return runs


def home_json(request: HttpRequest, lang: str = "it") -> JsonResponse:
    """
    Get upcoming events for the association in JSON format.

    Args:
        request: HTTP request object containing association info
        lang: Language code for localization (default: "it")

    Returns:
        JsonResponse: JSON response containing list of upcoming events
    """
    # Extract association ID from request
    aid = request.assoc["id"]

    # Set language code if provided
    if lang:
        request.LANGUAGE_CODE = lang

    res = []
    runs = get_coming_runs(aid)

    # Track already processed events to avoid duplicates
    already = []

    # Process each run and add unique events to result
    for run in runs:
        if run.event.id not in already:
            res.append(run.event.show())
        already.append(run.event.id)

    return JsonResponse({"res": res})


def carousel(request: HttpRequest) -> HttpResponse:
    """
    Display event carousel with recent and upcoming events.

    Retrieves events from the current association, excludes development/cancelled events,
    and prepares them for carousel display. Events are deduplicated by event_id and
    marked as "coming" if they end within 3 days of today.

    Args:
        request: HTTP request object containing association context

    Returns:
        HttpResponse: Rendered carousel template with event list and JSON data

    Note:
        Only shows events that have ended and are not in START or CANC development status.
        Events ending after 3 days ago are marked as "coming".
    """
    # Initialize context with default user context and empty list
    ctx = def_user_ctx(request)
    ctx.update({"list": []})

    # Cache to track processed events and prevent duplicates
    cache = {}

    # Reference date: 3 days ago from now
    ref = (datetime.now() - timedelta(days=3)).date()

    # Query runs for current association, excluding development/cancelled events
    # Order by end date descending to get most recent first
    for run in (
        Run.objects.filter(event__assoc_id=request.assoc["id"])
        .exclude(development=DevelopStatus.START)
        .exclude(development=DevelopStatus.CANC)
        .order_by("-end")
        .select_related("event")
    ):
        # Skip if event already processed (deduplicate by event_id)
        if run.event_id in cache:
            continue

        # Skip runs without end date
        if not run.end:
            continue

        # Mark event as processed and get event display data
        cache[run.event_id] = 1
        el = run.event.show()

        # Mark as "coming" if event ends after reference date
        el["coming"] = run.end > ref
        ctx["list"].append(el)

    # Convert event list to JSON for frontend consumption
    ctx["json"] = json.dumps(ctx["list"])

    return render(request, "larpmanager/general/carousel.html", ctx)


@login_required
def share(request: HttpRequest) -> HttpResponse:
    """Handle member data sharing consent for organization.

    This view allows members to grant data sharing permissions with an organization.
    If the member has already granted permission, they are redirected with a success message.
    For POST requests, the membership status is updated to JOINED.

    Args:
        request (HttpRequest): The HTTP request object containing user and session data.

    Returns:
        HttpResponse: Either a rendered template for the sharing form or a redirect
                     to the home page after successful consent or if already granted.

    Raises:
        AttributeError: If request.user.member or request.assoc is not available.
    """
    # Initialize the user context for template rendering
    ctx = def_user_ctx(request)

    # Get the user's membership status for this organization
    el = get_user_membership(request.user.member, request.assoc["id"])

    # Check if user has already granted data sharing permission
    if el.status != MembershipStatus.EMPTY:
        messages.success(request, _("You have already granted data sharing with this organisation") + "!")
        return redirect("home")

    # Handle POST request to grant data sharing consent
    if request.method == "POST":
        # Update membership status to indicate consent granted
        el.status = MembershipStatus.JOINED
        el.save()

        # Show success message and redirect to home
        messages.success(request, _("You have granted data sharing with this organisation!"))
        return redirect("home")

    # Prepare context for rendering the consent form
    ctx["disable_join"] = True

    return render(request, "larpmanager/member/share.html", ctx)


@login_required
def legal_notice(request):
    ctx = def_user_ctx(request)
    ctx.update({"text": get_assoc_text(request.assoc["id"], AssocTextType.LEGAL)})
    return render(request, "larpmanager/general/legal.html", ctx)


@login_required
def event_register(request: HttpRequest, s: str) -> Union[HttpResponseRedirect, HttpResponse]:
    """Display event registration options for future runs.

    Shows available registration options for an event. If no future runs exist
    and pre-registration is enabled, redirects to pre-registration. If only one
    run is available, redirects directly to that run's registration. Otherwise,
    displays a list of all available runs with their registration status.

    Args:
        request: Django HTTP request object containing user and session data
        s: Event slug identifier used to lookup the specific event

    Returns:
        HttpResponseRedirect: Redirect to pre-registration or single run registration
        HttpResponse: Rendered template with list of available runs for selection

    Raises:
        Event.DoesNotExist: If the event slug doesn't match any existing event
    """
    # Get event context and validate access permissions
    ctx = get_event(request, s)

    # Filter for future runs that are not in development and are visible
    runs = (
        Run.objects.filter(event=ctx["event"], end__gte=datetime.now())
        .exclude(development=DevelopStatus.START)
        .exclude(event__visible=False)
        .order_by("end")
    )

    # Handle case where no future runs exist - check for pre-registration feature
    if len(runs) == 0 and "pre_register" in request.assoc["features"]:
        return redirect("pre_register", s=s)

    # If only one run available, redirect directly to its registration
    elif len(runs) == 1:
        run = runs.first()
        return redirect("register", s=run.get_slug())

    # Build list of runs with registration status for template rendering
    ctx["list"] = []
    features_map = {ctx["event"].slug: ctx["features"]}

    # Process each run to determine and cache registration status
    for r in runs:
        registration_status(r, request.user, features_map=features_map)
        ctx["list"].append(r)

    # Render template with list of available runs for user selection
    return render(request, "larpmanager/general/event_register.html", ctx)


def calendar_past(request: HttpRequest) -> HttpResponse:
    """Display calendar of past events for the association.

    This view retrieves and displays all past events for the current association,
    including user registration status and related information if the user is authenticated.

    Args:
        request: HTTP request object containing user authentication data and
                association information in request.assoc

    Returns:
        HttpResponse: Rendered template showing past events calendar with user-specific
                     registration information and status for each event

    Note:
        Requires user to have access to the association specified in request.assoc.
        Anonymous users will see events without registration information.
    """
    # Get association ID and initialize user context
    aid = request.assoc["id"]
    ctx = def_user_ctx(request)

    # Retrieve all past runs for this association
    runs = get_coming_runs(aid, future=False)

    # Initialize dictionaries for user-specific data
    my_regs_dict = {}
    character_rels_dict = {}
    payment_invoices_dict = {}
    pre_registrations_dict = {}

    # Fetch user registration data if authenticated
    if request.user.is_authenticated:
        # Get all valid registrations for this user in this association
        my_regs = Registration.objects.filter(
            run__event__assoc_id=aid,
            cancellation_date__isnull=True,
            redeem_code__isnull=True,
            member=request.user.member,
        ).select_related("ticket", "run")
        my_regs_dict = {reg.run_id: reg for reg in my_regs}

        # Build related data dictionaries for efficient lookup
        character_rels_dict = get_character_rels_dict(my_regs_dict, request.user.member)
        payment_invoices_dict = get_payment_invoices_dict(my_regs_dict, request.user.member)
        pre_registrations_dict = get_pre_registrations_dict(aid, request.user.member)

    # Process each run and add registration status information
    runs_list = list(runs)
    ctx["list"] = []

    for run in runs_list:
        # Get user's registration for this specific run
        user_reg = my_regs_dict.get(run.id) if my_regs_dict else None
        my_regs_for_run = [user_reg] if user_reg else []

        # Update run object with registration status and related data
        registration_status(
            run,
            request.user,
            my_regs=my_regs_for_run,
            character_rels_dict=character_rels_dict,
            payment_invoices_dict=payment_invoices_dict,
            pre_registrations_dict=pre_registrations_dict,
        )
        ctx["list"].append(run)

    # Set page identifier and render template
    ctx["page"] = "calendar_past"
    return render(request, "larpmanager/general/past.html", ctx)


def check_gallery_visibility(request: HttpRequest, ctx: dict) -> bool:
    """Check if gallery is visible to the current user based on event configuration.

    Determines gallery visibility based on admin status, management context,
    authentication state, and event-specific configuration settings.

    Args:
        request: HTTP request object containing user authentication information
        ctx: Context dictionary containing event and run data with configuration

    Returns:
        True if gallery should be visible to the user, False otherwise

    Note:
        Modifies ctx dictionary by adding 'hide_login' or 'hide_signup' flags
        when corresponding visibility restrictions are applied.
    """
    # Admin users always have gallery access
    if is_lm_admin(request):
        return True

    # Management context always allows gallery access
    if "manage" in ctx:
        return True

    # Get event configuration for gallery visibility rules
    hide_signup = ctx["event"].get_config("gallery_hide_signup", False)
    hide_login = ctx["event"].get_config("gallery_hide_login", False)

    # Check login requirement - hide gallery for unauthenticated users
    if hide_login and not request.user.is_authenticated:
        ctx["hide_login"] = True
        return False

    # Check signup requirement - hide gallery for users without registration
    if hide_signup and not ctx["run"].reg:
        ctx["hide_signup"] = True
        return False

    # Default: gallery is visible
    return True


def gallery(request: HttpRequest, s: str) -> HttpResponse:
    """Display event gallery with character and registration data.

    Shows approved characters and unassigned registrations for events with
    character features enabled. Handles visibility permissions and caching.

    Args:
        request: HTTP request object containing user session and permissions
        s: Event slug identifier for the specific event

    Returns:
        HttpResponse: Rendered gallery template with character and registration
            context data, or redirect if character feature not enabled

    Raises:
        Http404: If event/run not found or user lacks permissions
    """
    # Get event context and verify character feature is enabled
    ctx = get_event_run(request, s, status=True)
    if "character" not in ctx["features"]:
        return redirect("event", s=ctx["run"].get_slug())

    # Initialize registration list for unassigned players
    ctx["reg_list"] = []

    # Get event features for permission checks
    features = get_event_features(ctx["event"].id)

    # Check if user has permission to view gallery content
    if check_gallery_visibility(request, ctx):
        # Load character cache if writing fields are visible or character display forced
        if not ctx["event"].get_config("writing_field_visibility", False) or ctx.get("show_character"):
            get_event_cache_all(ctx)

        # Check if uncasted players should be hidden from gallery
        hide_uncasted_players = ctx["event"].get_config("gallery_hide_uncasted_players", False)
        if not hide_uncasted_players:
            # Get registrations that already have assigned characters
            que = RegistrationCharacterRel.objects.filter(reg__run_id=ctx["run"].id)
            if ctx["event"].get_config("user_character_approval", False):
                que = que.filter(character__status__in=[CharacterStatus.APPROVED])
            assigned = que.values_list("reg_id", flat=True)

            # Get active registrations without assigned characters
            que_reg = Registration.objects.filter(run_id=ctx["run"].id, cancellation_date__isnull=True)
            que_reg = que_reg.exclude(pk__in=assigned).exclude(ticket__tier=TicketTier.WAITING)

            # Add non-provisional members to registration list
            for reg in que_reg.select_related("member", "ticket").order_by("search"):
                if not is_reg_provisional(reg, event=ctx["event"], features=features):
                    ctx["reg_list"].append(reg.member)

    return render(request, "larpmanager/event/gallery.html", ctx)


def event(request: HttpRequest, s: str) -> HttpResponse:
    """
    Display main event page with runs, registration status, and event details.

    Args:
        request: HTTP request object containing user authentication and session data
        s: Event slug used to identify the specific event

    Returns:
        HttpResponse: Rendered event template with context containing event details,
                     runs categorized as coming/past, and registration information

    Note:
        - Categorizes runs as 'coming' (ended within 3 days) or 'past'
        - Includes user registration status if authenticated
        - Sets no_robots flag based on development status and timing
    """
    # Get base context with event and run information
    ctx = get_event_run(request, s, status=True)
    ctx["coming"] = []
    ctx["past"] = []

    # Retrieve user's registrations for this event if authenticated
    my_regs = None
    if request.user.is_authenticated:
        my_regs = Registration.objects.filter(
            run__event=ctx["event"],
            redeem_code__isnull=True,
            cancellation_date__isnull=True,
            member=request.user.member,
        )

    # Get all runs for the event and set reference date (3 days ago)
    runs = Run.objects.filter(event=ctx["event"])
    ref = datetime.now() - timedelta(days=3)

    # Prepare features mapping for registration status checking
    features_map = {ctx["event"].slug: ctx["features"]}

    # Process each run to determine registration status and categorize by timing
    for r in runs:
        if not r.end:
            continue

        # Update run with registration status information
        registration_status(r, request.user, my_regs=my_regs, features_map=features_map)

        # Categorize run as coming (recent) or past based on end date
        if r.end > ref.date():
            ctx["coming"].append(r)
        else:
            ctx["past"].append(r)

    # Refresh event object to ensure latest data
    ctx["event"] = Event.objects.get(pk=ctx["event"].pk)

    # Determine if search engines should index this page
    ctx["no_robots"] = (
        not ctx["run"].development == DevelopStatus.SHOW
        or not ctx["run"].end
        or datetime.today().date() > ctx["run"].end
    )

    return render(request, "larpmanager/event/event.html", ctx)


def event_redirect(request, s):
    return redirect("event", s=s)


def search(request: HttpRequest, s: str) -> HttpResponse:
    """Display event search page with character gallery and search functionality.

    This view handles the character search functionality for events, filtering
    characters based on visibility permissions and preparing data for frontend
    search capabilities.

    Args:
        request: The HTTP request object containing user session and permissions
        s: The event slug string used to identify the specific event

    Returns:
        HttpResponse: Rendered search.html template with searchable character data,
            including character fields, factions, questions, and search configuration

    Note:
        Characters are only displayed if gallery visibility is enabled and
        character display is permitted for the current user and event.
    """
    # Get event context with run information and status validation
    ctx = get_event_run(request, s, status=True)

    # Check if user has permission to view gallery and characters are enabled
    if check_gallery_visibility(request, ctx) and ctx["show_character"]:
        # Load all event cache data including characters, factions, etc.
        get_event_cache_all(ctx)

        # Retrieve custom search text for this event if configured
        ctx["search_text"] = get_event_text(ctx["event"].id, EventTextType.SEARCH)

        # Determine which character fields should be visible to the user
        visible_writing_fields(ctx, QuestionApplicable.CHARACTER)

        # Filter character fields based on visibility permissions
        for _num, char in ctx["chars"].items():
            fields = char.get("fields")
            if not fields:
                continue

            # Remove fields that shouldn't be visible to current user
            to_delete = [
                qid for qid in list(fields) if str(qid) not in ctx.get("show_character", []) and "show_all" not in ctx
            ]
            for qid in to_delete:
                del fields[qid]

    # Ensure all required context keys exist and convert to JSON for frontend
    for slug in ["chars", "factions", "questions", "options", "searchable"]:
        if slug not in ctx:
            ctx[slug] = {}
        # Create JSON versions for JavaScript consumption
        ctx[f"{slug}_json"] = json.dumps(ctx[slug])

    return render(request, "larpmanager/event/search.html", ctx)


def get_fact(qs):
    ls = []
    for f in qs:
        fac = f.show_complete()
        # print(fac)
        if len(fac["characters"]) == 0:
            continue
        ls.append(fac)
    return ls


def get_factions(ctx):
    fcs = ctx["event"].get_elements(Faction)
    ctx["sec"] = get_fact(fcs.filter(typ=FactionType.PRIM).order_by("number"))
    ctx["trasv"] = get_fact(fcs.filter(typ=FactionType.TRASV).order_by("number"))


def check_visibility(ctx, typ, name):
    mapping = _get_writing_mapping()
    if mapping.get(typ) not in ctx["features"]:
        raise Http404(typ + " not active")

    if "staff" not in ctx and not ctx[f"show_{typ}"]:
        raise HiddenError(ctx["run"].get_slug(), name)


def factions(request, s):
    ctx = get_event_run(request, s, status=True)
    check_visibility(ctx, "faction", _("Factions"))
    get_event_cache_all(ctx)
    return render(request, "larpmanager/event/factions.html", ctx)


def faction(request: HttpRequest, s: str, g: str) -> HttpResponse:
    """Display detailed information for a specific faction.

    Args:
        request: HTTP request object containing user and session data
        s: Event slug string used to identify the specific event
        g: Faction identifier string used to locate the faction

    Returns:
        HttpResponse: Rendered faction detail page with faction information

    Raises:
        Http404: If faction does not exist or has invalid type/missing ID
    """
    # Get event context and verify user access permissions
    ctx = get_event_run(request, s, status=True)
    check_visibility(ctx, "faction", _("Factions"))

    # Load all cached event data including factions
    get_event_cache_all(ctx)

    # Check if faction exists in the cached data
    typ = None
    if g in ctx["factions"]:
        ctx["faction"] = ctx["factions"][g]
        typ = ctx["faction"]["typ"]

    # Validate faction exists and has proper type and ID
    if "faction" not in ctx or typ == "g" or "id" not in ctx["faction"]:
        raise Http404("Faction does not exist")

    # Get faction-specific writing elements and questions
    ctx["fact"] = get_writing_element_fields(
        ctx, "faction", QuestionApplicable.FACTION, ctx["faction"]["id"], only_visible=True
    )

    return render(request, "larpmanager/event/faction.html", ctx)


def quests(request, s: str, g: str = None) -> HttpResponse:
    """Display quest types or specific quests for an event.

    Shows either a list of quest types for an event, or if a quest type
    is specified, shows all visible quests of that type.

    Args:
        request: The HTTP request object
        s: Event slug identifier
        g: Optional quest type number. If None, shows quest types list

    Returns:
        HttpResponse: Rendered template with quest types or quests list
    """
    # Get event context and verify user can view quests
    ctx = get_event_run(request, s, status=True)
    check_visibility(ctx, "quest", _("Quest"))

    # If no quest type specified, show list of quest types
    if not g:
        ctx["list"] = QuestType.objects.filter(event=ctx["event"]).order_by("number").prefetch_related("quests")
        return render(request, "larpmanager/event/quest_types.html", ctx)

    # Get specific quest type by number
    get_element(ctx, g, "quest_type", QuestType, by_number=True)

    # Build list of visible quests for the specified quest type
    ctx["list"] = []
    for el in Quest.objects.filter(event=ctx["event"], hide=False, typ=ctx["quest_type"]).order_by("number"):
        ctx["list"].append(el.show_complete())

    return render(request, "larpmanager/event/quests.html", ctx)


def quest(request: HttpRequest, s: str, g: int) -> HttpResponse:
    """Display individual quest details and associated traits.

    Retrieves and displays a specific quest along with its associated traits
    and form fields. Checks user permissions and event visibility before
    rendering the quest template.

    Args:
        request: HTTP request object containing user session and metadata
        s: Event slug identifier for the specific event
        g: Quest number identifier to retrieve the specific quest

    Returns:
        HttpResponse: Rendered quest template with quest details, fields, and traits

    Raises:
        Http404: If quest is not found or user lacks permission to view
    """
    # Get event context and verify user has access to view quest content
    ctx = get_event_run(request, s, status=True)
    check_visibility(ctx, "quest", _("Quest"))

    # Retrieve the specific quest by number and add to context
    get_element(ctx, g, "quest", Quest, by_number=True)

    # Get visible form fields associated with this quest
    ctx["quest_fields"] = get_writing_element_fields(
        ctx, "quest", QuestionApplicable.QUEST, ctx["quest"].id, only_visible=True
    )

    # Build list of traits associated with this quest including their fields
    traits = []
    for el in ctx["quest"].traits.all():
        # Get form fields for each trait and merge with trait display data
        res = get_writing_element_fields(ctx, "trait", QuestionApplicable.TRAIT, el.id, only_visible=True)
        res.update(el.show())
        traits.append(res)
    ctx["traits"] = traits

    return render(request, "larpmanager/event/quest.html", ctx)


def limitations(request: HttpRequest, s: str) -> HttpResponse:
    """Display event limitations including ticket availability and discounts.

    This view shows the availability status of tickets, registration options, and
    active discounts for a specific event run. It retrieves current registration
    counts and calculates remaining availability for each item.

    Args:
        request: The HTTP request object containing user and session data.
        s: The event slug identifier used to retrieve the specific event.

    Returns:
        An HttpResponse object with the rendered limitations template containing
        ticket availability, registration options, and discount information.
    """
    # Get event context and verify event status
    ctx = get_event_run(request, s, status=True)

    # Retrieve current registration counts for capacity calculations
    counts = get_reg_counts(ctx["run"])

    # Process visible discounts for the event run
    ctx["disc"] = []
    for discount in ctx["run"].discounts.exclude(visible=False):
        ctx["disc"].append(discount.show(ctx["run"]))

    # Process available tickets with usage tracking
    ctx["tickets"] = []
    for ticket in RegistrationTicket.objects.filter(event=ctx["event"], max_available__gt=0, visible=True):
        dt = ticket.show(ctx["run"])
        key = f"tk_{ticket.id}"
        # Add current usage count if available
        if key in counts:
            dt["used"] = counts[key]
        ctx["tickets"].append(dt)

    # Process registration options with availability limits
    ctx["opts"] = []
    que = RegistrationOption.objects.filter(question__event=ctx["event"], max_available__gt=0)
    for option in que:
        dt = option.show(ctx["run"])
        key = f"option_{option.id}"
        # Track option usage against limits
        if key in counts:
            dt["used"] = counts[key]
        ctx["opts"].append(dt)

    return render(request, "larpmanager/event/limitations.html", ctx)


def export(request: HttpRequest, s: str, t: str) -> JsonResponse:
    """Export event elements as JSON for external consumption.

    This function exports various types of event-related elements (characters,
    factions, quests, or traits) in JSON format for external systems to consume.

    Args:
        request: The HTTP request object containing user and session information.
        s: The event slug identifier used to locate the specific event.
        t: The type of elements to export. Must be one of:
           - 'char': Export characters associated with the event
           - 'faction': Export factions associated with the event
           - 'quest': Export quests belonging to the event
           - 'trait': Export traits from quests in the event

    Returns:
        JsonResponse: A JSON response containing the exported elements data,
                     with element numbers as keys and element details as values.

    Raises:
        Http404: If the provided type parameter is not one of the valid options.
    """
    # Get the event context using the provided slug
    ctx = get_event(request, s)

    # Determine which type of elements to export based on the type parameter
    if t == "char":
        # Export characters, ordered by their number field
        lst = ctx["event"].get_elements(Character).order_by("number")
    elif t == "faction":
        # Export factions, ordered by their number field
        lst = ctx["event"].get_elements(Faction).order_by("number")
    elif t == "quest":
        # Export quests directly filtered by event, ordered by number
        lst = Quest.objects.filter(event=ctx["event"]).order_by("number")
    elif t == "trait":
        # Export traits from quests belonging to this event, ordered by number
        lst = Trait.objects.filter(quest__event=ctx["event"]).order_by("number")
    else:
        # Raise 404 error for invalid export types
        raise Http404("wrong type")

    # r = Run(event=ctx["event"])

    # Build the response dictionary with element numbers as keys
    aux = {}
    for el in lst:
        # Convert each element to its display representation using the run context
        aux[el.number] = el.show(ctx["run"])

    # Return the elements data as a JSON response
    return JsonResponse(aux)
