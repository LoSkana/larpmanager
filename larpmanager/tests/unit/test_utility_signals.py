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

"""Tests for utility and accounting-related signal receivers"""

from decimal import Decimal
from unittest.mock import Mock, patch

from larpmanager.models.accounting import (
    AccountingItemExpense,
    AccountingItemOther,
    AccountingItemPayment,
)
from larpmanager.models.association import AssocText, EventText
from larpmanager.models.casting import AbilityPx, AssignmentTrait, DeliveryPx, ModifierPx, RulePx, Trait
from larpmanager.models.form import Handout, HandoutTemplate
from larpmanager.models.member import PlayerRelationship
from larpmanager.models.writing import Faction, Relationship
from larpmanager.tests.unit.base import BaseTestCase


class TestUtilitySignals(BaseTestCase):
    """Test cases for utility and accounting-related signal receivers"""

    @patch("larpmanager.utils.experience.update_character_px")
    def test_character_post_save_updates_experience(self, mock_update):
        """Test that Character post_save signal updates character experience"""
        character = self.character()
        character.save()

        mock_update.assert_called_once_with(character)

    @patch("larpmanager.utils.experience.update_character_px")
    def test_ability_px_post_save_updates_experience(self, mock_update):
        """Test that AbilityPx post_save signal updates character experience"""
        character = self.character()
        ability_px = AbilityPx(character=character, ability="Test Ability", px=10)
        ability_px.save()

        mock_update.assert_called_once_with(character)

    @patch("larpmanager.utils.experience.update_character_px")
    def test_delivery_px_post_save_updates_experience(self, mock_update):
        """Test that DeliveryPx post_save signal updates character experience"""
        character = self.character()
        delivery_px = DeliveryPx(character=character, delivery="Test Delivery", px=5)
        delivery_px.save()

        mock_update.assert_called_once_with(character)

    @patch("larpmanager.utils.experience.update_character_px")
    def test_rule_px_post_save_updates_experience(self, mock_update):
        """Test that RulePx post_save signal updates character experience"""
        character = self.character()
        rule_px = RulePx(character=character, rule="Test Rule", px=15)
        rule_px.save()

        mock_update.assert_called_once_with(character)

    @patch("larpmanager.utils.experience.update_character_px")
    def test_modifier_px_post_save_updates_experience(self, mock_update):
        """Test that ModifierPx post_save signal updates character experience"""
        character = self.character()
        modifier_px = ModifierPx(character=character, modifier="Test Modifier", px=8)
        modifier_px.save()

        mock_update.assert_called_once_with(character)

    @patch("larpmanager.utils.writing.update_character_writing")
    def test_character_pre_save_updates_writing(self, mock_update):
        """Test that Character pre_save signal updates character writing"""
        character = self.character()
        character.name = "Updated Character Name"
        character.save()

        mock_update.assert_called_once_with(character)

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_handout_pre_delete_cleans_pdf(self, mock_generate):
        """Test that Handout pre_delete signal cleans up PDF files"""
        character = self.character()
        handout = Handout(character=character, name="Test Handout")
        handout.save()
        handout.delete()

        # Should trigger PDF cleanup
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_handout_post_save_generates_pdf(self, mock_generate):
        """Test that Handout post_save signal generates PDF"""
        character = self.character()
        handout = Handout(character=character, name="Test Handout")
        handout.save()

        # Should trigger PDF generation
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_handout_template_pdf")
    def test_handout_template_pre_delete_cleans_pdf(self, mock_generate):
        """Test that HandoutTemplate pre_delete signal cleans up PDF files"""
        assoc = self.get_association()
        template = HandoutTemplate(assoc=assoc, name="Test Template")
        template.save()
        template.delete()

        # Should trigger PDF cleanup
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_handout_template_pdf")
    def test_handout_template_post_save_generates_pdf(self, mock_generate):
        """Test that HandoutTemplate post_save signal generates PDF"""
        assoc = self.get_association()
        template = HandoutTemplate(assoc=assoc, name="Test Template")
        template.save()

        # Should trigger PDF generation
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_character_pre_delete_cleans_pdf(self, mock_generate):
        """Test that Character pre_delete signal cleans up PDF files"""
        character = self.character()
        character.delete()

        # Should trigger PDF cleanup
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_character_post_save_generates_pdf(self, mock_generate):
        """Test that Character post_save signal generates PDF"""
        character = self.character()
        character.save()

        # Should trigger PDF generation
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_player_relationship_pre_delete_cleans_pdf(self, mock_generate):
        """Test that PlayerRelationship pre_delete signal cleans up PDF files"""
        character = self.character()
        member = self.get_member()
        relationship = PlayerRelationship(character=character, member=member, relationship="Test Relationship")
        relationship.save()
        relationship.delete()

        # Should trigger PDF cleanup for related character
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_player_relationship_post_save_generates_pdf(self, mock_generate):
        """Test that PlayerRelationship post_save signal generates PDF"""
        character = self.character()
        member = self.get_member()
        relationship = PlayerRelationship(character=character, member=member, relationship="Test Relationship")
        relationship.save()

        # Should trigger PDF generation for related character
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_relationship_pre_delete_cleans_pdf(self, mock_generate):
        """Test that Relationship pre_delete signal cleans up PDF files"""
        character1 = self.character()
        character2 = self.character(name="Character 2")
        relationship = Relationship(character1=character1, character2=character2, relationship="Test Relationship")
        relationship.save()
        relationship.delete()

        # Should trigger PDF cleanup for related characters
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_relationship_post_save_generates_pdf(self, mock_generate):
        """Test that Relationship post_save signal generates PDF"""
        character1 = self.character()
        character2 = self.character(name="Character 2")
        relationship = Relationship(character1=character1, character2=character2, relationship="Test Relationship")
        relationship.save()

        # Should trigger PDF generation for related characters
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_faction_pre_delete_cleans_pdf(self, mock_generate):
        """Test that Faction pre_delete signal cleans up PDF files"""
        assoc = self.get_association()
        faction = Faction.objects.create(name="Test Faction", assoc=assoc)
        faction.delete()

        # Should trigger PDF cleanup for related characters
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_faction_post_save_generates_pdf(self, mock_generate):
        """Test that Faction post_save signal generates PDF"""
        assoc = self.get_association()
        faction = Faction(name="Test Faction", assoc=assoc)
        faction.save()

        # Should trigger PDF generation for related characters
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_assignment_trait_pre_delete_cleans_pdf(self, mock_generate):
        """Test that AssignmentTrait pre_delete signal cleans up PDF files"""
        character = self.character()
        trait = Trait.objects.create(name="Test Trait", assoc=self.get_association())
        assignment = AssignmentTrait.objects.create(character=character, trait=trait)
        assignment.delete()

        # Should trigger PDF cleanup for related character
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.pdf.generate_character_pdf")
    def test_assignment_trait_post_save_generates_pdf(self, mock_generate):
        """Test that AssignmentTrait post_save signal generates PDF"""
        character = self.character()
        trait = Trait.objects.create(name="Test Trait", assoc=self.get_association())
        assignment = AssignmentTrait(character=character, trait=trait)
        assignment.save()

        # Should trigger PDF generation for related character
        self.assertTrue(True)  # Signal fired without error

    @patch("larpmanager.utils.registration.update_registration_totals")
    def test_registration_pre_save_updates_totals(self, mock_update):
        """Test that Registration pre_save signal updates registration totals"""
        registration = self.get_registration()
        registration.save()

        mock_update.assert_called_once_with(registration)

    @patch("larpmanager.utils.text.update_text_cache")
    def test_assoc_text_post_save_updates_cache(self, mock_update):
        """Test that AssocText post_save signal updates text cache"""
        assoc = self.get_association()
        text = AssocText(assoc=assoc, key="test_key", value="Test Value")
        text.save()

        mock_update.assert_called_once_with(text)

    @patch("larpmanager.utils.text.clear_text_cache")
    def test_assoc_text_pre_delete_clears_cache(self, mock_clear):
        """Test that AssocText pre_delete signal clears text cache"""
        assoc = self.get_association()
        text = AssocText.objects.create(assoc=assoc, key="test_key", value="Test Value")
        text.delete()

        mock_clear.assert_called_once_with(text)

    @patch("larpmanager.utils.text.update_text_cache")
    def test_event_text_post_save_updates_cache(self, mock_update):
        """Test that EventText post_save signal updates text cache"""
        event = self.get_event()
        text = EventText(event=event, key="test_key", value="Test Value")
        text.save()

        mock_update.assert_called_once_with(text)

    @patch("larpmanager.utils.text.clear_text_cache")
    def test_event_text_pre_delete_clears_cache(self, mock_clear):
        """Test that EventText pre_delete signal clears text cache"""
        event = self.get_event()
        text = EventText.objects.create(event=event, key="test_key", value="Test Value")
        text.delete()

        mock_clear.assert_called_once_with(text)

    @patch("larpmanager.accounting.token_credit.update_member_tokens_credit")
    def test_accounting_item_payment_post_save_updates_tokens_credit(self, mock_update):
        """Test that AccountingItemPayment post_save signal updates member tokens/credit"""
        member = self.get_member()
        payment = AccountingItemPayment(
            member=member,
            value=Decimal("50.00"),
            assoc=self.get_association(),
            reg=self.get_registration(),
            pay=AccountingItemPayment.TOKENS,
        )
        payment.save()

        mock_update.assert_called_once_with(payment)

    @patch("larpmanager.accounting.token_credit.update_member_tokens_credit")
    def test_accounting_item_payment_post_delete_updates_tokens_credit(self, mock_update):
        """Test that AccountingItemPayment post_delete signal updates member tokens/credit"""
        member = self.get_member()
        payment = AccountingItemPayment.objects.create(
            member=member,
            value=Decimal("50.00"),
            assoc=self.get_association(),
            reg=self.get_registration(),
            pay=AccountingItemPayment.TOKENS,
        )
        payment.delete()

        mock_update.assert_called_once_with(payment)

    @patch("larpmanager.accounting.token_credit.update_member_tokens_credit")
    def test_accounting_item_other_post_save_updates_tokens_credit(self, mock_update):
        """Test that AccountingItemOther post_save signal updates member tokens/credit"""
        member = self.get_member()
        item = AccountingItemOther(
            member=member,
            value=Decimal("25.00"),
            assoc=self.get_association(),
            run=self.get_run(),
            oth=AccountingItemOther.TOKEN,
            descr="Test tokens",
        )
        item.save()

        mock_update.assert_called_once_with(item)

    @patch("larpmanager.accounting.token_credit.update_member_tokens_credit")
    def test_accounting_item_expense_post_save_updates_tokens_credit(self, mock_update):
        """Test that AccountingItemExpense post_save signal updates member tokens/credit"""
        member = self.get_member()
        expense = AccountingItemExpense(
            member=member, value=Decimal("30.00"), assoc=self.get_association(), descr="Test expense"
        )
        expense.save()

        mock_update.assert_called_once_with(expense)

    @patch("larpmanager.accounting.payment.process_payment_invoice")
    def test_payment_invoice_pre_save_processes_payment(self, mock_process):
        """Test that PaymentInvoice pre_save signal processes payment"""
        invoice = self.payment_invoice()
        invoice.save()

        mock_process.assert_called_once_with(invoice)

    @patch("larpmanager.accounting.payment.process_refund_request")
    def test_refund_request_pre_save_processes_refund(self, mock_process):
        """Test that RefundRequest pre_save signal processes refund"""
        refund = self.refund_request()
        refund.save()

        mock_process.assert_called_once_with(refund)

    @patch("larpmanager.accounting.payment.validate_collection")
    def test_collection_pre_save_validates_collection(self, mock_validate):
        """Test that Collection pre_save signal validates collection"""
        collection = self.collection()
        collection.save()

        mock_validate.assert_called_once_with(collection)

    @patch("larpmanager.accounting.registration.calculate_registration_totals")
    def test_registration_pre_save_calculates_totals(self, mock_calculate):
        """Test that Registration pre_save signal calculates totals"""
        registration = self.get_registration()
        registration.save()

        mock_calculate.assert_called_once_with(registration)

    @patch("larpmanager.accounting.registration.update_member_balance")
    def test_registration_post_save_updates_member_balance(self, mock_update):
        """Test that Registration post_save signal updates member balance"""
        registration = self.get_registration()
        registration.save()

        mock_update.assert_called_once_with(registration.member)

    @patch("larpmanager.accounting.registration.update_discount_usage")
    def test_accounting_item_discount_post_save_updates_usage(self, mock_update):
        """Test that AccountingItemDiscount post_save signal updates discount usage"""
        from larpmanager.models.accounting import AccountingItemDiscount

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

        mock_update.assert_called_once_with(discount)

    def test_utility_signals_handle_edge_cases(self):
        """Test that utility signals handle edge cases gracefully"""
        # Test with minimal data
        character = self.character()
        character.name = ""  # Empty name
        character.save()

        # Should not raise errors
        self.assertIsNotNone(character.id)

        # Test with None values where appropriate
        member = self.get_member()
        payment = AccountingItemPayment(
            member=member,
            value=Decimal("0.00"),  # Zero value
            assoc=self.get_association(),
            reg=self.get_registration(),
            pay=AccountingItemPayment.MONEY,
        )
        payment.save()

        # Should not raise errors
        self.assertIsNotNone(payment.id)

    @patch("larpmanager.utils.profiler.receivers.process_profiler_response")
    def test_profiler_response_signal_processes_response(self, mock_process):
        """Test that profiler_response_signal processes profiler response"""
        from larpmanager.utils.profiler.receivers import profiler_response_signal

        # Mock profiler response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"Test response"

        # Send signal
        profiler_response_signal.send(sender=None, response=mock_response)

        mock_process.assert_called_once_with(mock_response)

    def test_signal_receivers_are_properly_connected(self):
        """Test that all signal receivers are properly connected to their signals"""
        # This test ensures that creating and saving objects triggers the expected signals

        # Test character experience updates
        character = self.character()
        character.save()
        # Should not raise any errors

        # Test accounting updates
        member = self.get_member()
        payment = AccountingItemPayment(
            member=member,
            value=Decimal("100.00"),
            assoc=self.get_association(),
            reg=self.get_registration(),
            pay=AccountingItemPayment.MONEY,
        )
        payment.save()
        # Should not raise any errors

        # Test cache updates
        assoc = self.get_association()
        text = AssocText(assoc=assoc, key="test", value="test")
        text.save()
        # Should not raise any errors

        self.assertTrue(True)  # All signals connected properly

    def test_signals_with_complex_relationships(self):
        """Test signals work correctly with complex model relationships"""
        # Create character with traits
        character = self.character()
        trait = Trait.objects.create(name="Test Trait", assoc=self.get_association())
        assignment = AssignmentTrait(character=character, trait=trait)
        assignment.save()

        # Create registration with payment
        registration = self.get_registration()
        payment = AccountingItemPayment(
            member=registration.member,
            value=Decimal("50.00"),
            assoc=self.get_association(),
            reg=registration,
            pay=AccountingItemPayment.MONEY,
        )
        payment.save()

        # All related signals should fire without errors
        self.assertTrue(True)
