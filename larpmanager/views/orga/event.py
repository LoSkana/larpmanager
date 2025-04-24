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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import reset_run
from larpmanager.cache.run import get_cache_run
from larpmanager.forms.event import (
    OrgaAppearanceForm,
    OrgaConfigForm,
    OrgaEventButtonForm,
    OrgaEventForm,
    OrgaEventRoleForm,
    OrgaEventTextForm,
    OrgaRunForm,
)
from larpmanager.models.access import EventRole
from larpmanager.models.base import Feature, FeatureModule
from larpmanager.models.event import Event, EventButton, EventText
from larpmanager.utils.common import get_feature
from larpmanager.utils.deadlines import check_run_deadlines
from larpmanager.utils.edit import orga_edit
from larpmanager.utils.event import check_event_permission


@login_required
def orga_event(request, s, n):
    return orga_edit(request, s, n, "orga_event", OrgaEventForm, None, "manage")


@login_required
def orga_roles(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_roles")
    ctx["list"] = list(EventRole.objects.filter(event=ctx["event"]).order_by("number"))
    if not ctx["list"]:
        ctx["list"].append(EventRole.objects.create(event=ctx["event"], number=1, name="Organizer"))
    return render(request, "larpmanager/orga/roles.html", ctx)


@login_required
def orga_roles_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_roles", OrgaEventRoleForm, num)


@login_required
def orga_appearance(request, s, n):
    return orga_edit(request, s, n, "orga_appearance", OrgaAppearanceForm, None, "manage")


@login_required
def orga_run(request, s, n):
    return orga_edit(request, s, n, "orga_run", OrgaRunForm, get_cache_run(s, n), "manage")


@login_required
def orga_texts(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_texts")
    ctx["list"] = EventText.objects.filter(event_id=ctx["event"].id).order_by("typ", "default", "language")
    return render(request, "larpmanager/orga/texts.html", ctx)


@login_required
def orga_texts_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_texts", OrgaEventTextForm, num)


@login_required
def orga_buttons(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_buttons")
    ctx["list"] = EventButton.objects.filter(event_id=ctx["event"].id).order_by("number")
    return render(request, "larpmanager/orga/buttons.html", ctx)


@login_required
def orga_buttons_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_buttons", OrgaEventButtonForm, num)


@login_required
def orga_config(request, s, n):
    return orga_edit(request, s, n, "orga_config", OrgaConfigForm, None, "manage")


@login_required
def orga_features(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_features")
    # mod_id = list(ctx['event'].feature_modules.values_list('id', flat=True))
    prefetch = Prefetch(
        "features",
        queryset=Feature.objects.filter(overall=False, placeholder=False).order_by("order"),
    )
    ctx["modules"] = FeatureModule.objects.filter(default=False)
    ctx["modules"] = ctx["modules"].order_by("order").prefetch_related(prefetch)

    feat_id = list(ctx["event"].features.values_list("id", flat=True))

    for mod in ctx["modules"]:
        for el in mod.features.all():
            # if el.module and el.module.id not in mod_id:
            # continue
            el.activated = el.id in feat_id

    # slarpmanager_run(ctx['run'])
    return render(request, "larpmanager/orga/features.html", ctx)


def orga_features_go(request, ctx, num, on=True):
    get_feature(ctx, num)
    feat_id = list(ctx["event"].features.values_list("id", flat=True))
    f_id = ctx["feature"].id
    reset_run(ctx["run"])
    if on:
        if f_id not in feat_id:
            ctx["event"].features.add(f_id)
            messages.success(request, _("Feature activated"))
        else:
            messages.success(request, _("Feature already activated"))
    else:
        if f_id not in feat_id:
            messages.success(request, _("Feature already deactivated"))
        else:
            ctx["event"].features.remove(f_id)
            messages.success(request, _("Feature deactivated"))

    ctx["event"].save()
    # update cached event features, for itself, and the events for which they are parent
    for ev in Event.objects.filter(parent=ctx["event"]):
        ev.save()


@login_required
def orga_features_on(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_features")
    orga_features_go(request, ctx, num, on=True)
    return redirect("orga_features", s=s, n=n)


@login_required
def orga_features_off(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_features")
    orga_features_go(request, ctx, num, on=False)
    return redirect("orga_features", s=s, n=n)


@login_required
def orga_deadlines(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_deadlines")
    ctx["res"] = check_run_deadlines([ctx["run"]])[0]
    return render(request, "larpmanager/orga/deadlines.html", ctx)
