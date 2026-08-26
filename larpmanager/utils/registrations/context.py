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

from pathlib import Path
from typing import TYPE_CHECKING, Any

import qrcode
from django.conf import settings
from django.http import Http404

from larpmanager.cache.config import get_event_config
from larpmanager.cache.question import get_cached_registration_questions
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.models.event import PreRegistration
from larpmanager.models.registration import Registration
from larpmanager.utils.core.common import add_context_by_uuid, geo_prefetch

if TYPE_CHECKING:
    from django.db.models import QuerySet


def get_registration(context: dict, registration_uuid: str) -> None:
    """Get registration by ID and add to context."""
    add_context_by_uuid(
        context,
        "registration",
        Registration,
        registration_uuid,
        set_name=True,
        run=context["run"],
    )


def with_geo_configs_registrations(registrations_qs: QuerySet) -> QuerySet:
    """Prefetch pub_lat/pub_lon EventConfigs through registration->run->event."""
    return registrations_qs.prefetch_related(geo_prefetch("run__event"))


def get_checkin_qr_path(registration: Registration) -> str:
    """Return the absolute path to the registration's check-in QR code PNG, generating it if missing.

    The QR code encodes the registration's own uuid, so staff scanning it can resolve the
    participant even without connectivity (see orga/checkin.py).
    """
    directory = Path(settings.MEDIA_ROOT) / "checkin_qr"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{registration.uuid}.png"
    if not path.exists():
        qrcode.make(registration.uuid).save(path)
    return str(path)


def _register_prepare(context: dict, registration: Any) -> Any:
    """Prepare registration context with payment information and locks.

    Args:
        context: Context dictionary to update
        registration: Existing registration instance or None for new registration

    Returns:
        bool: True if this is a new registration, False if updating existing

    """
    is_new_registration = True
    context["tot_payed"] = 0
    if registration:
        context["tot_payed"] = registration.tot_payed
        is_new_registration = False

        # we lock changing values with lower prices if there is already a payment (done or submitted)
        has_pending_payment = (
            PaymentInvoice.objects.filter(
                idx=registration.id,
                member_id=registration.member_id,
                status=PaymentStatus.SUBMITTED,
                typ=PaymentType.REGISTRATION,
            ).count()
            > 0
        )
        context["payment_lock"] = has_pending_payment or registration.tot_payed > 0
        registration.pending = has_pending_payment

    _add_bring_friend_discounts(context)

    return is_new_registration


def _add_bring_friend_discounts(context: dict) -> None:
    """Add bring-a-friend discount configuration to context if feature is enabled."""
    if "bring_friend" not in context["features"]:
        return

    # Retrieve discount configuration for both directions (to/from)
    for discount_config_name in ["bring_friend_discount_to", "bring_friend_discount_from"]:
        context[discount_config_name] = get_event_config(context["event"].id, discount_config_name, context=context)


def get_registration_gift(context: dict, gift_uuid: str) -> Registration | None:
    """Get a registration with gift redeem code for the current user."""
    if not gift_uuid:
        return None

    try:
        # Query for valid gift registration matching all criteria
        return Registration.objects.get(
            uuid=gift_uuid,
            run=context["run"],
            member=context["member"],
            redeem_code__isnull=False,  # Must have a redeem code (gift)
            cancellation_date__isnull=True,  # Must not be cancelled
        )
    except Exception as error:
        # Convert any lookup error to 404 for security
        msg = "what are you trying to do?"
        raise Http404(msg) from error


def _get_registration_fields(context: dict, member: Any, event_questions: list | None = None) -> dict:
    """Get registration questions that are accessible to the given member.

    Args:
        context: Context dictionary containing event, features, run, and all_runs information
        member: Member object to check question access permissions for
        event_questions: Pre-fetched list of questions; fetched from cache if not provided

    Returns:
        Dictionary mapping question IDs to RegistrationQuestion objects that the member can access

    """
    registration_questions = {}

    if event_questions is None:
        event_questions = get_cached_registration_questions(context["event"].id)

    for question in event_questions:
        # Check if question has access restrictions enabled
        allowed_map = question.get("allowed_map", [])
        if "reg_que_allowed" in context["features"] and allowed_map and allowed_map[0]:
            current_run_id = context["run"].id

            # Check if user is an organizer for this run
            is_organizer = 1 in context["all_runs"].get(current_run_id, {})

            # Skip question if user is not organizer and not in allowed list
            if not is_organizer and member.id not in allowed_map:
                continue

        # Add accessible question to results
        registration_questions[question["uuid"]] = question

    return registration_questions


def get_pre_registration(event: Any) -> dict[str, list | dict[int, int]]:
    """Get pre-registration data for an event.

    Args:
        event: The event to get pre-registration data for.

    Returns:
        Dictionary containing:
        - 'list': All pre-registrations for the event
        - 'pred': Pre-registrations from members who haven't signed up yet
        - Additional keys with preference counts

    """
    # Initialize result dictionary with empty lists
    result_data = {"list": [], "pred": []}

    # Get set of member IDs who have already registered for this event
    signed_member_ids = set(
        Registration.objects.filter(run__event=event, cancellation_date__isnull=True, pending=False).values_list(
            "member_id", flat=True
        )
    )

    # Get all pre-registrations ordered by preference and creation date
    pre_registrations = PreRegistration.objects.filter(event=event).order_by("pref", "created")

    # Process each pre-registration
    for pre_registration in pre_registrations.select_related("member"):
        # Check if member hasn't signed up yet
        if pre_registration.member_id not in signed_member_ids:
            result_data["pred"].append(pre_registration)
        else:
            # Mark as already signed up
            pre_registration.signed = True

        # Add to main list and count preferences
        result_data["list"].append(pre_registration)
        if pre_registration.pref not in result_data:
            result_data[pre_registration.pref] = 0
        result_data[pre_registration.pref] += 1

    return result_data
