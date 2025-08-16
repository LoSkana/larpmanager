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
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_orga

pytestmark = pytest.mark.e2e


def test_exe_accounting(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    config(page, live_server)

    add_exe(page, live_server)

    add_orga(page, live_server)

    sign_up_pay(page, live_server)

    verify(page, live_server)


def verify(page, live_server):
    go_to(page, live_server, "/test/1/manage/accounting/")
    expect(page.locator("#one")).to_contain_text("Total revenue: 133.00")
    expect(page.locator("#one")).to_contain_text("Net profit: 71.00")
    expect(page.locator("#one")).to_contain_text("Organization tax: 17.29")
    expect(page.locator("#one")).to_contain_text("Registrations: 70.00")
    expect(page.locator("#one")).to_contain_text("Outflows: 62.00")
    expect(page.locator("#one")).to_contain_text("Inflows: 63.00")
    expect(page.locator("#one")).to_contain_text("Income: 70.00")

    go_to(page, live_server, "/test/1/manage/payments/")
    expect(page.locator('[id="\\31 "]')).to_contain_text("70")
    expect(page.locator('[id="\\31 "]')).to_contain_text("5.70")

    go_to(page, live_server, "/manage/accounting/")
    expect(page.locator("#one")).to_contain_text("20.00")
    expect(page.locator("#one")).to_contain_text("91.00")
    expect(page.locator("#one")).to_contain_text("70.00")
    expect(page.locator("#one")).to_contain_text("93.00")
    expect(page.locator("#one")).to_contain_text("72.00")
    expect(page.locator("#one")).to_contain_text("10.00")
    expect(page.locator("#one")).to_contain_text("30.00")


def sign_up_pay(page, live_server):
    go_to(page, live_server, "/test/1/manage/registrations/tickets/")
    page.get_by_role("link", name="").click()
    page.locator("#id_price").click()
    page.locator("#id_price").press("Home")
    page.locator("#id_price").fill("50.00")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "test/1/manage/registrations/form/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("pay")
    page.locator("#id_name").press("Tab")
    page.locator("#id_description").fill("pay")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("ff")
    page.locator("#id_description").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("20")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/register/")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/manage/payments/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").press("Home")
    page.locator("#id_value").fill("70")
    page.get_by_text("---------").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp - Admin Test", exact=True).click()
    page.get_by_role("row", name="Info").locator("td").click()
    page.locator("#id_info").fill("sss")
    page.get_by_role("button", name="Confirm", exact=True).click()


def add_exe(page, live_server):
    go_to(page, live_server, "/manage/outflows")
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").press("ArrowLeft")
    page.locator("#id_value").fill("10")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("babe")
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_invoice").set_input_files(str(image_path))
    page.get_by_role("cell", name="--------- Indicate the").click()
    page.locator("#id_exp").select_option("a")
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("15")
    page.get_by_label("---------").get_by_text("---------").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="Test Larp").click()
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("bibi")
    page.locator("#id_invoice").set_input_files(str(image_path))
    page.locator("#id_exp").select_option("c")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/manage/inflows")
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").press("ArrowLeft")
    page.locator("#id_value").fill("50")
    page.locator("#select2-id_run-container").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp").click()
    page.get_by_role("combobox", name="×Test Larp").press("Tab")
    page.locator("#id_descr").fill("ggg")
    page.locator("#id_invoice").set_input_files(str(image_path))
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("30")
    page.locator("#id_value").press("Tab")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("sdfs")
    page.locator("#id_invoice").set_input_files(str(image_path))
    page.get_by_role("button", name="Confirm", exact=True).click()


def add_orga(page, live_server):
    go_to(page, live_server, "/test/1/manage/inflows")
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("13")
    page.locator("#id_value").press("Tab")
    page.locator("#id_descr").fill("asdsada")
    image_path = Path(__file__).parent / "image.jpg"
    page.locator("#id_invoice").set_input_files(str(image_path))
    page.get_by_role("button", name="Confirm", exact=True).click()
    expect(page.locator('[id="\\33 "]')).to_contain_text("13.00")
    expect(page.locator('[id="\\31 "]')).to_contain_text("50.00")
    expect(page.locator('[id="\\33 "]')).to_contain_text("asdsada")
    expect(page.locator('[id="\\31 "]')).to_contain_text("ggg")

    go_to(page, live_server, "/test/1/manage/outflows")
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("47")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("asdsad")
    page.locator("#id_invoice").set_input_files(str(image_path))
    page.locator("#id_exp").select_option("e")
    page.get_by_role("button", name="Confirm", exact=True).click()


def config(page, live_server):
    # activate payments
    go_to(page, live_server, "/manage/features/111/on")
    # activate taxes
    go_to(page, live_server, "/manage/features/173/on")
    # activate inflows
    go_to(page, live_server, "/manage/features/144/on")
    # activate organization tax
    go_to(page, live_server, "/manage/features/121/on")
    # activate outflows
    go_to(page, live_server, "/manage/features/108/on")

    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name="Payments ").click()
    page.locator("#id_payment_special_code").check()
    page.get_by_role("link", name="VAT ").click()
    page.locator("#id_vat_ticket").click()
    page.locator("#id_vat_ticket").fill("7")
    page.locator("#id_vat_options").click()
    page.locator("#id_vat_options").fill("11")
    page.get_by_role("link", name="Organisation fee ").click()
    page.get_by_role("cell", name="Percentage of takings").click()
    page.locator("#id_organization_tax_perc").fill("13")
    page.get_by_role("button", name="Confirm", exact=True).click()
