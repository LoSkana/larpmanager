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

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from django.http import HttpRequest


class FeatureError(Exception):
    """Exception raised when a required feature is not enabled.

    Attributes:
        feature (str): The feature that was required but not enabled
        run (int): Run ID associated with the error
        path (str): Request path where the error occurred

    """

    def __init__(self, feature: str, run: int, path: str) -> None:
        """Initialize the object with feature, run, and path parameters."""
        super().__init__()
        # Store the feature reference
        self.feature = feature
        # Store the run reference
        self.run = run
        # Store the path string
        self.path = path


class RedirectError(Exception):
    """Trigger a redirect from middleware."""

    def __init__(
        self,
        view: Any,
        args: Iterable[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        """Init exception with redirect params."""
        super().__init__()
        self.view = view
        self.args = tuple(args or ())
        self.kwargs = dict(kwargs or {})


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
        """Initialize with association slug."""
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


class UserPermissionError(Exception):
    """Exception raised when user lacks required permissions."""


class UnknowRunError(Exception):
    """Exception raised when a run cannot be found or identified."""


class MembershipError(Exception):
    """Exception raised for membership-related issues.

    Attributes:
        assocs (list, optional): List of associations related to the error

    """

    def __init__(self, assocs: list | None = None) -> None:
        """Initialize form with optional associations list."""
        super().__init__()
        self.assocs = assocs


def check_association_feature(request: HttpRequest, context: dict, feature_slug: str) -> None:
    """Check if association has required feature enabled."""
    # Check if the requested feature slug exists in the association's enabled features
    if feature_slug not in context["features"]:
        # Raise error with feature slug, error code 0, and current request path
        raise FeatureError(feature_slug, 0, request.path)


def check_event_feature(request: HttpRequest, context: dict, feature_slug: str) -> None:
    """Check if event has required feature enabled."""
    # Check if the requested feature slug exists in the event's enabled features
    if feature_slug not in context["features"]:
        # Raise detailed error with context information for debugging
        raise FeatureError(feature_slug, context["run"].id, request.path)


class MainPageError(Exception):
    """Exception used to redirect to main page.

    Attributes:
        path (str, optional): Original request path

    """

    def __init__(self, request: HttpRequest | None = None) -> None:
        """Initialize with request path and base domain from association."""
        super().__init__()
        self.path = request.path
        self.base_domain = request.association["main_domain"]


# For when you want to just return a json value
class ReturnNowError(Exception):
    """Exception used to immediately return a value from view processing.

    Attributes:
        value: Value to return (typically JSON response)

    """

    def __init__(self, value: Any = None) -> None:
        """Initialize with optional value."""
        super().__init__()
        self.value = value


class RewokedMembershipError(Exception):
    """Exception for RewokedMembershipError."""
