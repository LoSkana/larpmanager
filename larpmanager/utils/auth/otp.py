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

from typing import TYPE_CHECKING

from django_otp import user_has_device
from django_otp.admin import OTPAdminSite

if TYPE_CHECKING:
    from django.http import HttpRequest


class LarpManagerOTPAdminSite(OTPAdminSite):
    """Admin site that enforces OTP only for users who have enrolled a device.

    Users without any OTP device can still log in (so they can enroll TOTP
    from the admin). Once a device is enrolled, OTP verification is required
    on every subsequent login.
    """

    def has_permission(self, request: HttpRequest) -> bool:
        """Allow access if staff; require OTP verification only when a device is enrolled."""
        if not super(OTPAdminSite, self).has_permission(request):
            return False
        if user_has_device(request.user):
            return request.user.is_verified()
        return True
