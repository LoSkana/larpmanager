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

"""Utilities for managing sticky messages stored in MemberConfig."""

from __future__ import annotations

import ast
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from larpmanager.cache.config import save_single_config

if TYPE_CHECKING:
    from larpmanager.models.member import Member


def _get_sticky(member: Member) -> dict:
    """Get sticky messages for member."""
    value = member.get_config("sticky", default_value="{}")
    return ast.literal_eval(value)


def add_sticky_message(
    member: Member,
    message: str,
    expires_days: int = 7,
    element_uuid: str | None = None,
) -> str:
    """Add a new sticky message for a member.

    Args:
        member: Member instance to add message for
        message: Message text to display
        expires_days: Number of days until message expires (default: 7)
        element_uuid: Optional UUID of related element (e.g., event UUID)

    Returns:
        str: The ID of the created message

    """
    # Get existing sticky messages or create empty dict
    sticky_messages = _get_sticky(member)
    if not isinstance(sticky_messages, dict):
        sticky_messages = {}

    # Generate unique ID for this message
    message_id = str(uuid.uuid4())

    # Calculate expiration time
    expires_at = timezone.now() + timedelta(days=expires_days)

    # Add new message
    sticky_messages[message_id] = {
        "message": message,
        "created_at": timezone.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "dismissed": False,
        "element_uuid": element_uuid,
    }

    # Save back to config
    save_single_config(member, "sticky", sticky_messages)

    return message_id


def get_sticky_messages(member: Member, element_uuid: str | None = None) -> list[dict]:
    """Get all active sticky messages for a member.

    Filters out dismissed and expired messages. Optionally filters by element_uuid.
    Also performs automatic cleanup of old dismissed or expired messages.

    Args:
        member: Member instance to get messages for
        element_uuid: Optional UUID to filter messages for specific element (e.g., event)

    Returns:
        list: List of active sticky message dicts with 'id' included

    """
    # Get sticky messages from config
    sticky_messages = _get_sticky(member)
    if not isinstance(sticky_messages, dict):
        return []

    # Current time for expiration check
    current_time = timezone.now()

    # Filter active messages and identify messages to cleanup
    active_messages = []
    messages_to_remove = []

    for message_id, message_data in sticky_messages.items():
        _process_sticky(active_messages, current_time, element_uuid, message_data, message_id, messages_to_remove)

    # Cleanup old messages if any found
    if messages_to_remove:
        for message_id in messages_to_remove:
            del sticky_messages[message_id]
        save_single_config(member, "sticky", sticky_messages)

    # Sort by created_at descending (newest first)
    active_messages.sort(key=lambda m: m.get("created_at", ""), reverse=True)

    return active_messages


def _process_sticky(
    active_messages: list,
    current_time: datetime,
    element_uuid: str,
    message_data: dict,
    message_id: int,
    messages_to_remove: list,
) -> None:
    """Process sticky messages for visualization."""
    # Mark dismissed messages for cleanup
    if message_data.get("dismissed", False):
        messages_to_remove.append(message_id)
        return

    # Mark expired messages for cleanup
    expires_at_str = message_data.get("expires_at")
    if expires_at_str:
        expires_at = timezone.datetime.fromisoformat(expires_at_str)
        if expires_at < current_time:
            messages_to_remove.append(message_id)
            return

    # Filter by element_uuid if provided
    message_element_uuid = message_data.get("element_uuid")
    if element_uuid is not None:
        # If filtering by element_uuid, only include messages for that element
        if message_element_uuid != element_uuid:
            return

    # If not filtering, only include messages without element_uuid (global messages)
    elif message_element_uuid is not None:
        return

    # Add message with ID
    message_with_id = message_data.copy()
    message_with_id["id"] = message_id
    active_messages.append(message_with_id)


def dismiss_sticky_message(member: Member, message_id: str) -> bool:
    """Dismiss a sticky message for a member.

    Args:
        member: Member instance
        message_id: ID of the message to dismiss

    Returns:
        bool: True if message was found and dismissed, False otherwise

    """
    # Get sticky messages from config
    sticky_messages = _get_sticky(member)
    if not isinstance(sticky_messages, dict):
        return False

    # Check if message exists
    if message_id not in sticky_messages:
        return False

    # Mark as dismissed
    sticky_messages[message_id]["dismissed"] = True

    # Save back to config
    save_single_config(member, "sticky", sticky_messages)

    return True
