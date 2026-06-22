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
Test: Organization accounting with payments, taxes, inflows, and outflows.
Verifies organization and event-level accounting entries, VAT calculations,
organization tax percentages, payment tracking, and consolidated accounting reports.
"""
import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, load_image, login_orga, submit_confirm, expect_normalized, submit_register, \
    new_option, submit_option, get_modal_iframe, save_modal, just_wait

pytestmark = pytest.mark.e2e


def test_exe_accounting(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    config(page, live_server)

    add_exe(page, live_server)

    add_orga(page, live_server)

    sign_up_pay(page, live_server)

    verify(page, live_server)


def verify(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/accounting/")
    expect_normalized(page, page.locator("#one"), "Realized revenue: 133.00")
    expect_normalized(page, page.locator("#one"), "Net profit: 71.00")
    expect_normalized(page, page.locator("#one"), "Organization tax: 17.29")
    expect_normalized(page, page.locator("#one"), "Registrations: 70.00")
    expect_normalized(page, page.locator("#one"), "Outflows: 62.00")
    expect_normalized(page, page.locator("#one"), "Inflows: 63.00")
    expect_normalized(page, page.locator("#one"), "Income: 70.00")

    go_to(page, live_server, "/test/manage/payments/")
    # Check for payment row with value 70
    expect(page.get_by_role("row", name="Admin Test Money 70")).to_be_visible()

    go_to(page, live_server, "/manage/accounting/")
    expect_normalized(page, page.locator("#one"), "20.00")
    expect_normalized(page, page.locator("#one"), "91.00")
    expect_normalized(page, page.locator("#one"), "70.00")
    expect_normalized(page, page.locator("#one"), "93.00")
    expect_normalized(page, page.locator("#one"), "72.00")
    expect_normalized(page, page.locator("#one"), "10.00")
    expect_normalized(page, page.locator("#one"), "30.00")


def sign_up_pay(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/tickets/")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_price").click()
    edit_iframe.locator("#id_price").press("Home")
    edit_iframe.locator("#id_price").fill("50.00")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "test/manage/form/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("pay")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_description").fill("pay")
    option_row = new_option(edit_iframe)
    option_row.locator("#id_name").click()
    option_row.locator("#id_name").fill("ff")
    option_row.locator("#id_price").click()
    option_row.locator("#id_price").fill("20")
    submit_option(edit_iframe, option_row)

    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/register/")
    page.locator('label[for="id_que_u2_0"]').click()
    submit_register(page)

    go_to(page, live_server, "/test/manage/payments/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").press("Home")
    edit_iframe.locator("#id_value").fill("70")
    edit_iframe.get_by_text("---------").click()
    edit_iframe.get_by_role("searchbox").fill("tes")
    edit_iframe.get_by_role("option", name="Test Larp - Admin Test", exact=True).click()
    edit_iframe.get_by_role("row", name="Info").locator("td").click()
    edit_iframe.locator("#id_info").fill("sss")
    save_modal(page, edit_iframe)


def add_exe(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/manage/outflows")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").press("ArrowLeft")
    edit_iframe.locator("#id_value").fill("10")
    edit_iframe.locator("#id_descr").click()
    edit_iframe.locator("#id_descr").fill("babe")
    load_image(edit_iframe,"#id_invoice")
    edit_iframe.get_by_role("cell", name="--------- Indicate the").click()
    edit_iframe.locator("#id_exp").select_option("a")
    save_modal(page, edit_iframe)
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").fill("15")
    edit_iframe.get_by_label("---------").get_by_text("---------").click()
    edit_iframe.get_by_role("searchbox").fill("te")
    edit_iframe.get_by_role("option", name="Test Larp").click()
    edit_iframe.locator("#id_descr").click()
    edit_iframe.locator("#id_descr").fill("bibi")
    load_image(edit_iframe,"#id_invoice")
    edit_iframe.locator("#id_exp").select_option("c")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/manage/inflows")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").press("ArrowLeft")
    edit_iframe.locator("#id_value").fill("50")
    edit_iframe.locator("#select2-id_run-container").click()
    edit_iframe.get_by_role("searchbox").fill("tes")
    edit_iframe.get_by_role("option", name="Test Larp").click()
    edit_iframe.get_by_role("combobox", name=re.compile("Test Larp$")).press("Tab")
    edit_iframe.locator("#id_descr").fill("ggg")
    load_image(edit_iframe,"#id_invoice")
    save_modal(page, edit_iframe)
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").fill("30")
    edit_iframe.locator("#id_value").press("Tab")
    edit_iframe.locator("#id_descr").click()
    edit_iframe.locator("#id_descr").fill("sdfs")
    load_image(edit_iframe,"#id_invoice")
    save_modal(page, edit_iframe)


def add_orga(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/inflows")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").fill("13")
    edit_iframe.locator("#id_value").press("Tab")
    edit_iframe.locator("#id_descr").fill("asdsada")
    load_image(edit_iframe,"#id_invoice")
    save_modal(page, edit_iframe)

    just_wait(page)
    # Check for the inflow with value 13.00 and description "asdsada"
    expect(page.get_by_role("row", name="Test Larp asdsada 13")).to_be_visible()
    # Check for the inflow with value 50.00 and description "ggg"
    expect(page.get_by_role("row", name="Test Larp ggg 50")).to_be_visible()

    go_to(page, live_server, "/test/manage/outflows")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").fill("47")
    edit_iframe.locator("#id_descr").click()
    edit_iframe.locator("#id_descr").fill("asdsad")
    load_image(edit_iframe,"#id_invoice")
    edit_iframe.locator("#id_exp").select_option("e")
    save_modal(page, edit_iframe)


def config(page: Any, live_server: Any) -> None:
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
    page.get_by_role("link", name=re.compile(r"^Payments ")).click()
    page.locator("#id_payment_special_code").check()
    page.get_by_role("link", name=re.compile(r"^VAT ")).click()
    page.locator("#id_vat_ticket").click()
    page.locator("#id_vat_ticket").fill("7")
    page.locator("#id_vat_options").click()
    page.locator("#id_vat_options").fill("11")
    page.get_by_role("link", name=re.compile(r"^Organisation fee ")).click()
    page.get_by_role("cell", name="Percentage of takings").click()
    page.locator("#id_organization_tax_perc").fill("13")
    submit_confirm(page)
