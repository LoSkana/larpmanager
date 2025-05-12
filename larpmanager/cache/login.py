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

from django.core.cache import cache


def get_session_key(request):
    session_id = request.session.session_key
    if not session_id:
        request.session.save()
        session_id = request.session.session_key
    return f"login_{session_id}"


def set_login_subdomain(request):
    key = get_session_key(request)
    subdomain = get_subdomain(request)
    cache.set(key, subdomain, 600)


def get_login_subdomain(request):
    key = get_session_key(request)
    return cache.get(key)


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
