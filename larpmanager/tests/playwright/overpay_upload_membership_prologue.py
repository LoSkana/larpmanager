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

from larpmanager.tests.utils import fill_tinymce, go_to, load_image, login_orga

pytestmark = pytest.mark.e2e


def test_overpay_upload_membership_prologue(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/")

    check_overpay(page, live_server)
    check_overpay_2(page, live_server)

    check_special_cod(page, live_server)

    upload_membership(page, live_server)
    upload_membership_fee(page, live_server)


def check_overpay(page, live_server):
    go_to(page, live_server, "/manage")
    # Activate tokens / credits
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Tokens / Credits").check()
    page.get_by_role("button", name="Confirm").click()

    # Set ticket price
    go_to(page, live_server, "/test/manage")
    page.locator("#orga_registration_tickets").get_by_role("link", name="Tickets").click()
    page.get_by_role("link", name="").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("100.00")
    page.get_by_role("button", name="Confirm").click()

    # Signup
    go_to(page, live_server, "/")
    page.get_by_role("link", name="Registration is open!").click()
    page.locator("#register_form").click()
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm").click()

    # Add credits
    go_to(page, live_server, "/test/manage")
    page.get_by_role("link", name="Credits").click()
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("ad")
    page.locator(".select2-results__option").first.click()
    page.locator("#id_value").fill("60")
    page.locator("#id_descr").fill("cre")
    page.get_by_role("button", name="Confirm").click()

    # Check signup accounting
    page.get_by_role("link", name="Registrations").click()
    page.get_by_role("link", name="accounting", exact=True).click()
    expect(page.locator("#one")).to_contain_text("Admin Test Standard 84060100 60")


def check_overpay_2(page, live_server):
    # Add tokens
    page.get_by_role("link", name="Tokens").click()
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("adm")
    page.locator(".select2-results__option").first.click()
    page.locator("#id_value").press("Home")
    page.locator("#id_value").fill("60")
    page.locator("#id_descr").fill("www")
    page.get_by_role("button", name="Confirm").click()

    # Check signup accounting
    page.get_by_role("link", name="Registrations").click()
    page.get_by_role("link", name="accounting", exact=True).click()
    expect(page.locator("#one")).to_contain_text("Admin Test Standard 100100 6040")

    # Check accounting
    go_to(page, live_server, "/accounting")
    expect(page.locator("#one")).to_contain_text("Tokens Total: 20.00")

    # Change ticket price
    go_to(page, live_server, "/test/manage")
    page.get_by_role("link", name="Tickets").click()
    page.get_by_role("link", name="").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("80.00")
    page.get_by_role("button", name="Confirm").click()

    # Check accounting
    page.get_by_role("link", name="Registrations").click()
    page.get_by_role("link", name="accounting", exact=True).click()
    expect(page.locator("#one")).to_contain_text("Admin Test Standard -2010080204040")

    # Perform save
    page.get_by_role("link", name="").click()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="accounting", exact=True).click()
    expect(page.locator("#one")).to_contain_text("Admin Test Standard 8080 4040")

    # Check accounting
    go_to(page, live_server, "/accounting")
    expect(page.locator("#one")).to_contain_text(
        "Credits Total: 20.00€. They will be used automatically when you sign up for a new event! Tokens Total: 20.00. They will be used automatically when you sign up for a new event! Registration history Test Larp Test Larp Ticket chosen Standard (80.00€)"
    )


def check_special_cod(page, live_server):
    go_to(page, live_server, "/test/manage")
    page.locator("#orga_config").get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Registrations ").click()
    page.locator("#id_registration_unique_code").check()
    page.locator("#id_registration_no_grouping").check()
    page.locator("#id_registration_reg_que_allowed").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Registrations", exact=True).click()
    expect(page.locator("#one")).to_contain_text("Admin Test Standard")
    page.get_by_role("link", name="").click()
    expect(page.locator("#main_form")).to_contain_text(
        "Registration Member Admin Test - orga@test.it Admin Test - orga@test.it Details Unique code Confirm"
    )
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("#one")).to_contain_text("Admin Test Standard")


def prologues(page):
    # activate prologues
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Prologues").check()
    page.get_by_role("button", name="Confirm").click()

    # redirected to prologue types
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("test")
    page.get_by_role("button", name="Confirm").click()

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
    page.get_by_role("button", name="Confirm").click()

    # check result
    page.get_by_role("link", name="Characters").click()
    expect(page.locator("#one")).to_contain_text("P1 ffff (test) #1 Test Character")


def upload_membership(page, live_server):
    # Activate membership
    go_to(page, live_server, "/manage")
    page.locator("#exe_features").click()
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Membership").check()
    page.get_by_role("button", name="Confirm").click()

    # Set membership fee
    page.locator("#id_membership_fee").click()
    page.locator("#id_membership_fee").fill("10")
    page.get_by_role("button", name="Confirm").click()

    # Upload membership
    page.get_by_role("link", name="Membership").click()
    page.get_by_role("link", name="Upload membership document").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("adm")
    page.locator(".select2-results__option").first.click()
    load_image(page, "#id_request")
    load_image(page, "#id_document")
    page.locator("#id_date").fill("2024-06-11")
    page.wait_for_timeout(2000)
    page.locator("#id_date").click()
    page.get_by_role("button", name="Confirm").click()

    # Try accessing member form
    expect(page.locator("#one")).to_contain_text("Test Admin orga@test.it Accepted 1")
    page.get_by_role("link", name="").click()

    # Check result
    go_to(page, live_server, "/membership")
    page.get_by_role("checkbox", name="Authorisation").check()
    page.get_by_role("button", name="Submit").click()
    go_to(page, live_server, "/membership")

    expect(page.locator("#one")).to_contain_text("You are a regular member of our Organization")
    expect(page.locator("#one")).to_contain_text("In the membership book the number of your membership card is: 0001")
    expect(page.locator("#one")).to_contain_text(
        "The payment of your membership fee for this year has NOT been receive"
    )


def upload_membership_fee(page, live_server):
    # upload fee
    go_to(page, live_server, "/manage")
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Payments", exact=True).check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("rwerewrwe")
    page.locator("#id_wire_fee").click()
    page.locator("#id_wire_fee").fill("22")
    page.locator("#id_wire_payee").click()
    page.locator("#id_wire_payee").fill("3123213213")
    page.locator("#id_wire_iban").click()
    page.locator("#id_wire_iban").fill("321321321")
    page.get_by_role("button", name="Confirm").click()

    page.get_by_role("link", name="Membership").click()
    page.get_by_role("link", name="Upload membership fee").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill("adm")
    page.locator(".select2-results__option").first.click()
    load_image(page, "#id_invoice")
    page.get_by_role("button", name="Confirm").click()

    # check
    expect(page.locator("#one")).to_contain_text("Test Admin orga@test.it Payed 1")
    page.get_by_role("link", name="Invoices").click()
    expect(page.locator("#one")).to_contain_text("Admin TestWiremembershipConfirmed10Membership fee of Admin Test")
