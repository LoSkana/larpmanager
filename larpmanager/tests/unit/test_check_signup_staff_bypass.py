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

"""Tests for check_signup staff bypass functionality.

Verifies that staff members can bypass signup checks while regular users
cannot access features without registration.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Member, Membership
from larpmanager.models.registration import Registration, RegistrationTicket, TicketTier
from larpmanager.utils.core.exceptions import SignupError
from larpmanager.utils.users.registration import check_signup


@pytest.fixture
def association(db):
    """Create test association."""
    return Association.objects.create(
        name="Test Association",
        slug="test",
        main_mail="test@test.com",
    )


@pytest.fixture
def event(association):
    """Create test event."""
    return Event.objects.create(
        name="Test Event",
        association=association,
    )


@pytest.fixture
def run(event):
    """Create test run."""
    today = date.today()
    return Run.objects.create(
        event=event,
        number=1,
        start=today,
        end=today + timedelta(days=7),
    )


@pytest.fixture
def user(db):
    """Create test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@test.com",
        password="testpass123",  # noqa: S106
    )


@pytest.fixture
def member(user, association):
    """Create test member with membership."""
    member = user.member
    member.name = "Test"
    member.surname = "User"
    member.save()

    Membership.objects.create(
        member=member,
        association=association,
        credit=Decimal("0"),
        tokens=Decimal("0"),
    )

    return member


@pytest.fixture
def ticket(event):
    """Create test ticket."""
    return RegistrationTicket.objects.create(
        event=event,
        name="Standard Ticket",
        price=Decimal("100.00"),
        tier=TicketTier.NORMAL,
    )


@pytest.fixture
def registration_user(member, run, ticket):
    """Create test registration."""
    return Registration.objects.create(
        member=member,
        run=run,
        ticket=ticket,
        tot_iscr=Decimal("100.00"),
        tot_payed=Decimal("0.00"),
    )


@pytest.mark.django_db
class TestCheckSignupStaffBypass:
    """Test check_signup function with staff bypass logic."""

    def test_staff_bypasses_signup_check(self, run: Run) -> None:
        """Test that staff members bypass the signup check.

        When context contains 'staff' flag, check_signup should return early
        without raising SignupError, even if there's no registration.
        """
        # Create context with staff flag but no registration
        context = {
            "run": run,
            "staff": "1",  # Staff flag set
            "registration": None,  # No registration
        }

        # Should not raise SignupError for staff
        check_signup(context)  # No exception = test passes

    def test_non_staff_without_registration_raises_error(self, run: Run) -> None:
        """Test that non-staff users without registration get SignupError.

        When context does not contain 'staff' flag and there's no registration,
        check_signup should raise SignupError.
        """
        # Create context without staff flag and without registration
        context = {
            "run": run,
            "registration": None,  # No registration
        }

        # Should raise SignupError for non-staff users without registration
        with pytest.raises(SignupError) as exc_info:
            check_signup(context)

        # Verify the exception contains the correct run slug
        assert exc_info.value.slug == run.get_slug()

    def test_non_staff_with_registration_passes(self, run: Run, registration_user) -> None:
        """Test that non-staff users with valid registration pass the check.

        When context does not contain 'staff' flag but has a valid registration,
        check_signup should not raise any exception.
        """
        # Create context without staff flag but with registration
        context = {
            "run": run,
            "registration": registration_user,  # Has valid registration
        }

        # Should not raise any exception
        check_signup(context)  # No exception = test passes

    def test_staff_flag_false_still_requires_registration(self, run: Run) -> None:
        """Test that staff flag must be truthy to bypass check.

        When staff flag is present but evaluates to False, the signup check
        should still be performed.
        """
        # Create context with falsy staff flag and no registration
        context = {
            "run": run,
            "staff": "",  # Falsy staff flag
            "registration": None,
        }

        # Should raise SignupError because staff flag is falsy
        with pytest.raises(SignupError):
            check_signup(context)

    def test_staff_with_registration_also_works(self, run: Run, registration_user) -> None:
        """Test that staff members with registration also pass (edge case).

        Verifies that having both staff flag and registration doesn't cause issues.
        """
        # Create context with both staff flag and registration
        context = {
            "run": run,
            "staff": "1",
            "registration": registration_user,
        }

        # Should bypass check due to staff flag (registration is ignored)
        check_signup(context)  # No exception = test passes
