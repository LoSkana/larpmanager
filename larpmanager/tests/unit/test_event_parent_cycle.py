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

"""Tests for campaign parent loops: form validation and the event text fallback."""

from django.core.cache import cache

from larpmanager.cache.event_text import get_event_text
from larpmanager.forms.event import OrgaEventForm
from larpmanager.models.event import Event, EventTextType
from larpmanager.tests.unit.base import BaseTestCase


class TestEventParentCycle(BaseTestCase):
    """An event cannot become its own campaign ancestor."""

    def _edit_form(self, event: Event, parent: Event) -> OrgaEventForm:
        """Build an event edit form selecting the given parent."""
        context = {"association_id": event.association_id, "features": {"campaign"}}
        data = {"name": event.name, "max_pg": 0, "max_waiting": 0, "max_filler": 0, "parent": parent.pk}
        return OrgaEventForm(data=data, instance=event, context=context)

    def test_event_text_self_parent_returns_empty(self) -> None:
        """An event that is its own parent yields an empty text instead of recursing."""
        event = self.create_event(name="Loop")
        Event.objects.filter(pk=event.pk).update(parent_id=event.pk)
        cache.clear()

        assert get_event_text(event.pk, EventTextType.REGISTRATION_APPROVAL, "en") == ""

    def test_event_text_two_event_loop_returns_empty(self) -> None:
        """A loop through two events yields an empty text instead of recursing."""
        first = self.create_event(name="First")
        second = self.create_event(name="Second", parent=first)
        Event.objects.filter(pk=first.pk).update(parent_id=second.pk)
        cache.clear()

        assert get_event_text(first.pk, EventTextType.REGISTRATION_APPROVAL, "en") == ""

    def test_form_rejects_self_parent(self) -> None:
        """The event itself is not a valid parent, nor a choice of the widget."""
        event = self.create_event(name="Self")
        self.create_event(name="Other")
        form = self._edit_form(event, event)

        assert not form.fields["parent"].queryset.filter(pk=event.pk).exists()
        assert not form.is_valid()
        assert "parent" in form.errors

    def test_form_rejects_parent_with_parent(self) -> None:
        """A parent already in a campaign is rejected, blocking A -> B -> A loops."""
        event = self.create_event(name="Root")
        child = self.create_event(name="Child", parent=event)
        self.create_event(name="Other")
        form = self._edit_form(event, child)

        assert not form.is_valid()
        assert "parent" in form.errors

    def test_form_accepts_valid_parent(self) -> None:
        """A top-level event of the same association is a valid parent."""
        event = self.create_event(name="Chapter")
        parent = self.create_event(name="Campaign")
        form = self._edit_form(event, parent)

        form.is_valid()
        assert "parent" not in form.errors
