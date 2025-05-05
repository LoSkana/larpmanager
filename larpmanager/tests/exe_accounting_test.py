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


import pytest
from playwright.sync_api import expect, sync_playwright

from larpmanager.tests.utils import handle_error, login_orga, page_start


@pytest.mark.django_db
def test_exe_accounting(live_server):
    with sync_playwright() as p:
        browser, context, page = page_start(p)
        try:
            exe_accounting(live_server, page)

        except Exception as e:
            handle_error(page, e, "exe_accounting")

        finally:
            context.close()
            browser.close()


def exe_accounting(live_server, page):
    login_orga(page, live_server)

    config(page)

    add_outflows(page)

    add_inflows(page)

    sign_up_pay(page)

    verify(page)


def verify(page):
    page.get_by_role("link", name="Accounting").click()
    expect(page.locator("#one")).to_contain_text("Net revenue: 133.00")
    expect(page.locator("#one")).to_contain_text("Balance: 71.00")
    expect(page.locator("#one")).to_contain_text("Organization tax: 17.29")
    expect(page.locator("#one")).to_contain_text("Registrations: 70.00")
    expect(page.locator("#one")).to_contain_text("Outflows: 62.00")
    expect(page.locator("#one")).to_contain_text("Inflows: 63.00")
    expect(page.locator("#one")).to_contain_text("Income: 70.00")
    page.get_by_role("link", name="Payments", exact=True).click()
    page.goto("http://127.0.0.1:8000/test/1/manage/invoices/")
    page.get_by_role("link", name="Payments", exact=True).click()
    page.goto("http://127.0.0.1:8000/test/1/manage/payments/")
    page.get_by_role("link", name="").click()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="").click()
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator('[id="\\31 "]')).to_contain_text("5.70")
    page.get_by_role("link", name="Organization").click()
    page.get_by_role("link", name="Payments").click()
    expect(page.locator('[id="\\31 "]')).to_contain_text("70")
    expect(page.locator('[id="\\31 "]')).to_contain_text("Test Larp")
    expect(page.locator('[id="\\31 "]')).to_contain_text("5.70")
    page.get_by_role("link", name="Accounting").click()
    expect(page.locator("#one")).to_contain_text("20.00")
    expect(page.locator("#one")).to_contain_text("91.00")
    expect(page.locator("#one")).to_contain_text("70.00")
    expect(page.locator("#one")).to_contain_text("93.00")
    expect(page.locator("#one")).to_contain_text("72.00")
    expect(page.locator("#one")).to_contain_text("10.00")
    expect(page.locator("#one")).to_contain_text("30.00")
    page.get_by_role("link", name="Invoices").click()
    page.get_by_role("link", name="Audits").click()


def sign_up_pay(page):
    page.get_by_role("link", name="Tickets").click()
    page.get_by_role("link", name="").click()
    page.locator("#id_price").click()
    page.locator("#id_price").press("Home")
    page.locator("#id_price").fill("50.00")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Form").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_display").click()
    page.locator("#id_display").fill("pay")
    page.locator("#id_display").press("Tab")
    page.locator("#id_description").fill("pay")
    page.get_by_role("link", name="New").click()
    page.locator("#id_display").click()
    page.locator("#id_display").fill("ff")
    page.locator("#id_details").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("20")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Register").click()
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Payments", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").press("Home")
    page.locator("#id_value").fill("70")
    page.get_by_text("---------").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp - Admin Test", exact=True).click()
    page.get_by_role("row", name="Info").locator("td").click()
    page.locator("#id_info").fill("sss")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_text("Accounting Payments Inflows").click()


def add_outflows(page):
    page.get_by_role("link", name="Organization").click()
    page.get_by_role("link", name="Outflows").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").press("ArrowLeft")
    page.locator("#id_value").fill("10")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("babe")
    page.get_by_role("button", name="Choose File").click()
    page.get_by_role("button", name="Choose File").set_input_files("WhatsApp Image 2025-05-02 at 19.18.25.jpeg")
    page.get_by_role("cell", name="--------- Indicate the").click()
    page.locator("#id_exp").select_option("a")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("15")
    page.get_by_label("---------").get_by_text("---------").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="Test Larp").click()
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("bibi")
    page.get_by_role("button", name="Choose File").click()
    page.get_by_role("button", name="Choose File").set_input_files("WhatsApp Image 2025-05-02 at 19.18.25.jpeg")
    page.locator("#id_exp").select_option("c")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Organization").click()
    page.get_by_role("link", name="Inflows").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").press("ArrowLeft")
    page.locator("#id_value").fill("50")
    page.locator("#select2-id_run-container").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp").click()
    page.get_by_role("combobox", name="×Test Larp").press("Tab")
    page.locator("#id_descr").fill("ggg")
    page.get_by_role("button", name="Choose File").click()
    page.get_by_role("button", name="Choose File").set_input_files("WhatsApp Image 2025-05-02 at 19.18.25.jpeg")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("30")
    page.locator("#id_value").press("Tab")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("sdfs")
    page.get_by_role("button", name="Choose File").click()
    page.get_by_role("button", name="Choose File").set_input_files("WhatsApp Image 2025-05-02 at 19.18.25.jpeg")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Test Larp").click()


def add_inflows(page):
    page.get_by_role("link", name="Inflows").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").press("ArrowLeft")
    page.locator("#id_value").fill("13")
    page.locator("#id_value").press("Tab")
    page.locator("#id_descr").fill("ttt")
    page.get_by_role("button", name="Choose File").click()
    page.get_by_role("button", name="Choose File").set_input_files("WhatsApp Image 2025-05-02 at 19.18.25.jpeg")
    page.locator("#id_payment_date").click()
    page.locator("#id_payment_date").press("F5")
    page.get_by_text("Calendar Gallery View the").click()
    page.locator("body").press("F5")
    page.goto("http://127.0.0.1:8000/test/1/manage/inflows/edit/0/")
    page.locator("#id_value").click()
    page.locator("#id_value").fill("13")
    page.locator("#id_value").press("Tab")
    page.locator("#id_descr").fill("asdsada")
    page.get_by_role("button", name="Choose File").click()
    page.get_by_role("button", name="Choose File").set_input_files("WhatsApp Image 2025-05-02 at 19.18.25.jpeg")
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator('[id="\\33 "]')).to_contain_text("13.00")
    expect(page.locator('[id="\\31 "]')).to_contain_text("50.00")
    expect(page.locator('[id="\\33 "]')).to_contain_text("asdsada")
    expect(page.locator('[id="\\31 "]')).to_contain_text("ggg")
    page.get_by_role("link", name="menu Sidebar").click()
    page.get_by_role("link", name="Outflows").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("47")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("asdsad")
    page.get_by_role("button", name="Choose File").click()
    page.get_by_role("button", name="Choose File").set_input_files("WhatsApp Image 2025-05-02 at 19.18.25.jpeg")
    page.locator("#id_exp").select_option("e")
    page.get_by_role("button", name="Confirm").click()


def config(page):
    page.get_by_role("link", name="Organization").click()
    page.get_by_role("link", name="Features").click()
    page.get_by_role("link", name="Accounting ").click()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("row", name="Activate Payments Enables").get_by_role("link").click()
    page.goto("http://127.0.0.1:8000/manage/features/")
    page.get_by_role("link", name="Accounting ").click()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("row", name="Activate Taxes Shows the").get_by_role("link").click()
    page.get_by_role("textbox", name="Search").click()
    page.get_by_role("link", name="Accounting ").click()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("row", name="Activate Inflows Enables").get_by_role("link").click()
    page.get_by_role("link", name="Accounting ").click()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("row", name="Activate Organisation tax").get_by_role("link").click()
    page.get_by_role("link", name="Accounting ").click()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("row", name="Activate Outflows Enables").get_by_role("link").click()
    page.get_by_role("link", name="Accounting ").click()
    page.get_by_role("link", name="Accounting ").click()
    page.get_by_role("link", name="Organization").click()
    page.get_by_role("link", name="Configuration").click()
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
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Features").click()
    page.get_by_role("link", name="Accounting ").click()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("row", name="Activate Verification").get_by_role("link").click()
