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
    cache.delete(cache_larpmanager_home_key())


def cache_larpmanager_home_key():
    return "cache_lm_home"


def get_cache_lm_home() -> dict:
    """Get cached LM home data, computing if not cached.

    Returns:
        Cached or freshly computed home data.
    """
    # Get cache key and attempt to retrieve cached data
    cache_key = cache_larpmanager_home_key()
    cached_data = cache.get(cache_key)

    # If cache miss, compute fresh data and cache it
    if cached_data is None:
        cached_data = update_cache_lm_home()
        cache.set(cache_key, cached_data, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)

    return cached_data


def update_cache_lm_home() -> dict[str, int | list]:
    """Update and return cached data for the LarpManager home page.

    Collects statistics for various models including events, characters,
    registrations, members, and payment invoices. Also gathers data about
    active runs, promoters, showcases, and reviews.

    Returns:
        dict[str, int | list]: Dictionary containing:
            - cnt_<model>: Rounded count for each model type
            - cnt_run: Count of runs with more than 5 registrations
            - promoters: List of promoter data
            - showcase: List of showcase items
            - reviews: List of review data
    """
    context = {}

    # Count objects for main models and round to two significant digits
    for el in [Event, Character, Registration, Member, PaymentInvoice]:
        nm = str(el.__name__).lower()
        cnt = el.objects.count()
        context[f"cnt_{nm}"] = int(round_to_two_significant_digits(cnt))

    # Count runs that have more than 5 registrations
    que_run = Run.objects.annotate(num_reg=Count("registrations")).filter(num_reg__gt=5)
    context["cnt_run"] = int(round_to_two_significant_digits(que_run.count()))

    # Gather additional display data
    context["promoters"] = _get_promoters()
    context["showcase"] = _get_showcases()
    context["reviews"] = _get_reviews()

    return context


def _get_reviews() -> list[dict]:
    """Get all LARP manager reviews as dictionaries.

    Returns:
        List of review dictionaries.
    """
    reviews = []
    # Convert each review object to dictionary representation
    for review in LarpManagerReview.objects.all():
        reviews.append(review.as_dict())
    return reviews


def _get_showcases() -> list[dict]:
    """Return all showcases as a list of dictionaries ordered by number."""
    showcases = []
    # Iterate through showcases ordered by number and convert to dict
    for showcase in LarpManagerShowcase.objects.order_by("number"):
        showcases.append(showcase.as_dict())
    return showcases


def _get_promoters() -> list[dict]:
    """Get all promoters from associations that have promoter data.

    Returns:
        List of promoter dictionaries from associations with valid promoter data.
    """
    # Filter associations that have promoter data
    associations_queryset = Association.objects.exclude(promoter__isnull=True)
    associations_queryset = associations_queryset.exclude(promoter__exact="")

    # Convert each association's promoter to dictionary format
    promoters_list = []
    for association in associations_queryset:
        promoters_list.append(association.promoter_dict())
    return promoters_list
