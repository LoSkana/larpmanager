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

from larpmanager.tests.utils import go_to, login_orga, expect_normalized_text

pytestmark = pytest.mark.e2e


def test_orga_form_writing_config(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "test/1/manage")

    feature_fields(page)

    feature_fields2(page)

    form_other_writing(page)


def feature_fields(page: Any) -> None:
    # set feature
    page.locator("#orga_features").get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Characters").check()
    page.get_by_role("button", name="Confirm").click()

    # reorder test
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    expect_normalized_text(page.locator("#one"), "Name Name Presentation Presentation Text Sheet")
    page.locator('[id="u3"]').get_by_role("link", name="").click()
    expect_normalized_text(page.locator("#one"), "Name Name Text Sheet Presentation Presentation")

    # add config fields - title
    page.get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Writing ").click()
    page.locator("#id_writing_title").check()
    page.get_by_role("button", name="Confirm").click()

    # check
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    expect_normalized_text(page.locator("#one"), "Name Name Text Sheet Presentation Presentation Title Title Hidden")

    # add config fields - cover, assigned
    page.get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Writing ").click()
    page.locator("#id_writing_title").uncheck()
    page.locator("#id_writing_cover").check()
    page.locator("#id_writing_assigned").check()
    page.get_by_role("button", name="Confirm").click()

    # check
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    expect_normalized_text(
        page.locator("#one"),
        "Name Name Text Sheet Presentation Presentation Assigned Assigned Hidden Cover Cover Hidden",
    )


def feature_fields2(page: Any) -> None:
    # add config hide, assigned
    page.get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name="Writing ").click()
    page.locator("#id_writing_assigned").uncheck()
    page.locator("#id_writing_cover").uncheck()
    page.locator("#id_writing_hide").check()
    page.locator("#id_writing_assigned").check()
    page.get_by_role("button", name="Confirm").click()

    # check
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    expect_normalized_text(
        page.locator("#one"), "Name Name Text Sheet Presentation Presentation Assigned Assigned Hidden Hide Hide Hidden"
    )

    # set experience point
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Experience points").check()
    page.get_by_role("button", name="Confirm").click()

    # add field computed
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_typ").select_option("c")
    page.locator("#id_name").click()
    page.locator("#id_name").fill("comp")
    page.get_by_role("button", name="Confirm").click()

    # test save
    page.get_by_role("link", name="Event").click()
    page.get_by_role("button", name="Confirm").click()

    # check it has not been deleted
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    expect_normalized_text(
        page.locator("#one"),
        "Name Name Text Sheet Presentation Presentation Assigned Assigned Hidden Hide Hide Hidden comp Computed Private",
    )

    # remove px
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Experience points").uncheck()
    page.get_by_role("button", name="Confirm").click()

    # check
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    expect_normalized_text(
        page.locator("#one"), "Name Name Text Sheet Presentation Presentation Assigned Assigned Hidden Hide Hide Hidden"
    )


def form_other_writing(page: Any) -> None:
    # add other writing elements
    page.get_by_role("link", name="Features").click()
    page.get_by_role("checkbox", name="Plots").check()
    page.get_by_role("checkbox", name="Factions").check()
    page.get_by_role("checkbox", name="Quests and Traits").check()
    page.get_by_role("button", name="Confirm").click()

    # check
    page.locator("#orga_character_form").get_by_role("link", name="Form").click()
    page.get_by_role("link", name="Plot", exact=True).click()
    page.get_by_role("link", name="Character", exact=True).click()
    expect_normalized_text(
        page.locator("#one"),
        "Name Name Text Sheet Presentation Presentation Assigned Assigned Hidden Hide Hide Hidden Faction Factions Hidden",
    )
    page.get_by_role("link", name="Plot", exact=True).click()
    expect_normalized_text(page.locator("#one"), "Name Name Concept Presentation Text Sheet")
    page.get_by_role("link", name="Faction", exact=True).click()
    expect_normalized_text(page.locator("#one"), "Name Name Presentation Presentation Text Sheet")
    page.locator("#one").get_by_role("link", name="Quest").click()
    expect_normalized_text(page.locator("#one"), "Name Name Presentation Presentation Text Sheet")
    page.get_by_role("link", name="Trait", exact=True).click()
    expect_normalized_text(page.locator("#one"), "Name Name Presentation Presentation Text Sheet")
