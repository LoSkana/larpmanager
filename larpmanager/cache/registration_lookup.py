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
"""Registration/ticket lookups with no dependency back onto the registration signal chain.

Split out of larpmanager.cache.registration: larpmanager.cache.accounting needs these
lookups, while larpmanager.cache.registration itself needs
larpmanager.utils.registrations.signals (which pulls in larpmanager.cache.accounting),
so keeping everything in one module would create an import cycle.
"""

from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from larpmanager.models.registration import Registration, RegistrationTicket
from larpmanager.models.utils import decimal_to_str
from main.settings import CACHE_TIMEOUT_1_DAY


def get_active_registrations(run_id: int) -> Any:
    """Return registrations for a run that are neither cancelled nor a pending signup request."""
    return Registration.objects.filter(run_id=run_id, cancellation_date__isnull=True, pending=False)


def cache_registration_tickets_key(event_id: int) -> str:
    """Generate cache key for registration tickets."""
    return f"registration_tickets_{event_id}"


def clear_registration_tickets_cache(event_id: int) -> None:
    """Clear cached registration tickets for an event."""
    cache.delete(cache_registration_tickets_key(event_id))


def get_registration_tickets(event_id: int, *, reset_cache: bool = False) -> list[dict]:
    """Get registration tickets for an event with caching.

    Returns tickets ordered by 'order' field as dictionaries.

    Args:
        event_id: The event ID to get tickets for
        reset_cache: If True, force cache refresh

    Returns:
        List of ticket dictionaries ordered by order field

    """
    cache_key = cache_registration_tickets_key(event_id)

    cached_tickets = None if reset_cache else cache.get(cache_key)

    if cached_tickets is None:
        tickets = RegistrationTicket.objects.filter(event_id=event_id).order_by("order")
        cached_tickets = [ticket.as_dict(many_to_many=False) for ticket in tickets]
        # Cache for 1 day (tickets rarely change after event setup)
        cache.set(cache_key, cached_tickets, timeout=CACHE_TIMEOUT_1_DAY)

    return cached_tickets


def get_registration_tickets_by_tier(event_id: int, tier: str) -> list[dict]:
    """Get registration tickets filtered by tier."""
    all_tickets = get_registration_tickets(event_id)
    return [ticket for ticket in all_tickets if ticket["tier"] == tier]


def get_registration_ticket_by_id(event_id: int, ticket_id: int) -> dict | None:
    """Get a specific registration ticket by ID."""
    all_tickets = get_registration_tickets(event_id)
    for ticket in all_tickets:
        if ticket["id"] == ticket_id:
            return ticket
    return None


def get_ticket_form_text(ticket: dict, currency_symbol: str = "") -> str:
    """Generate formatted text representation for form display from ticket dict."""
    formatted_text = ticket["name"]

    # Add price information if available
    if ticket.get("price"):
        formatted_text += f" - {decimal_to_str(ticket['price'])}{currency_symbol}"

    # Add availability count if ticket has available key
    if "available" in ticket:
        formatted_text += f" - ({_('Available')}: {ticket['available']})"

    return formatted_text
