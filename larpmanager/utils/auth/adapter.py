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

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

if TYPE_CHECKING:
    from allauth.socialaccount.models import SocialLogin
    from django.forms import Form
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


def _get_redirect_url_with_subdomain_support(request: HttpRequest) -> str | None:
    """Get redirect URL with organization subdomain support.

    This helper method handles the common redirect logic for both login and signup:
    1. On org subdomain: Returns "/" to stay on same subdomain
    2. On main domain with 'next' parameter: Returns the next URL (for after_login flow)
    3. On main domain without 'next': Returns None (use default behavior)

    The 'next' parameter is set by JavaScript in login.html when users initiate
    OAuth from an organization page, pointing to: /after_login/{slug}/

    Args:
        request: Django HTTP request object

    Returns:
        str: Redirect URL path, or None to use default behavior

    """
    # Get the association from request context (set by AssociationIdentifyMiddleware)
    association_data = getattr(request, "association", {})
    association_id = association_data.get("id", 0)

    # If on organization subdomain (association ID != 0), stay on same subdomain
    if association_id != 0:
        return "/"

    # On main domain - check for 'next' parameter pointing to after_login
    # The 'next' parameter is set by JavaScript in login template when users
    # initiate OAuth from an organization page
    next_url = request.GET.get("next") or request.POST.get("next")

    if next_url:
        # Validate the next URL for security
        allowed_hosts = {request.get_host(), ".".join(request.get_host().split(".")[-2:])}
        if url_has_allowed_host_and_scheme(next_url, allowed_hosts=allowed_hosts):
            # Check if it's an after_login URL
            if "/after_login/" in next_url:
                # Return the path component of the URL
                # This will redirect to after_login which generates a token
                return next_url.split(request.get_host())[-1] if request.get_host() in next_url else next_url
            # For other valid next URLs, use them
            return next_url

    # No valid next parameter - caller should use default behavior
    return None


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account adapter for LarpManager.

    Handles automatic user linking and profile updates from social login data.
    """

    @staticmethod
    def update_member(user: User, sociallogin: SocialLogin) -> None:
        """Update member profile from social login data.

        Updates the member's name and surname fields if they are currently empty,
        using data from the social login provider (e.g., Google, Facebook).

        Args:
            user: Django User instance with associated member profile
            sociallogin: Social login instance containing extra data from OAuth provider

        Returns:
            None

        Side Effects:
            - Updates member's name field if empty and 'given_name' is available
            - Updates member's surname field if empty and 'family_name' is available
            - Saves the member instance to persist changes

        """
        # Extract extra data from social login account
        social_provider_data = sociallogin.account.extra_data

        # Update name field if it's empty and given_name is available
        if "given_name" in social_provider_data and len(user.member.name) == 0:
            user.member.name = social_provider_data["given_name"]

        # Update surname field if it's empty and family_name is available
        if "family_name" in social_provider_data and len(user.member.surname) == 0:
            user.member.surname = social_provider_data["family_name"]

        # Persist changes to database
        user.member.save()

        # if user exists, connect the account to the existing account and login

    def pre_social_login(self, request: HttpRequest, sociallogin: SocialLogin) -> None:
        """Handle social login before user creation.

        Links social account to existing user if email matches, preventing
        duplicate accounts when users sign up with social providers after
        already having an account with the same email.

        Args:
            request: Django HTTP request object containing session and user data
            sociallogin: Social login instance containing user data from provider

        Returns:
            None

        Side Effects:
            - Connects social account to existing user if email match found
            - Updates member profile with social login data
            - No action taken if user already exists or has no email

        """
        user = sociallogin.user

        # Skip processing if user already has an ID (already exists)
        if user.id:
            return

        # Skip processing if no email provided by social provider
        if not user.email:
            return

        try:
            # Look for existing user with matching email address
            user = User.objects.get(email=user.email)

            # Connect the social account to the existing user
            sociallogin.connect(request, user)

            # Update member profile with social login information
            self.update_member(user, sociallogin)
        except ObjectDoesNotExist:
            # No existing user found - let normal signup process continue
            logger.debug(
                "No existing user found for email %s - proceeding with signup",
                sociallogin.account.extra_data.get("email"),
            )

    def save_user(self, request: HttpRequest, sociallogin: SocialLogin, form: Form | None = None) -> User:
        """Save new user from social login."""
        # Create the base user instance using parent implementation
        user = super().save_user(request, sociallogin, form)

        # Update member profile with additional data from social login
        self.update_member(user, sociallogin)

        return user

    def get_login_redirect_url(self, request: HttpRequest) -> str:
        """Get redirect URL after social login with proper subdomain handling."""
        # Use common helper method for subdomain-aware redirect logic
        redirect_url = _get_redirect_url_with_subdomain_support(request)

        # If helper returned a URL, use it; otherwise use LOGIN_REDIRECT_URL setting
        if redirect_url is not None:
            return redirect_url

        # Default: use Django's LOGIN_REDIRECT_URL setting or reverse lookup
        return settings.LOGIN_REDIRECT_URL if hasattr(settings, "LOGIN_REDIRECT_URL") else reverse("home")


class MyAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter for LarpManager.

    Handles redirect URLs for first-time signups (including social OAuth signups).
    Uses the same logic as MySocialAccountAdapter to respect the 'next' parameter
    and enable token-based cross-subdomain authentication.
    """

    def get_signup_redirect_url(self, request: HttpRequest) -> str:
        """Get redirect URL after signup (first-time social login)."""
        # Use common helper method for subdomain-aware redirect logic
        redirect_url = _get_redirect_url_with_subdomain_support(request)

        # If helper returned a URL, use it; otherwise use default behavior
        return redirect_url if redirect_url is not None else super().get_signup_redirect_url(request)
