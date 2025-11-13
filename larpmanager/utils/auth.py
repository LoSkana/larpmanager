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
from typing import TYPE_CHECKING, Any

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max
from django.http import Http404, HttpRequest

from larpmanager.models.access import EventPermission

if TYPE_CHECKING:
    from allauth.socialaccount.models import SocialLogin
    from django.forms import Form

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
        # logger.debug(f"Social provider data: {social_provider_data}")

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
            pass

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


def is_lm_admin(request: HttpRequest) -> bool:
    """Check if user is a LarpManager administrator.

    This function determines if the authenticated user has administrator
    privileges within the LarpManager system by checking superuser status
    and admin group membership.

    Args:
        request: Django HTTP request object containing authenticated user data.
                Must have a 'user' attribute with potential 'member' relationship.

    Returns:
        bool: True if user is a superuser or belongs to LM admin group,
              False otherwise or if user lacks member relationship.

    Note:
        Admin group checking is currently not implemented (TODO).

    """
    # Check if user has associated member profile
    if not hasattr(request.user, "member"):
        return False

    # Superusers always have admin privileges
    # TODO: Implement admin group membership check
    # This should verify if user belongs to LarpManager admin group
    return request.user.is_superuser


def check_lm_admin(request: HttpRequest) -> dict[str, Any]:
    """Verify user is LM admin and return admin context.

    This function validates that the current user has LM (LarpManager) administrator
    privileges and returns a context dictionary containing association information
    and admin status flag.

    Args:
        request: Django HTTP request object containing user and association data.

    Returns:
        A dictionary containing:
            - association_id (int): The association ID from the request
            - lm_admin (int): Admin flag set to 1 indicating LM admin status

    Raises:
        Http404: If the user does not have LM administrator privileges.

    Example:
        >>> context = check_lm_admin(request)
        >>> print(context)
        {'association_id': 123, 'lm_admin': 1}

    """
    # Check if the current user has LM administrator privileges
    if not is_lm_admin(request):
        msg = "Not lm admin"
        raise Http404(msg)

    # Return admin context with association ID and admin flag
    return {"association_id": request.association["id"], "lm_admin": 1}


def get_allowed_managed() -> list[str]:
    """Get list of allowed management permission keys.

    This function returns a predefined list of permission strings that are
    allowed for management access within the LarpManager system. These
    permissions control access to various administrative and organizational
    features.

    Returns:
        list[str]: List of permission strings for management access. Includes
            both executive-level (exe_*) and organizational-level (orga_*)
            permissions.

    Example:
        >>> permissions = get_allowed_managed()
        >>> 'exe_events' in permissions
        True

    """
    return [
        # Executive-level permissions for organization-wide features
        "exe_events",
        "exe_accounting",
        "exe_preferences",
        # Event-specific organizational permissions
        "orga_event",
        "orga_cancellations",
        # Registration management permissions
        "orga_registration_form",
        "orga_registration_tickets",
        "orga_registrations",
        # Financial and sensitive data permissions
        "orga_accounting",
        "orga_sensitive",
        "orga_preferences",
    ]


def auto_assign_event_permission_number(event_permission: Any) -> None:
    """Assign number to event permission if not set.

    Args:
        event_permission: EventPermission instance to assign number to

    """
    if not event_permission.number:
        max_number = EventPermission.objects.filter(feature__module=event_permission.feature.module).aggregate(
            Max("number"),
        )["number__max"]
        if not max_number:
            max_number = 1
        event_permission.number = max_number + 10
