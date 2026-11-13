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

"""Unit tests for the role invitation email."""

from datetime import date

from django.core import mail
from django.utils.translation import get_language, override

from larpmanager.mail.base import _add_member_event_role, _latest_event_run, send_role_invite_email
from larpmanager.models.access import AssociationRole, EventRole, RoleInvite
from larpmanager.models.event import Run
from larpmanager.models.miscellanea import EmailContent, EmailRecipient
from larpmanager.tests.unit.base import BaseTestCase


class TestRoleInviteEmail(BaseTestCase):
    """Tests for the delivery and the tracking of role invitations."""

    def test_event_role_invite_shows_event_and_tracks_run(self):
        """Event role invites name the event and are stored on the run."""
        association = self.get_association()
        event = self.get_event()
        run = self.get_run()
        role = EventRole.objects.create(event=event, number=7, name="Staff")
        invite = RoleInvite.objects.create(
            email="invited@example.org", association=association, event=event, event_role=role
        )

        send_role_invite_email(invite, run)

        content = EmailContent.objects.get(subj__contains="invited")
        assert content.run_id == run.id
        assert content.association_id == association.id
        assert event.name in content.subj
        assert EmailRecipient.objects.get(email_content=content).sent is not None
        assert mail.outbox[-1].to == ["invited@example.org"]
        assert invite.token in mail.outbox[-1].alternatives[0].content

    def test_association_role_invite_has_no_run(self):
        """Association role invites are stored on the association only."""
        association = self.get_association()
        role = AssociationRole.objects.create(association=association, number=7, name="Staff")
        invite = RoleInvite.objects.create(email="invited@example.org", association=association, association_role=role)

        send_role_invite_email(invite)

        content = EmailContent.objects.get(subj__contains="invited")
        assert content.run_id is None
        assert content.association_id == association.id
        assert EmailRecipient.objects.get(email_content=content).sent is not None

    def test_invite_uses_language_of_registered_member(self):
        """Invites to a known address follow the member language, without touching the active one."""
        association = self.get_association()
        member = self.get_member()
        member.language = "it"
        member.save()
        role = AssociationRole.objects.create(association=association, number=7, name="Staff")
        invite = RoleInvite.objects.create(email=member.email.upper(), association=association, association_role=role)

        with override("en"):
            send_role_invite_email(invite)
            assert get_language() == "en"

        recipient = EmailRecipient.objects.get(email_content__association=association, recipient=member.email)
        assert recipient.language_code == "it"
        assert "Sei stato invitato" in recipient.email_content.subj

    def test_invite_to_unknown_address_is_in_english(self):
        """Invites to an address without an account are sent in English."""
        association = self.get_association()
        role = AssociationRole.objects.create(association=association, number=7, name="Staff")
        invite = RoleInvite.objects.create(email="invited@example.org", association=association, association_role=role)

        with override("it"):
            send_role_invite_email(invite)

        assert "You have been invited" in EmailContent.objects.get(subj__contains="invited").subj


class TestEventRoleApprovalEmail(BaseTestCase):
    """Tests for the mail sent when a member is added to an event role."""

    def test_approval_is_tied_to_latest_run_with_valid_link(self):
        """Approval mails are stored on the latest run, and carry a well formed link."""
        association = self.get_association()
        event = self.get_event()
        Run.objects.filter(event=event).update(end=date(2025, 1, 1))
        latest = self.create_run(event=event, number=2, end=date(2030, 1, 1))
        self.create_run(event=event, number=3, end=None)
        role = EventRole.objects.create(event=event, number=7, name="Staff")

        with override("en"):
            _add_member_event_role([], role, self.get_member().pk, association.id, _latest_event_run(event.id))

        content = EmailContent.objects.get(subj__contains=event.name)
        assert content.run_id == latest.id
        assert "<a href='https://" in content.body

    def test_approval_without_runs_falls_back_to_event(self):
        """Events without runs still send the mail, on the association only."""
        association = self.get_association()
        event = self.get_event()
        Run.objects.filter(event=event).delete()
        role = EventRole.objects.create(event=event, number=7, name="Staff")

        _add_member_event_role([], role, self.get_member().pk, association.id, _latest_event_run(event.id))

        content = EmailContent.objects.get(subj__contains=event.name)
        assert content.run_id is None
        assert content.association_id == association.id


class TestFirstRoleEmail(BaseTestCase):
    """Tests for the welcome mail sent to members receiving their first staff role."""

    first_role_subject = "Welcome to the staff"

    def _staff_association(self):
        """Return the association, making sure it has a staff member besides the new one."""
        association = self.get_association()
        staff_role = AssociationRole.objects.create(association=association, number=8, name="Helper")
        staff_role.members.add(self.get_member())
        EmailContent.objects.all().delete()
        return association

    def test_first_event_role_sends_guide_links(self):
        """A member without roles receives the welcome mail with the guide links."""
        self._staff_association()
        role = EventRole.objects.create(event=self.get_event(), number=7, name="Staff")
        member = self.create_member(self.create_user(username="newstaff", email="newstaff@example.org"))
        with override("en"):
            role.members.add(member)

        content = EmailContent.objects.get(subj__contains=self.first_role_subject)
        assert "https://larpmanager.com/guide/first/" in content.body
        assert "https://larpmanager.com/guides/" in content.body

    def test_second_role_sends_no_welcome(self):
        """A member who already holds a role in the association gets no welcome mail."""
        association = self._staff_association()
        member = self.create_member(self.create_user(username="newstaff", email="newstaff@example.org"))
        previous_role = EventRole.objects.create(event=self.get_event(), number=7, name="Staff")
        previous_role.members.add(member)
        role = AssociationRole.objects.create(association=association, number=9, name="Treasurer")
        EmailContent.objects.all().delete()
        with override("en"):
            role.members.add(member)

        assert not EmailContent.objects.filter(subj__contains=self.first_role_subject).exists()

    def test_sole_staff_member_gets_no_welcome(self):
        """The only staff member of an association (its creator) gets no welcome mail."""
        association = self.get_association()
        AssociationRole.members.through.objects.filter(associationrole__association=association).delete()
        EventRole.members.through.objects.filter(eventrole__event__association=association).delete()
        role = AssociationRole.objects.create(association=association, number=9, name="Treasurer")
        member = self.get_member()
        EmailContent.objects.all().delete()
        with override("en"):
            role.members.add(member)

        assert not EmailContent.objects.filter(subj__contains=self.first_role_subject).exists()
