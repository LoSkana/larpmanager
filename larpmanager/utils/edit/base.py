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

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


class Action(Enum):
    """Action to be executed upon element."""

    NEW = "new"
    EDIT = "edit"
    DELETE = "delete"
    VIEW = "view"
    VERSIONS = "versions"
    ORDER = "order"


def prepare_change(request: HttpRequest, context: dict, action_data: dict) -> str:
    """Prepare context and redirect view for create/edit actions.

    Configures the context dictionary based on the type of form being processed
    (association, event, or member) and determines the appropriate redirect view.
    Also extracts section navigation parameters from the URL for form jump functionality.

    Args:
        request: HTTP request object containing resolver match data
        context: Context dictionary to update with form configuration
        action_data: Dictionary containing form metadata (assoc_form, event_form, member_form flags)

    Returns:
        str | None: Redirect view name ("manage" for special forms, None otherwise)
    """
    redirect_view = None

    if action_data.get("assoc_form"):
        context["add_another"] = False
        context["assoc_form"] = True
        redirect_view = "manage"

    if action_data.get("event_form"):
        context["add_another"] = False
        context["event_form"] = True
        redirect_view = "manage"

    if action_data.get("member_form"):
        context["add_another"] = False
        context["member_form"] = True
        redirect_view = "manage"

    # Extract section parameter from URL if present (for jump_section in forms)
    if hasattr(request, "resolver_match") and request.resolver_match:
        section = request.resolver_match.kwargs.get("section")
        if section:
            context["jump_section"] = section

    # Pass frame parameter to context for modal rendering
    if request.GET.get("frame") == "1" or request.POST.get("frame") == "1":
        context["frame"] = True

    return redirect_view
