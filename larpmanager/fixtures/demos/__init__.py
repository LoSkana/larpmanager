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
"""Registry of demo fixture builders, run by the `load_demos` management command."""

from __future__ import annotations

from larpmanager.fixtures.demos.accounting_demo import build_accounting_demo
from larpmanager.fixtures.demos.campaign_demo import build_campaign_demo
from larpmanager.fixtures.demos.casting_demo import build_casting_demo
from larpmanager.fixtures.demos.experience_demo import build_experience_demo
from larpmanager.fixtures.demos.player_characters_demo import build_player_characters_demo
from larpmanager.fixtures.demos.writing_demo import build_writing_demo

DEMO_BUILDERS = [
    build_experience_demo,
    build_writing_demo,
    build_casting_demo,
    build_accounting_demo,
    build_player_characters_demo,
    build_campaign_demo,
]
