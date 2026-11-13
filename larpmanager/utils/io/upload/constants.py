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

import re

from larpmanager.models.experience import AbilityExp
from larpmanager.models.form import WritingOption
from larpmanager.models.writing import Character, Faction

MAX_CSV_ROWS = 10_000
MAX_COMMA_VALUES = 100
MAX_CSV_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_PROFILE_IMAGE_SIZE = 1024 * 1024  # 1MB
MAX_PROFILE_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB: guard against decompression bombs
_QUALITY_START = 95
_QUALITY_STEP = 10
_QUALITY_MIN = 20
_SCALE_STEP = 0.1
_SCALE_MIN = 0.1

_HTML_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>")

# Criterion and delivery columns whose empty value is meaningful: it clears the relation instead of being ignored
_RELATION_COLUMNS = frozenset({"prerequisites", "requirements", "factions", "characters"})

_ABILITY_PLAIN_FIELDS = frozenset({"descr"})

_REL_PREREQUISITES = ("prerequisites", AbilityExp, "Prerequisite")
_REL_REQUIREMENTS = ("requirements", WritingOption, "requirements")
_REL_FACTIONS = ("factions", Faction, "Faction")
_REL_CHARACTERS = ("characters", Character, "Character")
