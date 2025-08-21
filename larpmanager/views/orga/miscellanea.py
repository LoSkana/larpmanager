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
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.miscellanea import (
    OrgaAlbumForm,
    OrgaInventoryAreaForm,
    OrgaInventoryAssignmentForm,
    OrgaProblemForm,
    UploadAlbumsForm,
    UtilForm,
    WorkshopModuleForm,
    WorkshopOptionForm,
    WorkshopQuestionForm,
)
from larpmanager.models.miscellanea import (
    Album,
    InventoryArea,
    InventoryAssignment,
    Problem,
    Util,
    WorkshopMemberRel,
    WorkshopModule,
    WorkshopOption,
    WorkshopQuestion,
)
from larpmanager.models.registration import Registration
from larpmanager.utils.common import (
    get_album_cod,
)
from larpmanager.utils.edit import orga_edit
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.miscellanea import get_inventory_optionals, upload_albums
from larpmanager.utils.writing import writing_post


@login_required
def orga_albums(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_albums")
    ctx["list"] = Album.objects.filter(run=ctx["run"]).order_by("-created")
    return render(request, "larpmanager/orga/albums.html", ctx)


@login_required
def orga_albums_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_albums", OrgaAlbumForm, num)


@login_required
def orga_albums_upload(request, s, n, a):
    ctx = check_event_permission(request, s, n, "orga_albums")
    get_album_cod(ctx, a)
    if request.method == "POST":
        form = UploadAlbumsForm(request, s, n.POST, request.FILES)
        if form.is_valid():
            upload_albums(ctx["album"], request.FILES["elem"])
            messages.success(request, s, n, _("Photos and videos successfully uploaded") + "!")
            return redirect(request, s, n.path_info)
    else:
        form = UploadAlbumsForm()
    ctx["form"] = form
    return render(request, "larpmanager/orga/albums_upload.html", ctx)


@login_required
def orga_utils(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_utils")
    ctx["list"] = Util.objects.filter(event=ctx["event"]).order_by("number")
    return render(request, "larpmanager/orga/utils.html", ctx)


@login_required
def orga_utils_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_utils", UtilForm, num)


@login_required
def orga_workshops(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_workshops")
    # get number of modules
    workshops = ctx["event"].workshops.all()
    limit = datetime.now() - timedelta(days=365)
    ctx["pinocchio"] = []
    ctx["list"] = []
    # count workshops done by players
    for reg in Registration.objects.filter(run=ctx["run"], cancellation_date__isnull=True):
        reg.num = 0
        for w in workshops:
            if WorkshopMemberRel.objects.filter(member=reg.member, workshop=w, created__gte=limit).count() >= 1:
                reg.num += 1
        if reg.num != len(workshops):
            ctx["pinocchio"].append(reg.member)
        ctx["list"].append(reg)
    return render(request, "larpmanager/orga/workshop/workshops.html", ctx)


@login_required
def orga_workshop_modules(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_workshop_modules")
    ctx["list"] = WorkshopModule.objects.filter(event=ctx["event"]).order_by("number")
    return render(request, "larpmanager/orga/workshop/modules.html", ctx)


@login_required
def orga_workshop_modules_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_workshop_modules", WorkshopModuleForm, num)


@login_required
def orga_workshop_questions(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_workshop_questions")
    if request.method == "POST":
        return writing_post(request, s, n, ctx, WorkshopQuestion, "workshop_question")
    ctx["list"] = WorkshopQuestion.objects.filter(module__event=ctx["event"]).order_by("module__number", "number")
    return render(request, "larpmanager/orga/workshop/questions.html", ctx)


@login_required
def orga_workshop_questions_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_workshop_questions", WorkshopQuestionForm, num)


@login_required
def orga_workshop_options(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_workshop_options")
    if request.method == "POST":
        return writing_post(request, s, n, ctx, WorkshopOption, "workshop_option")
    ctx["list"] = WorkshopOption.objects.filter(question__module__event=ctx["event"]).order_by(
        "question__module__number", "question__number", "is_correct"
    )
    return render(request, "larpmanager/orga/workshop/options.html", ctx)


@login_required
def orga_workshop_options_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_workshop_options", WorkshopOptionForm, num)


@login_required
def orga_problems(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_problems")
    ctx["list"] = Problem.objects.filter(event=ctx["event"]).order_by("status", "-severity")
    return render(request, "larpmanager/orga/problems.html", ctx)


@login_required
def orga_problems_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_problems", OrgaProblemForm, num)


@login_required
def orga_inventory_area(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_inventory_area")
    ctx["list"] = ctx["event"].get_elements(InventoryArea)
    return render(request, "larpmanager/orga/inventory/area.html", ctx)


@login_required
def orga_inventory_area_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_inventory_area", OrgaInventoryAreaForm, num)


@login_required
def orga_inventory_assignments(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_inventory_assignments")
    ctx["list"] = ctx["event"].get_elements(InventoryAssignment).select_related("area", "item")
    get_inventory_optionals(ctx, [4])
    return render(request, "larpmanager/orga/inventory/assignments.html", ctx)


@login_required
def orga_inventory_assignments_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_inventory_assignments", OrgaInventoryAssignmentForm, num)


@login_required
def orga_inventory_manifest(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_inventory_manifest")
    ctx["list"] = ctx["event"].get_elements(InventoryArea).prefetch_related("assignments", "assignments__item")
    get_inventory_optionals(ctx, [3, 4])
    return render(request, "larpmanager/orga/inventory/manifest.html", ctx)
