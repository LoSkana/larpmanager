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


class FeatureError(Exception):
    """Exception raised when a required feature is not enabled.

    Attributes:
        feature (str): The feature that was required but not enabled
        run (int): Run ID associated with the error
        path (str): Request path where the error occurred
    """

    def __init__(self, feature, run, path):
        super().__init__()
        self.feature = feature
        self.run = run
        self.path = path


class RedirectError(Exception):
    """Exception used to trigger view redirects.

    Attributes:
        view (str): View name to redirect to
    """

    def __init__(self, view):
        super().__init__()
        self.view = view


class SignupError(Exception):
    """Exception raised when signup is not allowed or available.

    Attributes:
        slug (str): Event slug associated with the signup error
    """

    def __init__(self, slug):
        super().__init__()
        self.slug = slug


class WaitingError(Exception):
    """Exception raised when user must wait for registration.

    Attributes:
        slug (str): Event slug for the waiting period
    """

    def __init__(self, slug):
        super().__init__()
        self.slug = slug


class HiddenError(Exception):
    """Exception raised when trying to access hidden content.

    Attributes:
        slug (str): Event slug
        name (str): Name of the hidden content
    """

    def __init__(self, slug, name):
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

    def __init__(self, assocs=None):
        super().__init__()
        self.assocs = assocs


def check_assoc_feature(request, s):
    """Check if association has required feature enabled.

    Args:
        request: Django HTTP request with association context
        s (str): Feature slug to check

    Raises:
        FeatureError: If feature is not enabled for the association
    """
    if s not in request.assoc["features"]:
        raise FeatureError(s, 0, request.path)


def check_event_feature(request, ctx, s):
    """Check if event has required feature enabled.

    Args:
        request: Django HTTP request
        ctx (dict): Event context with features
        s (str): Feature slug to check

    Raises:
        FeatureError: If feature is not enabled for the event
    """
    if s not in ctx["features"]:
        raise FeatureError(s, ctx["run"].id, request.path)


class MainPageError(Exception):
    """Exception used to redirect to main page.

    Attributes:
        path (str, optional): Original request path
    """

    def __init__(self, path=None):
        super().__init__()
        self.path = path


# For when you want to just return a json value
class ReturnNowError(Exception):
    """Exception used to immediately return a value from view processing.

    Attributes:
        value: Value to return (typically JSON response)
    """

    def __init__(self, value=None):
        super().__init__()
        self.value = value
