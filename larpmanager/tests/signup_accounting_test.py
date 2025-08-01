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
import asyncio
import re
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start, submit


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_signup_accounting(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await signup_accounting(live_server, page)

        except Exception as e:
            await handle_error(page, e, "reg_signup_accounting")

        finally:
            await context.close()
            await browser.close()


async def signup_accounting(live_server, page):
    await login_orga(page, live_server)

    await setup_payment(live_server, page)

    await signup_pay(live_server, page)

    await token_credits(live_server, page)

    await pay(live_server, page)

    await discount(live_server, page)

    await check_delete(live_server, page)


async def check_delete(live_server, page):
    # update signup - orga
    await go_to(page, live_server, "/test/1/manage/registrations")
    await page.locator("a:has(i.fas.fa-edit)").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # cancel signup
    await page.locator("a:has(i.fas.fa-edit)").click()
    await page.get_by_role("link", name="Delete").click()
    await asyncio.sleep(1)
    await page.get_by_role("button", name="Confirmation delete").click()
    await go_to(page, live_server, "/test/1/manage/cancellations")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("orga@test.it")

    # delete payments
    await go_to(page, live_server, "/test/1/manage/tokens")
    await page.locator("a:has(i.fas.fa-edit)").click()
    await page.get_by_role("link", name="Delete").click()
    await asyncio.sleep(2)
    await page.get_by_role("button", name="Confirmation delete").click()
    await go_to(page, live_server, "/test/1/manage/credits")
    await page.locator("a:has(i.fas.fa-edit)").click()
    await page.get_by_role("link", name="Delete").click()
    await asyncio.sleep(2)
    await page.get_by_role("button", name="Confirmation delete").click()
    await go_to(page, live_server, "/test/1/manage/payments")
    await page.locator('[id="\\35 "]').get_by_role("link", name="").click()
    await page.get_by_role("link", name="Delete").click()
    await asyncio.sleep(2)
    await page.get_by_role("button", name="Confirmation delete").click()


async def discount(live_server, page):
    # check signup
    await go_to(page, live_server, "/test/1/manage/registrations")
    await page.get_by_role("link", name="accounting", exact=True).click()
    await expect(page.locator('[id="\\31 "]')).to_contain_text("100")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("52")
    await go_to(page, live_server, "/test/1/register")
    await page.locator("#one").get_by_role("link", name="Accounting").click()
    await expect(page.locator("#one")).to_contain_text("Total payments: 100")

    # update signup
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # use discount
    await go_to(page, live_server, "/test/1/manage/features/12/on")
    await go_to(page, live_server, "/test/1/manage/discounts/")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("discount")
    await page.get_by_role("checkbox", name="Test Larp").check()
    await page.locator("#id_value").click()
    await page.locator("#id_value").press("Home")
    await page.locator("#id_value").fill("20")
    await page.locator("#id_value").press("Tab")
    await page.locator("#id_max_redeem").fill("0")
    await page.locator("#id_cod").click()
    await page.locator("#id_cod").fill("code")
    await page.locator("#id_typ").select_option("a")
    await page.locator("#id_visible").check()
    await page.locator("#id_only_reg").uncheck()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/register/")
    await page.get_by_role("link", name="Discounts ").click()
    await page.locator("#id_discount").click()
    await page.locator("#id_discount").fill("code")
    await page.locator("#discount_go").click()
    await expect(page.locator("#discount_res")).to_contain_text(
        "The discount has been added! It has been reserved for you for 15 minutes, after which it will be removed"
    )
    await expect(page.locator("#discount_tbl")).to_contain_text("20.00€")
    await page.get_by_role("button", name="Continue").click()
    await expect(page.locator("#riepilogo")).to_contain_text("Your updated registration total is: 80€.")
    await page.locator("#register_go").click()


async def pay(live_server, page):
    # check accounting
    await go_to(page, live_server, "/test/1/register")
    await page.locator("#one").get_by_role("link", name="Accounting").click()
    await expect(page.locator("#one")).to_contain_text("Total registration fee: 100")
    await expect(page.locator("#one")).to_contain_text("Total payments: 48")
    await expect(page.locator("#one")).to_contain_text("Next payment: 52")
    await go_to(page, live_server, "/test/1/manage/registrations")
    await page.get_by_role("link", name="accounting", exact=True).click()
    await expect(page.locator('[id="\\31 "]')).to_contain_text("52")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("48")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("100")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("100")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("24")

    # pay
    await go_to(page, live_server, "/accounting/registration/1/")
    await expect(page.locator("#one")).to_contain_text("100")
    await expect(page.locator("#one")).to_contain_text("48")
    await expect(page.locator("#one")).to_contain_text("52")
    await submit(page)
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await expect(page.locator("#one")).to_contain_text("52")
    await submit(page)

    # confirm payment
    await go_to(page, live_server, "/test/1/manage/invoices")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("52")
    await page.get_by_role("link", name="Confirm", exact=True).click()


async def token_credits(live_server, page):
    # activate tokens credits
    await go_to(page, live_server, "/manage/features/107/on")
    await go_to(page, live_server, "/manage/tokens")
    await page.get_by_role("link", name="New").click()
    await page.locator("#select2-id_member-container").click()
    await page.get_by_role("searchbox").fill("ad")
    await page.get_by_role("option", name="Admin Test - orga@test.it").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").fill("7")
    await page.locator("#id_descr").click()
    await page.locator("#id_descr").fill("test")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/manage/credits")
    await page.get_by_role("link", name="New").click()
    await page.locator("#select2-id_member-container").click()
    await page.get_by_role("searchbox").fill("org")
    await page.get_by_role("option", name="Admin Test - orga@test.it").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").fill("5")
    await page.locator("#id_descr").click()
    await page.locator("#id_descr").fill("test")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/tokens")
    await page.get_by_role("link", name="New").click()
    await page.locator("#select2-id_member-container").click()
    await page.get_by_role("searchbox").fill("org")
    await page.get_by_role("option", name="Admin Test - orga@test.it").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").fill("17")
    await page.locator("#id_descr").click()
    await page.locator("#id_descr").fill("teeest")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/credits")
    await page.get_by_role("link", name="New").click()
    await page.get_by_text("---------").click()
    await page.get_by_role("searchbox").fill("org")
    await page.get_by_role("option", name="Admin Test - orga@test.it").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").fill("19")
    await page.locator("#id_descr").click()
    await page.locator("#id_descr").fill("testet")
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def signup_pay(live_server, page):
    # Signup
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await go_to(page, live_server, "/test/1/register")
    await expect(page.locator("#one")).to_contain_text("Provisional registration")
    await page.locator("#one").get_by_role("link", name="Accounting").click()
    await expect(page.locator("#one")).to_contain_text("100")

    # Check accounting
    await go_to(page, live_server, "/accounting")
    await expect(page.locator("#one")).to_contain_text("100")

    # check pay
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("link", name=re.compile(r"proceed with payment")).click()
    await page.get_by_role("cell", name="Wire", exact=True).click()
    await expect(page.locator("b")).to_contain_text("100")
    await submit(page)
    await expect(page.locator("#one")).to_contain_text("100")
    await expect(page.locator("#one")).to_contain_text("test beneficiary")
    await expect(page.locator("#one")).to_contain_text("test iban")


async def setup_payment(live_server, page):
    # Activate payments
    await go_to(page, live_server, "/manage/features/111/on")
    await go_to(page, live_server, "/manage/config")
    await page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    await page.locator("#id_mail_cc").check()
    await page.locator("#id_mail_signup_new").check()
    await page.locator("#id_mail_signup_update").check()
    await page.locator("#id_mail_signup_del").check()
    await page.locator("#id_mail_payment").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await go_to(page, live_server, "/manage/payments/details")
    await page.locator('#id_payment_methods input[type="checkbox"][value="1"]').check()
    await page.locator("#id_wire_descr").click()
    await page.locator("#id_wire_descr").fill("test wire")
    await page.locator("#id_wire_fee").fill("0")
    await page.locator("#id_wire_descr").press("Tab")
    await page.locator("#id_wire_payee").fill("test beneficiary")
    await page.locator("#id_wire_payee").press("Tab")
    await page.locator("#id_wire_iban").fill("test iban")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # set ticket price
    await go_to(page, live_server, "/test/1/manage/registrations/tickets")
    await page.locator("a:has(i.fas.fa-edit)").click()
    await page.locator("#id_price").click()
    await page.locator("#id_price").fill("100.00")
    await page.get_by_role("button", name="Confirm", exact=True).click()
