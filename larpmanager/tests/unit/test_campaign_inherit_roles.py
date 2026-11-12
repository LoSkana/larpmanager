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

"""Tests for the campaign_inherit_roles config: new campaign events copy the roles of the last event."""

from datetime import date

from larpmanager.models.access import EventPermission, EventRole
from larpmanager.models.base import Feature
from larpmanager.models.event import EventConfig, Run
from larpmanager.tests.unit.base import BaseTestCase


class TestCampaignInheritRoles(BaseTestCase):
    """Roles of the most recent campaign event are inherited by a new child event."""

    def _setup_campaign(self, *, inherit: bool) -> tuple:
        """Create a campaign parent with a previous child event holding a custom role."""
        parent = self.create_event(name="Campaign Parent")
        campaign_feature, _created = Feature.objects.get_or_create(slug="campaign", defaults={"name": "Campaign"})
        parent.features.add(campaign_feature)
        if inherit:
            EventConfig.objects.create(event=parent, name="campaign_inherit_roles", value="True")

        Run.objects.filter(event=parent).update(end=date(2024, 1, 1))

        previous = self.create_event(name="Previous Chapter", parent=parent)
        Run.objects.filter(event=previous).update(end=date(2025, 1, 1))

        member = self.create_member()
        permission = EventPermission.objects.first()
        role = EventRole.objects.create(event=previous, number=2, name="Writer")
        role.members.add(member)
        if permission:
            role.permissions.add(permission)

        return parent, member, permission

    def test_roles_inherited_when_enabled(self) -> None:
        """A new child event receives roles, members and permissions of the last campaign event."""
        parent, member, permission = self._setup_campaign(inherit=True)

        new_event = self.create_event(name="Next Chapter", parent=parent)

        role = EventRole.objects.get(event=new_event, number=2)
        assert role.name == "Writer"
        assert member in role.members.all()
        if permission:
            assert permission in role.permissions.all()

    def test_roles_not_inherited_when_disabled(self) -> None:
        """Without the config, the new child event gets no roles from the campaign."""
        parent, _member, _permission = self._setup_campaign(inherit=False)

        new_event = self.create_event(name="Next Chapter", parent=parent)

        assert not EventRole.objects.filter(event=new_event, number=2).exists()
