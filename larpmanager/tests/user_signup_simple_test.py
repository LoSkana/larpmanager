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
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_orga

pytestmark = pytest.mark.e2e


def test_user_signup_simple(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    pre_register(live_server, page)

    signup(live_server, page)

    help_questions(live_server, page)


def signup(live_server, page):
    # sign up
    go_to(page, live_server, "/")
    expect(page.locator("#one")).to_contain_text("Registration is open!")
    page.get_by_role("link", name="Registration is open!").click()
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # test mails
    go_to(page, live_server, "/debug/mail")

    # delete sign up
    go_to(page, live_server, "/test/1/manage/registrations")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.get_by_role("link", name="Delete").click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Confirmation delete").click()

    # sign up, confirm profile
    go_to(page, live_server, "/test/1/register")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    expect(page.locator("#one")).to_contain_text("Registration confirmed")
    expect(page.locator("#one")).to_contain_text("please fill in your profile.")

    page.get_by_role("link", name="please fill in your profile.").click()
    page.get_by_role("checkbox", name="Authorisation").check()
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("Registration confirmed (Standard)")

    # test update of signup with no payments
    go_to(page, live_server, "/test/1/register")
    page.get_by_role("button", name="Continue").click()
    expect(page.locator("#banner")).not_to_contain_text("Register")


def help_questions(live_server, page):
    # test help
    go_to(page, live_server, "/manage/features/28/on")
    page.get_by_role("link", name="Need help?").click()
    page.get_by_role("textbox", name="Text").click()
    page.get_by_role("textbox", name="Text").fill("please help me")
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_attachment").set_input_files(str(image_path))
    page.get_by_label("Event").select_option("1")
    page.get_by_role("button", name="Confirm", exact=True).click()

    # check questions
    expect(page.locator("#one")).to_contain_text("[Test Larp] - please help me (Attachment)")
    go_to(page, live_server, "/manage/questions")
    expect(page.locator("#one")).to_contain_text("please help me")

    page.get_by_role("link", name="Answer", exact=True).click()
    page.get_by_role("textbox", name="Text").click()
    page.get_by_role("textbox", name="Text").fill("aasadsada")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="Need help?").click()
    page.get_by_role("textbox", name="Text").click()
    page.get_by_role("textbox", name="Text").fill("e adessoooo")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/manage/questions")
    page.get_by_role("link", name="Close").click()
    page.get_by_role("link", name="Show questions already").click()
    page.get_by_role("button", name="Confirm", exact=True).click()


def pre_register(live_server, page):
    # Set email send
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_cc").check()
    page.locator("#id_mail_signup_new").check()
    page.locator("#id_mail_signup_update").check()
    page.locator("#id_mail_signup_del").check()
    page.locator("#id_mail_payment").check()

    # Activate pre-register
    go_to(page, live_server, "/manage/features/32/on")

    go_to(page, live_server, "/test/1/manage/config")
    page.get_by_role("link", name=re.compile(r"^Pre-registration\s.+")).click()
    page.locator("#id_pre_register_active").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/")
    expect(page.locator("#one")).to_contain_text("Registration not yet open!")
    expect(page.locator("#one")).to_contain_text("Pre-register to the event!")
    page.get_by_role("link", name="Pre-register to the event!").click()

    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="Delete").click()
    page.get_by_role("textbox", name="Informations").click()
    page.get_by_role("textbox", name="Informations").fill("bauuu")
    page.get_by_label("Event").select_option("1")
    page.get_by_role("button", name="Confirm", exact=True).click()
    expect(page.locator("#one")).to_contain_text("bauuu")

    # disable preregistration, sign up really
    go_to(page, live_server, "/test/1/manage/config")
    page.get_by_role("link", name=re.compile(r"^Pre-registration\s.+")).click()
    page.locator("#id_pre_register_active").uncheck()
    page.get_by_role("button", name="Confirm", exact=True).click()
