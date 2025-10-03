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

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, F, Min, Sum
from django.http import Http404, HttpResponseForbidden, JsonResponse
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


def lm_home(request):
    """Display the LarpManager home page with promoters and reviews.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered home page template with context data
    """
    ctx = get_lm_contact(request)
    ctx["index"] = True

    if request.assoc["base_domain"] == "ludomanager.it":
        return ludomanager(ctx, request)

    ctx.update(get_cache_lm_home())
    random.shuffle(ctx["promoters"])
    random.shuffle(ctx["reviews"])

    return render(request, "larpmanager/larpmanager/home.html", ctx)


def ludomanager(ctx, request):
    """Render the LudoManager skin version of the home page.

    Args:
        ctx: Context dictionary to update
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered LudoManager template
    """
    ctx["assoc_skin"] = "LudoManager"
    ctx["platform"] = "LudoManager"
    return render(request, "larpmanager/larpmanager/skin/ludomanager.html", ctx)


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
    ctx = {}
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
        ctx["form"] = form

    return render(request, "larpmanager/larpmanager/contact.html", ctx)


def go_redirect(request, slug, p, base_domain="larpmanager.com"):
    """Redirect user to association-specific subdomain or main domain.

    Args:
        request: Django HTTP request object
        slug: Association slug for subdomain
        p: Path to append to URL
        base_domain: Base domain name (default: "larpmanager.com")

    Returns:
        HttpResponseRedirect: Redirect to appropriate URL
    """
    if request.enviro in ["dev", "test"]:
        return redirect("http://127.0.0.1:8000/")

    if slug:
        n_p = f"https://{slug}.{base_domain}/"
    else:
        n_p = f"https://{base_domain}/"

    if p:
        n_p += p

    return redirect(n_p)


def choose_assoc(request, p, slugs):
    """Handle association selection when multiple associations are available.

    Args:
        request: Django HTTP request object
        p: URL path to redirect to after selection
        slugs: List of association slugs to choose from

    Returns:
        HttpResponse: Redirect to selected association or selection form
    """
    if len(slugs) == 0:
        return render(request, "larpmanager/larpmanager/na_assoc.html")
    elif len(slugs) == 1:
        return go_redirect(request, slugs[0], p)
    else:
        # show page to choose them
        if request.POST:
            form = RedirectForm(request.POST, slugs=slugs)
            if form.is_valid():
                counter = int(form.cleaned_data["slug"])
                if counter < len(slugs):
                    return go_redirect(request, slugs[counter], p)
        else:
            form = RedirectForm(slugs=slugs)
        return render(
            request,
            "larpmanager/larpmanager/redirect.html",
            {"form": form, "name": "association"},
        )


def go_redirect_run(run, p):
    """Redirect to a specific run's URL on its association's domain.

    Args:
        run: Run object to redirect to
        p: URL path to append after the run slug

    Returns:
        HttpResponseRedirect: Redirect to the run's URL
    """
    n_p = f"https://{run.event.assoc.slug}.{run.event.assoc.skin.domain}/{run.get_slug()}/{p}"
    return redirect(n_p)


def choose_run(request, p, event_ids):
    """Handle run selection when multiple runs are available.

    Args:
        request: Django HTTP request object
        p: URL path to redirect to after selection
        event_ids: List of event IDs to get runs from

    Returns:
        HttpResponse: Redirect to selected run or selection form
    """
    runs = []
    slugs = []

    for r in Run.objects.filter(event_id__in=event_ids, end__gte=datetime.now()):
        runs.append(r)
        slugs.append(f"{r.search} - {r.event.assoc.slug}")

    if len(slugs) == 0:
        return render(request, "larpmanager/larpmanager/na_event.html")
    elif len(slugs) == 1:
        return go_redirect_run(runs[0], p)

    else:
        # show page to choose them
        if request.POST:
            form = RedirectForm(request.POST, slugs=slugs)
            if form.is_valid():
                counter = int(form.cleaned_data["slug"])
                if counter < len(slugs):
                    return go_redirect_run(runs[counter], p)
        else:
            form = RedirectForm(slugs=slugs)
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


def activate_feature_assoc(request, cod, p=None):
    """Activate a feature for an association.

    Args:
        request: Django HTTP request object
        cod: Feature slug/code to activate
        p: Optional URL path to redirect to after activation

    Returns:
        HttpResponseRedirect: Redirect to specified path or feature view

    Raises:
        Http404: If feature doesn't exist or isn't overall
        PermissionError: If user lacks exe_features permission
    """
    feature = get_object_or_404(Feature, slug=cod)
    if not feature.overall:
        raise Http404("feature not overall")

    # check the user has the permission to add features
    if not has_assoc_permission(request, {}, "exe_features"):
        raise PermissionError()

    # add feature
    assoc = get_object_or_404(Association, pk=request.assoc["id"])
    assoc.features.add(feature)
    assoc.save()

    messages.success(request, _("Feature activated") + ":" + feature.name)

    # redirect either to the requested next, or to the best match for the permission asked
    if p:
        return redirect("/" + p)
    view_name = feature.assoc_permissions.first().slug
    return redirect(reverse(view_name))


def activate_feature_event(request, s, cod, p=None):
    """Activate a feature for a specific event.

    Args:
        request: Django HTTP request object
        s: Event slug identifier
        cod: Feature slug/code to activate
        p: Optional URL path to redirect to after activation

    Returns:
        HttpResponseRedirect: Redirect to specified path or feature view

    Raises:
        Http404: If feature doesn't exist or is overall (not event-specific)
        PermissionError: If user lacks orga_features permission
    """
    feature = get_object_or_404(Feature, slug=cod)
    if feature.overall:
        raise Http404("feature overall")

    # check the user has the permission to add features
    ctx = get_event_run(request, s)
    if not has_event_permission(request, {}, ctx["event"].slug, "orga_features"):
        raise PermissionError()

    # add feature
    ctx["event"].features.add(feature)
    ctx["event"].save()

    messages.success(request, _("Feature activated") + ":" + feature.name)

    # redirect either to the requested next, or to the best match for the permission asked
    if p:
        return redirect("/" + p)
    view_name = feature.event_permissions.first().slug
    return redirect(reverse(view_name, kwargs={"s": s}))


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


def debug_slug(request, s=""):
    """Set debug slug in session for development testing.

    Only available in development and test environments.
    Sets a debug slug in the session for testing purposes.

    Args:
        request: Django HTTP request object
        s: Debug slug to set in session

    Returns:
        HttpResponseRedirect: Redirect to home page

    Raises:
        Http404: If not in dev or test environment
    """
    if request.enviro not in ["dev", "test"]:
        raise Http404()

    request.session["debug_slug"] = s
    return redirect("home")


def ticket(request, s=""):
    """Handle support ticket creation and submission.

    Displays ticket form and processes ticket submissions.
    Associates tickets with current association and user if authenticated.

    Args:
        request: Django HTTP request object
        s: Optional reason/category for the ticket

    Returns:
        HttpResponse: Rendered ticket form or redirect after successful submission
    """
    ctx = {"reason": s}
    if request.POST:
        form = LarpManagerTicketForm(request.POST, request.FILES, request=request, ctx=ctx)
        if form.is_valid():
            lm_ticket = form.save(commit=False)
            lm_ticket.assoc_id = request.assoc["id"]
            if s:
                lm_ticket.reason = s
            if request.user.is_authenticated:
                lm_ticket.member = request.user.member
            lm_ticket.save()
            messages.success(request, _("Your request has been sent, we will reply as soon as possible!"))
            return redirect("home")
    else:
        form = LarpManagerTicketForm(request=request, ctx=ctx)
    ctx["form"] = form
    return render(request, "larpmanager/member/ticket.html", ctx)


def is_suspicious_user_agent(user_agent):
    """Check if a user agent string appears to be from a bot.

    Args:
        user_agent (str): User agent string to check

    Returns:
        bool: True if user agent appears to be from a bot, False otherwise
    """
    known_bots = ["bot", "crawler", "spider", "http", "archive", "wget", "curl"]
    return any(bot in user_agent.lower() for bot in known_bots)


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
    ctx = {"form": form}
    return render(request, "larpmanager/larpmanager/discord.html", ctx)


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
    ctx = get_lm_contact(request)
    if "red" in ctx:
        return redirect(ctx["red"])

    assoc = _join_form(ctx, request)
    if assoc:
        # send message
        messages.success(request, _("Welcome to %(name)s!") % {"name": request.assoc["name"]})
        # send email
        if request.assoc["skin_id"] == 1:
            join_email(assoc)
        # redirect
        return redirect("after_login", subdomain=assoc.slug, path="manage")

    return render(request, "larpmanager/larpmanager/join.html", ctx)


def _join_form(ctx, request):
    """Process association creation form for new users.

    Handles form validation, association creation, user role assignment,
    and admin notifications for new organizations.

    Args:
        ctx: Context dictionary to update with form data
        request: Django HTTP request object

    Returns:
        Association: Created association object if successful, None otherwise
    """
    if request.method == "POST":
        form = FirstAssociationForm(request.POST, request.FILES)
        if form.is_valid():
            # set skin
            assoc = form.save(commit=False)
            assoc.skin_id = request.assoc["skin_id"]
            assoc.save()

            # Add member to admins
            (ar, created) = AssocRole.objects.get_or_create(assoc=assoc, number=1, name="Admin")
            ar.members.add(request.user.member)
            ar.save()
            el = get_user_membership(request.user.member, assoc.id)
            el.status = MembershipStatus.JOINED
            el.save()

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
        form = FirstAssociationForm()

    ctx["form"] = form
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
    ctx = get_lm_contact(request)
    ctx["index"] = True
    ctx["discover"] = LarpManagerDiscover.objects.order_by("order")
    return render(request, "larpmanager/larpmanager/discover.html", ctx)


@override("en")
def tutorials(request, slug=None):
    """Display tutorial pages with navigation.

    Shows individual tutorials with previous/next navigation.
    Always rendered in English locale.

    Args:
        request: Django HTTP request object
        slug: Optional tutorial slug, defaults to first tutorial

    Returns:
        HttpResponse: Rendered tutorial page

    Raises:
        Http404: If tutorial with specified slug doesn't exist
    """
    ctx = get_lm_contact(request, False)
    ctx["index"] = True

    try:
        if slug:
            tutorial = LarpManagerTutorial.objects.get(slug=slug)
        else:
            tutorial = LarpManagerTutorial.objects.order_by("order").first()
            ctx["intro"] = True
    except ObjectDoesNotExist as err:
        raise Http404("tutorial not found") from err

    if tutorial:
        order = tutorial.order
        ctx["seq"] = order

        que = LarpManagerTutorial.objects.order_by("order")
        ctx["list"] = que.values_list("name", "order", "slug")

        ctx["next"] = None
        ctx["prev"] = None
        for el in ctx["list"]:
            if el[1] < order:
                ctx["prev"] = el
            if el[1] > order and not ctx["next"]:
                ctx["next"] = el

    ctx["iframe"] = request.GET.get("in_iframe") == "1"
    ctx["opened"] = tutorial

    return render(request, "larpmanager/larpmanager/tutorials.html", ctx)


@cache_page(60 * 15)
def guides(request):
    """Display list of published guides for LarpManager users.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered guides template with list of published guides
    """
    ctx = get_lm_contact(request)
    ctx["list"] = LarpManagerGuide.objects.filter(published=True).order_by("number")
    ctx["index"] = True
    return render(request, "larpmanager/larpmanager/guides.html", ctx)


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
    ctx = get_lm_contact(request)
    ctx["index"] = True

    try:
        ctx["guide"] = LarpManagerGuide.objects.get(slug=slug, published=True)
    except ObjectDoesNotExist as err:
        raise Http404("guide not found") from err

    ctx["og_image"] = ctx["guide"].thumb.url
    ctx["og_title"] = f"{ctx['guide'].title} - LarpManager"
    ctx["og_description"] = f"{ctx['guide'].description} - LarpManager"

    return render(request, "larpmanager/larpmanager/guide.html", ctx)


@cache_page(60 * 15)
def privacy(request):
    """Display privacy policy page.

    Cached for 15 minutes. Shows association-specific privacy text.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered privacy policy page
    """
    ctx = get_lm_contact(request)
    ctx.update({"text": get_assoc_text(request.assoc["id"], AssocTextType.PRIVACY)})
    return render(request, "larpmanager/larpmanager/privacy.html", ctx)


@cache_page(60 * 15)
def usage(request):
    """Display usage/terms page.

    Cached for 15 minutes. Shows usage guidelines and terms.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered usage page
    """
    ctx = get_lm_contact(request)
    ctx["index"] = True
    return render(request, "larpmanager/larpmanager/usage.html", ctx)


@cache_page(60 * 15)
def about_us(request):
    """Display about us page.

    Cached for 15 minutes. Shows information about the platform.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponse: Rendered about us page
    """
    ctx = get_lm_contact(request)
    ctx["index"] = True
    return render(request, "larpmanager/larpmanager/about_us.html", ctx)


def get_lm_contact(request, check=True):
    """Get base context for LarpManager contact pages.

    Args:
        request: Django HTTP request object
        check: Whether to check if user is on main site (default True)

    Returns:
        dict: Base context with contact form and platform info

    Raises:
        MainPageError: If check=True and user is on association site
    """
    if check and request.assoc["id"] > 0:
        raise MainPageError(request.path)
    ctx = {"lm": 1, "contact_form": LarpManagerContact(request=request), "platform": "LarpManager"}
    return ctx


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
    ctx = check_lm_admin(request)

    ctx["list"] = Association.objects.annotate(total_registrations=Count("events__runs__registrations")).order_by(
        "-total_registrations"
    )

    return render(request, "larpmanager/larpmanager/list.html", ctx)


@login_required
def lm_payments(request):
    """Display payment management page for admin users.

    Shows unpaid runs and payment totals by year.
    Requires admin permissions.

    Args:
        request: Django HTTP request object (must be authenticated admin)

    Returns:
        HttpResponse: Rendered payments management page
    """
    ctx = check_lm_admin(request)
    min_registrations = 5
    que = Run.objects.filter(paid__isnull=True).order_by("start")

    ctx["list"] = []
    ctx["total"] = 0
    for el in que:
        if not el.plan:
            continue

        get_run_lm_payment(el)

        if el.active_registrations < min_registrations:
            continue

        ctx["list"].append(el)
        ctx["total"] += el.total

    que = Run.objects.aggregate(oldest_date=Min("start"))
    ctx["totals"] = {}
    for year in list(range(datetime.today().year, que["oldest_date"].year - 1, -1)):
        start_of_year = date(year, 1, 1)
        end_of_year = date(year, 12, 31)
        total_paid = Run.objects.filter(start__range=(start_of_year, end_of_year)).aggregate(total=Sum("paid"))["total"]
        ctx["totals"][year] = total_paid

    return render(request, "larpmanager/larpmanager/payments.html", ctx)


def get_run_lm_payment(el):
    """Calculate payment details for a run.

    Calculates features count, active registrations, and total payment
    based on association plan.

    Args:
        el: Run object to calculate payment for

    Side effects:
        Modifies el object with features, active_registrations, and total attributes
    """
    el.features = len(get_assoc_features(el.event.assoc_id)) + len(get_event_features(el.event_id))
    el.active_registrations = (
        Registration.objects.filter(run__id=el.id, cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.WAITING, TicketTier.NPC])
        .count()
    )
    if el.plan == AssociationPlan.FREE:
        el.total = 0
    elif el.plan == AssociationPlan.SUPPORT:
        el.total = el.active_registrations


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
    ctx = check_lm_admin(request)
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
    ctx["form"] = form
    return render(request, "larpmanager/exe/users/send_mail.html", ctx)


@login_required
def lm_profile(request):
    """Display performance profiling data aggregated by domain and view function.

    Shows view function performance metrics aggregated across dates.
    Calculates average duration and total calls for each domain/view combination.
    Requires admin permissions.

    Args:
        request: Django HTTP request object (must be authenticated admin)

    Returns:
        HttpResponse: Rendered profiling data page
    """
    ctx = check_lm_admin(request)
    st = datetime.now() - timedelta(hours=168)

    # Aggregate data by domain and view_func_name across different dates
    # Calculate weighted average duration using num_calls as weights
    ctx["res"] = (
        LarpManagerProfiler.objects.filter(date__gte=st)
        .values("domain", "view_func_name")
        .annotate(
            total_duration=Sum(F("mean_duration") * F("num_calls")),
            total_calls=Sum("num_calls"),
            avg_duration=F("total_duration") / F("total_calls"),
        )
        .order_by("-avg_duration")[:50]
    )

    return render(request, "larpmanager/larpmanager/profile.html", ctx)


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
    ctx = {"form": form}
    return render(request, "larpmanager/larpmanager/donate.html", ctx)


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
    ctx = {"form": form}
    return render(request, "larpmanager/larpmanager/demo.html", ctx)


def _create_demo(request):
    """Create a demo organization with test user.

    Creates a new demo association with a test admin user
    and logs the user in automatically.

    Args:
        request: Django HTTP request object

    Returns:
        HttpResponseRedirect: Redirect to demo organization management
    """
    new_pk = Association.objects.order_by("-pk").values_list("pk", flat=True).first()
    new_pk += 1

    # create assoc
    assoc = Association.objects.create(
        slug=f"test{new_pk}", name="Demo Organization", skin_id=request.assoc["skin_id"], demo=True
    )

    # create test user
    user = User.objects.create(email=f"test{new_pk}@demo.it", username=f"test{new_pk}", password="pippo")
    member = user.member
    member.name = "Demo"
    member.surname = "Admin"
    member.save()

    # Add member to admins
    (ar, created) = AssocRole.objects.get_or_create(assoc=assoc, number=1, name="Admin")
    ar.members.add(member)
    ar.save()
    el = get_user_membership(member, assoc.id)
    el.status = MembershipStatus.JOINED
    el.save()

    login(request, user, backend=get_user_backend())

    return redirect("after_login", subdomain=assoc.slug, path="manage")
