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

import pytest

from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.exceptions import SignupError
from larpmanager.utils.users.registration import check_signup


class TestCheckSignupStaffBypass(BaseTestCase):
    """Test check_signup function with staff bypass logic."""

    def test_staff_bypasses_signup_check(self) -> None:
        """Test that staff members bypass the signup check.

        When context contains 'staff' flag, check_signup should return early
        without raising SignupError, even if there's no registration.
        """
        run = self.get_run()

        # Create context with staff flag but no registration
        context = {
            "run": run,
            "staff": "1",  # Staff flag set
            "registration": None,  # No registration
            "member": self.get_member()
        }

        # Should not raise SignupError for staff
        check_signup(context)  # No exception = test passes

    def test_non_staff_without_registration_raises_error(self) -> None:
        """Test that non-staff users without registration get SignupError.

        When context does not contain 'staff' flag and there's no registration,
        check_signup should raise SignupError.
        """
        run = self.get_run()

        # Create context without staff flag and without registration
        context = {
            "run": run,
            "registration": None,  # No registration
            "member": self.get_member()
        }

        # Should raise SignupError for non-staff users without registration
        with pytest.raises(SignupError) as exc_info:
            check_signup(context)

        # Verify the exception contains the correct run slug
        assert exc_info.value.slug == run.get_slug()

    def test_non_staff_with_registration_passes(self) -> None:
        """Test that non-staff users with valid registration pass the check.

        When context does not contain 'staff' flag but has a valid registration,
        check_signup should not raise any exception.
        """
        run = self.get_run()
        registration_user = self.get_registration()

        # Create context without staff flag but with registration
        context = {
            "run": run,
            "registration": registration_user,  # Has valid registration
            "member": self.get_member()
        }

        # Should not raise any exception
        check_signup(context)  # No exception = test passes

    def test_staff_flag_false_still_requires_registration(self) -> None:
        """Test that staff flag must be truthy to bypass check.

        When staff flag is present but evaluates to False, the signup check
        should still be performed.
        """
        run = self.get_run()

        # Create context with falsy staff flag and no registration
        context = {
            "run": run,
            "staff": "",  # Falsy staff flag
            "registration": None,
            "member": self.get_member()
        }

        # Should raise SignupError because staff flag is falsy
        with pytest.raises(SignupError):
            check_signup(context)

    def test_staff_with_registration_also_works(self) -> None:
        """Test that staff members with registration also pass (edge case).

        Verifies that having both staff flag and registration doesn't cause issues.
        """
        run = self.get_run()
        registration_user = self.get_registration()

        # Create context with both staff flag and registration
        context = {
            "run": run,
            "staff": "1",
            "registration": registration_user,
            "member": self.get_member()
        }

        # Should bypass check due to staff flag (registration is ignored)
        check_signup(context)  # No exception = test passes
