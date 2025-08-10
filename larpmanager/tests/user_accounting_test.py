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

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start, submit


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_user_accounting(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await user_accounting(live_server, page)

        except Exception as e:
            await handle_error(page, e, "user_accounting")

        finally:
            await context.close()
            await browser.close()


async def user_accounting(live_server, page):
    await login_orga(page, live_server)

    await prepare(page, live_server)

    await donation(page, live_server)

    await membership_fees(page, live_server)

    await collections(page, live_server)


async def prepare(page, live_server):
    # Activate payments
    await go_to(page, live_server, "/manage/features/111/on")

    await go_to(page, live_server, "/manage/config")
    await page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    await page.locator("#id_mail_cc").check()
    await page.locator("#id_mail_signup_new").check()
    await page.locator("#id_mail_signup_update").check()
    await page.locator("#id_mail_signup_del").check()
    await page.locator("#id_mail_payment").check()

    await page.get_by_role("link", name=re.compile(r"^Payments\s.+")).click()
    await page.locator("#id_payment_special_code").check()

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


async def donation(page, live_server):
    # test donation
    await go_to(page, live_server, "/manage/features/36/on")

    await go_to(page, live_server, "/accounting")
    await page.get_by_role("link", name="follow this link").click()
    await page.locator("#id_amount").click()
    await page.locator("#id_amount").fill("10")
    await page.locator("#id_amount").press("Tab")
    await page.locator("#id_descr").fill("test donation")
    await page.get_by_role("cell", name="test wire").click()
    await submit(page)

    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await expect(page.locator("#one")).to_contain_text("test beneficiary")
    await expect(page.locator("#one")).to_contain_text("test iban")
    await submit(page)

    await go_to(page, live_server, "/manage/invoices")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("Donation of Admin Test")
    await page.get_by_role("link", name="Confirm").click()

    await go_to(page, live_server, "/accounting")
    await expect(page.locator("#one")).to_contain_text("Donations done")
    await expect(page.locator("#one")).to_contain_text("(10.00€)")


async def membership_fees(page, live_server):
    # test membership fees
    await go_to(page, live_server, "/manage/features/45/on")

    await go_to(page, live_server, "/membership")
    await page.get_by_role("checkbox", name="Authorisation").check()
    await submit(page)

    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_request").set_input_files(str(image_path))
    await page.locator("#id_document").set_input_files(str(image_path))
    await submit(page)

    await page.locator("#id_confirm_1").check()
    await page.get_by_text("I confirm that I have").click()
    await page.locator("#id_confirm_2").check()
    await page.get_by_text("I confirm that I have").click()
    await page.locator("#id_confirm_3").check()
    await page.locator("#id_confirm_4").check()
    await submit(page)

    await go_to(page, live_server, "/manage/membership/")
    await page.get_by_role("link", name="Request").click()
    await page.get_by_role("button", name="Confirm").click()

    await go_to(page, live_server, "/manage/config")
    await page.get_by_role("link", name=re.compile(r"Members\s.+")).click()
    await page.locator("#id_membership_fee").click()
    await page.locator("#id_membership_fee").fill("15")
    await page.locator("#id_membership_grazing").click()
    await page.locator("#id_membership_grazing").fill("12")
    await page.locator("#id_membership_day").click()
    await page.locator("#id_membership_day").fill("01-01")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/accounting")
    await expect(page.locator("#one")).to_contain_text("Payment membership fee")
    await page.get_by_role("link", name="Pay the annual fee").click()
    await page.get_by_role("cell", name="test wire").click()
    await submit(page)

    await expect(page.locator("#one")).to_contain_text("15")
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await expect(page.locator("#one")).to_contain_text("test beneficiary")
    await expect(page.locator("#one")).to_contain_text("test iban")
    await submit(page)

    await go_to(page, live_server, "/manage/invoices")
    await expect(page.locator('[id="\\32 "]')).to_contain_text("Membership fee of Admin Test")
    await page.get_by_role("link", name="Confirm").click()

    await go_to(page, live_server, "/accounting")
    await expect(page.locator("#one")).not_to_contain_text("Payment membership fee")


async def collections(page, live_server):
    # test collections
    await go_to(page, live_server, "/manage/features/31/on")

    await go_to(page, live_server, "/accounting")
    await page.get_by_role("link", name="Create a new collection").click()
    await page.get_by_role("textbox", name="Name").click()
    await page.get_by_role("textbox", name="Name").fill("User")
    await submit(page)

    await page.get_by_role("link", name="Link to participate in").click()
    await page.locator("#id_amount").click()
    await page.locator("#id_amount").fill("20")
    await submit(page)

    await expect(page.locator("#one")).to_contain_text("20")
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await expect(page.locator("#one")).to_contain_text("test beneficiary")
    await expect(page.locator("#one")).to_contain_text("test iban")
    await submit(page)

    await go_to(page, live_server, "/manage/invoices")
    await expect(page.locator("#one")).to_contain_text("Collected contribution of Admin Test for User")
    await page.get_by_role("link", name="Confirm").click()

    await go_to(page, live_server, "/accounting")
    await page.get_by_role("link", name="Manage it here!").click()
    await page.get_by_role("link", name="Link to close the collection").click()
    await page.get_by_role("link", name="Collection links").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/accounting")
