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
Test: Make Credits page readonly in event panel
Verifies activation of Credits feature, setting of readonly flag,
and CRUD actions with flag active and inactive.
"""

import re
from typing import Any

import pytest

from larpmanager.tests.utils import get_modal_iframe, go_to, login_orga, submit_confirm, save_modal
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

def test_credits_readonly_event(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    # Login as admin
    login_orga(page, live_server)

    # Activate Credits feature (keep readonly flag deactivated)
    go_to(page, live_server, "/manage/features/")
    page.get_by_role("checkbox", name="Credits").check()
    page.get_by_role("button", name="Confirm").click()

    # Go to event and insert a new Credit
    go_to(page, live_server, "/test/manage/credits/")
    page.get_by_role("link", name= "New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("org")
    edit_iframe.get_by_role("option", name="Admin Test - orga@test.it").click()
    edit_iframe.locator("#id_value").fill("10")
    edit_iframe.locator("#id_descr").fill("test")
    save_modal(page, edit_iframe)

    # Check presence of New, Edit and Delete links
    expect(page.get_by_role("link", name= "New")).to_have_count(1)
    expect(page.locator('i.fas.fa-edit')).to_have_count(1)
    expect(page.locator('i.fas.fa-trash')).to_have_count(1)

    # Activate readonly flag
    go_to(page, live_server, "/manage/config/")
    page.locator('a[tog="sec_credits"]').click()
    page.locator("#id_credit_readonly_event").check()
    page.get_by_role("button", name="Confirm").click()

    # Go to event and check lack of New, Edit and Delete links
    go_to(page, live_server, "/test/manage/credits/")
    expect(page.get_by_role("link", name= "New")).to_have_count(0)
    expect(page.locator('i.fas.fa-edit')).to_have_count(0)
    expect(page.locator('i.fas.fa-trash')).to_have_count(0)

    # Go to orga and check presence of New, Edit and Delete links
    go_to(page, live_server, "/manage/credits/")
    expect(page.get_by_role("link", name= "New")).to_have_count(1)
    expect(page.locator('i.fas.fa-edit')).to_have_count(1)
    expect(page.locator('i.fas.fa-trash')).to_have_count(1)
