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
from typing import Optional

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
from larpmanager.utils.base import get_context, get_event_context
from larpmanager.utils.exceptions import MainPageError, PermissionError
from larpmanager.utils.tasks import my_send_mail, send_mail_exec
from larpmanager.utils.text import get_assoc_text
from larpmanager.views.user.member import get_user_backend


def lm_home(request):
    """Display the LarpManager home page with promoters and reviews.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered home page template with context data
    """
    context = get_lm_contact(request)
    context["index"] = True

    if context["base_domain"] == "ludomanager.it":
        return ludomanager(context, request)

    context.update(get_cache_lm_home())
    random.shuffle(context["promoters"])
    random.shuffle(context["reviews"])

    return render(request, "larpmanager/larpmanager/home.html", context)


def ludomanager(context, request):
    """Render the LudoManager skin version of the home page.

    Args:
        context: Context dictionary to update
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered LudoManager template
    """
    context["assoc_skin"] = "LudoManager"
    context["platform"] = "LudoManager"
    return render(request, "larpmanager/larpmanager/skin/ludomanager.html", context)


@csrf_exempt
def contact(request):
    """Handle contact form submissions and display contact page.

    Processes contact form data and sends emails to administrators when valid
    submissions are received.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered contact template with form or success state
    """
    context = {}
    done = False
    if request.POST:
        form = LarpManagerContact(request.POST, request=request)
        if form.is_valid():
            ct = form.cleaned_data["email"]
            for _name, email in conf_settings.ADMINS:
                subj = "LarpManager contact - " + ct
                body = form.cleaned_data["content"]
                my_send_mail(subj, body, email)
                done = True
    else:
        form = LarpManagerContact(request=request)

    if not done:
        context["form"] = form

    return render(request, "larpmanager/larpmanager/contact.html", context)


def go_redirect(request, slug, path, base_domain="larpmanager.com"):
    """Redirect user to association-specific subdomain or main domain.

    Args:
        request: Django HTTP request object
        slug: Association slug for subdomain
        path: Path to append to URL
        base_domain: Base domain name (default: "larpmanager.com")

    Returns:
        HttpResponseRedirect: Redirect to appropriate URL
    """
    if request.enviro in ["dev", "test"]:
        return redirect("http://127.0.0.1:8000/")

    if slug:
        new_path = f"https://{slug}.{base_domain}/"
    else:
        new_path = f"https://{base_domain}/"

    if path:
        new_path += path

    return redirect(new_path)


def choose_assoc(request, redirect_path, association_slugs):
    """Handle association selection when multiple associations are available.

    Args:
        request: Django HTTP request object
        redirect_path: URL path to redirect to after selection
        association_slugs: List of association slugs to choose from

    Returns:
        HttpResponse: Redirect to selected association or selection form
    """
    if len(association_slugs) == 0:
        return render(request, "larpmanager/larpmanager/na_assoc.html")
    elif len(association_slugs) == 1:
        return go_redirect(request, association_slugs[0], redirect_path)
    else:
        # show page to choose them
        if request.POST:
            form = RedirectForm(request.POST, slugs=association_slugs)
            if form.is_valid():
                selected_index = int(form.cleaned_data["slug"])
                if selected_index < len(association_slugs):
                    return go_redirect(request, association_slugs[selected_index], redirect_path)
        else:
            form = RedirectForm(slugs=association_slugs)
        return render(
            request,
            "larpmanager/larpmanager/redirect.html",
            {"form": form, "name": "association"},
        )


def go_redirect_run(run, path):
    """Redirect to a specific run's URL on its association's domain.

    Args:
        run: Run object to redirect to
        path: URL path to append after the run slug

    Returns:
        HttpResponseRedirect: Redirect to the run's URL
    """
    full_url = f"https://{run.event.assoc.slug}.{run.event.assoc.skin.domain}/{run.get_slug()}/{path}"
    return redirect(full_url)


def choose_run(request, redirect_path, event_ids):
    """Handle run selection when multiple runs are available.

    Args:
        request: Django HTTP request object
        redirect_path: URL path to redirect to after selection
        event_ids: List of event IDs to get runs from

    Returns:
        HttpResponse: Redirect to selected run or selection form
    """
    available_runs = []
    run_display_names = []

    for run in Run.objects.filter(event_id__in=event_ids, end__gte=datetime.now()):
        available_runs.append(run)
        run_display_names.append(f"{run.search} - {run.event.assoc.slug}")

    if len(run_display_names) == 0:
        return render(request, "larpmanager/larpmanager/na_event.html")
    elif len(run_display_names) == 1:
        return go_redirect_run(available_runs[0], redirect_path)

    else:
        # show page to choose them
        if request.POST:
            form = RedirectForm(request.POST, slugs=run_display_names)
            if form.is_valid():
                selected_index = int(form.cleaned_data["slug"])
                if selected_index < len(run_display_names):
                    return go_redirect_run(available_runs[selected_index], redirect_path)
        else:
            form = RedirectForm(slugs=run_display_names)
        return render(
            request,
            "larpmanager/larpmanager/redirect.html",
            {"form": form, "name": "event"},
        )


@login_required
def redr(request, p):
    """Handle redirects based on user roles and permissions.

    Redirects users to appropriate associations or events based on their
    assigned roles and the requested path.

    Args:
        request: Django HTTP request object (must be authenticated)
        p: URL path to redirect to

    Returns:
        HttpResponse: Redirect to appropriate association or event selection
    """
    if not p.startswith("event/"):
        slugs = set()
        for ar in AssocRole.objects.filter(members=request.user.member).select_related("assoc"):
            slugs.add(ar.assoc.slug)
        # get all events where they have assoc role
        return choose_assoc(request, p, list(slugs))

    p = p.replace("event/", "")
    ids = set()
    for er in EventRole.objects.filter(members=request.user.member):
        ids.add(er.event_id)

    # get all events where they have event role
    return choose_run(request, p, list(ids))


def activate_feature_assoc(request: HttpRequest, cod: str, p: Optional[str] = None) -> HttpResponseRedirect:
    """Activate a feature for an association.

    Activates a feature by adding it to the association's features and redirects
    to either a specified path or the feature's default view.

    Args:
        request: Django HTTP request object containing user and association context
        cod: Feature slug/code to activate
        p: Optional URL path to redirect to after activation. If None, redirects
           to the feature's default view based on associated permissions

    Returns:
        HttpResponseRedirect to the specified path or feature's default view

    Raises:
        Http404: If feature doesn't exist or isn't marked as overall
        PermissionError: If user lacks exe_features permission for the association
    """
    context = get_context(request)
    # Retrieve the feature by slug, ensuring it exists
    feature = get_object_or_404(Feature, slug=cod)

    # Validate that this is an organization-wide feature
    if not feature.overall:
        raise Http404("feature not overall")

    # Verify user has permission to manage association features
    if not has_assoc_permission(request, context, "exe_features"):
        raise PermissionError()

    # Get the association from request context and activate the feature
    assoc = get_object_or_404(Association, pk=context["association_id"])
    assoc.features.add(feature)
    assoc.save()

    # Display success message to user
    messages.success(request, _("Feature activated") + ":" + feature.name)

    # Redirect to specified path or feature's default view
    if p:
        return redirect("/" + p)

    # Use the first associated permission's slug as the default view
    view_name = feature.assoc_permissions.first().slug
    return redirect(reverse(view_name))


def activate_feature_event(request: HttpRequest, event_slug: str, cod: str, p: str = None) -> HttpResponseRedirect:
    """Activate a feature for a specific event.

    Enables a non-overall feature for the specified event and redirects the user
    to either a custom path or the feature's default view.

    Args:
        request: Django HTTP request object containing user and session data
        event_slug: Event slug identifier used to locate the target event
        cod: Feature slug/code identifying which feature to activate
        p: Optional URL path to redirect to after successful activation.
           If None, redirects to the feature's default event view.

    Returns:
        HttpResponseRedirect: Redirect response to specified path or feature view

    Raises:
        Http404: If feature doesn't exist or is marked as overall (organization-wide)
        PermissionError: If user lacks orga_features permission for the event
    """
    # Retrieve the feature by slug, raise 404 if not found
    feature = get_object_or_404(Feature, slug=cod)

    # Ensure this is an event-specific feature, not organization-wide
    if feature.overall:
        raise Http404("feature overall")

    # Get event context and verify user has permission to manage features
    context = get_event_context(request, event_slug)
    if not has_event_permission(request, {}, context["event"].slug, "orga_features"):
        raise PermissionError()

    # Add the feature to the event's feature set and persist changes
    context["event"].features.add(feature)
    context["event"].save()

    # Display success message to user with feature name
    messages.success(request, _("Feature activated") + ":" + feature.name)

    # Redirect to custom path if provided, otherwise use feature's default view
    if p:
        return redirect("/" + p)

    # Get the first event permission's slug as the default view name
    view_name = feature.event_permissions.first().slug
    return redirect(reverse(view_name, kwargs={"event_slug": event_slug}))


def toggle_sidebar(request):
    """Toggle the sidebar open/closed state in user session.

    Args:
        request: Django HTTP request object

    Returns:
        JsonResponse: Status response indicating success
    """
    key = "is_sidebar_open"
    if key in request.session:
        request.session[key] = not request.session[key]
    else:
        request.session[key] = True
    return JsonResponse({"status": "success"})


def debug_mail(request):
    """Send reminder emails to all registrations for debugging.

    Only available in development and test environments.
    Sends profile, membership, membership fee, and payment reminders.

    Args:
        request: Django HTTP request object

    Returns:
        JsonResponse: Status response

    Raises:
        Http404: If not in dev or test environment
    """
    if request.enviro not in ["dev", "test"]:
        raise Http404()

    for reg in Registration.objects.all():
        remember_profile(reg)
        remember_membership(reg)
        remember_membership_fee(reg)
        remember_pay(reg)

    return redirect("home")


def debug_slug(request, assoc_slug=""):
    """Set debug slug in session for development testing.

    Only available in development and test environments.
    Sets a debug slug in the session for testing purposes.

    Args:
        request: Django HTTP request object
        assoc_slug: Debug slug to set in session

    Returns:
        HttpResponseRedirect: Redirect to home page

    Raises:
        Http404: If not in dev or test environment
    """
    if request.enviro not in ["dev", "test"]:
        raise Http404()

    request.session["debug_slug"] = assoc_slug
    return redirect("home")


def ticket(request, reason=""):
    """Handle support ticket creation and submission.

    Displays ticket form and processes ticket submissions.
    Associates tickets with current association and user if authenticated.

    Args:
        request: Django HTTP request object
        reason: Optional reason/category for the ticket

    Returns:
        HttpResponse: Rendered ticket form or redirect after successful submission
    """
    context = get_context(request)
    context.update({"reason": reason})
    if request.POST:
        form = LarpManagerTicketForm(request.POST, request.FILES, request=request, context=context)
        if form.is_valid():
            lm_ticket = form.save(commit=False)
            lm_ticket.assoc_id = context["association_id"]
            if reason:
                lm_ticket.reason = reason
            if request.user.is_authenticated:
                lm_ticket.member = request.user.member
            lm_ticket.save()
            messages.success(request, _("Your request has been sent, we will reply as soon as possible!"))
            return redirect("home")
    else:
        form = LarpManagerTicketForm(request=request, context=context)
    context["form"] = form
    return render(request, "larpmanager/member/ticket.html", context)


def is_suspicious_user_agent(user_agent_string):
    """Check if a user agent string appears to be from a bot.

    Args:
        user_agent_string (str): User agent string to check

    Returns:
        bool: True if user agent appears to be from a bot, False otherwise
    """
    known_bot_identifiers = ["bot", "crawler", "spider", "http", "archive", "wget", "curl"]
    return any(bot_identifier in user_agent_string.lower() for bot_identifier in known_bot_identifiers)


@ratelimit(key="ip", rate="5/m", block=True)
def discord(request):
    """Handle Discord invite page with bot protection.

    Rate-limited endpoint that blocks bots and provides
    a form-protected redirect to Discord server.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered Discord form or redirect to Discord server
        HttpResponseForbidden: If bot detected
    """
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    if is_suspicious_user_agent(user_agent):
        return HttpResponseForbidden("Bots not allowed.")

    if request.POST:
        form = LarpManagerCheck(request.POST, request=request)
        if form.is_valid():
            return redirect("https://discord.gg/C4KuyQbuft")
    else:
        form = LarpManagerCheck(request=request)
    context = {"form": form}
    return render(request, "larpmanager/larpmanager/discord.html", context)


@login_required
def join(request):
    """Handle user joining an association.

    Processes association joining form and sends welcome messages
    and emails upon successful joining.

    Args:
        request: Django HTTP request object (must be authenticated)

    Returns:
        HttpResponse: Rendered join form or redirect after successful joining
    """
    context = get_lm_contact(request)
    if "red" in context:
        return redirect(context["red"])

    joined_association = _join_form(context, request)
    if joined_association:
        # send message
        messages.success(request, _("Welcome to %(name)s!") % {"name": request.assoc["name"]})
        # send email
        if request.assoc["skin_id"] == 1:
            join_email(joined_association)
        # redirect
        return redirect("after_login", subdomain=joined_association.slug, path="manage")

    return render(request, "larpmanager/larpmanager/join.html", context)


def _join_form(context: dict, request) -> Association | None:
    """Process association creation form for new users.

    Handles form validation, association creation, user role assignment,
    and admin notifications for new organizations.

    Args:
        context: Context dictionary to update with form data.
        request: Django HTTP request object containing POST data and user info.

    Returns:
        Created Association object if form submission is successful and valid,
        None if GET request or form validation fails.

    Note:
        Updates context dictionary with form instance for template rendering.
        Sends email notifications to all configured admins upon successful creation.
    """
    if request.method == "POST":
        # Initialize and validate the association creation form
        form = FirstAssociationForm(request.POST, request.FILES)
        if form.is_valid():
            # Create association with inherited skin from request context
            new_association = form.save(commit=False)
            new_association.skin_id = request.assoc["skin_id"]
            new_association.save()

            # Create admin role for the new association and assign creator
            (admin_role, created) = AssocRole.objects.get_or_create(assoc=new_association, number=1, name="Admin")
            admin_role.members.add(context["member"])
            admin_role.save()

            # Update membership status to joined for the creator
            membership = get_user_membership(request.user.member, new_association.id)
            membership.status = MembershipStatus.JOINED
            membership.save()

            # Send notification emails to all configured administrators
            for _admin_name, admin_email in conf_settings.ADMINS:
                subject = _("New organization created")
                body = _("Name: %(name)s, slug: %(slug)s, creator: %(user)s %(email)s") % {
                    "name": new_association.name,
                    "slug": new_association.slug,
                    "user": context["member"],
                    "email": context["member"].email,
                }
                my_send_mail(subject, body, admin_email)

            # return redirect('first', assoc=new_association.slug)
            return new_association
    else:
        # Initialize empty form for GET requests
        form = FirstAssociationForm()

    # Add form to context for template rendering
    context["form"] = form
    return None


@cache_page(60 * 15)
def discover(request):
    """Display discovery page with featured content.

    Cached for 15 minutes. Shows LarpManager discover items
    ordered by their specified order.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered discover page template
    """
    context = get_lm_contact(request)
    context["index"] = True
    context["discover"] = LarpManagerDiscover.objects.order_by("order")
    return render(request, "larpmanager/larpmanager/discover.html", context)


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
    context = get_lm_contact(request)
    context["index"] = True

    try:
        # Get tutorial by slug or fetch first tutorial by order
        if slug:
            tutorial = LarpManagerTutorial.objects.get(slug=slug)
        else:
            tutorial = LarpManagerTutorial.objects.order_by("order").first()
            context["intro"] = True
    except ObjectDoesNotExist as err:
        raise Http404("tutorial not found") from err

    if tutorial:
        # Set current tutorial order for navigation
        order = tutorial.order
        context["seq"] = order

        # Get all tutorials ordered by sequence for navigation
        que = LarpManagerTutorial.objects.order_by("order")
        context["list"] = que.values_list("name", "order", "slug")

        # Initialize navigation links
        context["next"] = None
        context["prev"] = None

        # Find previous and next tutorials based on order
        for el in context["list"]:
            if el[1] < order:
                context["prev"] = el
            if el[1] > order and not context["next"]:
                context["next"] = el

    # Check if page should be displayed in iframe
    context["iframe"] = request.GET.get("in_iframe") == "1"
    context["opened"] = tutorial

    return render(request, "larpmanager/larpmanager/tutorials.html", context)


@cache_page(60 * 15)
def guides(request):
    """Display list of published guides for LarpManager users.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered guides template with list of published guides
    """
    context = get_lm_contact(request)
    context["list"] = LarpManagerGuide.objects.filter(published=True).order_by("number")
    context["index"] = True
    return render(request, "larpmanager/larpmanager/guides.html", context)


def guide(request, slug):
    """Display a specific guide article by slug.

    Args:
        request: Django HTTP request object
        slug: URL slug of the guide to display

    Returns:
        HttpResponse: Rendered guide template with article content

    Raises:
        Http404: If guide with given slug is not found or not published
    """
    context = get_lm_contact(request)
    context["index"] = True

    try:
        context["guide"] = LarpManagerGuide.objects.get(slug=slug, published=True)
    except ObjectDoesNotExist as err:
        raise Http404("guide not found") from err

    context["og_image"] = context["guide"].thumb.url
    context["og_title"] = f"{context['guide'].title} - LarpManager"
    context["og_description"] = f"{context['guide'].description} - LarpManager"

    return render(request, "larpmanager/larpmanager/guide.html", context)


@cache_page(60 * 15)
def privacy(request):
    """Display privacy policy page.

    Cached for 15 minutes. Shows association-specific privacy text.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered privacy policy page
    """
    context = get_lm_contact(request)
    context.update({"text": get_assoc_text(context["association_id"], AssocTextType.PRIVACY)})
    return render(request, "larpmanager/larpmanager/privacy.html", context)


@cache_page(60 * 15)
def usage(request):
    """Display usage/terms page.

    Cached for 15 minutes. Shows usage guidelines and terms.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered usage page
    """
    context = get_lm_contact(request)
    context["index"] = True
    return render(request, "larpmanager/larpmanager/usage.html", context)


@cache_page(60 * 15)
def about_us(request):
    """Display about us page.

    Cached for 15 minutes. Shows information about the platform.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered about us page
    """
    context = get_lm_contact(request)
    context["index"] = True
    return render(request, "larpmanager/larpmanager/about_us.html", context)


def get_lm_contact(request, check_main_site=True):
    """Get base context for LarpManager contact pages.

    Args:
        request: Django HTTP request object
        check_main_site: Whether to check if user is on main site (default True)

    Returns:
        dict: Base context with contact form and platform info

    Raises:
        MainPageError: If check_main_site=True and user is on association site
    """
    context = get_context(request)
    if check_main_site and context["association_id"] > 0:
        raise MainPageError(request)
    context.update({"lm": 1, "contact_form": LarpManagerContact(request=request), "platform": "LarpManager"})
    return context


@login_required
def lm_list(request):
    """Display list of associations for admin users.

    Shows associations ordered by total registrations count.
    Requires admin permissions.

    Args:
        request: Django HTTP request object (must be authenticated admin)

    Returns:
        HttpResponse: Rendered association list page
    """
    context = check_lm_admin(request)

    context["list"] = Association.objects.annotate(total_registrations=Count("events__runs__registrations")).order_by(
        "-total_registrations"
    )

    return render(request, "larpmanager/larpmanager/list.html", context)


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
    context = check_lm_admin(request)
    min_registrations = 5

    # Get all unpaid runs ordered by start date
    que = Run.objects.filter(paid__isnull=True).order_by("start")

    # Initialize lists and totals for unpaid runs
    context["list"] = []
    context["total"] = 0

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
        context["list"].append(el)
        context["total"] += el.total

    # Get the oldest run date to determine year range
    que = Run.objects.aggregate(oldest_date=Min("start"))
    context["totals"] = {}

    # Calculate yearly payment totals from current year to oldest
    for year in list(range(datetime.today().year, que["oldest_date"].year - 1, -1)):
        start_of_year = date(year, 1, 1)
        end_of_year = date(year, 12, 31)

        # Sum all paid amounts for runs in this year
        total_paid = Run.objects.filter(start__range=(start_of_year, end_of_year)).aggregate(total=Sum("paid"))["total"]
        context["totals"][year] = total_paid

    return render(request, "larpmanager/larpmanager/payments.html", context)


def get_run_lm_payment(run):
    """Calculate payment details for a run.

    Calculates features count, active registrations, and total payment
    based on association plan.

    Args:
        run: Run object to calculate payment for

    Side effects:
        Modifies run object with features, active_registrations, and total attributes
    """
    run.features = len(get_assoc_features(run.event.assoc_id)) + len(get_event_features(run.event_id))
    run.active_registrations = (
        Registration.objects.filter(run__id=run.id, cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.WAITING, TicketTier.NPC])
        .count()
    )
    if run.plan == AssociationPlan.FREE:
        run.total = 0
    elif run.plan == AssociationPlan.SUPPORT:
        run.total = run.active_registrations


@login_required
def lm_payments_confirm(request, r):
    """Confirm payment for a specific run.

    Marks a run as paid with calculated total.
    Requires admin permissions.

    Args:
        request: Django HTTP request object (must be authenticated admin)
        r: Run ID to confirm payment for

    Returns:
        HttpResponseRedirect: Redirect to payments list
    """
    check_lm_admin(request)
    run = Run.objects.get(pk=r)
    get_run_lm_payment(run)
    run.paid = run.total
    run.save()
    return redirect("lm_payments")


@login_required
def lm_send(request):
    """Send bulk email to users.

    Provides form for sending emails to multiple recipients.
    Requires admin permissions.

    Args:
        request: Django HTTP request object (must be authenticated admin)

    Returns:
        HttpResponse: Rendered email form or redirect after sending
    """
    context = check_lm_admin(request)
    if request.method == "POST":
        form = SendMailForm(request.POST)
        if form.is_valid():
            players = request.POST["players"]
            subj = request.POST["subject"]
            body = request.POST["body"]
            send_mail_exec(players, subj, body)
            messages.success(request, _("Mail added to queue!"))
            return redirect(request.path_info)
    else:
        form = SendMailForm()
    context["form"] = form
    return render(request, "larpmanager/exe/users/send_mail.html", context)


@login_required
def lm_profile(request: HttpRequest) -> HttpResponse:
    """Display performance profiling data aggregated by domain and view function.

    Shows view function performance metrics computed from individual executions.
    Calculates average duration and total calls for each domain/view combination.
    Requires admin permissions.

    Args:
        request: Django HTTP request object (must be authenticated admin)

    Returns:
        HttpResponse: Rendered profiling data page with performance metrics

    Note:
        Only shows data from the last 168 hours (7 days) and limits results to top 50
        entries by total duration.
    """
    # Check admin permissions and get base context
    context = check_lm_admin(request)

    # Set time threshold to 7 days ago (168 hours)
    st = datetime.now() - timedelta(hours=168)

    # Aggregate data from individual executions by domain and view_func_name
    # Calculate average duration and total calls directly from execution records
    context["res"] = (
        LarpManagerProfiler.objects.filter(created__gte=st)
        .values("domain", "view_func_name")
        .annotate(
            # Count total number of executions for each domain/view combination
            total_calls=Count("id"),
            # Calculate average execution duration across all calls
            avg_duration=Avg("duration"),
            # Sum total time spent in this view across all executions
            total_duration=Sum("duration"),
        )
        # Order by total duration descending to show most time-consuming views first
        .order_by("-total_duration")[:50]
    )

    # Render the profiling template with aggregated performance data
    return render(request, "larpmanager/larpmanager/profile.html", context)


@ratelimit(key="ip", rate="5/m", block=True)
def donate(request):
    """Handle donation page with bot protection.

    Rate-limited endpoint that blocks bots and provides
    a form-protected redirect to PayPal donation page.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered donation form or redirect to PayPal
        HttpResponseForbidden: If bot detected
    """
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    if is_suspicious_user_agent(user_agent):
        return HttpResponseForbidden("Bots not allowed.")

    if request.POST:
        form = LarpManagerCheck(request.POST, request=request)
        if form.is_valid():
            return redirect("https://www.paypal.com/paypalme/mscanagatta")
    else:
        form = LarpManagerCheck(request=request)
    context = {"form": form}
    return render(request, "larpmanager/larpmanager/donate.html", context)


def debug_user(request, mid):
    """Login as a specific user for debugging purposes.

    Allows admin users to login as another user for debugging.
    Requires admin permissions.

    Args:
        request: Django HTTP request object
        mid: Member ID to login as

    Side effects:
        Logs in as the specified user
    """
    check_lm_admin(request)
    member = Member.objects.get(pk=mid)
    login(request, member.user, backend=get_user_backend())


@ratelimit(key="ip", rate="5/m", block=True)
def demo(request):
    """Handle demo organization creation with bot protection.

    Rate-limited endpoint that blocks bots and creates
    demo organizations for testing purposes.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered demo form or redirect to created demo
        HttpResponseForbidden: If bot detected
    """
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    if is_suspicious_user_agent(user_agent):
        return HttpResponseForbidden("Bots not allowed.")

    if request.POST:
        form = LarpManagerCheck(request.POST, request=request)
        if form.is_valid():
            return _create_demo(request)
    else:
        form = LarpManagerCheck(request=request)
    context = {"form": form}
    return render(request, "larpmanager/larpmanager/demo.html", context)


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
    new_primary_key = Association.objects.order_by("-pk").values_list("pk", flat=True).first()
    new_primary_key += 1

    # Create demo association with unique slug and inherited skin
    demo_association = Association.objects.create(
        slug=f"test{new_primary_key}", name="Demo Organization", skin_id=request.assoc["skin_id"], demo=True
    )

    # Create test admin user with demo credentials
    (demo_user, created) = User.objects.get_or_create(
        email=f"test{new_primary_key}@demo.it", username=f"test{new_primary_key}"
    )
    demo_user.password = "pippo"
    demo_user.save()

    # Configure member profile with demo information
    demo_member = demo_user.member
    demo_member.name = "Demo"
    demo_member.surname = "Admin"
    demo_member.save()

    # Create admin role and assign member with full permissions
    (admin_role, created) = AssocRole.objects.get_or_create(assoc=demo_association, number=1, name="Admin")
    admin_role.members.add(demo_member)
    admin_role.save()

    # Set membership status to active/joined
    membership_element = get_user_membership(demo_member, demo_association.id)
    membership_element.status = MembershipStatus.JOINED
    membership_element.save()

    # Authenticate and log in the demo user
    login(request, demo_user, backend=get_user_backend())

    return redirect("after_login", subdomain=demo_association.slug, path="manage")
