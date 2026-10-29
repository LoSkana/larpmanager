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

"""Tests for the member select of the orga token form."""

from django.utils import timezone

from larpmanager.forms.accounting import OrgaTokenForm
from larpmanager.tests.unit.base import BaseTestCase


class TestOrgaTokenFormMember(BaseTestCase):
    """Test cases for the initial member shown when editing a token assignment"""

    def _form(self, **kwargs: object) -> OrgaTokenForm:
        run = self.get_run()
        return OrgaTokenForm(context={"run": run, "event": run.event, "features": {}}, **kwargs)

    def _token(self, member: object) -> object:
        token = self.other_item_token(member=member)
        token.save()
        return token

    def test_new_token_lists_only_registered_members(self) -> None:
        """Creation keeps the member choices restricted to members signed up to the run"""
        registered = self.create_member()
        other = self.create_member(user=self.create_user(username="other", email="other@example.com"))
        self.create_registration(member=registered)

        queryset = self._form().fields["member"].queryset
        assert queryset.filter(pk=registered.pk).exists()
        assert not queryset.filter(pk=other.pk).exists()

    def test_edit_shows_registered_member(self) -> None:
        """Editing renders the saved member as the selected option"""
        member = self.create_member()
        self.create_registration(member=member)
        form = self._form(instance=self._token(member))

        assert f'<option value="{member.pk}" selected>' in str(form["member"])

    def test_edit_shows_member_with_cancelled_registration(self) -> None:
        """Editing still renders the saved member when its registration was cancelled"""
        member = self.create_member()
        self.create_registration(member=member, cancellation_date=timezone.now())
        form = self._form(instance=self._token(member))

        assert f'<option value="{member.pk}" selected>' in str(form["member"])

    def test_edit_keeps_member_with_cancelled_registration_on_save(self) -> None:
        """Saving an edit without changing the member is valid even if no longer registered"""
        member = self.create_member()
        self.create_registration(member=member, cancellation_date=timezone.now())
        token = self._token(member)
        data = {"member": member.pk, "value": "7", "descr": token.descr}

        form = self._form(instance=token, data=data)

        assert form.is_valid(), form.errors
        assert form.save().member_id == member.pk
