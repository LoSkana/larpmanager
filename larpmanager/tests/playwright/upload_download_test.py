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
Test: CSV upload and download functionality for all features.
Verifies bulk upload/download for character forms, factions, characters, registration forms,
registrations, quests/traits, plots, relationships, abilities, and full backup.
"""
import re
from pathlib import Path
from typing import Any

import pytest

from larpmanager.tests.utils import (
    check_download,
    check_feature,
    go_to,
    login_orga,
    submit_confirm,
    upload,
    expect_normalized, sidebar,
)

pytestmark = pytest.mark.e2e


def test_upload_download(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "/manage/")

    # prepare
    go_to(page, live_server, "/test/manage/")
    page.get_by_role("link", name="Features").first.click()
    check_feature(page, "Characters")
    check_feature(page, "Factions")
    check_feature(page, "Plots")
    check_feature(page, "Quests and Traits")
    check_feature(page, "Experience points")
    submit_confirm(page)

    char_form(page)

    factions(page)

    characters(page)

    reg_form(page)

    registrations(page)

    quest_trait(page)

    plots(live_server, page)

    relationships(page)

    abilities(page)

    full(page)


def abilities(page: Any) -> None:
    # add type
    page.get_by_role("link", name="Ability type").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("test")
    submit_confirm(page)

    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Experience points ")).click()
    page.locator("#id_px_user").check()
    submit_confirm(page)

    sidebar(page, "Ability")
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_first").click()
    upload(page, "#id_first", get_path("abilities.csv"))
    submit_confirm(page)
    expect_normalized(
        page,
        page.locator("#one"),
        "Loading performed, see logs Proceed Logs OK - Created sword OK - Created shield OK - Created sneak",
    )
    page.get_by_role("link", name="Proceed").click()
    expect_normalized(
        page,
        page.locator("#one"),
        "sword test 2 baba True shield test 3 bibi True sword sneak test 4 bubu True sword | shield trtr | rrrrrr",
    )
    check_download(page, "Download")


def full(page: Any) -> None:
    page.get_by_role("link", name="Dashboard").click()

    check_download(page, "Full backup")


def relationships(page: Any) -> None:
    page.get_by_role("link", name="Features").first.click()
    check_feature(page, "Relationships")
    submit_confirm(page)
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_second").click()
    upload(page, "#id_second", get_path("relationships.csv"))
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), " OK - Relationship characcter test character")
    page.get_by_role("link", name="Proceed").click()
    page.get_by_role("link", name="Relationships").click()
    expect_normalized(
        page,
        page.locator("#one"),
        "#1 Test Character Test Teaser Test Text #2 characcter trg poor ertd fewr Test Character",
    )


def plots(live_server: Any, page: Any) -> None:
    page.get_by_role("link", name="Plots").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.locator("#id_first").click()
    upload(page, "#id_first", get_path("plot.csv"))
    page.locator("#id_second").click()
    upload(page, "#id_second", get_path("roles.csv"))
    submit_confirm(page)
    expect_normalized(
        page,
        page.locator("#one"),
        "Loading performed, see logs Proceed Logs OK - Created plott OK - Plot role characcter plott",
    )
    page.get_by_role("link", name="Proceed").click()
    expect_normalized(page, page.locator("#one"), "plott conceptt textt")
    page.locator(".fa-edit").click()
    page.get_by_role("cell", name="Show This text will be added").get_by_role("link").click()
    expect_normalized(page, page.locator("#id_char_role_2_tr"), "#2 characcter")
    expect_normalized(page, page.locator("#id_char_role_2_tr"), "super start")
    go_to(page, live_server, "/test/manage/plots/")
    check_download(page, "Download")


def quest_trait(page: Any) -> None:
    sidebar(page, "Quest")
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    page.get_by_role("link", name="Quest type").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("bhbh")
    submit_confirm(page)
    sidebar(page, "Quest")
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    upload(page, "#id_first", get_path("quest.csv"))
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Loading performed, see logs Proceed Logs OK - Created questt")
    page.get_by_role("link", name="Proceed").click()
    expect_normalized(page, page.locator("#one"), "Q1 questt bhbh presenttation ttext")
    check_download(page, "Download")
    sidebar(page, "Traits")
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    upload(page, "#id_first", get_path("trait.csv"))
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Loading performed, see logs Proceed Logs OK - Created traitt")
    page.get_by_role("link", name="Proceed").click()
    expect_normalized(page, page.locator("#one"), "T1 traitt Q1 questt ppresentation teeeext")
    check_download(page, "Download")


def registrations(page: Any) -> None:
    page.get_by_role("link", name="Registrations").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    upload(page, "#id_first", get_path("registration.csv"))
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), " OK - Created User Test")
    page.get_by_role("link", name="Proceed").click()
    expect_normalized(page, page.locator("#one"), "User Test #2 characcter")
    check_download(page, "Download")


def reg_form(page: Any) -> None:
    sidebar(page, "Form")
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    upload(page, "#id_first", get_path("reg-questions.csv"))
    page.locator("#id_second").click()
    upload(page, "#id_second", get_path("reg-options.csv"))
    submit_confirm(page)
    expect_normalized(
        page,
        page.locator("#one"),
        "Loading performed, see logs Proceed Logs OK - Created tbmobw OK - Created qmhcuf OK - Created holdmf OK - Created lyucez OK - Created bamkzw OK - Created npyrxd OK - Created rdtbgg OK - Created qkcyjr OK - Created fjxkum",
    )
    page.get_by_role("link", name="Proceed").click()
    expect_normalized(
        page,
        page.locator("#one"),
        "tbmobw npyrxd Multiple choice Optional npyrxd | rdtbgg qmhcuf rdtbgg Multi-line text Mandatory holdmf qkcyjr Single-line text Disabled lyucez fjxkum Advanced text editor Hidden bamkzw fzynqq Single choice Optional qkcyjr | fjxkum",
    )
    check_download(page, "Download")


def characters(page: Any) -> None:
    sidebar(page, "Characters")
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    upload(page, "#id_first", get_path("character.csv"))
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), " OK - Created characcter")
    page.get_by_role("link", name="Proceed").click()
    expect_normalized(
        page, page.locator("#one"), "#1 Test Character Test Teaser Test Text #2 characcter trg poor ertd fewr"
    )
    check_download(page, "Download")


def factions(page: Any) -> None:
    page.get_by_role("link", name="Factions").click()
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    upload(page, "#id_first", get_path("faction.csv"))
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), " OK - Created facction")
    page.get_by_role("link", name="Proceed").click()
    expect_normalized(page, page.locator("#one"), "facction Primary gh asd oeir sdf")
    check_download(page, "Download")


def char_form(page: Any) -> None:
    sidebar(page, "Sheet")
    page.get_by_role("link", name="Upload").click()
    check_download(page, "Download example template")
    upload(page, "#id_first", get_path("char-questions.csv"))
    upload(page, "#id_second", get_path("char-options.csv"))
    submit_confirm(page)
    expect_normalized(
        page,
        page.locator("#one"),
        "Loading performed, see logs Proceed Logs OK - Created bibi OK - Created baba OK - Created wer OK - Created asd OK - Created poi OK - Created huhu OK - Created trtr OK - Created rrrrrr OK - Created tttttt",
    )
    page.get_by_role("link", name="Proceed").click()
    expect_normalized(
        page,
        page.locator("#one"),
        "Name Name Presentation Presentation Text Sheet Faction Factions Hidden bibi baba Multiple choice Searchable huhu | trtr",
    )
    check_download(page, "Download")
    page.get_by_role("link", name="Plot", exact=True).click()
    expect_normalized(
        page, page.locator("#one"), "Name Name Concept Presentation Text Sheet wer fghj Single-line text Hidden"
    )
    page.get_by_role("link", name="Faction", exact=True).click()
    expect_normalized(
        page, page.locator("#one"), "Name Name Presentation Presentation Text Sheet baba bebe Multi-line text Private"
    )
    page.locator("#one").get_by_role("link", name="Quest").click()
    expect_normalized(
        page,
        page.locator("#one"),
        "Name Name Presentation Presentation Text Sheet asd kloi Advanced text editor Public",
    )
    page.get_by_role("link", name="Trait", exact=True).click()
    expect_normalized(
        page,
        page.locator("#one"),
        "Name Name Presentation Presentation Text Sheet poi rweerw Single choice Public rrrrrr | tttttt",
    )

def get_path(file: Any) -> Any:
    return Path(__file__).parent.parent / "resources" / "test_upload" / file
