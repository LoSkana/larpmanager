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
Test: post_popup functionality for long registration and character question answers.

Verifies that when question answers exceed the snippet limit (150 chars), an eye icon
appears in the organiser list views. Clicking the icon triggers a POST request that
returns the full content displayed in a popup (uglipop).

Tests cover:
- Registration question of type 'e' (advanced editor / TinyMCE)
- Character writing question of type 'e' (advanced editor / TinyMCE)
- Multiline (paragraph 'p') question loaded via AJAX in the registrations list
  Note: the popup eye icon for paragraph answers is shown only when the truncated
  text is detected server-side; the AJAX path adds the link when len >= max_length.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    fill_tinymce,
    go_to,
    just_wait,
    login_orga,
    login_user,
    logout,
    submit_confirm,
)

pytestmark = pytest.mark.e2e

# Long enough texts to exceed FIELD_SNIPPET_LIMIT (150 chars) after HTML stripping
LONG_TEXT_REG_EDITOR = "REG_EDITOR_" + "AAAAAAA " * 40
LONG_HTML_REG_EDITOR = "<p>" + LONG_TEXT_REG_EDITOR + "</p>"

LONG_TEXT_REG_PARA = "REG_PARA_" + "BBBBBB " * 40
LONG_TEXT_CHAR_EDITOR = "CHAR_EDITOR_" + "CCCCCCC " * 40
LONG_HTML_CHAR_EDITOR = "<p>" + LONG_TEXT_CHAR_EDITOR + "</p>"
LONG_TEXT_CHAR_PARA = "CHAR_PARA_" + "DDDDDDD " * 40

REG_EDITOR_QUESTION = "reg advanced editor"
REG_PARA_QUESTION = "reg multiline"
CHAR_EDITOR_QUESTION = "char advanced editor"
CHAR_PARA_QUESTION = "char multiline"


def test_orga_post_popup(pw_page: Any) -> None:
    """Test that eye icons appear for long answers and clicking shows full content."""
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Enable characters feature
    go_to(page, live_server, "/test/manage/features/character/on")

    # Character: advanced editor writing question (e)
    create_char_editor_question(page, live_server)
    create_character_with_long_editor_answer(page, live_server)
    verify_char_editor_popup(page, live_server)

    # Character: multiline paragraph writing question (p)
    create_char_paragraph_question(page, live_server)
    fill_character_with_long_paragraph_answer(page, live_server)
    verify_char_paragraph_popup(page, live_server)

    # Registration: advanced editor question (e)
    create_reg_editor_question(page, live_server)

    logout(page)
    login_user(page, live_server)
    register_with_long_editor_answer(page, live_server)

    logout(page)
    login_orga(page, live_server)
    verify_reg_editor_popup(page, live_server)

    go_to(page, live_server, "/test/manage/registrations/")
    page.locator("a:has(i.fas.fa-trash)").click()

    # Registration: multiline paragraph question (p)
    create_reg_paragraph_question(page, live_server)

    logout(page)
    login_user(page, live_server)
    register_with_long_paragraph_answer(page, live_server)

    logout(page)
    login_orga(page, live_server)
    verify_reg_paragraph_popup(page, live_server)


#------------------------------------------------------------------------
# Registration: advanced editor question
#------------------------------------------------------------------------


def create_reg_editor_question(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/form/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("e")
    page.locator("#id_name").fill(REG_EDITOR_QUESTION)
    submit_confirm(page)


def _get_que_textarea_id(page: Any) -> str:
    """Return the id of the first 'id_que_*' textarea on the page."""
    return page.evaluate(
        """
        () => {
            const el = document.querySelector('textarea[id^="id_que_"]');
            return el ? el.id : '';
        }
    """
    )


def register_with_long_editor_answer(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/register/")
    editor_id = _get_que_textarea_id(page)
    fill_tinymce(page, editor_id, LONG_HTML_REG_EDITOR)
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)


def verify_reg_editor_popup(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/registrations/")
    # The editor column is hidden by default: toggle it visible
    page.get_by_role("link", name=REG_EDITOR_QUESTION).click()
    just_wait(page)
    # Eye icon should now appear in the column for the long answer
    eye_icon = page.locator(".post_popup").first
    eye_icon.wait_for(state="visible", timeout=10000)
    eye_icon.click()
    # Popup shows full content
    popup = page.locator("#uglipop_popbox")
    popup.wait_for(state="visible", timeout=10000)
    expect(popup).to_contain_text(LONG_TEXT_REG_EDITOR[:80])


#------------------------------------------------------------------------
# Registration: multiline paragraph question
#------------------------------------------------------------------------


def create_reg_paragraph_question(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/form/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("p")
    page.locator("#id_name").fill(REG_PARA_QUESTION)
    submit_confirm(page)


def register_with_long_paragraph_answer(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/register/")
    page.get_by_role("textbox", name=REG_PARA_QUESTION).fill(LONG_TEXT_REG_PARA)
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)


def verify_reg_paragraph_popup(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/registrations/")
    # Load the paragraph question answers via the AJAX load button
    page.get_by_role("link", name=REG_PARA_QUESTION).click()
    just_wait(page, big=True)
    # Eye icon should appear for the long paragraph answer
    eye_icon = page.locator(".post_popup").first
    eye_icon.wait_for(state="visible", timeout=10000)
    eye_icon.click()
    # Popup shows full content
    popup = page.locator("#uglipop_popbox")
    popup.wait_for(state="visible", timeout=10000)
    expect(popup).to_contain_text(LONG_TEXT_REG_PARA[:80])


#------------------------------------------------------------------------
# Character: advanced editor writing question
#------------------------------------------------------------------------


def create_char_editor_question(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/writing/form/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("e")
    page.locator("#id_name").fill(CHAR_EDITOR_QUESTION)
    submit_confirm(page)


def create_character_with_long_editor_answer(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/characters")
    page.locator("a:has(i.fas.fa-trash)").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("popup test character")
    # Fill the editor writing question with a long answer
    editor_id = _get_que_textarea_id(page)
    fill_tinymce(page, editor_id, LONG_HTML_CHAR_EDITOR)
    submit_confirm(page)


def verify_char_editor_popup(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/characters/")
    # Toggle the editor question column visible
    page.get_by_role("link", name=CHAR_EDITOR_QUESTION).click()
    just_wait(page)
    # Eye icon should appear for the long answer
    eye_icon = page.locator(".post_popup").first
    eye_icon.wait_for(state="visible", timeout=10000)
    eye_icon.click()
    # Popup shows full content
    popup = page.locator("#uglipop_popbox")
    popup.wait_for(state="visible", timeout=10000)
    expect(popup).to_contain_text(LONG_TEXT_CHAR_EDITOR[:80])


#------------------------------------------------------------------------
# Character: multiline paragraph writing question
#------------------------------------------------------------------------


def create_char_paragraph_question(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/writing/form/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("p")
    page.locator("#id_name").fill(CHAR_PARA_QUESTION)
    submit_confirm(page)


def fill_character_with_long_paragraph_answer(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/characters")
    page.locator("a:has(i.fas.fa-trash)").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").fill("popup test character 2")
    page.get_by_role("row").filter(has_text=CHAR_PARA_QUESTION).get_by_role("textbox").fill(LONG_TEXT_CHAR_PARA)
    submit_confirm(page)


def verify_char_paragraph_popup(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/characters/")
    # The paragraph column is loaded via AJAX (load_que); AJAX returns empty for inline
    # questions so the pre-rendered inline content (with eye icon) is preserved
    page.get_by_role("link", name=CHAR_PARA_QUESTION).click()
    just_wait(page)
    # Eye icon should appear for the long answer
    eye_icon = page.locator(".post_popup").first
    eye_icon.wait_for(state="visible", timeout=10000)
    eye_icon.click()
    # Popup shows full content
    popup = page.locator("#uglipop_popbox")
    popup.wait_for(state="visible", timeout=10000)
    expect(popup).to_contain_text(LONG_TEXT_CHAR_PARA[:80])
