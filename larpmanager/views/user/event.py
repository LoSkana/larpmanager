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
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.cache.association_text import get_association_text
from larpmanager.cache.character import (
    get_event_cache_all,
    get_writing_element_fields,
)
from larpmanager.cache.config import get_event_config
from larpmanager.cache.event_text import get_event_text
from larpmanager.cache.feature import get_event_features
from larpmanager.cache.fields import visible_writing_fields
from larpmanager.cache.registration import get_reg_counts
from larpmanager.models.accounting import PaymentInvoice, PaymentType
from larpmanager.models.association import AssociationTextType
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
from larpmanager.models.member import MembershipStatus
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
from larpmanager.utils.base import get_context, get_event, get_event_context
from larpmanager.utils.common import get_element
from larpmanager.utils.exceptions import HiddenError
from larpmanager.utils.registration import registration_status


def calendar(request: HttpRequest, context: dict, lang: str) -> HttpResponse:
    """Display the event calendar with open and future runs for an association.

    This function retrieves upcoming runs for an association, checks user registration status,
    and categorizes runs into 'open' (available for registration) and 'future' (not yet open).
    It also filters runs based on development status and user permissions.

    Args:
        request: HTTP request object containing user and association data. Must include
                'association' key with association information and authenticated user data.
        context: Dict context informations.
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
    association_id = context["association_id"]

    # Get upcoming runs with optimized queries using select_related and prefetch_related
    runs = get_coming_runs(association_id)

    # Initialize user registration tracking
    user_registrations_by_run_id = {}
    character_relations_by_registration_id = {}
    payment_invoices_by_registration_id = {}
    pre_registrations_by_event_id = {}

    if "member" in context:
        # Define cutoff date (3 days ago) for filtering relevant registrations
        cutoff_date = timezone.now() - timedelta(days=3)

        member = context["member"]

        # Fetch user's active registrations for upcoming runs
        user_registrations = Registration.objects.filter(
            run__event__association_id=association_id,
            cancellation_date__isnull=True,  # Exclude cancelled registrations
            redeem_code__isnull=True,  # Exclude redeemed registrations
            member=member,
            run__end__gte=cutoff_date.date(),  # Only future/recent runs
        ).select_related("ticket", "run")

        # Create lookup dictionary for O(1) access to user registrations
        user_registrations_by_run_id = {registration.run_id: registration for registration in user_registrations}
        user_registered_run_ids = list(user_registrations_by_run_id.keys())

        # Filter runs: authenticated users can see START development runs they're registered for
        runs = runs.exclude(Q(development=DevelopStatus.START) & ~Q(id__in=user_registered_run_ids))

        # Precompute character rels, payment invoices, and pre-registrations objects
        character_relations_by_registration_id = get_character_rels_dict(user_registrations_by_run_id, member)
        payment_invoices_by_registration_id = get_payment_invoices_dict(user_registrations_by_run_id, member)
        pre_registrations_by_event_id = get_pre_registrations_dict(association_id, member)
    else:
        # Anonymous users cannot see runs in START development status
        runs = runs.exclude(development=DevelopStatus.START)

    # Initialize context with default user context and empty collections
    context = get_context(request)
    context.update({"open": [], "future": [], "langs": [], "page": "calendar"})

    # Add language filter to context if specified
    if lang:
        context["lang"] = lang

    context.update(
        {
            "my_regs": user_registrations_by_run_id,
            "character_rels_dict": character_relations_by_registration_id,
            "payment_invoices_dict": payment_invoices_by_registration_id,
            "pre_registrations_dict": pre_registrations_by_event_id,
        },
    )

    # Process each run to determine registration status and categorize
    for run in runs:
        # Calculate registration status (open, closed, full, etc.)
        registration_status(run, context["member"], context)

        # Categorize runs based on registration availability
        if run.status["open"]:
            context["open"].append(run)  # Available for registration
        elif "already" not in run.status:
            context["future"].append(run)  # Future runs (not yet open, not already registered)

    # Add association-specific homepage text to context
    context["custom_text"] = get_association_text(context["association_id"], AssociationTextType.HOME)

    return render(request, "larpmanager/general/calendar.html", context)


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
            reg_id__in=registration_ids,
            member=member,
            typ=PaymentType.REGISTRATION,
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
            event__association_id=association_id,
            member=member,
            deleted__isnull=True,
        ).select_related("event")

        # Group pre-registrations by event ID for fast lookup
        # Each event can have only one pre-registration per member
        for pre_registration in member_pre_registrations:
            event_id_to_pre_registration[pre_registration.event_id] = pre_registration

    return event_id_to_pre_registration


def get_coming_runs(association_id: int | None, *, future: bool = True) -> QuerySet[Run]:
    """Get upcoming or past runs for an association with optimized queries.

    Args:
        association_id: Association ID to filter by. If None, returns runs for all associations.
        future: If True, get future runs; if False, get past runs. Defaults to True.

    Returns:
        QuerySet of Run objects with optimized select_related, ordered by end date.
        Future runs are ordered ascending, past runs descending.

    """
    # Base queryset: exclude cancelled runs and invisible events, optimize with select_related
    runs = Run.objects.exclude(development=DevelopStatus.CANC).exclude(event__visible=False).select_related("event")

    # Filter by association if specified
    if association_id:
        runs = runs.filter(event__association_id=association_id)

    # Apply date filtering and ordering based on future/past requirement
    if future:
        # Get runs ending 3+ days from now, ordered by end date (earliest first)
        reference_date = timezone.now() - timedelta(days=3)
        runs = runs.filter(end__gte=reference_date.date()).order_by("end")
    else:
        # Get runs that ended 3+ days ago, ordered by end date (latest first)
        reference_date = timezone.now() + timedelta(days=3)
        runs = runs.filter(end__lte=reference_date.date()).order_by("-end")

    return runs


def home_json(request: HttpRequest, lang: str = "it") -> object:
    """Return JSON response with upcoming events for the association.

    Args:
        request: HTTP request object containing association context
        lang: Language code for localization, defaults to "it"

    Returns:
        JsonResponse: JSON object containing list of upcoming events

    """
    # Extract association ID from request context
    context = get_context(request)
    aid = context["association_id"]

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
    context = get_context(request)
    context.update({"list": []})

    # Cache to track processed events and set reference date (3 days ago)
    cache = {}
    ref = (timezone.now() - timedelta(days=3)).date()

    # Query runs from current association, excluding development/cancelled events
    # Order by end date descending to show most recent first
    for run in (
        Run.objects.filter(event__association_id=context["association_id"])
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
        context["list"].append(el)

    # Convert event list to JSON for frontend use
    context["json"] = json.dumps(context["list"])

    return render(request, "larpmanager/general/carousel.html", context)


@login_required
def share(request: HttpRequest):
    """Handle member data sharing consent for organization.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered template or redirect to home

    """
    context = get_context(request)

    el = context["membership"]
    if el.status != MembershipStatus.EMPTY:
        messages.success(request, _("You have already granted data sharing with this organisation") + "!")
        return redirect("home")

    if request.method == "POST":
        el.status = MembershipStatus.JOINED
        el.save()
        messages.success(request, _("You have granted data sharing with this organisation!"))
        return redirect("home")

    context["disable_join"] = True

    return render(request, "larpmanager/member/share.html", context)


@login_required
def legal_notice(request: HttpRequest) -> HttpResponse:
    """Render legal notice page with association-specific text."""
    # Build context with user data and legal notice text
    context = get_context(request)
    context.update({"text": get_association_text(context["association_id"], AssociationTextType.LEGAL)})
    return render(request, "larpmanager/general/legal.html", context)


@login_required
def event_register(request: HttpRequest, event_slug: str):
    """Display event registration options for future runs.

    Args:
        request: Django HTTP request object
        event_slug: Event slug identifier

    Returns:
        Redirect to single run registration or list of available runs

    """
    context = get_event(request, event_slug)
    # check future runs
    runs = (
        Run.objects.filter(event=context["event"], end__gte=timezone.now())
        .exclude(development=DevelopStatus.START)
        .exclude(event__visible=False)
        .order_by("end")
    )
    if len(runs) == 0 and "pre_register" in context["features"]:
        return redirect("pre_register", event_slug=event_slug)
    if len(runs) == 1:
        run = runs.first()
        return redirect("register", event_slug=run.get_slug())
    context["list"] = []
    context.update({"features_map": {context["event"].id: context["features"]}})
    for r in runs:
        registration_status(r, context["member"], context)
        context["list"].append(r)
    return render(request, "larpmanager/general/event_register.html", context)


def calendar_past(request: HttpRequest) -> HttpResponse:
    """Display calendar of past events for the association.

    Renders a calendar view showing past events for the current association.
    For authenticated users, includes registration status, character relationships,
    payment information, and pre-registration data.

    Args:
        request: HTTP request object containing user authentication and association data.
                Must include 'association' key with association ID in request context.

    Returns:
        HttpResponse: Rendered template response with past events calendar data.
                     Template: 'larpmanager/general/past.html'

    """
    # Extract association ID and initialize user context
    context = get_context(request)
    aid = context["association_id"]

    # Get all past runs for this association
    runs = get_coming_runs(aid, future=False)

    # Initialize dictionaries for user-specific data
    my_regs_dict = {}
    character_rels_dict = {}
    payment_invoices_dict = {}
    pre_registrations_dict = {}

    # Fetch user-specific registration data if authenticated
    if "member" in context:
        member = context["member"]
        # Get all non-cancelled registrations for this user and association
        my_regs = Registration.objects.filter(
            run__event__association_id=aid,
            cancellation_date__isnull=True,
            redeem_code__isnull=True,
            member=member,
        ).select_related("ticket", "run")

        # Create dictionary mapping run_id to registration for quick lookup
        my_regs_dict = {reg.run_id: reg for reg in my_regs}

        # Build related data dictionaries for character, payment, and pre-registration info
        character_rels_dict = get_character_rels_dict(my_regs_dict, member)
        payment_invoices_dict = get_payment_invoices_dict(my_regs_dict, member)
        pre_registrations_dict = get_pre_registrations_dict(aid, member)

    # Convert runs queryset to list and initialize context list
    runs_list = list(runs)
    context["list"] = []

    context.update(
        {
            "my_regs": my_regs_dict,
            "character_rels_dict": character_rels_dict,
            "payment_invoices_dict": payment_invoices_dict,
            "pre_registrations_dict": pre_registrations_dict,
        },
    )

    # Process each run to add registration status information
    for run in runs_list:
        # Update run object with registration status data
        registration_status(run, context["member"], context)

        # Add processed run to context list
        context["list"].append(run)

    # Set page identifier and render template
    context["page"] = "calendar_past"
    return render(request, "larpmanager/general/past.html", context)


def check_gallery_visibility(request: HttpRequest, context: dict) -> bool:
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

    hide_gallery_for_non_signup = get_event_config(
        context["event"].id, "gallery_hide_signup", default_value=False, context=context
    )
    hide_gallery_for_non_login = get_event_config(
        context["event"].id, "gallery_hide_login", default_value=False, context=context
    )

    if hide_gallery_for_non_login and not request.user.is_authenticated:
        context["hide_login"] = True
        return False

    if hide_gallery_for_non_signup and not context["run"].reg:
        context["hide_signup"] = True
        return False

    return True


def gallery(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Event gallery display with permissions and character filtering.

    Displays the event gallery page showing characters and registrations based on
    event configuration and user permissions. Handles character approval status,
    uncasted player visibility, and writing field visibility settings.

    Args:
        request: The HTTP request object containing user and session data
        event_slug: Event identifier string used to retrieve the specific event

    Returns:
        HttpResponse: Rendered gallery template with character and registration
        context data, or redirect to event page if character feature disabled

    Raises:
        Http404: If event or run not found (handled by get_event_context)

    """
    # Get event context and check if character feature is enabled
    context = get_event_context(request, event_slug, include_status=True)
    if "character" not in context["features"]:
        return redirect("event", event_slug=context["run"].get_slug())

    # Initialize registration list for unassigned members
    context["registration_list"] = []

    # Get event features for permission checking
    features = get_event_features(context["event"].id)

    # Check if user has permission to view gallery content
    if check_gallery_visibility(request, context):
        # Load character cache if writing fields are visible or character display is forced
        if not get_event_config(
            context["event"].id, "writing_field_visibility", default_value=False, context=context
        ) or context.get(
            "show_character",
        ):
            get_event_cache_all(context)

        # Check configuration for hiding uncasted players
        hide_uncasted_players = get_event_config(
            context["event"].id, "gallery_hide_uncasted_players", default_value=False, context=context
        )
        if not hide_uncasted_players:
            # Get registrations that have assigned characters
            que = RegistrationCharacterRel.objects.filter(reg__run_id=context["run"].id)

            # Filter by character approval status if required
            if get_event_config(context["event"].id, "user_character_approval", default_value=False, context=context):
                que = que.filter(character__status__in=[CharacterStatus.APPROVED])
            assigned = que.values_list("reg_id", flat=True)

            # Pre-filter ticket IDs to exclude from registration without character assigned
            excluded_ticket_ids = RegistrationTicket.objects.filter(
                event_id=context["event"].id,
                tier__in=[
                    TicketTier.WAITING,
                    TicketTier.STAFF,
                    TicketTier.NPC,
                    TicketTier.COLLABORATOR,
                    TicketTier.SELLER,
                ],
            ).values_list("id", flat=True)

            # Get registrations without assigned characters
            que_reg = Registration.objects.filter(run_id=context["run"].id, cancellation_date__isnull=True)
            que_reg = que_reg.exclude(pk__in=assigned).exclude(ticket_id__in=excluded_ticket_ids)

            # Add non-provisional registered members to the display list
            for reg in que_reg.select_related("member"):
                if not is_reg_provisional(reg, event=context["event"], features=features, context=context):
                    context["registration_list"].append(reg.member)

    return render(request, "larpmanager/event/gallery.html", context)


def event(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display main event page with runs, registration status, and event details.

    Args:
        request: HTTP request object containing user authentication and session data
        event_slug: Event slug used to identify the specific event

    Returns:
        HttpResponse: Rendered event template with context containing event details,
                     runs categorized as coming/past, and registration information

    Note:
        - Categorizes runs as 'coming' (ended within 3 days) or 'past'
        - Includes user registration status if authenticated
        - Sets no_robots flag based on development status and timing

    """
    # Get base context with event and run information
    context = get_event_context(request, event_slug, include_status=True)
    context["coming"] = []
    context["past"] = []

    # Retrieve user's registrations for this event if authenticated
    my_regs = []
    if request.user.is_authenticated:
        my_regs = Registration.objects.filter(
            run__event=context["event"],
            redeem_code__isnull=True,
            cancellation_date__isnull=True,
            member=context["member"],
        )

    # Get all runs for the event and set reference date (3 days ago)
    runs = Run.objects.filter(event=context["event"])
    ref = timezone.now() - timedelta(days=3)

    # Prepare features mapping for registration status checking
    features_map = {context["event"].id: context["features"]}
    context.update({"my_regs": {reg.run_id: reg for reg in my_regs}, "features_map": features_map})

    # Process each run to determine registration status and categorize by timing
    for r in runs:
        if not r.end:
            continue

        # Update run with registration status information
        registration_status(r, context["member"], context)

        # Categorize run as coming (recent) or past based on end date
        if r.end > ref.date():
            context["coming"].append(r)
        else:
            context["past"].append(r)

    # Refresh event object to ensure latest data
    context["event"] = Event.objects.get(pk=context["event"].pk)

    # Determine if search engines should index this page
    context["no_robots"] = (
        context["run"].development != DevelopStatus.SHOW
        or not context["run"].end
        or timezone.now().date() > context["run"].end
    )

    return render(request, "larpmanager/event/event.html", context)


def event_redirect(request: HttpRequest, event_slug: str) -> HttpResponseRedirect:
    """Redirect to the event detail view with the given slug."""
    return redirect("event", event_slug=event_slug)


def search(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display event search page with character gallery and search functionality.

    This view handles the character search functionality for events, including
    filtering visible character fields and preparing data for frontend search.

    Args:
        request: Django HTTP request object containing user session and data
        event_slug: Event slug string used to identify the specific event

    Returns:
        HttpResponse: Rendered search.html template with searchable character data
        and JSON-serialized context for frontend functionality

    Note:
        Characters and their fields are filtered based on visibility permissions
        and event configuration settings.

    """
    # Get event context and validate user access
    context = get_event_context(request, event_slug, include_status=True)

    # Check if gallery is visible and character display is enabled
    if check_gallery_visibility(request, context) and context["show_character"]:
        # Load all cached event data including characters
        get_event_cache_all(context)

        # Get custom search text for this event
        context["search_text"] = get_event_text(context["event"].id, EventTextType.SEARCH)

        # Determine which writing fields should be visible
        visible_writing_fields(context, QuestionApplicable.CHARACTER)

        # Filter character fields based on visibility settings
        for character_data in context["chars"].values():
            character_fields = character_data.get("fields")
            if not character_fields:
                continue

            # Remove fields that shouldn't be shown to current user
            fields_to_remove = [
                question_id
                for question_id in list(character_fields)
                if str(question_id) not in context.get("show_character", []) and "show_all" not in context
            ]
            for question_id in fields_to_remove:
                del character_fields[question_id]

    # Serialize context data to JSON for frontend consumption
    for context_key in ["chars", "factions", "questions", "options", "searchable"]:
        if context_key not in context:
            context[context_key] = {}
        # Create JSON versions of each data structure
        context[f"{context_key}_json"] = json.dumps(context[context_key])

    return render(request, "larpmanager/event/search.html", context)


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


def get_factions(context: dict) -> None:
    """Populate context with faction data organized by type."""
    fcs = context["event"].get_elements(Faction)
    # Get primary factions ordered by number
    context["sec"] = get_fact(fcs.filter(typ=FactionType.PRIM).order_by("number"))
    # Get transversal factions ordered by number
    context["trasv"] = get_fact(fcs.filter(typ=FactionType.TRASV).order_by("number"))


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


def factions(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render factions page for an event run."""
    # Get event run context and validate status
    context = get_event_context(request, event_slug, include_status=True)

    # Verify user has permission to view factions
    check_visibility(context, "faction", _("Factions"))

    # Load all event cache data into context
    get_event_cache_all(context)

    return render(request, "larpmanager/event/factions.html", context)


def faction(request: HttpRequest, event_slug: str, faction_id):
    """Display detailed information for a specific faction.

    Args:
        request: HTTP request object
        event_slug: Event slug string
        faction_id: Faction identifier string

    Returns:
        HttpResponse: Rendered faction detail page

    """
    context = get_event_context(request, event_slug, include_status=True)
    check_visibility(context, "faction", _("Factions"))

    get_event_cache_all(context)

    typ = None
    if faction_id in context["factions"]:
        context["faction"] = context["factions"][faction_id]
        typ = context["faction"]["typ"]

    if "faction" not in context or typ == "g" or "id" not in context["faction"]:
        msg = "Faction does not exist"
        raise Http404(msg)

    context["fact"] = get_writing_element_fields(
        context,
        "faction",
        QuestionApplicable.FACTION,
        context["faction"]["id"],
        only_visible=True,
    )

    return render(request, "larpmanager/event/faction.html", context)


def quests(request: HttpRequest, event_slug: str, quest_type_id: str | None = None) -> HttpResponse:
    """Display quest types or quests for a specific type in an event.

    Args:
        request: The HTTP request object
        event_slug: Event identifier string
        quest_type_id: Optional quest type number. If None, shows all quest types

    Returns:
        HttpResponse: Rendered template with quest types or specific quests

    """
    # Get event context and verify user can view quests
    context = get_event_context(request, event_slug, include_status=True)
    check_visibility(context, "quest", _("Quest"))

    # If no quest type specified, show all quest types for the event
    if not quest_type_id:
        context["list"] = QuestType.objects.filter(event=context["event"]).order_by("number").prefetch_related("quests")
        return render(request, "larpmanager/event/quest_types.html", context)

    # Get specific quest type and build list of visible quests
    get_element(context, quest_type_id, "quest_type", QuestType, by_number=True)
    context["list"] = []

    # Filter quests by event, visibility, and type, then add complete quest data
    for el in Quest.objects.filter(event=context["event"], hide=False, typ=context["quest_type"]).order_by("number"):
        context["list"].append(el.show_complete())

    return render(request, "larpmanager/event/quests.html", context)


def quest(request: HttpRequest, event_slug: str, quest_id):
    """Display individual quest details and associated traits.

    Args:
        request: HTTP request object
        event_slug: Event slug
        quest_id: Quest number

    Returns:
        HttpResponse: Rendered quest template

    """
    context = get_event_context(request, event_slug, include_status=True)
    check_visibility(context, "quest", _("Quest"))

    get_element(context, quest_id, "quest", Quest, by_number=True)
    context["quest_fields"] = get_writing_element_fields(
        context,
        "quest",
        QuestionApplicable.QUEST,
        context["quest"].id,
        only_visible=True,
    )

    traits = []
    for el in context["quest"].traits.all():
        res = get_writing_element_fields(context, "trait", QuestionApplicable.TRAIT, el.id, only_visible=True)
        res.update(el.show())
        traits.append(res)
    context["traits"] = traits

    return render(request, "larpmanager/event/quest.html", context)


def limitations(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Display event limitations including ticket availability and discounts.

    This view shows the current availability status of tickets, discounts, and
    registration options for a specific event run, helping users understand
    what's available for registration.

    Args:
        request: The HTTP request object containing user session and request data.
        event_slug: Event slug identifier.

    Returns:
        HttpResponse: Rendered template showing limitations, ticket availability,
        discounts, and registration options with their current usage counts.

    """
    # Get event and run context with status validation
    context = get_event_context(request, event_slug, include_status=True)

    # Retrieve current registration counts for tickets and options
    counts = get_reg_counts(context["run"])

    # Build discounts list with visibility filtering
    context["disc"] = []
    for discount in context["run"].discounts.exclude(visible=False):
        context["disc"].append(discount.show(context["run"]))

    # Build tickets list with availability and usage data
    context["tickets"] = []
    for ticket in RegistrationTicket.objects.filter(event=context["event"], max_available__gt=0, visible=True):
        dt = ticket.show(context["run"])
        key = f"tk_{ticket.id}"
        # Add usage count if available in registration counts
        if key in counts:
            dt["used"] = counts[key]
        context["tickets"].append(dt)

    # Build registration options list with availability constraints
    context["opts"] = []
    que = RegistrationOption.objects.filter(question__event=context["event"], max_available__gt=0)
    for option in que:
        dt = option.show(context["run"])
        key = f"option_{option.id}"
        # Add usage count if available in registration counts
        if key in counts:
            dt["used"] = counts[key]
        context["opts"].append(dt)

    return render(request, "larpmanager/event/limitations.html", context)


def export(request: HttpRequest, event_slug: str, export_type):
    """Export event elements as JSON for external consumption.

    Args:
        request: HTTP request object
        event_slug: Event slug
        export_type: Type of elements to export ('char', 'faction', 'quest', 'trait')

    Returns:
        JsonResponse: Exported elements data

    """
    context = get_event(request, event_slug)
    if export_type == "char":
        lst = context["event"].get_elements(Character).order_by("number")
    elif export_type == "faction":
        lst = context["event"].get_elements(Faction).order_by("number")
    elif export_type == "quest":
        lst = Quest.objects.filter(event=context["event"]).order_by("number")
    elif export_type == "trait":
        lst = Trait.objects.filter(quest__event=context["event"]).order_by("number")
    else:
        msg = "wrong type"
        raise Http404(msg)
    # r = Run(event=context["event"])
    aux = {}
    for el in lst:
        aux[el.number] = el.show(context["run"])
    return JsonResponse(aux)
