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

from larpmanager.tests.utils import go_to, login_orga, login_user, submit

pytestmark = pytest.mark.e2e


def test_user_registration_form_gift(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    prepare(page, live_server)

    field_choice(page, live_server)

    field_multiple(page, live_server)

    field_text(page, live_server)

    gift(page, live_server)


def prepare(page, live_server):
    # Activate payments
    go_to(page, live_server, "/manage/features/111/on")

    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_cc").check()
    page.locator("#id_mail_signup_new").check()
    page.locator("#id_mail_signup_update").check()
    page.locator("#id_mail_signup_del").check()
    page.locator("#id_mail_payment").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/manage/payments/details")
    page.locator('#id_payment_methods input[type="checkbox"][value="1"]').check()
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("test wire")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_descr").press("Tab")
    page.locator("#id_wire_payee").fill("test beneficiary")
    page.locator("#id_wire_payee").press("Tab")
    page.locator("#id_wire_iban").fill("test iban")
    page.get_by_role("button", name="Confirm", exact=True).click()

    # Activate gift
    go_to(page, live_server, "/test/1/manage/features/175/on")

    go_to(page, live_server, "/test/1/manage/registrations/form/")


def field_choice(page, live_server):
    # create single choice
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("choice")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("asd")
    page.locator("#id_description").press("Shift+Home")
    page.locator("#id_description").fill("")
    page.locator("#id_giftable").check()

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("prima")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("f")
    page.locator("#id_price").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("10")
    page.locator("#id_price").press("Tab")
    page.locator("#id_max_available").fill("2")
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("secondas")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("s")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("button", name="Confirm", exact=True).click()


def field_multiple(page, live_server):
    # create multiple choice
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("m")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("wow")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("buuuug")
    page.locator("#id_status").select_option("m")
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").fill("1")
    page.locator("#id_giftable").check()

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("one")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("asdas")
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("twp")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("asdas")
    page.locator("#id_price").click()
    page.locator("#id_price").press("Home")
    page.locator("#id_price").fill("10")
    page.locator("#id_max_available").click()
    page.locator("#id_max_available").fill("2")
    page.get_by_role("button", name="Confirm", exact=True).click()

    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("hhasd")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("sarrrr")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.locator('[id="\\34 "]').get_by_role("link", name="").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="").click()
    page.get_by_role("link", name="New").click()


def field_text(page, live_server):
    # create text
    page.locator("#id_typ").select_option("t")
    page.locator("#id_description").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("who")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("gtqwe")
    page.locator("#id_status").select_option("d")
    page.locator("#id_status").select_option("o")
    page.locator("#id_giftable").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # create paragraph
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("p")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("when")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("sadsaddd")
    page.locator("#id_giftable").check()
    page.locator("#id_max_length").click()
    page.locator("#id_max_length").fill("100")
    page.get_by_role("button", name="Confirm", exact=True).click()

    # sign up
    go_to(page, live_server, "/test/1/register/")
    page.get_by_text("twp (10€) - (Available 2)").click()
    expect(page.locator("#register_form")).to_contain_text("options: 1 / 1")
    page.get_by_label("choice").select_option("2")
    page.get_by_role("textbox", name="who").click()
    page.get_by_role("textbox", name="who").fill("sadsadas")
    page.get_by_role("textbox", name="when").click()
    page.get_by_role("textbox", name="when").fill("sadsadsadsad")
    expect(page.locator("#register_form")).to_contain_text("text length: 12 / 100")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="Register").click()
    expect(page.get_by_label("when")).to_contain_text("sadsadsadsad")
    expect(page.get_by_label("choice")).to_contain_text("secondas")


def gift(page, live_server):
    # make ticket giftable
    go_to(page, live_server, "/test/1/manage/registrations/tickets/")
    page.get_by_role("link", name="").click()
    page.get_by_text("Indicates whether the ticket").click()
    page.locator("#id_giftable").check()
    page.get_by_role("button", name="Confirm", exact=True).click()

    # gift
    go_to(page, live_server, "/test/1/gift/")
    page.get_by_role("link", name="Add new").click()
    page.locator("#id_q2").get_by_text("one").click()
    page.get_by_label("choice").select_option("1")
    page.get_by_role("textbox", name="who").click()
    page.get_by_role("textbox", name="who").fill("wwww")
    page.get_by_role("textbox", name="when").click()
    page.get_by_role("textbox", name="when").fill("fffdsfs")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    expect(page.locator("#one")).to_contain_text("( Standard ) choice - prima (10.00€) , wow - one")
    expect(page.locator("#one")).to_contain_text("10€ within 8 days")

    # pay
    page.get_by_role("link", name="10€ within 8 days").click()
    page.get_by_role("button", name="Submit").click()
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_invoice").set_input_files(str(image_path))
    submit(page)

    page.get_by_role("checkbox", name="Authorisation").check()
    page.get_by_role("button", name="Submit").click()

    go_to(page, live_server, "/test/1/gift/")
    expect(page.locator("#one")).to_contain_text("Payment currently in review by the staff.")

    # approve payment
    go_to(page, live_server, "/test/1/manage/invoices")
    page.get_by_role("link", name="Confirm", exact=True).click()

    # redeem
    go_to(page, live_server, "/test/1/gift/")
    expect(page.locator("#one")).to_contain_text("Redeem code")
    href = page.get_by_role("link", name="Redeem code").get_attribute("href")

    login_user(page, live_server)
    go_to(page, live_server, href)
    expect(page.locator("#header")).to_contain_text("Redeem registration")
    page.get_by_role("button", name="Confirm", exact=True).click()
    expect(page.locator("#one")).to_contain_text("Registration confirmed")
