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

from django.apps import AppConfig


class LarpManagerConfig(AppConfig):
    """Django app configuration for LarpManager."""

    name = "larpmanager"

    def ready(self) -> None:
        """Initialize signal handlers and profiler receivers on app startup."""
        _ = __import__("larpmanager.models.signals")
        _ = __import__("larpmanager.utils.profiler.receivers")

        # Swap default AdminSite to OTP-enforced version
        from django.contrib import admin  # noqa: PLC0415

        from larpmanager.utils.auth.otp import LarpManagerOTPAdminSite  # noqa: PLC0415

        admin.site.__class__ = LarpManagerOTPAdminSite
