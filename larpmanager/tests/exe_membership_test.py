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
from playwright.sync_api import expect, sync_playwright

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start, submit


@pytest.mark.django_db(transaction=True)
def test_exe_membership(live_server):
    with sync_playwright() as p:
        browser, context, page = page_start(p)
        try:
            exe_membership(live_server, page)

        except Exception as e:
            handle_error(page, e, "exe_membership")

        finally:
            context.close()
            browser.close()


def exe_membership(live_server, page):
    login_orga(page, live_server)

    # activate members
    go_to(page, live_server, "/manage/features/45/on")

    # register
    go_to(page, live_server, "/test/1/register")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # confirm profile
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)

    # compile request
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_request").set_input_files(str(image_path))
    page.locator("#id_document").set_input_files(str(image_path))
    submit(page)

    # confirm request
    page.locator("#id_confirm_1").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_2").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_3").check()
    page.locator("#id_confirm_4").check()
    submit(page)

    # go to memberships
    go_to(page, live_server, "/manage/membership/")
    expect(page.locator("#one")).to_contain_text("Request (1)")
    expect(page.locator("#one")).to_contain_text("Test")
    expect(page.locator("#one")).to_contain_text("Admin")
    expect(page.locator("#one")).to_contain_text("orga@test.it")
    expect(page.locator("#one")).to_contain_text("Test Larp")

    # open pages
    page.get_by_role("link", name="Details").click()
    go_to(page, live_server, "/manage/membership/")
    expect(page.locator("#banner")).not_to_contain_text("Oops!")

    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Member").click()
    expect(page.locator("#banner")).not_to_contain_text("Oops!")

    # approve
    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Request").click()
    page.get_by_role("button", name="Approve").click()

    # test
    expect(page.locator("#one")).to_contain_text("Accepted (1)")
    expect(page.locator("#one")).to_contain_text("Test")
    expect(page.locator("#one")).to_contain_text("Admin")
    expect(page.locator("#one")).to_contain_text("orga@test.it")
    expect(page.locator("#one")).to_contain_text("Test Larp")
