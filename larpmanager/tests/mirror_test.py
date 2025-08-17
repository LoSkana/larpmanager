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

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_orga, submit

pytestmark = pytest.mark.e2e


def test_orga_mirror(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # activate characters
    go_to(page, live_server, "/test/1/manage/features/178/on")

    # show chars
    go_to(page, live_server, "/test/1/manage/config")
    page.get_by_role("link", name=re.compile(r"^Writing")).click()
    page.locator("#id_writing_field_visibility").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/manage/run")
    page.locator("#id_show_character_0").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # check gallery
    go_to(page, live_server, "/test/1/")
    expect(page.locator("#one")).to_contain_text("Test Character")

    # activate casting
    go_to(page, live_server, "/test/1/manage/features/27/on")

    # activate mirror
    go_to(page, live_server, "/test/1/manage/config")
    page.get_by_role("link", name=re.compile(r"^Casting\s.+")).click()
    page.locator("#id_casting_mirror").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # create mirror
    go_to(page, live_server, "/test/1/manage/characters/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("Mirror")
    page.locator("#id_mirror").select_option("1")
    page.get_by_role("button", name="Confirm", exact=True).click()

    # check gallery
    go_to(page, live_server, "/test/1/")
    expect(page.locator("#one")).to_contain_text("Mirror")
    expect(page.locator("#one")).to_contain_text("Test Character")

    casting(live_server, page)


def casting(live_server, page):
    go_to(page, live_server, "/test/1/manage/config")
    page.get_by_role("link", name=re.compile(r"^Casting\s.+")).click()
    page.locator("#id_casting_characters").click()
    page.locator("#id_casting_characters").fill("1")
    page.locator("#id_casting_min").click()
    page.locator("#id_casting_min").fill("1")
    page.locator("#id_casting_max").click()
    page.locator("#id_casting_max").fill("1")
    page.get_by_role("button", name="Confirm", exact=True).click()

    # sign up and fill preferences
    go_to(page, live_server, "/test/1/register")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/casting")
    page.locator("#faction0").select_option("all")
    page.locator("#choice0").click()
    expect(page.locator("#casting")).to_contain_text("Mirror")
    expect(page.locator("#casting")).to_contain_text("Test Character")
    page.locator("#choice0").select_option("2")
    submit(page)

    # perform casting
    go_to(page, live_server, "/test/1/manage/casting")
    page.get_by_role("button", name="Start algorithm").click()
    expect(page.locator("#assegnazioni")).to_contain_text("#1 Test Character")
    expect(page.locator("#assegnazioni")).to_contain_text("-> #2 Mirror")
    page.get_by_role("button", name="Upload").click()

    # check assignment
    go_to(page, live_server, "/test/1/manage/registrations")
    expect(page.locator("#one")).to_contain_text("#1 Test Character")

    go_to(page, live_server, "/test/1")
    expect(page.locator("#one")).to_contain_text("Test Character")
    expect(page.locator("#one")).not_to_contain_text("Mirror")
