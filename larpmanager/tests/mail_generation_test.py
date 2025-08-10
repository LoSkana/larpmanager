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
from playwright.async_api import async_playwright

from larpmanager.tests.utils import check_download, fill_tinymce, go_to, handle_error, login_orga, page_start, submit


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mail_generation(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await mail_generation(live_server, page)

        except Exception as e:
            await handle_error(page, e, "mail_generation")

        finally:
            await context.close()
            await browser.close()


async def mail_generation(live_server, page):
    await login_orga(page, live_server)

    await chat(live_server, page)

    image_path = Path(__file__).parent / "image.jpg"

    await badge(live_server, page, image_path)

    await submit_membership(live_server, page, image_path)

    await resubmit_membership(live_server, page)

    await expense(image_path, live_server, page)


async def expense(image_path, live_server, page):
    # approve it
    await go_to(page, live_server, "/manage/membership/")
    await page.get_by_role("link", name="Request").click()
    await page.get_by_role("textbox", name="Response").fill("yeaaaa")
    await page.get_by_role("button", name="Confirm").click()

    # expenses
    await go_to(page, live_server, "/manage/features/106/on")
    await go_to(page, live_server, "/test/1/manage/expenses/my")
    await page.get_by_role("link", name="New").click()
    await page.get_by_role("spinbutton", name="Value").click()
    await page.get_by_role("spinbutton", name="Value").fill("10")
    await page.locator("#id_invoice").set_input_files(str(image_path))
    await page.get_by_label("Type").select_option("g")
    await page.get_by_role("textbox", name="Descr").click()
    await page.get_by_role("textbox", name="Descr").fill("dsadas")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await go_to(page, live_server, "/test/1/manage/expenses")
    await page.get_by_role("link", name="Approve").click()


async def resubmit_membership(live_server, page):
    # refute it
    await go_to(page, live_server, "/manage/membership/")
    await page.get_by_role("link", name="Request").click()
    await page.locator("form").locator("#id_is_approved").click()
    await page.locator("form").locator("#id_response").fill("nope")
    await page.get_by_role("button", name="Confirm").click()
    # signup
    await go_to(page, live_server, "/test/1/manage/registrations/tickets/")
    await page.locator("a:has(i.fas.fa-edit)").click()
    await page.locator("#id_price").click()
    await page.locator("#id_price").fill("100")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/test/1/register/")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    # Set membership fee
    await go_to(page, live_server, "/manage/config/")
    await page.get_by_role("link", name=re.compile(r"^Members\s.+")).click()
    await page.locator("#id_membership_fee").click()
    await page.locator("#id_membership_fee").fill("10")
    await page.locator("#id_membership_day").click()
    await page.locator("#id_membership_day").fill("01-01")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    # update signup, go to membership
    await go_to(page, live_server, "/test/1/register/")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await submit(page)
    await page.locator("#id_confirm_1").check()
    await page.locator("#id_confirm_2").check()
    await page.locator("#id_confirm_3").check()
    await page.locator("#id_confirm_4").check()
    await submit(page)


async def submit_membership(live_server, page, image_path):
    # Test membership
    await go_to(page, live_server, "/manage/features/45/on")
    await go_to(page, live_server, "/manage/texts")
    await page.wait_for_timeout(2000)
    await page.get_by_role("link", name="New").click()

    await fill_tinymce(page, "id_text_ifr", "Ciao {{ member.name }}!")

    await page.locator("#main_form").click()
    await page.locator("#id_typ").select_option("m")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await go_to(page, live_server, "/membership")
    await page.get_by_role("checkbox", name="Authorisation").check()
    await submit(page)

    await check_download(page, "download it here")

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


async def badge(live_server, page, image_path):
    # Test badge
    await go_to(page, live_server, "/manage/features/65/on")
    await go_to(page, live_server, "/manage/badges")
    await page.get_by_role("link", name="New").click()
    await page.locator("#id_name").click()
    await page.locator("#id_name").fill("prova")
    await page.locator("#id_name").press("Tab")
    await page.locator("#id_name_eng").fill("prova")
    await page.locator("#id_name_eng").press("Tab")
    await page.locator("#id_descr").fill("asdsa")
    await page.locator("#id_descr").press("Tab")
    await page.locator("#id_descr_eng").fill("asdsadaasd")
    await page.locator("#id_cod").click()
    await page.locator("#id_cod").fill("asd")
    await page.locator("#id_cod").click()
    await page.locator("#id_cod").fill("asasdsadd")
    await page.locator("#id_img").click()

    await page.locator("#id_img").set_input_files(str(image_path))
    await page.get_by_role("searchbox").fill("user")
    await page.get_by_role("option", name="User Test - user@test.it").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def chat(live_server, page):
    # Test chat
    await go_to(page, live_server, "/manage/features/52/on")
    await go_to(page, live_server, "/public/3/")
    await page.get_by_role("link", name="Chat").click()
    await page.get_by_role("textbox").fill("ciao!")
    await submit(page)
