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
Test: Overpayments with tokens/credits, membership uploads, and special codes.
Verifies overpayment handling with tokens and credits, registration accounting adjustments,
membership document/fee uploads, and special payment code configuration.
"""
import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import just_wait, fill_tinymce, go_to, load_image, login_orga, expect_normalized, submit_confirm

pytestmark = pytest.mark.e2e


def test_overpay_upload_membership_prologue(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/")

    check_overpay(page, live_server)
    check_overpay_2(page, live_server)

    check_special_cod(page, live_server)

    upload_membership(page, live_server)
    upload_membership_fee(page, live_server)


def check_overpay(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/manage")
    # Activate tokens / credits
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Tokens").check()
    page.get_by_role("checkbox", name="Credits").check()
    submit_confirm(page)

    # Set ticket price
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Tickets").first.click()
    page.locator(".fa-edit").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("100.00")
    submit_confirm(page)

    # Signup
    go_to(page, live_server, "/")
    page.get_by_role("link", name="Registration is open!").click()
    page.locator("#register_form").click()
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Add credits
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Credits").click()
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("ad")
    page.locator(".select2-results__option").first.click()
    page.locator("#id_value").fill("60")
    page.locator("#id_descr").fill("cre")
    submit_confirm(page)

    # Check signup accounting
    page.get_by_role("link", name="Registrations").click()
    page.get_by_role("link", name="accounting", exact=True).click()
    expect_normalized(page, page.locator("#one"), "Admin Test Standard 8 40 60 100 60")


def check_overpay_2(page: Any, live_server: Any) -> None:
    # Add tokens
    page.get_by_role("link", name="Tokens").click()
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("adm")
    page.locator(".select2-results__option").first.click()
    page.locator("#id_value").press("Home")
    page.locator("#id_value").fill("60")
    page.locator("#id_descr").fill("www")
    submit_confirm(page)

    # Check signup accounting
    page.get_by_role("link", name="Registrations").click()
    page.get_by_role("link", name="accounting", exact=True).click()
    expect_normalized(page, page.locator("#one"), "Admin Test Standard 100 100 60 40")

    # Check accounting
    go_to(page, live_server, "/accounting")
    expect_normalized(page, page.locator("#one"), "Tokens Total: 20.00")

    # Change ticket price
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Tickets").first.click()
    page.locator(".fa-edit").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("80.00")
    submit_confirm(page)

    # Check accounting
    page.get_by_role("link", name="Registrations").click()
    page.get_by_role("link", name="accounting", exact=True).click()
    expect_normalized(page, page.locator("#one"), "Admin Test Standard -20 100 80 20 40 40")

    # Perform save
    page.locator(".fa-edit").click()
    submit_confirm(page)
    page.get_by_role("link", name="accounting", exact=True).click()
    expect_normalized(page, page.locator("#one"), "Admin Test Standard 80 80 40 40")

    # Check accounting
    go_to(page, live_server, "/accounting")
    expect_normalized(page,
        page.locator("#one"),
        "Credits Total: 20.00€"
    )

    expect_normalized(page,
        page.locator("#one"),
        "Tokens Total: 20.00"
    )


def check_special_cod(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Registrations ")).click()
    page.locator("#id_registration_no_grouping").check()
    page.locator("#id_registration_reg_que_allowed").check()
    submit_confirm(page)
    page.get_by_role("link", name="Registrations", exact=True).click()
    expect_normalized(page, page.locator("#one"), "Admin Test Standard")
    page.locator(".fa-edit").click()
    expect_normalized(page,
        page.locator("#main_form"),
        "Registration Member Admin Test - orga@test.it Admin Test - orga@test.it",
    )
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Admin Test Standard")


def prologues(page: Any) -> None:
    # activate prologues
    page.get_by_role("link", name="Features").first.click()
    page.get_by_role("checkbox", name="Prologues").check()
    submit_confirm(page)

    # redirected to prologue types
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("test")
    submit_confirm(page)

    # add prologue
    page.get_by_role("link", name="Prologues", exact=True).click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("ffff")
    fill_tinymce(page, "id_text", "sadsadsa")
    page.get_by_role("link", name="Show").click()
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("tes")
    page.locator(".select2-results__option").first.click()
    page.locator("#main_form").click()
    submit_confirm(page)

    # check result
    page.get_by_role("link", name="Characters").click()
    expect_normalized(page, page.locator("#one"), "P1 ffff (test) #1 Test Character")


def upload_membership(page: Any, live_server: Any) -> None:
    # Activate membership
    go_to(page, live_server, "/manage")
    page.locator("#exe_features").click()
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Membership").check()
    submit_confirm(page)

    # Set membership fee
    page.locator("#id_membership_fee").click()
    page.locator("#id_membership_fee").fill("10")
    submit_confirm(page)

    # Upload membership
    page.get_by_role("link", name="Members").click()
    page.get_by_role("link", name="Upload membership document").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("adm")
    page.locator(".select2-results__option").first.click()
    page.locator("#id_date").fill("2024-06-11")
    load_image(page, "#id_request")
    load_image(page, "#id_document")
    just_wait(page)
    page.locator("#id_date").click()
    just_wait(page)
    submit_confirm(page)

    # Try accessing member form
    just_wait(page)
    expect_normalized(page, page.locator("#one"), "Test Admin orga@test.it Accepted 1")
    page.locator(".fa-edit").click()

    # Check result
    go_to(page, live_server, "/membership")
    page.get_by_role("checkbox", name="Authorisation").check()
    submit_confirm(page)
    go_to(page, live_server, "/membership")

    expect_normalized(page, page.locator("#one"), "You are a regular member of our Organization")
    expect_normalized(page, page.locator("#one"), "In the membership book the number of your membership card is: 0001")
    expect_normalized(page,
        page.locator("#one"), "The payment of your membership fee for this year has NOT been receive"
    )


def upload_membership_fee(page: Any, live_server: Any) -> None:
    # upload fee
    go_to(page, live_server, "/manage")
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Payments", exact=True).check()
    submit_confirm(page)
    page.get_by_role("checkbox", name="Wire").check()
    just_wait(page)
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("rwerewrwe")
    page.locator("#id_wire_fee").click()
    page.locator("#id_wire_fee").fill("22")
    page.locator("#id_wire_payee").click()
    page.locator("#id_wire_payee").fill("3123213213")
    page.locator("#id_wire_iban").click()
    page.locator("#id_wire_iban").fill("321321321")
    page.locator("#id_wire_bic").fill("test iban")
    submit_confirm(page)

    page.get_by_role("link", name="Members").click()
    page.get_by_role("link", name="Upload membership fee").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("adm")
    page.locator(".select2-results__option").first.click()
    load_image(page, "#id_invoice")
    submit_confirm(page)

    # check
    expect_normalized(page, page.locator("#one"), "Test Admin orga@test.it Payed 1")
    page.get_by_role("link", name="Invoices").click()
    expect_normalized(page, page.locator("#one"), "Admin Test Wire membership Confirmed 10 Membership fee of Admin Test")
