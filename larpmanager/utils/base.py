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

from django.utils.translation import gettext_lazy as _

from larpmanager.cache.links import cache_event_links
from larpmanager.models.association import Association
from larpmanager.models.member import get_user_membership
from larpmanager.models.utils import get_payment_details
from larpmanager.utils.exceptions import MembershipException


def def_user_ctx(request):
    # check the home page has been reached, redirect to the correct organization page
    if request.assoc["id"] == 0:
        if hasattr(request, "user") and hasattr(request.user, "member"):
            assocs = [el.assoc for el in request.user.member.memberships.all()]
            raise MembershipException(assocs)
        raise MembershipException()

    res = {"a_id": request.assoc["id"]}
    for s in request.assoc:
        res[s] = request.assoc[s]

    if hasattr(request, "user") and hasattr(request.user, "member"):
        res["member"] = request.user.member
        res["membership"] = get_user_membership(request.user.member, request.assoc["id"])
    res.update(cache_event_links(request))

    if "token_credit" in res["features"]:
        if not res["token_name"]:
            res["token_name"] = _("Tokens")
        if not res["credit_name"]:
            res["credit_name"] = _("Credits")

    return res


def is_shuttle(request):
    if not hasattr(request.user, "member"):
        return False
    return "shuttle" in request.assoc and request.user.member.id in request.assoc["shuttle"]


def update_payment_details(request, ctx):
    assoc = Association.objects.get(pk=request.assoc["id"])
    payment_details = get_payment_details(assoc)
    ctx.update(payment_details)
