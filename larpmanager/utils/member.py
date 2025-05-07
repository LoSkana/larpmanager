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

from django.core.cache import cache

from larpmanager.models.member import Badge, Membership


def count_differences(s1, s2):
    # If the lengths of the strings are different, they can't be almost identical
    if len(s1) != len(s2):
        return False

    # Count the number of differences between the two strings
    differences = 0
    for c1, c2 in zip(s1, s2):
        if c1 != c2:
            differences += 1

    return differences


def almost_equal(s1, s2):
    # Ensure that one string has exactly one more character than the other
    if abs(len(s1) - len(s2)) != 1:
        return False

    # Identify which string is longer
    if len(s1) > len(s2):
        longer, shorter = s1, s2
    else:
        longer, shorter = s2, s1

    # Try to find the single extra character
    for i in range(len(longer)):
        # Create a new string by removing the character at index i
        modified = longer[:i] + longer[i + 1 :]
        if modified == shorter:
            return True

    return False


def leaderboard_key(a_id):
    return f"leaderboard_{a_id}"


def update_leaderboard(a_id):
    res = []
    for mb in Membership.objects.filter(assoc_id=a_id):
        el = {
            "id": mb.member_id,
            "count": mb.member.badges.filter(assoc_id=a_id).count(),
            "created": mb.created,
            "name": mb.member.display_member(),
        }
        if mb.member.profile:
            el["profile"] = mb.member.profile_thumb.url
        if el["count"] > 0:
            res.append(el)
    res = sorted(res, key=lambda x: (x["count"], x["created"]), reverse=True)
    cache.set(leaderboard_key(a_id), res)
    return res


def get_leaderboard(a_id):
    res = cache.get(leaderboard_key(a_id))
    if not res:
        res = update_leaderboard(a_id)
    return res


def assign_badge(member, cod):
    try:
        b = Badge.objects.get(cod=cod)
        b.members.add(member)
    except Exception as e:
        print(e)
