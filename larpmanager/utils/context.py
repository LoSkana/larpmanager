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

from django.conf import settings as conf_settings

from larpmanager.models.association import Association


def cache_association(request):
    ctx = {}
    if hasattr(request, "assoc"):
        ctx["assoc"] = request.assoc
    if request.enviro == "staging":
        ctx["staging"] = 1
    if not hasattr(request, "user") or not hasattr(request.user, "member"):
        ctx["languages"] = conf_settings.LANGUAGES

    # TODO remove
    if hasattr(request, "assoc"):
        if request.assoc["id"] > 1:
            assoc = Association.objects.get(pk=request.assoc["id"])
            ctx["interface_old"] = assoc.get_config("interface_old", False)
        else:
            ctx["interface_old"] = True

    return ctx
