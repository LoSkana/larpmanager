# LarpManager - https://larpmanager.com
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

"""Regression tests for deferred_delete_demo (demo association + orphan user teardown)."""

from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User

from larpmanager.models import signals as lm_signals
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.form import RegistrationOption, RegistrationQuestion
from larpmanager.models.larpmanager import LarpManagerDemoType
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import Registration, RegistrationTicket
from larpmanager.models.writing import Character, Faction, Relationship
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.clone_guard import clone_signals_suppressed
from larpmanager.utils.services.demo import deferred_delete_demo


class TestDeferredDeleteDemo(BaseTestCase):
    """Regression tests for the demo association/user cleanup task.

    A demo association whose sole member gains a stray Membership row via a
    signal fired mid-teardown used to blow up with a ForeignKeyViolation on
    larpmanager_membership. See deferred_delete_demo in
    larpmanager/utils/services/demo.py.
    """

    def setUp(self) -> None:
        """Build a demo association with a full graph (registration, options, characters, factions, relations)."""
        self.demo_type = LarpManagerDemoType.objects.create(
            name="Fantasy", slug="fantasy-teardown", template_association=self.get_association()
        )
        self.demo_association = Association.objects.create(
            name="Demo Org", slug="demo-org-teardown", demo_type=self.demo_type
        )

        demo_user = User.objects.create(username="demo-player", email="demo-player@demo.it")
        self.demo_member = demo_user.member
        self.demo_member.name = "Demo"
        self.demo_member.surname = "Player"
        self.demo_member.save()
        Membership.objects.create(
            member=self.demo_member, association=self.demo_association, status=MembershipStatus.JOINED
        )

        self.event = Event.objects.create(association=self.demo_association, name="Demo Event", slug="demoevent")
        self.run = Run.objects.filter(event=self.event).first()

        self.ticket = RegistrationTicket.objects.filter(event=self.event).first()
        self.question = RegistrationQuestion.objects.create(event=self.event, name="Choice")
        self.option = RegistrationOption.objects.create(event=self.event, question=self.question, name="A")

        self.character_one = self.character(event=self.event, name="Hero")
        self.character_two = self.character(event=self.event, name="Villain")
        Relationship.objects.create(source=self.character_one, target=self.character_two, text="Nemesis")
        self.faction = Faction.objects.create(event=self.event, name="Guild", number=1)
        self.faction.characters.add(self.character_one)

        self.registration = Registration.objects.create(
            run=self.run,
            member=self.demo_member,
            ticket=self.ticket,
            tot_iscr=Decimal("100.00"),
            tot_payed=Decimal("50.00"),
        )

    def test_teardown_completes_without_fk_violation(self) -> None:
        """Full demo graph teardown must not raise, and must leave no orphan rows."""
        deferred_delete_demo.now(self.demo_association.pk)

        assert not Association.objects.filter(pk=self.demo_association.pk).exists()
        assert not User.objects.filter(pk=self.demo_member.user_id).exists()
        assert not Member.objects.filter(pk=self.demo_member.pk).exists()
        assert not Membership.objects.filter(member_id=self.demo_member.pk).exists()

    def test_users_deleted_before_association(self) -> None:
        """Users (and their Members/Memberships) must be gone before the association delete runs.

        Deleting the association first used to leave stale references (or
        trigger signals) that could race with the later, separate User
        delete; deleting users first closes that window.
        """
        demo_user_id = self.demo_member.user_id
        demo_member_id = self.demo_member.pk
        original_delete = Association.delete
        seen = {}

        def wrapped_delete(association_self: Association, *args: object, **kwargs: object) -> object:
            seen["user_gone"] = not User.objects.filter(pk=demo_user_id).exists()
            seen["member_gone"] = not Member.objects.filter(pk=demo_member_id).exists()
            return original_delete(association_self, *args, **kwargs)

        with mock.patch.object(Association, "delete", wrapped_delete):
            deferred_delete_demo.now(self.demo_association.pk)

        assert seen == {"user_gone": True, "member_gone": True}

    def test_signal_handlers_skip_side_effects_when_clone_suppressed(self) -> None:
        """post_delete handlers touched by the association cascade must no-op while signals are suppressed."""
        with mock.patch("larpmanager.models.signals.refresh_character_related_caches") as refresh_char:
            lm_signals.post_delete_character_reset_rels(Character, self.character_one)
        refresh_char.assert_called_once()

        with (
            mock.patch("larpmanager.models.signals.refresh_character_related_caches") as refresh_char,
            clone_signals_suppressed(),
        ):
            lm_signals.post_delete_character_reset_rels(Character, self.character_one)
        refresh_char.assert_not_called()

        with mock.patch("larpmanager.models.signals.publish_registration") as publish:
            lm_signals.post_delete_registration_accounting_cache(Registration, self.registration)
        publish.assert_called_once()

        with (
            mock.patch("larpmanager.models.signals.publish_registration") as publish,
            clone_signals_suppressed(),
        ):
            lm_signals.post_delete_registration_accounting_cache(Registration, self.registration)
        publish.assert_not_called()
