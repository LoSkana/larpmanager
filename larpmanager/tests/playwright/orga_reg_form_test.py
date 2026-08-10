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
Test: Registration form with multiple features and surcharges.
Verifies registration form configuration with additional tickets, dynamic rates,
surcharges, pay what you want, and reserve tickets.
"""
import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import fill_date, go_to, login_orga, expect_normalized, submit_confirm, sidebar, \
    get_modal_iframe, save_modal, drag_reorder, expand_options

pytestmark = pytest.mark.e2e


def test_orga_registration_form(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    prepare_form(page, live_server)

    prepare_surcharge(page, live_server)

    signup(page, live_server)

    check_reserve(page, live_server)


def prepare_form(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "test/manage")
    # check initial reg form
    sidebar(page, "Form")
    expect_normalized(page, page.locator("#one"), "Ticket Your registration ticket Ticket")

    # Add features
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Additional tickets").check()
    page.get_by_role("checkbox", name="Dynamic rates").check()
    page.get_by_role("checkbox", name="Surcharge").check()
    page.get_by_role("checkbox", name="Pay what you want").check()
    submit_confirm(page)

    # check there are questions for all features
    page.get_by_role("link", name="Form").click()

    page.locator('[id="u1"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_text("Your registration ticket").click()
    edit_iframe.get_by_text("Your registration ticket").fill("Your registration ticket2")
    save_modal(page, edit_iframe)

    expect_normalized(page,
        page.locator("#one"),
        """
            Ticket Your registration ticket2 Ticket Additional Reserve additional tickets beyond your
            own Additional Optional Pay what you want Freely indicate the amount of your donation Pay
            what you want Optional payment installments select how many payments to split the fee into
             """
                      )
    expect_normalized(page,
        page.locator("#one"),
    "Installments Optional Surcharge Registration surcharge Surcharge Optional",
    )
    drag_reorder(
        page,
        page.locator('tr[id="u4"] td.reorder-handle'),
        page.locator('tr[id="u4"]').locator("xpath=preceding-sibling::tr[1]"),
    )
    drag_reorder(
        page,
        page.locator('tr[id="u2"] td.reorder-handle'),
        page.locator('tr[id="u2"]').locator("xpath=preceding-sibling::tr[1]"),
    )
    expect_normalized(page,
        page.locator("#one"),
        """
            Additional Reserve additional tickets beyond your own Additional Optional Ticket Your
            registration ticket2 Ticket payment installments select how many payments to split the fee into
        """
    )
    expect_normalized(page,
          page.locator("#one"),
        """
            Installments Optional Pay what you want Freely indicate the amount of your donation Pay what you want
            Optional Surcharge Registration surcharge Surcharge Optional
        """,
    )
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_text("Reserve additional tickets").click()
    edit_iframe.get_by_text("Reserve additional tickets").fill("Reserve additional tickets beyond your own2")
    save_modal(page, edit_iframe)
    expect_normalized(page, page.locator('[id="u2"]'), "Reserve additional tickets beyond your own2")

    # change ticket price
    page.get_by_role("link", name="Tickets").first.click()
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_price").click()
    edit_iframe.locator("#id_price").fill("5")
    edit_iframe.locator("#id_description").click()
    edit_iframe.locator("#id_description").fill("sadsadsadsa")
    save_modal(page, edit_iframe)


def prepare_surcharge(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "test/manage")
    # Add surcharges
    page.get_by_role("link", name="Surcharges").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_amount").click()
    edit_iframe.locator("#id_amount").fill("5")
    fill_date(edit_iframe, "#id_date", "2024-06-11")
    save_modal(page, edit_iframe)

    # set up payments
    go_to(page, live_server, "manage")
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Payments", exact=True).check()
    submit_confirm(page)
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").wait_for(state="visible")
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("dasdsadsa")
    page.locator("#id_wire_fee").click()
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_payee").click()
    page.locator("#id_wire_payee").fill("dsadsadsadas")
    page.locator("#id_wire_iban").click()
    page.locator("#id_wire_iban").fill("dasda")
    page.locator("#id_wire_fee").click()
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_bic").fill("test iban")
    submit_confirm(page)


def signup(page: Any, live_server: Any) -> None:
    # try signup
    go_to(page, live_server, "test/")
    page.get_by_role("link", name="Register").click()
    page.get_by_label("Additional").select_option("3")
    page.get_by_role("spinbutton", name="Pay what you want").click()
    page.get_by_role("spinbutton", name="Pay what you want").fill("4")
    page.get_by_role("button", name="Continue").click()
    expect_normalized(page, page.locator("#riepilogo"), "Your updated registration total is: 29€")
    submit_confirm(page)

    # submit profile
    page.get_by_role("checkbox", name="Authorisation").check()
    submit_confirm(page)

    expect_normalized(page, page.locator("#one"), "you are about to make a payment of: 29 €")

    # check form
    sidebar(page, "Your registration")
    # the registration already exists: unselected options start collapsed
    expand_options(page)
    expect_normalized(page,
        page.locator("#register_form"),
        """
        (*) : These fields are required Additional 0 1 2 3 4 5 Reserve additional tickets beyond your own2
        Ticket (*) Standard 5€ sadsadsadsa Hide other options Your registration ticket2
        Pay what you want Freely indicate the amount of your donation Surcharge 5€ Registration surcharge""",
    )


def check_reserve(page: Any, live_server: Any) -> None:
    # set up reserve
    go_to(page, live_server, "test/manage")
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Reserve").check()
    submit_confirm(page)

    sidebar(page, "Event")
    page.locator("#id_form1-max_filler").click()
    page.locator("#id_form1-max_filler").fill("5")
    submit_confirm(page)

    # check reserve is not there
    go_to(page, live_server, "test/")
    sidebar(page, "Your registration")
    # the accessible names include the show/hide options link, icon glyph included
    expect(page.locator("#id_ticket_tr")).to_match_aria_snapshot(
        """
        - row /Ticket \\(\\*\\) Standard 5€ sadsadsadsa .*Hide other options Your registration ticket2/:
          - cell "Ticket (*)"
          - cell /Standard 5€ sadsadsadsa .*Hide other options Your registration ticket2/:
            - radio "Standard 5€ sadsadsadsa" [checked]
        """
    )

    # enable config
    go_to(page, live_server, "test/manage")
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Reserve ")).click()
    page.locator("#id_filler_always").check()
    submit_confirm(page)

    # check filler is available
    go_to(page, live_server, "test/")
    sidebar(page, "Your registration")
    # the reserve ticket is not the selected one, so it starts collapsed
    ticket_row = page.locator("#id_ticket_tr")
    expect(ticket_row.get_by_role("radio", name="Reserve")).to_be_hidden()
    expand_options(page)
    expect(ticket_row.get_by_role("radio", name="Standard 5€ sadsadsadsa")).to_be_checked()
    expect(ticket_row.get_by_role("radio", name="Reserve")).not_to_be_checked()
    # expanded options are part of the visible text of the row
    expect_normalized(page, ticket_row, "Ticket (*) Standard 5€ sadsadsadsa Reserve")
