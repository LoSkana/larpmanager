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

"""Tests for the one-time tour shown on a member's first management dashboard visit."""

from importlib import import_module

from django.apps import apps

from larpmanager.cache.config import get_member_config
from larpmanager.models.access import AssociationRole
from larpmanager.models.member import MemberConfig
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.base import FIRST_ROLE_DRIVER_CONFIG_PREFIX, add_first_role_driver


class TestFirstRoleDriver(BaseTestCase):
    """First role tour selection and one-time consumption."""

    def _config_name(self) -> str:
        """Return the marker config name for the test association."""
        return f"{FIRST_ROLE_DRIVER_CONFIG_PREFIX}{self.get_association().id}"

    def _context(self, **extra: object) -> dict:
        """Build a dashboard context for the test member."""
        return {
            "member": self.get_member(),
            "association_id": self.get_association().id,
            "role_names": ["Staff"],
            **extra,
        }

    def test_shown_once(self) -> None:
        """The tour is shown on the first visit and never again."""
        first_visit = self._context()
        add_first_role_driver(first_visit)
        self.assertEqual(first_visit["intro_driver"], "first_role")
        self.assertTrue(get_member_config(self.get_member().id, self._config_name(), bypass_cache=True))

        second_visit = self._context()
        add_first_role_driver(second_visit)
        self.assertNotIn("intro_driver", second_visit)

    def test_shown_again_in_another_association(self) -> None:
        """Having seen the tour in one association does not affect the others."""
        add_first_role_driver(self._context())

        other_association = self._context(association_id=self.get_association().id + 1)
        add_first_role_driver(other_association)
        self.assertEqual(other_association["intro_driver"], "first_role")

    def test_association_tour_takes_precedence(self) -> None:
        """A pending association tour is kept and counts as the introduction."""
        context = self._context(intro_driver="welcome")
        add_first_role_driver(context)
        self.assertEqual(context["intro_driver"], "welcome")

        next_visit = self._context()
        add_first_role_driver(next_visit)
        self.assertNotIn("intro_driver", next_visit)

    def test_ignored_without_role(self) -> None:
        """Members accessing the dashboard without a role are not marked as introduced."""
        context = self._context(role_names=[])
        add_first_role_driver(context)
        self.assertNotIn("intro_driver", context)
        self.assertFalse(get_member_config(self.get_member().id, self._config_name(), bypass_cache=True))

    def test_migration_marks_existing_role_holders(self) -> None:
        """Members holding a role before the rollout never see the tour."""
        member = self.get_member()
        role, _created = AssociationRole.objects.get_or_create(
            association=self.get_association(), number=1, defaults={"name": "Admin"}
        )
        role.members.add(member)

        migration = import_module("larpmanager.migrations.0199_mark_first_role_driver_seen")
        migration.mark_existing_role_holders(apps, None)

        self.assertTrue(MemberConfig.objects.filter(member=member, name=self._config_name(), value="True").exists())
