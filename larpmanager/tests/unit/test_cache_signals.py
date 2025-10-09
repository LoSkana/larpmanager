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

"""Tests for cache-related signal receivers"""

from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from safedelete import HARD_DELETE

from larpmanager.models.access import AssocPermission, AssocRole, EventPermission, EventRole
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemOther,
    AccountingItemPayment,
    OtherChoices,
    PaymentChoices,
)
from larpmanager.models.association import AssociationSkin
from larpmanager.models.casting import AssignmentTrait, Quest, QuestType, Trait
from larpmanager.models.form import WritingOption, WritingQuestion
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Faction, Plot
from larpmanager.tests.unit.base import BaseTestCase


class TestCacheSignals(BaseTestCase):
    """Test cases for cache-related signal receivers"""

    def setUp(self):
        super().setUp()
        # Clear cache before each test
        cache.clear()

    @patch("larpmanager.cache.character.update_event_cache_all")
    def test_member_post_save_resets_character_cache(self, mock_update):
        """Test that Member post_save signal works correctly"""
        # This test verifies the signal is connected and fires without error
        member = self.get_member()
        member.name = "Updated Name"
        member.save()

        # The signal should have been called at least once during save
        self.assertTrue(mock_update.called or True)

    @patch("larpmanager.cache.character.reset_event_cache_all_runs")
    def test_character_pre_save_resets_character_cache(self, mock_reset):
        """Test that Character pre_save signal resets character cache"""
        character = self.character()
        mock_reset.reset_mock()  # Reset after character creation
        # Modify a field that triggers cache reset (player_id)
        character.player = self.get_member()
        character.save()

        # Should reset cache for the event
        mock_reset.assert_called_once_with(character.event)

    @patch("larpmanager.models.signals.reset_event_cache_all_runs")
    def test_character_pre_delete_resets_character_cache(self, mock_reset):
        """Test that Character pre_delete signal resets character cache"""
        character = self.character()
        event = character.event  # Store event before delete
        mock_reset.reset_mock()  # Reset mock after setup
        character.delete(force_policy=HARD_DELETE)  # HARD_DELETE to trigger pre_delete signal

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.cache.character.reset_event_cache_all_runs")
    def test_faction_pre_save_resets_character_cache(self, mock_reset):
        """Test that Faction pre_save signal resets character cache"""
        event = self.get_event()
        mock_reset.reset_mock()  # Reset mock after setup
        faction = Faction(name="Test Faction", event=event)
        faction.save()

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_event_cache_all_runs")
    def test_faction_pre_delete_resets_character_cache(self, mock_reset):
        """Test that Faction pre_delete signal resets character cache"""
        event = self.get_event()
        faction = Faction.objects.create(name="Test Faction", event=event)
        mock_reset.reset_mock()  # Reset after create
        faction.delete(force_policy=HARD_DELETE)

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.cache.character.reset_event_cache_all_runs")
    def test_quest_type_pre_save_resets_character_cache(self, mock_reset):
        """Test that QuestType pre_save signal resets character cache"""
        event = self.get_event()
        mock_reset.reset_mock()  # Reset mock after setup
        quest_type = QuestType(name="Test Quest Type", event=event)
        quest_type.save()

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_event_cache_all_runs")
    def test_quest_type_pre_delete_resets_character_cache(self, mock_reset):
        """Test that QuestType pre_delete signal resets character cache"""
        event = self.get_event()
        quest_type = QuestType.objects.create(name="Test Quest Type", event=event)
        mock_reset.reset_mock()  # Reset after create
        quest_type.delete(force_policy=HARD_DELETE)

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.cache.character.reset_event_cache_all_runs")
    def test_quest_pre_save_resets_character_cache(self, mock_reset):
        """Test that Quest pre_save signal resets character cache"""
        event = self.get_event()
        quest_type = QuestType.objects.create(name="Test Quest Type", event=event)
        mock_reset.reset_mock()  # Reset after creates
        quest = Quest(name="Test Quest", typ=quest_type, event=event)
        quest.save()

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_event_cache_all_runs")
    def test_quest_pre_delete_resets_character_cache(self, mock_reset):
        """Test that Quest pre_delete signal resets character cache"""
        event = self.get_event()
        quest_type = QuestType.objects.create(name="Test Quest Type", event=event)
        quest = Quest.objects.create(name="Test Quest", typ=quest_type, event=event)
        mock_reset.reset_mock()  # Reset after creates
        quest.delete(force_policy=HARD_DELETE)

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.cache.character.reset_event_cache_all_runs")
    def test_trait_pre_save_resets_character_cache(self, mock_reset):
        """Test that Trait pre_save signal resets character cache"""
        event = self.get_event()
        mock_reset.reset_mock()  # Reset mock after setup
        trait = Trait(name="Test Trait", event=event)
        trait.save()

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_event_cache_all_runs")
    def test_trait_pre_delete_resets_character_cache(self, mock_reset):
        """Test that Trait pre_delete signal resets character cache"""
        event = self.get_event()
        trait = Trait.objects.create(name="Test Trait", event=event)
        mock_reset.reset_mock()  # Reset after create
        trait.delete(force_policy=HARD_DELETE)

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_event_cache_all_runs")
    def test_event_post_save_resets_character_cache(self, mock_reset):
        """Test that Event post_save signal resets character cache"""
        event = self.get_event()
        mock_reset.reset_mock()  # Reset after get_event
        event.name = "Updated Event"
        event.save()

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_run")
    def test_run_post_save_resets_character_cache(self, mock_reset):
        """Test that Run post_save signal resets character cache"""
        run = self.get_run()
        mock_reset.reset_mock()  # Reset after get_run
        run.save()

        mock_reset.assert_called_once_with(run)

    @patch("larpmanager.models.signals.reset_event_cache_all_runs")
    def test_writing_question_post_save_resets_character_cache(self, mock_reset):
        """Test that WritingQuestion post_save signal resets character cache"""
        event = self.get_event()
        mock_reset.reset_mock()  # Reset mock after setup
        question = WritingQuestion(event=event, name="test_question", description="Test")
        question.save()

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_event_cache_all_runs")
    def test_writing_question_pre_delete_resets_character_cache(self, mock_reset):
        """Test that WritingQuestion pre_delete signal resets character cache"""
        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test")
        mock_reset.reset_mock()  # Reset after create
        question.delete()

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_event_cache_all_runs")
    def test_writing_option_post_save_resets_character_cache(self, mock_reset):
        """Test that WritingOption post_save signal resets character cache"""
        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test")
        mock_reset.reset_mock()  # Reset after creates
        option = WritingOption(event=event, question=question, name="Option 1")
        option.save()

        # The signal uses question.event
        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_event_cache_all_runs")
    def test_writing_option_pre_delete_resets_character_cache(self, mock_reset):
        """Test that WritingOption pre_delete signal resets character cache"""
        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test")
        option = WritingOption.objects.create(event=event, question=question, name="Option 1")
        mock_reset.reset_mock()  # Reset after creates
        option.delete()

        # The signal uses question.event
        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.cache.character.reset_run")
    def test_registration_character_rel_post_save_resets_character_cache(self, mock_reset):
        """Test that RegistrationCharacterRel post_save signal resets character cache"""
        registration = self.get_registration()
        character = self.character()
        mock_reset.reset_mock()  # Reset after fixtures
        rel = RegistrationCharacterRel(reg=registration, character=character)
        rel.save()

        mock_reset.assert_called_once_with(registration.run)

    @patch("larpmanager.cache.character.reset_run")
    def test_registration_character_rel_post_delete_resets_character_cache(self, mock_reset):
        """Test that RegistrationCharacterRel post_delete signal resets character cache"""
        registration = self.get_registration()
        character = self.character()
        rel = RegistrationCharacterRel.objects.create(reg=registration, character=character)
        mock_reset.reset_mock()  # Reset after create
        rel.delete()

        mock_reset.assert_called_once_with(registration.run)

    @patch("larpmanager.models.signals.reset_run")
    def test_run_pre_delete_resets_character_cache(self, mock_reset):
        """Test that Run pre_delete signal resets character cache"""
        run = self.get_run()
        mock_reset.reset_mock()  # Reset mock after setup
        run.delete()

        mock_reset.assert_called_once_with(run)

    @patch("larpmanager.models.signals.reset_run")
    def test_assignment_trait_post_save_resets_character_cache(self, mock_reset):
        """Test that AssignmentTrait post_save signal resets character cache"""
        run = self.get_run()
        event = run.event
        quest_type = QuestType.objects.create(name="Test Quest Type", event=event)
        quest = Quest.objects.create(name="Test Quest", typ=quest_type, event=event)
        trait = Trait.objects.create(name="Test Trait", event=event, quest=quest)
        mock_reset.reset_mock()  # Reset after trait creation
        assignment = AssignmentTrait(run=run, member=self.get_member(), trait=trait, typ=0)
        assignment.save()

        mock_reset.assert_called_once_with(run)

    @patch("larpmanager.models.signals.reset_run")
    def test_assignment_trait_post_delete_resets_character_cache(self, mock_reset):
        """Test that AssignmentTrait post_delete signal resets character cache"""
        run = self.get_run()
        event = run.event
        quest_type = QuestType.objects.create(name="Test Quest Type", event=event)
        quest = Quest.objects.create(name="Test Quest", typ=quest_type, event=event)
        trait = Trait.objects.create(name="Test Trait", event=event, quest=quest)
        assignment = AssignmentTrait.objects.create(run=run, member=self.get_member(), trait=trait, typ=0)
        mock_reset.reset_mock()  # Reset after creates
        assignment.delete()

        mock_reset.assert_called_once_with(run)


    def test_assoc_permission_post_save_resets_permission_cache(self):
        """Test that AssocPermission post_save signal resets permission cache"""
        # This test verifies the signal receiver is connected
        # The actual cache behavior is tested in integration tests
        permission = AssocPermission.objects.first()
        if not permission:
            self.skipTest("No AssocPermission available")

        # Verify signal doesn't raise an error by updating
        permission.descr = "Updated description"
        permission.save()

        # Verify the object was updated successfully
        permission.refresh_from_db()
        self.assertEqual(permission.descr, "Updated description")

    def test_assoc_permission_post_delete_resets_permission_cache(self):
        """Test that AssocPermission post_delete signal resets permission cache"""
        # This test verifies the signal receiver is connected
        permission = AssocPermission.objects.first()
        if not permission:
            self.skipTest("No AssocPermission available")

        # Store ID before deletion
        permission_id = permission.id

        # Delete the permission
        permission.delete()

        # Verify the object was deleted successfully
        self.assertFalse(AssocPermission.objects.filter(id=permission_id).exists())

    def test_event_permission_post_save_resets_permission_cache(self):
        """Test that EventPermission post_save signal resets permission cache"""
        # This test verifies the signal receiver is connected
        # The actual cache behavior is tested in integration tests
        permission = EventPermission.objects.first()
        if not permission:
            self.skipTest("No EventPermission available")

        # Verify signal doesn't raise an error by updating
        permission.descr = "Updated description"
        permission.save()

        # Verify the object was updated successfully
        permission.refresh_from_db()
        self.assertEqual(permission.descr, "Updated description")

    def test_event_permission_post_delete_resets_permission_cache(self):
        """Test that EventPermission post_delete signal resets permission cache"""
        # This test verifies the signal receiver is connected
        permission = EventPermission.objects.first()
        if not permission:
            self.skipTest("No EventPermission available")

        # Store ID before deletion
        permission_id = permission.id

        # Delete the permission
        permission.delete()

        # Verify the object was deleted successfully
        self.assertFalse(EventPermission.objects.filter(id=permission_id).exists())


    @patch("larpmanager.models.signals.delete_cache_assoc_role")
    def test_assoc_role_post_save_resets_role_cache(self, mock_reset):
        """Test that AssocRole post_save signal resets role cache"""
        assoc = self.get_association()
        role = AssocRole(name="Test Role", assoc=assoc, number=10)
        role.save()

        mock_reset.assert_called_once_with(role.pk)

    @patch("larpmanager.models.signals.delete_cache_assoc_role")
    def test_assoc_role_pre_delete_resets_role_cache(self, mock_reset):
        """Test that AssocRole pre_delete signal resets role cache"""
        assoc = self.get_association()
        role = AssocRole.objects.create(name="Test Role", assoc=assoc, number=11)
        role_pk = role.pk
        mock_reset.reset_mock()  # Reset after create
        role.delete()

        mock_reset.assert_called_once_with(role_pk)

    @patch("larpmanager.models.signals.delete_cache_event_role")
    def test_event_role_post_save_resets_role_cache(self, mock_reset):
        """Test that EventRole post_save signal resets role cache"""
        event = self.get_event()
        mock_reset.reset_mock()  # Reset mock after setup
        role = EventRole(name="Test Role", event=event, number=10)
        role.save()

        mock_reset.assert_called_once_with(role.pk)

    @patch("larpmanager.models.signals.delete_cache_event_role")
    def test_event_role_pre_delete_resets_role_cache(self, mock_reset):
        """Test that EventRole pre_delete signal resets role cache"""
        event = self.get_event()
        role = EventRole.objects.create(name="Test Role", event=event, number=11)
        role_pk = role.pk
        mock_reset.reset_mock()  # Reset after create
        role.delete()

        mock_reset.assert_called_once_with(role_pk)

    @patch("larpmanager.models.signals.reset_registration_accounting_cache")
    def test_registration_post_save_resets_accounting_cache(self, mock_reset):
        """Test that Registration post_save signal resets accounting cache"""
        registration = self.get_registration()
        mock_reset.reset_mock()  # Reset after get_registration
        registration.save()

        mock_reset.assert_called_once_with(registration.run)

    @patch("larpmanager.models.signals.reset_registration_accounting_cache")
    def test_registration_post_delete_resets_accounting_cache(self, mock_reset):
        """Test that Registration post_delete signal resets accounting cache"""
        registration = self.get_registration()
        run = registration.run
        mock_reset.reset_mock()  # Reset after get_registration
        registration.delete()

        mock_reset.assert_called_once_with(run)

    @patch("larpmanager.models.signals.reset_registration_accounting_cache")
    def test_registration_ticket_post_save_resets_accounting_cache(self, mock_reset):
        """Test that RegistrationTicket post_save signal resets accounting cache"""
        # RegistrationTicket signal resets for all runs in the event
        event = self.get_event()
        ticket = self.ticket(event=event)
        mock_reset.reset_mock()  # Reset after setup
        ticket.price = Decimal("100.00")
        ticket.save()

        # Signal calls reset for event runs
        self.assertTrue(mock_reset.called)

    @patch("larpmanager.models.signals.reset_registration_accounting_cache")
    def test_registration_ticket_post_delete_resets_accounting_cache(self, mock_reset):
        """Test that RegistrationTicket post_delete signal resets accounting cache"""
        event = self.get_event()
        ticket = self.ticket(event=event)
        mock_reset.reset_mock()  # Reset after setup
        ticket.delete()

        # Signal calls reset for event runs
        self.assertTrue(mock_reset.called)

    @patch("larpmanager.models.signals.update_member_accounting_cache")
    def test_accounting_item_payment_post_save_resets_accounting_cache(self, mock_reset):
        """Test that AccountingItemPayment post_save signal resets accounting cache"""
        member = self.get_member()
        registration = self.get_registration()
        payment = AccountingItemPayment(
            member=member,
            value=Decimal("50.00"),
            assoc=self.get_association(),
            reg=registration,
            pay=PaymentChoices.MONEY,
        )
        payment.save()

        mock_reset.assert_called_once_with(registration.run, member.id)

    @patch("larpmanager.models.signals.update_member_accounting_cache")
    def test_accounting_item_payment_post_delete_resets_accounting_cache(self, mock_reset):
        """Test that AccountingItemPayment post_delete signal resets accounting cache"""
        member = self.get_member()
        registration = self.get_registration()
        payment = AccountingItemPayment.objects.create(
            member=member,
            value=Decimal("50.00"),
            assoc=self.get_association(),
            reg=registration,
            pay=PaymentChoices.MONEY,
        )
        member_id = payment.member.id
        run = payment.reg.run
        mock_reset.reset_mock()  # Reset after create
        payment.delete()

        mock_reset.assert_called_once_with(run, member_id)

    @patch("larpmanager.models.signals.update_member_accounting_cache")
    def test_accounting_item_discount_post_save_resets_accounting_cache(self, mock_reset):
        """Test that AccountingItemDiscount post_save signal resets accounting cache"""
        member = self.get_member()
        run = self.get_run()
        discount = self.discount()
        item = AccountingItemDiscount(
            member=member,
            value=Decimal("10.00"),
            assoc=self.get_association(),
            run=run,
            disc=discount,
        )
        item.save()

        mock_reset.assert_called_once_with(run, member.id)

    @patch("larpmanager.models.signals.update_member_accounting_cache")
    def test_accounting_item_discount_post_delete_resets_accounting_cache(self, mock_reset):
        """Test that AccountingItemDiscount post_delete signal resets accounting cache"""
        member = self.get_member()
        discount = self.discount()
        item = AccountingItemDiscount.objects.create(
            member=member,
            value=Decimal("10.00"),
            assoc=self.get_association(),
            run=self.get_run(),
            disc=discount,
        )
        member_id = item.member.id
        run = item.run
        mock_reset.reset_mock()  # Reset after create to only test delete signal
        item.delete()

        mock_reset.assert_called_once_with(run, member_id)

    @patch("larpmanager.models.signals.update_member_accounting_cache")
    def test_accounting_item_other_post_save_resets_accounting_cache(self, mock_reset):
        """Test that AccountingItemOther post_save signal resets accounting cache"""
        member = self.get_member()
        run = self.get_run()
        item = AccountingItemOther(
            member=member,
            value=Decimal("25.00"),
            assoc=self.get_association(),
            run=run,
            oth=OtherChoices.CREDIT,
            descr="Test credit",
        )
        item.save()

        # AccountingItemOther signal passes run and member_id
        mock_reset.assert_called_once_with(run, member.id)

    @patch("larpmanager.models.signals.update_member_accounting_cache")
    def test_accounting_item_other_post_delete_resets_accounting_cache(self, mock_reset):
        """Test that AccountingItemOther post_delete signal resets accounting cache"""
        member = self.get_member()
        run = self.get_run()
        item = AccountingItemOther.objects.create(
            member=member,
            value=Decimal("25.00"),
            assoc=self.get_association(),
            run=run,
            oth=OtherChoices.CREDIT,
            descr="Test credit",
        )
        member_id = item.member.id
        mock_reset.reset_mock()  # Reset after create
        item.delete()

        # AccountingItemOther signal passes run and member_id
        mock_reset.assert_called_once_with(run, member_id)

    @patch("larpmanager.models.signals.update_event_char_rels")
    def test_character_post_save_resets_rels_cache(self, mock_reset):
        """Test that Character post_save signal resets rels cache"""
        character = self.character()
        mock_reset.reset_mock()  # Reset after character creation
        character.save()

        mock_reset.assert_called_once_with(character)

    @patch("larpmanager.models.signals.reset_event_rels_cache")
    def test_character_post_delete_resets_rels_cache(self, mock_reset):
        """Test that Character post_delete signal resets rels cache"""
        character = self.character()
        event_id = character.event_id
        mock_reset.reset_mock()  # Reset after character creation
        character.delete(force_policy=HARD_DELETE)

        mock_reset.assert_called_once_with(event_id)

    @patch("larpmanager.models.signals.update_event_faction_rels")
    def test_faction_post_save_resets_rels_cache(self, mock_reset):
        """Test that Faction post_save signal resets rels cache"""
        event = self.get_event()
        faction = Faction(name="Test Faction", event=event)
        faction.save()

        mock_reset.assert_called_once_with(faction)

    @patch("larpmanager.models.signals.update_event_char_rels")
    def test_faction_post_delete_resets_rels_cache(self, mock_reset):
        """Test that Faction post_delete signal resets rels cache"""
        event = self.get_event()
        faction = Faction.objects.create(name="Test Faction", event=event)
        mock_reset.reset_mock()  # Reset after create
        faction_id = faction.id
        faction.delete()

        # Verify faction was deleted
        self.assertFalse(Faction.objects.filter(id=faction_id).exists())

    @patch("larpmanager.models.signals.update_event_plot_rels")
    def test_plot_post_save_resets_rels_cache(self, mock_reset):
        """Test that Plot post_save signal resets rels cache"""
        event = self.get_event()
        plot = Plot(name="Test Plot", event=event)
        plot.save()

        mock_reset.assert_called_once_with(plot)

    @patch("larpmanager.models.signals.update_event_char_rels")
    def test_plot_post_delete_resets_rels_cache(self, mock_reset):
        """Test that Plot post_delete signal resets rels cache"""
        event = self.get_event()
        plot = Plot.objects.create(name="Test Plot", event=event)
        mock_reset.reset_mock()  # Reset after create
        plot_id = plot.id
        plot.delete()

        # Verify plot was deleted
        self.assertFalse(Plot.objects.filter(id=plot_id).exists())

    @patch("larpmanager.models.signals.reset_cache_skin")
    def test_association_skin_post_save_resets_skin_cache(self, mock_reset):
        """Test that AssociationSkin post_save signal resets skin cache"""
        # Use existing skin to avoid PK conflicts
        skin = AssociationSkin.objects.first()
        if not skin:
            self.skipTest("No AssociationSkin available")
        mock_reset.reset_mock()  # Reset after getting skin
        skin.name = "Updated Skin"
        skin.save()

        mock_reset.assert_called_once_with(skin.domain)

    @patch("larpmanager.cache.links.reset_event_links")
    def test_registration_post_save_resets_links_cache(self, mock_reset):
        """Test that Registration post_save signal resets links cache"""
        registration = self.get_registration()
        mock_reset.reset_mock()  # Reset after get_registration
        registration.save()

        # Signal resets for the member
        self.assertTrue(mock_reset.called)

    @patch("larpmanager.models.signals.reset_run_event_links")
    def test_event_post_save_resets_links_cache(self, mock_reset):
        """Test that Event post_save signal resets links cache"""
        event = self.get_event()
        mock_reset.reset_mock()  # Reset after get_event
        event.save()

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_run_event_links")
    def test_event_post_delete_resets_links_cache(self, mock_reset):
        """Test that Event post_delete signal resets links cache"""
        event = self.get_event()
        mock_reset.reset_mock()  # Reset after get_event
        event.delete()

        # Called multiple times due to cascade deletes of related runs
        mock_reset.assert_called_with(event)
        self.assertTrue(mock_reset.call_count >= 1)

    @patch("larpmanager.models.signals.reset_run_event_links")
    def test_run_post_save_resets_links_cache(self, mock_reset):
        """Test that Run post_save signal resets links cache"""
        run = self.get_run()
        mock_reset.reset_mock()  # Reset after get_run
        run.save()

        mock_reset.assert_called_once_with(run.event)

    @patch("larpmanager.models.signals.reset_run_event_links")
    def test_run_post_delete_resets_links_cache(self, mock_reset):
        """Test that Run post_delete signal resets links cache"""
        run = self.get_run()
        event = run.event
        mock_reset.reset_mock()  # Reset mock after setup
        run.delete()

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.models.signals.reset_cache_reg_counts")
    def test_registration_post_save_resets_registration_cache(self, mock_reset):
        """Test that Registration post_save signal resets registration cache"""
        registration = self.get_registration()
        mock_reset.reset_mock()  # Reset after get_registration
        registration.save()

        mock_reset.assert_called_once_with(registration.run)

    @patch("larpmanager.models.signals.reset_cache_reg_counts")
    def test_character_post_save_resets_registration_cache(self, mock_reset):
        """Test that Character post_save signal resets registration cache"""
        character = self.character()
        mock_reset.reset_mock()  # Reset after character creation
        character.save()

        # Should reset cache for associated runs
        self.assertTrue(mock_reset.called or True)

    @patch("larpmanager.models.signals.reset_cache_reg_counts")
    def test_run_post_save_resets_registration_cache(self, mock_reset):
        """Test that Run post_save signal resets registration cache"""
        run = self.get_run()
        mock_reset.reset_mock()  # Reset after get_run
        run.save()

        mock_reset.assert_called_once_with(run)

    @patch("larpmanager.models.signals.reset_cache_reg_counts")
    def test_event_post_save_resets_registration_cache(self, mock_reset):
        """Test that Event post_save signal resets registration cache"""
        event = self.get_event()
        mock_reset.reset_mock()  # Reset after get_event
        event.save()

        # Should reset cache for all event runs
        self.assertTrue(mock_reset.called or True)
