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

import logging
from typing import TYPE_CHECKING

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.db.models import Max
from django.http import Http404
from django.utils import timezone

from larpmanager.models.member import Badge, Member, Membership, MembershipStatus, NotificationQueue
from larpmanager.models.miscellanea import EmailRecipient
from larpmanager.utils.core.common import get_object_uuid

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from larpmanager.models.association import Association
    from larpmanager.models.event import Run


logger = logging.getLogger(__name__)


def count_differences(first_string: str, second_string: str) -> int | bool:
    """Count the number of character differences between two strings.

    Args:
        first_string: First string to compare
        second_string: Second string to compare

    Returns:
        False if strings have different lengths, otherwise the number of
        character differences between the strings

    Example:
        >>> count_differences("hello", "hallo")
        1
        >>> count_differences("abc", "abcd")
        False

    """
    # If the lengths of the strings are different, they can't be almost identical
    if len(first_string) != len(second_string):
        return False

    # Count the number of differences between the two strings
    differences = 0
    for first_char, second_char in zip(first_string, second_string, strict=False):
        if first_char != second_char:
            differences += 1

    return differences


def almost_equal(s1: str, s2: str) -> bool:
    """Check if two strings are almost equal (differ by exactly one character insertion).

    Two strings are considered "almost equal" if one can be transformed into the other
    by inserting exactly one character at any position.

    Args:
        s1: First string to compare.
        s2: Second string to compare.

    Returns:
        True if strings differ by exactly one character insertion, False otherwise.

    Examples:
        >>> almost_equal("abc", "abcd")
        True
        >>> almost_equal("hello", "helo")
        True
        >>> almost_equal("test", "best")
        False

    """
    # Ensure that one string has exactly one more character than the other
    if abs(len(s1) - len(s2)) != 1:
        return False

    # Identify which string is longer and which is shorter
    if len(s1) > len(s2):
        longer_string, shorter_string = s1, s2
    else:
        longer_string, shorter_string = s2, s1

    # Try to find the single extra character by removing each character from longer string
    for char_index in range(len(longer_string)):
        # Create a new string by removing the character at index char_index
        string_with_char_removed = longer_string[:char_index] + longer_string[char_index + 1 :]
        # Check if the modified string matches the shorter string
        if string_with_char_removed == shorter_string:
            return True

    # No single character removal made the strings equal
    return False


def leaderboard_key(association_id: int) -> str:
    """Return cache key for association leaderboard."""
    return f"leaderboard_{association_id}"


def update_leaderboard(association_id: int) -> list[dict]:
    """Generate leaderboard data for members with badges.

    Retrieves all memberships for a given association and creates a leaderboard
    based on badge counts. Only includes members with at least one badge.
    Results are sorted by badge count (descending) and creation date (descending).

    Args:
        association_id: Association ID to generate leaderboard for

    Returns:
        List of member dictionaries containing:
            - id: Member ID
            - count: Number of badges for this association
            - created: Membership creation date
            - name: Member display name
            - profile: Profile thumbnail URL (if available)

    """
    leaderboard_entries = []

    # Iterate through all memberships for the association
    for membership in Membership.objects.filter(association_id=association_id):
        # Build member data with badge count and basic info
        member_entry = {
            "uuid": membership.member.uuid,
            "count": membership.member.badges.filter(association_id=association_id).count(),
            "created": membership.created,
            "name": membership.member.display_member(),
        }

        # Add profile thumbnail if available
        if membership.member.profile:
            member_entry["profile"] = membership.member.profile_thumb.url

        # Only include members with at least one badge
        if member_entry["count"] > 0:
            leaderboard_entries.append(member_entry)

    # Sort by badge count (desc) then by creation date (desc)
    leaderboard_entries = sorted(leaderboard_entries, key=lambda x: (x["count"], x["created"]), reverse=True)

    # Cache the results for one day
    cache.set(leaderboard_key(association_id), leaderboard_entries, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return leaderboard_entries


def get_leaderboard(association_id: int) -> dict:
    """Get leaderboard data for an association, using cache when available."""
    # Try to retrieve cached leaderboard data
    cached_leaderboard = cache.get(leaderboard_key(association_id))

    # If not cached, compute and cache the leaderboard
    if not cached_leaderboard:
        cached_leaderboard = update_leaderboard(association_id)
    return cached_leaderboard


def assign_badge(member: Member, badge_code: str) -> None:
    """Assign a badge to a member by badge code."""
    try:
        badge = Badge.objects.get(cod=badge_code)
        badge.members.add(member)
    except Exception:
        logger.exception("Failed to assign badge %s to member %s", badge_code, member)


def get_mail(context: dict, email_uuid: str) -> EmailRecipient:
    """Retrieve an email recipient object with proper authorization checks.

    Args:
        context: Context dictionary that may contain run information
        email_uuid: UUID of the email recipient to retrieve

    Returns:
        EmailRecipient: The requested email recipient object if authorized

    Raises:
        Http404: If email not found, belongs to different association,
                or belongs to different run when run context is provided

    """
    # Attempt to retrieve the email recipient by UUID
    email_recipient = get_object_uuid(EmailRecipient, email_uuid)

    # Verify email belongs to the requesting association
    if email_recipient.email_content.association_id != context["association_id"]:
        msg = "not your association"
        raise Http404(msg)

    # Check run-specific authorization if run context is provided
    run = context.get("run")
    if run and email_recipient.email_content.run_id != run.id:
        msg = "not your run"
        raise Http404(msg)

    return email_recipient


def create_member_profile_for_user(user: User, *, is_newly_created: bool) -> None:
    """Create member profile and sync email when user is saved."""
    # Create new Member profile for newly registered users
    if is_newly_created:
        Member.objects.create(user=user)

    # Sync email address from User model to Member profile
    user.member.email = user.email
    user.member.save()


def process_membership_status_updates(membership: Membership) -> None:
    """Handle membership status changes and card numbering.

    Updates membership card numbers and dates based on status changes.
    For ACCEPTED memberships, assigns the next available card number and
    sets the current date if not already set. For EMPTY memberships,
    clears both card number and date fields.

    Args:
        membership: The Membership instance being processed. Must have
            status, card_number, date, and association attributes.

    Returns:
        None: Modifies the membership instance in-place.

    Note:
        This function should be called before saving the membership
        to ensure proper field updates based on status.

    """
    # Handle ACCEPTED status: assign card number and date
    if membership.status == MembershipStatus.ACCEPTED:
        # Assign next available card number if not already set
        if not membership.card_number:
            max_card_number = Membership.objects.filter(association=membership.association).aggregate(
                Max("card_number"),
            )["card_number__max"]
            if not max_card_number:
                max_card_number = 0
            membership.card_number = max_card_number + 1

        # Set current date if not already set
        if not membership.date:
            membership.date = timezone.now().date()

    # Handle EMPTY status: clear card number and date
    if membership.status == MembershipStatus.EMPTY:
        # Remove card number for empty memberships
        if membership.card_number:
            membership.card_number = None

        # Remove date for empty memberships
        if membership.date:
            membership.date = None


def get_member_uuid(slug: str) -> Member:
    """Retrieves a member by their uuid."""
    return get_object_uuid(Member, slug)


def queue_organizer_notification(
    run: Run,
    member: Member,
    notification_type: str,
    object_id: int | None = None,
) -> NotificationQueue:
    """Add notification to queue instead of sending immediately."""
    return NotificationQueue.objects.create(
        run=run, member=member, notification_type=notification_type, object_id=object_id
    )


def queue_executive_notification(
    association: Association,
    member: Member | None,
    notification_type: str,
    object_id: int | None = None,
) -> NotificationQueue:
    """Add executive notification to queue instead of sending immediately."""
    return NotificationQueue.objects.create(
        association=association, member=member, notification_type=notification_type, object_id=object_id
    )
