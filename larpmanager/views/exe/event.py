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

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from larpmanager.cache.feature import get_event_features
from larpmanager.cache.registration import get_reg_counts
from larpmanager.forms.event import (
    ExeEventForm,
    ExeTemplateForm,
    ExeTemplateRolesForm,
    OrgaAppearanceForm,
    OrgaConfigForm,
    OrgaRunForm,
)
from larpmanager.models.access import EventRole
from larpmanager.models.event import (
    Event,
    Run,
)
from larpmanager.utils.base import check_assoc_permission, def_user_ctx
from larpmanager.utils.common import (
    get_event_template,
)
from larpmanager.utils.deadlines import check_run_deadlines
from larpmanager.utils.edit import backend_edit, backend_get, exe_edit
from larpmanager.views.manage import _get_registration_status
from larpmanager.views.orga.event import full_event_edit
from larpmanager.views.orga.registration import get_pre_registration
from larpmanager.views.user.event import get_coming_runs


@login_required
def exe_events(request):
    ctx = check_assoc_permission(request, "exe_events")
    ctx["list"] = Run.objects.filter(event__assoc_id=ctx["a_id"]).select_related("event").order_by("end")
    for run in ctx["list"]:
        run.registration_status = _get_registration_status(run)
        run.counts = get_reg_counts(run)
    return render(request, "larpmanager/exe/events.html", ctx)


@login_required
def exe_events_edit(request, num):
    ctx = check_assoc_permission(request, "exe_events")

    if num:
        # edit existing event / run
        backend_get(ctx, Run, num, "event")
        return full_event_edit(ctx, request, ctx["el"].event, ctx["el"], exe=True)

    # create new event
    ctx["exe"] = True
    if backend_edit(request, ctx, ExeEventForm, num):
        if "saved" in ctx and num == 0:
            # Add member to organizers
            (er, created) = EventRole.objects.get_or_create(event=ctx["saved"], number=1)
            if not er.name:
                er.name = "Organizer"
            er.members.add(request.user.member)
            er.save()
            return redirect("orga_quick", s=ctx["saved"].slug, n=1)
        return redirect("exe_events")
    ctx["add_another"] = False
    return render(request, "larpmanager/exe/edit.html", ctx)


@login_required
def exe_runs_edit(request, num):
    return exe_edit(request, OrgaRunForm, num, "exe_events", afield="event")


@login_required
def exe_events_appearance(request, num):
    return exe_edit(request, OrgaAppearanceForm, num, "exe_events", add_ctx={"add_another": False})


@login_required
def exe_templates(request):
    ctx = check_assoc_permission(request, "exe_templates")
    ctx["list"] = Event.objects.filter(assoc_id=ctx["a_id"], template=True).order_by("-updated")
    for el in ctx["list"]:
        el.roles = EventRole.objects.filter(event=el).order_by("number")
        if not el.roles:
            el.roles = [EventRole.objects.create(event=el, number=1, name="Organizer")]
    return render(request, "larpmanager/exe/templates.html", ctx)


@login_required
def exe_templates_edit(request, num):
    return exe_edit(request, ExeTemplateForm, num, "exe_templates")


@login_required
def exe_templates_config(request, num):
    add_ctx = def_user_ctx(request)
    get_event_template(add_ctx, num)
    add_ctx["features"].update(get_event_features(add_ctx["event"].id))
    add_ctx["add_another"] = False
    return exe_edit(request, OrgaConfigForm, num, "exe_templates", add_ctx=add_ctx)


@login_required
def exe_templates_roles(request, eid, num):
    add_ctx = def_user_ctx(request)
    get_event_template(add_ctx, eid)
    return exe_edit(request, ExeTemplateRolesForm, num, "exe_templates", add_ctx=add_ctx)


@login_required
def exe_pre_registrations(request):
    ctx = check_assoc_permission(request, "exe_pre_registrations")
    ctx["list"] = []
    ctx["pr"] = []

    ctx["seen"] = []

    for r in Event.objects.filter(assoc_id=request.assoc["id"], template=False):
        if not r.get_config("pre_register_active", False):
            continue

        pr = get_pre_registration(r)
        r.count = {}
        # print (pr)
        for idx in range(1, 6):
            r.count[idx] = 0
            if idx in pr:
                r.count[idx] = pr[idx]
        ctx["list"].append(r)
    return render(request, "larpmanager/exe/pre_registrations.html", ctx)


@login_required
def exe_deadlines(request):
    ctx = check_assoc_permission(request, "exe_deadlines")
    runs = get_coming_runs(request.assoc["id"])
    ctx["list"] = check_run_deadlines(runs)
    return render(request, "larpmanager/exe/deadlines.html", ctx)
