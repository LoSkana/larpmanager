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
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from larpmanager.cache.config import get_event_config
from larpmanager.models.casting import AssignmentTrait, QuestType, Trait
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.utils.core.common import get_element_event

if TYPE_CHECKING:
    from django.http import HttpRequest


def lottery_info(request: HttpRequest, context: dict) -> None:  # noqa: ARG001
    """Add lottery-related information to the context dictionary.

    Args:
        request: HTTP request object
        context: Context dictionary to update with lottery info

    """
    # Get number of lottery draws from event configuration
    context["num_draws"] = int(get_event_config(context["event"].id, "lottery_num_draws", context=context))

    # Get lottery ticket configuration
    context["ticket"] = get_event_config(context["event"].id, "lottery_ticket", context=context)

    # Count active lottery registrations
    context["num_lottery"] = Registration.objects.filter(
        run=context["run"],
        ticket__tier=TicketTier.LOTTERY,
        cancellation_date__isnull=True,
    ).count()

    # Count definitive (confirmed) registrations excluding special tiers
    context["num_def"] = (
        Registration.objects.filter(run=context["run"], cancellation_date__isnull=True)
        .exclude(ticket__tier__in=[TicketTier.LOTTERY, TicketTier.STAFF, TicketTier.NPC, TicketTier.WAITING])
        .count()
    )


def _save_questbuilder(context: dict, form: object, registration: Any) -> None:
    """Save quest type assignments from questbuilder form.

    Args:
        context: Context dictionary containing event and run data
        form: Form containing quest type selections
        registration: Registration object for the member

    """
    for qt in QuestType.objects.filter(event=context["event"]):
        trait_uuid = form.cleaned_data.get(f"qt_{qt.uuid}")
        base_kwargs = {
            "run": context["run"],
            "member": registration.member,
            "typ": qt.number,
        }

        if not trait_uuid or trait_uuid == "0":
            AssignmentTrait.objects.filter(**base_kwargs).delete()
            continue

        trait = get_element_event(context, trait_uuid, Trait)
        AssignmentTrait.objects.update_or_create(
            **base_kwargs,
            defaults={"trait": trait},
        )
