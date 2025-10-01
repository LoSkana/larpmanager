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

"""Tests for model signal receivers in larpmanager.models.signals"""

from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth.models import User

from larpmanager.models.access import AssocPermission, EventPermission
from larpmanager.models.accounting import AccountingItemCollection, AccountingItemPayment, Collection
from larpmanager.models.association import Association, AssociationConfig
from larpmanager.models.casting import Trait
from larpmanager.models.event import Event, EventButton, EventConfig, Run, RunConfig
from larpmanager.models.form import RegistrationQuestion
from larpmanager.models.larpmanager import LarpManagerFaq, LarpManagerGuide, LarpManagerTicket, LarpManagerTutorial
from larpmanager.models.member import MemberConfig, Membership, MembershipStatus
from larpmanager.models.miscellanea import WarehouseItem
from larpmanager.models.registration import Registration
from larpmanager.models.writing import CharacterConfig, Faction, Plot, Prologue, SpeedLarp
from larpmanager.tests.unit.base import BaseTestCase


class TestModelSignals(BaseTestCase):
    """Test cases for model signal receivers"""

    def test_pre_save_callback_sets_number_for_event_scoped_models(self):
        """Test that pre_save_callback automatically sets number field for event-scoped models"""
        event = self.get_event()

        # Create first object - should get number 1
        plot1 = Plot(name="Test Plot 1", event=event)
        plot1.save()
        self.assertEqual(plot1.number, 1)

        # Create second object - should get number 2
        plot2 = Plot(name="Test Plot 2", event=event)
        plot2.save()
        self.assertEqual(plot2.number, 2)

    def test_pre_save_callback_sets_order_for_association_scoped_models(self):
        """Test that pre_save_callback automatically sets order field for association-scoped models"""
        assoc = self.get_association()

        # Create objects that should get auto-incremented order
        question1 = RegistrationQuestion(name="question1", description="Test", assoc=assoc)
        question1.save()
        self.assertEqual(question1.order, 1)

        question2 = RegistrationQuestion(name="question2", description="Test", assoc=assoc)
        question2.save()
        self.assertEqual(question2.order, 2)

    def test_association_pre_save_creates_slug(self):
        """Test that Association pre_save signal creates slug from name"""
        assoc = Association(name="Test Association Name", email="test@example.com")
        assoc.save()
        self.assertEqual(assoc.slug, "test-association-name")

    def test_assoc_permission_pre_save_creates_slug(self):
        """Test that AssocPermission pre_save signal creates slug"""
        assoc = self.get_association()
        member = self.get_member()

        perm = AssocPermission(name="Test Permission", assoc=assoc, member=member)
        perm.save()
        self.assertEqual(perm.slug, "test-permission")

    def test_event_permission_pre_save_creates_slug(self):
        """Test that EventPermission pre_save signal creates slug"""
        event = self.get_event()
        member = self.get_member()

        perm = EventPermission(name="Test Event Permission", event=event, member=member)
        perm.save()
        self.assertEqual(perm.slug, "test-event-permission")

    def test_plot_pre_save_creates_slug(self):
        """Test that Plot pre_save signal creates slug"""
        event = self.get_event()

        plot = Plot(name="Test Plot Name", event=event)
        plot.save()
        self.assertEqual(plot.slug, "test-plot-name")

    def test_faction_pre_save_creates_slug(self):
        """Test that Faction pre_save signal creates slug"""
        assoc = self.get_association()

        faction = Faction(name="Test Faction", assoc=assoc)
        faction.save()
        self.assertEqual(faction.slug, "test-faction")

    def test_prologue_pre_save_creates_slug(self):
        """Test that Prologue pre_save signal creates slug"""
        assoc = self.get_association()

        prologue = Prologue(name="Test Prologue", assoc=assoc)
        prologue.save()
        self.assertEqual(prologue.slug, "test-prologue")

    @patch("larpmanager.models.signals.reset_event_features")
    def test_run_post_save_resets_event_features_cache(self, mock_reset):
        """Test that Run post_save signal resets event features cache"""
        event = self.get_event()
        run = Run(event=event, number=1, start=date.today(), end=date.today())
        run.save()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.models.signals.update_traits_all")
    def test_trait_post_save_updates_traits_all(self, mock_update):
        """Test that Trait post_save signal calls update_traits_all"""
        assoc = self.get_association()
        trait = Trait(name="Test Trait", assoc=assoc)
        trait.save()

        mock_update.assert_called_once()

    def test_accounting_item_payment_post_save_updates_token_credit(self):
        """Test that AccountingItemPayment post_save signal updates member token/credit"""
        member = self.get_member()
        original_credit = member.membership.credit
        original_tokens = member.membership.tokens

        # Create a payment that should update tokens
        payment = AccountingItemPayment(
            member=member,
            value=Decimal("10.00"),
            assoc=self.get_association(),
            reg=self.get_registration(),
            pay=AccountingItemPayment.TOKENS,
        )
        payment.save()

        # Refresh member's membership
        member.membership.refresh_from_db()

        # Tokens should be reduced by payment amount
        self.assertEqual(member.membership.tokens, original_tokens - Decimal("10.00"))
        self.assertEqual(member.membership.credit, original_credit)

    def test_accounting_item_payment_pre_save_sets_member_from_registration(self):
        """Test that AccountingItemPayment pre_save signal sets member from registration"""
        registration = self.get_registration()

        payment = AccountingItemPayment(
            value=Decimal("50.00"), assoc=self.get_association(), reg=registration, pay=AccountingItemPayment.MONEY
        )
        payment.save()

        self.assertEqual(payment.member, registration.member)

    def test_collection_pre_save_creates_slug(self):
        """Test that Collection pre_save signal creates slug"""
        assoc = self.get_association()
        organizer = self.organizer()

        collection = Collection(name="Test Collection Name", assoc=assoc, organizer=organizer)
        collection.save()
        self.assertEqual(collection.slug, "test-collection-name")

    @patch("larpmanager.models.signals.my_send_mail")
    def test_accounting_item_collection_post_save_sends_notification(self, mock_mail):
        """Test that AccountingItemCollection post_save signal sends notification email"""
        collection = self.collection()
        member = self.get_member()

        item = AccountingItemCollection(
            member=member, value=Decimal("25.00"), assoc=self.get_association(), collection=collection
        )
        item.save()

        # Should send notification email
        self.assertTrue(mock_mail.called)

    def test_speed_larp_pre_save_creates_slug(self):
        """Test that SpeedLarp pre_save signal creates slug"""
        assoc = self.get_association()

        speed_larp = SpeedLarp(name="Test Speed Larp", assoc=assoc)
        speed_larp.save()
        self.assertEqual(speed_larp.slug, "test-speed-larp")

    def test_larp_manager_tutorial_pre_save_creates_slug(self):
        """Test that LarpManagerTutorial pre_save signal creates slug"""
        tutorial = LarpManagerTutorial(name="Test Tutorial")
        tutorial.save()
        self.assertEqual(tutorial.slug, "test-tutorial")

    def test_larp_manager_faq_pre_save_creates_slug(self):
        """Test that LarpManagerFaq pre_save signal creates slug"""
        faq = LarpManagerFaq(name="Test FAQ")
        faq.save()
        self.assertEqual(faq.slug, "test-faq")

    @patch("larpmanager.models.signals.my_send_mail")
    def test_user_post_save_sends_welcome_email(self, mock_mail):
        """Test that User post_save signal sends welcome email for new users"""
        # Create a new user (not using fixtures)
        user = User.objects.create_user(
            username="newuser", email="newuser@example.com", first_name="New", last_name="User"
        )

        # Should send welcome email for new user
        self.assertTrue(mock_mail.called)

    def test_membership_pre_save_sets_status_based_on_credit(self):
        """Test that Membership pre_save signal sets status based on credit amount"""
        member = self.get_member()
        assoc = self.get_association()

        # Create membership with negative credit
        membership = Membership(member=member, assoc=assoc, credit=Decimal("-50.00"), tokens=Decimal("0.00"))
        membership.save()

        self.assertEqual(membership.status, MembershipStatus.DEBTOR)

        # Update with positive credit
        membership.credit = Decimal("100.00")
        membership.save()

        self.assertEqual(membership.status, MembershipStatus.GOOD)

    @patch("larpmanager.models.signals.cache.delete")
    def test_event_button_post_save_clears_cache(self, mock_cache_delete):
        """Test that EventButton post_save signal clears button cache"""
        event = self.get_event()

        button = EventButton(event=event, name="Test Button", typ=EventButton.REGISTRATION)
        button.save()

        # Should clear the cache
        mock_cache_delete.assert_called()

    @patch("larpmanager.models.signals.cache.delete")
    def test_event_button_pre_delete_clears_cache(self, mock_cache_delete):
        """Test that EventButton pre_delete signal clears button cache"""
        event = self.get_event()

        button = EventButton.objects.create(event=event, name="Test Button", typ=EventButton.REGISTRATION)
        button.delete()

        # Should clear the cache
        mock_cache_delete.assert_called()

    def test_event_pre_save_creates_slug(self):
        """Test that Event pre_save signal creates slug"""
        assoc = self.get_association()

        event = Event(name="Test Event Name", assoc=assoc)
        event.save()
        self.assertEqual(event.slug, "test-event-name")

    @patch("larpmanager.models.signals.reset_event_features")
    @patch("larpmanager.models.signals.reset_event_fields_cache")
    def test_event_post_save_resets_caches(self, mock_reset_fields, mock_reset_features):
        """Test that Event post_save signal resets various caches"""
        assoc = self.get_association()

        event = Event(name="Test Event", assoc=assoc)
        event.save()

        # Should reset both caches
        mock_reset_features.assert_called_once_with(event.id)
        mock_reset_fields.assert_called_once_with(event.id)

    @patch("larpmanager.models.signals.my_send_mail")
    def test_registration_post_save_sends_confirmation_email(self, mock_mail):
        """Test that Registration post_save signal sends confirmation email"""
        member = self.get_member()
        run = self.get_run()

        registration = Registration(
            member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"), quotas=1
        )
        registration.save()

        # Should send confirmation email
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.models.signals.reset_configs")
    def test_event_config_post_save_resets_configs(self, mock_reset):
        """Test that EventConfig post_save signal resets configs cache"""
        event = self.get_event()

        config = EventConfig(event=event, key="test_key", value="test_value")
        config.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_configs")
    def test_event_config_post_delete_resets_configs(self, mock_reset):
        """Test that EventConfig post_delete signal resets configs cache"""
        event = self.get_event()

        config = EventConfig.objects.create(event=event, key="test_key", value="test_value")
        config.delete()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_configs")
    def test_association_config_post_save_resets_configs(self, mock_reset):
        """Test that AssociationConfig post_save signal resets configs cache"""
        assoc = self.get_association()

        config = AssociationConfig(assoc=assoc, key="test_key", value="test_value")
        config.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_configs")
    def test_association_config_post_delete_resets_configs(self, mock_reset):
        """Test that AssociationConfig post_delete signal resets configs cache"""
        assoc = self.get_association()

        config = AssociationConfig.objects.create(assoc=assoc, key="test_key", value="test_value")
        config.delete()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_configs")
    def test_run_config_post_save_resets_configs(self, mock_reset):
        """Test that RunConfig post_save signal resets configs cache"""
        run = self.get_run()

        config = RunConfig(run=run, key="test_key", value="test_value")
        config.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_configs")
    def test_run_config_post_delete_resets_configs(self, mock_reset):
        """Test that RunConfig post_delete signal resets configs cache"""
        run = self.get_run()

        config = RunConfig.objects.create(run=run, key="test_key", value="test_value")
        config.delete()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_configs")
    def test_member_config_post_save_resets_configs(self, mock_reset):
        """Test that MemberConfig post_save signal resets configs cache"""
        member = self.get_member()

        config = MemberConfig(member=member, key="test_key", value="test_value")
        config.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_configs")
    def test_member_config_post_delete_resets_configs(self, mock_reset):
        """Test that MemberConfig post_delete signal resets configs cache"""
        member = self.get_member()

        config = MemberConfig.objects.create(member=member, key="test_key", value="test_value")
        config.delete()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_configs")
    def test_character_config_post_save_resets_configs(self, mock_reset):
        """Test that CharacterConfig post_save signal resets configs cache"""
        character = self.character()

        config = CharacterConfig(character=character, key="test_key", value="test_value")
        config.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_configs")
    def test_character_config_post_delete_resets_configs(self, mock_reset):
        """Test that CharacterConfig post_delete signal resets configs cache"""
        character = self.character()

        config = CharacterConfig.objects.create(character=character, key="test_key", value="test_value")
        config.delete()

        mock_reset.assert_called_once()

    def test_association_pre_save_creates_default_values(self):
        """Test that Association pre_save signal creates default values"""
        assoc = Association(name="New Association", email="new@example.com")
        assoc.save()

        # Should have created default slug and other auto-generated fields
        self.assertEqual(assoc.slug, "new-association")
        self.assertIsNotNone(assoc.id)

    @patch("larpmanager.models.signals.get_assoc_features")
    def test_association_post_save_updates_features(self, mock_get_features):
        """Test that Association post_save signal updates features"""
        mock_get_features.return_value = []

        assoc = Association(name="Test Association", email="test@example.com")
        assoc.save()

        # Should call get_assoc_features to update features
        mock_get_features.assert_called()

    @patch("larpmanager.models.signals.index_tutorial")
    def test_larp_manager_tutorial_post_save_indexes_tutorial(self, mock_index):
        """Test that LarpManagerTutorial post_save signal indexes tutorial"""
        tutorial = LarpManagerTutorial(name="Test Tutorial")
        tutorial.save()

        mock_index.assert_called_once_with(tutorial)

    @patch("larpmanager.models.signals.delete_index_tutorial")
    def test_larp_manager_tutorial_post_delete_removes_index(self, mock_delete_index):
        """Test that LarpManagerTutorial post_delete signal removes tutorial from index"""
        tutorial = LarpManagerTutorial.objects.create(name="Test Tutorial")
        tutorial.delete()

        mock_delete_index.assert_called_once_with(tutorial)

    @patch("larpmanager.models.signals.index_guide")
    def test_larp_manager_guide_post_save_indexes_guide(self, mock_index):
        """Test that LarpManagerGuide post_save signal indexes guide"""
        guide = LarpManagerGuide(name="Test Guide")
        guide.save()

        mock_index.assert_called_once_with(guide)

    @patch("larpmanager.models.signals.delete_index_guide")
    def test_larp_manager_guide_post_delete_removes_index(self, mock_delete_index):
        """Test that LarpManagerGuide post_delete signal removes guide from index"""
        guide = LarpManagerGuide.objects.create(name="Test Guide")
        guide.delete()

        mock_delete_index.assert_called_once_with(guide)

    @patch("larpmanager.models.signals.reset_event_fields_cache")
    def test_writing_question_post_save_resets_cache(self, mock_reset):
        """Test that WritingQuestion post_save signal resets event fields cache"""
        from larpmanager.models.form import WritingQuestion

        event = self.get_event()
        question = WritingQuestion(event=event, name="test_question", description="Test")
        question.save()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.models.signals.reset_event_fields_cache")
    def test_writing_question_pre_delete_resets_cache(self, mock_reset):
        """Test that WritingQuestion pre_delete signal resets event fields cache"""
        from larpmanager.models.form import WritingQuestion

        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test")
        question.delete()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.models.signals.my_send_mail")
    def test_larp_manager_ticket_post_save_sends_notification(self, mock_mail):
        """Test that LarpManagerTicket post_save signal sends notification"""
        member = self.get_member()

        ticket = LarpManagerTicket(
            member=member, subject="Test Ticket", message="Test message", typ=LarpManagerTicket.BUG
        )
        ticket.save()

        # Should send notification email
        self.assertTrue(mock_mail.called)

    @patch("larpmanager.models.signals.PILImage.open")
    def test_warehouse_item_pre_save_rotates_vertical_photo(self, mock_pil):
        """Test that WarehouseItem pre_save signal rotates vertical photos"""
        # Mock PIL Image operations
        mock_image = Mock()
        mock_image._getexif.return_value = {274: 6}  # Orientation: Rotate 90 CW
        mock_pil.return_value = mock_image

        assoc = self.get_association()
        item = WarehouseItem(name="Test Item", assoc=assoc)

        # Mock the photo field
        from django.core.files.uploadedfile import SimpleUploadedFile

        photo_file = SimpleUploadedFile("test.jpg", b"fake image content", content_type="image/jpeg")
        item.photo = photo_file

        item.save()

        # Should attempt to open image for rotation
        self.assertTrue(mock_pil.called)

    @patch("larpmanager.models.signals.my_send_mail")
    def test_registration_post_save_automatic_accounting(self, mock_mail):
        """Test that Registration post_save signal handles automatic accounting"""
        member = self.get_member()
        run = self.get_run()

        # Set up event with automatic accounting
        run.event.automatic_accounting = True
        run.event.save()

        registration = Registration(
            member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"), quotas=1
        )
        registration.save()

        # Should handle automatic accounting operations
        self.assertTrue(mock_mail.called)
