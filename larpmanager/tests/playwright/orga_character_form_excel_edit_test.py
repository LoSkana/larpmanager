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
Test: Character form inline editing in Excel-style character grid.
Verifies double-click editing for all field types (name, teaser, text, custom questions)
including text, paragraph, single choice, and multiple choice fields.
Tests editing on both populated and empty cells, and validates persistence after refresh.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    just_wait,
    expect_normalized,
    fill_tinymce,
    go_to,
    login_orga,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_character_form_inline_edit(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Activate characters feature
    go_to(page, live_server, "/test/manage/features/character/on")

    # Create character form with 5 questions
    create_character_form(page, live_server)

    # Edit first character (u1) with values
    edit_first_character(page, live_server)

    # Create second character with only name
    create_second_character(page, live_server)

    # Test inline editing on character grid
    inline_editing_name(page, live_server)
    inline_editing_teaser(page, live_server)
    inline_editing_text(page, live_server)
    inline_editing_text_question(page, live_server)
    inline_editing_paragraph_question(page, live_server)
    inline_editing_singlechoice_question(page, live_server)
    inline_editing_multichoice_question(page, live_server)
    inline_editing_text2_question(page, live_server)

    # Refresh and verify all values are still correct
    verify_after_refresh(page, live_server)


def create_character_form(page: Any, live_server: Any) -> None:
    """Create 5 questions: text, paragraph, singlechoice, multichoice, text2."""
    go_to(page, live_server, "/test/manage/writing/form/")

    # Question 1: Text field
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.locator("#id_name").fill("Text Question")
    page.locator("#id_description").fill("A text field")
    page.locator("#id_max_length").fill("50")
    submit_confirm(page)

    # Question 2: Paragraph field
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("p")
    page.locator("#id_name").fill("Paragraph Question")
    page.locator("#id_description").fill("A paragraph field")
    submit_confirm(page)

    # Question 3: Single choice with 3 options
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("s")
    page.locator("#id_name").fill("Single Choice")
    page.locator("#id_description").fill("Choose one option")

    # Add option 1
    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#id_name").fill("Option A")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    # Add option 2
    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").fill("Option B")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    # Add option 3
    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").fill("Option C")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    submit_confirm(page)

    # Question 4: Multiple choice with 3 options
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("m")
    page.locator("#id_name").fill("Multiple Choice")
    page.locator("#id_description").fill("Choose multiple options")
    page.locator("#id_max_length").fill("3")

    # Add option 1
    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").fill("Choice X")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    # Add option 2
    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").fill("Choice Y")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    # Add option 3
    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").fill("Choice Z")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    submit_confirm(page)

    # Question 5: Another text field
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("e")
    page.locator("#id_name").fill("Advanced Question")
    page.locator("#id_description").fill("Advanced text field")
    submit_confirm(page)


def edit_first_character(page: Any, live_server: Any) -> None:
    """Edit character u1 (Test Character) with values for all questions."""
    go_to(page, live_server, "/test/manage/characters/")
    page.locator('[id="u1"]').get_by_role("link", name="").first.click()

    # Fill all custom questions
    page.locator("#id_que_u4").fill("Text value 1")
    page.locator("#id_que_u5").fill("Paragraph value 1")
    page.locator("#id_que_u6").select_option("u1")  # Option A
    page.get_by_role("checkbox", name="Choice X").check()
    page.get_by_role("checkbox", name="Choice Y").check()
    fill_tinymce(page, "id_que_u8", "Advanced value 1")

    submit_confirm(page)


def create_second_character(page: Any, live_server: Any) -> None:
    """Create a new character with only the name set."""
    go_to(page, live_server, "/test/manage/characters/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("Second Character")
    fill_tinymce(page, "id_teaser", "")
    fill_tinymce(page, "id_text", "")
    submit_confirm(page)


def inline_editing_name(page: Any, live_server: Any) -> None:
    """Test editing name field inline for both characters."""
    go_to(page, live_server, "/test/manage/characters/")
    just_wait(page)

    # Edit u1 name (existing value)
    page.get_by_role("cell", name="#1 Test Character").dblclick()
    just_wait(page)
    page.locator("#id_name").fill("Test Character Modified")
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u1"]'), "Test Character Modified")

    # Edit u2 name (existing value)
    page.locator('[id="u2"]').get_by_role("cell").filter(has_text="Second Character").dblclick()
    just_wait(page)
    page.locator("#id_name").fill("Second Character Modified")
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u2"]'), "Second Character Modified")


def inline_editing_teaser(page: Any, live_server: Any) -> None:
    """Test editing teaser field inline for both characters."""
    # Edit u1 teaser (existing value)
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text="Test Teaser").dblclick()
    just_wait(page)
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").fill(
        "Modified Teaser 1"
    )
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u1"]'), "Modified Teaser 1")

    # Edit u2 teaser (empty cell - click on the cell in the teaser column)
    cells_u2 = page.locator('[id="u2"]').get_by_role("cell")
    cells_u2.nth(3).dblclick()
    just_wait(page)
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").fill(
        "New Teaser 2"
    )
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u2"]'), "New Teaser 2")


def inline_editing_text(page: Any, live_server: Any) -> None:
    """Test editing text field inline for both characters."""
    # Edit u1 text (existing value)
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text="Test Text").dblclick()
    just_wait(page)
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").fill(
        "Modified Text 1"
    )
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u1"]'), "Modified Text 1")

    # Edit u2 text (empty cell)
    cells_u2 = page.locator('[id="u2"]').get_by_role("cell")
    cells_u2.nth(4).dblclick()
    just_wait(page)
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").fill(
        "New Text 2"
    )
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u2"]'), "New Text 2")


def inline_editing_text_question(page: Any, live_server: Any) -> None:
    """Test editing Text Question field inline for both characters."""

    page.get_by_role("link", name="Text Question").click()

    # Edit u1 (existing value)
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text="Text value 1").dblclick()
    just_wait(page)
    page.locator("#id_que_u4").fill("Text value modified")
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u1"]'), "Text value modified")

    # Edit u2 (empty cell) - click on the appropriate column
    cells_u2 = page.locator('[id="u2"]').get_by_role("cell")
    cells_u2.nth(5).dblclick()
    just_wait(page)
    page.locator("#id_que_u4").fill("Text value 2")
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u2"]'), "Text value 2")


def inline_editing_paragraph_question(page: Any, live_server: Any) -> None:
    """Test editing Paragraph Question field inline for both characters."""

    page.get_by_role("link", name="Paragraph Question").click()

    # Edit u1 (existing value)
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text="Paragraph value 1").dblclick()
    just_wait(page)
    page.locator("#id_que_u5").fill("Paragraph modified")
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u1"]'), "Paragraph modified")

    # Edit u2 (empty cell)
    cells_u2 = page.locator('[id="u2"]').get_by_role("cell")
    cells_u2.nth(6).dblclick()
    just_wait(page)
    page.locator("#id_que_u5").fill("Paragraph value 2")
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u2"]'), "Paragraph value 2")


def inline_editing_singlechoice_question(page: Any, live_server: Any) -> None:
    """Test editing Single Choice field inline for both characters."""

    page.get_by_role("link", name="Single Choice").first.click()

    # Edit u1 (existing value - Option A)
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text="Option A").dblclick()
    just_wait(page)
    page.locator("#id_que_u6").select_option("u2")  # Option B
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u1"]'), "Option B")

    # Edit u2 (empty cell)
    cells_u2 = page.locator('[id="u2"]').get_by_role("cell")
    cells_u2.nth(7).dblclick()
    just_wait(page)
    page.locator("#id_que_u6").select_option("u3")  # Option C
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u2"]'), "Option C")


def inline_editing_multichoice_question(page: Any, live_server: Any) -> None:
    """Test editing Multiple Choice field inline for both characters."""

    page.get_by_role("link", name="Multiple Choice").first.click()

    # Edit u1 (existing values - Choice X and Y)
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text="Choice X").dblclick()
    just_wait(page)
    page.get_by_role("checkbox", name="Choice X").uncheck()
    page.get_by_role("checkbox", name="Choice Z").check()
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u1"]'), "Choice Y")
    expect_normalized(page, page.locator('[id="u1"]'), "Choice Z")

    # Edit u2 (empty cell)
    cells_u2 = page.locator('[id="u2"]').get_by_role("cell")
    cells_u2.nth(8).dblclick()
    just_wait(page)
    page.get_by_role("checkbox", name="Choice X").check()
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u2"]'), "Choice X")


def inline_editing_text2_question(page: Any, live_server: Any) -> None:
    """Test editing Text Question 2 field inline for both characters."""

    page.get_by_role("link", name="Advanced Question").click()

    # Edit u1 (existing value)
    page.locator('[id="u1"]').get_by_role("cell").filter(has_text="Advanced value 1").dblclick()
    just_wait(page)
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").fill(
        "Text 2 modified"
    )
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u1"]'), "Text 2 modified")

    # Edit u2 (empty cell)
    cells_u2 = page.locator('[id="u2"]').get_by_role("cell")
    cells_u2.nth(9).dblclick()
    just_wait(page)
    page.locator('iframe[title="Rich Text Area"]').content_frame.get_by_label("Rich Text Area").fill(
        "Text 2 value 2"
    )
    submit_confirm(page)
    just_wait(page)
    expect_normalized(page, page.locator('[id="u2"]'), "Text 2 value 2")


def verify_after_refresh(page: Any, live_server: Any) -> None:
    """Refresh the page and verify all edited values are still correct."""
    go_to(page, live_server, "/test/manage/characters/")

    page.get_by_role("link", name="Text Question").click()
    page.get_by_role("link", name="Paragraph Question").click()
    page.get_by_role("link", name="Single Choice").first.click()
    page.get_by_role("link", name="Multiple Choice").first.click()
    page.get_by_role("link", name="Advanced Question").click()
    just_wait(page)

    # Verify u1 values
    expect_normalized(page, page.locator('[id="u1"]'), "Test Character Modified")
    expect_normalized(page, page.locator('[id="u1"]'), "Modified Teaser 1")
    expect_normalized(page, page.locator('[id="u1"]'), "Modified Text 1")
    expect_normalized(page, page.locator('[id="u1"]'), "Text value modified")
    expect_normalized(page, page.locator('[id="u1"]'), "Paragraph modified")
    expect_normalized(page, page.locator('[id="u1"]'), "Option B")
    expect_normalized(page, page.locator('[id="u1"]'), "Choice Y")
    expect_normalized(page, page.locator('[id="u1"]'), "Choice Z")
    expect_normalized(page, page.locator('[id="u1"]'), "Text 2 modified")

    # Verify u2 values
    expect_normalized(page, page.locator('[id="u2"]'), "Second Character Modified")
    expect_normalized(page, page.locator('[id="u2"]'), "New Teaser 2")
    expect_normalized(page, page.locator('[id="u2"]'), "New Text 2")
    expect_normalized(page, page.locator('[id="u2"]'), "Text value 2")
    expect_normalized(page, page.locator('[id="u2"]'), "Paragraph value 2")
    expect_normalized(page, page.locator('[id="u2"]'), "Option C")
    expect_normalized(page, page.locator('[id="u2"]'), "Choice X")
    expect_normalized(page, page.locator('[id="u2"]'), "Text 2 value 2")
