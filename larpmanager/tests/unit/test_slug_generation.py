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

"""Tests for the slug generated when the slug field is left collapsed."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import RequestFactory, override_settings

from larpmanager.forms.association import FirstAssociationForm
from larpmanager.forms.event import OrgaEventForm
from larpmanager.models.association import Association, AssociationSkin
from larpmanager.models.event import Event
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.views.larpmanager import _join_form, get_started_real

SLUG_GENERATED_MARKER = 'class="slug_auto" value="1"'
# Smallest valid GIF image
GIF_BYTES = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00"
    b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def slug_integrity_error(constraint_name: str) -> IntegrityError:
    """Build an IntegrityError as raised by the database driver for a constraint."""
    cause = Exception()
    cause.diag = SimpleNamespace(constraint_name=constraint_name)
    error = IntegrityError(f'duplicate key violates "{constraint_name}"')
    error.__cause__ = cause
    return error


class TestFormSlug(BaseTestCase):
    """Tests for the slug fields of the creation forms."""

    def _event_form(self, association: Association, data: dict) -> OrgaEventForm:
        """Build an event creation form for an association."""
        context = {"association_id": association.id, "features": set()}
        return OrgaEventForm(data=data, context=context)

    def test_event_slug_generated_when_omitted(self) -> None:
        """Keep only lowercase ASCII letters and digits, within the maximum length."""
        form = self._event_form(self.get_association(), {"name": "Prova Larp-2 \u00e0!" + "a" * 60})

        form.is_valid()
        assert "slug" not in form.errors
        assert form.cleaned_data["slug"] == ("provalarp2a" + "a" * 60)[:50]

    def test_event_slug_conflict_suggests_available_slug(self) -> None:
        """Warn the user instead of saving under an unexpected URL, opening the field with a suggestion."""
        association = self.get_association()
        Event.objects.create(name="Taken", slug="moonlight", association=association)
        Event.objects.create(name="Taken", slug="moonlight2", association=association)

        form = self._event_form(association, {"name": "Moonlight"})

        assert not form.is_valid()
        assert "slug" in form.errors
        assert form["slug"].value() == "moonlight3"
        assert 'disabled="disabled"' not in str(form["slug"])
        assert SLUG_GENERATED_MARKER in str(form["slug"])

    def test_event_slug_suggestion_keeps_max_length(self) -> None:
        """Keep the counter within the maximum length."""
        association = self.get_association()
        Event.objects.create(name="Taken", slug="a" * 50, association=association)

        form = self._event_form(association, {"name": "a" * 60})

        assert not form.is_valid()
        assert form["slug"].value() == "a" * 49 + "2"

    def test_event_slug_avoids_reserved_words(self) -> None:
        """Warn when the slug matches a static URL prefix."""
        with override_settings(STATIC_PREFIXES=["moonlight"]):
            form = self._event_form(self.get_association(), {"name": "Moonlight"})

            assert not form.is_valid()

        assert form["slug"].value() == "moonlight2"

    def test_event_name_without_ascii_opens_field(self) -> None:
        """Ask for a slug when none can be built from the name."""
        form = self._event_form(self.get_association(), {"name": "\u65e5\u672c"})

        assert not form.is_valid()
        assert "slug" in form.errors
        assert 'disabled="disabled"' not in str(form["slug"])

    def test_invalid_name_only_reports_name(self) -> None:
        """Avoid a slug error when the name itself is missing."""
        form = self._event_form(self.get_association(), {})

        assert not form.is_valid()
        assert "name" in form.errors
        assert "slug" not in form.errors

    def test_explicit_event_slug_conflict_is_reported(self) -> None:
        """Report conflicts on a slug chosen by the user instead of changing it."""
        association = self.get_association()
        Event.objects.create(name="Taken", slug="moonlight", association=association)

        form = self._event_form(association, {"name": "Other", "slug": "moonlight"})

        assert not form.is_valid()
        assert "slug" in form.errors
        assert SLUG_GENERATED_MARKER not in str(form["slug"])

    def test_slug_matching_name_conflict_suggests_available_slug(self) -> None:
        """Treat the slug auto-filled from the name as generated, even if sent by the opened field."""
        association = self.get_association()
        Event.objects.create(name="Taken", slug="moonlight", association=association)

        form = self._event_form(association, {"name": "Moonlight", "slug": "moonlight"})

        assert not form.is_valid()
        assert form["slug"].value() == "moonlight2"

    def test_slug_suggestion_uses_single_query(self) -> None:
        """Find the first free variant without one query per counter."""
        association = self.get_association()
        for counter in range(2, 12):
            Event.objects.create(name="Taken", slug=f"moonlight{counter}", association=association)
        form = self._event_form(association, {"name": "Moonlight"})
        form.is_valid()

        with self.assertNumQueries(1):
            form.suggest_slug("moonlight")

        assert form["slug"].value() == "moonlight12"

    def test_generated_slug_stays_generated_after_resubmit(self) -> None:
        """Keep following the name when a previous suggestion is sent back and another field fails."""
        association = self.get_association()
        form = self._event_form(association, {"name": "Moonlight", "slug": "moonlight2", "slug_auto": "1"})
        form.is_valid()
        assert SLUG_GENERATED_MARKER in str(form["slug"])

    def test_legacy_slugs_stay_valid_on_models(self) -> None:
        """Keep hyphenated demo slugs and old rows valid outside the creation forms."""
        Association(name="Demo", slug="test-1234").clean_fields(exclude=["skin"])

    def test_slug_suggestion_keeps_uploaded_file_notice(self) -> None:
        """Ask to select again a file the browser will not send back."""
        association = self.get_association()
        Association.objects.filter(pk=association.pk).update(slug="moonlight")
        logo = SimpleUploadedFile("logo.gif", GIF_BYTES, content_type="image/gif")

        form = FirstAssociationForm(data={"name": "Moonlight"}, files={"profile": logo})

        assert not form.is_valid()
        assert "select this file again" in form.errors["profile"][0]

    def test_unusable_name_keeps_uploaded_file_notice(self) -> None:
        """Ask to select a file again when the slug cannot be built from the name."""
        logo = SimpleUploadedFile("logo.gif", GIF_BYTES, content_type="image/gif")

        form = FirstAssociationForm(data={"name": "\u65e5\u672c"}, files={"profile": logo})

        assert not form.is_valid()
        assert "select this file again" in form.errors["profile"][0]

    def test_explicit_slug_conflict_keeps_uploaded_file_notice(self) -> None:
        """Ask to select a file again when a chosen slug is taken."""
        association = self.get_association()
        Association.objects.filter(pk=association.pk).update(slug="moonlight")
        logo = SimpleUploadedFile("logo.gif", GIF_BYTES, content_type="image/gif")

        form = FirstAssociationForm(data={"name": "Other", "slug": "moonlight"}, files={"profile": logo})

        assert not form.is_valid()
        assert "select this file again" in form.errors["profile"][0]

    def test_association_slug_conflict_suggests_available_slug(self) -> None:
        """Warn the user when another association already uses the slug."""
        association = self.get_association()
        Association.objects.filter(pk=association.pk).update(slug="moonlight")

        form = FirstAssociationForm(data={"name": "Moonlight"})

        assert not form.is_valid()
        assert "slug" in form.errors
        assert form["slug"].value() == "moonlight2"

    def test_association_slug_avoids_reserved_subdomains(self) -> None:
        """Reject reserved subdomains, generated or chosen by the user."""
        generated = FirstAssociationForm(data={"name": "WWW"})
        explicit = FirstAssociationForm(data={"name": "Other", "slug": "www"})

        assert not generated.is_valid()
        assert generated["slug"].value() == "www2"
        assert not explicit.is_valid()
        assert "slug" in explicit.errors

    def test_association_slug_avoids_main_domains(self) -> None:
        """Protect the domain root, that would load an organization named after the domain."""
        # Explicit pk, as fixtures use hardcoded low ids
        max_id = AssociationSkin.objects.order_by("-id").first().id
        AssociationSkin.objects.create(id=max_id + 1, name="Moonlight", domain="moonlight.com")

        form = FirstAssociationForm(data={"name": "Moon Light"})

        assert not form.is_valid()
        assert form["slug"].value() == "moonlight2"

    def test_association_name_needs_letters_or_numbers(self) -> None:
        """Reject blank-looking names, while accepting non-Latin ones."""
        assert "name" in FirstAssociationForm(data={"name": "***"}).errors
        assert "name" in FirstAssociationForm(data={"name": "\u200b"}).errors
        assert "name" not in FirstAssociationForm(data={"name": "\u65e5\u672c"}).errors
        assert "data-invalid-message" in str(FirstAssociationForm()["name"])

    def test_concurrent_slug_conflict_is_reported(self) -> None:
        """Report as a form error a slug taken after validation."""
        form = FirstAssociationForm(data={"name": "Moonlight"})
        form.is_valid()

        conflict = slug_integrity_error("unique_association_without_optional")

        with patch.object(form, "save", side_effect=conflict):
            assert form.save_unique_slug() is None

        assert "slug" in form.errors
        assert form["slug"].value() == "moonlight2"
        assert 'disabled="disabled"' not in str(form["slug"])

    def test_concurrent_conflict_on_suggestion_restarts_from_name(self) -> None:
        """Number the suggestion from the name, not from the suggestion that lost the race."""
        form = FirstAssociationForm(data={"name": "Moonlight", "slug": "moonlight2", "slug_auto": "1"})
        form.is_valid()
        association = self.get_association()
        Association.objects.filter(pk=association.pk).update(slug="moonlight2")

        with patch.object(form, "save", side_effect=slug_integrity_error("unique_association_without_optional")):
            assert form.save_unique_slug() is None

        assert form["slug"].value() == "moonlight3"

    def test_concurrent_conflict_keeps_chosen_slug(self) -> None:
        """Leave a slug chosen by the user as it is, and not marked as generated."""
        form = FirstAssociationForm(data={"name": "Moonlight", "slug": "mygroup"})
        form.is_valid()

        with patch.object(form, "save", side_effect=slug_integrity_error("unique_association_without_optional")):
            assert form.save_unique_slug() is None

        assert form.errors["slug"] == ["Slug already used!"]
        assert form["slug"].value() == "mygroup"
        assert SLUG_GENERATED_MARKER not in str(form["slug"])

    def test_unrelated_integrity_error_is_raised(self) -> None:
        """Let errors of other constraints through."""
        form = FirstAssociationForm(data={"name": "Moonlight"})
        form.is_valid()

        with (
            patch.object(form, "save", side_effect=slug_integrity_error("other")),
            pytest.raises(IntegrityError),
        ):
            form.save_unique_slug()

    def test_explicit_association_slug_conflict_is_reported(self) -> None:
        """Report conflicts on a slug chosen by the user instead of changing it."""
        association = self.get_association()
        Association.objects.filter(pk=association.pk).update(slug="moonlight")

        form = FirstAssociationForm(data={"name": "Other", "slug": "moonlight"})

        assert not form.is_valid()
        assert form.errors["slug"] == ["Slug already used!"]

    def test_explicit_slug_rejects_characters_outside_run_url_format(self) -> None:
        """Reject separators the model validator allows, as run URLs split on hyphens."""
        association_form = FirstAssociationForm(data={"name": "Other", "slug": "my-org"})
        event_form = self._event_form(self.get_association(), {"name": "Other", "slug": "my_event"})

        assert not association_form.is_valid()
        assert "slug" in association_form.errors
        assert not event_form.is_valid()
        assert "slug" in event_form.errors

    def _join(
        self,
        member: object,
        token: str = "",
        name: str = "Moonlight",
    ) -> tuple[Association | None, bool]:
        """Submit the organization creation form."""
        data = {"name": name, "payment_currency": "e", "timezone": "Europe/Rome", "join_token": token}
        request = RequestFactory().post("/join", data)
        request.association = {"skin_id": self.get_association().skin_id}
        return _join_form({"member": member}, request)

    def test_repeated_join_submit_returns_same_organization(self) -> None:
        """Lead a double submit to the organization created by the first one."""
        member = self.get_member()
        token = str(uuid.uuid4())

        created, is_new = self._join(member, token)
        repeated, repeated_is_new = self._join(member, token)

        assert is_new
        assert not repeated_is_new
        assert repeated == created
        assert Association.objects.filter(name="Moonlight").count() == 1

    def test_repeated_join_submit_warns_organization_exists(self) -> None:
        """Tell the user no new organization was created when the same form is sent again."""
        association = self.get_association()
        request = RequestFactory().post("/join")
        request.user = self.get_member().user

        with (
            patch("larpmanager.views.larpmanager.get_lm_contact", return_value={}),
            patch("larpmanager.views.larpmanager._join_form", return_value=(association, False)),
            patch("larpmanager.views.larpmanager.messages") as mocked_messages,
        ):
            response = get_started_real(request)

        assert response.status_code == 302
        mocked_messages.warning.assert_called_once()
        assert association.name in mocked_messages.warning.call_args.args[1]
        mocked_messages.success.assert_not_called()

    def test_new_join_form_with_same_name_is_not_a_repeat(self) -> None:
        """Treat a new rendering of the form as a new request, reporting the taken slug."""
        member = self.get_member()
        created, _unused = self._join(member, str(uuid.uuid4()))

        repeated, is_new = self._join(member, str(uuid.uuid4()))

        assert created
        assert repeated is None
        assert not is_new

    def test_join_name_with_nul_character_is_a_form_error(self) -> None:
        """Report through the form a name the database would refuse."""
        association, is_new = self._join(self.get_member(), str(uuid.uuid4()), name="abc\x00")

        assert association is None
        assert not is_new

    def test_failed_join_setup_leaves_no_organization(self) -> None:
        """Roll back the organization when its setup fails, so that a retry finds its URL free."""
        with (
            patch("larpmanager.views.larpmanager.save_single_config", side_effect=RuntimeError),
            pytest.raises(RuntimeError),
        ):
            self._join(self.get_member())

        assert not Association.objects.filter(slug="moonlight").exists()
