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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.character import (
    get_event_cache_all,
    get_writing_element_fields,
)
from larpmanager.cache.config import get_event_config
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
from larpmanager.utils.base import def_user_context
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

    # Initialize context with default user context and empty collections
    ctx = def_user_context(request)
    ctx.update({"open": [], "future": [], "langs": [], "page": "calendar"})

    # Add language filter to context if specified
    if lang:
        ctx["lang"] = lang

    ctx_reg = {
        "my_regs": my_regs_dict,
        "character_rels_dict": character_rels_dict,
        "payment_invoices_dict": payment_invoices_dict,
        "pre_registrations_dict": pre_registrations_dict,
    }

    # Process each run to determine registration status and categorize
    for run in runs:
        # Calculate registration status (open, closed, full, etc.)
        registration_status(run, request.user, ctx_reg)

        # Categorize runs based on registration availability
        if run.status["open"]:
            ctx["open"].append(run)  # Available for registration
        elif "already" not in run.status:
            ctx["future"].append(run)  # Future runs (not yet open, not already registered)

    # Add association-specific homepage text to context
    ctx["custom_text"] = get_assoc_text(request.assoc["id"], AssocTextType.HOME)

    return render(request, "larpmanager/general/calendar.html", ctx)


def get_character_rels_dict(registrations_by_run_dict: dict, member) -> dict:
    """Get character relations dictionary grouped by registration ID.

    Precalculates RegistrationCharacterRel data for all runs to optimize queries
    by fetching all character relations in a single database query and grouping
    them by registration ID.

    Args:
        registrations_by_run_dict: Dictionary of user's registrations
        member: Member object to filter registrations

    Returns:
        Dictionary mapping registration IDs to lists of RegistrationCharacterRel objects
    """
    # Initialize empty dictionary to store character relations grouped by registration ID
    character_relations_by_registration_dict = {}

    # Only proceed if user has registrations
    if registrations_by_run_dict:
        # Extract all registration IDs from the registrations dictionary
        registration_ids = [registration.id for registration in registrations_by_run_dict.values()]

        # Fetch all RegistrationCharacterRel objects for user's registrations in one optimized query
        # Include character data and order by character number for consistent results
        character_relations = (
            RegistrationCharacterRel.objects.filter(reg_id__in=registration_ids, reg__member=member)
            .select_related("character")
            .order_by("character__number")
        )

        # Group character relations by registration ID for efficient lookup
        for character_relation in character_relations:
            # Initialize list for new registration IDs
            if character_relation.reg_id not in character_relations_by_registration_dict:
                character_relations_by_registration_dict[character_relation.reg_id] = []
            # Add character relation to the appropriate registration group
            character_relations_by_registration_dict[character_relation.reg_id].append(character_relation)

    return character_relations_by_registration_dict


def get_payment_invoices_dict(registrations_by_id: dict, member) -> dict:
    """Get payment invoices organized by registration ID for the given member.

    Precalculates PaymentInvoice data for all registrations to optimize database queries
    by fetching all relevant invoices in a single query and grouping them by registration ID.

    Args:
        registrations_by_id: Dictionary containing registration objects as values
        member: Member object to filter payment invoices for

    Returns:
        Dictionary mapping registration IDs to lists of PaymentInvoice objects
    """
    # Initialize empty dictionary to store grouped payment invoices
    payment_invoices_by_registration = {}

    # Only proceed if we have registrations to process
    if registrations_by_id:
        # Extract all registration IDs for bulk query optimization
        registration_ids = [registration.id for registration in registrations_by_id.values()]

        # Fetch all payment invoices for user's registrations in single optimized query
        # Include method relation to avoid N+1 queries when accessing invoice.method
        payment_invoices = PaymentInvoice.objects.filter(
            reg_id__in=registration_ids, member=member, typ=PaymentType.REGISTRATION
        ).select_related("method")

        # Group payment invoices by registration ID using idx field as key
        # This allows quick lookup of all invoices for a specific registration
        for invoice in payment_invoices:
            registration_id = invoice.idx
            if registration_id not in payment_invoices_by_registration:
                payment_invoices_by_registration[registration_id] = []
            payment_invoices_by_registration[registration_id].append(invoice)

    return payment_invoices_by_registration


def get_pre_registrations_dict(association_id: int, member) -> dict:
    """Get pre-registrations for a member organized by event ID.

    Precalculates PreRegistration data for all events to optimize queries
    by fetching all relevant pre-registrations in a single database query
    and organizing them in a dictionary for fast lookup.

    Args:
        association_id: The association ID to filter events by
        member: The member object to get pre-registrations for

    Returns:
        Dictionary mapping event IDs to PreRegistration objects.
        Empty dict if member is None or has no pre-registrations.
    """
    # Initialize empty dictionary for pre-registration lookup
    event_id_to_pre_registration = {}

    # Only proceed if member is provided
    if member:
        # Get all pre-registrations for user's events in one query
        # Filter by association, member, and exclude deleted records
        member_pre_registrations = PreRegistration.objects.filter(
            event__assoc_id=association_id, member=member, deleted__isnull=True
        ).select_related("event")

        # Group pre-registrations by event ID for fast lookup
        # Each event can have only one pre-registration per member
        for pre_registration in member_pre_registrations:
            event_id_to_pre_registration[pre_registration.event_id] = pre_registration

    return event_id_to_pre_registration


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
        reference_date = datetime.now() - timedelta(days=3)
        runs = runs.filter(end__gte=reference_date.date()).order_by("end")
    else:
        # Get runs that ended 3+ days ago, ordered by end date (latest first)
        reference_date = datetime.now() + timedelta(days=3)
        runs = runs.filter(end__lte=reference_date.date()).order_by("-end")

    return runs


def home_json(request: object, lang: str = "it") -> object:
    """
    Returns JSON response with upcoming events for the association.

    Args:
        request: HTTP request object containing association context
        lang: Language code for localization, defaults to "it"

    Returns:
        JsonResponse: JSON object containing list of upcoming events
    """
    # Extract association ID from request context
    aid = request.assoc["id"]

    # Set language code if provided
    if lang:
        request.LANGUAGE_CODE = lang

    # Initialize result list and tracking set
    res = []
    runs = get_coming_runs(aid)
    already = []

    # Process each run and avoid duplicate events
    for run in runs:
        # Only add event if not already processed
        if run.event_id not in already:
            res.append(run.event.show())
        already.append(run.event_id)

    return JsonResponse({"res": res})


def carousel(request: HttpRequest) -> HttpResponse:
    """Display event carousel with recent and upcoming events.

    Shows a carousel of events from the current association, filtering out
    development and cancelled events. Events are ordered by end date and
    marked as 'coming' if they end within 3 days of now.

    Args:
        request: HTTP request object containing association context

    Returns:
        HttpResponse: Rendered carousel template with event list and JSON data

    Note:
        Uses caching to avoid duplicate events from multiple runs.
        Only includes events with valid end dates.
    """
    # Initialize context with default user data and empty list
    ctx = def_user_context(request)
    ctx.update({"list": []})

    # Cache to track processed events and set reference date (3 days ago)
    cache = {}
    ref = (datetime.now() - timedelta(days=3)).date()

    # Query runs from current association, excluding development/cancelled events
    # Order by end date descending to show most recent first
    for run in (
        Run.objects.filter(event__assoc_id=request.assoc["id"])
        .exclude(development=DevelopStatus.START)
        .exclude(development=DevelopStatus.CANC)
        .order_by("-end")
        .select_related("event")
    ):
        # Skip if event already processed or has no end date
        if run.event_id in cache:
            continue
        if not run.end:
            continue

        # Mark event as processed and get event display data
        cache[run.event_id] = 1
        el = run.event.show()

        # Mark event as 'coming' if it ends after reference date
        el["coming"] = run.end > ref
        ctx["list"].append(el)

    # Convert event list to JSON for frontend use
    ctx["json"] = json.dumps(ctx["list"])

    return render(request, "larpmanager/general/carousel.html", ctx)


@login_required
def share(request):
    """Handle member data sharing consent for organization.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered template or redirect to home
    """
    ctx = def_user_context(request)

    el = get_user_membership(request.user.member, request.assoc["id"])
    if el.status != MembershipStatus.EMPTY:
        messages.success(request, _("You have already granted data sharing with this organisation") + "!")
        return redirect("home")

    if request.method == "POST":
        el.status = MembershipStatus.JOINED
        el.save()
        messages.success(request, _("You have granted data sharing with this organisation!"))
        return redirect("home")

    ctx["disable_join"] = True

    return render(request, "larpmanager/member/share.html", ctx)


@login_required
def legal_notice(request: HttpRequest) -> HttpResponse:
    """Render legal notice page with association-specific text."""
    # Build context with user data and legal notice text
    ctx = def_user_context(request)
    ctx.update({"text": get_assoc_text(request.assoc["id"], AssocTextType.LEGAL)})
    return render(request, "larpmanager/general/legal.html", ctx)


@login_required
def event_register(request, s):
    """Display event registration options for future runs.

    Args:
        request: Django HTTP request object
        s: Event slug identifier

    Returns:
        Redirect to single run registration or list of available runs
    """
    ctx = get_event(request, s)
    # check future runs
    runs = (
        Run.objects.filter(event=ctx["event"], end__gte=datetime.now())
        .exclude(development=DevelopStatus.START)
        .exclude(event__visible=False)
        .order_by("end")
    )
    if len(runs) == 0 and "pre_register" in request.assoc["features"]:
        return redirect("pre_register", s=s)
    elif len(runs) == 1:
        run = runs.first()
        return redirect("register", s=run.get_slug())
    ctx["list"] = []
    ctx_reg = {"features_map": {ctx["event"].id: ctx["features"]}}
    for r in runs:
        registration_status(r, request.user, ctx_reg)
        ctx["list"].append(r)
    return render(request, "larpmanager/general/event_register.html", ctx)


def calendar_past(request: HttpRequest) -> HttpResponse:
    """Display calendar of past events for the association.

    Renders a calendar view showing past events for the current association.
    For authenticated users, includes registration status, character relationships,
    payment information, and pre-registration data.

    Args:
        request: HTTP request object containing user authentication and association data.
                Must include 'assoc' key with association ID in request context.

    Returns:
        HttpResponse: Rendered template response with past events calendar data.
                     Template: 'larpmanager/general/past.html'
    """
    # Extract association ID and initialize user context
    ctx = def_user_context(request)
    aid = ctx["association_id"]

    # Get all past runs for this association
    runs = get_coming_runs(aid, future=False)

    # Initialize dictionaries for user-specific data
    my_regs_dict = {}
    character_rels_dict = {}
    payment_invoices_dict = {}
    pre_registrations_dict = {}

    # Fetch user-specific registration data if authenticated
    if request.user.is_authenticated:
        # Get all non-cancelled registrations for this user and association
        my_regs = Registration.objects.filter(
            run__event__assoc_id=aid,
            cancellation_date__isnull=True,
            redeem_code__isnull=True,
            member=request.user.member,
        ).select_related("ticket", "run")

        # Create dictionary mapping run_id to registration for quick lookup
        my_regs_dict = {reg.run_id: reg for reg in my_regs}

        # Build related data dictionaries for character, payment, and pre-registration info
        character_rels_dict = get_character_rels_dict(my_regs_dict, request.user.member)
        payment_invoices_dict = get_payment_invoices_dict(my_regs_dict, request.user.member)
        pre_registrations_dict = get_pre_registrations_dict(aid, request.user.member)

    # Convert runs queryset to list and initialize context list
    runs_list = list(runs)
    ctx["list"] = []

    ctx_reg = {
        "my_regs": my_regs_dict,
        "character_rels_dict": character_rels_dict,
        "payment_invoices_dict": payment_invoices_dict,
        "pre_registrations_dict": pre_registrations_dict,
    }

    # Process each run to add registration status information
    for run in runs_list:
        # Update run object with registration status data
        registration_status(run, request.user, ctx_reg)

        # Add processed run to context list
        ctx["list"].append(run)

    # Set page identifier and render template
    ctx["page"] = "calendar_past"
    return render(request, "larpmanager/general/past.html", ctx)


def check_gallery_visibility(request, context):
    """Check if gallery is visible to the current user based on event configuration.

    Args:
        request: HTTP request object with user authentication information
        context: Context dictionary containing event and run data

    Returns:
        bool: True if gallery should be visible, False otherwise
    """
    if is_lm_admin(request):
        return True

    if "manage" in context:
        return True

    hide_gallery_for_non_signup = get_event_config(context["event"].id, "gallery_hide_signup", False, context)
    hide_gallery_for_non_login = get_event_config(context["event"].id, "gallery_hide_login", False, context)

    if hide_gallery_for_non_login and not request.user.is_authenticated:
        context["hide_login"] = True
        return False

    if hide_gallery_for_non_signup and not context["run"].reg:
        context["hide_signup"] = True
        return False

    return True


def gallery(request: HttpRequest, s: str) -> HttpResponse:
    """Event gallery display with permissions and character filtering.

    Displays the event gallery page showing characters and registrations based on
    event configuration and user permissions. Handles character approval status,
    uncasted player visibility, and writing field visibility settings.

    Args:
        request: The HTTP request object containing user and session data
        s: The event slug identifier used to retrieve the specific event

    Returns:
        HttpResponse: Rendered gallery template with character and registration
        context data, or redirect to event page if character feature disabled

    Raises:
        Http404: If event or run not found (handled by get_event_run)
    """
    # Get event context and check if character feature is enabled
    ctx = get_event_run(request, s, include_status=True)
    if "character" not in ctx["features"]:
        return redirect("event", s=ctx["run"].get_slug())

    # Initialize registration list for unassigned members
    ctx["registration_list"] = []

    # Get event features for permission checking
    features = get_event_features(ctx["event"].id)

    # Check if user has permission to view gallery content
    if check_gallery_visibility(request, ctx):
        # Load character cache if writing fields are visible or character display is forced
        if not get_event_config(ctx["event"].id, "writing_field_visibility", False, ctx) or ctx.get("show_character"):
            get_event_cache_all(ctx)

        # Check configuration for hiding uncasted players
        hide_uncasted_players = get_event_config(ctx["event"].id, "gallery_hide_uncasted_players", False, ctx)
        if not hide_uncasted_players:
            # Get registrations that have assigned characters
            que = RegistrationCharacterRel.objects.filter(reg__run_id=ctx["run"].id)

            # Filter by character approval status if required
            if get_event_config(ctx["event"].id, "user_character_approval", False, ctx):
                que = que.filter(character__status__in=[CharacterStatus.APPROVED])
            assigned = que.values_list("reg_id", flat=True)

            # Pre-filter ticket IDs to exclude from registration without character assigned
            excluded_ticket_ids = RegistrationTicket.objects.filter(
                event_id=ctx["event"].id,
                tier__in=[
                    TicketTier.WAITING,
                    TicketTier.STAFF,
                    TicketTier.NPC,
                    TicketTier.COLLABORATOR,
                    TicketTier.SELLER,
                ],
            ).values_list("id", flat=True)

            # Get registrations without assigned characters
            que_reg = Registration.objects.filter(run_id=ctx["run"].id, cancellation_date__isnull=True)
            que_reg = que_reg.exclude(pk__in=assigned).exclude(ticket_id__in=excluded_ticket_ids)

            # Add non-provisional registered members to the display list
            for reg in que_reg.select_related("member"):
                if not is_reg_provisional(reg, event=ctx["event"], features=features):
                    ctx["registration_list"].append(reg.member)

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
    ctx = get_event_run(request, s, include_status=True)
    ctx["coming"] = []
    ctx["past"] = []

    # Retrieve user's registrations for this event if authenticated
    my_regs = []
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
    features_map = {ctx["event"].id: ctx["features"]}
    ctx_reg = {"my_regs": {reg.run_id: reg for reg in my_regs}, "features_map": features_map}

    # Process each run to determine registration status and categorize by timing
    for r in runs:
        if not r.end:
            continue

        # Update run with registration status information
        registration_status(r, request.user, ctx_reg)

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

    This view handles the character search functionality for events, including
    filtering visible character fields and preparing data for frontend search.

    Args:
        request: Django HTTP request object containing user session and data
        s: Event slug string used to identify the specific event

    Returns:
        HttpResponse: Rendered search.html template with searchable character data
        and JSON-serialized context for frontend functionality

    Note:
        Characters and their fields are filtered based on visibility permissions
        and event configuration settings.
    """
    # Get event context and validate user access
    ctx = get_event_run(request, s, include_status=True)

    # Check if gallery is visible and character display is enabled
    if check_gallery_visibility(request, ctx) and ctx["show_character"]:
        # Load all cached event data including characters
        get_event_cache_all(ctx)

        # Get custom search text for this event
        ctx["search_text"] = get_event_text(ctx["event"].id, EventTextType.SEARCH)

        # Determine which writing fields should be visible
        visible_writing_fields(ctx, QuestionApplicable.CHARACTER)

        # Filter character fields based on visibility settings
        for _character_number, character_data in ctx["chars"].items():
            character_fields = character_data.get("fields")
            if not character_fields:
                continue

            # Remove fields that shouldn't be shown to current user
            fields_to_remove = [
                question_id
                for question_id in list(character_fields)
                if str(question_id) not in ctx.get("show_character", []) and "show_all" not in ctx
            ]
            for question_id in fields_to_remove:
                del character_fields[question_id]

    # Serialize context data to JSON for frontend consumption
    for context_key in ["chars", "factions", "questions", "options", "searchable"]:
        if context_key not in ctx:
            ctx[context_key] = {}
        # Create JSON versions of each data structure
        ctx[f"{context_key}_json"] = json.dumps(ctx[context_key])

    return render(request, "larpmanager/event/search.html", ctx)


def get_fact(factions_queryset) -> list[dict]:
    """Filter queryset to return only factions with characters.

    Args:
        factions_queryset: QuerySet of faction objects to filter

    Returns:
        List of faction dictionaries containing character data
    """
    factions_with_characters = []

    # Iterate through each faction in the queryset
    for faction in factions_queryset:
        faction_data = faction.show_complete()

        # Skip factions that have no characters
        if len(faction_data["characters"]) == 0:
            continue

        factions_with_characters.append(faction_data)
    return factions_with_characters


def get_factions(ctx: dict) -> None:
    """Populate context with faction data organized by type."""
    fcs = ctx["event"].get_elements(Faction)
    # Get primary factions ordered by number
    ctx["sec"] = get_fact(fcs.filter(typ=FactionType.PRIM).order_by("number"))
    # Get transversal factions ordered by number
    ctx["trasv"] = get_fact(fcs.filter(typ=FactionType.TRASV).order_by("number"))


def check_visibility(context: dict, writing_type: str, writing_name: str) -> None:
    """Check if a writing type is visible and accessible to the current user.

    Args:
        context: Context dictionary containing features, staff status, and visibility flags
        writing_type: Type of writing content to check
        writing_name: Name identifier for error reporting

    Raises:
        Http404: If the writing type is not active in current features
        HiddenError: If user lacks permission to view the content
    """
    # Get the mapping of writing types to features
    writing_type_to_feature_mapping = _get_writing_mapping()

    # Check if the writing type feature is active
    if writing_type_to_feature_mapping.get(writing_type) not in context["features"]:
        raise Http404(writing_type + " not active")

    # Check user permissions - staff can see all, others need specific visibility flag
    if "staff" not in context and not context[f"show_{writing_type}"]:
        raise HiddenError(context["run"].get_slug(), writing_name)


def factions(request: HttpRequest, s: str) -> HttpResponse:
    """Render factions page for an event run."""
    # Get event run context and validate status
    ctx = get_event_run(request, s, include_status=True)

    # Verify user has permission to view factions
    check_visibility(ctx, "faction", _("Factions"))

    # Load all event cache data into context
    get_event_cache_all(ctx)

    return render(request, "larpmanager/event/factions.html", ctx)


def faction(request, s, g):
    """Display detailed information for a specific faction.

    Args:
        request: HTTP request object
        s: Event slug string
        g: Faction identifier string

    Returns:
        HttpResponse: Rendered faction detail page
    """
    ctx = get_event_run(request, s, include_status=True)
    check_visibility(ctx, "faction", _("Factions"))

    get_event_cache_all(ctx)

    typ = None
    if g in ctx["factions"]:
        ctx["faction"] = ctx["factions"][g]
        typ = ctx["faction"]["typ"]

    if "faction" not in ctx or typ == "g" or "id" not in ctx["faction"]:
        raise Http404("Faction does not exist")

    ctx["fact"] = get_writing_element_fields(
        ctx, "faction", QuestionApplicable.FACTION, ctx["faction"]["id"], only_visible=True
    )

    return render(request, "larpmanager/event/faction.html", ctx)


def quests(request: HttpRequest, s: str, g: str | None = None) -> HttpResponse:
    """Display quest types or quests for a specific type in an event.

    Args:
        request: The HTTP request object
        s: The event slug identifier
        g: Optional quest type number. If None, shows all quest types

    Returns:
        HttpResponse: Rendered template with quest types or specific quests
    """
    # Get event context and verify user can view quests
    ctx = get_event_run(request, s, include_status=True)
    check_visibility(ctx, "quest", _("Quest"))

    # If no quest type specified, show all quest types for the event
    if not g:
        ctx["list"] = QuestType.objects.filter(event=ctx["event"]).order_by("number").prefetch_related("quests")
        return render(request, "larpmanager/event/quest_types.html", ctx)

    # Get specific quest type and build list of visible quests
    get_element(ctx, g, "quest_type", QuestType, by_number=True)
    ctx["list"] = []

    # Filter quests by event, visibility, and type, then add complete quest data
    for el in Quest.objects.filter(event=ctx["event"], hide=False, typ=ctx["quest_type"]).order_by("number"):
        ctx["list"].append(el.show_complete())

    return render(request, "larpmanager/event/quests.html", ctx)


def quest(request, s, g):
    """Display individual quest details and associated traits.

    Args:
        request: HTTP request object
        s: Event slug
        g: Quest number

    Returns:
        HttpResponse: Rendered quest template
    """
    ctx = get_event_run(request, s, include_status=True)
    check_visibility(ctx, "quest", _("Quest"))

    get_element(ctx, g, "quest", Quest, by_number=True)
    ctx["quest_fields"] = get_writing_element_fields(
        ctx, "quest", QuestionApplicable.QUEST, ctx["quest"].id, only_visible=True
    )

    traits = []
    for el in ctx["quest"].traits.all():
        res = get_writing_element_fields(ctx, "trait", QuestionApplicable.TRAIT, el.id, only_visible=True)
        res.update(el.show())
        traits.append(res)
    ctx["traits"] = traits

    return render(request, "larpmanager/event/quest.html", ctx)


def limitations(request: HttpRequest, s: str) -> HttpResponse:
    """
    Display event limitations including ticket availability and discounts.

    This view shows the current availability status of tickets, discounts, and
    registration options for a specific event run, helping users understand
    what's available for registration.

    Args:
        request: The HTTP request object containing user session and request data.
        s: The event slug used to identify the specific event.

    Returns:
        HttpResponse: Rendered template showing limitations, ticket availability,
        discounts, and registration options with their current usage counts.
    """
    # Get event and run context with status validation
    ctx = get_event_run(request, s, include_status=True)

    # Retrieve current registration counts for tickets and options
    counts = get_reg_counts(ctx["run"])

    # Build discounts list with visibility filtering
    ctx["disc"] = []
    for discount in ctx["run"].discounts.exclude(visible=False):
        ctx["disc"].append(discount.show(ctx["run"]))

    # Build tickets list with availability and usage data
    ctx["tickets"] = []
    for ticket in RegistrationTicket.objects.filter(event=ctx["event"], max_available__gt=0, visible=True):
        dt = ticket.show(ctx["run"])
        key = f"tk_{ticket.id}"
        # Add usage count if available in registration counts
        if key in counts:
            dt["used"] = counts[key]
        ctx["tickets"].append(dt)

    # Build registration options list with availability constraints
    ctx["opts"] = []
    que = RegistrationOption.objects.filter(question__event=ctx["event"], max_available__gt=0)
    for option in que:
        dt = option.show(ctx["run"])
        key = f"option_{option.id}"
        # Add usage count if available in registration counts
        if key in counts:
            dt["used"] = counts[key]
        ctx["opts"].append(dt)

    return render(request, "larpmanager/event/limitations.html", ctx)


def export(request, s, t):
    """Export event elements as JSON for external consumption.

    Args:
        request: HTTP request object
        s: Event slug
        t: Type of elements to export ('char', 'faction', 'quest', 'trait')

    Returns:
        JsonResponse: Exported elements data
    """
    ctx = get_event(request, s)
    if t == "char":
        lst = ctx["event"].get_elements(Character).order_by("number")
    elif t == "faction":
        lst = ctx["event"].get_elements(Faction).order_by("number")
    elif t == "quest":
        lst = Quest.objects.filter(event=ctx["event"]).order_by("number")
    elif t == "trait":
        lst = Trait.objects.filter(quest__event=ctx["event"]).order_by("number")
    else:
        raise Http404("wrong type")
    # r = Run(event=ctx["event"])
    aux = {}
    for el in lst:
        aux[el.number] = el.show(ctx["run"])
    return JsonResponse(aux)
