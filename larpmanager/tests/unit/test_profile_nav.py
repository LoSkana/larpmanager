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

"""Tests for the profile navigation shortcuts."""

from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse

from larpmanager.models.member import Membership
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.nav import build_profile_home_nav_items


class TestProfileHomeNavAccounting(BaseTestCase):
    """Test cases for the accounting shortcut of the profile navigation."""

    def _accounting_shown(self, member: Any, association: Any) -> bool:
        request = RequestFactory().get("/")
        request.user = User.objects.get(pk=member.user_id)
        request.association = {"id": association.id, "features": set()}
        request.resolver_match = None
        return any(item["url"] == reverse("accounting") for item in build_profile_home_nav_items(request))

    def test_accounting_hidden_without_registrations_or_balance(self) -> None:
        """Test the shortcut is hidden for a user with nothing to show."""
        member = self.create_member()
        association = self.get_association()
        Membership.objects.filter(member=member, association=association).update(credit=0, tokens=0)

        self.assertFalse(self._accounting_shown(member, association))

    def test_accounting_shown_with_credits(self) -> None:
        """Test the shortcut is shown for a user holding credits, even without registrations."""
        member = self.create_member()
        association = self.get_association()
        Membership.objects.filter(member=member, association=association).update(credit=Decimal("130.00"), tokens=0)

        self.assertTrue(self._accounting_shown(member, association))
