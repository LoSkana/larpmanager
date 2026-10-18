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

"""Test: Require payment before characters.

Verifies that with the require_payment config the registration is shown as incomplete, and the
player cannot create a character until a payment is submitted, while it can afterwards.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    expect_normalized,
    fill_tinymce,
    get_modal_iframe,
    go_to,
    load_image,
    login_orga,
    login_user,
    logout,
    save_modal,
    sidebar,
    submit,
    submit_confirm,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_require_payment(pw_page: Any) -> None:
    """Test characters are blocked until the registration payment is submitted."""
    page, live_server, _unused = pw_page

    login_orga(page, live_server)
    setup_event(page, live_server)
    logout(page)

    login_user(page, live_server)
    go_to(page, live_server, "/test/register/")
    submit_register(page)

    check_blocked(page, live_server)
    pay_wire(page, live_server)
    check_unlocked(page, live_server)


def setup_event(page: Any, live_server: Any) -> None:
    """Enable payments and player characters, with a paid ticket and the require_payment config."""
    go_to(page, live_server, "/manage/features/payment/on")
    go_to(page, live_server, "/manage/config")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Payments")).click()
    page.locator("#id_payment_require_receipt").check()
    submit_confirm(page)

    go_to(page, live_server, "/manage/methods")
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("test wire")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_payee").fill("test beneficiary")
    page.locator("#id_wire_iban").fill("test iban")
    page.locator("#id_wire_bic").fill("test iban")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/tickets")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_price").click()
    edit_iframe.locator("#id_price").fill("100.00")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/manage/features/character/on")
    go_to(page, live_server, "/test/manage/features/user_character/on")

    go_to(page, live_server, "/test/manage/config")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Payments")).click()
    page.locator("#id_require_payment").check()
    submit_confirm(page)


def check_blocked(page: Any, live_server: Any) -> None:
    """Check the registration is incomplete, and creating a character leads to the payment page."""
    go_to(page, live_server, "/test/")
    expect_normalized(page, page.locator("#one"), "Your registration is not complete")
    expect(page.get_by_role("link", name=re.compile("Create your character"))).to_have_count(0)

    go_to(page, live_server, "/test/character/create/")
    expect(page).to_have_url(re.compile(r"/test/payments/"))
    expect_normalized(page, page.locator("body"), "Complete your registration by submitting your payment")

    go_to(page, live_server, "/test/character/list/")
    expect(page.get_by_role("link", name="Create new character")).to_have_count(0)


def pay_wire(page: Any, live_server: Any) -> None:
    """Submit a wire transfer payment with its receipt."""
    go_to(page, live_server, "/test/")
    page.get_by_role("link", name=re.compile(r"Submit your payment")).first.click()

    # the only payment method available is shown directly
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()
    submit(page)


def check_unlocked(page: Any, live_server: Any) -> None:
    """Check the submitted payment allows creating the character, which is assigned to the registration."""
    go_to(page, live_server, "/test/")
    expect_normalized(page, page.locator("#one"), "Create the character you will play in this event")

    go_to(page, live_server, "/test/register/")
    sidebar(page, "Create your character")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("paid character")
    fill_tinymce(page, "id_teaser", "teaser of paid character")
    fill_tinymce(page, "id_text", "sheet of paid character")
    submit_confirm(page)

    go_to(page, live_server, "/test/character/list/")
    expect(page.locator(".char-choose-badge")).to_have_count(1)
    expect(page.locator("#characters")).to_contain_text("paid character")
