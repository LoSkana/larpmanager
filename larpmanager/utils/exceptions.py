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
    def __init__(self, feature, run, path):
        super().__init__()
        self.feature = feature
        self.run = run
        self.path = path


class RedirectError(Exception):
    def __init__(self, view):
        super().__init__()
        self.view = view


class SignupError(Exception):
    def __init__(self, slug, number):
        super().__init__()
        self.slug = slug
        self.number = number


class WaitingError(Exception):
    def __init__(self, slug, number):
        super().__init__()
        self.slug = slug
        self.number = number


class HiddenError(Exception):
    def __init__(self, slug, number, name):
        super().__init__()
        self.slug = slug
        self.number = number
        self.name = name


class NotFoundError(Exception):
    pass


class PermissionError(Exception):
    pass


class UnknowRunError(Exception):
    pass


class MembershipError(Exception):
    def __init__(self, assocs=None):
        super().__init__()
        self.assocs = assocs


def check_assoc_feature(request, s):
    if s not in request.assoc["features"]:
        raise FeatureError(s, 0, request.path)


def check_event_feature(request, ctx, s):
    if s not in ctx["features"]:
        raise FeatureError(s, ctx["run"].id, request.path)


class MainPageError(Exception):
    def __init__(self, path=None):
        super().__init__()
        self.path = path

# For when you want to just return a json value
class ReturnJson(Exception):
    def __init__(self, value=None):
        super().__init__()
        self.value = value