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

from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_exe_accounting(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await exe_accounting(live_server, page)

        except Exception as e:
            await handle_error(page, e, "exe_accounting")

        finally:
            await context.close()
            await browser.close()


async def exe_accounting(live_server, page):
    await login_orga(page, live_server)

    await config(page, live_server)

    await add_exe(page, live_server)

    await add_orga(page, live_server)

    await sign_up_pay(page, live_server)

    await verify(page, live_server)


async def verify(page, live_server):
    await go_to(page, live_server, "/test/1/manage/accounting/")
    await expect(page.locator("#one")).to_contain_text("Total revenue: 133.00")
    await expect(page.locator("#one")).to_contain_text("Net profit: 71.00")
    await expect(page.locator("#one")).to_contain_text("Organization tax: 17.29")
    await expect(page.locator("#one")).to_contain_text("Registrations: 70.00")
    await expect(page.locator("#one")).to_contain_text("Outflows: 62.00")
    await expect(page.locator("#one")).to_contain_text("Inflows: 63.00")
    await expect(page.locator("#one")).to_contain_text("Income: 70.00")

    await go_to(page, live_server, "/test/1/manage/payments/")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("70")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("5.70")

    await go_to(page, live_server, "/manage/accounting/")
    await expect(page.locator("#one")).to_contain_text("20.00")
    await expect(page.locator("#one")).to_contain_text("91.00")
    await expect(page.locator("#one")).to_contain_text("70.00")
    await expect(page.locator("#one")).to_contain_text("93.00")
    await expect(page.locator("#one")).to_contain_text("72.00")
    await expect(page.locator("#one")).to_contain_text("10.00")
    await expect(page.locator("#one")).to_contain_text("30.00")


async def sign_up_pay(page, live_server):
    await go_to(page, live_server, "/test/1/manage/registrations/tickets/")
    await page.get_by_role("link", name="").click()
    await page.locator("#id_price").click()
    await page.locator("#id_price").press("Home")
    await page.locator("#id_price").fill("50.00")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "test/1/manage/registrations/form/")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("pay")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_description").fill("pay")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("ff")
    await page.locator("#id_description").click()
    await page.locator("#id_price").click()
    await page.locator("#id_price").fill("20")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/register/")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/manage/payments/")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").press("Home")
    await page.locator("#id_value").fill("70")
    await page.get_by_text("---------").click()
    await page.get_by_role("searchbox").fill("tes")
    await page.get_by_role("option", name="Test Larp - Admin Test", exact=True).click()
    await page.get_by_role("row", name="Info").locator("td").click()
    await page.locator("#id_info").fill("sss")
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def add_exe(page, live_server):
    await go_to(page, live_server, "/manage/outflows")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").press("ArrowLeft")
    await page.locator("#id_value").fill("10")
    await page.locator("#id_descr").click()
    await page.locator("#id_descr").fill("babe")
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await page.get_by_role("cell", name="--------- Indicate the").click()
    await page.locator("#id_exp").select_option("a")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").fill("15")
    await page.get_by_label("---------").get_by_text("---------").click()
    await page.get_by_role("searchbox").fill("te")
    await page.get_by_role("option", name="Test Larp").click()
    await page.locator("#id_descr").click()
    await page.locator("#id_descr").fill("bibi")
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await page.locator("#id_exp").select_option("c")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/manage/inflows")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").press("ArrowLeft")
    await page.locator("#id_value").fill("50")
    await page.locator("#select2-id_run-container").click()
    await page.get_by_role("searchbox").fill("tes")
    await page.get_by_role("option", name="Test Larp").click()
    await page.get_by_role("combobox", name="×Test Larp").press("Tab")
    await page.locator("#id_descr").fill("ggg")
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").fill("30")
    await page.locator("#id_value").press("Tab")
    await page.locator("#id_descr").click()
    await page.locator("#id_descr").fill("sdfs")
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def add_orga(page, live_server):
    await go_to(page, live_server, "/test/1/manage/inflows")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").fill("13")
    await page.locator("#id_value").press("Tab")
    await page.locator("#id_descr").fill("asdsada")
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await expect(page.locator('[id="\\33 "]')).to_contain_text("13.00")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("50.00")
    await expect(page.locator('[id="\\33 "]')).to_contain_text("asdsada")
    await expect(page.locator('[id="\\31 "]')).to_contain_text("ggg")

    await go_to(page, live_server, "/test/1/manage/outflows")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_value").click()
    await page.locator("#id_value").fill("47")
    await page.locator("#id_descr").click()
    await page.locator("#id_descr").fill("asdsad")
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await page.locator("#id_exp").select_option("e")
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def config(page, live_server):
    # activate payments
    await go_to(page, live_server, "/manage/features/111/on")
    # activate taxes
    await go_to(page, live_server, "/manage/features/173/on")
    # activate inflows
    await go_to(page, live_server, "/manage/features/144/on")
    # activate organization tax
    await go_to(page, live_server, "/manage/features/121/on")
    # activate outflows
    await go_to(page, live_server, "/manage/features/108/on")

    await go_to(page, live_server, "/manage/config")
    await page.get_by_role("link", name="Payments ").click()
    await page.locator("#id_payment_special_code").check()
    await page.get_by_role("link", name="VAT ").click()
    await page.locator("#id_vat_ticket").click()
    await page.locator("#id_vat_ticket").fill("7")
    await page.locator("#id_vat_options").click()
    await page.locator("#id_vat_options").fill("11")
    await page.get_by_role("link", name="Organisation fee ").click()
    await page.get_by_role("cell", name="Percentage of takings").click()
    await page.locator("#id_organization_tax_perc").fill("13")
    await page.get_by_role("button", name="Confirm", exact=True).click()
