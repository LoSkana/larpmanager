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

from typing import Any

from django.http import Http404, HttpRequest


def is_lm_admin(request: HttpRequest) -> bool:
    """Check if user is a LarpManager administrator."""
    # Check if user has associated member profile
    if not hasattr(request.user, "member"):
        return False

    # Superusers always have admin privileges
    # TODO: Implement admin group membership check
    # This should verify if user belongs to LarpManager admin group
    return request.user.is_superuser


def check_lm_admin(request: HttpRequest) -> dict[str, Any]:
    """Verify user is LM admin and return admin context."""
    # Check if the current user has LM administrator privileges
    if not is_lm_admin(request):
        msg = "Not lm admin"
        raise Http404(msg)

    # Return admin context with association ID and admin flag
    return {"association_id": request.association["id"], "lm_admin": 1}


def get_allowed_managed() -> list[str]:
    """Get list of allowed management permission keys.

    This function returns a predefined list of permission strings that are
    allowed for management access within the LarpManager system. These
    permissions control access to various administrative and organizational
    features.

    Returns:
        list[str]: List of permission strings for management access. Includes
            both executive-level (exe_*) and organizational-level (orga_*)
            permissions.

    Example:
        >>> permissions = get_allowed_managed()
        >>> 'exe_events' in permissions
        True

    """
    return [
        # Executive-level permissions for organization-wide features
        "exe_events",
        "exe_accounting",
        "exe_preferences",
        # Event-specific organizational permissions
        "orga_event",
        "orga_cancellations",
        # Registration management permissions
        "orga_registration_form",
        "orga_registration_tickets",
        "orga_registrations",
        # Financial and sensitive data permissions
        "orga_accounting",
        "orga_sensitive",
        "orga_preferences",
    ]


def is_allowed_managed(ar: dict, context: dict) -> bool:
    """Check if user is allowed to access managed association features."""
    # Check if the association skin is managed and the user is not staff
    if context.get("skin_managed", False) and not context.get("is_staff", False):
        allowed = get_allowed_managed()

        # If the feature is a placeholder different than the management of events
        if ar["feature__placeholder"] and ar["slug"] not in allowed:
            return False

    return True
