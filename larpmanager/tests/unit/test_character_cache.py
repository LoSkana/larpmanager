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

"""Tests for character cache functions"""

from larpmanager.cache.character import get_writing_element_fields_batch
from larpmanager.models.form import QuestionApplicable, WritingAnswer, WritingChoice, WritingOption, WritingQuestion
from larpmanager.tests.unit.base import BaseTestCase


class TestCharacterCache(BaseTestCase):
    """Test cases for character cache functions"""

    def test_get_writing_element_fields_batch_with_text_and_choice_answers(self) -> None:
        """Test that having both text and choice answers for same question doesn't cause error.

        This is a regression test for a bug where processing text answers before choice answers
        caused an AttributeError when trying to append to a string.
        """
        # Create a character
        character = self.character()
        event = character.event

        # Create a question that will have both text and choice answers (data inconsistency scenario)
        question = WritingQuestion.objects.create(
            event=event,
            name="test_question",
            description="Test Question",
            applicable=QuestionApplicable.CHARACTER,
        )

        # Create an option for the question
        option = WritingOption.objects.create(
            event=event,
            question=question,
            name="Test Option",
        )

        # Create BOTH a text answer and a choice answer for the same character and question
        # This simulates data inconsistency that could occur in production
        WritingAnswer.objects.create(
            element_id=character.id,
            question=question,
            text="Test text answer",
        )

        WritingChoice.objects.create(
            element_id=character.id,
            question=question,
            option=option,
        )

        # Build context for the function
        context = {
            "event": event,
            "features": {"character"},
            "questions": {question.uuid: {"name": question.name}},
            "options": {option.uuid: {"name": option.name}},
        }

        # This should not raise an AttributeError
        # Previously this would fail with: 'str' object has no attribute 'append'
        result = get_writing_element_fields_batch(
            context,
            "character",
            QuestionApplicable.CHARACTER,
            [character.id],
            only_visible=False,
        )

        # Verify the result structure
        self.assertIn(character.id, result)
        self.assertIn("fields", result[character.id])
        self.assertIn("questions", result[character.id])
        self.assertIn("options", result[character.id])

        # When both text and choice exist, text answer should take precedence (overwrites)
        self.assertEqual(result[character.id]["fields"][question.uuid], "Test text answer")

    def test_get_writing_element_fields_batch_with_only_choice_answers(self) -> None:
        """Test that choice answers are properly stored as lists."""
        # Create a character
        character = self.character()
        event = character.event

        # Create a question with multiple options
        question = WritingQuestion.objects.create(
            event=event,
            name="test_question",
            description="Test Question",
            applicable=QuestionApplicable.CHARACTER,
        )

        # Create multiple options
        option1 = WritingOption.objects.create(
            event=event,
            question=question,
            name="Option 1",
        )

        option2 = WritingOption.objects.create(
            event=event,
            question=question,
            name="Option 2",
        )

        # Create choice answers
        WritingChoice.objects.create(
            element_id=character.id,
            question=question,
            option=option1,
        )

        WritingChoice.objects.create(
            element_id=character.id,
            question=question,
            option=option2,
        )

        # Build context for the function
        context = {
            "event": event,
            "features": {"character"},
            "questions": {question.uuid: {"name": question.name}},
            "options": {
                option1.uuid: {"name": option1.name},
                option2.uuid: {"name": option2.name},
            },
        }

        # Call the function
        result = get_writing_element_fields_batch(
            context,
            "character",
            QuestionApplicable.CHARACTER,
            [character.id],
            only_visible=False,
        )

        # Verify choice answers are stored as a list
        self.assertIsInstance(result[character.id]["fields"][question.uuid], list)
        self.assertEqual(len(result[character.id]["fields"][question.uuid]), 2)
        self.assertIn(option1.uuid, result[character.id]["fields"][question.uuid])
        self.assertIn(option2.uuid, result[character.id]["fields"][question.uuid])

    def test_get_writing_element_fields_batch_with_only_text_answers(self) -> None:
        """Test that text answers are properly stored as strings."""
        # Create a character
        character = self.character()
        event = character.event

        # Create a text question
        question = WritingQuestion.objects.create(
            event=event,
            name="test_question",
            description="Test Question",
            applicable=QuestionApplicable.CHARACTER,
        )

        # Create a text answer
        WritingAnswer.objects.create(
            element_id=character.id,
            question=question,
            text="This is a test answer",
        )

        # Build context for the function
        context = {
            "event": event,
            "features": {"character"},
            "questions": {question.uuid: {"name": question.name}},
            "options": {},
        }

        # Call the function
        result = get_writing_element_fields_batch(
            context,
            "character",
            QuestionApplicable.CHARACTER,
            [character.id],
            only_visible=False,
        )

        # Verify text answer is stored as a string
        self.assertIsInstance(result[character.id]["fields"][question.uuid], str)
        self.assertEqual(result[character.id]["fields"][question.uuid], "This is a test answer")
