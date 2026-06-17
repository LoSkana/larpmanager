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
Test: Paginate views (orga_paginate and exe_paginate).
Verifies all pages using orga_paginate/exe_paginate can be accessed,
new items can be created, and items appear in the paginated table after creation.
"""

from typing import Any

import pytest

from larpmanager.tests.utils import expect_normalized, get_modal_iframe, go_to, just_wait, load_image, login_orga, \
    submit_confirm, submit, save_modal

pytestmark = pytest.mark.e2e


def test_paginate(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    config(page, live_server)

    orga_paginate_views(page, live_server)

    exe_paginate_views(page, live_server)


def config(page: Any, live_server: Any) -> None:
    for feature in [
        "inflow",
        "outflow",
        "payment",
        "tokens",
        "credits",
        "donate",
        "expense",
        "refund",
        "logs",
    ]:
        go_to(page, live_server, f"/manage/features/{feature}/on")

    # set up payment method
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

    # set ticket price
    go_to(page, live_server, "/test/manage/tickets")
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_price").click()
    edit_iframe.locator("#id_price").fill("100.00")
    save_modal(page, edit_iframe)

    # Signup
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)
    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Provisional registration")
    page.locator("#one").get_by_role("link", name="Accounting").click()
    expect_normalized(page, page.locator("#one"), "100")

    # pay
    go_to(page, live_server, "/accounting/registration/u1/")
    expect_normalized(page, page.locator("#one"), "100")
    submit(page)
    page.get_by_role("checkbox", name="Payment confirmation:").check()
    submit(page)

    # confirm payment
    go_to(page, live_server, "/test/manage/invoices")
    page.get_by_role("link", name="Confirm", exact=True).click()




def check_paginate(page: Any, live_server: Any, path: str, descr: str) -> None:
    """Navigate to a paginate list page and verify item appears in the table."""
    go_to(page, live_server, path)
    just_wait(page, big=True)
    expect_normalized(page, page.locator("#one"), descr)

    # try to change it
    page.locator(".fa-edit").first.click()



def exe_paginate_views(page: Any, live_server: Any) -> None:
    # exe_outflows
    go_to(page, live_server, "/manage/outflows/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").fill("10")
    edit_iframe.locator("#id_descr").fill("test outflow exe")
    load_image(edit_iframe,"#id_invoice")
    edit_iframe.locator("#id_exp").select_option("a")
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/manage/outflows/", "test outflow exe")

    # exe_inflows
    go_to(page, live_server, "/manage/inflows/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").fill("20")
    edit_iframe.locator("#id_descr").fill("test inflow exe")
    load_image(edit_iframe,"#id_invoice")
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/manage/inflows/", "test inflow exe")

    # exe_donations
    go_to(page, live_server, "/manage/donations/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("User")
    edit_iframe.get_by_role("option", name="User Test").click()
    edit_iframe.locator("#id_descr").fill("test donation exe")
    edit_iframe.locator("#id_value").fill("5")
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/manage/donations/", "test donation exe")

    # exe_credits
    go_to(page, live_server, "/manage/credits/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("User")
    edit_iframe.get_by_role("option", name="User Test").click()
    edit_iframe.locator("#id_descr").fill("test credit exe")
    edit_iframe.locator("#id_value").fill("50")
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/manage/credits/", "test credit exe")

    # exe_tokens
    go_to(page, live_server, "/manage/tokens/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("User")
    edit_iframe.get_by_role("option", name="User Test").click()
    edit_iframe.locator("#id_descr").fill("test token exe")
    edit_iframe.locator("#id_value").fill("30")
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/manage/tokens/", "test token exe")

    # exe_expenses
    go_to(page, live_server, "/manage/expenses/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("User")
    edit_iframe.get_by_role("option", name="User Test").click()
    edit_iframe.locator("#id_descr").fill("test expense exe")
    edit_iframe.locator("#id_value").fill("15")
    load_image(edit_iframe,"#id_invoice")
    edit_iframe.locator("#id_exp").select_option("a")
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/manage/expenses/", "test expense exe")

    # exe_payments - page load only
    go_to(page, live_server, "/manage/payments/")

    # exe_invoices - page load only
    go_to(page, live_server, "/manage/invoices/")

    # exe_refunds - page load only
    go_to(page, live_server, "/manage/refunds/")

    # exe_log - read only
    go_to(page, live_server, "/manage/logs/")


def orga_paginate_views(page: Any, live_server: Any) -> None:
    # orga_outflows
    go_to(page, live_server, "/test/manage/outflows/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").fill("10")
    edit_iframe.locator("#id_descr").fill("test outflow orga")
    load_image(edit_iframe,"#id_invoice")
    edit_iframe.locator("#id_exp").select_option("a")
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/test/manage/outflows/", "test outflow orga")

    # orga_inflows
    go_to(page, live_server, "/test/manage/inflows/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").fill("20")
    edit_iframe.locator("#id_descr").fill("test inflow orga")
    load_image(edit_iframe,"#id_invoice")
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/test/manage/inflows/", "test inflow orga")

    # orga_tokens
    go_to(page, live_server, "/test/manage/tokens/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_descr").fill("test token orga")
    edit_iframe.locator("#id_value").fill("30")
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("ad")
    edit_iframe.get_by_role("option", name="Admin Test - orga@test.it").click()
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/test/manage/tokens/", "test token orga")

    # orga_credits
    go_to(page, live_server, "/test/manage/credits/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_descr").fill("test credit orga")
    edit_iframe.locator("#id_value").fill("50")
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("ad")
    edit_iframe.get_by_role("option", name="Admin Test - orga@test.it").click()
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/test/manage/credits/", "test credit orga")

    # orga_expenses
    go_to(page, live_server, "/test/manage/expenses/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#select2-id_member-container").click()
    edit_iframe.get_by_role("searchbox").fill("ad")
    edit_iframe.get_by_role("option", name="Admin Test - orga@test.it").click()
    edit_iframe.locator("#id_descr").fill("test expense orga")
    edit_iframe.locator("#id_value").fill("15")
    load_image(edit_iframe,"#id_invoice")
    edit_iframe.locator("#id_exp").select_option("a")
    save_modal(page, edit_iframe)
    check_paginate(page, live_server, "/test/manage/expenses/", "test expense orga")

    # orga_payments - page load only
    go_to(page, live_server, "/test/manage/payments/")

    # orga_log - read only
    go_to(page, live_server, "/test/manage/logs/")

    # open request
    go_to(page, live_server, "/accounting/")
    page.get_by_role("link", name="refund request").click()
    page.get_by_role("textbox", name="Details").click()
    page.get_by_role("textbox", name="Details").fill("asdsadsadsa")
    page.get_by_role("spinbutton", name="Value").click()
    page.get_by_role("spinbutton", name="Value").fill("20")
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Requests open: asdsadsadsa (20.00)")
