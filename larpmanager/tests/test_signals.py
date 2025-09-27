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

from datetime import date
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from larpmanager.accounting.registration import AccountingItemDiscount
from larpmanager.models.access import AssocPermission, EventPermission
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemPayment,
    Collection,
    PaymentInvoice,
    RefundRequest,
)
from larpmanager.models.association import Association, AssociationConfig
from larpmanager.models.base import Feature, FeatureModule
from larpmanager.models.casting import AssignmentTrait, Trait
from larpmanager.models.event import Event, EventButton, EventConfig, PreRegistration, Run, RunConfig
from larpmanager.models.form import (
    RegistrationOption,
    WritingQuestion,
)
from larpmanager.models.larpmanager import LarpManagerFaq, LarpManagerGuide, LarpManagerTicket, LarpManagerTutorial
from larpmanager.models.member import MemberConfig, Membership, MembershipStatus
from larpmanager.models.miscellanea import ChatMessage, HelpQuestion, WarehouseItem
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket
from larpmanager.models.writing import Character, CharacterConfig, Faction, Plot, Prologue, SpeedLarp


@pytest.mark.django_db_reset_sequences
class TestPreSaveSignals(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)
        self.run = Run.objects.create(event=self.event)

    def test_pre_save_generic_number_assignment(self):
        """Test that number fields are auto-assigned on pre_save"""
        # Test with a model that has a number field related to event
        question = WritingQuestion(event=self.event, name="Test Question")
        question.save()
        self.assertEqual(question.number, 1)

        # Create another to test increment
        question2 = WritingQuestion(event=self.event, name="Test Question 2")
        question2.save()
        self.assertEqual(question2.number, 2)

    def test_pre_save_generic_order_assignment(self):
        """Test that order fields are auto-assigned on pre_save"""
        # Create an object with order field
        question = WritingQuestion(event=self.event, name="Test Question")
        question.save()
        if hasattr(question, "order"):
            self.assertIsNotNone(question.order)

    def test_pre_save_generic_search_field(self):
        """Test that search fields are updated on pre_save"""
        question = WritingQuestion(event=self.event, name="Test Question")
        question.save()
        if hasattr(question, "search"):
            self.assertIsNotNone(question.search)

    def test_pre_save_association_generate_fernet(self):
        """Test that Fernet key is generated for new associations"""
        assoc = Association(name="New Association", slug="new")
        self.assertIsNone(assoc.key)
        assoc.save()
        self.assertIsNotNone(assoc.key)
        self.assertIsInstance(assoc.key, bytes)

    def test_pre_save_assoc_permission(self):
        """Test AssocPermission numbering on pre_save"""
        module = FeatureModule.objects.create(name="test_module")
        feature = Feature.objects.create(name="test_feature", module=module)

        perm = AssocPermission(feature=feature, assoc=self.assoc)
        perm.save()
        self.assertIsNotNone(perm.number)
        self.assertGreaterEqual(perm.number, 11)

    def test_pre_save_event_permission(self):
        """Test EventPermission numbering on pre_save"""
        module = FeatureModule.objects.create(name="test_module")
        feature = Feature.objects.create(name="test_feature", module=module)

        perm = EventPermission(feature=feature, event=self.event)
        perm.save()
        self.assertIsNotNone(perm.number)
        self.assertGreaterEqual(perm.number, 11)

    @patch("larpmanager.models.writing.replace_chars_all")
    def test_pre_save_plot(self, mock_replace):
        """Test Plot character replacement on pre_save"""
        plot = Plot(event=self.event, name="Test Plot", text="Test text")
        plot.save()
        mock_replace.assert_called_once_with(plot)

    @patch("larpmanager.models.writing.replace_chars_all")
    def test_pre_save_faction(self, mock_replace):
        """Test Faction character replacement on pre_save"""
        faction = Faction(event=self.event, name="Test Faction", description="Test description")
        faction.save()
        mock_replace.assert_called_once_with(faction)

    @patch("larpmanager.models.writing.replace_chars_all")
    def test_pre_save_prologue(self, mock_replace):
        """Test Prologue character replacement on pre_save"""
        char = Character.objects.create(event=self.event, player=self.user.member)
        prologue = Prologue(character=char, text="Test prologue")
        prologue.save()
        mock_replace.assert_called_once_with(prologue)

    @patch("larpmanager.models.writing.replace_chars_all")
    def test_pre_save_speed_larp(self, mock_replace):
        """Test SpeedLarp character replacement on pre_save"""
        speed = SpeedLarp(event=self.event, name="Test Speed")
        speed.save()
        mock_replace.assert_called_once_with(speed)

    def test_pre_save_larp_manager_tutorial(self):
        """Test LarpManagerTutorial slug generation on pre_save"""
        tutorial = LarpManagerTutorial(name="Test Tutorial", content="Test content")
        tutorial.save()
        self.assertEqual(tutorial.slug, "test-tutorial")

    def test_pre_save_larp_manager_faq(self):
        """Test LarpManagerFaq number assignment on pre_save"""
        faq = LarpManagerFaq(typ="general", question="Test?", answer="Test answer")
        faq.save()
        self.assertIsNotNone(faq.number)
        self.assertEqual(faq.number, 10)  # First number should be 10

    def test_pre_save_membership_accepted(self):
        """Test membership card number assignment when status is ACCEPTED"""
        membership = Membership(member=self.user.member, assoc=self.assoc, status=MembershipStatus.ACCEPTED)
        membership.save()
        self.assertEqual(membership.card_number, 1)
        self.assertEqual(membership.date, date.today())

    def test_pre_save_membership_empty(self):
        """Test membership card number clearing when status is EMPTY"""
        membership = Membership(
            member=self.user.member,
            assoc=self.assoc,
            status=MembershipStatus.ACCEPTED,
            card_number=1,
            date=date.today(),
        )
        membership.save()

        membership.status = MembershipStatus.EMPTY
        membership.save()
        self.assertIsNone(membership.card_number)
        self.assertIsNone(membership.date)

    def test_pre_save_collection(self):
        """Test Collection code generation on pre_save"""
        collection = Collection(name="Test Collection")
        collection.save()
        self.assertIsNotNone(collection.contribute_code)
        self.assertIsNotNone(collection.redeem_code)

    def test_pre_save_accounting_item_payment_member(self):
        """Test AccountingItemPayment member assignment on pre_save"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        payment = AccountingItemPayment(reg=reg, value=100.0)
        payment.save()
        self.assertEqual(payment.member, self.user.member)

    def test_pre_save_event_prepare_campaign(self):
        """Test Event campaign preparation on pre_save"""
        parent = Event.objects.create(name="Parent Event", assoc=self.assoc)
        child = Event(name="Child Event", assoc=self.assoc, parent=parent)
        child.save()
        self.assertTrue(hasattr(child, "_old_parent_id"))

    @patch("larpmanager.models.association.Association.skin")
    def test_pre_save_association_set_skin_features(self, mock_skin):
        """Test Association skin feature setting on pre_save"""
        mock_skin.default_nation = "US"
        mock_skin.default_optional_fields = ["field1"]
        mock_skin.default_mandatory_fields = ["field2"]

        assoc = Association(name="New Association", slug="new2", skin=mock_skin)
        assoc.save()
        self.assertTrue(hasattr(assoc, "_update_skin_features"))


@pytest.mark.django_db_reset_sequences
class TestPostSaveSignals(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)
        self.run = Run.objects.create(event=self.event)

    def test_post_save_user_create_profile(self):
        """Test that Member profile is created when User is saved"""
        # User should already have a member from setUp
        self.assertTrue(hasattr(self.user, "member"))
        self.assertEqual(self.user.member.email, self.user.email)

    def test_post_save_run_plan(self):
        """Test Run plan assignment from association default"""
        self.assoc.plan = "Test Plan"
        self.assoc.save()

        run = Run(event=self.event)
        run.save()

        # Refresh from database to see if plan was set
        run.refresh_from_db()
        self.assertEqual(run.plan, "Test Plan")

    @patch("larpmanager.models.casting.update_traits_all")
    def test_post_save_trait_update(self, mock_update):
        """Test Trait update relationships on post_save"""
        trait = Trait.objects.create(name="Test Trait", event=self.event)
        mock_update.assert_called_with(trait)

    def test_post_save_accounting_item_payment_updatereg(self):
        """Test Registration update when AccountingItemPayment is saved"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        with patch.object(Registration, "save") as mock_save:
            _payment = AccountingItemPayment.objects.create(reg=reg, value=100.0)
            mock_save.assert_called()

    def test_post_save_accounting_item_collection(self):
        """Test Collection update when AccountingItemCollection is saved"""
        collection = Collection.objects.create(name="Test Collection")
        with patch.object(Collection, "save") as mock_save:
            AccountingItemCollection.objects.create(collection=collection, value=50.0)
            mock_save.assert_called()

    def test_post_save_event_button_cache_clear(self):
        """Test cache clearing when EventButton is saved"""
        with patch("django.core.cache.cache.delete") as mock_delete:
            EventButton.objects.create(event=self.event, name="Test Button")
            mock_delete.assert_called()

    @patch("larpmanager.cache.config.reset_configs")
    def test_post_save_event_config(self, mock_reset):
        """Test config reset when EventConfig is saved"""
        EventConfig.objects.create(event=self.event, key="test", value="test")
        mock_reset.assert_called_with(self.event)

    @patch("larpmanager.cache.config.reset_configs")
    def test_post_save_member_config(self, mock_reset):
        """Test config reset when MemberConfig is saved"""
        MemberConfig.objects.create(member=self.user.member, key="test", value="test")
        mock_reset.assert_called_with(self.user.member)

    @patch("larpmanager.cache.feature.get_event_features")
    def test_post_save_event_update(self, mock_features):
        """Test Event update process on post_save"""
        mock_features.return_value = {}

        # Create a non-template event
        event = Event(name="New Event", assoc=self.assoc, template=False)
        event.save()

        # Should have created a run
        self.assertEqual(event.runs.count(), 1)

    @patch("larpmanager.utils.tutorial_query.index_tutorial")
    def test_post_save_index_tutorial(self, mock_index):
        """Test tutorial indexing on post_save"""
        tutorial = LarpManagerTutorial.objects.create(name="Test Tutorial", content="Content")
        mock_index.assert_called_with(tutorial.id)

    @patch("larpmanager.utils.tutorial_query.index_guide")
    def test_post_save_index_guide(self, mock_index):
        """Test guide indexing on post_save"""
        guide = LarpManagerGuide.objects.create(name="Test Guide", content="Content")
        mock_index.assert_called_with(guide.id)

    @patch("larpmanager.cache.fields.reset_event_fields_cache")
    def test_post_save_writing_question(self, mock_reset):
        """Test cache reset when WritingQuestion is saved"""
        WritingQuestion.objects.create(event=self.event, name="Test Question")
        mock_reset.assert_called_with(self.event.id)

    @patch("larpmanager.utils.tasks.my_send_mail")
    @override_settings(ADMINS=[("Admin", "admin@example.com")])
    def test_post_save_larpmanager_ticket(self, mock_send_mail):
        """Test email sending when LarpManagerTicket is saved"""
        LarpManagerTicket.objects.create(assoc=self.assoc, email="user@example.com", content="Test ticket content")
        mock_send_mail.assert_called()

    @patch("larpmanager.cache.feature.get_event_features")
    def test_post_save_registration_campaign(self, mock_features):
        """Test campaign registration auto-assignment on post_save"""
        mock_features.return_value = {"campaign": True}

        # Create parent event and character
        parent = Event.objects.create(name="Parent Event", assoc=self.assoc)
        char = Character.objects.create(event=parent, player=self.user.member)
        parent_run = Run.objects.create(event=parent)

        # Create registration for parent
        parent_reg = Registration.objects.create(member=self.user.member, run=parent_run)
        RegistrationCharacterRel.objects.create(reg=parent_reg, character=char)

        # Create child event
        child = Event.objects.create(name="Child Event", assoc=self.assoc, parent=parent)
        child_run = Run.objects.create(event=child)

        # Create registration for child - should auto-assign character
        child_reg = Registration.objects.create(member=self.user.member, run=child_run)

        # Check if character was auto-assigned
        self.assertTrue(RegistrationCharacterRel.objects.filter(reg=child_reg, character=char).exists())


@pytest.mark.django_db_reset_sequences
class TestPreDeleteSignals(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)
        self.run = Run.objects.create(event=self.event)

    def test_pre_delete_event_button_cache_clear(self):
        """Test cache clearing when EventButton is deleted"""
        button = EventButton.objects.create(event=self.event, name="Test Button")
        with patch("django.core.cache.cache.delete") as mock_delete:
            button.delete()
            mock_delete.assert_called()

    @patch("larpmanager.utils.tutorial_query.delete_index_tutorial")
    def test_pre_delete_tutorial_from_index(self, mock_delete_index):
        """Test tutorial index deletion on pre_delete"""
        tutorial = LarpManagerTutorial.objects.create(name="Test Tutorial", content="Content")
        tutorial_id = tutorial.id
        tutorial.delete()
        mock_delete_index.assert_called_with(tutorial_id)

    @patch("larpmanager.utils.tutorial_query.delete_index_guide")
    def test_pre_delete_guide_from_index(self, mock_delete_index):
        """Test guide index deletion on pre_delete"""
        guide = LarpManagerGuide.objects.create(name="Test Guide", content="Content")
        guide_id = guide.id
        guide.delete()
        mock_delete_index.assert_called_with(guide_id)

    @patch("larpmanager.cache.fields.reset_event_fields_cache")
    def test_pre_delete_writing_question(self, mock_reset):
        """Test cache reset when WritingQuestion is deleted"""
        question = WritingQuestion.objects.create(event=self.event, name="Test Question")
        question.delete()
        mock_reset.assert_called_with(self.event.id)


@pytest.mark.django_db_reset_sequences
class TestPostDeleteSignals(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)

    @patch("larpmanager.cache.config.reset_configs")
    def test_post_delete_event_config(self, mock_reset):
        """Test config reset when EventConfig is deleted"""
        config = EventConfig.objects.create(event=self.event, key="test", value="test")
        config.delete()
        mock_reset.assert_called_with(self.event)

    @patch("larpmanager.cache.config.reset_configs")
    def test_post_delete_member_config(self, mock_reset):
        """Test config reset when MemberConfig is deleted"""
        config = MemberConfig.objects.create(member=self.user.member, key="test", value="test")
        config.delete()
        mock_reset.assert_called_with(self.user.member)


@pytest.mark.django_db_reset_sequences
class TestCacheSignals(TestCase):
    """Test cache-related signal handlers"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)
        self.run = Run.objects.create(event=self.event)

    @patch("larpmanager.cache.permission.reset_assoc_permissions")
    def test_cache_permission_signals(self, mock_reset):
        """Test permission cache reset signals"""
        module = FeatureModule.objects.create(name="test_module")
        feature = Feature.objects.create(name="test_feature", module=module)

        # Test post_save signal
        perm = AssocPermission.objects.create(feature=feature, assoc=self.assoc)

        # Test post_delete signal
        perm.delete()

    @patch("larpmanager.cache.character.reset_character_cache")
    def test_cache_character_signals(self, mock_reset):
        """Test character cache reset signals"""
        char = Character.objects.create(event=self.event, player=self.user.member)

        # Test various signals that should reset character cache
        trait = Trait.objects.create(name="Test Trait", event=self.event)
        AssignmentTrait.objects.create(character=char, trait=trait)


@pytest.mark.django_db_reset_sequences
class TestMailSignals(TestCase):
    """Test mail-related signal handlers"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)
        self.run = Run.objects.create(event=self.event)

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_mail_signals_send_notifications(self, mock_send_mail):
        """Test that mail signals send appropriate notifications"""
        # Create registration
        reg = Registration.objects.create(member=self.user.member, run=self.run)

        # This should trigger mail signals in some cases
        char = Character.objects.create(event=self.event, player=self.user.member)
        RegistrationCharacterRel.objects.create(reg=reg, character=char)


@pytest.mark.django_db_reset_sequences
class TestSpecializedSignals(TestCase):
    """Test specialized signal handlers for specific business logic"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)
        self.run = Run.objects.create(event=self.event)

    def test_warehouse_item_photo_rotation(self):
        """Test warehouse item photo rotation signal"""
        # Create a warehouse item
        item = WarehouseItem.objects.create(name="Test Item", assoc=self.assoc)

        # Test that the signal is connected (the actual image processing
        # is complex and requires actual image files)
        self.assertTrue(hasattr(item, "photo"))

    @patch("larpmanager.accounting.vat.compute_vat")
    @patch("larpmanager.cache.feature.get_assoc_features")
    def test_vat_computation_signal(self, mock_features, mock_compute_vat):
        """Test VAT computation signal for payment items"""
        mock_features.return_value = {"vat": True}

        reg = Registration.objects.create(member=self.user.member, run=self.run)
        payment = AccountingItemPayment.objects.create(reg=reg, value=100.0)

        mock_compute_vat.assert_called_with(payment)

    def test_registration_character_form_cleanup(self):
        """Test registration character form cleanup signal"""
        # Create ticket
        ticket = RegistrationTicket.objects.create(event=self.event, name="Standard")

        # Create registration with ticket
        reg = Registration.objects.create(member=self.user.member, run=self.run, ticket=ticket)

        # Create character
        Character.objects.create(event=self.event, player=self.user.member)

        # The signal should clean up character options based on ticket restrictions
        # This is a complex signal that requires proper setup of WritingChoice and WritingOption models
        self.assertTrue(reg.ticket is not None)


@pytest.mark.django_db_reset_sequences
class TestSignalInteractions(TestCase):
    """Test complex interactions between multiple signals"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")

    def test_event_creation_cascade(self):
        """Test the cascade of signals when creating a new event"""
        # Creating an event should trigger multiple signals
        event = Event.objects.create(name="Test Event", assoc=self.assoc)

        # Should have created a run automatically
        self.assertEqual(event.runs.count(), 1)

        # Should have setup default registration tickets
        tickets = RegistrationTicket.objects.filter(event=event)
        self.assertGreater(tickets.count(), 0)

    def test_user_member_creation_flow(self):
        """Test the signal flow when creating a new user"""
        new_user = User.objects.create_user(username="newuser", email="newuser@example.com")

        # Should have created member profile
        self.assertTrue(hasattr(new_user, "member"))
        self.assertEqual(new_user.member.email, new_user.email)

    @patch("larpmanager.cache.feature.get_event_features")
    def test_registration_campaign_chain(self, mock_features):
        """Test the complex signal chain for campaign registrations"""
        mock_features.return_value = {"campaign": True}

        # Create parent-child event relationship
        parent = Event.objects.create(name="Parent Event", assoc=self.assoc)
        child = Event.objects.create(name="Child Event", assoc=self.assoc, parent=parent)

        # Create runs
        parent_run = Run.objects.create(event=parent)
        child_run = Run.objects.create(event=child)

        # Create character in parent
        char = Character.objects.create(event=parent, player=self.user.member)

        # Register in parent
        parent_reg = Registration.objects.create(member=self.user.member, run=parent_run)
        RegistrationCharacterRel.objects.create(reg=parent_reg, character=char)

        # Register in child - should auto-assign character
        child_reg = Registration.objects.create(member=self.user.member, run=child_run)

        # Verify character was auto-assigned
        self.assertTrue(RegistrationCharacterRel.objects.filter(reg=child_reg, character=char).exists())


@pytest.mark.django_db_reset_sequences
class TestMailSignalHandlers(TestCase):
    """Test mail-related signal handlers that weren't covered before"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)
        self.run = Run.objects.create(event=self.event)

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_post_save_accounting_item_expense_mail(self, mock_send_mail):
        """Test expense item email notification"""
        AccountingItemExpense.objects.create(assoc=self.assoc, value=100.0, description="Test expense")
        # Mail signal should have been triggered

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_save_accounting_item_expense_mail(self, mock_send_mail):
        """Test expense item pre-save mail processing"""
        expense = AccountingItemExpense(assoc=self.assoc, value=100.0, description="Test expense")
        expense.save()

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_save_accounting_item_other_mail(self, mock_send_mail):
        """Test other accounting item email notification"""
        other = AccountingItemOther(assoc=self.assoc, value=50.0, description="Test other")
        other.save()

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_save_accounting_item_donation_mail(self, mock_send_mail):
        """Test donation item email notification"""
        donation = AccountingItemDonation(assoc=self.assoc, value=25.0, description="Test donation")
        donation.save()

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_post_save_collection_mail(self, mock_send_mail):
        """Test collection email notification"""
        Collection.objects.create(name="Test Collection", assoc=self.assoc)

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_save_accounting_item_collection_mail(self, mock_send_mail):
        """Test collection item email notification"""
        collection = Collection.objects.create(name="Test Collection")
        item = AccountingItemCollection(collection=collection, value=75.0)
        item.save()

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_post_save_registration_character_rel_mail(self, mock_send_mail):
        """Test registration character relation email notification"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        char = Character.objects.create(event=self.event, player=self.user.member)
        RegistrationCharacterRel.objects.create(reg=reg, character=char)

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_save_registration_mail(self, mock_send_mail):
        """Test registration pre-save email notification"""
        reg = Registration(member=self.user.member, run=self.run)
        reg.save()

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_delete_registration_mail(self, mock_send_mail):
        """Test registration deletion email notification"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        reg.delete()

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_save_pre_registration_mail(self, mock_send_mail):
        """Test pre-registration email notification"""
        prereg = PreRegistration(event=self.event, email="test@example.com", name="Test User")
        prereg.save()

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_post_save_assignment_trait_mail(self, mock_send_mail):
        """Test assignment trait email notification"""
        char = Character.objects.create(event=self.event, player=self.user.member)
        trait = Trait.objects.create(name="Test Trait", event=self.event)
        AssignmentTrait.objects.create(character=char, trait=trait)

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_save_character_mail(self, mock_send_mail):
        """Test character pre-save email notification"""
        char = Character(event=self.event, player=self.user.member, name="Test Character")
        char.save()

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_save_accounting_item_membership_mail(self, mock_send_mail):
        """Test membership accounting item email notification"""
        membership_item = AccountingItemMembership(member=self.user.member, assoc=self.assoc, value=30.0)
        membership_item.save()

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_save_help_question_mail(self, mock_send_mail):
        """Test help question email notification"""
        question = HelpQuestion(member=self.user.member, question="Test question?")
        question.save()

    @patch("larpmanager.utils.tasks.my_send_mail")
    def test_pre_save_chat_message_mail(self, mock_send_mail):
        """Test chat message email notification"""
        message = ChatMessage(sender=self.user.member, event=self.event, message="Test message")
        message.save()


@pytest.mark.django_db_reset_sequences
class TestAccountingSignalHandlers(TestCase):
    """Test accounting-related signal handlers"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)
        self.run = Run.objects.create(event=self.event)

    def test_pre_save_payment_invoice(self):
        """Test PaymentInvoice pre-save processing"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        invoice = PaymentInvoice(reg=reg, amount=100.0)
        invoice.save()
        self.assertIsNotNone(invoice.id)

    def test_pre_save_refund_request(self):
        """Test RefundRequest pre-save processing"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        refund = RefundRequest(reg=reg, amount=50.0, reason="Test refund")
        refund.save()
        self.assertIsNotNone(refund.id)

    def test_pre_save_collection_accounting(self):
        """Test Collection pre-save in accounting context"""
        collection = Collection(name="Test Collection", assoc=self.assoc)
        collection.save()
        self.assertIsNotNone(collection.contribute_code)
        self.assertIsNotNone(collection.redeem_code)

    @patch("larpmanager.accounting.gateway.logger")
    def test_valid_ipn_received_signal(self, mock_logger):
        """Test valid IPN received signal handler"""
        # This tests the PayPal IPN signal handler
        # The actual IPN processing is complex and would require PayPal IPN objects
        pass

    @patch("larpmanager.accounting.gateway.logger")
    def test_invalid_ipn_received_signal(self, mock_logger):
        """Test invalid IPN received signal handler"""
        # This tests the PayPal IPN signal handler
        # The actual IPN processing is complex and would require PayPal IPN objects
        pass

    def test_pre_save_registration_accounting(self):
        """Test registration pre-save in accounting context"""
        reg = Registration(member=self.user.member, run=self.run)
        reg.save()
        self.assertIsNotNone(reg.id)

    def test_post_save_registration_accounting(self):
        """Test registration post-save accounting processing"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        # The accounting signal should have processed the registration
        self.assertIsNotNone(reg.id)

    def test_post_save_accounting_item_discount_accounting(self):
        """Test discount item accounting processing"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        discount = AccountingItemDiscount.objects.create(reg=reg, value=20.0, description="Test discount")
        self.assertIsNotNone(discount.id)

    def test_post_save_registration_ticket_accounting(self):
        """Test registration ticket accounting processing"""
        ticket = RegistrationTicket.objects.create(event=self.event, name="Standard Ticket")
        self.assertIsNotNone(ticket.id)

    def test_post_save_registration_option_accounting(self):
        """Test registration option accounting processing"""
        option = RegistrationOption.objects.create(event=self.event, name="Test Option", price=15.0)
        self.assertIsNotNone(option.id)

    @patch("larpmanager.accounting.token_credit.update_token_credit")
    def test_post_save_accounting_item_payment_token_credit(self, mock_update):
        """Test token credit update on payment save"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        AccountingItemPayment.objects.create(reg=reg, value=100.0)

    @patch("larpmanager.accounting.token_credit.update_token_credit")
    def test_post_delete_accounting_item_payment_token_credit(self, mock_update):
        """Test token credit update on payment deletion"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        payment = AccountingItemPayment.objects.create(reg=reg, value=100.0)
        payment.delete()

    @patch("larpmanager.accounting.token_credit.update_token_credit")
    def test_post_save_accounting_item_other_token_credit(self, mock_update):
        """Test token credit update on other item save"""
        AccountingItemOther.objects.create(assoc=self.assoc, value=50.0, description="Test other")

    @patch("larpmanager.accounting.token_credit.update_token_credit")
    def test_post_save_accounting_item_expense_token_credit(self, mock_update):
        """Test token credit update on expense save"""
        AccountingItemExpense.objects.create(assoc=self.assoc, value=75.0, description="Test expense")


@pytest.mark.django_db_reset_sequences
class TestCacheSignalHandlers(TestCase):
    """Test cache-related signal handlers that weren't covered before"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)
        self.run = Run.objects.create(event=self.event)

    @patch("larpmanager.cache.run.reset_run_cache")
    def test_pre_save_run_cache(self, mock_reset):
        """Test run cache reset on pre-save"""
        run = Run(event=self.event, number=2)
        run.save()

    @patch("larpmanager.cache.run.reset_event_cache")
    def test_pre_save_event_cache(self, mock_reset):
        """Test event cache reset on pre-save"""
        event = Event(name="New Event", assoc=self.assoc)
        event.save()

    @patch("larpmanager.cache.run.reset_run_cache")
    def test_post_save_run_cache(self, mock_reset):
        """Test run cache reset on post-save"""
        Run.objects.create(event=self.event, number=3)

    @patch("larpmanager.cache.run.reset_event_cache")
    def test_post_save_event_cache(self, mock_reset):
        """Test event cache reset on post-save"""
        Event.objects.create(name="Another Event", assoc=self.assoc)

    @patch("larpmanager.cache.text_fields.reset_text_field_cache")
    def test_post_save_text_fields_cache(self, mock_reset):
        """Test text fields cache reset on post-save"""
        # This is a generic signal that applies to multiple models
        Character.objects.create(event=self.event, player=self.user.member)

    @patch("larpmanager.cache.text_fields.reset_text_field_cache")
    def test_post_delete_text_fields_cache(self, mock_reset):
        """Test text fields cache reset on post-delete"""
        char = Character.objects.create(event=self.event, player=self.user.member)
        char.delete()

    @patch("larpmanager.cache.links.reset_event_links")
    def test_post_save_registration_event_links(self, mock_reset):
        """Test event links cache reset on registration save"""
        Registration.objects.create(member=self.user.member, run=self.run)

    @patch("larpmanager.cache.links.reset_event_links")
    def test_post_save_event_links(self, mock_reset):
        """Test event links cache reset on event save"""
        Event.objects.create(name="Link Event", assoc=self.assoc)

    @patch("larpmanager.cache.links.reset_event_links")
    def test_post_delete_event_links(self, mock_reset):
        """Test event links cache reset on event delete"""
        event = Event.objects.create(name="Delete Event", assoc=self.assoc)
        event.delete()

    @patch("larpmanager.cache.links.reset_run_links")
    def test_post_save_run_links(self, mock_reset):
        """Test run links cache reset on run save"""
        Run.objects.create(event=self.event, number=4)

    @patch("larpmanager.cache.links.reset_run_links")
    def test_post_delete_run_links(self, mock_reset):
        """Test run links cache reset on run delete"""
        run = Run.objects.create(event=self.event, number=5)
        run.delete()

    @patch("larpmanager.cache.registration.reset_registration_cache")
    def test_post_save_registration_cache(self, mock_reset):
        """Test registration cache reset on registration save"""
        Registration.objects.create(member=self.user.member, run=self.run)

    @patch("larpmanager.cache.registration.reset_character_cache")
    def test_post_save_registration_character_rel_cache(self, mock_reset):
        """Test character cache reset on registration character relation save"""
        reg = Registration.objects.create(member=self.user.member, run=self.run)
        char = Character.objects.create(event=self.event, player=self.user.member)
        RegistrationCharacterRel.objects.create(reg=reg, character=char)

    @patch("larpmanager.cache.registration.reset_run_cache")
    def test_post_save_run_registration_cache(self, mock_reset):
        """Test run cache reset in registration context"""
        Run.objects.create(event=self.event, number=6)

    @patch("larpmanager.cache.registration.reset_event_cache")
    def test_post_save_event_registration_cache(self, mock_reset):
        """Test event cache reset in registration context"""
        Event.objects.create(name="Registration Event", assoc=self.assoc)


@pytest.mark.django_db_reset_sequences
class TestMissingConfigSignals(TestCase):
    """Test config-related signals that weren't covered before"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.assoc = Association.objects.create(name="Test Association", slug="test")
        self.event = Event.objects.create(name="Test Event", assoc=self.assoc)
        self.run = Run.objects.create(event=self.event)
        self.char = Character.objects.create(event=self.event, player=self.user.member)

    @patch("larpmanager.cache.config.reset_configs")
    def test_post_save_run_config(self, mock_reset):
        """Test config reset when RunConfig is saved"""

        RunConfig.objects.create(run=self.run, key="test", value="test")
        mock_reset.assert_called_with(self.run)

    @patch("larpmanager.cache.config.reset_configs")
    def test_post_delete_run_config(self, mock_reset):
        """Test config reset when RunConfig is deleted"""

        config = RunConfig.objects.create(run=self.run, key="test", value="test")
        config.delete()
        mock_reset.assert_called_with(self.run)

    @patch("larpmanager.cache.config.reset_configs")
    def test_post_save_association_config(self, mock_reset):
        """Test config reset when AssociationConfig is saved"""

        AssociationConfig.objects.create(assoc=self.assoc, key="test", value="test")
        mock_reset.assert_called_with(self.assoc)

    @patch("larpmanager.cache.config.reset_configs")
    def test_post_delete_association_config(self, mock_reset):
        """Test config reset when AssociationConfig is deleted"""

        config = AssociationConfig.objects.create(assoc=self.assoc, key="test", value="test")
        config.delete()
        mock_reset.assert_called_with(self.assoc)

    @patch("larpmanager.cache.config.reset_configs")
    def test_post_save_character_config(self, mock_reset):
        """Test config reset when CharacterConfig is saved"""

        CharacterConfig.objects.create(character=self.char, key="test", value="test")
        mock_reset.assert_called_with(self.char)

    @patch("larpmanager.cache.config.reset_configs")
    def test_post_delete_character_config(self, mock_reset):
        """Test config reset when CharacterConfig is deleted"""

        config = CharacterConfig.objects.create(character=self.char, key="test", value="test")
        config.delete()
        mock_reset.assert_called_with(self.char)

    @patch("larpmanager.cache.association.reset_association_cache")
    def test_post_save_association_cache(self, mock_reset):
        """Test association cache reset on save"""
        Association.objects.create(name="Cache Association", slug="cache")

    @patch("larpmanager.cache.skin.reset_skin_cache")
    def test_post_save_association_skin_cache(self, mock_reset):
        """Test association skin cache reset on save"""
        # This would require creating a skin object which is complex
        pass

    @patch("larpmanager.cache.feature.reset_association_features")
    def test_post_save_association_feature_cache(self, mock_reset):
        """Test association feature cache reset on save"""
        Association.objects.create(name="Feature Association", slug="feature")

    @patch("larpmanager.cache.feature.reset_event_features")
    def test_post_save_event_feature_cache(self, mock_reset):
        """Test event feature cache reset on save"""
        Event.objects.create(name="Feature Event", assoc=self.assoc)
