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
from django.db.models.signals import post_save
from django.dispatch import receiver

from larpmanager.models.association import Association


def reset_cache_promoters():
    cache.delete(cache_cache_promoters_key())


def cache_cache_promoters_key():
    return "cache_promoters"


def get_cache_promoters():
    key = cache_cache_promoters_key()
    res = cache.get(key)
    if not res:
        res = update_cache_promoters()
        cache.set(key, res)
    return res


def update_cache_promoters():
    que = Association.objects.exclude(promoter__isnull=True)
    que = que.exclude(promoter__exact="")
    res = []
    for s in que:
        res.append((s.slug, s.name, s.promoter_thumb.url))
    return res


@receiver(post_save, sender=Association)
def update_association_reset_promoters(sender, instance, **kwargs):
    reset_cache_promoters()
