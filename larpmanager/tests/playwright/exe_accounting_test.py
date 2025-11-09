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
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, load_image, login_orga, submit_confirm

pytestmark = pytest.mark.e2e


def test_exe_accounting(pw_page) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    config(page, live_server)

    add_exe(page, live_server)

    add_orga(page, live_server)

    sign_up_pay(page, live_server)

    verify(page, live_server)


def verify(page, live_server) -> None:
    go_to(page, live_server, "/test/manage/accounting/")
    expect(page.locator("#one")).to_contain_text("Total revenue: 133.00")
    expect(page.locator("#one")).to_contain_text("Net profit: 71.00")
    expect(page.locator("#one")).to_contain_text("Organization tax: 17.29")
    expect(page.locator("#one")).to_contain_text("Registrations: 70.00")
    expect(page.locator("#one")).to_contain_text("Outflows: 62.00")
    expect(page.locator("#one")).to_contain_text("Inflows: 63.00")
    expect(page.locator("#one")).to_contain_text("Income: 70.00")

    go_to(page, live_server, "/test/manage/payments/")
    # Check for payment row with value 70
    expect(page.get_by_role("row", name="Admin Test Money 70")).to_be_visible()

    go_to(page, live_server, "/manage/accounting/")
    expect(page.locator("#one")).to_contain_text("20.00")
    expect(page.locator("#one")).to_contain_text("91.00")
    expect(page.locator("#one")).to_contain_text("70.00")
    expect(page.locator("#one")).to_contain_text("93.00")
    expect(page.locator("#one")).to_contain_text("72.00")
    expect(page.locator("#one")).to_contain_text("10.00")
    expect(page.locator("#one")).to_contain_text("30.00")


def sign_up_pay(page, live_server) -> None:
    go_to(page, live_server, "/test/manage/tickets/")
    page.get_by_role("link", name="").click()
    page.locator("#id_price").click()
    page.locator("#id_price").press("Home")
    page.locator("#id_price").fill("50.00")
    submit_confirm(page)

    go_to(page, live_server, "test/1/manage/form/")
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
    submit_confirm(page)

    go_to(page, live_server, "/test/register/")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/payments/")
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").press("Home")
    page.locator("#id_value").fill("70")
    page.get_by_text("---------").click()
    page.get_by_role("searchbox").fill("tes")
    page.get_by_role("option", name="Test Larp - Admin Test", exact=True).click()
    page.get_by_role("row", name="Info").locator("td").click()
    page.locator("#id_info").fill("sss")
    submit_confirm(page)


def add_exe(page, live_server) -> None:
    go_to(page, live_server, "/manage/outflows")
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").press("ArrowLeft")
    page.locator("#id_value").fill("10")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("babe")
    load_image(page, "#id_invoice")
    page.get_by_role("cell", name="--------- Indicate the").click()
    page.locator("#id_exp").select_option("a")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("15")
    page.get_by_label("---------").get_by_text("---------").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="Test Larp").click()
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("bibi")
    load_image(page, "#id_invoice")
    page.locator("#id_exp").select_option("c")
    submit_confirm(page)

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
    load_image(page, "#id_invoice")
    submit_confirm(page)
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("30")
    page.locator("#id_value").press("Tab")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("sdfs")
    load_image(page, "#id_invoice")
    submit_confirm(page)


def add_orga(page, live_server) -> None:
    go_to(page, live_server, "/test/manage/inflows")
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("13")
    page.locator("#id_value").press("Tab")
    page.locator("#id_descr").fill("asdsada")
    load_image(page, "#id_invoice")
    submit_confirm(page)
    # Check for the inflow with value 13.00 and description "asdsada"
    expect(page.get_by_role("row", name="Test Larp asdsada 13")).to_be_visible()
    # Check for the inflow with value 50.00 and description "ggg"
    expect(page.get_by_role("row", name="Test Larp ggg 50")).to_be_visible()

    go_to(page, live_server, "/test/manage/outflows")
    page.get_by_role("link", name="New").click()
    page.locator("#id_value").click()
    page.locator("#id_value").fill("47")
    page.locator("#id_descr").click()
    page.locator("#id_descr").fill("asdsad")
    load_image(page, "#id_invoice")
    page.locator("#id_exp").select_option("e")
    submit_confirm(page)


def config(page, live_server) -> None:
    # activate payments
    go_to(page, live_server, "/manage/features/payment/on")
    # activate taxes
    go_to(page, live_server, "/manage/features/vat/on")
    # activate inflows
    go_to(page, live_server, "/manage/features/inflow/on")
    # activate organization tax
    go_to(page, live_server, "/manage/features/organization_tax/on")
    # activate outflows
    go_to(page, live_server, "/manage/features/outflow/on")

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
    submit_confirm(page)
