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
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from larpmanager.tests.utils import check_download, go_to, handle_error, login_orga, page_start, submit


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_user_signup_membership(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await user_signup_membership(live_server, page)

        except Exception as e:
            await handle_error(page, e, "user_signup_membership")

        finally:
            await context.close()
            await browser.close()


async def user_signup_membership(live_server, page):
    await login_orga(page, live_server)

    await signup(live_server, page)

    await membership(live_server, page)

    await pay(live_server, page)


async def signup(live_server, page):
    # Activate payments
    await go_to(page, live_server, "/manage/features/111/on")
    # Activate membership
    await go_to(page, live_server, "/manage/features/45/on")
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
    # signup
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("button", name="Continue").click()
    await expect(page.locator("#riepilogo")).to_contain_text("you must request to register as a member")
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def membership(live_server, page):
    # send membership
    await go_to(page, live_server, "/test/1/register")
    await expect(page.locator("#one")).to_contain_text("Provisional registration")
    await expect(page.locator("#one")).to_contain_text("please upload your membership application to proceed")
    await page.get_by_role("link", name="please upload your membership").click()
    await page.get_by_role("checkbox", name="Authorisation").check()
    await page.get_by_role("button", name="Submit").click()
    # compile request
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_request").set_input_files(str(image_path))
    await page.locator("#id_document").set_input_files(str(image_path))
    await check_download(page, "download it here")
    await submit(page)
    # confirm request
    await page.locator("#id_confirm_1").check()
    await page.get_by_text("I confirm that I have").click()
    await page.locator("#id_confirm_2").check()
    await page.get_by_text("I confirm that I have").click()
    await page.locator("#id_confirm_3").check()
    await page.locator("#id_confirm_4").check()
    await submit(page)
    # approve request signup
    await go_to(page, live_server, "/manage/membership/")
    await page.get_by_role("link", name="Request").click()
    await page.get_by_role("button", name="Confirm").click()
    # check register
    await go_to(page, live_server, "/test/1/register")
    await expect(page.locator("#one")).to_contain_text("to confirm it proceed with payment")
    await page.get_by_role("link", name="to confirm it proceed with").click()


async def pay(live_server, page):
    # pay
    await page.get_by_role("cell", name="Wire", exact=True).click()
    await expect(page.locator("b")).to_contain_text("100")
    await submit(page)
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await submit(page)
    # approve payment
    await go_to(page, live_server, "/test/1/manage/invoices")
    await page.get_by_role("link", name="Confirm", exact=True).click()
    # check payment
    await go_to(page, live_server, "/test/1/register")
    await expect(page.locator("#one")).to_contain_text("Registration confirmed (Standard)")
    await page.locator("a#menu-open").click()
    await page.get_by_role("link", name="Logout").click()
    await expect(page.locator("#one")).to_contain_text("Registration is open!")
    await expect(page.locator("#one")).to_contain_text("Hurry: only 9 tickets available")
    # test mails
    await go_to(page, live_server, "/debug/mail")
