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

VERSIONS = [
    {
        "number": 16,
        "description": "Sidebar: menu links moved to sidebar, dashboard with menu actions",
        "available": True,
    },
    {
        "number": 17,
        "description": "Dashboard: widgets shown as cards in columns",
        "available": True,
    },
    {
        "number": 18,
        "description": "Form appearance: left-centered and more readable",
        "available": True,
    },
    {
        "number": 19,
        "description": "Menu appearance: more immediate and understandable",
        "available": True,
    },
    {
        "number": 20,
        "description": "User interface: cleaner and focused",
        "available": True,
    },
    {
        "number": 21,
        "description": "Clean form edit, with inline popups",
        "available": True,
    },
    {
        "number": 22,
        "description": "Introduces an organized user interface sidebar",
        "available": True,
    },
]

LATEST_AVAILABLE_VERSION = max(v["number"] for v in VERSIONS if v["available"])
