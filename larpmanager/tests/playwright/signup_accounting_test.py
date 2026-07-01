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
Test: Registration accounting with payments, tokens, credits, and discounts.
Verifies signup payment workflows, token/credit management, discount codes,
payment confirmation, and registration cancellation with refunds.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import get_modal_iframe, go_to, load_image, login_orga, submit, submit_confirm, \
    submit_register, delete_modal, \
    expect_normalized, save_modal, wait_accounting_load, _wait_lm_ready, SHORT_TIMEOUT

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
    page.wait_for_selector("table.go_datatable")
    page.wait_for_selector(".fa-edit", timeout=SHORT_TIMEOUT)
    page.locator(".fa-edit").click(force=True)
    edit_iframe = get_modal_iframe(page)
    save_modal(page, edit_iframe)

    # cancel signup
    go_to(page, live_server, "/test/manage/registrations")
    delete_modal(page)
    expect(page.locator("#one")).not_to_contain_text("Admin Test")

    # delete payments
    go_to(page, live_server, "/test/manage/tokens")
    delete_modal(page, page.get_by_role("row", name="Admin Test Test Larp teeest").locator('.fa-trash'))

    go_to(page, live_server, "/test/manage/credits")
    delete_modal(page, page.get_by_role("row", name="Admin Test Test Larp testet").locator('.fa-trash'))

    go_to(page, live_server, "/test/manage/payments")
    delete_modal(page, page.get_by_role("row", name="Admin Test Wire Money").locator('.fa-trash'))



def discount(live_server: Any, page: Any) -> None:
    # check signup
    go_to(page, live_server, "/test/manage/registrations")
    page.get_by_role("link", name="accounting", exact=True).click()
    wait_accounting_load(page)
    # Check for registration data with discount applied
    expect_normalized(page, page.locator("#regs_u1_Participant"), "100")
    expect_normalized(page, page.locator("#regs_u1_Participant"), "52")
    go_to(page, live_server, "/test/register")
    page.locator("#one").get_by_role("link", name="Accounting").click()
    _wait_lm_ready(page)
    expect_normalized(page, page.locator("#one"), "Total payments: 100")

    # update signup
    go_to(page, live_server, "/test/register")
    submit_register(page)

    # use discount
    go_to(page, live_server, "/test/manage/features/discount/on")
    go_to(page, live_server, "/test/manage/discounts/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("discount")
    edit_iframe.get_by_role("checkbox", name="Test Larp").check(force=True)
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").press("Home")
    edit_iframe.locator("#id_value").fill("20")
    edit_iframe.locator("#id_value").press("Tab")
    edit_iframe.locator("#id_max_redeem").fill("0")
    edit_iframe.locator("#id_cod").click()
    edit_iframe.locator("#id_cod").fill("code")
    edit_iframe.locator("#id_typ").select_option("a")
    edit_iframe.locator("#id_visible").check()
    edit_iframe.locator("#id_only_reg").uncheck()
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/register/")
    page.get_by_role("link", name=re.compile(r"^Discounts ")).click()
    page.locator("#id_discount").click()
    page.locator("#id_discount").fill("code")
    page.locator("#discount_go").click()
    expect_normalized(page,
        page.locator("#discount_res"),
        "The discount has been added! It has been reserved for you for 15 minutes, after which it will be removed",
    )
    expect_normalized(page, page.locator("#discount_tbl"), "20.00€")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "Your updated registration total is: 80€.")
    page.locator("#register_go").click()


def pay(live_server: Any, page: Any) -> None:
    # check accounting
    go_to(page, live_server, "/test/register")
    page.locator("#one").get_by_role("link", name="Accounting").click()
    _wait_lm_ready(page)
    expect_normalized(page, page.locator("#one"), "Total registration fee: 100")
    expect_normalized(page, page.locator("#one"), "Total payments: 48")
    expect_normalized(page, page.locator("#one"), "Next payment: 52")
    go_to(page, live_server, "/test/manage/registrations")
    page.get_by_role("link", name="accounting", exact=True).click()
    # Check for registration accounting data in the table
    wait_accounting_load(page)
    expect_normalized(page, page.locator("#regs_u1_Participant"), "52")
    expect_normalized(page, page.locator("#regs_u1_Participant"), "48")
    expect_normalized(page, page.locator("#regs_u1_Participant"), "100")

    # pay
    go_to(page, live_server, "/accounting/registration/u1/")
    expect_normalized(page, page.locator("#one"), "100")
    expect_normalized(page, page.locator("#one"), "48")
    expect_normalized(page, page.locator("#one"), "52")
    page.get_by_role("cell", name="Wire", exact=True).click()
    submit(page)
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()

    expect_normalized(page, page.locator("#one"), "52")
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
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("ad")
    edit_iframe.get_by_role("option", name="Admin Test - orga@test.it").click()
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").fill("7")
    edit_iframe.locator("#id_descr").click()
    edit_iframe.locator("#id_descr").fill("test")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/manage/credits")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("org")
    edit_iframe.get_by_role("option", name="Admin Test - orga@test.it").click()
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").fill("5")
    edit_iframe.locator("#id_descr").click()
    edit_iframe.locator("#id_descr").fill("test")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/manage/tokens")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("org")
    edit_iframe.get_by_role("option", name="Admin Test - orga@test.it").click()
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").fill("17")
    edit_iframe.locator("#id_descr").click()
    edit_iframe.locator("#id_descr").fill("teeest")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/manage/credits")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_text("---------").click()
    edit_iframe.get_by_role("searchbox").fill("org")
    edit_iframe.get_by_role("option", name="Admin Test - orga@test.it").click()
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").fill("19")
    edit_iframe.locator("#id_descr").click()
    edit_iframe.locator("#id_descr").fill("testet")
    save_modal(page, edit_iframe)


def signup_pay(live_server: Any, page: Any) -> None:
    # Signup
    go_to(page, live_server, "/test/register")
    submit_register(page)
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Provisional registration")
    page.locator("#one").get_by_role("link", name="Accounting").click()
    _wait_lm_ready(page)
    expect_normalized(page, page.locator("#one"), "100")

    # Check accounting
    go_to(page, live_server, "/accounting")
    expect_normalized(page, page.locator("#one"), "100")

    # check pay
    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name=re.compile(r"Proceed with payment")).click()
    page.get_by_role("cell", name="Wire", exact=True).click()
    expect_normalized(page, page.locator("b"), "100")
    submit(page)
    expect_normalized(page, page.locator("#one"), "100")
    expect_normalized(page, page.locator("#one"), "test beneficiary")
    expect_normalized(page, page.locator("#one"), "test iban")


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

    page.get_by_role("link", name=re.compile(r"^Payments ")).click()
    page.locator("#id_payment_require_receipt").check()

    submit_confirm(page)
    go_to(page, live_server, "/manage/methods")
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("test wire")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_descr").press("Tab")
    page.locator("#id_wire_payee").fill("test beneficiary")
    page.locator("#id_wire_payee").press("Tab")
    page.locator("#id_wire_iban").fill("test iban")
    page.locator("#id_wire_bic").fill("test iban")
    page.get_by_role("checkbox", name="Freeform").check()
    page.locator("#id_any_descr").click()
    page.locator("#id_any_descr").fill("freeeeee")
    page.locator("#id_any_fee").click()
    page.locator("#id_any_fee").fill("1")
    submit_confirm(page)

    # set ticket price
    go_to(page, live_server, "/test/manage/tickets")
    page.wait_for_selector("table.go_datatable")
    page.wait_for_selector(".fa-edit", timeout=SHORT_TIMEOUT)
    page.locator(".fa-edit").click(force=True)
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_price").click()
    edit_iframe.locator("#id_price").fill("100.00")
    save_modal(page, edit_iframe)
