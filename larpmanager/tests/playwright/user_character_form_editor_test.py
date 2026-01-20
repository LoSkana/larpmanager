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
Test: Character form editor with player editor feature.
Verifies dynamic character form creation with single/multiple choice fields, text fields,
prerequisites, availability limits, and player character creation/approval workflow.
"""
import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import just_wait, fill_tinymce, go_to, login_orga, submit_confirm, expect_normalized

pytestmark = pytest.mark.e2e


def test_user_character_form_editor(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    prepare(page, live_server)

    field_single(page, live_server)

    field_multiple(page, live_server)

    field_text(page, live_server)

    character(page, live_server)

    verify_characters_shortcut(page, live_server)


def prepare(page: Any, live_server: Any) -> None:
    # Activate characters
    go_to(page, live_server, "/test/manage/features/character/on")

    # Activate player editor
    go_to(page, live_server, "/test/manage/features/user_character/on")

    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name="Player editor ").click()
    page.locator("#id_user_character_approval").check()
    page.get_by_role("cell", name="Maximum number of characters").click()
    page.locator("#id_user_character_max").fill("1")
    page.get_by_role("link", name="Character form ").click()
    page.locator("#id_character_form_wri_que_max").check()
    page.locator("#id_character_form_wri_que_requirements").check()
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/writing/form/")
    expect_normalized(page, page.locator('[id="u1"]'), "Name")
    expect_normalized(page, page.locator('[id="u2"]'), "Presentation")
    expect_normalized(page, page.locator('[id="u3"]'), "Sheet")


def field_single(page: Any, live_server: Any) -> None:
    # add single
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("single")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("sssssingle")

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("ff")
    page.locator("#id_max_available").click()
    page.locator("#id_max_available").fill("3")
    submit_confirm(page)

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("rrrr")
    submit_confirm(page)

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("wwww")
    submit_confirm(page)

    submit_confirm(page)


def field_multiple(page: Any, live_server: Any) -> None:
    # Add multiple
    page.get_by_role("link", name="New").click()
    page.get_by_text("Question type").click()
    page.locator("#id_typ").select_option("m")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("rrrrrr")
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").fill("1")

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("q1")
    submit_confirm(page)

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("q2")
    submit_confirm(page)

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("q3")
    submit_confirm(page)

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("14")
    page.locator("#id_max_available").click()
    page.locator("#id_max_available").fill("3")
    page.get_by_role("row", name="Prerequisites").get_by_role("searchbox").fill("ww")
    page.get_by_role("option", name="Test Larp - single wwww").click()
    submit_confirm(page)

    submit_confirm(page)


def field_text(page: Any, live_server: Any) -> None:
    # Add text
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("t")
    page.get_by_role("cell", name="Question name (keep it short)").click()
    page.locator("#id_name").fill("text")
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").fill("10")
    submit_confirm(page)

    # Add paragraph
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("p")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("rrr")
    submit_confirm(page)

    # Create new character
    go_to(page, live_server, "/test/manage/characters")
    just_wait(page)
    page.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("provaaaa")

    fill_tinymce(page, "id_teaser", "adsdsadsa")

    fill_tinymce(page, "id_text", "rrrr")

    just_wait(page)
    page.locator("#id_que_u4").select_option("u3")
    page.locator("#id_que_u4").select_option("u1")
    page.get_by_role("checkbox", name="q2").check()
    page.locator("#id_que_u6").click()
    page.locator("#id_que_u6").fill("sad")
    page.locator("#id_que_u7").click()
    page.locator("#id_que_u7").fill("sadsadas")
    submit_confirm(page)


def character(page: Any, live_server: Any) -> None:
    # signup, create char
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    page.get_by_role("checkbox", name="Authorisation").check()
    submit_confirm(page)

    expect_normalized(page, page.locator("#one"), "Create your character!")
    page.get_by_role("link", name="Create your character!").click()
    just_wait(page)
    page.locator("#id_name").click()
    page.locator("#id_name").fill("my character")

    fill_tinymce(page, "id_teaser", "so coool")

    fill_tinymce(page, "id_text", "so braaaave")

    page.locator("#id_que_u4").select_option("u1")
    page.locator("#id_que_u4").select_option("u3")
    page.get_by_role("checkbox", name="- (Available 3)").check()
    page.locator("#id_que_u6").click()
    page.locator("#id_que_u6").fill("wow")
    page.locator("#id_que_u7").click()
    page.locator("#id_que_u7").fill("asdsadsa")
    submit_confirm(page)

    # confirm char
    expect_normalized(page, page.locator("#one"), "my character (Creation)")
    page.get_by_role("link", name="my character (Creation)").click()
    page.get_by_role("link", name="Change").click()
    page.get_by_role("cell", name="Click here to confirm that").click()
    page.get_by_text("Click here to confirm that").click()
    page.locator("#id_propose").check()
    submit_confirm(page)

    # check char
    expect_normalized(page, page.locator("#one"), "my character (Proposed)")

    # approve char
    go_to(page, live_server, "/test/manage/characters")
    page.locator('[id="u3"]').get_by_role("link", name="").click()
    page.locator("#id_status").select_option("a")
    submit_confirm(page)

    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Your character is my character")

    go_to(page, live_server, "/test")
    expect_normalized(page, page.locator("#one"), "Your character is my character")

def verify_characters_shortcut(page: Any, live_server: Any) -> None:
    """Enable the user_characters_shortcut configuration."""

    # Enable characters shortcut
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name="Interface ").click()
    page.locator("#id_user_characters_shortcut").check()
    page.locator("#id_user_registrations_shortcut").check()
    submit_confirm(page)

    # Verify the Characters link is visible in the topbar
    go_to(page, live_server, "/")
    just_wait(page)
    page.get_by_role("link", name=" Characters").click()

    # Verify the page shows characters content
    expect_normalized(page, page.locator("#one"), "character active last event character active last event my character test larp")

    page.get_by_role("link", name=" Registrations").click()

    expect_normalized(page, page.locator("#one"),
  """event date status details event date status details test larp 19 march 2050
            registration confirmed (standard) your character is my character""")
