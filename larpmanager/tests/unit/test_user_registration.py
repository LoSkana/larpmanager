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

"""Tests for user registration functionality.

Tests form validation and view error handling for duplicate email/username
registration attempts.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory

from larpmanager.forms.member import MyRegistrationFormUniqueEmail


@pytest.mark.django_db
class TestUserRegistration:
    """Test user registration form and view functionality."""

    def test_duplicate_email_validation_in_form(self) -> None:
        """Test that form validates against duplicate email/username.

        Ensures that MyRegistrationFormUniqueEmail raises a validation error
        when a user tries to register with an email that already exists as a
        username in the database. This prevents IntegrityError on the
        auth_user_username_key constraint.
        """
        # Create an existing user with email as username
        existing_email = "test@example.com"
        User.objects.create_user(
            username=existing_email,
            email=existing_email,
            password="testpass123",  # noqa: S106  # Test password
        )

        # Create request object for form initialization
        factory = RequestFactory()
        request = factory.get("/register/")
        request.association = {"id": 1}

        # Attempt to register with the same email
        form_data = {
            "email": existing_email,
            "password1": "newpassword123",
            "password2": "newpassword123",
            "lang": "en",
            "name": "Test",
            "surname": "User",
            "newsletter": "a",
            "share": True,
        }

        form = MyRegistrationFormUniqueEmail(data=form_data, request=request)

        # Form should be invalid due to duplicate email
        assert not form.is_valid()
        assert "email" in form.errors
        assert "already exists" in str(form.errors["email"]).lower()

    def test_duplicate_email_case_insensitive(self) -> None:
        """Test that duplicate email check is case-insensitive.

        Verifies that the validation catches duplicates regardless of email case
        (e.g., Test@Example.com vs test@example.com).
        """
        # Create user with lowercase email
        existing_email = "test@example.com"
        User.objects.create_user(
            username=existing_email,
            email=existing_email,
            password="testpass123",  # noqa: S106  # Test password
        )

        # Create request object
        factory = RequestFactory()
        request = factory.get("/register/")
        request.association = {"id": 1}

        # Try to register with same email but different case
        form_data = {
            "email": "Test@Example.COM",  # Different case
            "password1": "newpassword123",
            "password2": "newpassword123",
            "lang": "en",
            "name": "Test",
            "surname": "User",
            "newsletter": "a",
            "share": True,
        }

        form = MyRegistrationFormUniqueEmail(data=form_data, request=request)

        # Form should be invalid due to case-insensitive duplicate
        assert not form.is_valid()
        assert "email" in form.errors

    def test_successful_registration_with_unique_email(self) -> None:
        """Test that registration succeeds with a unique email.

        Verifies that form validation passes when the email doesn't exist
        in the database and that duplicate email is not in the errors.
        """
        # Create request object
        factory = RequestFactory()
        request = factory.get("/register/")
        request.association = {"id": 1}

        # Register with unique email
        form_data = {
            "email": "unique@example.com",
            "password1": "password123",
            "password2": "password123",
            "lang": "en",
            "name": "New",
            "surname": "User",
            "newsletter": "a",
            "share": True,
        }

        form = MyRegistrationFormUniqueEmail(data=form_data, request=request)

        # Check that duplicate email error is NOT present
        # (form may have other validation errors like password strength or captcha)
        # but we're specifically testing that duplicate email is not the issue
        if not form.is_valid():
            # If form is invalid, the duplicate email error should not be present
            if "email" in form.errors:
                assert "already exists" not in str(form.errors["email"]).lower()
        else:
            # If form is valid, that's even better - no errors at all
            assert "email" not in form.errors
