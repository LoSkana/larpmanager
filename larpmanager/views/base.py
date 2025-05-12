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
from django.contrib.auth.views import LoginView

from larpmanager.cache.role import get_index_assoc_permissions
from larpmanager.models.association import Association
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.event import get_event_run, get_index_event_permissions
from larpmanager.utils.miscellanea import check_centauri
from larpmanager.views.larpmanager import lm_home
from larpmanager.views.user.event import calendar


def home(request, lang=None):
   subdomain = request.session.get('subdomain')
   if subdomain:
        del request.session['subdomain']
        new_url = f"{request.scheme}://{subdomain}.larpmanager.com/{request.get_full_path()}"
        return redirect(new_url)  
    
    if request.assoc["id"] == 0:
        return lm_home(request)
    
    return check_centauri(request) or calendar(request, lang)


@login_required
def manage(request, s=None, n=None):
    if request.assoc["id"] == 0:
        return redirect("home")

    assoc = Association.objects.get(pk=request.assoc["id"])
    if not s:
        ctx = def_user_ctx(request)
        get_index_assoc_permissions(ctx, request, request.assoc["id"])
    else:
        ctx = get_event_run(request, s, n, status=True)
        get_index_event_permissions(ctx, request, s)
        if assoc.get_config("interface_admin_links", False):
            get_index_assoc_permissions(ctx, request, request.assoc["id"], check=False)

    ctx["manage"] = 1

    return render(request, "larpmanager/manage/index.html", ctx)


def error_404(request, exception):
    # print(vars(request))
    # Print ("hello")
    return render(request, "404.html", {"exe": exception})


def error_500(request):
    return render(request, "500.html")
    
# Maintain subdomain after login
class MyLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = MyAuthForm

    def form_valid(self, form):
        subdomain = self.request.session.get('subdomain')
        response = super().form_valid(form)
        if subdomain:
            self.request.session['subdomain'] = subdomain

        return response    

# Save the domain before the login
def prepare_login(request):
    request.session['subdomain'] = get_subdomain(request)
    
# Obtain subdomain    
def get_subdomain(request):
    host = request.get_host()
    host = host.split(":")[0]

    parts = host.split(".")

    domain_part_number = 2
    if len(parts) > domain_part_number:
        subdomain = parts[0]
    else:
        subdomain = None

    return subdomain    
