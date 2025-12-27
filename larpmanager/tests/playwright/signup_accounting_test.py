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

from larpmanager.tests.utils import go_to, load_image, login_orga, submit, submit_confirm

pytestmark = pytest.mark.e2e


def test_signup_accounting(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup_payment(live_server, page)

    signup_pay(live_server, page)

    token_credits(live_server, page)

    pay(live_server, page)

    discount(live_server, page)

    check_delete(live_server, page)


def check_delete(live_server: Any, page: Any) -> None:
    # update signup - orga
    go_to(page, live_server, "/test/manage/registrations")
    page.wait_for_selector("table")
    page.locator("a:has(i.fas.fa-edit)").click(force=True)
    submit_confirm(page)

    # cancel signup
    page.locator("a:has(i.fas.fa-edit)").click(force=True)
    page.get_by_role("link", name="Delete").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirmation delete").click()
    go_to(page, live_server, "/test/manage/cancellations")
    expect(page.get_by_role("row", name="100 52 24 4 Admin Test")).to_contain_text("orga@test.it")

    # delete payments
    go_to(page, live_server, "/test/manage/tokens")
    page.get_by_role("row", name="Admin Test Test Larp teeest").get_by_role("link").click()
    page.get_by_role("link", name="Delete").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirmation delete").click()
    go_to(page, live_server, "/test/manage/credits")
    page.get_by_role("row", name="Admin Test Test Larp testet").get_by_role("link").click()
    page.get_by_role("link", name="Delete").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirmation delete").click()
    go_to(page, live_server, "/test/manage/payments")
    page.get_by_role("row", name="Admin Test Wire Money").get_by_role("link").click()
    page.get_by_role("link", name="Delete").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirmation delete").click()


def discount(live_server: Any, page: Any) -> None:
    # check signup
    go_to(page, live_server, "/test/manage/registrations")
    page.get_by_role("link", name="accounting", exact=True).click()
    # Check for registration data with discount applied
    expect(page.locator("#regs_u1_Participant")).to_contain_text("100")
    expect(page.locator("#regs_u1_Participant")).to_contain_text("52")
    go_to(page, live_server, "/test/register")
    page.locator("#one").get_by_role("link", name="Accounting").click()
    expect(page.locator("#one")).to_contain_text("Total payments: 100")

    # update signup
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # use discount
    go_to(page, live_server, "/test/manage/features/discount/on")
    go_to(page, live_server, "/test/manage/discounts/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("discount")
    page.get_by_role("checkbox", name="Test Larp").check()
    page.locator("#id_value").click()
    page.locator("#id_value").press("Home")
    page.locator("#id_value").fill("20")
    page.locator("#id_value").press("Tab")
    page.locator("#id_max_redeem").fill("0")
    page.locator("#id_cod").click()
    page.locator("#id_cod").fill("code")
    page.locator("#id_typ").select_option("a")
    page.locator("#id_visible").check()
    page.locator("#id_only_reg").uncheck()
    submit_confirm(page)

    go_to(page, live_server, "/test/register/")
    page.get_by_role("link", name="Discounts ").click()
    page.locator("#id_discount").click()
    page.locator("#id_discount").fill("code")
    page.locator("#discount_go").click()
    page.wait_for_timeout(2000)
    expect(page.locator("#discount_res")).to_contain_text(
        "The discount has been added! It has been reserved for you for 15 minutes, after which it will be removed"
    )
    expect(page.locator("#discount_tbl")).to_contain_text("20.00€")
    page.get_by_role("button", name="Continue").click()
    expect(page.locator("#riepilogo")).to_contain_text("Your updated registration total is: 80€.")
    page.wait_for_timeout(2000)
    page.locator("#register_go").click()


def pay(live_server: Any, page: Any) -> None:
    # check accounting
    go_to(page, live_server, "/test/register")
    page.locator("#one").get_by_role("link", name="Accounting").click()
    expect(page.locator("#one")).to_contain_text("Total registration fee: 100")
    expect(page.locator("#one")).to_contain_text("Total payments: 48")
    expect(page.locator("#one")).to_contain_text("Next payment: 52")
    go_to(page, live_server, "/test/manage/registrations")
    page.get_by_role("link", name="accounting", exact=True).click()
    # Check for registration accounting data in the table
    expect(page.locator("#regs_u1_Participant")).to_contain_text("52")
    expect(page.locator("#regs_u1_Participant")).to_contain_text("48")
    expect(page.locator("#regs_u1_Participant")).to_contain_text("100")

    # pay
    go_to(page, live_server, "/accounting/registration/u1/")
    expect(page.locator("#one")).to_contain_text("100")
    expect(page.locator("#one")).to_contain_text("48")
    expect(page.locator("#one")).to_contain_text("52")
    submit(page)
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()

    expect(page.locator("#one")).to_contain_text("52")
    submit(page)

    # confirm payment
    go_to(page, live_server, "/test/manage/invoices")
    expect(page.get_by_role("row", name="Admin Test Wire registration")).to_contain_text("52")
    page.get_by_role("link", name="Confirm", exact=True).click()


def token_credits(live_server: Any, page: Any) -> None:
    # activate tokens credits
    go_to(page, live_server, "/manage/features/tokens/on")
    go_to(page, live_server, "/manage/features/credits/on")
    go_to(page, live_server, "/manage/tokens")
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("ad")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("7")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("test")
    submit_confirm(page)

    go_to(page, live_server, "/manage/credits")
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("org")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("5")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("test")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/tokens")
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("org")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("17")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("teeest")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/credits")
    page.get_by_role("link", name="New").click()
    page.get_by_text("---------").click()
    page.get_by_role("searchbox").fill("org")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("19")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("testet")
    submit_confirm(page)


def signup_pay(live_server: Any, page: Any) -> None:
    # Signup
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)
    go_to(page, live_server, "/test/register")
    expect(page.locator("#one")).to_contain_text("Provisional registration")
    page.locator("#one").get_by_role("link", name="Accounting").click()
    expect(page.locator("#one")).to_contain_text("100")

    # Check accounting
    go_to(page, live_server, "/accounting")
    expect(page.locator("#one")).to_contain_text("100")

    # check pay
    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name=re.compile(r"proceed with payment")).click()
    page.get_by_role("cell", name="Wire", exact=True).click()
    expect(page.locator("b")).to_contain_text("100")
    submit(page)
    expect(page.locator("#one")).to_contain_text("100")
    expect(page.locator("#one")).to_contain_text("test beneficiary")
    expect(page.locator("#one")).to_contain_text("test iban")


def setup_payment(live_server: Any, page: Any) -> None:
    # Activate payments
    go_to(page, live_server, "/manage/features/payment/on")

    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_cc").check()
    page.locator("#id_mail_signup_new").check()
    page.locator("#id_mail_signup_update").check()
    page.locator("#id_mail_signup_del").check()
    page.locator("#id_mail_payment").check()

    page.get_by_role("link", name="Payments ").click()
    page.locator("#id_payment_require_receipt").check()

    submit_confirm(page)
    go_to(page, live_server, "/manage/methods")
    page.locator('#id_payment_methods input[type="checkbox"][value="1"]').check()
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("test wire")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_descr").press("Tab")
    page.locator("#id_wire_payee").fill("test beneficiary")
    page.locator("#id_wire_payee").press("Tab")
    page.locator("#id_wire_iban").fill("test iban")
    submit_confirm(page)

    # set ticket price
    go_to(page, live_server, "/test/manage/tickets")
    page.wait_for_selector("table.go_datatable")
    page.wait_for_selector("a:has(i.fas.fa-edit)", timeout=10000)
    page.locator("a:has(i.fas.fa-edit)").click(force=True)
    page.locator("#id_price").click()
    page.locator("#id_price").fill("100.00")
    submit_confirm(page)
