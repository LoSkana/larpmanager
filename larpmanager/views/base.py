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

from django.shortcuts import redirect, render

from larpmanager.utils.miscellanea import check_centauri
from larpmanager.views.larpmanager import lm_home
from larpmanager.views.user.event import calendar


def home(request, lang=None):
    if request.assoc["id"] == 0:
        return lm_home(request)

    return check_centauri(request) or calendar(request, lang)


def error_404(request, exception):
    return render(request, "404.html", {"exe": exception})


def error_500(request):
    return render(request, "500.html")


def after_login(request, subdomain, path=""):
    return redirect(f"https://{subdomain}.larpmanager.com/{path}")
