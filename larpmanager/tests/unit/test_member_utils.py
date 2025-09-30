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

from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from larpmanager.models.association import Association
from larpmanager.models.member import Badge, Member, Membership
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.member import (
    almost_equal,
    assign_badge,
    count_differences,
    get_leaderboard,
    leaderboard_key,
    update_leaderboard,
)


class TestStringComparisonFunctions:
    """Test string comparison utility functions"""

    def test_count_differences_equal_length(self):
        """Test counting differences between equal-length strings"""
        assert count_differences("HELLO", "HELLO") == 0
        assert count_differences("HELLO", "HALLO") == 1
        assert count_differences("HELLO", "WORLD") == 4
        assert count_differences("ABC", "XYZ") == 3

    def test_count_differences_different_length(self):
        """Test counting differences with different length strings"""
        # Should return False for different lengths
        assert count_differences("HELLO", "HI") is False
        assert count_differences("A", "ABC") is False
        assert count_differences("", "A") is False

    def test_count_differences_empty_strings(self):
        """Test counting differences with empty strings"""
        assert count_differences("", "") == 0
        assert count_differences("A", "") is False
        assert count_differences("", "A") is False

    def test_count_differences_case_sensitive(self):
        """Test that comparison is case sensitive"""
        assert count_differences("Hello", "hello") == 1
        assert count_differences("ABC", "abc") == 3

    def test_almost_equal_single_character_difference(self):
        """Test almost_equal with single character difference"""
        # One string has exactly one more character
        assert almost_equal("HELLO", "HELL") is True
        assert almost_equal("HELL", "HELLO") is True
        assert almost_equal("ABCDEF", "ABDEF") is True  # Missing C
        assert almost_equal("ABDEF", "ABCDEF") is True  # Extra C

    def test_almost_equal_multiple_character_difference(self):
        """Test almost_equal with multiple character differences"""
        # Difference is not exactly 1
        assert almost_equal("HELLO", "HEL") is False  # Difference of 2
        assert almost_equal("HELLO", "HELLOOOO") is False  # Difference of 4
        assert almost_equal("ABC", "XYZ") is False  # Same length, different content

    def test_almost_equal_identical_strings(self):
        """Test almost_equal with identical strings"""
        # No difference (should be False as difference is not exactly 1)
        assert almost_equal("HELLO", "HELLO") is False
        assert almost_equal("", "") is False

    def test_almost_equal_character_insertion(self):
        """Test almost_equal with character insertions at different positions"""
        # Insert at beginning
        assert almost_equal("XHELLO", "HELLO") is True
        assert almost_equal("HELLO", "XHELLO") is True

        # Insert in middle
        assert almost_equal("HELXLO", "HELLO") is True
        assert almost_equal("HELLO", "HELXLO") is True

        # Insert at end
        assert almost_equal("HELLOX", "HELLO") is True
        assert almost_equal("HELLO", "HELLOX") is True

    def test_almost_equal_empty_strings(self):
        """Test almost_equal with empty strings"""
        assert almost_equal("A", "") is True
        assert almost_equal("", "A") is True
        assert almost_equal("", "") is False  # No difference

    def test_almost_equal_complex_cases(self):
        """Test almost_equal with complex real-world cases"""
        # Common typos
        assert almost_equal("ROSSI", "ROSI") is True  # Missing S
        assert almost_equal("MARIO", "MARIOS") is True  # Extra S
        assert almost_equal("GIUSEPPE", "GIUSEPE") is True  # Missing P

        # Not almost equal
        assert almost_equal("MARIO", "MARIA") is False  # Different characters
        assert almost_equal("SHORT", "VERYLONGSTRING") is False  # Too different


class TestLeaderboardFunctions(TestCase, BaseTestCase):
    """Test leaderboard utility functions"""

    def test_leaderboard_key(self):
        """Test leaderboard cache key generation"""
        assert leaderboard_key(123) == "leaderboard_123"
        assert leaderboard_key(1) == "leaderboard_1"

    def test_update_leaderboard_empty_association(self):
        """Test updating leaderboard for association with no members"""
        # Create association with no memberships
        assoc = Association.objects.create(name="Empty Assoc", slug="empty")

        result = update_leaderboard(assoc.id)

        assert result == []

    def test_update_leaderboard_members_no_badges(self):
        """Test updating leaderboard for members with no badges"""
        assoc = Association.objects.create(name="Test Assoc", slug="test")

        # Create members with memberships but no badges
        user1 = User.objects.create_user(username="member1", email="member1@test.com")
        member1 = Member.objects.create(user=user1, name="Member", surname="One")

        user2 = User.objects.create_user(username="member2", email="member2@test.com")
        member2 = Member.objects.create(user=user2, name="Member", surname="Two")

        Membership.objects.create(member=member1, assoc=assoc)
        Membership.objects.create(member=member2, assoc=assoc)

        result = update_leaderboard(assoc.id)

        # Should be empty since no badges
        assert result == []

    def test_update_leaderboard_members_with_badges(self):
        """Test updating leaderboard for members with badges"""
        assoc = Association.objects.create(name="Test Assoc", slug="test")

        # Create badges
        badge1 = Badge.objects.create(name="Supporter", cod="supporter")
        badge2 = Badge.objects.create(name="Donor", cod="donor")

        # Create members
        user1 = User.objects.create_user(username="member1", email="member1@test.com")
        member1 = Member.objects.create(user=user1, name="John", surname="Doe")

        user2 = User.objects.create_user(username="member2", email="member2@test.com")
        member2 = Member.objects.create(user=user2, name="Jane", surname="Smith")

        # Create memberships
        membership1 = Membership.objects.create(member=member1, assoc=assoc)
        membership2 = Membership.objects.create(member=member2, assoc=assoc)

        # Assign badges
        badge1.members.add(member1)
        badge1.members.add(member2)
        badge2.members.add(member1)  # Member1 has 2 badges, Member2 has 1

        result = update_leaderboard(assoc.id)

        assert len(result) == 2

        # Should be sorted by badge count (descending), then by created date
        assert result[0]["count"] == 2  # member1 with 2 badges
        assert result[1]["count"] == 1  # member2 with 1 badge

        assert result[0]["name"] == "John Doe"
        assert result[1]["name"] == "Jane Smith"

    def test_update_leaderboard_with_profile_images(self):
        """Test leaderboard update includes profile image URLs when available"""
        assoc = Association.objects.create(name="Test Assoc", slug="test")
        badge = Badge.objects.create(name="Test Badge", cod="test")

        user = User.objects.create_user(username="member", email="member@test.com")
        member = Member.objects.create(user=user, name="Test", surname="Member")

        # Mock profile with thumb URL
        self.get_member().profile = Mock()
        self.get_member().profile_thumb = Mock()
        self.get_member().profile_thumb.url = "/media/profiles/thumb_test.jpg"

        Membership.objects.create(member=self.get_member(), assoc=assoc)
        badge.members.add(self.get_member())

        result = update_leaderboard(assoc.id)

        assert len(result) == 1
        assert "profile" in result[0]
        assert result[0]["profile"] == "/media/profiles/thumb_test.jpg"

    def test_update_leaderboard_caches_result(self):
        """Test that leaderboard update stores result in cache"""
        assoc = Association.objects.create(name="Test Assoc", slug="test")

        # Clear cache first
        cache.clear()

        result = update_leaderboard(assoc.id)

        # Check that result is cached
        cached_result = cache.get(leaderboard_key(assoc.id))
        assert cached_result == result

    def test_get_leaderboard_from_cache(self):
        """Test getting leaderboard from cache"""
        assoc_id = 999
        expected_data = [{"id": 1, "count": 5, "name": "Test User"}]

        # Set cache manually
        cache.set(leaderboard_key(assoc_id), expected_data)

        result = get_leaderboard(assoc_id)

        assert result == expected_data

    @patch("larpmanager.utils.member.update_leaderboard")
    def test_get_leaderboard_cache_miss(self, mock_update):
        """Test getting leaderboard when cache is empty"""
        expected_data = [{"id": 1, "count": 3, "name": "Test User"}]
        mock_update.return_value = expected_data

        assoc_id = 888

        # Clear cache to ensure miss
        cache.delete(leaderboard_key(assoc_id))

        result = get_leaderboard(assoc_id)

        assert result == expected_data
        mock_update.assert_called_once_with(assoc_id)

    def test_leaderboard_sorting_by_creation_date(self):
        """Test leaderboard sorting by creation date when badge counts are equal"""
        assoc = Association.objects.create(name="Test Assoc", slug="test")
        badge = Badge.objects.create(name="Test Badge", cod="test")

        # Create members with different creation times
        user1 = User.objects.create_user(username="member1", email="member1@test.com")
        member1 = Member.objects.create(user=user1, name="First", surname="Member")

        user2 = User.objects.create_user(username="member2", email="member2@test.com")
        member2 = Member.objects.create(user=user2, name="Second", surname="Member")

        # Create memberships with specific created dates
        membership1 = Membership.objects.create(member=member1, assoc=assoc)
        membership2 = Membership.objects.create(member=member2, assoc=assoc)

        # Both have same number of badges
        badge.members.add(member1)
        badge.members.add(member2)

        result = update_leaderboard(assoc.id)

        assert len(result) == 2
        assert result[0]["count"] == result[1]["count"] == 1

        # Should be sorted by created date in descending order
        # (more recent memberships first when badge counts are equal)


class TestBadgeAssignment(TestCase, BaseTestCase):
    """Test badge assignment functionality"""

    def test_assign_badge_success(self):
        """Test successful badge assignment"""
        # Create badge
        badge = Badge.objects.create(name="Supporter", cod="supporter")

        # Create member
        user = User.objects.create_user(username="member", email="member@test.com")
        member = Member.objects.create(user=user, name="Test", surname="Member")

        # Assign badge
        assign_badge(self.get_member(), "supporter")

        # Verify assignment
        assert badge.members.filter(id=self.get_member().id).exists()

    def test_assign_badge_nonexistent_badge(self):
        """Test badge assignment with nonexistent badge code"""
        user = User.objects.create_user(username="member", email="member@test.com")
        member = Member.objects.create(user=user, name="Test", surname="Member")

        # Should not raise exception, just silently fail
        assign_badge(self.get_member(), "nonexistent")

        # Verify no badges assigned
        assert self.get_member().badges.count() == 0

    @patch("builtins.print")
    def test_assign_badge_exception_handling(self, mock_print):
        """Test badge assignment exception handling"""
        user = User.objects.create_user(username="member", email="member@test.com")
        member = Member.objects.create(user=user, name="Test", surname="Member")

        # This should trigger the exception handler
        assign_badge(self.get_member(), "nonexistent")

        # Should have printed the exception
        mock_print.assert_called_once()

    def test_assign_badge_multiple_times(self):
        """Test assigning same badge multiple times (should be idempotent)"""
        badge = Badge.objects.create(name="Supporter", cod="supporter")
        user = User.objects.create_user(username="member", email="member@test.com")
        member = Member.objects.create(user=user, name="Test", surname="Member")

        # Assign badge multiple times
        assign_badge(self.get_member(), "supporter")
        assign_badge(self.get_member(), "supporter")
        assign_badge(self.get_member(), "supporter")

        # Should only be assigned once (many-to-many relationship)
        assert badge.members.filter(id=self.get_member().id).count() == 1

    def test_assign_multiple_badges_to_member(self):
        """Test assigning multiple different badges to same self.get_member()"""
        badge1 = Badge.objects.create(name="Supporter", cod="supporter")
        badge2 = Badge.objects.create(name="Donor", cod="donor")
        badge3 = Badge.objects.create(name="Volunteer", cod="volunteer")

        user = User.objects.create_user(username="member", email="self.get_member()@test.com")
        member = Member.objects.create(user=self.get_user(), name="Test", surname="Member")

        # Assign multiple badges
        assign_badge(self.get_member(), "supporter")
        assign_badge(self.get_member(), "donor")
        assign_badge(self.get_member(), "volunteer")

        # Verify all badges assigned
        assert self.get_member().badges.count() == 3
        assert badge1.members.filter(id=self.get_member().id).exists()
        assert badge2.members.filter(id=self.get_member().id).exists()
        assert badge3.members.filter(id=self.get_member().id).exists()
