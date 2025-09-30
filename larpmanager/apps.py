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
    name = "larpmanager"

    # Import signals
    def ready(self):
        _ = __import__("larpmanager.models.signals")
        _ = __import__("larpmanager.utils.profiler.receivers")
        # Import cache modules individually to register signal handlers
        _ = __import__("larpmanager.cache.accounting")
        _ = __import__("larpmanager.cache.association")
        _ = __import__("larpmanager.cache.character")
        _ = __import__("larpmanager.cache.feature")
        _ = __import__("larpmanager.cache.fields")
        _ = __import__("larpmanager.cache.larpmanager")
        _ = __import__("larpmanager.cache.links")
        _ = __import__("larpmanager.cache.permission")
        _ = __import__("larpmanager.cache.registration")
        _ = __import__("larpmanager.cache.role")
        _ = __import__("larpmanager.cache.run")
        _ = __import__("larpmanager.cache.skin")
        _ = __import__("larpmanager.cache.text_fields")
