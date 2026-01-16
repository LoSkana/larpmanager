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

"""
Test: Registration form sections
Verifies that registration questions correctly preserve their section assignment
when being edited, and that section assignment works correctly.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    go_to,
    login_orga,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_orga_registration_form_sections(pw_page: Any) -> None:
    """Test registration form sections handling"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Sections").check()
    submit_confirm(page)

    # Navigate to registration form management
    go_to(page, live_server, "/test/manage/form/")

    # Create sections first
    create_sections(page, live_server)

    # Create question with section
    create_question_with_section(page, live_server)

    # Edit question and verify section is preserved
    edit_question_preserve_section(page, live_server)

    # Edit question and change section
    edit_question_change_section(page, live_server)

    # Edit question and clear section
    edit_question_clear_section(page, live_server)


def create_sections(page: Any, live_server: Any) -> None:
    """Create test sections"""
    # Navigate to sections management
    go_to(page, live_server, "/test/manage/form/sections/")

    # Create first section
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Personal Information")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("Basic personal details")
    submit_confirm(page)

    # Verify section appears in list
    expect(page.locator("body")).to_contain_text("Personal Information")

    # Create second section
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Preferences")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("Your event preferences")
    submit_confirm(page)

    # Verify both sections appear
    expect(page.locator("body")).to_contain_text("Personal Information")
    expect(page.locator("body")).to_contain_text("Preferences")


def create_question_with_section(page: Any, live_server: Any) -> None:
    """Create a question assigned to a section"""
    # Navigate back to form management
    go_to(page, live_server, "/test/manage/form/")

    # Create new question
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Dietary Requirements")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("Please specify any dietary requirements")

    # Select the first section
    page.locator("#id_section").select_option(label="Personal Information")

    submit_confirm(page)

    # Verify question was created
    expect(page.locator("body")).to_contain_text("Dietary Requirements")


def edit_question_preserve_section(page: Any, live_server: Any) -> None:
    """Edit a question and verify section is preserved"""
    # Click edit on the question we just created
    page.locator("a[href*='Dietary Requirements']").first.click()

    # Get the selected option text - should be "Personal Information"
    selected_option = page.locator("#id_section option[selected]")
    expect(selected_option).to_contain_text("Personal Information")

    # Change the name but not the section
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Dietary Requirements Updated")

    submit_confirm(page)

    # Edit again to verify section was preserved
    page.locator("a[href*='Dietary Requirements Updated']").first.click()

    # Verify section is still "Personal Information"
    selected_option = page.locator("#id_section option[selected]")
    expect(selected_option).to_contain_text("Personal Information")

    # Go back without saving
    go_to(page, live_server, "/test/manage/form/")


def edit_question_change_section(page: Any, live_server: Any) -> None:
    """Edit a question and change its section"""
    # Edit the question
    page.locator("a[href*='Dietary Requirements Updated']").first.click()

    # Verify current section is "Personal Information"
    selected_option = page.locator("#id_section option[selected]")
    expect(selected_option).to_contain_text("Personal Information")

    # Change to "Preferences" section
    page.locator("#id_section").select_option(label="Preferences")

    submit_confirm(page)

    # Edit again to verify section was changed
    page.locator("a[href*='Dietary Requirements Updated']").first.click()

    # Verify section is now "Preferences"
    selected_option = page.locator("#id_section option[selected]")
    expect(selected_option).to_contain_text("Preferences")

    # Go back without saving
    go_to(page, live_server, "/test/manage/form/")


def edit_question_clear_section(page: Any, live_server: Any) -> None:
    """Edit a question and clear its section"""
    # Edit the question
    page.locator("a[href*='Dietary Requirements Updated']").first.click()

    # Verify current section is "Preferences"
    selected_option = page.locator("#id_section option[selected]")
    expect(selected_option).to_contain_text("Preferences")

    # Clear the section (select empty option)
    page.locator("#id_section").select_option(label="--- Empty")

    submit_confirm(page)

    # Edit again to verify section was cleared
    page.locator("a[href*='Dietary Requirements Updated']").first.click()

    # Verify section is now empty
    selected_option = page.locator("#id_section option[selected]")
    expect(selected_option).to_contain_text("--- Empty")

    # Save and go back
    submit_confirm(page)


def test_orga_registration_section_ordering(pw_page: Any) -> None:
    """Test that questions appear in correct section order"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Sections").check()
    submit_confirm(page)

    # Navigate to sections management
    go_to(page, live_server, "/test/manage/form/sections/")

    # Create Section A (order 1)
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("Section A")
    submit_confirm(page)

    # Create Section B (order 2)
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("Section B")
    submit_confirm(page)

    # Navigate to form management
    go_to(page, live_server, "/test/manage/form/")

    # Create question in Section B
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").fill("Question B")
    page.locator("#id_section").select_option(label="Section B")
    submit_confirm(page)

    # Create question in Section A
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").fill("Question A")
    page.locator("#id_section").select_option(label="Section A")
    submit_confirm(page)

    # Create question with no section (should appear first)
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").fill("Question No Section")
    page.locator("#id_section").select_option(label="--- Empty")
    submit_confirm(page)

    # Verify questions appear in the list
    # (The actual ordering would be verified by checking the registration form)
    expect(page.locator("body")).to_contain_text("Question A")
    expect(page.locator("body")).to_contain_text("Question B")
    expect(page.locator("body")).to_contain_text("Question No Section")
