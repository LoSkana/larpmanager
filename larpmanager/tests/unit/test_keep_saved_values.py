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

"""Tests for scoped select fields keeping the values saved on the instance."""

from larpmanager.forms.accounting import ExeTokenForm
from larpmanager.forms.event import OrgaEventRoleForm
from larpmanager.models.access import EventRole
from larpmanager.models.member import MembershipStatus
from larpmanager.tests.unit.base import BaseTestCase


class TestKeepSavedValues(BaseTestCase):
    """Test cases for edit forms whose saved values fall outside the widget queryset"""

    def _revoked_member(self, username: str = "revoked") -> object:
        member = self.create_member(user=self.create_user(username=username, email=f"{username}@example.com"))
        member.membership.status = MembershipStatus.REWOKED
        member.membership.save()
        return member

    def _accepted_member(self, username: str = "accepted") -> object:
        member = self.create_member(user=self.create_user(username=username, email=f"{username}@example.com"))
        member.membership.status = MembershipStatus.ACCEPTED
        member.membership.save()
        return member

    def _token_form(self, **kwargs: object) -> ExeTokenForm:
        context = {"association_id": self.get_association().id, "tokens_name": "Tokens", "features": {}}
        return ExeTokenForm(context=context, **kwargs)

    def test_new_exe_token_excludes_revoked_member(self) -> None:
        """Creation keeps the member choices restricted to valid memberships"""
        revoked = self._revoked_member()
        accepted = self._accepted_member()

        queryset = self._token_form().fields["member"].queryset
        assert queryset.filter(pk=accepted.pk).exists()
        assert not queryset.filter(pk=revoked.pk).exists()

    def test_edit_exe_token_shows_revoked_member(self) -> None:
        """Editing renders the saved member as selected even after the membership was revoked"""
        revoked = self._revoked_member()
        token = self.other_item_token(member=revoked)
        token.save()

        form = self._token_form(instance=token)

        assert f'<option value="{revoked.pk}" selected>' in str(form["member"])
        assert form.fields["member"].queryset.filter(pk=self._accepted_member().pk).exists()

    def test_edit_role_keeps_revoked_members(self) -> None:
        """Editing a role keeps every saved member, also the ones whose membership was revoked"""
        revoked = self._revoked_member()
        accepted = self._accepted_member()
        role = EventRole.objects.create(event=self.get_event(), name="Staff", number=2)
        role.members.add(revoked, accepted)
        context = {"association_id": self.get_association().id, "event": role.event, "features": {}}

        form = OrgaEventRoleForm(instance=role, context=context)
        html = str(form["members"])

        assert f'<option value="{revoked.pk}" selected>' in html
        assert f'<option value="{accepted.pk}" selected>' in html
