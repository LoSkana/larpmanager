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

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from larpmanager.accounting.registration import registration_payments_status
from larpmanager.cache.registration_lookup import get_active_registrations
from larpmanager.models.registration import CheckIn, Registration
from larpmanager.utils.core.checks import check_event_context


def _resolve_registration(run_id: int, registration_uuid: str) -> Registration:
    """Return the registration for the run matching a scanned QR code's uuid."""
    return Registration.objects.get(
        uuid=registration_uuid, run_id=run_id, cancellation_date__isnull=True, pending=False
    )


def _registration_row(registration: Registration) -> dict:
    """Build the JSON-serializable row used by the check-in list and chart."""
    registration_payments_status(registration)
    characters = ", ".join(rel.character.name for rel in registration.rcrs.select_related("character"))
    check_in = getattr(registration, "check_in", None)
    return {
        "uuid": registration.uuid,
        "member": registration.display_member(),
        "character": characters,
        "paid": registration.payment_status == "c",
        "checked_in_at": check_in.checked_in_at.isoformat() if check_in and check_in.checked_in_at else None,
    }


@login_required
def orga_checkin(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render the check-in dashboard: registration list, chart and scan control.

    Ships the full registration list for the run inline, so the page keeps working
    (lookup + local list/chart update) even without connectivity; a scan is synced
    to the server in the background, or queued in localStorage until it succeeds.
    """
    context = check_event_context(request, event_slug, "orga_checkin")

    registrations = (
        get_active_registrations(context["run"].id)
        .select_related("member", "check_in")
        .prefetch_related("rcrs__character")
    )
    rows = [_registration_row(registration) for registration in registrations]

    context["checkin_data"] = json.dumps(rows)
    return render(request, "larpmanager/orga/checkin.html", context)


@login_required
def orga_checkin_scan(request: HttpRequest, event_slug: str) -> JsonResponse:
    """Validate a scanned QR token and mark the matching registration present.

    Accepts an optional client-supplied `scanned_at` timestamp so scans buffered
    offline keep their real scan time once synced.
    """
    context = check_event_context(request, event_slug, "orga_checkin")

    registration_uuid = request.POST.get("uuid", "")
    try:
        registration = _resolve_registration(context["run"].id, registration_uuid)
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko", "error": "invalid_uuid"}, status=400)

    scanned_at = parse_datetime(request.POST.get("scanned_at", "")) or timezone.now()

    with transaction.atomic():
        check_in, _created = CheckIn.objects.select_for_update().get_or_create(registration=registration)
        if not check_in.checked_in_at:
            check_in.checked_in_at = scanned_at
            check_in.checked_in_by = request.user.member
            check_in.save()

    return JsonResponse({"res": "ok", "row": _registration_row(registration)})
