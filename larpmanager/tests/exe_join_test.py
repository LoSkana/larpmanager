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

from pathlib import Path

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, submit

pytestmark = pytest.mark.e2e


def test_exe_join(pw_page):
    page, live_server, _ = pw_page

    go_to(page, live_server, "/debug")

    go_to(page, live_server, "/join")
    page.get_by_role("link", name="Register").click()
    page.get_by_role("textbox", name="Email address").click()
    page.get_by_role("textbox", name="Email address").fill("orga@prova.it")
    page.get_by_role("textbox", name="Email address").press("Tab")
    page.get_by_role("textbox", name="Password", exact=True).fill("banana1234!")
    page.get_by_role("textbox", name="Password", exact=True).press("Tab")
    page.get_by_role("textbox", name="Password confirmation").fill("banana1234!")
    page.get_by_role("textbox", name="Name", exact=True).click()
    page.get_by_role("textbox", name="Name", exact=True).fill("prova")
    page.get_by_role("cell", name="Yes, keep me posted! Do you").click()
    page.get_by_label("Newsletter").select_option("o")
    page.get_by_role("textbox", name="Surname").click()
    page.get_by_role("textbox", name="Surname").fill("orga")
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)

    go_to(page, live_server, "/join")
    page.get_by_role("textbox", name="Name").click()
    page.get_by_role("textbox", name="Name").fill("Prova Larp")
    page.locator("#id_profile").wait_for(state="visible")
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_profile").set_input_files(str(image_path))
    page.locator("#slug").fill("prova")
    submit(page)

    page.wait_for_timeout(1000)
    go_to(page, live_server, "/debug/prova")

    expect(page.locator("#header")).to_contain_text("Prova Larp")
