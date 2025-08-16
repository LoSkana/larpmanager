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

from larpmanager.tests.utils import check_download, go_to, login_orga

pytestmark = pytest.mark.e2e


def test_upload_download(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/manage/")

    # check shows fee
    check_user_fee(live_server, page)

    # prepare
    go_to(page, live_server, "/test/1/manage/")
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.locator("#id_mod_1_0").check()
    page.locator("#id_mod_1_3").check()
    page.locator("#id_mod_1_4").check()
    page.locator("#id_mod_5_1").check()
    page.get_by_role("button", name="Confirm").click()

    char_form(page)

    factions(page)

    characters(page)

    reg_form(page)

    registrations(page)

    quest_trait(page)

    plots(live_server, page)

    relationships(page)

    full(page)


def full(page):
    page.get_by_role("link", name="Dashboard").click()
    check_download(page, "Full backup")


def relationships(page):
    page.get_by_role("link", name="Features").click()
    page.locator("#id_mod_1_6").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_second").click()
    page.locator("#id_second").set_input_files(get_path("relationships.csv"))
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("OK - Relationship characcter test character")
    page.get_by_role("link", name="Proceed").click()
    page.get_by_role("link", name="Relationships").click()
    expect(page.locator("#one")).to_contain_text(
        "#1 Test Character Test Teaser Test Text #2 characcter trg poor ertd fewr #1 Test Character"
    )


def plots(live_server, page):
    page.get_by_role("link", name="Plots").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_first").click()
    page.locator("#id_first").set_input_files(get_path("plot.csv"))
    page.locator("#id_second").click()
    page.locator("#id_second").set_input_files(get_path("roles.csv"))
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text(
        "Loading performed, see logs Proceed Logs OK - Created plottOK - Plot role characcter plott"
    )
    page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text("T1 plott conceptt textt")
    page.get_by_role("link", name="").click()
    page.get_by_role("cell", name="Show This text will be added").get_by_role("link").click()
    expect(page.locator("#id_char_role_2_tr")).to_contain_text("#2 characcter")
    expect(page.locator("#id_char_role_2_tr")).to_contain_text("super start")
    go_to(page, live_server, "/test/1/manage/plots/")
    check_download(page, "Download")


def quest_trait(page):
    page.get_by_role("link", name="Quest", exact=True).click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.get_by_role("link", name="Quest type").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("bhbh")
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name="Quest", exact=True).click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_first").set_input_files(get_path("quest.csv"))
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("Loading performed, see logs Proceed Logs OK - Created questt")
    page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text("Q1 questt bhbh presenttation ttext")
    check_download(page, "Download")
    page.locator("#orga_traits").get_by_role("link", name="Traits").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_first").set_input_files(get_path("trait.csv"))
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("Loading performed, see logs Proceed Logs OK - Created traitt")
    page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text("T1 traitt Q1 questt ppresentation teeeext")
    check_download(page, "Download")


def registrations(page):
    page.get_by_role("link", name="Registrations").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_first").set_input_files(get_path("registration.csv"))
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("OK - Created User Test")
    page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text("User Test Standard #2 characcter")
    check_download(page, "Download")


def reg_form(page):
    page.locator("#orga_registration_form").get_by_role("link", name="Form").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_first").set_input_files(get_path("reg-questions.csv"))
    page.locator("#id_second").click()
    page.locator("#id_second").set_input_files(get_path("reg-options.csv"))
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text(
        "Loading performed, see logs Proceed Logs OK - Created tbmobwOK - Created qmhcufOK - Created holdmfOK - Created lyucezOK - Created bamkzwOK - Created npyrxdOK - Created rdtbggOK - Created qkcyjrOK - Created fjxkum"
    )
    page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text(
        "tbmobw npyrxd Multiple choice Optional npyrxd , rdtbgg qmhcuf rdtbgg Multi-line text Mandatory holdmf qkcyjr Single-line text Disabled lyucez fjxkum Advanced text editor Hidden bamkzw fzynqq Single choice Optional qkcyjr , fjxkum"
    )
    check_download(page, "Download")


def characters(page):
    page.locator("#orga_characters").get_by_role("link", name="Characters").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_first").set_input_files(get_path("character.csv"))
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("OK - Created characcter")
    page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text(
        "#1 Test Character Test Teaser Test Text #2 characcter trg poor ertd fewr"
    )
    check_download(page, "Download")


def factions(page):
    page.get_by_role("link", name="Factions").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_first").set_input_files(get_path("faction.csv"))
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text("OK - Created facction")
    page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text("facction Primary gh asd oeir sdf")
    check_download(page, "Download")


def char_form(page):
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_first").set_input_files(get_path("char-questions.csv"))
    page.locator("#id_second").set_input_files(get_path("char-options.csv"))
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#one")).to_contain_text(
        "Loading performed, see logs Proceed Logs OK - Created bibiOK - Created babaOK - Created werOK - Created asdOK - Created poiOK - Created huhuOK - Created trtrOK - Created rrrrrrOK - Created tttttt"
    )
    page.get_by_role("link", name="Proceed").click()
    expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet Faction Factions Hidden bibi baba Multiple choice Searchable huhu , trtr"
    )
    check_download(page, "Download")
    page.get_by_role("link", name="Plot", exact=True).click()
    expect(page.locator("#one")).to_contain_text(
        "Name Name Concept Presentation Text Sheet wer fghj Single-line text Hidden"
    )
    page.get_by_role("link", name="Faction", exact=True).click()
    expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet baba bebe Multi-line text Private"
    )
    page.locator("#one").get_by_role("link", name="Quest").click()
    expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet asd kloi Advanced text editor Public"
    )
    page.get_by_role("link", name="Trait", exact=True).click()
    expect(page.locator("#one")).to_contain_text(
        "Name Name Presentation Presentation Text Sheet poi rweerw Single choice Public rrrrrr , tttttt"
    )


def check_user_fee(live_server, page):
    go_to(page, live_server, "/manage/")
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.locator("#id_mod_2_0").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").click()
    page.locator("#id_wire_descr").fill("aaaa")
    page.locator("#id_wire_fee").click()
    page.locator("#id_wire_fee").fill("2")
    page.locator("#id_wire_payee").click()
    page.locator("#id_wire_payee").fill("2asdsadas")
    page.locator("#id_wire_iban").click()
    page.locator("#id_wire_iban").fill("3sadsadsa")
    page.get_by_role("button", name="Confirm").click()
    page.locator("#exe_features").get_by_role("link", name="Features").click()
    page.locator("#id_mod_2_1").check()
    page.get_by_role("button", name="Confirm").click()
    page.locator("#exe_config").get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Payments ").click()
    page.locator("#id_payment_fees_user").check()
    page.get_by_role("button", name="Confirm").click()
    page.get_by_role("link", name=" Accounting").click()
    page.get_by_role("link", name="follow this link").click()
    expect(page.locator("#wrapper")).to_contain_text(
        "Test Larp Organization Home Indicate the amount of your donation: Please enter the occasion for which you wish to make the donation Choose the payment method: Wire Fee: +2% aaaa Submit"
    )


def get_path(file):
    return Path(__file__).parent / "resources" / "test_upload" / file
