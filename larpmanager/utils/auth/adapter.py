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

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

if TYPE_CHECKING:
    from allauth.socialaccount.models import SocialLogin
    from django.forms import Form
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


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
        """Save new user from social login.

        Creates a new user account from social authentication data and updates
        the associated member profile with information from the social provider.

        Args:
            request: Django HTTP request object containing session and user data
            sociallogin: Social login instance containing provider authentication data
            form: Optional form data for additional user information

        Returns:
            User: The newly created and configured user instance

        Raises:
            ValidationError: If user data from social login is invalid
            IntegrityError: If user already exists or conflicts with existing data

        Side Effects:
            - Creates new User instance in database
            - Updates associated Member profile with social login data
            - May trigger user creation signals

        """
        # Create the base user instance using parent implementation
        user = super().save_user(request, sociallogin, form)

        # Update member profile with additional data from social login
        self.update_member(user, sociallogin)

        return user
