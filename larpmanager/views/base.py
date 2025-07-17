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
import secrets
import uuid
from datetime import datetime

from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from larpmanager.forms.member import MyAuthForm
from larpmanager.utils.common import welcome_user
from larpmanager.utils.miscellanea import check_centauri
from larpmanager.utils.tutorial_query import query_index
from larpmanager.views.larpmanager import lm_home
from larpmanager.views.user.event import calendar


class MyLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = MyAuthForm

    def form_valid(self, form):
        welcome_user(self.request, form.get_user())
        return super().form_valid(form)


def home(request, lang=None):
    if request.assoc["id"] == 0:
        return lm_home(request)

    return check_centauri(request) or calendar(request, lang)


def error_404(request, exception):
    return render(request, "404.html", {"exe": exception})


def error_500(request):
    return render(request, "500.html")


def after_login(request, subdomain, path=""):
    user = request.user
    if not user.is_authenticated:
        return redirect("/login/")

    token = secrets.token_urlsafe(32)
    cache.set(f"session_token:{token}", user.id, timeout=60)

    base_domain = get_base_domain(request)
    return redirect(f"https://{subdomain}.{base_domain}/{path}?token={token}")


def get_base_domain(request):
    host = request.get_host()
    parts = host.split(".")
    domain_parts = 2
    if len(parts) >= domain_parts:
        return ".".join(parts[-2:])
    return host


@require_POST
def tutorial_query(request):
    return query_index(request)


@csrf_exempt
def upload_image(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{uuid.uuid4().hex}{file.name[file.name.rfind('.') :]}"
        path = default_storage.save(f"tinymce_uploads/{request.assoc['id']}/{filename}", file)
        return JsonResponse({"location": default_storage.url(path)})
    return JsonResponse({"error": "Invalid request"}, status=400)
