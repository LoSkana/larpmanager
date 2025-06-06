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
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_event_features
from larpmanager.models.association import Association
from larpmanager.models.event import Run
from larpmanager.utils.base import def_user_ctx, get_index_assoc_permissions
from larpmanager.utils.common import format_datetime
from larpmanager.utils.event import get_event_run, get_index_event_permissions
from larpmanager.utils.miscellanea import check_centauri
from larpmanager.utils.registration import registration_available
from larpmanager.views.larpmanager import lm_home
from larpmanager.views.user.event import calendar


def home(request, lang=None):
    if request.assoc["id"] == 0:
        return lm_home(request)

    return check_centauri(request) or calendar(request, lang)


@login_required
def manage(request, s=None, n=None):
    if request.assoc["id"] == 0:
        return redirect("home")

    if s:
        return _orga_manage(request, s, n)
    else:
        return _exe_manage(request)


def _get_registration_status(run):
    features = get_event_features(run.event_id)
    if "register_link" in features and run.event.register_link:
        return _("Registrations on external link")

    # check pre-register
    if not run.registration_open and run.event.get_config("pre_register_active", False):
        return _("Pre-registration active")

    dt = datetime.today()
    # check registration open
    if "registration_open" in features:
        if not run.registration_open:
            return _("Registrations opening not set")

        elif run.registration_open > dt:
            return _("Registrations opening at: %(date)s") % {"date": run.registration_open.strftime(format_datetime)}

    run.status = {}
    registration_available(run, features)

    # signup open, not already signed in
    status = run.status
    messages = {
        "primary": _("Registrations open"),
        "filler": _("Filler registrations"),
        "waiting": _("Waiting list registrations"),
    }

    # pick the first matching message (or None)
    mes = next((msg for key, msg in messages.items() if key in status), None)
    if mes:
        return mes
    else:
        return _("Registration closed")


def _exe_manage(request):
    ctx = def_user_ctx(request)
    get_index_assoc_permissions(ctx, request, request.assoc["id"])

    ctx["runs"] = Run.objects.filter(event__assoc_id=ctx["a_id"], development__in=[Run.START, Run.SHOW]).select_related(
        "event"
    )
    for run in ctx["runs"]:
        run.registration_status = _get_registration_status(run)

    return render(request, "larpmanager/manage/exe.html", ctx)


def _orga_manage(request, s, n):
    ctx = get_event_run(request, s, n, status=True)
    get_index_event_permissions(ctx, request, s)
    assoc = Association.objects.get(pk=request.assoc["id"])
    if assoc.get_config("interface_admin_links", False):
        get_index_assoc_permissions(ctx, request, request.assoc["id"], check=False)

    ctx["registration_status"] = _get_registration_status(ctx["run"])
    return render(request, "larpmanager/manage/orga.html", ctx)


def error_404(request, exception):
    # print(vars(request))
    # Print ("hello")
    return render(request, "404.html", {"exe": exception})


def error_500(request):
    return render(request, "500.html")


def after_login(request, subdomain, path=""):
    return redirect(f"https://{subdomain}.larpmanager.com/{path}")
