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

from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.miscellanea import (
    HelpQuestionForm,
    ShuttleServiceEditForm,
    ShuttleServiceForm,
)
from larpmanager.models.event import (
    Run,
)
from larpmanager.models.miscellanea import (
    Album,
    AlbumUpload,
    HelpQuestion,
    ShuttleService,
    UrlShortner,
    Util,
    WorkshopMemberRel,
    WorkshopModule,
)
from larpmanager.models.writing import (
    Handout,
)
from larpmanager.utils.base import def_user_ctx, is_shuttle
from larpmanager.utils.common import (
    get_album,
    get_workshop,
)
from larpmanager.utils.event import get_event_run
from larpmanager.utils.exceptions import check_assoc_feature
from larpmanager.utils.pdf import (
    print_handout,
    return_pdf,
)


def url_short(request, s):
    el = get_object_or_404(UrlShortner, cod=s)
    return redirect(el.url)


def util(request, cod):
    try:
        u = Util.objects.get(cod=cod)
        return HttpResponseRedirect(u.download())
    except Exception as err:
        raise Http404("not found") from err


def help_red(request, n):
    ctx = def_user_ctx(request)
    ctx.update({"a_id": request.assoc["id"]})
    try:
        ctx["run"] = Run.objects.get(pk=n, event__assoc_id=ctx["a_id"])
    except ObjectDoesNotExist as err:
        raise Http404("Run does not exist") from err
    return redirect("help", s=ctx["run"].event.slug, n=ctx["run"].number)


@login_required
def help(request, s=None, n=None):
    if s and n:
        ctx = get_event_run(request, s, n, status=True)
    else:
        ctx = def_user_ctx(request)
        ctx["a_id"] = request.assoc["id"]

    if request.method == "POST":
        form = HelpQuestionForm(request.POST, request.FILES, ctx=ctx)
        if form.is_valid():
            hp = form.save(commit=False)
            hp.member = request.user.member
            if ctx["a_id"] != 0:
                hp.assoc_id = ctx["a_id"]
            hp.save()
            messages.success(request, _("Question saved!"))
            return redirect(request.path_info)
    else:
        form = HelpQuestionForm(ctx=ctx)

    ctx["form"] = form
    ctx["list"] = HelpQuestion.objects.filter(member=request.user.member).order_by("-created")
    if ctx["a_id"] != 0:
        ctx["list"] = ctx["list"].filter(assoc_id=ctx["a_id"])
    else:
        ctx["list"] = ctx["list"].filter(assoc=None)

    return render(request, "larpmanager/member/help.html", ctx)


@login_required
def help_attachment(request, p):
    ctx = def_user_ctx(request)
    try:
        hp = HelpQuestion.objects.get(pk=p)
    except ObjectDoesNotExist as err:
        raise Http404("HelpQuestion does not exist") from err

    if hp.member != request.user.member and not ctx["assoc_role"]:
        raise Http404("illegal access")

    return redirect(hp.attachment.url)


def handout_ext(request, s, n, cod):
    ctx = get_event_run(request, s, n)
    ctx["handout"] = get_object_or_404(Handout, event=ctx["event"], cod=cod)
    fp = print_handout(ctx)
    return return_pdf(fp, str(ctx["handout"]))


def album_aux(request, ctx, parent):
    ctx["subs"] = Album.objects.filter(run=ctx["run"], parent=parent, is_visible=True).order_by("-created")
    if parent is not None:
        lst = AlbumUpload.objects.filter(album=ctx["album"]).order_by("-created")
        paginator = Paginator(lst, 20)
        page = request.GET.get("page")
        try:
            lst = paginator.page(page)
        except PageNotAnInteger:
            lst = paginator.page(1)  # If page is not an integer, deliver first
        except EmptyPage:
            lst = paginator.page(
                paginator.num_pages
            )  # If page is out of range (e.g.  9999), deliver last page of results.
        ctx["page"] = lst
        ctx["name"] = f"{ctx['album']} - {str(ctx['run'])}"
    else:
        ctx["name"] = f"Album - {str(ctx['run'])}"
    ctx["parent"] = parent
    return render(request, "larpmanager/event/album.html", ctx)


@login_required
def album(request, s, n):
    ctx = get_event_run(request, s, n)
    return album_aux(request, ctx, None)


@login_required
def album_sub(request, s, n, num):
    ctx = get_event_run(request, s, n)
    get_album(ctx, num)
    return album_aux(request, ctx, ctx["album"])


@login_required
def workshops(request, s, n):
    ctx = get_event_run(request, s, n, signup=True, status=True)
    # get modules assigned to this event
    ctx["list"] = []
    for workshop in ctx["event"].workshops.all().order_by("number"):
        dt = workshop.show()
        limit = datetime.now() - timedelta(days=365)
        # print(limit)
        dt["done"] = (
            WorkshopMemberRel.objects.filter(member=request.user.member, workshop=workshop, created__gte=limit).count()
            >= 1
        )
        ctx["list"].append(dt)
    return render(request, "larpmanager/event/workshops/index.html", ctx)


def valid_workshop_answer(request, ctx):
    res = True
    for el in ctx["list"]:
        el["correct"] = []
        el["answer"] = []
        for o in el["opt"]:
            if o["is_correct"]:
                el["correct"].append(o["id"])
            ix = f"{el['id']}_{o['id']}"
            if request.POST.get(ix, "") == "on":
                el["answer"].append(o["id"])
        el["correct"].sort()
        el["answer"].sort()
        el["failed"] = el["correct"] != el["answer"]
        if el["failed"]:
            res = False
    return res


@login_required
def workshop_answer(request, s, n, m):
    ctx = get_event_run(request, s, n, signup=True, status=True)
    get_workshop(ctx, m)
    completed = [el.pk for el in request.user.member.workshops.all()]
    if ctx["workshop"].pk in completed:
        messages.success(request, _("Workshop already done!"))
        return redirect("workshops", s=ctx["event"].slug, n=ctx["run"].number)
    ctx["list"] = []
    for question in ctx["workshop"].questions.all().order_by("number"):
        ctx["list"].append(question.show())
    # if only preseting result
    if request.method != "POST":
        return render(request, "larpmanager/event/workshops/answer.html", ctx)
        # if correct
    if valid_workshop_answer(request, ctx):
        WorkshopMemberRel.objects.create(member=request.user.member, workshop=ctx["workshop"])
        remaining = (
            WorkshopModule.objects.filter(event=ctx["event"], number__gt=ctx["workshop"].number)
            .exclude(pk__in=completed)
            .order_by("number")
        )
        if len(remaining) > 0:
            messages.success(request, _("Completed module. Remaining: {number:d}").format(number=len(remaining)))
            return redirect(
                "workshop_answer",
                s=ctx["event"].slug,
                n=ctx["run"].number,
                m=remaining.first().number,
            )
        messages.success(request, _("Well done, you've completed all modules!"))
        return redirect("workshops", s=ctx["event"].slug, n=ctx["run"].number)

        # if wrong
    return render(request, "larpmanager/event/workshops/failed.html", ctx)


@login_required
def shuttle(request):
    check_assoc_feature(request, "shuttle")
    # get last shuttle requests
    ref = datetime.now() - timedelta(days=5)
    ctx = def_user_ctx(request)
    ctx.update(
        {
            "list": ShuttleService.objects.exclude(status=ShuttleService.DONE)
            .filter(assoc_id=request.assoc["id"])
            .order_by("status", "date", "time"),
            "is_shuttle": is_shuttle(request),
            "past": ShuttleService.objects.filter(
                created__gt=ref.date(),
                status=ShuttleService.DONE,
                assoc_id=request.assoc["id"],
            ).order_by("status", "date", "time"),
        }
    )
    return render(request, "larpmanager/general/shuttle.html", ctx)


@login_required
def shuttle_new(request):
    check_assoc_feature(request, "shuttle")
    ctx = def_user_ctx(request)
    ctx.update({"a_id": request.assoc["id"]})
    if request.method == "POST":
        form = ShuttleServiceForm(request.POST, request=request, ctx=ctx)
        if form.is_valid():
            el = form.save(commit=False)
            el.member = request.user.member
            el.save()
            return redirect("shuttle")
    else:
        form = ShuttleServiceForm(request=request, ctx=ctx)
    return render(
        request,
        "larpmanager/general/writing.html",
        {"form": form, "name": _("New shuttle request")},
    )


@login_required
def shuttle_edit(request, n):
    check_assoc_feature(request, "shuttle")
    ctx = def_user_ctx(request)
    ctx.update({"a_id": request.assoc["id"]})
    # check_shuttle(request)
    shuttle = ShuttleService.objects.get(pk=n)
    if request.method == "POST":
        form = ShuttleServiceEditForm(request.POST, instance=shuttle, request=request, ctx=ctx)
        if form.is_valid():
            form.save()
            return redirect("shuttle")
    else:
        form = ShuttleServiceEditForm(instance=shuttle, request=request, ctx=ctx)
    return render(
        request,
        "larpmanager/general/writing.html",
        {"form": form, "name": _("Modify shuttle request")},
    )
