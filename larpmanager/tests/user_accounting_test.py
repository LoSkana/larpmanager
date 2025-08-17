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

from larpmanager.tests.utils import go_to, login_orga, submit

pytestmark = pytest.mark.e2e


def test_user_accounting(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    prepare(page, live_server)

    donation(page, live_server)

    membership_fees(page, live_server)

    collections(page, live_server)


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

    page.get_by_role("link", name=re.compile(r"^Payments\s.+")).click()
    page.locator("#id_payment_special_code").check()

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


def donation(page, live_server):
    # test donation
    go_to(page, live_server, "/manage/features/36/on")

    go_to(page, live_server, "/accounting")
    page.get_by_role("link", name="follow this link").click()
    page.locator("#id_amount").click()
    page.locator("#id_amount").fill("10")
    page.locator("#id_amount").press("Tab")
    page.locator("#id_descr").fill("test donation")
    page.get_by_role("cell", name="test wire").click()
    submit(page)

    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_invoice").set_input_files(str(image_path))
    expect(page.locator("#one")).to_contain_text("test beneficiary")
    expect(page.locator("#one")).to_contain_text("test iban")
    submit(page)

    go_to(page, live_server, "/manage/invoices")
    expect(page.locator('[id="\\31 "]')).to_contain_text("Donation of Admin Test")
    page.get_by_role("link", name="Confirm").click()

    go_to(page, live_server, "/accounting")
    expect(page.locator("#one")).to_contain_text("Donations done")
    expect(page.locator("#one")).to_contain_text("(10.00€)")


def membership_fees(page, live_server):
    # test membership fees
    go_to(page, live_server, "/manage/features/45/on")

    go_to(page, live_server, "/membership")
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)

    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_request").set_input_files(str(image_path))
    page.locator("#id_document").set_input_files(str(image_path))
    submit(page)

    page.locator("#id_confirm_1").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_2").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_3").check()
    page.locator("#id_confirm_4").check()
    submit(page)

    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Request").click()
    page.get_by_role("button", name="Confirm").click()

    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"Members\s.+")).click()
    page.locator("#id_membership_fee").click()
    page.locator("#id_membership_fee").fill("15")
    page.locator("#id_membership_grazing").click()
    page.locator("#id_membership_grazing").fill("12")
    page.locator("#id_membership_day").click()
    page.locator("#id_membership_day").fill("01-01")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/accounting")
    expect(page.locator("#one")).to_contain_text("Payment membership fee")
    page.get_by_role("link", name="Pay the annual fee").click()
    page.get_by_role("cell", name="test wire").click()
    submit(page)

    expect(page.locator("#one")).to_contain_text("15")
    page.locator("#id_invoice").set_input_files(str(image_path))
    expect(page.locator("#one")).to_contain_text("test beneficiary")
    expect(page.locator("#one")).to_contain_text("test iban")
    submit(page)

    go_to(page, live_server, "/manage/invoices")
    expect(page.locator('[id="\\32 "]')).to_contain_text("Membership fee of Admin Test")
    page.get_by_role("link", name="Confirm").click()

    go_to(page, live_server, "/accounting")
    expect(page.locator("#one")).not_to_contain_text("Payment membership fee")


def collections(page, live_server):
    # test collections
    go_to(page, live_server, "/manage/features/31/on")

    go_to(page, live_server, "/accounting")
    page.get_by_role("link", name="Create a new collection").click()
    page.get_by_role("textbox", name="Name").click()
    page.get_by_role("textbox", name="Name").fill("User")
    submit(page)

    page.get_by_role("link", name="Link to participate in").click()
    page.locator("#id_amount").click()
    page.locator("#id_amount").fill("20")
    submit(page)

    expect(page.locator("#one")).to_contain_text("20")
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_invoice").set_input_files(str(image_path))
    expect(page.locator("#one")).to_contain_text("test beneficiary")
    expect(page.locator("#one")).to_contain_text("test iban")
    submit(page)

    go_to(page, live_server, "/manage/invoices")
    expect(page.locator("#one")).to_contain_text("Collected contribution of Admin Test for User")
    page.get_by_role("link", name="Confirm").click()

    go_to(page, live_server, "/accounting")
    page.get_by_role("link", name="Manage it here!").click()
    page.get_by_role("link", name="Link to close the collection").click()
    page.get_by_role("link", name="Collection links").click()
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/accounting")
