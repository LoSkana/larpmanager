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
import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_orga, submit, submit_confirm, expect_normalized

pytestmark = pytest.mark.e2e


def test_orga_mirror(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # activate characters
    go_to(page, live_server, "/test/manage/features/character/on")

    # show chars
    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Writing")).click()
    page.locator("#id_writing_field_visibility").check()
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/run")
    page.locator("#id_show_character_0").check()
    submit_confirm(page)

    # check gallery
    go_to(page, live_server, "/test/")
    expect_normalized(page.locator("#one"), "Test Character")

    # activate casting
    go_to(page, live_server, "/test/manage/features/casting/on")

    # activate mirror
    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Casting\s.+")).click()
    page.locator("#id_casting_mirror").check()
    submit_confirm(page)

    # create mirror
    go_to(page, live_server, "/test/manage/characters/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Mirror")
    page.locator("#id_mirror").select_option("u1")
    submit_confirm(page)

    # check gallery
    go_to(page, live_server, "/test/")
    expect_normalized(page.locator("#one"), "Mirror")
    expect_normalized(page.locator("#one"), "Test Character")

    casting(live_server, page)


def casting(live_server: Any, page: Any) -> None:
    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Casting\s.+")).click()
    page.locator("#id_casting_characters").click()
    page.locator("#id_casting_characters").fill("1")
    page.locator("#id_casting_min").click()
    page.locator("#id_casting_min").fill("1")
    page.locator("#id_casting_max").click()
    page.locator("#id_casting_max").fill("1")
    submit_confirm(page)

    # sign up and fill preferences
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    go_to(page, live_server, "/test/casting")
    page.locator("#faction0").select_option("all")
    page.locator("#choice0").click()
    expect_normalized(page.locator("#casting"), "Mirror")
    expect_normalized(page.locator("#casting"), "Test Character")
    page.locator("#choice0").select_option("u2")
    submit(page)

    # perform casting
    go_to(page, live_server, "/test/manage/casting")
    page.get_by_role("button", name="Start algorithm").click()
    expect_normalized(page.locator("#assegnazioni"), "#1 Test Character")
    expect_normalized(page.locator("#assegnazioni"), "-> #2 Mirror")
    page.get_by_role("button", name="Upload").click()

    # check assignment
    go_to(page, live_server, "/test/manage/registrations")
    expect_normalized(page.locator("#one"), "#1 Test Character")

    go_to(page, live_server, "/test")
    expect_normalized(page.locator("#one"), "Test Character")
    expect(page.locator("#one")).not_to_contain_text("Mirror")
