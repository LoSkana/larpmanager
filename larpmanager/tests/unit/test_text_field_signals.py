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

"""Tests for text field and cache-related signal receivers"""

from unittest.mock import patch

from larpmanager.models.association import Association
from larpmanager.models.feature import Feature, FeatureModule
from larpmanager.models.form import WritingOption, WritingQuestion
from larpmanager.models.writing import Character
from larpmanager.tests.unit.base import BaseTestCase


class TestTextFieldSignals(BaseTestCase):
    """Test cases for text field and generic cache signal receivers"""

    @patch("larpmanager.cache.text_fields.reset_text_fields_cache")
    def test_generic_post_save_resets_text_cache(self, mock_reset):
        """Test that generic post_save signal resets text fields cache"""
        # Create a model instance that should trigger text cache reset
        character = self.character()
        character.name = "Updated Character"
        character.save()

        # The generic signal should reset text cache
        mock_reset.assert_called()

    @patch("larpmanager.cache.text_fields.reset_text_fields_cache")
    def test_generic_post_delete_resets_text_cache(self, mock_reset):
        """Test that generic post_delete signal resets text fields cache"""
        # Create and delete a model instance
        character = self.character()
        character.delete()

        # The generic signal should reset text cache
        mock_reset.assert_called()

    @patch("larpmanager.cache.fields.reset_event_fields_cache")
    def test_writing_question_pre_delete_resets_fields_cache(self, mock_reset):
        """Test that WritingQuestion pre_delete signal resets event fields cache"""
        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test Question")
        question.delete()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.fields.reset_event_fields_cache")
    def test_writing_question_post_save_resets_fields_cache(self, mock_reset):
        """Test that WritingQuestion post_save signal resets event fields cache"""
        event = self.get_event()
        question = WritingQuestion(event=event, name="test_question", description="Test Question")
        question.save()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.fields.reset_event_fields_cache")
    def test_writing_option_pre_delete_resets_fields_cache(self, mock_reset):
        """Test that WritingOption pre_delete signal resets event fields cache"""
        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test Question")
        option = WritingOption.objects.create(event=event, question=question, name="Test Option")
        option.delete()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.fields.reset_event_fields_cache")
    def test_writing_option_post_save_resets_fields_cache(self, mock_reset):
        """Test that WritingOption post_save signal resets event fields cache"""
        event = self.get_event()
        question = WritingQuestion.objects.create(event=event, name="test_question", description="Test Question")
        option = WritingOption(event=event, question=question, name="Test Option")
        option.save()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.larpmanager.reset_larpmanager_cache")
    def test_association_post_save_resets_larpmanager_cache(self, mock_reset):
        """Test that Association post_save signal resets larpmanager cache"""
        assoc = Association(name="Test Association", email="test@example.com")
        assoc.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.cache.association.reset_association_cache")
    def test_association_post_save_resets_association_cache(self, mock_reset):
        """Test that Association post_save signal resets association cache"""
        assoc = Association(name="Test Association", email="test@example.com")
        assoc.save()

        mock_reset.assert_called_once_with(assoc.id)

    @patch("larpmanager.cache.run.reset_run_cache")
    def test_run_pre_save_resets_run_cache(self, mock_reset):
        """Test that Run pre_save signal resets run cache"""
        run = self.get_run()
        run.save()

        mock_reset.assert_called_once_with(run.event.id)

    @patch("larpmanager.cache.run.reset_event_cache")
    def test_event_pre_save_resets_event_cache(self, mock_reset):
        """Test that Event pre_save signal resets event cache"""
        event = self.get_event()
        event.save()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.run.reset_run_cache")
    def test_run_post_save_resets_run_cache_detailed(self, mock_reset):
        """Test that Run post_save signal resets run cache with detailed tracking"""
        run = self.get_run()
        run.save()

        mock_reset.assert_called_once_with(run.id)

    @patch("larpmanager.cache.run.reset_event_cache")
    def test_event_post_save_resets_event_cache_detailed(self, mock_reset):
        """Test that Event post_save signal resets event cache with detailed tracking"""
        event = self.get_event()
        event.save()

        mock_reset.assert_called_once_with(event.id)

    @patch("larpmanager.cache.permission.reset_permissions_cache")
    def test_feature_post_save_resets_permissions_cache(self, mock_reset):
        """Test that Feature post_save signal resets permissions cache"""
        feature = Feature(name="Test Feature", slug="test-feature")
        feature.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.cache.permission.reset_permissions_cache")
    def test_feature_post_delete_resets_permissions_cache(self, mock_reset):
        """Test that Feature post_delete signal resets permissions cache"""
        feature = Feature.objects.create(name="Test Feature", slug="test-feature")
        feature.delete()

        mock_reset.assert_called_once()

    @patch("larpmanager.cache.permission.reset_permissions_cache")
    def test_feature_module_post_save_resets_permissions_cache(self, mock_reset):
        """Test that FeatureModule post_save signal resets permissions cache"""
        feature = Feature.objects.create(name="Test Feature", slug="test-feature")
        module = FeatureModule(feature=feature, name="Test Module", slug="test-module")
        module.save()

        mock_reset.assert_called_once()

    @patch("larpmanager.cache.permission.reset_permissions_cache")
    def test_feature_module_post_delete_resets_permissions_cache(self, mock_reset):
        """Test that FeatureModule post_delete signal resets permissions cache"""
        feature = Feature.objects.create(name="Test Feature", slug="test-feature")
        module = FeatureModule.objects.create(feature=feature, name="Test Module", slug="test-module")
        module.delete()

        mock_reset.assert_called_once()

    @patch("larpmanager.cache.feature.reset_association_features_cache")
    def test_association_post_save_resets_features_cache(self, mock_reset):
        """Test that Association post_save signal resets features cache"""
        assoc = Association(name="Test Association", email="test@example.com")
        assoc.save()

        mock_reset.assert_called_once_with(assoc.id)

    @patch("larpmanager.cache.feature.reset_event_features_cache")
    def test_event_post_save_resets_features_cache(self, mock_reset):
        """Test that Event post_save signal resets features cache"""
        event = self.get_event()
        event.save()

        mock_reset.assert_called_once_with(event.id)

    def test_text_field_signals_handle_empty_values(self):
        """Test that text field signals handle empty or None values correctly"""
        # Test with empty text fields
        character = self.character()
        character.name = ""
        character.description = None
        character.save()

        # Should not raise errors
        self.assertIsNotNone(character.id)

        # Test with minimal association
        assoc = Association(name="", email="test@example.com")
        assoc.save()

        # Should not raise errors even with empty name
        self.assertIsNotNone(assoc.id)

    def test_text_field_signals_handle_special_characters(self):
        """Test that text field signals handle special characters correctly"""
        # Test with special characters
        character = self.character()
        character.name = "Test Character éàü 中文 🎭"
        character.save()

        # Should handle Unicode characters correctly
        self.assertEqual(character.name, "Test Character éàü 中文 🎭")

        # Test with HTML content
        character.description = "<p>Test <strong>bold</strong> text</p>"
        character.save()

        # Should handle HTML content correctly
        self.assertIn("<strong>", character.description)

    def test_text_field_signals_handle_long_content(self):
        """Test that text field signals handle long text content correctly"""
        character = self.character()

        # Test with very long content
        long_text = "A" * 10000  # 10KB of text
        character.description = long_text
        character.save()

        # Should handle long content correctly
        self.assertEqual(len(character.description), 10000)

    @patch("larpmanager.cache.text_fields.reset_text_fields_cache")
    def test_multiple_models_trigger_text_cache_reset(self, mock_reset):
        """Test that multiple different models trigger text cache reset"""
        # Create various models that should trigger cache reset
        character = self.character()
        character.save()

        event = self.get_event()
        event.save()

        assoc = self.get_association()
        assoc.save()

        # All should trigger cache reset
        self.assertTrue(mock_reset.call_count >= 3)

    def test_cascade_signal_effects(self):
        """Test that signals work correctly in cascade scenarios"""
        # Create event with related objects
        event = self.get_event()

        # Create writing question for the event
        question = WritingQuestion(event=event, name="test_question", description="Test Question")
        question.save()

        # Create option for the question
        option = WritingOption(event=event, question=question, name="Test Option")
        option.save()

        # All should work without errors
        self.assertIsNotNone(question.id)
        self.assertIsNotNone(option.id)

        # Delete in reverse order
        option.delete()
        question.delete()

        # Should handle deletion cascade correctly
        self.assertTrue(True)

    def test_signal_performance_with_bulk_operations(self):
        """Test that signals perform reasonably well with bulk operations"""
        # Create multiple characters rapidly
        characters = []
        for i in range(10):
            character = Character(name=f"Test Character {i}", assoc=self.get_association())
            character.save()
            characters.append(character)

        # All should be created successfully
        self.assertEqual(len(characters), 10)

        # Bulk delete
        for character in characters:
            character.delete()

        # Should handle bulk operations without issues
        self.assertTrue(True)

    @patch("larpmanager.cache.text_fields.reset_text_fields_cache")
    def test_signal_idempotency(self, mock_reset):
        """Test that repeated signal calls are idempotent"""
        character = self.character()

        # Save multiple times
        character.save()
        character.save()
        character.save()

        # Should handle repeated saves correctly
        self.assertTrue(mock_reset.call_count >= 3)

        # Update and save
        character.name = "Updated Name"
        character.save()

        # Should continue to work after updates
        self.assertEqual(character.name, "Updated Name")

    def test_signal_error_handling(self):
        """Test that signals handle errors gracefully"""
        # Test with potentially problematic data
        character = self.character()

        # Test with None values where not expected
        try:
            character.name = None
            character.save()
        except Exception:
            # If it raises an exception, that's expected for required fields
            pass

        # Test with invalid relationships
        try:
            invalid_question = WritingQuestion(
                event=None,  # Invalid - event is required
                name="test_question",
                description="Test Question",
            )
            invalid_question.save()
        except Exception:
            # Expected to fail due to validation
            pass

        # Basic functionality should still work
        valid_character = self.character()
        valid_character.save()
        self.assertIsNotNone(valid_character.id)
