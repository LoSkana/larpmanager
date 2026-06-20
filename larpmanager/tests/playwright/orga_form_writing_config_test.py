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
Test: Writing form configuration with dynamic fields.
Verifies character/plot/faction/quest/trait form field reordering, configuration-based
fields (title, cover, assigned, hide), computed fields, and form persistence.
"""

import re
from typing import Any

import pytest

from larpmanager.tests.utils import go_to, login_orga, expect_normalized, submit_confirm, sidebar, get_modal_iframe, \
    save_modal, click_and_wait_question

pytestmark = pytest.mark.e2e


def test_orga_form_writing_config(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "test/1/manage")

    feature_fields(page)

    feature_fields2(page, live_server)

    form_other_writing(page)


def feature_fields(page: Any) -> None:
    # set feature
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Characters").check()
    submit_confirm(page)

    # reorder test
    sidebar(page, "Sheet")
    expect_normalized(page, page.locator("#one"), "Name Name Presentation Presentation Text Sheet")
    page.locator('tr[id="u3"] td.reorder-handle').drag_to(
        page.locator('tr[id="u3"]').locator("xpath=preceding-sibling::tr[1]")
    )
    page.wait_for_timeout(300)
    expect_normalized(page, page.locator("#one"), "Name Name Text Sheet Presentation Presentation")

    # add config fields - title
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Characters ")).click()
    page.locator("#id_writing_title").check()
    submit_confirm(page)

    # check
    sidebar(page, "Sheet")
    expect_normalized(page, page.locator("#one"), "Name Name Text Sheet Presentation Presentation Title Title Hidden")

    # add config fields - cover, assigned
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Characters")).click()
    page.locator("#id_writing_title").uncheck()
    page.locator("#id_writing_cover").check()
    page.locator("#id_writing_assigned").check()
    submit_confirm(page)

    # check
    sidebar(page, "Sheet")
    expect_normalized(page,
        page.locator("#one"),
        "Name Name Text Sheet Presentation Presentation Assigned Assigned Hidden Cover Cover Hidden",
    )


def feature_fields2(page: Any, live_server: Any) -> None:
    # add config hide, assigned
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Characters")).click()
    page.locator("#id_writing_assigned").uncheck()
    page.locator("#id_writing_cover").uncheck()
    page.locator("#id_writing_hide").check()
    page.locator("#id_writing_assigned").check()
    submit_confirm(page)

    # check
    sidebar(page, "Sheet")
    expect_normalized(page,
        page.locator("#one"), "Name Name Text Sheet Presentation Presentation Assigned Assigned Hidden Hide Hide Hidden"
    )

    # set experience point
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Experience points").check()
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Experience points\s.+")).click()
    page.locator("#id_exp_rules").check()
    submit_confirm(page)

    # add field computed
    sidebar(page, "Sheet")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("c")
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("comp")
    save_modal(page, edit_iframe)

    # test save
    page.get_by_role("link", name="Event").click()
    submit_confirm(page)

    # check it has not been deleted
    sidebar(page, "Sheet")
    expect_normalized(page,
        page.locator("#one"),
        "Name Name Text Sheet Presentation Presentation Assigned Assigned Hidden Hide Hide Hidden comp Computed Private",
    )

    # remove experience
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Experience points").uncheck()
    submit_confirm(page)

    # check
    sidebar(page, "Sheet")
    expect_normalized(page,
        page.locator("#one"), "Name Name Text Sheet Presentation Presentation Assigned Assigned Hidden Hide Hide Hidden"
    )


def form_other_writing(page: Any) -> None:
    # add other writing elements
    sidebar(page, "Features")
    page.get_by_role("checkbox", name="Plots").check()
    page.get_by_role("checkbox", name="Factions").check()
    page.get_by_role("checkbox", name="Quests and Traits").check()
    submit_confirm(page)

    # check
    sidebar(page, "Sheet")
    expect_normalized(page,
        page.locator("#one"),
        "Name Name Text Sheet Presentation Presentation Assigned Assigned Hidden Hide Hide Hidden Faction Factions Hidden",
    )
    page.get_by_role("link", name="Plot", exact=True).click()
    expect_normalized(page, page.locator("#one"), "Name Name Concept Presentation Text Sheet")
    page.get_by_role("link", name="Faction", exact=True).click()
    expect_normalized(page, page.locator("#one"), "Name Name Presentation Presentation Text Sheet")
    page.locator("#one").get_by_role("link", name="Quest").click()
    expect_normalized(page, page.locator("#one"), "Name Name Presentation Presentation Text Sheet")
    page.get_by_role("link", name="Trait", exact=True).click()
    expect_normalized(page, page.locator("#one"), "Name Name Presentation Presentation Text Sheet")
