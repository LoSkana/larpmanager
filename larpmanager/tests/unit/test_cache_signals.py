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

from larpmanager.models.access import AssocPermission, AssocRole, EventPermission, EventRole
from larpmanager.models.accounting import AccountingItemDiscount, AccountingItemOther, AccountingItemPayment, PaymentChoices
from larpmanager.models.association import AssociationSkin
from larpmanager.models.casting import AssignmentTrait, Trait
from larpmanager.models.form import WritingOption, WritingQuestion
from larpmanager.models.member import Member
from larpmanager.models.registration import RegistrationCharacterRel, RegistrationTicket
from larpmanager.models.writing import Faction, Plot
from larpmanager.models.casting import QuestType
from larpmanager.models.casting import Quest
from larpmanager.tests.unit.base import BaseTestCase


class TestCacheSignals(BaseTestCase):
    """Test cases for cache-related signal receivers"""

    def setUp(self):
        super().setUp()
        # Clear cache before each test
        cache.clear()

    def test_member_post_save_resets_character_cache(self):
        """Test that Member post_save signal works correctly"""
        user = self.create_user(username="testmember")
        member = Member(user=user, name="Test", surname="Member")

        # This should not raise an exception when signals are fired
        member.save()

        # Verify member was saved successfully
        self.assertIsNotNone(member.id)
        self.assertEqual(member.name, "Test")

    @patch("larpmanager.cache.character.reset_character_cache_on_character_save")
    def test_character_pre_save_resets_character_cache(self, mock_reset):
        """Test that Character pre_save signal resets character cache"""
        character = self.character()
        character.name = "Updated Character"
        character.save()

        mock_reset.assert_called_once_with(character)

    @patch("larpmanager.cache.character.reset_character_cache_on_character_delete")
    def test_character_pre_delete_resets_character_cache(self, mock_reset):
        """Test that Character pre_delete signal resets character cache"""
        character = self.character()
        character.delete()

        mock_reset.assert_called_once_with(character)

    @patch("larpmanager.cache.character.reset_character_cache_on_faction_save")
    def test_faction_pre_save_resets_character_cache(self, mock_reset):
        """Test that Faction pre_save signal resets character cache"""
        assoc = self.get_association()
        faction = Faction(name="Test Faction", assoc=assoc)
        faction.save()

        mock_reset.assert_called_once_with(faction)

    @patch("larpmanager.cache.character.reset_character_cache_on_faction_delete")
    def test_faction_pre_delete_resets_character_cache(self, mock_reset):
        """Test that Faction pre_delete signal resets character cache"""
        assoc = self.get_association()
        faction = Faction.objects.create(name="Test Faction", assoc=assoc)
        faction.delete()

        mock_reset.assert_called_once_with(faction)

    @patch("larpmanager.cache.character.reset_character_cache_on_quest_type_save")
    def test_quest_type_pre_save_resets_character_cache(self, mock_reset):
        """Test that QuestType pre_save signal resets character cache"""
        assoc = self.get_association()
        quest_type = QuestType(name="Test Quest Type", assoc=assoc)
        quest_type.save()

        mock_reset.assert_called_once_with(quest_type)

    @patch("larpmanager.cache.character.reset_character_cache_on_quest_type_delete")
    def test_quest_type_pre_delete_resets_character_cache(self, mock_reset):
        """Test that QuestType pre_delete signal resets character cache"""
        assoc = self.get_association()
        quest_type = QuestType.objects.create(name="Test Quest Type", assoc=assoc)
        quest_type.delete()

        mock_reset.assert_called_once_with(quest_type)

    @patch("larpmanager.cache.character.reset_character_cache_on_quest_save")
    def test_quest_pre_save_resets_character_cache(self, mock_reset):
        """Test that Quest pre_save signal resets character cache"""
        assoc = self.get_association()
        quest_type = QuestType.objects.create(name="Test Quest Type", assoc=assoc)
        quest = Quest(name="Test Quest", typ=quest_type, assoc=assoc)
        quest.save()

        mock_reset.assert_called_once_with(quest)

    @patch("larpmanager.cache.character.reset_character_cache_on_quest_delete")
    def test_quest_pre_delete_resets_character_cache(self, mock_reset):
        """Test that Quest pre_delete signal resets character cache"""
        assoc = self.get_association()
        quest_type = QuestType.objects.create(name="Test Quest Type", assoc=assoc)
        quest = Quest.objects.create(name="Test Quest", typ=quest_type, assoc=assoc)
        quest.delete()

        mock_reset.assert_called_once_with(quest)

    @patch("larpmanager.cache.character.reset_character_cache_on_trait_save")
    def test_trait_pre_save_resets_character_cache(self, mock_reset):
        """Test that Trait pre_save signal resets character cache"""
        assoc = self.get_association()
        trait = Trait(name="Test Trait", assoc=assoc)
        trait.save()

        mock_reset.assert_called_once_with(trait)

    @patch("larpmanager.cache.character.reset_character_cache_on_trait_delete")
    def test_trait_pre_delete_resets_character_cache(self, mock_reset):
        """Test that Trait pre_delete signal resets character cache"""
        assoc = self.get_association()
        trait = Trait.objects.create(name="Test Trait", assoc=assoc)
        trait.delete()

        mock_reset.assert_called_once_with(trait)

    @patch("larpmanager.cache.character.reset_character_cache_on_event_save")
    def test_event_post_save_resets_character_cache(self, mock_reset):
        """Test that Event post_save signal resets character cache"""
        event = self.get_event()
        event.name = "Updated Event"
        event.save()

        mock_reset.assert_called_once_with(event)

    @patch("larpmanager.cache.character.reset_character_cache_on_run_save")
    def test_run_post_save_resets_character_cache(self, mock_reset):
        """Test that Run post_save signal resets character cache"""
        run = self.get_run()
        run.save()

        mock_reset.assert_called_once_with(run)

    @patch("larpmanager.cache.character.reset_character_cache_on_writing_question_save")
    def test_writing_question_post_save_resets_character_cache(self, mock_reset):
        """Test that WritingQuestion post_save signal resets character cache"""
        event = self.get_event()
        question = WritingQuestion(event=event, name="test_question", description="Test")
        question.save()

        mock_reset.assert_called_once_with(question)

    @patch("larpmanager.cache.character.reset_character_cache_on_writing_question_delete")
    def test_writing_question_pre_delete_resets_character_cache(self, mock_reset):
        """Test that WritingQuestion pre_delete signal resets character cache"""
        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test")
        question.delete()

        mock_reset.assert_called_once_with(question)

    @patch("larpmanager.cache.character.reset_character_cache_on_writing_option_save")
    def test_writing_option_post_save_resets_character_cache(self, mock_reset):
        """Test that WritingOption post_save signal resets character cache"""
        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test")
        option = WritingOption(event=event, question=question, name="Option 1")
        option.save()

        mock_reset.assert_called_once_with(option)

    @patch("larpmanager.cache.character.reset_character_cache_on_writing_option_delete")
    def test_writing_option_pre_delete_resets_character_cache(self, mock_reset):
        """Test that WritingOption pre_delete signal resets character cache"""
        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test")
        option = WritingOption.objects.create(event=event, question=question, name="Option 1")
        option.delete()

        mock_reset.assert_called_once_with(option)

    @patch("larpmanager.cache.character.reset_character_cache_on_registration_character_rel_save")
    def test_registration_character_rel_post_save_resets_character_cache(self, mock_reset):
        """Test that RegistrationCharacterRel post_save signal resets character cache"""
        registration = self.get_registration()
        character = self.character()
        rel = RegistrationCharacterRel(registration=registration, character=character)
        rel.save()

        mock_reset.assert_called_once_with(rel)

    @patch("larpmanager.cache.character.reset_character_cache_on_registration_character_rel_delete")
    def test_registration_character_rel_post_delete_resets_character_cache(self, mock_reset):
        """Test that RegistrationCharacterRel post_delete signal resets character cache"""
        registration = self.get_registration()
        character = self.character()
        rel = RegistrationCharacterRel.objects.create(registration=registration, character=character)
        rel.delete()

        mock_reset.assert_called_once_with(rel)

    @patch("larpmanager.cache.character.reset_character_cache_on_run_delete")
    def test_run_pre_delete_resets_character_cache(self, mock_reset):
        """Test that Run pre_delete signal resets character cache"""
        run = self.get_run()
        run.delete()

        mock_reset.assert_called_once_with(run)

    @patch("larpmanager.cache.character.reset_character_cache_on_assignment_trait_save")
    def test_assignment_trait_post_save_resets_character_cache(self, mock_reset):
        """Test that AssignmentTrait post_save signal resets character cache"""
        character = self.character()
        trait = Trait.objects.create(name="Test Trait", assoc=self.get_association())
        assignment = AssignmentTrait(character=character, trait=trait)
        assignment.save()

        mock_reset.assert_called_once_with(assignment)

    @patch("larpmanager.cache.character.reset_character_cache_on_assignment_trait_delete")
    def test_assignment_trait_post_delete_resets_character_cache(self, mock_reset):
        """Test that AssignmentTrait post_delete signal resets character cache"""
        character = self.character()
        trait = Trait.objects.create(name="Test Trait", assoc=self.get_association())
        assignment = AssignmentTrait.objects.create(character=character, trait=trait)
        assignment.delete()

        mock_reset.assert_called_once_with(assignment)

    @patch("larpmanager.cache.permission.reset_assoc_permissions_cache")
    def test_assoc_permission_post_save_resets_permission_cache(self, mock_reset):
        """Test that AssocPermission post_save signal resets permission cache"""
        assoc = self.get_association()
        member = self.get_member()
        permission = AssocPermission(name="Test Permission", assoc=assoc, member=member)
        permission.save()

        mock_reset.assert_called_once_with(assoc.id)

    @patch("larpmanager.cache.permission.reset_assoc_permissions_cache")
    def test_assoc_permission_post_delete_resets_permission_cache(self, mock_reset):
        """Test that AssocPermission post_delete signal resets permission cache"""
        assoc = self.get_association()
        member = self.get_member()
        permission = AssocPermission.objects.create(name="Test Permission", assoc=assoc, member=member)
        permission.delete()

        mock_reset.assert_called_once_with(assoc.id)

    @patch("larpmanager.cache.permission.reset_event_permissions_cache")
    def test_event_permission_post_save_resets_permission_cache(self, mock_reset):
        """Test that EventPermission post_save signal resets permission cache"""
        event = self.get_event()
        member = self.get_member()
        permission = EventPermission(name="Test Permission", event=event, member=member)
        permission.save()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.permission.reset_event_permissions_cache")
    def test_event_permission_post_delete_resets_permission_cache(self, mock_reset):
        """Test that EventPermission post_delete signal resets permission cache"""
        event = self.get_event()
        member = self.get_member()
        permission = EventPermission.objects.create(name="Test Permission", event=event, member=member)
        permission.delete()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.role.reset_assoc_roles_cache")
    def test_assoc_role_post_save_resets_role_cache(self, mock_reset):
        """Test that AssocRole post_save signal resets role cache"""
        assoc = self.get_association()
        member = self.get_member()
        role = AssocRole(name="Test Role", assoc=assoc, member=member)
        role.save()

        mock_reset.assert_called_once_with(assoc.id)

    @patch("larpmanager.cache.role.reset_assoc_roles_cache")
    def test_assoc_role_pre_delete_resets_role_cache(self, mock_reset):
        """Test that AssocRole pre_delete signal resets role cache"""
        assoc = self.get_association()
        member = self.get_member()
        role = AssocRole.objects.create(name="Test Role", assoc=assoc, member=member)
        role.delete()

        mock_reset.assert_called_once_with(assoc.id)

    @patch("larpmanager.cache.role.reset_event_roles_cache")
    def test_event_role_post_save_resets_role_cache(self, mock_reset):
        """Test that EventRole post_save signal resets role cache"""
        event = self.get_event()
        member = self.get_member()
        role = EventRole(name="Test Role", event=event, member=member)
        role.save()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.role.reset_event_roles_cache")
    def test_event_role_pre_delete_resets_role_cache(self, mock_reset):
        """Test that EventRole pre_delete signal resets role cache"""
        event = self.get_event()
        member = self.get_member()
        role = EventRole.objects.create(name="Test Role", event=event, member=member)
        role.delete()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.accounting.reset_registration_accounting_cache")
    def test_registration_post_save_resets_accounting_cache(self, mock_reset):
        """Test that Registration post_save signal resets accounting cache"""
        registration = self.get_registration()
        registration.save()

        mock_reset.assert_called_once_with(registration.run)

    @patch("larpmanager.cache.accounting.reset_registration_accounting_cache")
    def test_registration_post_delete_resets_accounting_cache(self, mock_reset):
        """Test that Registration post_delete signal resets accounting cache"""
        registration = self.get_registration()
        run = registration.run
        registration.delete()

        mock_reset.assert_called_once_with(run)

    @patch("larpmanager.cache.accounting.update_member_accounting_cache")
    def test_registration_ticket_post_save_resets_accounting_cache(self, mock_reset):
        """Test that RegistrationTicket post_save signal resets accounting cache"""
        event = self.get_event()
        ticket = self.ticket(event=event)
        registration = self.get_registration()
        reg_ticket = RegistrationTicket(registration=registration, ticket=ticket, value=1)
        reg_ticket.save()

        mock_reset.assert_called_once_with(registration.member.id)

    @patch("larpmanager.cache.accounting.update_member_accounting_cache")
    def test_registration_ticket_post_delete_resets_accounting_cache(self, mock_reset):
        """Test that RegistrationTicket post_delete signal resets accounting cache"""
        event = self.get_event()
        ticket = self.ticket(event=event)
        registration = self.get_registration()
        reg_ticket = RegistrationTicket.objects.create(registration=registration, ticket=ticket, value=1)
        member_id = reg_ticket.registration.member.id
        reg_ticket.delete()

        mock_reset.assert_called_once_with(member_id)

    @patch("larpmanager.cache.accounting.update_member_accounting_cache")
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

    @patch("larpmanager.cache.accounting.update_member_accounting_cache")
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
        payment.delete()

        mock_reset.assert_called_once_with(run, member_id)

    @patch("larpmanager.cache.accounting.update_member_accounting_cache")
    def test_accounting_item_discount_post_save_resets_accounting_cache(self, mock_reset):
        """Test that AccountingItemDiscount post_save signal resets accounting cache"""
        member = self.get_member()
        discount = self.discount()
        item = AccountingItemDiscount(
            member=member,
            value=Decimal("10.00"),
            assoc=self.get_association(),
            registration=self.get_registration(),
            discount=discount,
        )
        item.save()

        mock_reset.assert_called_once_with(member.id)

    @patch("larpmanager.cache.accounting.update_member_accounting_cache")
    def test_accounting_item_discount_post_delete_resets_accounting_cache(self, mock_reset):
        """Test that AccountingItemDiscount post_delete signal resets accounting cache"""
        member = self.get_member()
        discount = self.discount()
        item = AccountingItemDiscount.objects.create(
            member=member,
            value=Decimal("10.00"),
            assoc=self.get_association(),
            registration=self.get_registration(),
            discount=discount,
        )
        member_id = item.member.id
        item.delete()

        mock_reset.assert_called_once_with(member_id)

    @patch("larpmanager.cache.accounting.update_member_accounting_cache")
    def test_accounting_item_other_post_save_resets_accounting_cache(self, mock_reset):
        """Test that AccountingItemOther post_save signal resets accounting cache"""
        member = self.get_member()
        item = AccountingItemOther(
            member=member,
            value=Decimal("25.00"),
            assoc=self.get_association(),
            run=self.get_run(),
            oth=AccountingItemOther.CREDIT,
            descr="Test credit",
        )
        item.save()

        mock_reset.assert_called_once_with(member.id)

    @patch("larpmanager.cache.accounting.update_member_accounting_cache")
    def test_accounting_item_other_post_delete_resets_accounting_cache(self, mock_reset):
        """Test that AccountingItemOther post_delete signal resets accounting cache"""
        member = self.get_member()
        item = AccountingItemOther.objects.create(
            member=member,
            value=Decimal("25.00"),
            assoc=self.get_association(),
            run=self.get_run(),
            oth=AccountingItemOther.CREDIT,
            descr="Test credit",
        )
        member_id = item.member.id
        item.delete()

        mock_reset.assert_called_once_with(member_id)

    @patch("larpmanager.cache.rels.reset_character_rels_cache")
    def test_character_post_save_resets_rels_cache(self, mock_reset):
        """Test that Character post_save signal resets rels cache"""
        character = self.character()
        character.save()

        mock_reset.assert_called_once_with(character.id)

    @patch("larpmanager.cache.rels.reset_character_rels_cache")
    def test_character_post_delete_resets_rels_cache(self, mock_reset):
        """Test that Character post_delete signal resets rels cache"""
        character = self.character()
        character_id = character.id
        character.delete()

        mock_reset.assert_called_once_with(character_id)

    @patch("larpmanager.cache.rels.reset_faction_rels_cache")
    def test_faction_post_save_resets_rels_cache(self, mock_reset):
        """Test that Faction post_save signal resets rels cache"""
        assoc = self.get_association()
        faction = Faction(name="Test Faction", assoc=assoc)
        faction.save()

        mock_reset.assert_called_once_with(faction.id)

    @patch("larpmanager.cache.rels.reset_faction_rels_cache")
    def test_faction_post_delete_resets_rels_cache(self, mock_reset):
        """Test that Faction post_delete signal resets rels cache"""
        assoc = self.get_association()
        faction = Faction.objects.create(name="Test Faction", assoc=assoc)
        faction_id = faction.id
        faction.delete()

        mock_reset.assert_called_once_with(faction_id)

    @patch("larpmanager.cache.rels.reset_plot_rels_cache")
    def test_plot_post_save_resets_rels_cache(self, mock_reset):
        """Test that Plot post_save signal resets rels cache"""
        event = self.get_event()
        plot = Plot(name="Test Plot", event=event)
        plot.save()

        mock_reset.assert_called_once_with(plot.id)

    @patch("larpmanager.cache.rels.reset_plot_rels_cache")
    def test_plot_post_delete_resets_rels_cache(self, mock_reset):
        """Test that Plot post_delete signal resets rels cache"""
        event = self.get_event()
        plot = Plot.objects.create(name="Test Plot", event=event)
        plot_id = plot.id
        plot.delete()

        mock_reset.assert_called_once_with(plot_id)

    @patch("larpmanager.cache.skin.reset_association_skin_cache")
    def test_association_skin_post_save_resets_skin_cache(self, mock_reset):
        """Test that AssociationSkin post_save signal resets skin cache"""
        assoc = self.get_association()
        skin = AssociationSkin(assoc=assoc, name="Test Skin")
        skin.save()

        mock_reset.assert_called_once_with(assoc.id)

    @patch("larpmanager.cache.links.reset_registration_links_cache")
    def test_registration_post_save_resets_links_cache(self, mock_reset):
        """Test that Registration post_save signal resets links cache"""
        registration = self.get_registration()
        registration.save()

        mock_reset.assert_called_once_with(registration.run.id)

    @patch("larpmanager.cache.links.reset_event_links_cache")
    def test_event_post_save_resets_links_cache(self, mock_reset):
        """Test that Event post_save signal resets links cache"""
        event = self.get_event()
        event.save()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.links.reset_event_links_cache")
    def test_event_post_delete_resets_links_cache(self, mock_reset):
        """Test that Event post_delete signal resets links cache"""
        event = self.get_event()
        event_id = event.id
        event.delete()

        mock_reset.assert_called_once_with(event_id)

    @patch("larpmanager.cache.links.reset_run_links_cache")
    def test_run_post_save_resets_links_cache(self, mock_reset):
        """Test that Run post_save signal resets links cache"""
        run = self.get_run()
        run.save()

        mock_reset.assert_called_once_with(run.id)

    @patch("larpmanager.cache.links.reset_run_links_cache")
    def test_run_post_delete_resets_links_cache(self, mock_reset):
        """Test that Run post_delete signal resets links cache"""
        run = self.get_run()
        run_id = run.id
        run.delete()

        mock_reset.assert_called_once_with(run_id)

    @patch("larpmanager.cache.registration.reset_registration_cache")
    def test_registration_post_save_resets_registration_cache(self, mock_reset):
        """Test that Registration post_save signal resets registration cache"""
        registration = self.get_registration()
        registration.save()

        mock_reset.assert_called_once_with(registration.run.id)

    @patch("larpmanager.cache.registration.reset_registration_cache")
    def test_character_post_save_resets_registration_cache(self, mock_reset):
        """Test that Character post_save signal resets registration cache"""
        character = self.character()
        character.save()

        # Should reset cache for associated runs
        mock_reset.assert_called()

    @patch("larpmanager.cache.registration.reset_registration_cache")
    def test_run_post_save_resets_registration_cache(self, mock_reset):
        """Test that Run post_save signal resets registration cache"""
        run = self.get_run()
        run.save()

        mock_reset.assert_called_once_with(run.id)

    @patch("larpmanager.cache.registration.reset_registration_cache")
    def test_event_post_save_resets_registration_cache(self, mock_reset):
        """Test that Event post_save signal resets registration cache"""
        event = self.get_event()
        event.save()

        # Should reset cache for all event runs
        mock_reset.assert_called()
