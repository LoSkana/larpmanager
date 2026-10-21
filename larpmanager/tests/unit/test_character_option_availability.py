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

"""Unit tests for the availability of limited character options, counted on the characters assigned to the run."""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from larpmanager.cache.registration_counts import get_registration_counts
from larpmanager.forms.base import get_question_key
from larpmanager.forms.character import CharacterForm
from larpmanager.mail.registration import notify_character_full_options
from larpmanager.models.event import Event
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.member import NotificationType
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character, CharacterConfig, CharacterStatus
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.registrations.characters import (
    check_assign_character,
    get_character_full_options,
    get_characters_full_options,
)


@pytest.mark.django_db
class TestCharacterOptionAvailability(BaseTestCase):
    """Check that only characters assigned to the run take the spots of limited options."""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.run = self.get_run()
        self.event = self.run.event

        WritingQuestion.objects.get_or_create(
            event=self.event,
            applicable=QuestionApplicable.CHARACTER,
            typ=WritingQuestionType.NAME,
            defaults={"name": "Name", "order": 1},
        )
        self.origin = WritingQuestion.objects.create(
            event=self.event,
            applicable=QuestionApplicable.CHARACTER,
            typ=BaseQuestionType.SINGLE,
            status=QuestionStatus.OPTIONAL,
            name="Origin",
            order=2,
        )
        self.bunker = WritingOption.objects.create(
            event=self.event, question=self.origin, name="Bunker", order=1, max_available=1
        )
        self.wasteland = WritingOption.objects.create(event=self.event, question=self.origin, name="Wasteland", order=2)

        self.member_count = 0

    def _member(self) -> object:
        self.member_count += 1
        user = self.create_user(username=f"avail{self.member_count}", email=f"avail{self.member_count}@test.it")
        return self.create_member(user)

    def _character(self, name: str, option: WritingOption | None = None, player: object | None = None) -> Character:
        character = self.character(event=self.event, name=name, player=player, status=CharacterStatus.CREATION)
        if option:
            WritingChoice.objects.create(question=option.question, option=option, element_id=character.id)
        return character

    def _assign(self, character: Character, run: object | None = None, member: object | None = None) -> object:
        registration = self.create_registration(member=member or self._member(), run=run or self.run)
        RegistrationCharacterRel.objects.create(registration=registration, character=character)
        return registration

    def _counts(self, run: object | None = None) -> dict:
        run = run or self.run
        return get_registration_counts(run.id, run.event_id, reset_cache=True)

    def test_unassigned_character_not_counted(self) -> None:
        self._character("Free", self.bunker)

        assert self._counts().get(f"option_char_{self.bunker.id}", 0) == 0

    def test_assigned_character_counted(self) -> None:
        self._assign(self._character("Taken", self.bunker))

        assert self._counts()[f"option_char_{self.bunker.id}"] == 1

    def test_character_of_other_run_not_counted(self) -> None:
        # The slug of the second run is built from the event one
        Event.objects.filter(pk=self.event.pk, slug__isnull=True).update(slug="avail")
        self.event.refresh_from_db()
        other_run = self.create_run(event=self.event, number=2)
        self._assign(self._character("Elsewhere", self.bunker), run=other_run)

        assert self._counts().get(f"option_char_{self.bunker.id}", 0) == 0
        assert self._counts(other_run)[f"option_char_{self.bunker.id}"] == 1

    def test_cancelled_registration_not_counted(self) -> None:
        registration = self._assign(self._character("Gone", self.bunker))
        registration.cancellation_date = timezone.now()
        registration.save()

        assert self._counts().get(f"option_char_{self.bunker.id}", 0) == 0

    def test_full_options_detected(self) -> None:
        self._assign(self._character("Taken", self.bunker))
        candidate = self._character("Candidate", self.bunker)

        assert get_character_full_options(self.run.id, candidate.id) == [self.bunker]

    def test_full_options_ignore_character_itself(self) -> None:
        character = self._character("Taken", self.bunker)
        self._assign(character)

        assert get_character_full_options(self.run.id, character.id) == []

    def test_full_options_ignore_replaced_character(self) -> None:
        played = self._character("Played", self.bunker)
        self._assign(played)
        candidate = self._character("Candidate", self.bunker)

        assert get_character_full_options(self.run.id, candidate.id, [played.id]) == []

    def test_batch_full_options_per_character(self) -> None:
        taken = self._character("Taken", self.bunker)
        self._assign(taken)
        candidate = self._character("Candidate", self.bunker)
        free = self._character("Free", self.wasteland)

        full_options = get_characters_full_options(self.run.id, [taken.id, candidate.id, free.id])

        assert full_options == {candidate.id: [self.bunker]}

    def test_unlimited_option_never_full(self) -> None:
        self._assign(self._character("Taken", self.wasteland))
        candidate = self._character("Candidate", self.wasteland)

        assert get_character_full_options(self.run.id, candidate.id) == []

    def _form(self, character: Character, option: WritingOption, registration: object | None = None) -> CharacterForm:
        context = {
            "event": self.event,
            "run": self.run,
            "member": character.player or self.get_member(),
            "features": {"character", "user_character"},
            "association_id": self.event.association_id,
            "elementTyp": Character,
        }
        if registration:
            context["registration"] = registration
        data = {"name": character.name, get_question_key(self.origin): str(option.uuid)}
        return CharacterForm(data, instance=character if character.pk else None, context=context)

    def test_unassigned_character_can_pick_full_option(self) -> None:
        self._assign(self._character("Taken", self.bunker))

        form = self._form(self._character("Free"), self.bunker)

        assert form.is_valid(), form.errors

    def test_registered_player_cannot_pick_full_option(self) -> None:
        # the character of a registered player is auto-assigned on save, so it takes a spot
        self._assign(self._character("Taken", self.bunker))
        member = self._member()
        registration = self.create_registration(member=member, run=self.run)

        form = self._form(self._character("Free", player=member), self.bunker, registration)

        assert not form.is_valid()

    def test_player_with_more_characters_than_slots_can_pick_full_option(self) -> None:
        # with more candidates than free slots the choice is left to the player, nothing is auto-assigned
        self._assign(self._character("Taken", self.bunker))
        member = self._member()
        registration = self.create_registration(member=member, run=self.run)
        self._character("Other", player=member)

        form = self._form(self._character("Free", player=member), self.bunker, registration)

        assert form.is_valid(), form.errors

    def test_new_character_without_free_slots_can_pick_full_option(self) -> None:
        self._assign(self._character("Taken", self.bunker))
        member = self._member()
        registration = self._assign(self._character("Played", player=member), member=member)

        form = self._form(Character(event=self.event, name="New", player=member), self.bunker, registration)

        assert form.is_valid(), form.errors

    def test_new_character_with_free_slot_cannot_pick_full_option(self) -> None:
        self._assign(self._character("Taken", self.bunker))
        member = self._member()
        registration = self.create_registration(member=member, run=self.run)

        form = self._form(Character(event=self.event, name="New", player=member), self.bunker, registration)

        assert not form.is_valid()

    def test_assigned_character_cannot_pick_full_option(self) -> None:
        self._assign(self._character("Taken", self.bunker))
        character = self._character("Played", self.wasteland)
        self._assign(character)

        form = self._form(character, self.bunker)

        assert not form.is_valid()

    def test_auto_assign_skips_character_with_full_options(self) -> None:
        self._assign(self._character("Taken", self.bunker))
        member = self._member()
        candidate = self._character("Candidate", self.bunker, player=member)
        registration = self.create_registration(member=member, run=self.run)

        context = {
            "event": self.event,
            "run": self.run,
            "member": member,
            "registration": registration,
            "features": {"character", "user_character"},
        }
        blocked = check_assign_character(context)

        assert blocked == [(candidate, [self.bunker])]
        assert not RegistrationCharacterRel.objects.filter(registration=registration).exists()

    @patch("larpmanager.mail.registration.my_send_digest_email")
    @patch("larpmanager.mail.registration.get_event_organizers")
    @patch("larpmanager.mail.registration.my_send_mail")
    def test_notify_without_request_emails_player_and_organizers(
        self, mock_send_mail: object, mock_organizers: object, mock_digest: object
    ) -> None:
        organizer = self._member()
        mock_organizers.return_value = [organizer]
        member = self._member()
        candidate = self._character("Candidate", self.bunker, player=member)
        registration = self.create_registration(member=member, run=self.run)

        notify_character_full_options(registration, candidate, [self.bunker])

        mock_send_mail.assert_called_once()
        assert mock_send_mail.call_args.args[2] == member
        mock_digest.assert_called_once()
        assert mock_digest.call_args.kwargs["member"] == organizer
        assert mock_digest.call_args.kwargs["notification_type"] == NotificationType.CHARACTER_OPTION_FULL

    @patch("larpmanager.mail.registration.my_send_digest_email")
    @patch("larpmanager.mail.registration.get_event_organizers", return_value=[])
    @patch("larpmanager.mail.registration.my_send_mail")
    @patch("larpmanager.mail.registration.messages")
    def test_notify_with_request_shows_error_without_player_email(
        self, mock_messages: object, mock_send_mail: object, mock_organizers: object, mock_digest: object
    ) -> None:
        member = self._member()
        candidate = self._character("Candidate", self.bunker, player=member)
        registration = self.create_registration(member=member, run=self.run)

        notify_character_full_options(registration, candidate, [self.bunker], request=object())

        mock_messages.error.assert_called_once()
        mock_send_mail.assert_not_called()

    @patch("larpmanager.mail.registration.my_send_digest_email")
    @patch("larpmanager.mail.registration.get_event_organizers")
    @patch("larpmanager.mail.registration.my_send_mail")
    def test_notify_emails_only_once_for_same_options(
        self, mock_send_mail: object, mock_organizers: object, mock_digest: object
    ) -> None:
        mock_organizers.return_value = [self._member()]
        member = self._member()
        candidate = self._character("Candidate", self.bunker, player=member)
        registration = self.create_registration(member=member, run=self.run)
        limited = WritingOption.objects.create(
            event=self.event, question=self.origin, name="Vault", order=3, max_available=1
        )

        notify_character_full_options(registration, candidate, [self.bunker])
        notify_character_full_options(registration, candidate, [self.bunker])
        assert mock_send_mail.call_count == 1
        assert mock_digest.call_count == 1

        # A different set of full options is notified again
        notify_character_full_options(registration, candidate, [self.bunker, limited])
        assert mock_send_mail.call_count == 2
        assert mock_digest.call_count == 2

    @patch("larpmanager.mail.registration.my_send_digest_email")
    @patch("larpmanager.mail.registration.get_event_organizers", return_value=[])
    @patch("larpmanager.mail.registration.my_send_mail")
    def test_assignment_clears_notified_options(
        self, mock_send_mail: object, mock_organizers: object, mock_digest: object
    ) -> None:
        member = self._member()
        candidate = self._character("Candidate", self.bunker, player=member)
        registration = self.create_registration(member=member, run=self.run)
        notify_character_full_options(registration, candidate, [self.bunker])
        assert CharacterConfig.objects.filter(character=candidate, name=f"full_options_notified_{self.run.id}").exists()

        RegistrationCharacterRel.objects.create(registration=registration, character=candidate)

        assert not CharacterConfig.objects.filter(
            character=candidate, name=f"full_options_notified_{self.run.id}"
        ).exists()
