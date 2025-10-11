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
from django.core.exceptions import ObjectDoesNotExist

from larpmanager.accounting.base import get_payment_details
from larpmanager.cache.feature import get_assoc_features
from larpmanager.models.association import Association
from larpmanager.models.registration import Registration


def clear_association_cache(s):
    key = cache_assoc_key(s)
    cache.delete(key)


def cache_assoc_key(s):
    return f"assoc_{s}"


def get_cache_assoc(s):
    key = cache_assoc_key(s)
    res = cache.get(key)
    if not res:
        res = init_cache_assoc(s)
        if not res:
            return None
        cache.set(key, res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def init_cache_assoc(a_slug):
    """Initialize association cache with configuration data.

    Args:
        a_slug: Association slug identifier

    Returns:
        dict: Association cache data or None if not found
    """
    try:
        assoc = Association.objects.get(slug=a_slug)
    except ObjectDoesNotExist:
        return None

    assoc_dict = assoc.as_dict()

    _init_payments(assoc, assoc_dict)

    _init_member_fields(assoc, assoc_dict)

    if assoc.profile:
        try:
            assoc_dict["favicon"] = assoc.profile_fav.url
            assoc_dict["logo"] = assoc.profile_thumb.url
            assoc_dict["image"] = assoc.profile.url
        except FileNotFoundError:
            pass

    for m in [
        "created",
        "updated",
        "mandatory_fields",
        "optional_fields",
        "voting_candidates",
        "profile",
        "activated",
        "key",
    ]:
        if m in assoc_dict:
            del assoc_dict[m]

    _init_features(assoc, assoc_dict)

    _init_skin(assoc, assoc_dict)

    max_demo = 10
    assoc_dict["demo"] = Registration.objects.filter(run__event__assoc_id=assoc.id).count() < max_demo

    return assoc_dict


def _init_skin(assoc, el):
    el["skin_css"] = assoc.skin.default_css
    el["main_domain"] = assoc.skin.domain
    el["platform"] = assoc.skin.name
    el["skin_id"] = assoc.skin.id
    el["skin_managed"] = assoc.skin.managed


def _init_features(assoc, el):
    """Initialize association features and related configuration in cache element.

    Args:
        assoc: Association object to get features from
        el: Cache element dictionary to populate with features and configs
    """
    el["features"] = get_assoc_features(assoc.id)

    if "custom_mail" in el["features"]:
        k = "mail_server_use_tls"
        el[k] = assoc.get_config(k, False)
        for s in ["host", "port", "host_user", "host_password"]:
            k = "mail_server_" + s
            el[k] = assoc.get_config(k)

    if "token_credit" in el["features"]:
        for s in ["token_name", "credit_name"]:
            el[s] = assoc.get_config("token_credit_" + s, None)

    if "centauri" in el["features"]:
        prob = assoc.get_config("centauri_prob")
        if prob:
            el["centauri_prob"] = prob


def _init_member_fields(assoc, el):
    el["members_fields"] = set()
    for fl in assoc.mandatory_fields.split(","):
        el["members_fields"].add(fl)
    for fl in assoc.optional_fields.split(","):
        el["members_fields"].add(fl)


def _init_payments(assoc, el):
    el["payment_currency"] = assoc.get_payment_currency_display()
    el["currency_symbol"] = assoc.get_currency_symbol()
    el["methods"] = {}
    payment_details = get_payment_details(assoc)
    for m in assoc.payment_methods.all():
        mel = m.as_dict()
        for s in ["fee", "descr"]:
            mel[s] = payment_details.get(f"{m.slug}_{s}")
        el["methods"][m.slug] = mel
