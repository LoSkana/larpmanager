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
Test: Verify presence of AICS button
Verifies activation of Bureucracy feature and AICS button,
registration of 10 members, and then verify presence of AICS button in Enrolment page.
"""

import re
from typing import Any

import pytest

from larpmanager.tests.utils import go_to, login_orga, load_image, logout
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

def test_credits_readonly_event(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    # Login as admin
    login_orga(page, live_server)

    # Activate Payment, Membership and Bureucracy features
    go_to(page, live_server, "/manage/features/")
    page.get_by_role("checkbox", name="Payments", exact=True).check()
    page.get_by_role("checkbox", name="Membership", exact=True).check()
    page.get_by_role("checkbox", name="Bureaucracy", exact=True).check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # Configure features
    go_to(page, live_server, "/manage/config/")
    page.get_by_role("link", name="Bureaucracy").click()
    page.locator("#id_aics").check()
    page.get_by_role("link", name=re.compile(r"^Members\s.+")).click()
    page.locator("#id_membership_fee").fill("5")
    page.locator("#id_membership_day").fill("01-01")
    page.locator("#id_membership_grazing").fill("0")
    page.get_by_role("button", name="Confirm", exact=True).click()
    go_to(page, live_server, "/manage/methods/")
    page.get_by_role("checkbox", name="Wire", exact=True).check()
    page.locator("#id_wire_descr").fill("x")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_payee").fill("x")
    page.locator("#id_wire_iban").fill("x")
    page.locator("#id_wire_bic").fill("x")
    page.get_by_role("button", name="Confirm").click()

    # Register 10 users
    users = ["user1@test.it","user2@test.it","user3@test.it","user4@test.it","user5@test.it","user6@test.it","user7@test.it","user8@test.it","user9@test.it","user0@test.it"]
    for user in users:

        # Register user
        logout(page)
        go_to(page, live_server, "/register/")
        page.get_by_role("textbox", name="Email address", exact=True).fill(user)
        page.get_by_role("textbox", name="Password", exact=True).fill("bananana")
        page.get_by_role("textbox", name="Password confirmation", exact=True).fill("bananana")
        page.get_by_role("checkbox", name="Authorisation", exact=True).check()
        page.get_by_role("textbox", name="Name", exact=True).fill(user[:5])
        page.get_by_role("textbox", name="Surname", exact=True).fill(user[:5])
        page.get_by_role("button", name="Submit", exact=True).click()

        # Submit membership request
        go_to(page, live_server, "/profile/")
        page.get_by_role("checkbox", name="Authorisation", exact=True).check()
        page.get_by_role("button", name="Submit", exact=True).click()
        go_to(page, live_server, "/membership/")
        load_image(page, "#id_request")
        load_image(page, "#id_document")
        page.get_by_role("button", name="Submit").click()
        page.locator("#id_confirm_1").check()
        page.locator("#id_confirm_2").check()
        page.locator("#id_confirm_3").check()
        page.locator("#id_confirm_4").check()
        page.get_by_role("button", name="Submit").click()

        # Login as admin and accept membership request
        logout(page)
        login_orga(page, live_server)
        go_to(page, live_server, "/manage/membership/")
        page.get_by_role("link", name="Request").click()
        page.get_by_role("button", name="Confirm").click()

        # Login as user and pay membership fee
        logout(page)
        go_to(page, live_server, "/login")
        page.locator("#id_username").fill(user)
        page.locator("#id_password").fill("bananana")
        page.get_by_role("button", name="Submit", exact=True).click()
        go_to(page, live_server, "/accounting/membership/")
        page.get_by_role("button", name="Submit").click()
        page.locator("#id_payment_confirmed").check()
        page.get_by_role("button", name="Submit").click()

        # Login as admin and accept membership fee (finally enrolled!)
        logout(page)
        login_orga(page, live_server)
        go_to(page, live_server, "/manage/membership/")
        page.get_by_role("link", name="Confirm").click()

    # As admin, after 10 enrolments, check presence of AICS button in Enrolment page
    go_to(page, live_server, "/manage/enrolment/")
    expect(page.get_by_role("button", name="AICS")).to_have_count(1)
