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

import time
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from larpmanager.middleware.sso import SocialLoginTargetMiddleware
from larpmanager.models.member import Member
from larpmanager.templatetags.show_tags import auth_next_query, get_social_login_url
from larpmanager.utils.auth.adapter import MyAccountAdapter, MySocialAccountAdapter
from larpmanager.utils.auth.sso import (
    SSO_SLUG_MAX_AGE,
    SSO_SLUG_SESSION_KEY,
    get_auth_next_url,
    safe_local_url,
)
from larpmanager.views.base import after_login


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

    def test_pre_social_login_links_by_email_case_insensitive(self) -> None:
        """Test that social login links an existing user whose email differs only in case."""
        existing_user = User.objects.create_user(
            username="Mixed.Case_unique@example.com", email="Mixed.Case_unique@example.com", password="testpass123"
        )
        if not hasattr(existing_user, "member"):
            Member.objects.create(user=existing_user, name="Mixed", surname="Case")

        request = RequestFactory().get("/accounts/google/login/callback/")
        request.user = Mock()

        provider_email = "mixed.case_unique@example.com"
        social_account = Mock(spec=SocialAccount)
        social_account.extra_data = {"email": provider_email, "given_name": "Mixed", "family_name": "Case"}
        social_account.provider = "google"
        sociallogin = SocialLogin(user=User(username="mixed", email=provider_email), account=social_account)

        MySocialAccountAdapter().pre_social_login(request, sociallogin)

        assert sociallogin.user.id == existing_user.id
        assert User.objects.filter(email__iexact=provider_email).count() == 1

    @staticmethod
    def _sociallogin(provider_email: str, extra: dict | None = None) -> SocialLogin:
        social_account = Mock(spec=SocialAccount)
        social_account.extra_data = {
            "email": provider_email,
            "given_name": "Dup",
            "family_name": "User",
            **(extra or {}),
        }
        social_account.provider = "google"
        return SocialLogin(user=User(username="dup", email=provider_email), account=social_account)

    @staticmethod
    def _callback_request() -> HttpRequest:
        request = RequestFactory().get("/accounts/google/login/callback/")
        request.user = Mock()
        return request

    def test_pre_social_login_links_oldest_user_when_email_duplicated(self) -> None:
        """Test that social login links the oldest user when several share the email in a different case."""
        oldest_user = User.objects.create_user(
            username="Dup_unique@example.com", email="Dup_unique@example.com", password="testpass123"
        )
        User.objects.create_user(username="dup_newer_unique", email="dUp_unique@example.com", password="testpass123")
        if not hasattr(oldest_user, "member"):
            Member.objects.create(user=oldest_user, name="Dup", surname="User")

        sociallogin = self._sociallogin("dup_unique@example.com")
        MySocialAccountAdapter().pre_social_login(self._callback_request(), sociallogin)

        assert sociallogin.user.id == oldest_user.id

    def test_pre_social_login_prefers_exact_email_match(self) -> None:
        """Test that social login links the user whose email matches exactly over older case variants."""
        User.objects.create_user(
            username="Exact_unique@example.com", email="Exact_unique@example.com", password="testpass123"
        )
        exact_user = User.objects.create_user(
            username="exact_newer_unique", email="exact_unique@example.com", password="testpass123"
        )
        if not hasattr(exact_user, "member"):
            Member.objects.create(user=exact_user, name="Exact", surname="User")

        sociallogin = self._sociallogin("exact_unique@example.com")
        MySocialAccountAdapter().pre_social_login(self._callback_request(), sociallogin)

        assert sociallogin.user.id == exact_user.id

    def test_pre_social_login_skips_unverified_email(self) -> None:
        """Test that social login never links an existing user on an unverified provider email."""
        User.objects.create_user(
            username="unverified_unique@example.com", email="unverified_unique@example.com", password="testpass123"
        )

        sociallogin = self._sociallogin("unverified_unique@example.com", {"email_verified": False})
        MySocialAccountAdapter().pre_social_login(self._callback_request(), sociallogin)

        assert sociallogin.user.id is None

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

    def test_get_login_redirect_url_main_domain_with_next_parameter(self) -> None:
        """Test that login redirect respects the 'next' parameter, not request.association.

        The OAuth callback always lands on the main domain (Google's redirect URI is
        only registered there), so request.association is always the main-domain
        association at this point - it must NOT be used to decide the redirect.
        The originating subdomain travels exclusively via the 'next' parameter,
        set server-side by get_social_login_url in show_tags.py.
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

    def test_get_signup_redirect_url_main_domain_with_next_parameter(self) -> None:
        """Test that signup redirect respects the 'next' parameter, not request.association.

        Same reasoning as the login case: the OAuth callback always lands on the main
        domain, so request.association can't identify the originating subdomain there.
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


class TestSocialLoginTargetMiddleware:
    """Test that the target subdomain of a social login is remembered."""

    @staticmethod
    def _run(path: str, params: dict) -> dict:
        request = RequestFactory().get(path, params)
        request.session = {}
        SocialLoginTargetMiddleware(lambda _request: HttpResponse())(request)
        return request.session

    def test_stashes_slug_from_next(self) -> None:
        """The slug of the after_login target is stored in the session."""
        session = self._run("/accounts/google/login/", {"next": "https://larpmanager.com/after_login/test-org/"})

        assert session[SSO_SLUG_SESSION_KEY][0] == "test-org"

    def test_ignores_unrelated_next(self) -> None:
        """A next parameter that is not an after_login URL stores nothing."""
        session = self._run("/accounts/google/login/", {"next": "/manage/"})

        assert SSO_SLUG_SESSION_KEY not in session

    def test_ignores_other_paths(self) -> None:
        """Requests outside the provider login URLs store nothing."""
        session = self._run("/manage/", {"next": "https://larpmanager.com/after_login/test-org/"})

        assert SSO_SLUG_SESSION_KEY not in session


@pytest.mark.django_db
class TestStashedSlugFallback:
    """Test the fallback used when django-allauth loses its session state.

    The OAuth callback carries no 'next' of its own: allauth keeps it in a
    per-attempt session state that is garbage collected once too many logins are
    pending. Without a fallback the user would be sent to the main domain.
    """

    @staticmethod
    def _callback_request(stashed: object) -> RequestFactory:
        request = RequestFactory().get("/accounts/google/login/callback/")
        request.association = {"id": 0, "slug": "", "name": "LarpManager"}
        request.session = {SSO_SLUG_SESSION_KEY: stashed}
        return request

    def test_login_redirect_uses_stashed_slug(self) -> None:
        """A login without 'next' goes back to the stashed subdomain."""
        request = self._callback_request(["test-org", time.time()])

        redirect_url = MyAccountAdapter().get_login_redirect_url(request)

        assert redirect_url == "/after_login/test-org/"
        # The slug is consumed, so it cannot hijack a later login
        assert SSO_SLUG_SESSION_KEY not in request.session

    def test_signup_redirect_uses_stashed_slug(self) -> None:
        """A first-time social signup also goes back to the stashed subdomain."""
        request = self._callback_request(["test-org", time.time()])

        assert MyAccountAdapter().get_signup_redirect_url(request) == "/after_login/test-org/"

    def test_stale_slug_is_ignored(self) -> None:
        """An abandoned social login does not redirect a later login."""
        request = self._callback_request(["test-org", time.time() - SSO_SLUG_MAX_AGE - 1])
        # The allauth default redirect asserts an authenticated user
        request.user = Mock(is_authenticated=True)

        redirect_url = MyAccountAdapter().get_login_redirect_url(request)

        assert "/after_login/" not in redirect_url


class TestAuthNextDestination:
    """Test that the page a login starts from survives the authentication flow."""

    @staticmethod
    def _request(path: str, params: dict | None = None) -> HttpRequest:
        request = RequestFactory().get(path, params or {})
        request.association = {"id": 2, "slug": "test-org", "main_domain": "larpmanager.com"}
        return request

    def test_next_url_is_current_page(self) -> None:
        """Outside auth pages, the current page is the destination."""
        request = self._request("/event/test/register/", {"ticket": "a"})

        assert get_auth_next_url(request) == "/event/test/register/?ticket=a"

    def test_next_url_passes_through_on_login_page(self) -> None:
        """On the login page the incoming 'next' is kept instead of the login page itself."""
        request = self._request("/login/", {"next": "/event/test/register/"})

        assert get_auth_next_url(request) == "/event/test/register/"

    def test_next_url_skips_home(self) -> None:
        """The home page is the default landing, so it is not carried."""
        assert get_auth_next_url(self._request("/")) is None

    def test_next_url_register_subpages_are_destinations(self) -> None:
        """Only the signup page itself passes 'next' through, not its sub pages."""
        assert get_auth_next_url(self._request("/register/conditions/")) == "/register/conditions/"

    def test_next_url_rejects_external(self) -> None:
        """An external 'next' is never propagated."""
        request = self._request("/login/", {"next": "https://evil.example/"})

        assert get_auth_next_url(request) is None
        assert safe_local_url("//evil.example/") is None

    def test_social_login_url_carries_destination(self) -> None:
        """A subdomain Google login brings the user back to the page it started for."""
        request = self._request("/login/", {"next": "/event/test/register/"})

        url = get_social_login_url({"association": request.association, "request": request}, "google")

        query = parse_qs(urlparse(url).query)
        after_login = urlparse(query["next"][0])
        assert after_login.path == "/after_login/test-org/"
        assert parse_qs(after_login.query)["next"] == ["/event/test/register/"]

    def test_auth_next_query(self) -> None:
        """Login links point back to the current page."""
        request = self._request("/event/test/")

        assert auth_next_query({"request": request}) == "?next=%2Fevent%2Ftest%2F"


@pytest.mark.django_db
class TestAfterLogin:
    """Test the cross-subdomain hop after a social login."""

    @pytest.fixture(autouse=True)
    def _allowed_hosts(self, settings: object) -> None:
        settings.ALLOWED_HOSTS = ["larpmanager.com"]

    @staticmethod
    def _request(path: str, params: dict | None = None) -> HttpRequest:
        request = RequestFactory().get(path, params or {}, HTTP_HOST="larpmanager.com")
        request.user = Mock(is_authenticated=True, id=1)
        request.enviro = "prod"
        return request

    def test_redirects_to_next_with_token(self) -> None:
        """The destination page is kept, with the token appended to its query."""
        request = self._request("/after_login/test-org/", {"next": "/event/test/register/?ticket=a"})

        response = after_login(request, "test-org")

        target = urlparse(response.url)
        assert target.netloc == "test-org.larpmanager.com"
        assert target.path == "/event/test/register/"
        query = parse_qs(target.query)
        assert query["ticket"] == ["a"]
        assert "token" in query

    def test_ignores_external_next(self) -> None:
        """An external 'next' falls back to the subdomain path."""
        request = self._request("/after_login/test-org/", {"next": "https://evil.example/"})

        response = after_login(request, "test-org")

        target = urlparse(response.url)
        assert target.netloc == "test-org.larpmanager.com"
        assert target.path == "/"

    def test_token_precedes_fragment(self) -> None:
        """The token is kept in the query even when the destination has a fragment."""
        request = self._request("/after_login/test-org/", {"next": "/event/test/?ticket=a#form"})

        response = after_login(request, "test-org")

        target = urlparse(response.url)
        assert target.fragment == "form"
        query = parse_qs(target.query)
        assert query["ticket"] == ["a"]
        assert "token" in query

    def test_anonymous_keeps_destination(self) -> None:
        """An anonymous hit is sent to login, coming back here afterwards."""
        request = self._request("/after_login/test-org/")
        request.user = Mock(is_authenticated=False)

        response = after_login(request, "test-org")

        assert parse_qs(urlparse(response.url).query)["next"] == ["/after_login/test-org/"]
