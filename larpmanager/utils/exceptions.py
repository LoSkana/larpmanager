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

class FeatureException(Exception):
    def __init__(self, feature, run, path):
        super().__init__()
        self.feature = feature
        self.run = run
        self.path = path


class RedirectException(Exception):
    def __init__(self, view):
        super().__init__()
        self.view = view


class SignupException(Exception):
    def __init__(self, slug, number):
        super().__init__()
        self.slug = slug
        self.number = number


class WaitingException(Exception):
    def __init__(self, slug, number):
        super().__init__()
        self.slug = slug
        self.number = number


class HiddenException(Exception):
    def __init__(self, slug, number, name):
        super().__init__()
        self.slug = slug
        self.number = number
        self.name = name


class NotFoundException(Exception):
    pass


class PermissionException(Exception):
    pass


class UnknowRunException(Exception):
    pass


class MembershipException(Exception):
    def __init__(self, assocs=None):
        super().__init__()
        self.assocs = assocs


def check_assoc_feature(request, s):
    if s not in request.assoc["features"]:
        raise FeatureException(s, 0, request.path)


def check_event_feature(request, ctx, s):
    if s not in ctx["features"]:
        raise FeatureException(s, ctx["run"].id, request.path)
