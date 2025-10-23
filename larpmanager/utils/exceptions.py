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
from typing import Any

from django.http import HttpRequest

from larpmanager.models.base import Feature
from larpmanager.models.event import Run


class FeatureError(Exception):
    """Exception raised when a required feature is not enabled.

    Attributes:
        feature (str): The feature that was required but not enabled
        run (int): Run ID associated with the error
        path (str): Request path where the error occurred
    """

    def __init__(self, feature: Feature, run: Run, path: str) -> None:
        """Initialize the object with feature, run, and path parameters.

        Args:
            feature: The feature object to associate
            run: The run object to associate
            path: The file path string
        """
        super().__init__()
        # Store the feature reference
        self.feature = feature
        # Store the run reference
        self.run = run
        # Store the path string
        self.path = path


class RedirectError(Exception):
    """Exception used to trigger view redirects.

    Attributes:
        view (str): View name to redirect to
    """

    def __init__(self, view: Any) -> None:
        # Initialize base class
        super().__init__()
        self.view = view


class SignupError(Exception):
    """Exception raised when signup is not allowed or available.

    Attributes:
        slug (str): Event slug associated with the signup error
    """

    def __init__(self, slug: str) -> None:
        """Initialize with association slug."""
        super().__init__()
        self.slug = slug


class WaitingError(Exception):
    """Exception raised when user must wait for registration.

    Attributes:
        slug (str): Event slug for the waiting period
    """

    def __init__(self, slug: str) -> None:
        super().__init__()
        self.slug = slug


class HiddenError(Exception):
    """Exception raised when trying to access hidden content.

    Attributes:
        slug (str): Event slug
        name (str): Name of the hidden content
    """

    def __init__(self, slug: str, name: str) -> None:
        """Initialize with slug and name."""
        super().__init__()
        self.slug = slug
        self.name = name


class NotFoundError(Exception):
    """Generic exception for content not found scenarios."""

    pass


class PermissionError(Exception):
    """Exception raised when user lacks required permissions."""

    pass


class UnknowRunError(Exception):
    """Exception raised when a run cannot be found or identified."""

    pass


class MembershipError(Exception):
    """Exception raised for membership-related issues.

    Attributes:
        assocs (list, optional): List of associations related to the error
    """

    def __init__(self, assocs: list | None = None) -> None:
        """Initialize form with optional associations list."""
        super().__init__()
        self.assocs = assocs


def check_assoc_feature(request: HttpRequest, s: str) -> None:
    """Check if association has required feature enabled.

    Validates that the specified feature is enabled for the association
    in the current request context. This is typically used as a guard
    to ensure users only access functionality their organization has
    subscribed to or enabled.

    Args:
        request: Django HTTP request object containing association context
            with 'assoc' attribute that includes 'features' dictionary
        s: Feature slug identifier to validate against enabled features

    Raises:
        FeatureError: If the specified feature is not enabled for the
            association, includes feature slug, error code 0, and request path

    Example:
        check_assoc_feature(request, 'advanced_registration')
    """
    # Check if the requested feature slug exists in the association's enabled features
    if s not in request.assoc["features"]:
        # Raise error with feature slug, error code 0, and current request path
        raise FeatureError(s, 0, request.path)


def check_event_feature(request: HttpRequest, ctx: dict, s: str) -> None:
    """Check if event has required feature enabled.

    Validates that a specific feature is enabled for the current event context.
    Raises an exception if the feature is not available, preventing access to
    functionality that requires the feature.

    Args:
        request: Django HTTP request object containing user and session data
        ctx: Event context dictionary containing features and run information
        s: Feature slug string identifier to check for availability

    Raises:
        FeatureError: If the specified feature is not enabled for the event,
                     includes feature slug, run ID, and request path for debugging

    Example:
        >>> check_event_feature(request, event_ctx, 'character_creation')
        # Raises FeatureError if 'character_creation' feature is disabled
    """
    # Check if the requested feature slug exists in the event's enabled features
    if s not in ctx["features"]:
        # Raise detailed error with context information for debugging
        raise FeatureError(s, ctx["run"].id, request.path)


class MainPageError(Exception):
    """Exception used to redirect to main page.

    Attributes:
        path (str, optional): Original request path
    """

    def __init__(self, request: HttpRequest | None = None) -> None:
        """Initialize with request path and base domain from association."""
        super().__init__()
        self.path = request.path
        self.base_domain = request.assoc["main_domain"]


# For when you want to just return a json value
class ReturnNowError(Exception):
    """Exception used to immediately return a value from view processing.

    Attributes:
        value: Value to return (typically JSON response)
    """

    def __init__(self, value: Any = None) -> None:
        super().__init__()
        self.value = value


class RewokedMembershipError(Exception):
    pass
