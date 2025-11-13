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

from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.http import HttpRequest


class EmailOrUsernameModelBackend(ModelBackend):
    """Authentication backend which allows users to authenticate using either their username or email address.

    Source: https://stackoverflow.com/a/35836674/59984
    """

    def authenticate(
        self,
        request: HttpRequest | None,  # noqa: ARG002
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> AbstractUser | None:
        """Authenticate user with username/password allowing email or username.

        Attempts to authenticate a user by checking both username and email fields
        for a match. This allows users to login with either their username or email
        address. Implements timing attack protection for non-existent users.

        Args:
            request: HTTP request object (may be None in Django <2.1)
            username: Username or email address for authentication
            password: Plain text password for authentication
            **kwargs: Additional authentication parameters including USERNAME_FIELD

        Returns:
            Authenticated user object if credentials are valid, None otherwise

        Note:
            Django <2.1 does not pass the request parameter.

        """
        # Get the user model for this authentication backend
        user_model = get_user_model()

        # Extract username from kwargs if not provided directly
        if username is None:
            username = kwargs.get(user_model.USERNAME_FIELD)

        # Query for users matching either username field or email field
        # The username field allows '@' characters so email addresses could
        # potentially exist in either field, even for different users
        # noinspection PyProtectedMember
        matching_users = user_model._default_manager.filter(  # noqa: SLF001  # Django model manager
            Q(**{user_model.USERNAME_FIELD: username}) | Q(email__iexact=username),
        )

        # Test password against each matching user record
        # Return the first user with valid credentials
        for candidate_user in matching_users:
            if candidate_user.check_password(password):
                return candidate_user

        # Timing attack protection: run password hasher even when no users found
        # This ensures consistent response time regardless of username existence
        if not matching_users:
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a non-existing user (see
            # https://code.djangoproject.com/ticket/20760)
            user_model().set_password(password)
        return None
