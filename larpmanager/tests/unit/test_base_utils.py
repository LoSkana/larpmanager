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
#   commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary

from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.http import HttpRequest

from larpmanager.models.association import Association
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.utils.base import (
    check_assoc_permission,
    def_user_ctx,
    get_index_assoc_permissions,
    get_index_permissions,
    is_allowed_managed,
    is_shuttle,
    update_payment_details,
)
from larpmanager.utils.exceptions import FeatureError, MembershipError, PermissionError


@pytest.mark.django_db
class TestUserContextGeneration:
    """Test user context generation functions"""

    def test_def_user_ctx_home_page_redirect(self):
        """Test home page redirect when association ID is 0"""
        request = Mock()
        request.assoc = {"id": 0}

        # Test with no user
        with pytest.raises(MembershipError):
            def_user_ctx(request)

        # Test with user but no member
        request.user = Mock()
        with pytest.raises(MembershipError):
            def_user_ctx(request)

        # Test with user and member
        request.user.member = Mock()
        request.user.member.memberships.all.return_value = []

        with pytest.raises(MembershipError):
            def_user_ctx(request)

    @patch("larpmanager.utils.base.get_user_membership")
    @patch("larpmanager.utils.base.get_index_assoc_permissions")
    @patch("larpmanager.utils.base.cache_event_links")
    def test_def_user_ctx_with_valid_association(self, mock_cache_links, mock_get_permissions, mock_get_membership):
        """Test context generation with valid association"""
        # Setup mocks
        mock_cache_links.return_value = {"features": ["payment"], "token_name": "", "credit_name": ""}
        mock_membership = Mock()
        mock_get_membership.return_value = mock_membership

        # Create request
        request = Mock()
        request.assoc = {"id": 1, "name": "Test Association", "slug": "test"}
        request.user.member = Mock()
        request.user.member.get_config.return_value = False
        request.user.is_staff = True
        request.resolver_match = Mock()
        request.resolver_match.func.__name__ = "test_view"

        # Mock Association.objects.get
        with patch("larpmanager.utils.base.Association.objects.get") as mock_get_assoc:
            mock_assoc = Mock()
            mock_assoc.get_config.return_value = False
            mock_get_assoc.return_value = mock_assoc

            result = def_user_ctx(request)

            assert result["a_id"] == 1
            assert result["name"] == "Test Association"
            assert result["slug"] == "test"
            assert result["member"] == request.user.member
            assert result["membership"] == mock_membership
            assert result["is_staff"] is True
            assert result["interface_collapse_sidebar"] is False
            assert result["request_func_name"] == "test_view"

    @patch("larpmanager.utils.base.cache_event_links")
    def test_def_user_ctx_token_credit_names(self, mock_cache_links):
        """Test token/credit name setting in context"""
        mock_cache_links.return_value = {"features": ["token_credit"], "token_name": "", "credit_name": ""}

        request = Mock()
        request.assoc = {"id": 1}
        request.user.member = Mock()
        request.user.member.get_config.return_value = False
        request.user.is_staff = False
        request.resolver_match = None

        with patch("larpmanager.utils.base.Association.objects.get") as mock_get_assoc:
            mock_assoc = Mock()
            mock_assoc.get_config.return_value = False
            mock_get_assoc.return_value = mock_assoc

            with patch("larpmanager.utils.base.get_user_membership"):
                with patch("larpmanager.utils.base.get_index_assoc_permissions"):
                    result = def_user_ctx(request)

                    assert result["token_name"] == "Tokens"
                    assert result["credit_name"] == "Credits"

    def test_is_shuttle_with_no_member(self):
        """Test shuttle check when user has no member"""
        request = Mock()
        request.user = Mock()
        delattr(request.user, "member")

        assert is_shuttle(request) is False

    def test_is_shuttle_with_member_in_shuttle_list(self):
        """Test shuttle check with member in shuttle list"""
        request = Mock()
        request.user.member.id = 123
        request.assoc = {"shuttle": [123, 456, 789]}

        assert is_shuttle(request) is True

    def test_is_shuttle_with_member_not_in_shuttle_list(self):
        """Test shuttle check with member not in shuttle list"""
        request = Mock()
        request.user.member.id = 999
        request.assoc = {"shuttle": [123, 456, 789]}

        assert is_shuttle(request) is False

    def test_is_shuttle_no_shuttle_key(self):
        """Test shuttle check when shuttle key doesn't exist"""
        request = Mock()
        request.user.member.id = 123
        request.assoc = {}

        assert is_shuttle(request) is False

    @patch("larpmanager.utils.base.get_payment_details")
    def test_update_payment_details(self, mock_get_payment_details):
        """Test payment details update"""
        mock_payment_details = {"payment_methods": ["paypal", "stripe"], "currency": "EUR"}
        mock_get_payment_details.return_value = mock_payment_details

        request = Mock()
        request.assoc = {"id": 1}

        ctx = {}

        with patch("larpmanager.utils.base.Association.objects.get") as mock_get_assoc:
            mock_assoc = Mock()
            mock_get_assoc.return_value = mock_assoc

            update_payment_details(request, ctx)

            assert ctx["payment_methods"] == ["paypal", "stripe"]
            assert ctx["currency"] == "EUR"
            mock_get_payment_details.assert_called_once_with(mock_assoc)


@pytest.mark.django_db
class TestPermissionChecking:
    """Test permission checking functions"""

    @patch("larpmanager.utils.base.def_user_ctx")
    @patch("larpmanager.utils.base.has_assoc_permission")
    def test_check_assoc_permission_denied(self, mock_has_permission, mock_def_user_ctx):
        """Test permission check when permission is denied"""
        mock_def_user_ctx.return_value = {}
        mock_has_permission.return_value = False

        request = Mock()

        with pytest.raises(PermissionError):
            check_assoc_permission(request, "test_permission")

    @patch("larpmanager.utils.base.def_user_ctx")
    @patch("larpmanager.utils.base.has_assoc_permission")
    @patch("larpmanager.utils.base.get_assoc_permission_feature")
    def test_check_assoc_permission_feature_not_available(
        self, mock_get_feature, mock_has_permission, mock_def_user_ctx
    ):
        """Test permission check when required feature is not available"""
        mock_def_user_ctx.return_value = {}
        mock_has_permission.return_value = True
        mock_get_feature.return_value = ("required_feature", "tutorial", "config")

        request = Mock()
        request.assoc = {"features": ["other_feature"]}
        request.path = "/test/path"

        with pytest.raises(FeatureError) as exc_info:
            check_assoc_permission(request, "test_permission")

        assert exc_info.value.path == "/test/path"
        assert exc_info.value.feature == "required_feature"

    @patch("larpmanager.utils.base.def_user_ctx")
    @patch("larpmanager.utils.base.has_assoc_permission")
    @patch("larpmanager.utils.base.get_assoc_permission_feature")
    @patch("larpmanager.utils.base.get_index_assoc_permissions")
    def test_check_assoc_permission_success(
        self, mock_get_index_permissions, mock_get_feature, mock_has_permission, mock_def_user_ctx
    ):
        """Test successful permission check"""
        mock_def_user_ctx.return_value = {}
        mock_has_permission.return_value = True
        mock_get_feature.return_value = ("def", "tutorial_url", None)

        request = Mock()
        request.assoc = {"features": ["payment"], "id": 1}
        request.session = {"is_sidebar_open": True}

        result = check_assoc_permission(request, "test_permission")

        assert result["manage"] == 1
        assert result["is_sidebar_open"] is True
        assert result["exe_page"] == 1
        assert result["tutorial"] == "tutorial_url"

    @patch("larpmanager.utils.base.get_assoc_roles")
    def test_get_index_assoc_permissions_no_permissions(self, mock_get_roles):
        """Test index permissions when user has no permissions"""
        mock_get_roles.return_value = (False, [], [])

        ctx = {}
        request = Mock()
        request.session = {"is_sidebar_open": False}

        with pytest.raises(PermissionError):
            get_index_assoc_permissions(ctx, request, 1, check=True)

        # Test with check=False
        get_index_assoc_permissions(ctx, request, 1, check=False)
        # Should return without setting any permissions

    @patch("larpmanager.utils.base.get_assoc_roles")
    @patch("larpmanager.utils.base.get_assoc_features")
    @patch("larpmanager.utils.base.get_index_permissions")
    def test_get_index_assoc_permissions_success(self, mock_get_index_permissions, mock_get_features, mock_get_roles):
        """Test successful index permissions retrieval"""
        mock_get_roles.return_value = (True, ["perm1", "perm2"], ["Admin"])
        mock_get_features.return_value = ["feature1", "feature2"]
        mock_get_index_permissions.return_value = {"permissions": "data"}

        ctx = {}
        request = Mock()
        request.session = {"is_sidebar_open": True}

        get_index_assoc_permissions(ctx, request, 1)

        assert ctx["role_names"] == ["Admin"]
        assert ctx["assoc_pms"] == {"permissions": "data"}
        assert ctx["is_sidebar_open"] is True

    @patch("larpmanager.utils.base.get_cache_index_permission")
    @patch("larpmanager.utils.base.is_allowed_managed")
    def test_get_index_permissions_filtering(self, mock_is_allowed_managed, mock_get_cache_permission):
        """Test permission filtering in get_index_permissions"""
        mock_permission_data = [
            {
                "slug": "perm1",
                "hidden": False,
                "feature__placeholder": False,
                "feature__slug": "feature1",
                "module__name": "Test Module",
                "module__icon": "icon1",
            },
            {
                "slug": "perm2",
                "hidden": True,  # Should be filtered out
                "feature__placeholder": False,
                "feature__slug": "feature2",
                "module__name": "Hidden Module",
                "module__icon": "icon2",
            },
            {
                "slug": "perm3",
                "hidden": False,
                "feature__placeholder": False,
                "feature__slug": "missing_feature",  # Feature not available
                "module__name": "Missing Feature Module",
                "module__icon": "icon3",
            },
        ]

        mock_get_cache_permission.return_value = mock_permission_data
        mock_is_allowed_managed.return_value = True

        ctx = {}
        features = ["feature1", "feature2"]
        has_default = True
        permissions = ["perm1", "perm3"]

        result = get_index_permissions(ctx, features, has_default, permissions, "assoc")

        # Should only include perm1 (not hidden, feature available, user has permission)
        assert len(result) == 1
        module_key = ("Test Module", "icon1")
        assert module_key in result
        assert len(result[module_key]) == 1
        assert result[module_key][0]["slug"] == "perm1"

    def test_is_allowed_managed_staff_user(self):
        """Test managed permission check for staff user"""
        ctx = {"skin_managed": True, "is_staff": True}
        ar = {"feature__placeholder": True, "slug": "restricted_permission"}

        # Staff should always be allowed
        assert is_allowed_managed(ar, ctx) is True

    def test_is_allowed_managed_non_staff_restricted(self):
        """Test managed permission check for non-staff user with restricted permission"""
        ctx = {"skin_managed": True, "is_staff": False}
        ar = {"feature__placeholder": True, "slug": "restricted_permission"}

        with patch("larpmanager.utils.base.get_allowed_managed") as mock_get_allowed:
            mock_get_allowed.return_value = ["allowed_permission"]

            # Non-staff user should not be allowed for restricted permission
            assert is_allowed_managed(ar, ctx) is False

    def test_is_allowed_managed_non_staff_allowed(self):
        """Test managed permission check for non-staff user with allowed permission"""
        ctx = {"skin_managed": True, "is_staff": False}
        ar = {"feature__placeholder": True, "slug": "allowed_permission"}

        with patch("larpmanager.utils.base.get_allowed_managed") as mock_get_allowed:
            mock_get_allowed.return_value = ["allowed_permission"]

            # Non-staff user should be allowed for allowed permission
            assert is_allowed_managed(ar, ctx) is True

    def test_is_allowed_managed_not_managed_skin(self):
        """Test managed permission check when skin is not managed"""
        ctx = {"skin_managed": False, "is_staff": False}
        ar = {"feature__placeholder": True, "slug": "any_permission"}

        # Should always be allowed when skin is not managed
        assert is_allowed_managed(ar, ctx) is True

    def test_is_allowed_managed_non_placeholder_feature(self):
        """Test managed permission check for non-placeholder feature"""
        ctx = {"skin_managed": True, "is_staff": False}
        ar = {"feature__placeholder": False, "slug": "any_permission"}

        # Should always be allowed for non-placeholder features
        assert is_allowed_managed(ar, ctx) is True


# Fixtures
@pytest.fixture
def association():
    """Create test association"""
    return Association.objects.create(name="Test Association", slug="test")


@pytest.fixture
def member():
    """Create test member"""
    user = User.objects.create_user(username="testmember", email="test@test.com")
    return Member.objects.create(user=user, name="Test", surname="Member")


@pytest.fixture
def membership(member, association):
    """Create test membership"""
    return Membership.objects.create(member=member, assoc=association, status=MembershipStatus.ACCEPTED)


@pytest.fixture
def mock_request():
    """Create mock request object"""
    request = Mock(spec=HttpRequest)
    request.user = Mock()
    request.session = {}
    return request
