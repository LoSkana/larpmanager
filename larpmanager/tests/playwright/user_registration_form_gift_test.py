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
Test: Gift registration with giftable form fields and payment.
Verifies giftable ticket/field configuration, gift purchase workflow,
payment for gifts, approval process, and gift redemption by recipients.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (just_wait,
    go_to,
    load_image,
    login_orga,
    login_user,
    submit,
    submit_confirm,
    expect_normalized,
)

pytestmark = pytest.mark.e2e


def test_user_registration_form_gift(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    prepare(page, live_server)

    field_choice(page, live_server)

    field_multiple(page, live_server)

    field_text(page, live_server)

    gift(page, live_server)


def prepare(page: Any, live_server: Any) -> None:
    # Activate payments
    go_to(page, live_server, "/manage/features/payment/on")

    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_cc").check()
    page.locator("#id_mail_signup_new").check()
    page.locator("#id_mail_signup_update").check()
    page.locator("#id_mail_signup_del").check()
    page.locator("#id_mail_payment").check()

    page.get_by_role("link", name="Payments ").click()
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
    submit_confirm(page)

    # Activate gift
    go_to(page, live_server, "/test/manage/features/gift/on")

    go_to(page, live_server, "/test/manage/form/")


def field_choice(page: Any, live_server: Any) -> None:
    # create single choice
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("choice")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("asd")
    page.locator("#id_description").press("Shift+Home")
    page.locator("#id_description").fill("")
    page.locator("#id_giftable").check()

    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").fill("prima")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").press("Tab")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_description").fill("f")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_price").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_price").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_price").fill("10")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_price").press("Tab")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_max_available").fill("2")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").fill("secondas")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_description").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_description").fill("s")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    submit_confirm(page)


def field_multiple(page: Any, live_server: Any) -> None:
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

    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").fill("one")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").press("Tab")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_description").fill("asdas")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").fill("twp")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").press("Tab")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_description").fill("asdas")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_price").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_price").press("Home")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_price").fill("10")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_max_available").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_max_available").fill("2")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    page.locator("#options-iframe").content_frame.get_by_role("link", name="New").click()
    just_wait(page)
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_name").fill("hhasd")
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_description").click()
    page.locator("#uglipop_popbox iframe").content_frame.locator("#id_description").fill("sarrrr")
    page.locator("#uglipop_popbox iframe").content_frame.get_by_role("button", name="Confirm").click()
    just_wait(page)

    page.locator("#options-iframe").content_frame.locator('[id="u4"]').get_by_role("link", name="").click()
    just_wait(page)
    submit_confirm(page)
    page.locator('[id="u3"]').get_by_role("link", name="").click()
    page.get_by_role("link", name="New").click()


def field_text(page: Any, live_server: Any) -> None:
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
    submit_confirm(page)

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
    submit_confirm(page)

    # sign up
    go_to(page, live_server, "/test/register/")
    page.get_by_text("twp (10€) - (Available 2)").click()
    expect_normalized(page, page.locator("#register_form"), "options: 1 / 1")
    page.get_by_label("choice").select_option("u2")
    page.get_by_role("textbox", name="who").click()
    page.get_by_role("textbox", name="who").fill("sadsadas")
    page.get_by_role("textbox", name="when").click()
    page.get_by_role("textbox", name="when").fill("sadsadsadsad")
    expect_normalized(page, page.locator("#register_form"), "text length: 12 / 100")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    go_to(page, live_server, "/test/register/")
    page.get_by_role("link", name="Registration", exact=True).click()
    expect(page.get_by_label("when")).to_contain_text("sadsadsadsad")
    expect(page.get_by_label("choice")).to_contain_text("secondas")


def gift(page: Any, live_server: Any) -> None:
    # make ticket giftable
    go_to(page, live_server, "/test/manage/tickets/")
    page.get_by_role("link", name="").click()
    page.get_by_text("Indicates whether the ticket").click()
    page.locator("#id_giftable").check()
    submit_confirm(page)

    # gift
    go_to(page, live_server, "/test/gift/")
    page.get_by_role("link", name="Add new").click()
    page.locator("#id_que_u3").get_by_text("one").click()
    page.get_by_label("choice").select_option("u1")
    page.get_by_role("textbox", name="who").click()
    page.get_by_role("textbox", name="who").fill("wwww")
    page.get_by_role("textbox", name="when").click()
    page.get_by_role("textbox", name="when").fill("fffdsfs")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "( Standard ) wow - one | choice - prima (10.00€)")
    expect_normalized(page, page.locator("#one"), "10€ within 8 days")

    # pay
    page.get_by_role("link", name="10€ within 8 days").click()
    submit_confirm(page)
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()

    submit(page)

    page.get_by_role("checkbox", name="Authorisation").check()
    submit_confirm(page)

    go_to(page, live_server, "/test/gift/")
    expect_normalized(page, page.locator("#one"), "Payment currently in review by the staff.")

    # approve payment
    go_to(page, live_server, "/test/manage/invoices")
    page.get_by_role("link", name="Confirm", exact=True).click()

    # redeem
    go_to(page, live_server, "/test/gift/")
    expect_normalized(page, page.locator("#one"), "Access link")
    href = page.get_by_role("link", name="Access link").get_attribute("href")

    login_user(page, live_server)
    go_to(page, live_server, href)
    expect_normalized(page, page.locator("#banner"), "Redeem registration")
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Registration confirmed")
