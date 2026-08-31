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

from django.utils.translation import gettext_lazy as _

# Kept in its own leaf module (no model imports) so that forms.miscellanea can
# use get_copy_choices without pulling in utils.core.copy, which imports
# forms.event and would otherwise create a circular import.

# Types of elements that can be copied, in the order they are shown
COPY_TARGETS: list[tuple[str, Any]] = [
    ("event", _("Event")),
    ("config", _("Configuration")),
    ("appearance", _("Appearance")),
    ("text", _("Texts")),
    ("navigation", _("Navigation")),
    ("role", _("Roles")),
    ("features", _("Features")),
    ("ticket", _("Registration Tickets")),
    ("question", _("Registration Form")),
    ("matchmaker_question", _("Matchmaker Form")),
    ("discount", _("Discount")),
    ("quota", _("Registration Quota")),
    ("installment", _("Registration Installment")),
    ("surcharge", _("Registration Surcharge")),
    ("writing_question", _("Character Sheet")),
    ("character", _("Characters")),
    ("experience", _("Experience")),
    ("faction", _("Factions")),
    ("quest", _("Quests and Traits")),
    ("prologue", _("Prologues")),
    ("speedlarp", _("SpeedLarps")),
    ("plot", _("Plots")),
    ("handout", _("Handout and templates")),
    ("workshop", _("Workshops")),
]


def get_copy_choices(features: Any) -> list[tuple[str, Any]]:
    """Return the element types available for copy, given the features of the event."""
    return [(key, label) for key, label in COPY_TARGETS if key != "matchmaker_question" or "matchmaker" in features]
