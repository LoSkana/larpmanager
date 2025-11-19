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


from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, login_orga

pytestmark = pytest.mark.e2e


def test_orga_reg_form(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    prepare_form(page, live_server)

    prepare_surcharge(page, live_server)

    signup(page, live_server)

    check_filler(page, live_server)


def prepare_form(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "test/manage")
    # check initial reg form
    page.locator("#orga_registration_form").get_by_role("link", name="Form").click()
    expect(page.locator("#one")).to_contain_text("Ticket Your registration ticket Ticket")

    # Add features
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Additional tickets").check()
    page.get_by_role("checkbox", name="Dynamic rates").check()
    page.get_by_role("checkbox", name="Surcharge").check()
    page.get_by_role("checkbox", name="Pay what you want").check()
    page.get_by_role("button", name="Confirm").click()

    # check there are questions for all features
    page.get_by_role("link", name="Form").click()
    page.locator('[id="\\31 "]').get_by_role("cell", name="").click()
    page.get_by_text("Your registration ticket").click()
    page.get_by_text("Your registration ticket").fill("Your registration ticket2")
    page.get_by_role("button", name="Confirm").click()

    expect(page.locator("#one")).to_contain_text(
        "Ticket Your registration ticket2 Ticket Additional Reserve additional tickets beyond your own Additional Optional Pay what you want Freely indicate the amount of your donation Pay what you want Optional Rate Number of installments to split the fee: payments… Rate Optional Surcharge Registration surcharge Surcharge Optional"
    )
    page.locator('[id="\\34 "]').get_by_role("link", name="").click()
    page.locator('[id="\\32 "]').get_by_role("link", name="").click()
    expect(page.locator("#one")).to_contain_text(
        "Additional Reserve additional tickets beyond your own Additional Optional Ticket Your registration ticket2 Ticket Rate Number of installments to split the fee: payments… Rate Optional Pay what you want Freely indicate the amount of your donation Pay what you want Optional Surcharge Registration surcharge Surcharge Optional"
    )
    page.locator('[id="\\32 "]').get_by_role("link", name="").click()
    page.get_by_text("Reserve additional tickets").click()
    page.get_by_text("Reserve additional tickets").fill("Reserve additional tickets beyond your own2")
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator('[id="\\32 "]')).to_contain_text("Reserve additional tickets beyond your own2")

    # change ticket price
    page.locator("#orga_registration_tickets").get_by_role("link", name="Tickets").click()
    page.get_by_role("link", name="").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("5")
    page.locator("#id_description").click()
    page.locator("#id_description").fill("sadsadsadsa")
    page.get_by_role("button", name="Confirm").click()


def prepare_surcharge(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "test/manage")
    # Add surcharges
    page.get_by_role("link", name="Surcharges").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_amount").click()
    page.locator("#id_amount").fill("5")
    page.locator("#id_date").fill("2024-06-11")
    page.wait_for_timeout(2000)
    page.locator("#id_date").click()
    page.get_by_role("button", name="Confirm").click()

    # set up payments
    go_to(page, live_server, "manage")
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Payments", exact=True).check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("checkbox", name="Wire").check()
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
    page.get_by_role("button", name="Confirm").click()


def signup(page: Any, live_server: Any) -> None:
    # try signup
    go_to(page, live_server, "test/")
    page.get_by_role("link", name="Register").click()
    page.get_by_label("Additional").select_option("3")
    page.get_by_role("spinbutton", name="Pay what you want").click()
    page.get_by_role("spinbutton", name="Pay what you want").fill("4")
    page.get_by_role("button", name="Continue").click()
    expect(page.locator("#riepilogo")).to_contain_text("Your updated registration total is: 29€")
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("#one")).to_contain_text("The total registration fee is: 29€")

    # check form
    page.get_by_role("link", name="Event").click()
    page.get_by_role("link", name="Registration", exact=True).click()
    expect(page.locator("#register_form")).to_contain_text(
        "(*) : These fields are mandatory Additional 0 1 2 3 4 5 Reserve additional tickets beyond your own2 Ticket (*) Standard - 5€ Your registration ticket2Standard: sadsadsadsa Pay what you want Freely indicate the amount of your donation Surcharge 5€ Registration surcharge"
    )


def check_filler(page: Any, live_server: Any) -> None:
    # set up filler
    go_to(page, live_server, "test/manage")
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Filler").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Event").click()
    page.locator("#id_form1-max_filler").click()
    page.locator("#id_form1-max_filler").fill("5")
    page.get_by_role("button", name="Confirm").click()

    # check filler is not there
    go_to(page, live_server, "test/")
    page.get_by_role("link", name="Registration", exact=True).click()
    page.get_by_label("Ticket (*)").click()
    expect(page.get_by_label("Ticket (*)")).to_match_aria_snapshot(
        '- combobox "Ticket (*)":\n  - option "Standard - 5€" [selected]'
    )

    # enable config
    go_to(page, live_server, "test/manage")
    page.locator("#orga_config").get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Ticket Filler ").click()
    page.locator("#id_filler_always").check()
    page.get_by_role("button", name="Confirm").click()

    # check filler is not available
    go_to(page, live_server, "test/")
    page.get_by_role("link", name="Registration", exact=True).click()
    page.get_by_label("Ticket (*)").click()
    expect(page.get_by_label("Ticket (*)")).to_match_aria_snapshot(
        '- combobox "Ticket (*)":\n  - option "Standard - 5€" [selected]\n  - option "Filler"'
    )
