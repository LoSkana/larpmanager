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

from larpmanager.tests.utils import go_to, handle_error, login_orga, page_start


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_user_signup_simple(live_server):
    async with async_playwright() as p:
        browser, context, page = await page_start(p)
        try:
            await user_signup_simple(live_server, page)

        except Exception as e:
            await handle_error(page, e, "user_signup_simple")

        finally:
            await context.close()
            await browser.close()


async def user_signup_simple(live_server, page):
    await login_orga(page, live_server)

    await pre_register(live_server, page)

    await signup(live_server, page)

    await help_questions(live_server, page)


async def signup(live_server, page):
    # sign up
    await go_to(page, live_server, "/")
    await expect(page.locator("#one")).to_contain_text("Registration is open!")
    await page.get_by_role("link", name="Registration is open!").click()
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # test mails
    await go_to(page, live_server, "/debug/mail")

    # delete sign up
    await go_to(page, live_server, "/test/1/manage/registrations")
    await page.locator("a:has(i.fas.fa-edit)").click()
    await page.get_by_role("link", name="Delete").click()
    await asyncio.sleep(2)
    await page.get_by_role("button", name="Confirmation delete").click()

    # sign up, confirm profile
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("button", name="Continue").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await expect(page.locator("#one")).to_contain_text("Registration confirmed")
    await expect(page.locator("#one")).to_contain_text("please fill in your profile.")

    await page.get_by_role("link", name="please fill in your profile.").click()
    await page.get_by_role("checkbox", name="Authorisation").check()
    await page.get_by_role("button", name="Submit").click()
    await expect(page.locator("#one")).to_contain_text("You are regularly signed up!")

    # test update of signup with no payments
    await go_to(page, live_server, "/test/1/register")
    await page.get_by_role("button", name="Continue").click()
    await expect(page.locator("#banner")).not_to_contain_text("Register")


async def help_questions(live_server, page):
    # test help
    await go_to(page, live_server, "/manage/features/28/on")
    await page.get_by_role("link", name="Need help?").click()
    await page.get_by_role("textbox", name="Text").click()
    await page.get_by_role("textbox", name="Text").fill("please help me")
    image_path = Path(__file__).parent / "image.jpg"
    await page.locator("#id_attachment").set_input_files(str(image_path))
    await page.get_by_label("Event").select_option("1")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    # check questions
    await expect(page.locator("#one")).to_contain_text("[Test Larp] - please help me (Attachment)")
    await go_to(page, live_server, "/manage/questions")
    await expect(page.get_by_role("grid")).to_contain_text("please help me")

    await page.get_by_role("link", name="Answer", exact=True).click()
    await page.get_by_role("textbox", name="Text").click()
    await page.get_by_role("textbox", name="Text").fill("aasadsada")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="Need help?").click()
    await page.get_by_role("textbox", name="Text").click()
    await page.get_by_role("textbox", name="Text").fill("e adessoooo")
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/manage/questions")
    await page.get_by_role("link", name="Close").click()
    await page.get_by_role("link", name="Show questions already").click()
    await page.get_by_role("button", name="Confirm", exact=True).click()


async def pre_register(live_server, page):
    # Set email send
    await go_to(page, live_server, "/manage/config")
    await page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    await page.locator("#id_mail_cc").check()
    await page.locator("#id_mail_signup_new").check()
    await page.locator("#id_mail_signup_update").check()
    await page.locator("#id_mail_signup_del").check()
    await page.locator("#id_mail_payment").check()

    # Activate pre-register
    await go_to(page, live_server, "/manage/features/32/on")

    await go_to(page, live_server, "/test/1/manage/config")
    await page.get_by_role("link", name=re.compile(r"^Pre-registration\s.+")).click()
    await page.locator("#id_pre_register_active").check()
    await page.get_by_role("button", name="Confirm", exact=True).click()

    await go_to(page, live_server, "/")
    await expect(page.locator("#one")).to_contain_text("Registration not yet open!")
    await expect(page.locator("#one")).to_contain_text("Pre-register to the event!")
    await page.get_by_role("link", name="Pre-register to the event!").click()

    await page.get_by_role("button", name="Confirm", exact=True).click()
    await page.get_by_role("link", name="Delete").click()
    await page.get_by_role("textbox", name="Informations").click()
    await page.get_by_role("textbox", name="Informations").fill("bauuu")
    await page.get_by_label("Event").select_option("1")
    await page.get_by_role("button", name="Confirm", exact=True).click()
    await expect(page.locator("#one")).to_contain_text("bauuu")

    # disable preregistration, sign up really
    await go_to(page, live_server, "/test/1/manage/config")
    await page.get_by_role("link", name=re.compile(r"^Pre-registration\s.+")).click()
    await page.locator("#id_pre_register_active").uncheck()
    await page.get_by_role("button", name="Confirm", exact=True).click()
