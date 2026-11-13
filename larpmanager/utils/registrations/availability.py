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

from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_event_features
from larpmanager.cache.registration_counts import get_registration_counts
from larpmanager.models.form import QuestionApplicable, WritingOption

if TYPE_CHECKING:
    from larpmanager.models.event import Run


def registration_available(run: Run, features: dict, run_status: dict, context: dict | None = None) -> None:
    """Check if registration is available based on capacity and rules.

    Validates registration availability considering maximum participants,
    ticket quotas, and advanced registration constraints. Updates the run's
    status dictionary with availability information.

    Args:
        run: The run object containing event and status information
        features: Dictionary of enabled features for the event
        run_status: Dictionary with run status
        context: Optional context dictionary containing cached data
    """
    # Extract values from context dictionary if provided
    if context is None:
        context = {}

    # Skip advanced registration rules if no maximum participant limit is set
    if run.event.max_pg == 0:
        run_status["primary"] = True
        return

    # Get registration counts if not provided
    registration_counts = context.get("registration_counts")
    if registration_counts is None:
        registration_counts = get_registration_counts(run.id, run.event_id)

    # Calculate remaining primary tickets
    remaining_primary_tickets = run.event.max_pg - registration_counts.get("count_player", 0)

    # Get event features if not provided
    if not features:
        features = get_event_features(run.event_id)

    # Check if primary tickets are available
    if remaining_primary_tickets > 0:
        run_status["primary"] = True

        # Show urgency warning when tickets are running low
        percentage_threshold_for_urgency = 0.3
        absolute_threshold_for_urgency = 10
        if (
            remaining_primary_tickets < absolute_threshold_for_urgency
            or remaining_primary_tickets * 1.0 / run.event.max_pg < percentage_threshold_for_urgency
        ):
            run_status["count"] = remaining_primary_tickets
            run_status["additional"] = _(" Hurry: only %(num)d tickets available.") % {"num": remaining_primary_tickets}
        return

    # Check if filler tickets are available (fallback option)
    if "filler" in features and _available_filler(run, run_status, registration_counts):
        return

    # Check if waiting list is available (last resort option)
    if "waiting" in features and _available_waiting(run, run_status, registration_counts):
        return

    # No registration options available - mark as closed
    run_status["closed"] = True
    return


def _available_waiting(run: Run, run_status: dict, registration_counts: dict) -> bool:
    """Check if waiting list spots are available for a registration.

    Args:
        run: Run object
        registration_counts: Dictionary containing registration counts including 'count_wait'
        run_status: Dictionary with run status

    Returns:
        bool: True if waiting list spots are available, False otherwise

    """
    # Handle infinite waiting list capacity
    if run.event.max_waiting == 0:
        run_status["waiting"] = True
        run_status["count"] = None  # Infinite
        return True

    # Check if limited waiting list has available spots
    if run.event.max_waiting > 0:
        # Calculate remaining waiting list capacity
        remaining_waiting_spots = run.event.max_waiting - registration_counts["count_wait"]

        # Set status if spots are available
        if remaining_waiting_spots > 0:
            run_status["waiting"] = True
            run_status["count"] = remaining_waiting_spots
            run_status["additional"] = _(" Hurry: only %(num)d tickets available.") % {"num": remaining_waiting_spots}
            return True

    # No waiting list spots available
    return False


def _available_filler(run: Run, run_status: dict, registration_counts: Any) -> bool:
    """Check if filler tickets are available for the given registration.

    Args:
        run: Run object
        registration_counts: Dictionary containing registration counts including 'count_fill'
        run_status: Dictionary with run status

    Returns:
        bool: True if filler tickets are available, False otherwise

    """
    # Handle infinite filler tickets case
    if run.event.max_filler == 0:
        run_status["filler"] = True
        run_status["count"] = None  # Infinite
        return True

    # Handle limited filler tickets case
    if run.event.max_filler > 0:
        # Calculate remaining filler tickets
        remaining_filler = run.event.max_filler - registration_counts["count_fill"]

        # Check if any filler tickets are still available
        if remaining_filler > 0:
            run_status["filler"] = True
            run_status["count"] = remaining_filler
            # Add urgency message for limited availability
            run_status["additional"] = _(" Hurry: only %(num)d tickets available.") % {"num": remaining_filler}
            return True

    # No filler tickets available
    return False


def get_character_options_availability(run: Run) -> list[dict[str, Any]]:
    """Return occupancy info for limited character options that don't depend on other options.

    Only options with a max_available limit and no prerequisites (requirements) are
    included, since those are the only ones whose availability can be shown upfront,
    before the player has started answering the character form.

    Args:
        run: The run to compute option occupancy for.

    Returns:
        List of dicts with name, question name, max_available and used count.

    """
    counts = get_registration_counts(run.id, run.event_id)

    options = WritingOption.objects.filter(
        event_id=run.event_id,
        question__applicable=QuestionApplicable.CHARACTER,
        max_available__gt=0,
        requirements__isnull=True,
    ).select_related("question")

    return [
        {
            "question": option.question.name,
            "name": option.name,
            "available": option.max_available - counts.get(f"option_char_{option.id}", 0),
        }
        for option in options
    ]
