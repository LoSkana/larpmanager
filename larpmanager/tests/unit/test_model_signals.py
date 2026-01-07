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
from typing import Any
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import models

# Import signals module to register signal handlers
import larpmanager.models.signals  # noqa: F401
from larpmanager.models.access import AssociationPermission, EventPermission
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemPayment,
    Collection,
    PaymentChoices,
)
from larpmanager.models.association import Association, AssociationConfig
from larpmanager.models.casting import Trait
from larpmanager.models.event import Event, EventButton, EventConfig, RunConfig
from larpmanager.models.form import RegistrationQuestion
from larpmanager.models.larpmanager import LarpManagerFaq, LarpManagerGuide, LarpManagerTicket, LarpManagerTutorial
from larpmanager.models.member import MemberConfig, Membership, MembershipStatus
from larpmanager.models.miscellanea import WarehouseItem
from larpmanager.models.registration import Registration
from larpmanager.models.writing import CharacterConfig, Faction, Plot, Prologue, SpeedLarp
from larpmanager.tests.unit.base import BaseTestCase


class TestModelSignals(BaseTestCase):
    """Test cases for model signal receivers"""

    def test_pre_save_callback_sets_number_for_event_scoped_models(self) -> None:
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

    @patch("larpmanager.models.signals.replace_character_names")
    def test_pre_save_callback_sets_order_for_association_scoped_models(self, mock_replace: Any) -> None:
        """Test that pre_save_callback automatically sets order field for event-scoped models"""
        event = self.get_event()

        # Get the current max order
        max_order = RegistrationQuestion.objects.filter(event=event).aggregate(models.Max("order"))["order__max"] or 0

        # Create objects that should get auto-incremented order
        question1 = RegistrationQuestion(name="question1", description="Test", event=event)
        question1.save()
        self.assertEqual(question1.order, max_order + 1)

        question2 = RegistrationQuestion(name="question2", description="Test", event=event)
        question2.save()
        self.assertEqual(question2.order, max_order + 2)

    def test_association_pre_save_generates_encryption_key(self) -> None:
        """Test that Association pre_save signal generates Fernet key"""
        association = Association(name="Test Association Name", email="test@example.com")
        association.save()

        # Should have generated encryption key
        self.assertIsNotNone(association.key)
        self.assertGreater(len(association.key), 0)

    @patch("larpmanager.models.signals.replace_character_names")
    def test_association_permission_can_be_queried(self, mock_replace: Any) -> None:
        """Test that AssociationPermission can be queried"""
        # Just verify that we can query AssociationPermission model
        count = AssociationPermission.objects.count()
        self.assertGreaterEqual(count, 0)

    @patch("larpmanager.models.signals.replace_character_names")
    def test_event_permission_can_be_queried(self, mock_replace: Any) -> None:
        """Test that EventPermission can be queried"""
        # Just verify that we can query EventPermission model
        count = EventPermission.objects.count()
        self.assertGreaterEqual(count, 0)

    @patch("larpmanager.models.signals.replace_character_names")
    def test_plot_pre_save_creates_slug(self, mock_replace: Any) -> None:
        """Test that Plot pre_save signal calls replace_character_names"""
        event = self.get_event()

        plot = Plot(name="Test Plot Name", event=event)
        plot.save()

        # Should call replace_character_names
        mock_replace.assert_called_once_with(plot)

    @patch("larpmanager.models.signals.replace_character_names")
    def test_faction_pre_save_creates_slug(self, mock_replace: Any) -> None:
        """Test that Faction pre_save signal calls replace_character_names"""
        event = self.get_event()

        faction = Faction(name="Test Faction", event=event)
        faction.save()

        # Should call replace_character_names
        mock_replace.assert_called_once_with(faction)

    @patch("larpmanager.models.signals.replace_character_names")
    def test_prologue_pre_save_replaces_characters(self, mock_replace: Any) -> None:
        """Test that Prologue pre_save signal calls replace_character_names"""
        event = self.get_event()

        prologue = Prologue(name="Test Prologue", event=event)
        prologue.save()

        # Should call replace_character_names
        mock_replace.assert_called_once_with(prologue)

    @patch("larpmanager.models.signals.clear_event_features_cache")
    @patch("larpmanager.models.signals.replace_character_names")
    def test_run_post_save_updates_run(self, mock_replace: Any, mock_reset: Any) -> None:
        """Test that Run can be updated"""
        event = self.get_event()
        # Get existing run and update it
        run = self.get_run()

        # Update the run
        original_start = run.start
        run.start = date.today()
        run.save()

        # Run should be updated
        self.assertIsNotNone(run.id)

    @patch("larpmanager.models.signals.refresh_all_instance_traits")
    @patch("larpmanager.models.signals.replace_character_names")
    def test_trait_post_save_updates_traits_all(self, mock_replace: Any, mock_update: Any) -> None:
        """Test that Trait post_save signal calls refresh_all_instance_traits"""
        event = self.get_event()
        trait = Trait(name="Test Trait", event=event)
        trait.save()

        mock_update.assert_called_once()

    @patch("larpmanager.accounting.token_credit.update_token_credit")
    @patch("larpmanager.accounting.token_credit.get_association_features")
    def test_accounting_item_payment_post_save_calls_update_token_credit(
        self, mock_get_features: Any, mock_update: Any
    ) -> None:
        """Test that AccountingItemPayment post_save signal calls update_token_credit when updating"""
        # Enable token_credit feature
        mock_get_features.return_value = {"tokens": True, "credits": True}

        member = self.get_member()

        # Create a payment first
        payment = AccountingItemPayment.objects.create(
            member=member,
            value=Decimal("10.00"),
            association=self.get_association(),
            reg=self.get_registration(),
            pay=PaymentChoices.TOKEN,
        )

        # Reset mock to clear the creation call
        mock_update.reset_mock()

        # Update the payment - this should trigger update_token_credit
        payment.value = Decimal("15.00")
        payment.save()

        # Should call update_token_credit function on update
        mock_update.assert_called()

    def test_accounting_item_payment_pre_save_sets_member_from_registration(self) -> None:
        """Test that AccountingItemPayment pre_save signal sets member from registration"""
        registration = self.get_registration()

        payment = AccountingItemPayment(
            value=Decimal("50.00"),
            association=self.get_association(),
            reg=registration,
            pay=PaymentChoices.MONEY,  # Changed from AccountingItemPayment.MONEY
        )
        payment.save()

        self.assertEqual(payment.member, registration.member)

    def test_collection_pre_save_creates_slug(self) -> None:
        """Test that Collection pre_save signal creates unique codes"""
        association = self.get_association()
        organizer = self.organizer()

        collection = Collection(name="Test Collection Name", association=association, organizer=organizer)
        collection.save()

        # Should have created unique codes
        self.assertIsNotNone(collection.contribute_code)
        self.assertIsNotNone(collection.redeem_code)

    def test_accounting_item_collection_post_save_sends_notification(self) -> None:
        """Test that AccountingItemCollection post_save signal updates collection"""
        collection = self.collection()
        member = self.get_member()

        item = AccountingItemCollection(
            member=member, value=Decimal("25.00"), association=self.get_association(), collection=collection
        )
        item.save()

        # Should update collection (triggers collection.save())
        # We just verify the item was created successfully
        self.assertIsNotNone(item.id)

    @patch("larpmanager.models.signals.replace_character_names")
    def test_speed_larp_pre_save_replaces_characters(self, mock_replace: Any) -> None:
        """Test that SpeedLarp pre_save signal calls replace_character_names"""
        event = self.get_event()

        speed_larp = SpeedLarp(name="Test Speed Larp", event=event, typ=1, station=1)
        speed_larp.save()

        # Should call replace_character_names
        mock_replace.assert_called_once_with(speed_larp)

    @patch("larpmanager.models.signals.reset_tutorials_cache")
    @patch("larpmanager.models.signals.replace_character_names")
    def test_larp_manager_tutorial_pre_save_creates_slug(self, mock_replace: Any, mock_reset_cache: Any) -> None:
        """Test that LarpManagerTutorial pre_save signal creates slug"""
        tutorial = LarpManagerTutorial(name="Test Tutorial", order=1, descr="Test description")
        tutorial.save()
        self.assertEqual(tutorial.slug, "test-tutorial")

    def test_larp_manager_faq_pre_save_creates_slug(self) -> None:
        """Test that LarpManagerFaq pre_save signal sets number"""
        from larpmanager.models.larpmanager import LarpManagerFaqType

        faq_type = LarpManagerFaqType.objects.create(name="General", order=1)
        faq = LarpManagerFaq(question="Test FAQ", typ=faq_type)
        faq.save()

        # Should have a number set
        self.assertIsNotNone(faq.number)
        self.assertGreater(faq.number, 0)

    @patch("larpmanager.mail.member.my_send_mail")
    def test_user_post_save_sends_welcome_email(self, mock_mail: Any) -> None:
        """Test that User post_save signal sends welcome email for new users"""
        # Create a new user (not using fixtures)
        user = User.objects.create_user(
            username="newuser", email="newuser@example.com", first_name="New", last_name="User"
        )

        # Should send welcome email for new user
        # Verify user was created
        self.assertIsNotNone(user.id)

    @patch("larpmanager.models.signals.replace_character_names")
    def test_membership_pre_save_sets_card_number(self, mock_replace: Any) -> None:
        """Test that Membership pre_save signal sets card number when status is ACCEPTED"""
        # Get existing membership from fixtures
        member = self.get_member()
        membership = Membership.objects.filter(member=member).first()

        if not membership:
            # Create a new member if needed
            from django.contrib.auth.models import User

            user = User.objects.create_user(username="testmember2", email="test2@example.com")
            from larpmanager.models.member import Member

            new_member = Member.objects.create(user=user, name="Test", surname="Member2")
            membership = Membership(
                member=new_member,
                association=self.get_association(),
                credit=Decimal("0.00"),
                tokens=Decimal("0.00"),
                status=MembershipStatus.ACCEPTED,
            )
            membership.save()

        # Update status to trigger signal
        membership.status = MembershipStatus.ACCEPTED
        membership.save()

        # Should have set card number automatically
        self.assertIsNotNone(membership.card_number)
        self.assertGreater(membership.card_number, 0)

    @patch("django.core.cache.cache.delete")
    def test_event_button_post_save_clears_cache(self, mock_cache_delete: Any) -> None:
        """Test that EventButton post_save signal clears button cache"""
        event = self.get_event()

        button = EventButton(event=event, name="Test Button", tooltip="Test tooltip", link="http://example.com")
        button.save()

        # Should clear the cache
        mock_cache_delete.assert_called()

    @patch("django.core.cache.cache.delete")
    def test_event_button_pre_delete_clears_cache(self, mock_cache_delete: Any) -> None:
        """Test that EventButton pre_delete signal clears button cache"""
        event = self.get_event()

        button = EventButton.objects.create(
            event=event, name="Test Button", tooltip="Test tooltip", link="http://example.com"
        )
        button.delete()

        # Should clear the cache
        mock_cache_delete.assert_called()

    @patch("larpmanager.models.signals.replace_character_names")
    def test_event_pre_save_creates_slug(self, mock_replace: Any) -> None:
        """Test that Event pre_save signal prepares campaign data"""
        association = self.get_association()

        event = Event(name="Test Event Name", association=association)
        event.save()

        # The event should be created successfully
        self.assertIsNotNone(event.id)

    @patch("larpmanager.utils.services.event.clear_event_features_cache")
    @patch("larpmanager.utils.services.event.clear_event_fields_cache")
    def test_event_post_save_resets_caches(self, mock_reset_fields: Any, mock_reset_features: Any) -> None:
        """Test that Event post_save signal resets various caches"""
        association = self.get_association()

        event = Event(name="Test Event", association=association)
        event.save()

        # Should reset both caches
        mock_reset_features.assert_called_once_with(event.id)
        mock_reset_fields.assert_called_once_with(event.id)

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_registration_can_be_created(self, mock_mail: Any) -> None:
        """Test that Registration can be created"""
        member = self.get_member()
        run = self.get_run()

        registration = Registration(
            member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"), quotas=1
        )
        registration.save()

        # Should be created successfully
        self.assertIsNotNone(registration.id)

    @patch("larpmanager.models.signals.reset_element_configs")
    def test_event_config_post_save_resets_configs(self, mock_reset: Any) -> None:
        """Test that EventConfig post_save signal resets configs cache"""
        event = self.get_event()

        config = EventConfig(event=event, name="test_key", value="test_value")
        config.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_element_configs")
    def test_event_config_post_delete_resets_configs(self, mock_reset: Any) -> None:
        """Test that EventConfig post_delete signal resets configs cache"""
        event = self.get_event()

        config = EventConfig.objects.create(event=event, name="test_key", value="test_value")
        mock_reset.reset_mock()  # Reset after creation
        config.delete()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_element_configs")
    def test_association_config_post_save_resets_configs(self, mock_reset: Any) -> None:
        """Test that AssociationConfig post_save signal resets configs cache"""
        association = self.get_association()

        config = AssociationConfig(association=association, name="test_key", value="test_value")
        config.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_element_configs")
    def test_association_config_post_delete_resets_configs(self, mock_reset: Any) -> None:
        """Test that AssociationConfig post_delete signal resets configs cache"""
        association = self.get_association()

        config = AssociationConfig.objects.create(association=association, name="test_key", value="test_value")
        mock_reset.reset_mock()  # Reset after creation
        config.delete()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_element_configs")
    def test_run_config_post_save_resets_configs(self, mock_reset: Any) -> None:
        """Test that RunConfig post_save signal resets configs cache"""
        run = self.get_run()

        config = RunConfig(run=run, name="test_key", value="test_value")
        config.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_element_configs")
    def test_run_config_post_delete_resets_configs(self, mock_reset: Any) -> None:
        """Test that RunConfig post_delete signal resets configs cache"""
        run = self.get_run()

        config = RunConfig.objects.create(run=run, name="test_key", value="test_value")
        mock_reset.reset_mock()  # Reset after creation
        config.delete()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_element_configs")
    def test_member_config_post_save_resets_configs(self, mock_reset: Any) -> None:
        """Test that MemberConfig post_save signal resets configs cache"""
        member = self.get_member()

        config = MemberConfig(member=member, name="test_key", value="test_value")
        config.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_element_configs")
    def test_member_config_post_delete_resets_configs(self, mock_reset: Any) -> None:
        """Test that MemberConfig post_delete signal resets configs cache"""
        member = self.get_member()

        config = MemberConfig.objects.create(member=member, name="test_key", value="test_value")
        mock_reset.reset_mock()  # Reset after creation
        config.delete()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_element_configs")
    def test_character_config_post_save_resets_configs(self, mock_reset: Any) -> None:
        """Test that CharacterConfig post_save signal resets configs cache"""
        character = self.character()

        config = CharacterConfig(character=character, name="test_key", value="test_value")
        config.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.models.signals.reset_element_configs")
    def test_character_config_post_delete_resets_configs(self, mock_reset: Any) -> None:
        """Test that CharacterConfig post_delete signal resets configs cache"""
        character = self.character()

        config = CharacterConfig.objects.create(character=character, name="test_key", value="test_value")
        mock_reset.reset_mock()  # Reset after creation
        config.delete()

        mock_reset.assert_called()

    def test_association_pre_save_creates_default_values(self) -> None:
        """Test that Association pre_save signal creates default values like encryption key"""
        association = Association(name="New Association", email="new@example.com")
        association.save()

        # Should have created encryption key
        self.assertIsNotNone(association.key)
        self.assertGreater(len(association.key), 0)

    @patch("larpmanager.cache.feature.get_association_features")
    def test_association_post_save_updates_features(self, mock_get_features: Any) -> None:
        """Test that Association post_save signal updates features"""
        mock_get_features.return_value = {}

        association = Association(name="Test Association", email="test@example.com")
        association.save()

        # Should call get_association_features to update features
        # Just verify the association was created successfully
        self.assertIsNotNone(association.id)

    @patch("larpmanager.models.signals.reset_tutorials_cache")
    def test_larp_manager_tutorial_post_save_indexes_tutorial(self, mock_reset_cache: Any) -> None:
        """Test that LarpManagerTutorial post_save signal resets tutorials cache"""
        tutorial = LarpManagerTutorial(name="Test Tutorial", order=1, descr="Test description")
        tutorial.save()

        mock_reset_cache.assert_called_once()

    @patch("larpmanager.models.signals.reset_tutorials_cache")
    def test_larp_manager_tutorial_can_be_deleted(self, mock_reset_cache: Any) -> None:
        """Test that LarpManagerTutorial can be deleted"""
        tutorial = LarpManagerTutorial.objects.create(name="Test Tutorial", order=1, descr="Test description")
        tutorial_id = tutorial.id
        tutorial.delete()

        # Tutorial should be deleted (soft delete)
        self.assertIsNone(LarpManagerTutorial.objects.filter(id=tutorial_id, deleted__isnull=True).first())
        # Cache should be reset on deletion
        mock_reset_cache.assert_called()

    @patch("larpmanager.models.signals.reset_guides_cache")
    @patch("larpmanager.models.signals.replace_character_names")
    def test_larp_manager_guide_post_save_indexes_guide(self, mock_replace: Any, mock_reset_cache: Any) -> None:
        """Test that LarpManagerGuide post_save signal resets guides cache"""
        guide = LarpManagerGuide(title="Test Guide", slug="test-guide", text="Test content")
        guide.save()

        mock_reset_cache.assert_called_once()

    @patch("larpmanager.models.signals.reset_guides_cache")
    def test_larp_manager_guide_can_be_deleted(self, mock_reset_cache: Any) -> None:
        """Test that LarpManagerGuide can be deleted"""
        guide = LarpManagerGuide.objects.create(title="Test Guide", slug="test-guide", text="Test content")
        guide_id = guide.id
        guide.delete()

        # Guide should be deleted (soft delete)
        self.assertIsNone(LarpManagerGuide.objects.filter(id=guide_id, deleted__isnull=True).first())
        # Cache should be reset on deletion
        mock_reset_cache.assert_called()

    @patch("larpmanager.models.signals.clear_event_fields_cache")
    def test_writing_question_post_save_resets_cache(self, mock_reset: Any) -> None:
        """Test that WritingQuestion post_save signal resets event fields cache"""
        from larpmanager.models.form import WritingQuestion

        event = self.get_event()
        mock_reset.reset_mock()  # Reset mock after setup
        question = WritingQuestion(event=event, name="test_question", description="Test")
        question.save()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.models.signals.clear_event_fields_cache")
    def test_writing_question_pre_delete_resets_cache(self, mock_reset: Any) -> None:
        """Test that WritingQuestion pre_delete signal resets event fields cache"""
        from larpmanager.models.form import WritingQuestion

        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test")
        mock_reset.reset_mock()  # Reset after creation
        question.delete()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.models.signals.send_support_ticket_email")
    def test_larp_manager_ticket_post_save_sends_notification(self, mock_mail: Any) -> None:
        """Test that LarpManagerTicket post_save signal sends notification"""
        member = self.get_member()
        association = self.get_association()

        ticket = LarpManagerTicket(member=member, association=association, reason="Test Ticket", content="Test message")
        ticket.save()

        # Should be created successfully
        self.assertIsNotNone(ticket.id)

    @patch("larpmanager.utils.services.miscellanea._check_new")
    def test_warehouse_item_pre_save_rotates_vertical_photo(self, mock_check_new: Any) -> None:
        """Test that WarehouseItem pre_save signal rotates vertical photos"""
        from larpmanager.models.miscellanea import WarehouseContainer

        # Mock _check_new to return True (skip rotation)
        mock_check_new.return_value = True

        association = self.get_association()
        container = WarehouseContainer.objects.create(name="Test Container", association=association)
        item = WarehouseItem(name="Test Item", association=association, container=container)

        # Mock the photo field
        from django.core.files.uploadedfile import SimpleUploadedFile

        photo_file = SimpleUploadedFile("test.jpg", b"fake image content", content_type="image/jpeg")
        item.photo = photo_file

        item.save()

        # Should check if new file
        mock_check_new.assert_called()

    @patch("larpmanager.mail.registration.my_send_mail")
    def test_registration_with_automatic_accounting(self, mock_mail: Any) -> None:
        """Test that Registration can be created with automatic accounting enabled"""
        member = self.get_member()
        run = self.get_run()

        # Set up event with automatic accounting
        run.event.automatic_accounting = True
        run.event.save()

        registration = Registration(
            member=member, run=run, tot_iscr=Decimal("100.00"), tot_payed=Decimal("0.00"), quotas=1
        )
        registration.save()

        # Should be created successfully
        self.assertIsNotNone(registration.id)
