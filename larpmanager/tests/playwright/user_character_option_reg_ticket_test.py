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
Test: Character form options restricted by registration ticket.
Verifies that character form field options are filtered based on the user's
selected ticket tier, enforcing ticket-specific restrictions on character creation.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import fill_tinymce, go_to, login_orga, logout, expect_normalized, submit_register, \
    submit_confirm, new_option, submit_option, sidebar, nav, get_modal_iframe, save_modal, _wait_select2_results, \
    _wait_lm_ready

pytestmark = pytest.mark.e2e


def test_user_character_option_reg_ticket(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/test/manage/")

    prepare(page)

    go_to(page, live_server, "/test")

    create_character(page)

    logout(page)

    go_to(page, live_server, "/test/character/u1")


def prepare(page: Any) -> None:
    # configure event
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Player editor").check()
    page.get_by_role("checkbox", name="Characters").check()
    submit_confirm(page)

    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Player editor ")).click()
    page.locator("#id_user_character_max").click()
    page.locator("#id_user_character_max").fill("1")
    page.get_by_role("link", name=re.compile(r"^Character Sheet")).click()
    page.locator("#id_character_form_wri_que_tickets").check()
    submit_confirm(page)

    # create ticket
    page.get_by_role("link", name="Tickets").first.click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("bambi")
    save_modal(page, edit_iframe)

    # set option based on ticket
    sidebar(page, "Sheet")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("choose")
    edit_iframe.locator("#id_status").select_option("m")

    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("st")
    option_row.get_by_role("searchbox").click()
    option_row.get_by_role("searchbox").fill("st")
    _wait_select2_results(edit_iframe)
    option_row.locator(".select2-results__option").first.click()
    submit_option(edit_iframe, option_row)

    option_row = new_option(edit_iframe)

    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("bmb")
    option_row.get_by_role("searchbox").click()
    option_row.get_by_role("searchbox").fill("bam")
    _wait_select2_results(edit_iframe)
    option_row.locator(".select2-results__option").first.click()
    submit_option(edit_iframe, option_row)

    expect_normalized(page, edit_iframe.locator("#options"), "bmb test larp (standard) bambi")
    save_modal(page, edit_iframe)


def create_character(page: Any) -> None:
    # signup first ticket
    page.get_by_role("link", name="Register").click()
    page.locator('label[for="id_ticket_0"]').click()
    submit_register(page)

    # confirm profile
    page.get_by_role("checkbox", name="Authorisation").check()
    submit_confirm(page)

    page.get_by_role("link", name="Create your character!").click()

    # check only one option
    expect(page.locator("#id_que_u4")).to_match_aria_snapshot('- radio "st"\n- text: st')
    page.locator('label[for="id_que_u4_0"]').click()  # select "st"

    # create player
    page.locator("#id_name").click()
    page.locator("#id_name").fill("myyyy")
    fill_tinymce(page, "id_teaser", "sdsa")
    fill_tinymce(page, "id_text", "asadas")
    submit_confirm(page)

    # check status, resubmit reg
    expect_normalized(page, page.locator("#one"), "Player: Admin Test choose: st Presentation sdsa")
    nav(page, "Registration")
    page.get_by_role("button", name="Continue").click()
    page.locator("a").filter(has_text=re.compile(r"^myyyy$")).click()
    _wait_lm_ready(page)
    expect_normalized(page, page.locator("#one"), "Player: Admin Test choose: st Presentation sdsa")

    # change ticket
    nav(page, "Registration")
    page.locator('label[for="id_ticket_1"]').click()
    page.get_by_role("button", name="Continue").click()
    page.locator("a").filter(has_text=re.compile(r"^myyyy$")).click()

    # check previous option is not selected anymore
    expect_normalized(page, page.locator("#one"), "The character have missing values in mandatory fields: choose")
    expect_normalized(page, page.locator("#one"), "Player: Admin Test Presentation sdsa Text asadas")
    page.get_by_role("link", name="myyyy").click()
    page.get_by_role("link", name="Edit").click()

    # check only one option available
    expect(page.locator("#id_que_u4")).to_match_aria_snapshot('- radio "bmb"\n- text: bmb')
    page.locator('label[for="id_que_u4_0"]').click()  # select "bmb" (only option)
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Player: Admin Test choose: bmb Presentation sdsa")

    # check with registration resubmit
    nav(page, "Registration")
    page.get_by_role("button", name="Continue").click()
    page.locator("a").filter(has_text=re.compile(r"^myyyy$")).click()
    page.get_by_role("link", name="Edit").click()
    expect(page.locator("#id_que_u4")).to_match_aria_snapshot('- radio "bmb"')
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Player: Admin Test choose: bmb Presentation sdsa")
