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

"""Tests for registration question form section field handling"""

import pytest
from django import forms

from larpmanager.forms.registration import OrgaRegistrationQuestionForm
from larpmanager.models.form import BaseQuestionType, RegistrationQuestion
from larpmanager.models.registration import RegistrationSection
from larpmanager.tests.unit.base import BaseTestCase


@pytest.mark.django_db
class TestRegistrationQuestionForm(BaseTestCase):
    """Test cases for registration question form"""

    def test_section_field_uses_queryset_not_choices(self) -> None:
        """Test that section field uses queryset instead of manually set choices"""
        event = self.get_event()
        run = self.get_run()

        # Create a section
        section = RegistrationSection.objects.create(
            event=event,
            name="Test Section",
            order=1,
        )

        # Initialize form with reg_que_sections feature enabled
        context = {
            "event": event,
            "run": run,
            "features": ["reg_que_sections"],
        }

        form = OrgaRegistrationQuestionForm(context=context)

        # Verify section field exists
        self.assertIn("section", form.fields)

        # Verify it's a ModelChoiceField
        self.assertIsInstance(form.fields["section"], forms.ModelChoiceField)

        # Verify it uses a queryset, not manually set choices
        self.assertIsNotNone(form.fields["section"].queryset)

        # Verify the queryset contains the correct section
        self.assertIn(section, form.fields["section"].queryset)

        # Verify the queryset filters by event
        self.assertEqual(form.fields["section"].queryset.count(), 1)
        self.assertEqual(form.fields["section"].queryset.first(), section)

    def test_section_field_preserves_value_on_edit(self) -> None:
        """Test that section field preserves its value when editing a question"""
        event = self.get_event()
        run = self.get_run()

        # Create sections
        section1 = RegistrationSection.objects.create(
            event=event,
            name="Section 1",
            order=1,
        )
        section2 = RegistrationSection.objects.create(
            event=event,
            name="Section 2",
            order=2,
        )

        # Create a question with section1
        question = RegistrationQuestion.objects.create(
            event=event,
            name="Test Question",
            typ=BaseQuestionType.TEXT,
            section=section1,
            order=1,
        )

        # Initialize form with the existing question
        context = {
            "event": event,
            "run": run,
            "features": ["reg_que_sections"],
        }

        form = OrgaRegistrationQuestionForm(instance=question, context=context)

        # Verify the section field is set to section1
        self.assertEqual(form.initial.get("section"), section1.uuid)

        # Simulate editing the question (changing name but not section)
        data = {
            "event": event.uuid,
            "name": "Updated Question",
            "typ": BaseQuestionType.TEXT,
            "section": str(section1.uuid),
            "status": "o",
            "max_length": 100,
        }

        form = OrgaRegistrationQuestionForm(data=data, instance=question, context=context)

        # Verify form is valid
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        # Save the form
        saved_question = form.save()

        # Verify the section is preserved
        self.assertEqual(saved_question.section, section1)
        self.assertNotEqual(saved_question.section, section2)

    def test_section_field_can_be_changed(self) -> None:
        """Test that section field can be changed when editing a question"""
        event = self.get_event()
        run = self.get_run()

        # Create sections
        section1 = RegistrationSection.objects.create(
            event=event,
            name="Section 1",
            order=1,
        )
        section2 = RegistrationSection.objects.create(
            event=event,
            name="Section 2",
            order=2,
        )

        # Create a question with section1
        question = RegistrationQuestion.objects.create(
            event=event,
            name="Test Question",
            typ=BaseQuestionType.TEXT,
            section=section1,
            order=1,
        )

        # Initialize form and change section
        context = {
            "event": event,
            "run": run,
            "features": ["reg_que_sections"],
        }

        data = {
            "event": event.uuid,
            "name": "Test Question",
            "typ": BaseQuestionType.TEXT,
            "section": str(section2.uuid),
            "status": "o",
            "max_length": 100,
        }

        form = OrgaRegistrationQuestionForm(data=data, instance=question, context=context)

        # Verify form is valid
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        # Save the form
        saved_question = form.save()

        # Verify the section was changed
        self.assertEqual(saved_question.section, section2)
        self.assertNotEqual(saved_question.section, section1)

    def test_section_field_can_be_cleared(self) -> None:
        """Test that section field can be set to None (empty)"""
        event = self.get_event()
        run = self.get_run()

        # Create a section
        section = RegistrationSection.objects.create(
            event=event,
            name="Test Section",
            order=1,
        )

        # Create a question with section
        question = RegistrationQuestion.objects.create(
            event=event,
            name="Test Question",
            typ=BaseQuestionType.TEXT,
            section=section,
            order=1,
        )

        # Initialize form and clear section
        context = {
            "event": event,
            "run": run,
            "features": ["reg_que_sections"],
        }

        data = {
            "event": event.uuid,
            "name": "Test Question",
            "typ": BaseQuestionType.TEXT,
            "section": "",  # Empty string to clear the section
            "status": "o",
            "max_length": 100,
        }

        form = OrgaRegistrationQuestionForm(data=data, instance=question, context=context)

        # Verify form is valid
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        # Save the form
        saved_question = form.save()

        # Verify the section was cleared
        self.assertIsNone(saved_question.section)

    def test_section_field_filters_by_event(self) -> None:
        """Test that section field only shows sections from the same event"""
        event1 = self.get_event()
        event2 = self.create_event(name="Event 2")
        run = self.get_run()

        # Create sections for different events
        section1 = RegistrationSection.objects.create(
            event=event1,
            name="Event 1 Section",
            order=1,
        )
        section2 = RegistrationSection.objects.create(
            event=event2,
            name="Event 2 Section",
            order=1,
        )

        # Initialize form for event1
        context = {
            "event": event1,
            "run": run,
            "features": ["reg_que_sections"],
        }

        form = OrgaRegistrationQuestionForm(context=context)

        # Verify only event1's section is in the queryset
        self.assertIn(section1, form.fields["section"].queryset)
        self.assertNotIn(section2, form.fields["section"].queryset)

    def test_section_field_removed_when_feature_disabled(self) -> None:
        """Test that section field is removed when reg_que_sections feature is disabled"""
        event = self.get_event()
        run = self.get_run()

        # Initialize form without reg_que_sections feature
        context = {
            "event": event,
            "run": run,
            "features": [],  # Feature not enabled
        }

        form = OrgaRegistrationQuestionForm(context=context)

        # Verify section field is not present
        self.assertNotIn("section", form.fields)
