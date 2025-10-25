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
from datetime import date

from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max
from django.http import Http404, HttpRequest

from larpmanager.models.member import Badge, Member, Membership, MembershipStatus
from larpmanager.models.miscellanea import Email


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
    for first_char, second_char in zip(first_string, second_string):
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


def leaderboard_key(association_id):
    return f"leaderboard_{association_id}"


def update_leaderboard(a_id: int) -> list[dict]:
    """Generate leaderboard data for members with badges.

    Retrieves all memberships for a given association and creates a leaderboard
    based on badge counts. Only includes members with at least one badge.
    Results are sorted by badge count (descending) and creation date (descending).

    Args:
        a_id: Association ID to generate leaderboard for

    Returns:
        List of member dictionaries containing:
            - id: Member ID
            - count: Number of badges for this association
            - created: Membership creation date
            - name: Member display name
            - profile: Profile thumbnail URL (if available)
    """
    res = []

    # Iterate through all memberships for the association
    for mb in Membership.objects.filter(assoc_id=a_id):
        # Build member data with badge count and basic info
        el = {
            "id": mb.member_id,
            "count": mb.member.badges.filter(assoc_id=a_id).count(),
            "created": mb.created,
            "name": mb.member.display_member(),
        }

        # Add profile thumbnail if available
        if mb.member.profile:
            el["profile"] = mb.member.profile_thumb.url

        # Only include members with at least one badge
        if el["count"] > 0:
            res.append(el)

    # Sort by badge count (desc) then by creation date (desc)
    res = sorted(res, key=lambda x: (x["count"], x["created"]), reverse=True)

    # Cache the results for one day
    cache.set(leaderboard_key(a_id), res, timeout=conf_settings.CACHE_TIMEOUT_1_DAY)
    return res


def get_leaderboard(a_id: int) -> dict:
    """Get leaderboard data for an association, using cache when available."""
    # Try to retrieve cached leaderboard data
    res = cache.get(leaderboard_key(a_id))

    # If not cached, compute and cache the leaderboard
    if not res:
        res = update_leaderboard(a_id)
    return res


def assign_badge(member, badge_code):
    try:
        badge = Badge.objects.get(cod=badge_code)
        badge.members.add(member)
    except Exception as e:
        print(e)


def get_mail(request: HttpRequest, context: dict, email_id: int) -> Email:
    """Retrieve an email object with proper authorization checks.

    Args:
        request: HTTP request object containing association information
        context: Context dictionary that may contain run information
        email_id: Primary key of the email to retrieve

    Returns:
        Email: The requested email object if authorized

    Raises:
        Http404: If email not found, belongs to different association,
                or belongs to different run when run context is provided
    """
    # Attempt to retrieve the email by primary key
    try:
        email = Email.objects.get(pk=email_id)
    except ObjectDoesNotExist as err:
        raise Http404("not found") from err

    # Verify email belongs to the requesting association
    if email.assoc_id != request.assoc["id"]:
        raise Http404("not your assoc")

    # Check run-specific authorization if run context is provided
    run = context.get("run")
    if run and email.run_id != run.id:
        raise Http404("not your run")

    return email


def create_member_profile_for_user(user: User, is_newly_created: bool) -> None:
    """Create member profile and sync email when user is saved.

    This function handles the creation of a Member profile for newly created users
    and ensures email synchronization between User and Member models.

    Args:
        user: User instance that was saved
        is_newly_created: Whether this is a new user (True for new users, False for updates)

    Returns:
        None
    """
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
            status, card_number, date, and assoc attributes.

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
            n = Membership.objects.filter(assoc=membership.assoc).aggregate(Max("card_number"))["card_number__max"]
            if not n:
                n = 0
            membership.card_number = n + 1

        # Set current date if not already set
        if not membership.date:
            membership.date = date.today()

    # Handle EMPTY status: clear card number and date
    if membership.status == MembershipStatus.EMPTY:
        # Remove card number for empty memberships
        if membership.card_number:
            membership.card_number = None

        # Remove date for empty memberships
        if membership.date:
            membership.date = None
