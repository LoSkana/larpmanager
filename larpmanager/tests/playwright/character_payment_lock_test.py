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

"""Test: Character access locked until the payment proof is uploaded.

Verifies that, with the payment required config enabled, the player cannot see nor open the
character creation until a payment proof is submitted for the registration, and that the
lock is lifted as soon as the proof is uploaded, even before organizer approval.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    expect_normalized,
    get_modal_iframe,
    go_to,
    login_orga,
    login_user,
    logout,
    save_modal,
    submit,
    submit_confirm,
    submit_register,
)

pytestmark = pytest.mark.e2e


def test_character_payment_lock(pw_page: Any) -> None:
    """Test the character access lock until the payment proof is uploaded."""
    page, live_server, _unused = pw_page

    login_orga(page, live_server)
    setup_event(page, live_server)
    logout(page)

    login_user(page, live_server)
    go_to(page, live_server, "/test/register/")
    submit_register(page)

    check_locked(page, live_server)
    upload_payment_proof(page, live_server)
    check_unlocked(page, live_server)


def setup_event(page: Any, live_server: Any) -> None:
    """Activate player characters, wire payments, a paid ticket and the payment required config."""
    go_to(page, live_server, "/test/manage/features/character/on")
    go_to(page, live_server, "/test/manage/features/user_character/on")
    go_to(page, live_server, "/manage/features/payment/on")

    go_to(page, live_server, "/manage/methods")
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").fill("test wire")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_payee").fill("test beneficiary")
    page.locator("#id_wire_iban").fill("test iban")
    page.locator("#id_wire_bic").fill("test bic")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/tickets")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_price").fill("100.00")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/manage/config")
    page.locator("#main_form").get_by_role("link", name=re.compile(r"^Character creation")).click()
    page.locator("#id_user_character_payment_required").check()
    submit_confirm(page)


def check_locked(page: Any, live_server: Any) -> None:
    """Check character links are hidden, and character pages redirect to the payment."""
    go_to(page, live_server, "/test/")
    expect_normalized(page, page.locator(".event-card-char"), "complete your payment to create or choose")
    expect(page.locator("#sidebar").get_by_role("link", name="Create your character")).to_have_count(0)

    go_to(page, live_server, "/test/character/create/")
    expect(page).to_have_url(re.compile(r"/(accounting/registration|test/payments)/"))
    expect_normalized(page, page.locator("#one"), "complete your payment to create or choose your character")

    go_to(page, live_server, "/test/character/list/")
    expect(page).to_have_url(re.compile(r"/(accounting/registration|test/payments)/"))


def upload_payment_proof(page: Any, live_server: Any) -> None:
    """Submit the wire transfer receipt for the registration."""
    go_to(page, live_server, "/test/register/")
    page.get_by_role("link", name=re.compile(r"to confirm your registration")).click()
    page.get_by_role("checkbox", name="Payment confirmation:").check()
    submit(page)


def check_unlocked(page: Any, live_server: Any) -> None:
    """Check the character creation is available once the proof is uploaded, before approval."""
    go_to(page, live_server, "/test/")
    expect(page.locator("#sidebar").get_by_role("link", name="Create your character")).to_be_visible()

    go_to(page, live_server, "/test/character/create/")
    expect(page.locator("#id_name")).to_be_visible()
