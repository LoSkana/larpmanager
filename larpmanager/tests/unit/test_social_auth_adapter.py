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

"""Tests for social authentication adapter functionality.

Tests that the MySocialAccountAdapter correctly links social accounts to existing
users based on email address, even when username differs from email.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.test import RequestFactory

from larpmanager.models.member import Member
from larpmanager.utils.auth.adapter import MyAccountAdapter, MySocialAccountAdapter


@pytest.mark.django_db
class TestSocialAuthAdapter:
    """Test social authentication adapter functionality."""

    def test_pre_social_login_links_by_email_not_username(self) -> None:
        """Test that social login links users by email even when username differs.

        When a user exists with username different from email, django-allauth should
        find and link the social account based on the email address, not the username.

        This test verifies that:
        1. An existing user with username != email can be found by email
        2. The social account is linked to that existing user
        3. No duplicate user is created
        """
        # Create an existing user with username different from email
        existing_username = "john_doe_test_unique"
        existing_email = "john_unique_test@example.com"
        existing_user = User.objects.create_user(
            username=existing_username, email=existing_email, password="testpass123"
        )

        # Check if member was auto-created, otherwise create it
        if not hasattr(existing_user, "member"):
            Member.objects.create(user=existing_user, name="John", surname="Doe")

        # Create a mock social login with the same email
        request = RequestFactory().get("/accounts/google/login/callback/")
        request.user = Mock()

        # Create a new user instance (not saved) that would be created by social login
        social_user = User(
            username=existing_email,  # Social login typically uses email as username
            email=existing_email,
        )

        # Create mock social account
        social_account = Mock(spec=SocialAccount)
        social_account.extra_data = {"email": existing_email, "given_name": "John", "family_name": "Doe"}
        social_account.provider = "google"

        # Create social login object
        sociallogin = SocialLogin(user=social_user, account=social_account)

        # Execute the adapter method
        adapter = MySocialAccountAdapter()
        adapter.pre_social_login(request, sociallogin)

        # Verify that the social login is now connected to the existing user
        assert sociallogin.user.id is not None
        assert sociallogin.user.id == existing_user.id
        assert sociallogin.user.username == existing_username
        assert sociallogin.user.email == existing_email

        # Verify no duplicate user was created
        assert User.objects.filter(email=existing_email).count() == 1

    def test_pre_social_login_creates_new_user_if_no_email_match(self) -> None:
        """Test that social login creates new user when email doesn't exist.

        When no user exists with the social login email, the adapter should
        allow the normal signup process to continue.
        """
        # Create a user with different email
        User.objects.create_user(username="jane_smith_unique", email="jane_unique@example.com", password="testpass123")

        # Create mock social login with different email
        request = RequestFactory().get("/accounts/google/login/callback/")
        request.user = Mock()

        new_email = "newuser_unique@example.com"
        social_user = User(username=new_email, email=new_email)

        social_account = Mock(spec=SocialAccount)
        social_account.extra_data = {"email": new_email, "given_name": "New", "family_name": "User"}

        sociallogin = SocialLogin(user=social_user, account=social_account)

        # Execute the adapter method
        adapter = MySocialAccountAdapter()
        adapter.pre_social_login(request, sociallogin)

        # Verify that no existing user was linked (id should still be None)
        assert sociallogin.user.id is None

        # Verify the email in the social user is correct
        assert sociallogin.user.email == new_email

    def test_update_member_populates_name_fields(self) -> None:
        """Test that update_member fills empty name/surname from social data.

        The adapter should update member name and surname fields when they are
        empty and the social provider supplies given_name and family_name.
        """
        # Create user with empty name/surname in member
        user = User.objects.create_user(
            username="testuser_populate", email="test_populate@example.com", password="testpass123"
        )

        # Check if member was auto-created, otherwise create it
        try:
            member = user.member
            member.name = ""
            member.surname = ""
            member.save()
        except ObjectDoesNotExist:
            member = Member.objects.create(user=user, name="", surname="")

        # Create mock social login with name data
        social_account = Mock(spec=SocialAccount)
        social_account.extra_data = {"email": "test_populate@example.com", "given_name": "Test", "family_name": "User"}

        sociallogin = Mock(spec=SocialLogin)
        sociallogin.account = social_account

        # Execute update_member
        adapter = MySocialAccountAdapter()
        adapter.update_member(user, sociallogin)

        # Verify member was updated
        member.refresh_from_db()
        assert member.name == "Test"
        assert member.surname == "User"

    def test_update_member_preserves_existing_name_fields(self) -> None:
        """Test that update_member doesn't overwrite existing name/surname.

        The adapter should not modify name/surname fields if they already
        contain data, even if the social provider supplies different values.
        """
        # Create user with existing name/surname in member
        user = User.objects.create_user(
            username="testuser_preserve", email="test_preserve@example.com", password="testpass123"
        )
        existing_name = "Existing"
        existing_surname = "Name"

        # Check if member was auto-created, otherwise create it
        try:
            member = user.member
            member.name = existing_name
            member.surname = existing_surname
            member.save()
        except ObjectDoesNotExist:
            member = Member.objects.create(user=user, name=existing_name, surname=existing_surname)

        # Create mock social login with different name data
        social_account = Mock(spec=SocialAccount)
        social_account.extra_data = {
            "email": "test_preserve@example.com",
            "given_name": "Different",
            "family_name": "Person",
        }

        sociallogin = Mock(spec=SocialLogin)
        sociallogin.account = social_account

        # Execute update_member
        adapter = MySocialAccountAdapter()
        adapter.update_member(user, sociallogin)

        # Verify member name was NOT changed
        member.refresh_from_db()
        assert member.name == existing_name
        assert member.surname == existing_surname

    def test_get_login_redirect_url_preserves_subdomain(self) -> None:
        """Test that login redirect preserves organization subdomain.

        When users log in via social auth on an organization subdomain,
        they should stay on that subdomain instead of being redirected
        to the main platform. This is especially important for first-time logins.
        """
        # Create a mock request with organization association context
        request = RequestFactory().get("/accounts/google/login/callback/")
        request.association = {"id": 123, "slug": "test-org", "name": "Test Organization"}

        # Execute get_login_redirect_url
        adapter = MySocialAccountAdapter()
        redirect_url = adapter.get_login_redirect_url(request)

        # Verify it returns a relative path (stays on same subdomain)
        assert redirect_url == "/"

    def test_get_login_redirect_url_main_domain_with_next_parameter(self) -> None:
        """Test that login redirect on main domain respects 'next' parameter.

        When users log in on the main platform with a 'next' parameter pointing
        to after_login, the adapter should use that URL to redirect to the org subdomain.
        """
        # Create a mock request with main domain and 'next' parameter
        request = RequestFactory().get(
            "/accounts/google/login/callback/", {"next": "https://larpmanager.com/after_login/test-org/"}
        )
        request.association = {"id": 0, "slug": "", "name": "LarpManager"}
        # Add get_host method for URL validation
        request.get_host = lambda: "larpmanager.com"

        # Execute get_login_redirect_url
        adapter = MySocialAccountAdapter()
        redirect_url = adapter.get_login_redirect_url(request)

        # Verify it uses the next parameter with after_login URL
        assert "/after_login/test-org/" in redirect_url

    def test_get_login_redirect_url_main_domain_uses_default(self) -> None:
        """Test that login redirect on main domain uses default behavior.

        When users log in on the main platform (association ID 0) without a next parameter,
        the default behavior using LOGIN_REDIRECT_URL should be used.
        """
        # Create a mock request with main domain association context
        request = RequestFactory().get("/accounts/google/login/callback/")
        request.association = {"id": 0, "slug": "", "name": "LarpManager"}

        # Execute get_login_redirect_url
        adapter = MySocialAccountAdapter()
        redirect_url = adapter.get_login_redirect_url(request)

        # Verify it uses default behavior
        # LOGIN_REDIRECT_URL = 'home' which may resolve to various paths
        # We verify it's a valid redirect (string type) and not an after_login URL
        assert isinstance(redirect_url, str)
        assert "/after_login/" not in redirect_url


@pytest.mark.django_db
class TestAccountAdapter:
    """Test custom account adapter functionality for signup redirects."""

    def test_get_signup_redirect_url_preserves_subdomain(self) -> None:
        """Test that signup redirect preserves organization subdomain.

        When users sign up via social auth on an organization subdomain (first-time login),
        they should stay on that subdomain instead of being redirected to the main platform.
        """
        # Create a mock request with organization association context
        request = RequestFactory().get("/accounts/google/login/callback/")
        request.association = {"id": 123, "slug": "test-org", "name": "Test Organization"}

        # Execute get_signup_redirect_url
        adapter = MyAccountAdapter()
        redirect_url = adapter.get_signup_redirect_url(request)

        # Verify it returns a relative path (stays on same subdomain)
        assert redirect_url == "/"

    def test_get_signup_redirect_url_main_domain_with_next_parameter(self) -> None:
        """Test that signup redirect on main domain respects 'next' parameter.

        When users sign up on the main platform with a 'next' parameter pointing to
        after_login (first-time OAuth from org page), the adapter should use that URL
        to redirect to the organization via after_login with token.
        """
        # Create a mock request with main domain and 'next' parameter
        request = RequestFactory().get(
            "/accounts/google/login/callback/", {"next": "https://larpmanager.com/after_login/test-org/"}
        )
        request.association = {"id": 0, "slug": "", "name": "LarpManager"}
        # Add get_host method for URL validation
        request.get_host = lambda: "larpmanager.com"

        # Execute get_signup_redirect_url
        adapter = MyAccountAdapter()
        redirect_url = adapter.get_signup_redirect_url(request)

        # Verify it uses the next parameter with after_login URL
        assert "/after_login/test-org/" in redirect_url

    def test_get_signup_redirect_url_main_domain_uses_default(self) -> None:
        """Test that signup redirect on main domain uses default behavior.

        When users sign up on the main platform without a next parameter,
        the default django-allauth redirect behavior should be used.
        """
        # Create a mock request with main domain association context
        request = RequestFactory().get("/accounts/google/login/callback/")
        request.association = {"id": 0, "slug": "", "name": "LarpManager"}

        # Execute get_signup_redirect_url
        adapter = MyAccountAdapter()
        redirect_url = adapter.get_signup_redirect_url(request)

        # Verify it uses default behavior
        # The default from django-allauth calls super() which resolves LOGIN_REDIRECT_URL
        # In test settings, LOGIN_REDIRECT_URL = 'home' which resolves to "/"
        # So we verify it's a valid redirect (string type) and not an after_login URL
        assert isinstance(redirect_url, str)
        assert "/after_login/" not in redirect_url
