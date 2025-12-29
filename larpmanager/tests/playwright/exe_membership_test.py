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


from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, load_image, login_orga, submit, submit_confirm, expect_normalized

pytestmark = pytest.mark.e2e


def test_exe_membership(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # activate members
    go_to(page, live_server, "/manage/features/membership/on")

    # register
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # confirm profile
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)

    # compile request
    load_image(page, "#id_request")
    load_image(page, "#id_document")
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
    expect_normalized(page.locator("#one"), "Total members: 1 - Request: 1")
    expect_normalized(page.locator("#one"), "Test")
    expect_normalized(page.locator("#one"), "Admin")
    expect_normalized(page.locator("#one"), "orga@test.it")
    expect_normalized(page.locator("#one"), "Test Larp")

    # approve
    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Request").click()
    submit_confirm(page)

    # test
    expect_normalized(page.locator("#one"), "Total members: 1 - Accepted: 1")
    expect_normalized(page.locator("#one"), "Test")
    expect_normalized(page.locator("#one"), "Admin")
    expect_normalized(page.locator("#one"), "orga@test.it")
    expect_normalized(page.locator("#one"), "Test Larp")
