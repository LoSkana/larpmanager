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
from django.db.models import Count, Min, Sum
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
from larpmanager.forms.larpmanager import LarpManagerCheck, LarpManagerContact, LarpManagerTicket
from larpmanager.forms.miscellanea import SendMailForm
from larpmanager.forms.utils import RedirectForm
from larpmanager.mail.base import join_email
from larpmanager.mail.remind import remember_membership, remember_membership_fee, remember_pay, remember_profile
from larpmanager.models.access import AssocRole, EventRole
from larpmanager.models.association import Association, AssocTextType
from larpmanager.models.base import Feature
from larpmanager.models.event import Run
from larpmanager.models.larpmanager import (
    LarpManagerBlog,
    LarpManagerDiscover,
    LarpManagerPlan,
    LarpManagerProfiler,
    LarpManagerTutorial,
)
from larpmanager.models.member import Member, MembershipStatus, get_user_membership
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.utils.auth import check_lm_admin
from larpmanager.utils.event import get_event_run
from larpmanager.utils.exceptions import PermissionError
from larpmanager.utils.tasks import my_send_mail, send_mail_exec
from larpmanager.utils.text import get_assoc_text
from larpmanager.views.user.member import get_user_backend


def lm_home(request):
    ctx = get_lm_contact(request)
    ctx["index"] = True

    if request.assoc["base_domain"] == "ludomanager.it":
        return ludomanager(ctx, request)

    ctx.update(get_cache_lm_home())
    random.shuffle(ctx["promoters"])
    random.shuffle(ctx["reviews"])

    return render(request, "larpmanager/larpmanager/home.html", ctx)


def ludomanager(ctx, request):
    ctx["assoc_skin"] = "LudoManager"
    ctx["platform"] = "LudoManager"
    return render(request, "larpmanager/larpmanager/skin/ludomanager.html", ctx)


@csrf_exempt
def contact(request):
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
        ctx["contact_form"] = form
    return render(request, "larpmanager/larpmanager/contact.html", ctx)


def go_redirect(request, slug, p, base_domain="larpmanager.com"):
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
    n_p = f"https://{run.event.assoc.slug}.{run.event.assoc.skin.domain}/{run.event.slug}/{run.number}/{p}"
    return redirect(n_p)


def choose_run(request, p, event_ids):
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
    feature = get_object_or_404(Feature, slug=cod)
    if not feature.overall:
        raise Http404("feature not overall")

    # check the user has the permission to add features
    if not has_assoc_permission(request, "exe_features"):
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


def activate_feature_event(request, s, n, cod, p=None):
    feature = get_object_or_404(Feature, slug=cod)
    if feature.overall:
        raise Http404("feature overall")

    # check the user has the permission to add features
    ctx = get_event_run(request, s, n)
    if not has_event_permission({}, request, ctx["event"].slug, "orga_features"):
        raise PermissionError()

    # add feature
    ctx["event"].features.add(feature)
    ctx["event"].save()

    messages.success(request, _("Feature activated") + ":" + feature.name)

    # redirect either to the requested next, or to the best match for the permission asked
    if p:
        return redirect("/" + p)
    view_name = feature.event_permissions.first().slug
    return redirect(reverse(view_name, kwargs={"s": s, "n": n}))


def toggle_sidebar(request):
    key = "is_sidebar_open"
    if key in request.session:
        request.session[key] = not request.session[key]
    else:
        request.session[key] = True
    return JsonResponse({"status": "success"})


def debug_mail(request):
    if request.enviro not in ["dev", "test"]:
        raise Http404()

    for reg in Registration.objects.all():
        remember_profile(reg)
        remember_membership(reg)
        remember_membership_fee(reg)
        remember_pay(reg)

    return redirect("home")


def debug_slug(request, s=""):
    if request.enviro not in ["dev", "test"]:
        raise Http404()

    request.session["debug_slug"] = s
    return redirect("home")


def ticket(request, s=""):
    ctx = {"reason": s}
    if request.POST:
        form = LarpManagerTicket(request.POST, request=request)
        if form.is_valid():
            for _name, email in conf_settings.ADMINS:
                subj = f"LarpManager ticket - {request.assoc['name']}"
                if s:
                    subj += f" [{s}]"
                body = f"Email: {form.cleaned_data['email']} <br /><br />"
                if request.user.is_authenticated:
                    body += f"User: {request.user.member} ({request.user.member.email}) <br /><br />"
                body += form.cleaned_data["content"]
                my_send_mail(subj, body, email)
            messages.success(request, _("Your request has been sent, we will reply as soon as possible!"))
            return redirect("home")
    else:
        form = LarpManagerTicket(request=request)
    ctx["form"] = form
    return render(request, "larpmanager/member/ticket.html", ctx)


def is_suspicious_user_agent(user_agent):
    known_bots = ["bot", "crawler", "spider", "http", "archive", "wget", "curl"]
    return any(bot in user_agent.lower() for bot in known_bots)


@ratelimit(key="ip", rate="5/m", block=True)
def discord(request):
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
    ctx = get_lm_contact(request)
    ctx["index"] = True
    ctx["discover"] = LarpManagerDiscover.objects.order_by("order")
    return render(request, "larpmanager/larpmanager/discover.html", ctx)


@override("en")
def tutorials(request, slug=None):
    ctx = get_lm_contact(request)
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
def blog(request, slug=""):
    ctx = get_lm_contact(request)
    ctx["index"] = True
    if slug:
        try:
            ctx["article"] = LarpManagerBlog.objects.get(slug=slug, published=True)
            ctx["og_image"] = ctx["article"].thumb.url
            ctx["og_title"] = ctx["article"].title
            ctx["og_description"] = ctx["article"].description
        except Exception as err:
            raise Http404("blog article not found") from err
    else:
        ctx["list"] = LarpManagerBlog.objects.filter(published=True)

    return render(request, "larpmanager/larpmanager/blog.html", ctx)


@cache_page(60 * 15)
def privacy(request):
    ctx = get_lm_contact(request)
    ctx.update({"text": get_assoc_text(request.assoc["id"], AssocTextType.PRIVACY)})
    return render(request, "larpmanager/larpmanager/privacy.html", ctx)


@cache_page(60 * 15)
def usage(request):
    ctx = get_lm_contact(request)
    ctx["index"] = True
    return render(request, "larpmanager/larpmanager/usage.html", ctx)


@cache_page(60 * 15)
def about_us(request):
    ctx = get_lm_contact(request)
    ctx["index"] = True
    return render(request, "larpmanager/larpmanager/about_us.html", ctx)


def get_lm_contact(request):
    ctx = {"lm": 1, "contact_form": LarpManagerContact(request=request), "platform": "LarpManager"}
    return ctx


@login_required
def lm_list(request):
    ctx = check_lm_admin(request)

    ctx["list"] = Association.objects.annotate(total_registrations=Count("events__runs__registrations")).order_by(
        "-total_registrations"
    )

    return render(request, "larpmanager/larpmanager/list.html", ctx)


@login_required
def lm_payments(request):
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
    el.features = len(get_assoc_features(el.event.assoc_id)) + len(get_event_features(el.event_id))
    el.active_registrations = (
        Registration.objects.filter(run__id=el.id, cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.STAFF, TicketTier.WAITING, TicketTier.NPC])
        .count()
    )
    if el.plan == LarpManagerPlan.FREE:
        el.total = 0
    elif el.plan == LarpManagerPlan.SUPPORT:
        el.total = el.active_registrations


@login_required
def lm_payments_confirm(request, r):
    check_lm_admin(request)
    run = Run.objects.get(pk=r)
    get_run_lm_payment(run)
    run.paid = run.total
    run.save()
    return redirect("lm_payments")


@login_required
def lm_send(request):
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
    ctx = check_lm_admin(request)
    st = datetime.now() - timedelta(hours=72)
    ctx["res"] = LarpManagerProfiler.objects.filter(date__gte=st).order_by("-mean_duration")[:50]
    return render(request, "larpmanager/larpmanager/profile.html", ctx)


@login_required
def lm_profile_rm(request, func):
    check_lm_admin(request)
    LarpManagerProfiler.objects.filter(view_func_name=func).delete()
    return redirect("lm_profile")


@ratelimit(key="ip", rate="5/m", block=True)
def donate(request):
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
    check_lm_admin(request)
    member = Member.objects.get(pk=mid)
    login(request, member.user, backend=get_user_backend())


@ratelimit(key="ip", rate="5/m", block=True)
def demo(request):
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
