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
from django.core.cache import cache
from django.db.models import Count

from larpmanager.models.accounting import PaymentInvoice
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.larpmanager import LarpManagerReview, LarpManagerShowcase
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Character
from larpmanager.utils.common import round_to_two_significant_digits


def clear_larpmanager_home_cache():
    cache.delete(cache_cache_lm_home_key())


def cache_cache_lm_home_key():
    return "cache_lm_home"


def get_cache_lm_home():
    key = cache_cache_lm_home_key()
    res = cache.get(key)
    if res is None:
        res = update_cache_lm_home()
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def update_cache_lm_home():
    ctx = {}
    for el in [Event, Character, Registration, Member, PaymentInvoice]:
        nm = str(el.__name__).lower()
        cnt = el.objects.count()
        ctx[f"cnt_{nm}"] = int(round_to_two_significant_digits(cnt))

    que_run = Run.objects.annotate(num_reg=Count("registrations")).filter(num_reg__gt=5)
    ctx["cnt_run"] = int(round_to_two_significant_digits(que_run.count()))

    ctx["promoters"] = _get_promoters()
    ctx["showcase"] = _get_showcases()
    ctx["reviews"] = _get_reviews()
    return ctx


def _get_reviews():
    res = []
    for element in LarpManagerReview.objects.all():
        res.append(element.as_dict())
    return res


def _get_showcases():
    res = []
    for element in LarpManagerShowcase.objects.order_by("number"):
        res.append(element.as_dict())
    return res


def _get_promoters():
    que = Association.objects.exclude(promoter__isnull=True)
    que = que.exclude(promoter__exact="")
    res = []
    for element in que:
        res.append(element.promoter_dict())
    return res
