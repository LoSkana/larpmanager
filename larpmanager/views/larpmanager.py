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

import random
from datetime import date, datetime, timedelta
from typing import Optional, Union

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Avg, Count, Min, Sum
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit

from larpmanager.cache.feature import get_assoc_features, get_event_features
from larpmanager.cache.larpmanager import get_cache_lm_home
from larpmanager.cache.role import has_assoc_permission, has_event_permission
from larpmanager.forms.association import FirstAssociationForm
from larpmanager.forms.larpmanager import LarpManagerCheck, LarpManagerContact, LarpManagerTicketForm
from larpmanager.forms.miscellanea import SendMailForm
from larpmanager.forms.utils import RedirectForm
from larpmanager.mail.base import join_email
from larpmanager.mail.remind import remember_membership, remember_membership_fee, remember_pay, remember_profile
from larpmanager.models.access import AssocRole, EventRole
from larpmanager.models.association import Association, AssociationPlan, AssocTextType
from larpmanager.models.base import Feature
from larpmanager.models.event import Run
from larpmanager.models.larpmanager import (
    LarpManagerDiscover,
    LarpManagerGuide,
    LarpManagerProfiler,
    LarpManagerTutorial,
)
from larpmanager.models.member import Member, MembershipStatus, get_user_membership
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.utils.auth import check_lm_admin
from larpmanager.utils.event import get_event_run
from larpmanager.utils.exceptions import MainPageError, PermissionError
from larpmanager.utils.tasks import my_send_mail, send_mail_exec
from larpmanager.utils.text import get_assoc_text
from larpmanager.views.user.member import get_user_backend


def lm_home(request: HttpRequest) -> HttpResponse:
    """Display the LarpManager home page with promoters and reviews.

    This function renders the main landing page for LarpManager, including
    promotional content and user reviews. Special handling is provided for
    the ludomanager.it domain.

    Args:
        request: Django HTTP request object containing user and session data

    Returns:
        HttpResponse: Rendered home page template with context containing
            promoters, reviews, and contact information
    """
    # Initialize context with contact information and mark as index page
    ctx = get_lm_contact(request)
    ctx["index"] = True

    # Handle special case for ludomanager.it domain
    if request.assoc["base_domain"] == "ludomanager.it":
        return ludomanager(ctx, request)

    # Load cached home page data (promoters and reviews)
    ctx.update(get_cache_lm_home())

    # Randomize order of promoters and reviews for variety
    random.shuffle(ctx["promoters"])
    random.shuffle(ctx["reviews"])

    # Render and return the home page template
    return render(request, "larpmanager/larpmanager/home.html", ctx)


def ludomanager(ctx: dict, request) -> HttpResponse:
    """Render the LudoManager skin version of the home page.

    This function configures the context for the LudoManager skin variant
    and renders the appropriate template with the updated context.

    Args:
        ctx (dict): Context dictionary to update with skin-specific values
        request: Django HTTP request object for rendering

    Returns:
        HttpResponse: Rendered LudoManager template response

    Note:
        Sets both assoc_skin and platform to "LudoManager" for consistency
        across the application's theming system.
    """
    # Configure skin-specific context variables
    ctx["assoc_skin"] = "LudoManager"
    ctx["platform"] = "LudoManager"

    # Render and return the LudoManager-specific template
    return render(request, "larpmanager/larpmanager/skin/ludomanager.html", ctx)


@csrf_exempt
def contact(request: HttpRequest) -> HttpResponse:
    """Handle contact form submissions and display contact page.

    Processes contact form data and sends emails to administrators when valid
    submissions are received. For GET requests, displays an empty contact form.
    For POST requests, validates the form and sends notification emails to all
    configured administrators.

    Args:
        request: Django HTTP request object containing form data or GET request

    Returns:
        HttpResponse: Rendered contact template with form context or success state

    Note:
        Uses LarpManagerContact form for validation and my_send_mail for email delivery.
        Email subject includes the sender's email address for identification.
    """
    # Initialize context and completion flag
    ctx = {}
    done = False

    if request.POST:
        # Process POST request with form validation
        form = LarpManagerContact(request.POST, request=request)
        if form.is_valid():
            # Extract validated form data
            ct = form.cleaned_data["email"]

            # Send notification email to all administrators
            for _name, email in conf_settings.ADMINS:
                subj = "LarpManager contact - " + ct
                body = form.cleaned_data["content"]
                my_send_mail(subj, body, email)
                done = True
    else:
        # Create empty form for GET requests
        form = LarpManagerContact(request=request)

    # Add form to context only if submission not completed
    if not done:
        ctx["form"] = form

    return render(request, "larpmanager/larpmanager/contact.html", ctx)


def go_redirect(request, slug: str | None, p: str | None, base_domain: str = "larpmanager.com") -> HttpResponseRedirect:
    """Redirect user to association-specific subdomain or main domain.

    Handles environment-specific redirects for development/test environments
    and constructs appropriate URLs for production with optional subdomains.

    Args:
        request: Django HTTP request object containing environment info
        slug: Association slug for subdomain creation, None for main domain
        p: URL path to append after domain, None for root path
        base_domain: Base domain name for URL construction

    Returns:
        HttpResponseRedirect object pointing to the constructed URL

    Examples:
        >>> go_redirect(request, "myassoc", "events/", "example.com")
        # Returns redirect to https://myassoc.example.com/events/

        >>> go_redirect(request, None, "about/", "example.com")
        # Returns redirect to https://example.com/about/
    """
    # Handle development and test environments with localhost redirect
    if request.enviro in ["dev", "test"]:
        return redirect("http://127.0.0.1:8000/")

    # Construct base URL with subdomain if slug provided
    if slug:
        n_p = f"https://{slug}.{base_domain}/"
    else:
        n_p = f"https://{base_domain}/"

    # Append path if provided
    if p:
        n_p += p

    # Return redirect response to constructed URL
    return redirect(n_p)


def choose_assoc(request, p: str, slugs: list[str]) -> HttpResponse:
    """Handle association selection when multiple associations are available.

    This function manages the logic for redirecting users when they have access
    to multiple associations. It handles three scenarios: no associations available,
    single association (direct redirect), or multiple associations (selection form).

    Args:
        request: Django HTTP request object containing user session and POST data.
        p: URL path to redirect to after association selection.
        slugs: List of association slugs available to the current user.

    Returns:
        HttpResponse: Either a redirect to the selected association or a rendered
        selection form template.

    Raises:
        No explicit exceptions, but may raise Django form validation errors.
    """
    # Handle case where user has no available associations
    if len(slugs) == 0:
        return render(request, "larpmanager/larpmanager/na_assoc.html")

    # Single association available - redirect directly
    elif len(slugs) == 1:
        return go_redirect(request, slugs[0], p)

    # Multiple associations - show selection form
    else:
        # Process form submission with selected association
        if request.POST:
            form = RedirectForm(request.POST, slugs=slugs)
            if form.is_valid():
                counter = int(form.cleaned_data["slug"])

                # Validate selection index and redirect to chosen association
                if counter < len(slugs):
                    return go_redirect(request, slugs[counter], p)

        # Display empty form for association selection
        else:
            form = RedirectForm(slugs=slugs)

        # Render the association selection template
        return render(
            request,
            "larpmanager/larpmanager/redirect.html",
            {"form": form, "name": "association"},
        )


def go_redirect_run(run: Run, p: str) -> HttpResponseRedirect:
    """Redirect to a specific run's URL on its association's domain.

    Constructs a URL using the run's association domain and slug, then
    redirects the user to that URL with the specified path appended.

    Args:
        run: Run object containing event and association information
        p: URL path segment to append after the run slug

    Returns:
        HttpResponseRedirect object that redirects to the constructed URL

    Example:
        >>> run = Run.objects.get(id=1)
        >>> redirect_response = go_redirect_run(run, "participants")
        >>> # Redirects to https://myassoc.example.com/run-slug/participants
    """
    # Construct the full URL using association domain and run slug
    n_p = f"https://{run.event.assoc.slug}.{run.event.assoc.skin.domain}/{run.get_slug()}/{p}"

    # Return the redirect response
    return redirect(n_p)


def choose_run(request: HttpRequest, p: str, event_ids: list[int]) -> HttpResponse:
    """Handle run selection when multiple runs are available.

    Args:
        request: Django HTTP request object containing POST data and user info
        p: URL path to redirect to after run selection is complete
        event_ids: List of event IDs to filter runs from active events

    Returns:
        HttpResponse: Either a redirect to the selected run, a form for run selection,
                     or a "no events available" page

    Raises:
        None: Function handles all error cases internally with appropriate responses
    """
    # Initialize collections for runs and their display slugs
    runs = []
    slugs = []

    # Filter active runs from provided event IDs and build display options
    for r in Run.objects.filter(event_id__in=event_ids, end__gte=datetime.now()):
        runs.append(r)
        slugs.append(f"{r.search} - {r.event.assoc.slug}")

    # Handle case where no active runs are found
    if len(slugs) == 0:
        return render(request, "larpmanager/larpmanager/na_event.html")

    # Direct redirect if only one run is available
    elif len(slugs) == 1:
        return go_redirect_run(runs[0], p)

    # Handle multiple runs - show selection form or process selection
    else:
        # Process form submission for run selection
        if request.POST:
            form = RedirectForm(request.POST, slugs=slugs)
            if form.is_valid():
                counter = int(form.cleaned_data["slug"])
                # Validate selection index and redirect to chosen run
                if counter < len(slugs):
                    return go_redirect_run(runs[counter], p)
        else:
            # Display form for run selection
            form = RedirectForm(slugs=slugs)

        # Render selection page with form and context
        return render(
            request,
            "larpmanager/larpmanager/redirect.html",
            {"form": form, "name": "event"},
        )


@login_required
def redr(request: HttpRequest, p: str) -> HttpResponse:
    """Handle redirects based on user roles and permissions.

    Redirects users to appropriate associations or events based on their
    assigned roles and the requested path. If the path doesn't start with
    'event/', redirects to association selection. Otherwise, redirects to
    event/run selection.

    Args:
        request: Django HTTP request object (must be authenticated)
        p: URL path to redirect to

    Returns:
        HttpResponse: Redirect to appropriate association or event selection

    Raises:
        AttributeError: If request.user.member is not available
    """
    # Handle non-event paths - redirect to association selection
    if not p.startswith("event/"):
        slugs = set()

        # Collect all association slugs where user has roles
        for ar in AssocRole.objects.filter(members=request.user.member).select_related("assoc"):
            slugs.add(ar.assoc.slug)

        # Redirect to association chooser with collected slugs
        return choose_assoc(request, p, list(slugs))

    # Handle event paths - extract event identifier and redirect to event selection
    p = p.replace("event/", "")
    ids = set()

    # Collect all event IDs where user has roles
    for er in EventRole.objects.filter(members=request.user.member):
        ids.add(er.event_id)

    # Redirect to run chooser with collected event IDs
    return choose_run(request, p, list(ids))


def activate_feature_assoc(request: HttpRequest, cod: str, p: str = None) -> HttpResponseRedirect:
    """Activate a feature for an association.

    This function enables a specific feature for an association by adding it to
    the association's features many-to-many relationship. Only overall features
    can be activated at the association level.

    Args:
        request: Django HTTP request object containing user and association context
        cod: Feature slug/code identifying the feature to activate
        p: Optional URL path to redirect to after successful activation.
           If not provided, redirects to the feature's default view.

    Returns:
        HttpResponseRedirect: Redirect response to either the specified path
        or the feature's associated permission view.

    Raises:
        Http404: If the feature doesn't exist or is not marked as 'overall'
        PermissionError: If the user lacks the 'exe_features' permission
    """
    # Retrieve the feature or return 404 if not found
    feature = get_object_or_404(Feature, slug=cod)

    # Ensure the feature is available at association level
    if not feature.overall:
        raise Http404("feature not overall")

    # Verify user has permission to manage association features
    if not has_assoc_permission(request, {}, "exe_features"):
        raise PermissionError()

    # Get the current association and add the feature to it
    assoc = get_object_or_404(Association, pk=request.assoc["id"])
    assoc.features.add(feature)
    assoc.save()

    # Display success message to the user
    messages.success(request, _("Feature activated") + ":" + feature.name)

    # Redirect to specified path or feature's default view
    if p:
        return redirect("/" + p)

    # Get the first associated permission's view name for redirection
    view_name = feature.assoc_permissions.first().slug
    return redirect(reverse(view_name))


def activate_feature_event(request: HttpRequest, s: str, cod: str, p: str = None) -> HttpResponseRedirect:
    """Activate a feature for a specific event.

    Activates a feature for an event by adding it to the event's features collection.
    Only non-overall features can be activated for specific events. Requires orga_features
    permission for the event.

    Args:
        request: Django HTTP request object containing user and session data
        s: Event slug identifier used to locate the target event
        cod: Feature slug/code identifying the feature to activate
        p: Optional URL path to redirect to after successful activation.
           If not provided, redirects to the feature's default view.

    Returns:
        HttpResponseRedirect: Redirect response to either the specified path
        or the feature's default event view.

    Raises:
        Http404: If the feature doesn't exist or is marked as overall
                (organization-wide rather than event-specific)
        PermissionError: If the user lacks orga_features permission for the event
    """
    # Retrieve the feature object or return 404 if not found
    feature = get_object_or_404(Feature, slug=cod)

    # Prevent activation of overall features at event level
    if feature.overall:
        raise Http404("feature overall")

    # Get event context and verify user has permission to manage features
    ctx = get_event_run(request, s)
    if not has_event_permission(request, {}, ctx["event"].slug, "orga_features"):
        raise PermissionError()

    # Add the feature to the event's features collection
    ctx["event"].features.add(feature)
    ctx["event"].save()

    # Display success message to user
    messages.success(request, _("Feature activated") + ":" + feature.name)

    # Redirect to specified path or feature's default view
    if p:
        return redirect("/" + p)

    # Get the default view name from feature's event permissions
    view_name = feature.event_permissions.first().slug
    return redirect(reverse(view_name, kwargs={"s": s}))


def toggle_sidebar(request: HttpRequest) -> JsonResponse:
    """Toggle the sidebar open/closed state in user session.

    Args:
        request: Django HTTP request object containing session data.

    Returns:
        JsonResponse: Status response indicating successful toggle operation.
    """
    # Define session key for sidebar state
    key = "is_sidebar_open"

    # Toggle existing state or set default to True if not present
    if key in request.session:
        request.session[key] = not request.session[key]
    else:
        request.session[key] = True

    # Return success response
    return JsonResponse({"status": "success"})


def debug_mail(request: HttpRequest) -> HttpResponseRedirect:
    """Send reminder emails to all registrations for debugging purposes.

    This function is designed for development and testing environments only.
    It iterates through all registrations and sends various types of reminder
    emails including profile completion, membership status, membership fees,
    and payment reminders.

    Args:
        request (HttpRequest): The Django HTTP request object containing
            environment information and user context.

    Returns:
        HttpResponseRedirect: Redirect response to the home page after
            processing all reminder emails.

    Raises:
        Http404: If the current environment is not 'dev' or 'test',
            preventing execution in production environments.

    Note:
        This function processes ALL registrations in the database, which
        could result in a large number of emails being sent. Use with caution
        even in development environments.
    """
    # Security check: only allow execution in development/test environments
    if request.enviro not in ["dev", "test"]:
        raise Http404()

    # Iterate through all registrations and send reminder emails
    # This includes profile, membership, fee, and payment reminders
    for reg in Registration.objects.all():
        # Send profile completion reminder
        remember_profile(reg)

        # Send membership status reminder
        remember_membership(reg)

        # Send membership fee reminder
        remember_membership_fee(reg)

        # Send payment reminder
        remember_pay(reg)

    # Redirect to home page after processing all reminders
    return redirect("home")


def debug_slug(request: HttpRequest, s: str = "") -> HttpResponseRedirect:
    """Set debug slug in session for development testing.

    This function allows setting a debug slug in the user's session for testing
    purposes. It's restricted to development and test environments only to prevent
    misuse in production.

    Args:
        request (HttpRequest): Django HTTP request object containing session data
        s (str, optional): Debug slug string to store in session. Defaults to "".

    Returns:
        HttpResponseRedirect: Redirect response to the home page after setting slug.

    Raises:
        Http404: If the current environment is not 'dev' or 'test'.

    Example:
        >>> debug_slug(request, "test-org")  # Sets debug slug to "test-org"
        >>> debug_slug(request)  # Sets debug slug to empty string
    """
    # Check if current environment allows debug functionality
    if request.enviro not in ["dev", "test"]:
        raise Http404()

    # Store the debug slug in the user's session
    request.session["debug_slug"] = s

    # Redirect user back to home page
    return redirect("home")


def ticket(request: HttpRequest, s: str = "") -> HttpResponse:
    """Handle support ticket creation and submission.

    Displays ticket form and processes ticket submissions.
    Associates tickets with current association and user if authenticated.

    Args:
        request: Django HTTP request object containing POST data and user info
        s: Optional reason/category for the ticket, defaults to empty string

    Returns:
        HttpResponse: Rendered ticket form template or redirect to home after
                     successful submission

    Note:
        - Requires request.assoc to be set by middleware
        - Auto-associates authenticated users with their member profile
        - Shows success message and redirects to home on valid submission
    """
    # Initialize context with reason parameter
    ctx = {"reason": s}

    # Handle POST request - form submission
    if request.POST:
        form = LarpManagerTicketForm(request.POST, request.FILES, request=request, ctx=ctx)

        # Process valid form submission
        if form.is_valid():
            # Create ticket instance without saving to DB yet
            lm_ticket = form.save(commit=False)

            # Associate ticket with current organization
            lm_ticket.assoc_id = request.assoc["id"]

            # Set reason if provided in URL parameter
            if s:
                lm_ticket.reason = s

            # Link authenticated user to their member profile
            if request.user.is_authenticated:
                lm_ticket.member = request.user.member

            # Save ticket to database
            lm_ticket.save()

            # Show success message and redirect
            messages.success(request, _("Your request has been sent, we will reply as soon as possible!"))
            return redirect("home")
    else:
        # Handle GET request - display empty form
        form = LarpManagerTicketForm(request=request, ctx=ctx)

    # Add form to context and render template
    ctx["form"] = form
    return render(request, "larpmanager/member/ticket.html", ctx)


def is_suspicious_user_agent(user_agent: str) -> bool:
    """Check if a user agent string appears to be from a bot.

    This function performs a case-insensitive search for known bot keywords
    in the provided user agent string to identify automated requests.

    Args:
        user_agent: User agent string to check for bot indicators.

    Returns:
        True if user agent appears to be from a bot, False otherwise.

    Example:
        >>> is_suspicious_user_agent("Mozilla/5.0 (compatible; Googlebot/2.1)")
        True
        >>> is_suspicious_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        False
    """
    # Define common bot identifiers found in user agent strings
    known_bots = ["bot", "crawler", "spider", "http", "archive", "wget", "curl"]

    # Check if any bot keyword exists in the lowercase user agent string
    return any(bot in user_agent.lower() for bot in known_bots)


@ratelimit(key="ip", rate="5/m", block=True)
def discord(request: HttpRequest) -> Union[HttpResponse, HttpResponseRedirect, HttpResponseForbidden]:
    """Handle Discord invite page with bot protection.

    This endpoint is rate-limited and provides protection against bots by checking
    user agents and requiring form validation before redirecting to the Discord server.

    Args:
        request (HttpRequest): Django HTTP request object containing user agent
            and POST data for form validation.

    Returns:
        HttpResponse: Rendered Discord form template when GET request or invalid form.
        HttpResponseRedirect: Redirect to Discord server URL when form is valid.
        HttpResponseForbidden: Error response when suspicious bot is detected.

    Raises:
        None: Function handles all error cases internally.
    """
    # Extract user agent from request headers for bot detection
    user_agent = request.META.get("HTTP_USER_AGENT", "")

    # Block suspicious bots based on user agent analysis
    if is_suspicious_user_agent(user_agent):
        return HttpResponseForbidden("Bots not allowed.")

    # Handle POST request with form validation
    if request.POST:
        form = LarpManagerCheck(request.POST, request=request)

        # Redirect to Discord server if form validation passes
        if form.is_valid():
            return redirect("https://discord.gg/C4KuyQbuft")
    else:
        # Initialize empty form for GET requests
        form = LarpManagerCheck(request=request)

    # Prepare template context and render Discord form page
    ctx = {"form": form}
    return render(request, "larpmanager/larpmanager/discord.html", ctx)


@login_required
def join(request: HttpRequest) -> HttpResponse:
    """Handle user joining an association.

    Processes association joining form and sends welcome messages
    and emails upon successful joining.

    Args:
        request: Django HTTP request object (must be authenticated)

    Returns:
        Rendered join form template or redirect response after successful joining

    Raises:
        Redirect: If context contains redirect URL or after successful joining
    """
    # Get context and check for redirect requirements
    ctx = get_lm_contact(request)
    if "red" in ctx:
        return redirect(ctx["red"])

    # Process the join form and attempt to join association
    assoc = _join_form(ctx, request)

    # Handle successful association joining
    if assoc:
        # Display success message to user
        messages.success(request, _("Welcome to %(name)s!") % {"name": request.assoc["name"]})

        # Send welcome email for default skin associations
        if request.assoc["skin_id"] == 1:
            join_email(assoc)

        # Redirect to management page for the joined association
        return redirect("after_login", subdomain=assoc.slug, path="manage")

    # Render join form template if joining was not successful
    return render(request, "larpmanager/larpmanager/join.html", ctx)


def _join_form(ctx: dict, request) -> Association | None:
    """Process association creation form for new users.

    Handles form validation, association creation, user role assignment,
    and admin notifications for new organizations.

    Args:
        ctx: Context dictionary to update with form data.
        request: Django HTTP request object containing POST data and user info.

    Returns:
        Created Association object if form submission is successful and valid,
        None if GET request or form validation fails.

    Note:
        Updates ctx dictionary with form instance for template rendering.
        Sends email notifications to all configured admins upon successful creation.
    """
    if request.method == "POST":
        # Initialize and validate the association creation form
        form = FirstAssociationForm(request.POST, request.FILES)
        if form.is_valid():
            # Create association with inherited skin from request context
            assoc = form.save(commit=False)
            assoc.skin_id = request.assoc["skin_id"]
            assoc.save()

            # Create admin role for the new association and assign creator
            (ar, created) = AssocRole.objects.get_or_create(assoc=assoc, number=1, name="Admin")
            ar.members.add(request.user.member)
            ar.save()

            # Update membership status to joined for the creator
            el = get_user_membership(request.user.member, assoc.id)
            el.status = MembershipStatus.JOINED
            el.save()

            # Send notification emails to all configured administrators
            for _name, email in conf_settings.ADMINS:
                subj = _("New organization created")
                body = _("Name: %(name)s, slug: %(slug)s, creator: %(user)s %(email)s") % {
                    "name": assoc.name,
                    "slug": assoc.slug,
                    "user": request.user.member,
                    "email": request.user.member.email,
                }
                my_send_mail(subj, body, email)

            # return redirect('first', assoc=assoc.slug)
            return assoc
    else:
        # Initialize empty form for GET requests
        form = FirstAssociationForm()

    # Add form to context for template rendering
    ctx["form"] = form
    return None


@cache_page(60 * 15)
def discover(request: HttpRequest) -> HttpResponse:
    """Display discovery page with featured content.

    Shows the LarpManager discovery page with featured items ordered by their
    specified order value. The page includes contact information and is marked
    as an index page for navigation purposes.

    Args:
        request (HttpRequest): Django HTTP request object containing user session
            and request metadata.

    Returns:
        HttpResponse: Rendered discover page template with context containing
            contact information, index flag, and ordered discover items.

    Note:
        The docstring mentions 15-minute caching but no caching is currently
        implemented in this function.
    """
    # Get base context with LarpManager contact information
    ctx = get_lm_contact(request)

    # Mark this page as an index page for navigation
    ctx["index"] = True

    # Fetch and order all discover items by their order field
    ctx["discover"] = LarpManagerDiscover.objects.order_by("order")

    # Render the discover template with the prepared context
    return render(request, "larpmanager/larpmanager/discover.html", ctx)


@override("en")
def tutorials(request: HttpRequest, slug: Optional[str] = None) -> HttpResponse:
    """Display tutorial pages with navigation.

    Shows individual tutorials with previous/next navigation.
    Always rendered in English locale.

    Args:
        request: Django HTTP request object.
        slug: Optional tutorial slug, defaults to first tutorial if None.

    Returns:
        HttpResponse: Rendered tutorial page with navigation context.

    Raises:
        Http404: If tutorial with specified slug doesn't exist.
    """
    # Initialize base context with contact information
    ctx = get_lm_contact(request)
    ctx["index"] = True

    try:
        # Get tutorial by slug or fetch first tutorial by order
        if slug:
            tutorial = LarpManagerTutorial.objects.get(slug=slug)
        else:
            tutorial = LarpManagerTutorial.objects.order_by("order").first()
            ctx["intro"] = True
    except ObjectDoesNotExist as err:
        raise Http404("tutorial not found") from err

    if tutorial:
        # Set current tutorial order for navigation
        order = tutorial.order
        ctx["seq"] = order

        # Get all tutorials ordered by sequence for navigation
        que = LarpManagerTutorial.objects.order_by("order")
        ctx["list"] = que.values_list("name", "order", "slug")

        # Initialize navigation links
        ctx["next"] = None
        ctx["prev"] = None

        # Find previous and next tutorials based on order
        for el in ctx["list"]:
            if el[1] < order:
                ctx["prev"] = el
            if el[1] > order and not ctx["next"]:
                ctx["next"] = el

    # Check if page should be displayed in iframe
    ctx["iframe"] = request.GET.get("in_iframe") == "1"
    ctx["opened"] = tutorial

    return render(request, "larpmanager/larpmanager/tutorials.html", ctx)


@cache_page(60 * 15)
def guides(request: HttpRequest) -> HttpResponse:
    """Display list of published guides for LarpManager users.

    Renders a template showing all published LarpManager guides ordered by
    their number field. Includes standard LarpManager contact information
    in the template context.

    Args:
        request: The Django HTTP request object containing user session
                and request metadata.

    Returns:
        An HttpResponse object with the rendered guides template containing
        the list of published guides and contact information.
    """
    # Get base context with LarpManager contact information
    ctx = get_lm_contact(request)

    # Retrieve all published guides ordered by number field
    ctx["list"] = LarpManagerGuide.objects.filter(published=True).order_by("number")

    # Set index flag for template rendering
    ctx["index"] = True

    # Render and return the guides template with context
    return render(request, "larpmanager/larpmanager/guides.html", ctx)


def guide(request: HttpRequest, slug: str) -> HttpResponse:
    """Display a specific guide article by slug.

    Retrieves and displays a published LarpManager guide article based on the
    provided slug. Sets up Open Graph metadata for social media sharing.

    Args:
        request: Django HTTP request object containing user session and metadata
        slug: URL slug identifier of the guide article to display

    Returns:
        HttpResponse: Rendered guide template with article content and metadata

    Raises:
        Http404: If guide with given slug is not found or not published
    """
    # Initialize context with base LarpManager contact information
    ctx = get_lm_contact(request)
    ctx["index"] = True

    # Retrieve the published guide article by slug
    try:
        ctx["guide"] = LarpManagerGuide.objects.get(slug=slug, published=True)
    except ObjectDoesNotExist as err:
        raise Http404("guide not found") from err

    # Set up Open Graph metadata for social media sharing
    ctx["og_image"] = ctx["guide"].thumb.url
    ctx["og_title"] = f"{ctx['guide'].title} - LarpManager"
    ctx["og_description"] = f"{ctx['guide'].description} - LarpManager"

    # Render and return the guide template with populated context
    return render(request, "larpmanager/larpmanager/guide.html", ctx)


@cache_page(60 * 15)
def privacy(request: HttpRequest) -> HttpResponse:
    """Display privacy policy page.

    Shows association-specific privacy text with 15-minute caching.

    Args:
        request (HttpRequest): Django HTTP request object containing
            association information in request.assoc

    Returns:
        HttpResponse: Rendered privacy policy page with association
            contact information and privacy text
    """
    # Get base context with association contact information
    ctx = get_lm_contact(request)

    # Add association-specific privacy policy text to context
    ctx.update({"text": get_assoc_text(request.assoc["id"], AssocTextType.PRIVACY)})

    # Render and return the privacy policy template
    return render(request, "larpmanager/larpmanager/privacy.html", ctx)


@cache_page(60 * 15)
def usage(request: HttpRequest) -> HttpResponse:
    """Display usage/terms page with cached content.

    This view renders the usage guidelines and terms page for the application.
    The page content is cached for 15 minutes to improve performance.

    Parameters
    ----------
    request : HttpRequest
        The Django HTTP request object containing user session and metadata.

    Returns
    -------
    HttpResponse
        Rendered HTML response containing the usage/terms page with context data.

    Notes
    -----
    The view automatically includes contact information and sets index flag to True
    for navigation purposes.
    """
    # Get contact information and base context for the organization
    ctx = get_lm_contact(request)

    # Set index flag to True for proper navigation highlighting
    ctx["index"] = True

    # Render the usage template with the prepared context
    return render(request, "larpmanager/larpmanager/usage.html", ctx)


@cache_page(60 * 15)
def about_us(request: HttpRequest) -> HttpResponse:
    """Display about us page with platform information.

    This view renders the about us page for the platform, providing general
    information about the service. The response is cached for 15 minutes
    to improve performance.

    Args:
        request (HttpRequest): Django HTTP request object containing
            request metadata and user information.

    Returns:
        HttpResponse: Rendered HTML response containing the about us page
            with platform contact information and index context.

    Note:
        The page includes contact information retrieved via get_lm_contact()
        and sets index=True for navigation context.
    """
    # Get platform contact information and base context
    ctx = get_lm_contact(request)

    # Set index flag for navigation context
    ctx["index"] = True

    # Render and return the about us template with context
    return render(request, "larpmanager/larpmanager/about_us.html", ctx)


def get_lm_contact(request: HttpRequest, check: bool = True) -> dict:
    """Get base context for LarpManager contact pages.

    This function creates a context dictionary for rendering LarpManager contact
    pages. It validates that the user is accessing the main site (not an
    association-specific site) when check=True.

    Args:
        request: Django HTTP request object containing user and site information
        check: Whether to verify user is on main site. Defaults to True.

    Returns:
        Dictionary containing:
            - lm: Integer flag (1) indicating LarpManager context
            - contact_form: Initialized LarpManagerContact form instance
            - platform: String identifier for the platform name

    Raises:
        MainPageError: When check=True and user is accessing an association site
            (request.assoc["id"] > 0)

    Example:
        >>> context = get_lm_contact(request)
        >>> # Returns: {'lm': 1, 'contact_form': <form>, 'platform': 'LarpManager'}
    """
    # Validate user is on main site if check is enabled
    if check and request.assoc["id"] > 0:
        raise MainPageError(request)

    # Build base context dictionary with form and platform info
    ctx = {"lm": 1, "contact_form": LarpManagerContact(request=request), "platform": "LarpManager"}

    return ctx


@login_required
def lm_list(request: HttpRequest) -> HttpResponse:
    """Display list of associations for admin users.

    Shows associations ordered by total registrations count.
    Requires admin permissions.

    Args:
        request (HttpRequest): Django HTTP request object (must be authenticated admin)

    Returns:
        HttpResponse: Rendered association list page with association context

    Raises:
        PermissionDenied: If user lacks admin permissions
    """
    # Check admin permissions and get base context
    ctx = check_lm_admin(request)

    # Query associations with registration count annotation
    # Order by total registrations descending to show most active first
    ctx["list"] = Association.objects.annotate(total_registrations=Count("events__runs__registrations")).order_by(
        "-total_registrations"
    )

    # Render the association list template with context
    return render(request, "larpmanager/larpmanager/list.html", ctx)


@login_required
def lm_payments(request: HttpRequest) -> HttpResponse:
    """Display payment management page for admin users.

    Shows unpaid runs with minimum registration requirements and calculates
    payment totals by year for administrative oversight.

    Args:
        request: Django HTTP request object. Must be from authenticated admin user.

    Returns:
        HttpResponse: Rendered payments management page with unpaid runs list,
                     total unpaid amount, and yearly payment totals.

    Raises:
        PermissionDenied: If user lacks admin permissions (handled by check_lm_admin).
    """
    # Verify admin permissions and get base context
    ctx = check_lm_admin(request)
    min_registrations = 5

    # Get all unpaid runs ordered by start date
    que = Run.objects.filter(paid__isnull=True).order_by("start")

    # Initialize lists and totals for unpaid runs
    ctx["list"] = []
    ctx["total"] = 0

    # Process each unpaid run
    for el in que:
        # Skip runs without a plan
        if not el.plan:
            continue

        # Calculate payment details for this run
        get_run_lm_payment(el)

        # Skip runs with insufficient registrations
        if el.active_registrations < min_registrations:
            continue

        # Add qualifying run to list and update total
        ctx["list"].append(el)
        ctx["total"] += el.total

    # Get the oldest run date to determine year range
    que = Run.objects.aggregate(oldest_date=Min("start"))
    ctx["totals"] = {}

    # Calculate yearly payment totals from current year to oldest
    for year in list(range(datetime.today().year, que["oldest_date"].year - 1, -1)):
        start_of_year = date(year, 1, 1)
        end_of_year = date(year, 12, 31)

        # Sum all paid amounts for runs in this year
        total_paid = Run.objects.filter(start__range=(start_of_year, end_of_year)).aggregate(total=Sum("paid"))["total"]
        ctx["totals"][year] = total_paid

    return render(request, "larpmanager/larpmanager/payments.html", ctx)


def get_run_lm_payment(el) -> None:
    """Calculate payment details for a run based on features and registrations.

    This function computes the total number of features (association + event level),
    counts active registrations excluding staff/waiting/NPC tiers, and calculates
    the total payment amount based on the association's plan type.

    Args:
        el: Run object to calculate payment for. Must have event attribute with
            assoc_id and event_id properties, and plan attribute.

    Returns:
        None: Function modifies the input object in-place.

    Side Effects:
        Modifies the el object by setting:
        - features: Total count of association and event features
        - active_registrations: Count of non-staff/waiting/NPC registrations
        - total: Payment amount based on plan type
    """
    # Calculate total features from both association and event levels
    el.features = len(get_assoc_features(el.event.assoc_id)) + len(get_event_features(el.event_id))

    # Count active registrations excluding staff, waiting list, and NPC tiers
    el.active_registrations = (
        Registration.objects.filter(run__id=el.id, cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.WAITING, TicketTier.NPC])
        .count()
    )

    # Calculate total payment based on association plan
    if el.plan == AssociationPlan.FREE:
        el.total = 0
    elif el.plan == AssociationPlan.SUPPORT:
        el.total = el.active_registrations


@login_required
def lm_payments_confirm(request: HttpRequest, r: int) -> HttpResponseRedirect:
    """Confirm payment for a specific run.

    This function marks a run as paid by setting the paid amount to the calculated
    total. It requires admin permissions to execute.

    Args:
        request (HttpRequest): Django HTTP request object. Must be from an
            authenticated admin user.
        r (int): Primary key of the Run instance to confirm payment for.

    Returns:
        HttpResponseRedirect: Redirect response to the payments list page.

    Raises:
        PermissionDenied: If the user doesn't have admin permissions.
        Run.DoesNotExist: If no run exists with the given primary key.
    """
    # Verify admin permissions before proceeding
    check_lm_admin(request)

    # Retrieve the run instance by primary key
    run = Run.objects.get(pk=r)

    # Calculate and update run payment details
    get_run_lm_payment(run)

    # Mark run as fully paid with the calculated total
    run.paid = run.total
    run.save()

    # Redirect back to the payments overview page
    return redirect("lm_payments")


@login_required
def lm_send(request: HttpRequest) -> HttpResponse:
    """Send bulk email to users.

    Provides a form interface for sending emails to multiple recipients.
    Requires admin permissions to access this functionality.

    Args:
        request (HttpRequest): Django HTTP request object containing user session
            and form data. Must be from an authenticated admin user.

    Returns:
        HttpResponse: Either a rendered email form template for GET requests,
            or a redirect response after successful email queue submission for
            valid POST requests.

    Raises:
        PermissionDenied: If user lacks admin permissions (handled by check_lm_admin).
    """
    # Verify admin permissions and get base context
    ctx = check_lm_admin(request)

    # Handle form submission
    if request.method == "POST":
        form = SendMailForm(request.POST)

        # Process valid form data
        if form.is_valid():
            # Extract email parameters from form
            players = request.POST["players"]
            subj = request.POST["subject"]
            body = request.POST["body"]

            # Queue email for background processing
            send_mail_exec(players, subj, body)
            messages.success(request, _("Mail added to queue!"))

            # Redirect to prevent duplicate submissions
            return redirect(request.path_info)
    else:
        # Initialize empty form for GET requests
        form = SendMailForm()

    # Add form to template context and render
    ctx["form"] = form
    return render(request, "larpmanager/exe/users/send_mail.html", ctx)


@login_required
def lm_profile(request: HttpRequest) -> HttpResponse:
    """Display performance profiling data aggregated by domain and view function.

    Shows view function performance metrics computed from individual executions.
    Calculates average duration and total calls for each domain/view combination.
    Requires admin permissions.

    Args:
        request: Django HTTP request object (must be authenticated admin)

    Returns:
        HttpResponse: Rendered profiling data page with aggregated metrics

    Note:
        Only shows data from the last 168 hours (7 days) and limits results to top 50
        entries ordered by total duration.
    """
    # Check admin permissions and get base context
    ctx = check_lm_admin(request)

    # Set time threshold to 7 days ago (168 hours)
    st = datetime.now() - timedelta(hours=168)

    # Aggregate data from individual executions by domain and view_func_name
    # Calculate average duration and total calls directly from execution records
    # Order by total duration descending and limit to top 50 results
    ctx["res"] = (
        LarpManagerProfiler.objects.filter(created__gte=st)
        .values("domain", "view_func_name")
        .annotate(
            total_calls=Count("id"),
            avg_duration=Avg("duration"),
            total_duration=Sum("duration"),
        )
        .order_by("-total_duration")[:50]
    )

    # Render the profiling template with aggregated data
    return render(request, "larpmanager/larpmanager/profile.html", ctx)


@ratelimit(key="ip", rate="5/m", block=True)
def donate(request: HttpRequest) -> Union[HttpResponse, HttpResponseRedirect, HttpResponseForbidden]:
    """Handle donation page with bot protection.

    This rate-limited endpoint blocks suspicious bots and provides a form-protected
    redirect to the PayPal donation page. Users must pass bot detection and submit
    a valid form to access the donation link.

    Args:
        request (HttpRequest): Django HTTP request object containing user agent
            and POST data for form validation.

    Returns:
        HttpResponseForbidden: If suspicious bot activity is detected based on
            user agent analysis.
        HttpResponseRedirect: If form is valid, redirects to PayPal donation page.
        HttpResponse: Renders donation form template for GET requests or invalid
            form submissions.

    Note:
        Uses LarpManagerCheck form for additional bot protection and CSRF validation.
    """
    # Extract and validate user agent to detect suspicious bot activity
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    if is_suspicious_user_agent(user_agent):
        return HttpResponseForbidden("Bots not allowed.")

    # Handle form submission and validation for POST requests
    if request.POST:
        form = LarpManagerCheck(request.POST, request=request)
        # Redirect to PayPal donation page if form passes all validations
        if form.is_valid():
            return redirect("https://www.paypal.com/paypalme/mscanagatta")
    else:
        # Initialize empty form for GET requests
        form = LarpManagerCheck(request=request)

    # Render donation template with form context
    ctx = {"form": form}
    return render(request, "larpmanager/larpmanager/donate.html", ctx)


def debug_user(request: HttpRequest, mid: int) -> None:
    """Login as a specific user for debugging purposes.

    Allows admin users to login as another user for debugging.
    Requires admin permissions.

    Args:
        request: Django HTTP request object
        mid: Member ID to login as

    Raises:
        PermissionDenied: If user doesn't have admin permissions
        Member.DoesNotExist: If member with given ID doesn't exist

    Side Effects:
        Logs in as the specified user, replacing current session
    """
    # Verify admin permissions before proceeding
    check_lm_admin(request)

    # Retrieve the target member object
    member = Member.objects.get(pk=mid)

    # Perform login with appropriate backend
    login(request, member.user, backend=get_user_backend())


@ratelimit(key="ip", rate="5/m", block=True)
def demo(request: HttpRequest) -> HttpResponse:
    """Handle demo organization creation with bot protection.

    This rate-limited endpoint blocks suspicious bots and creates demo
    organizations for testing purposes. It validates user agents and
    processes form submissions to generate temporary demo environments.

    Args:
        request (HttpRequest): Django HTTP request object containing
            user agent headers and potential POST data

    Returns:
        HttpResponse: Rendered demo form template or redirect to the
            newly created demo organization
        HttpResponseForbidden: Response with 403 status if bot is detected
            based on suspicious user agent patterns

    Raises:
        ValidationError: When form validation fails during POST processing
    """
    # Extract and validate user agent to detect potential bots
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    if is_suspicious_user_agent(user_agent):
        return HttpResponseForbidden("Bots not allowed.")

    # Process form submission for demo creation
    if request.POST:
        form = LarpManagerCheck(request.POST, request=request)
        # Validate form data and create demo if valid
        if form.is_valid():
            return _create_demo(request)
    else:
        # Initialize empty form for GET requests
        form = LarpManagerCheck(request=request)

    # Prepare template context and render demo form
    ctx = {"form": form}
    return render(request, "larpmanager/larpmanager/demo.html", ctx)


def _create_demo(request: HttpRequest) -> HttpResponseRedirect:
    """Create a demo organization with test user.

    Creates a new demo association with a test admin user and logs the user
    in automatically. The demo organization is created with a unique slug
    and configured with default settings for testing purposes.

    Args:
        request: Django HTTP request object containing user session data
            and association context information.

    Returns:
        HttpResponseRedirect: Redirect response to the demo organization's
            management dashboard where the newly created admin user can
            begin using the system.

    Note:
        The created demo organization inherits the skin configuration from
        the current request's association context.
    """
    # Generate unique primary key for new association
    new_pk = Association.objects.order_by("-pk").values_list("pk", flat=True).first()
    new_pk += 1

    # Create demo association with unique slug and inherited skin
    assoc = Association.objects.create(
        slug=f"test{new_pk}", name="Demo Organization", skin_id=request.assoc["skin_id"], demo=True
    )

    # Create test admin user with demo credentials
    (user, cr) = User.objects.get_or_create(email=f"test{new_pk}@demo.it", username=f"test{new_pk}")
    user.password = "pippo"
    user.save()

    # Configure member profile with demo information
    member = user.member
    member.name = "Demo"
    member.surname = "Admin"
    member.save()

    # Create admin role and assign member with full permissions
    (ar, created) = AssocRole.objects.get_or_create(assoc=assoc, number=1, name="Admin")
    ar.members.add(member)
    ar.save()

    # Set membership status to active/joined
    el = get_user_membership(member, assoc.id)
    el.status = MembershipStatus.JOINED
    el.save()

    # Authenticate and log in the demo user
    login(request, user, backend=get_user_backend())

    return redirect("after_login", subdomain=assoc.slug, path="manage")
