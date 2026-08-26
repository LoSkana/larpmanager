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
from typing import TYPE_CHECKING

import qrcode
from django.conf import settings

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
