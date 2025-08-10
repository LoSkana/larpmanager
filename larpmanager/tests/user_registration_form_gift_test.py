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

from larpmanager.tests.utils import go_to, handle_error, login_orga, login_user, page_start, submit


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_user_registration_form_gift(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await user_registration_form_gift(live_server, page)

        except Exception as e:
            await handle_error(page, e, "user_registration_form_gift")

        finally:
            await context.close()
            await browser.close()


async def user_registration_form_gift(live_server, page):
    await login_orga(page, live_server)

    await prepare(page, live_server)

    await field_choice(page, live_server)

    await field_multiple(page, live_server)

    await field_text(page, live_server)

    await gift(page, live_server)


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

    # Activate gift
    await go_to(page, live_server, "/test/1/manage/features/175/on")

    await go_to(page, live_server, "/test/1/manage/registrations/form/")


async def field_choice(page, live_server):
    # create single choice
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("choice")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("asd")
    await page.locator("#id_description").press("Shift+Home")
    await page.locator("#id_description").fill("")
    await page.locator("#id_giftable").check()

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("prima")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("f")
    await page.locator("#id_price").click()
    await page.locator("#id_price").click()
    await page.locator("#id_price").fill("10")
    await page.locator("#id_price").press("Tab")
    await page.locator("#id_max_available").fill("2")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("secondas")
    await page.locator("#id_description").click()
    await page.locator("#id_description").fill("s")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def field_multiple(page, live_server):
    # create multiple choice
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("m")
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("wow")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("buuuug")
    await page.locator("#id_status").select_option("m")
    await page.locator("#id_max_length").click()
    await page.locator("#id_max_length").fill("1")
    await page.locator("#id_giftable").check()

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("one")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("asdas")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("twp")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("asdas")
    await page.locator("#id_price").click()
    await page.locator("#id_price").press("Home")
    await page.locator("#id_price").fill("10")
    await page.locator("#id_max_available").click()
    await page.locator("#id_max_available").fill("2")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("hhasd")
    await page.locator("#id_description").click()
    await page.locator("#id_description").fill("sarrrr")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.locator('[id="\\34 "]').get_by_role("link", name="").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="").click()
    await page.get_by_role("link", name="New").click()


async def field_text(page, live_server):
    # create text
    await page.locator("#id_typ").select_option("t")
    await page.locator("#id_description").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("who")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("gtqwe")
    await page.locator("#id_status").select_option("d")
    await page.locator("#id_status").select_option("o")
    await page.locator("#id_giftable").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # create paragraph
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_typ").select_option("p")
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("when")
    await page.locator("#id_description").click()
    await page.locator("#id_description").fill("sadsaddd")
    await page.locator("#id_giftable").check()
    await page.locator("#id_max_length").click()
    await page.locator("#id_max_length").fill("100")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # sign up
    await go_to(page, live_server, "/test/1/register/")
    await page.get_by_text("twp (10€) - (Available 2)").click()
    await expect(page.locator("#register_form")).to_contain_text("options: 1 / 1")
    await page.get_by_label("choice").select_option("2")
    await page.get_by_role("textbox", name="who").click()
    await page.get_by_role("textbox", name="who").fill("sadsadas")
    await page.get_by_role("textbox", name="when").click()
    await page.get_by_role("textbox", name="when").fill("sadsadsadsad")
    await expect(page.locator("#register_form")).to_contain_text("text length: 12 / 100")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="Register").click()
    await expect(page.get_by_label("when")).to_contain_text("sadsadsadsad")
    await expect(page.get_by_label("choice")).to_contain_text("secondas")


async def gift(page, live_server):
    # make ticket giftable
    await go_to(page, live_server, "/test/1/manage/registrations/tickets/")
    await page.get_by_role("link", name="").click()
    await page.get_by_text("Indicates whether the ticket").click()
    await page.locator("#id_giftable").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # gift
    await go_to(page, live_server, "/test/1/gift/")
    await page.get_by_role("link", name="Add new").click()
    await page.locator("#id_q2").get_by_text("one").click()
    await page.get_by_label("choice").select_option("1")
    await page.get_by_role("textbox", name="who").click()
    await page.get_by_role("textbox", name="who").fill("wwww")
    await page.get_by_role("textbox", name="when").click()
    await page.get_by_role("textbox", name="when").fill("fffdsfs")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await expect(page.locator("#one")).to_contain_text("( Standard ) choice - prima (10.00€) , wow - one")
    await expect(page.locator("#one")).to_contain_text("10€ within 8 days")

    # pay
    await page.get_by_role("link", name="10€ within 8 days").click()
    await page.get_by_role("button", name="Submit").click()
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await submit(page)

    await page.get_by_role("checkbox", name="Authorisation").check()
    await page.get_by_role("button", name="Submit").click()

    await go_to(page, live_server, "/test/1/gift/")
    await expect(page.locator("#one")).to_contain_text("Payment currently in review by the staff.")

    # approve payment
    await go_to(page, live_server, "/test/1/manage/invoices")
    await page.get_by_role("link", name="Confirm", exact=True).click()

    # redeem
    await go_to(page, live_server, "/test/1/gift/")
    await expect(page.locator("#one")).to_contain_text("Redeem code")
    href = await page.get_by_role("link", name="Redeem code").get_attribute("href")

    await login_user(page, live_server)
    await go_to(page, live_server, href)
    await expect(page.locator("#header")).to_contain_text("Redeem registration")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await expect(page.locator("#one")).to_contain_text("Registration confirmed")
