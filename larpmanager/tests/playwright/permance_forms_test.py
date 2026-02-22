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
Test: Persistence of form configurations.
Verifies that organization and event roles, features, configuration settings,
and preferences persist correctly across page reloads and navigation.
"""
import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import just_wait, check_feature, go_to, login_orga, submit_confirm, expect_normalized

pytestmark = pytest.mark.e2e


def test_permanence_form(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/manage")

    check_exe_roles(page)

    check_exe_features(page)

    check_exe_config(page)

    go_to(page, live_server, "/test/manage/")

    check_orga_roles(page)

    check_orga_config(page)

    check_orga_features(page)

    check_orga_preferences(page)

    check_orga_visibility(page)


def check_orga_visibility(page: Any) -> None:
    page.get_by_role("link", name="Event").click()
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Writing ")).click()
    page.locator("#id_writing_field_visibility").check()
    submit_confirm(page)
    page.get_by_role("link", name="Event", exact=True).click()
    page.locator("#id_form2-show_character_0").check()
    page.locator("#id_form2-show_character_2").check()
    submit_confirm(page)
    page.get_by_role("link", name="Event", exact=True).click()
    expect(page.locator("#id_form2-show_character_0")).to_be_checked()
    expect(page.locator("#id_form2-show_character_2")).to_be_checked()
    expect(page.locator("#id_form2-show_character_1")).not_to_be_checked()


def check_orga_preferences(page: Any) -> None:
    page.get_by_role("link", name="Preferences", exact=True).click()
    page.locator("#id_open_registration_1_0").check()
    page.locator("#id_open_registration_1_2").check()
    submit_confirm(page)
    page.get_by_role("link", name="Preferences", exact=True).click()
    expect(page.locator("#id_open_registration_1_0")).to_be_checked()
    expect(page.locator("#id_open_registration_1_1")).not_to_be_checked()
    expect(page.locator("#id_open_registration_1_2")).to_be_checked()
    expect(page.locator("#id_open_registration_1_3")).not_to_be_checked()
    page.get_by_role("link", name="Features").first.click()
    check_feature(page, "Characters")
    submit_confirm(page)
    page.get_by_role("link", name="Preferences", exact=True).click()
    page.locator("#id_open_character_1_0").check()
    page.get_by_text("Stats").click()
    page.locator("#id_open_character_1_2").check()
    submit_confirm(page)
    page.get_by_role("link", name="Preferences", exact=True).click()
    expect(page.locator("#id_open_character_1_0")).to_be_checked()
    expect(page.locator("#id_open_character_1_1")).not_to_be_checked()
    expect(page.locator("#id_open_character_1_2")).to_be_checked()


def check_orga_features(page: Any) -> None:
    page.get_by_role("link", name="Features").first.click()
    checked = ["Participant cancellation", "Character customization", "Secret link", "Sections"]
    for s in checked:
        check_feature(page, s)

    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Now you can set customization options")
    expect_normalized(page,
        page.locator("#one"), "You have activated the following features, for each here's the links to follow"
    )
    page.get_by_role("link", name="Features").first.click()
    _check_checkboxes(checked, page)


def check_orga_config(page: Any) -> None:
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Visualisation ")).click()
    page.locator("#id_show_shortcuts_mobile").check()
    page.get_by_text("If checked: Show summary page").click()
    page.locator("#id_show_limitations").check()
    submit_confirm(page)
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_text("Email notifications Disable").click()
    page.get_by_text("If checked, options no longer").click()
    page.get_by_role("link", name=re.compile(r"^Registrations ")).click()
    page.get_by_role("link", name=re.compile(r"^Visualisation ")).click()
    expect(page.locator("#id_show_shortcuts_mobile")).to_be_checked()
    expect(page.locator("#id_show_export")).not_to_be_checked()
    expect(page.locator("#id_show_limitations")).to_be_checked()


def check_orga_roles(page: Any) -> None:
    page.locator("#orga_roles").get_by_role("link", name="Roles").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("testona")
    page.locator("#id_name").press("Tab")
    page.get_by_role("searchbox").fill("org")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    checked = ["Event", "Configuration", "Texts", "Navigation"]
    for s in checked:
        check_feature(page, s)
    submit_confirm(page)
    expect_normalized(page, page.locator('[id="u2"]'), "Event (Event, Configuration), Appearance (Texts, Navigation)")
    page.get_by_role("row", name="testona Admin Test Event (").locator(".fa-edit").click()
    _check_checkboxes(checked, page)


def _check_checkboxes(checked: Any, page: Any, skip_first: Any = False) -> None:
    for s in checked:
        expect(page.get_by_label(s)).to_be_checked()
    all_checkboxes = page.locator("input[type=checkbox]")
    count = all_checkboxes.count()
    start = 0
    if skip_first:
        start = 1
    for i in range(start, count):
        label = all_checkboxes.nth(i).evaluate("el => el.labels[0]?.innerText.trim()")
        if label not in checked:
            expect(all_checkboxes.nth(i)).not_to_be_checked()


def check_exe_config(page: Any) -> None:
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Interface ")).click()
    page.locator("#id_calendar_past_events").check()
    page.locator("#id_calendar_authors").check()
    page.locator("#id_calendar_tagline").check()
    submit_confirm(page)
    page.locator("#exe_config").get_by_role("link", name="Configuration").click()
    page.get_by_role("link", name=re.compile(r"^Interface ")).click()
    expect(page.locator("#id_calendar_past_events")).to_be_checked()
    expect(page.locator("#id_calendar_website")).not_to_be_checked()
    expect(page.locator("#id_calendar_where")).not_to_be_checked()
    expect(page.locator("#id_calendar_authors")).to_be_checked()
    expect(page.locator("#id_calendar_genre")).not_to_be_checked()
    expect(page.locator("#id_calendar_tagline")).to_be_checked()


def check_exe_features(page: Any) -> None:
    page.get_by_role("link", name="Features").first.click()

    checked = ["Template", "Treasurer", "Membership", "Badge"]
    for s in checked:
        check_feature(page, s)

    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Now you can create event templates")
    page.get_by_role("link", name="Features").first.click()
    _check_checkboxes(checked, page, True)


def check_exe_roles(page: Any) -> None:
    page.locator("#exe_roles").get_by_role("link", name="Roles").click()
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("test")
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("org")
    page.get_by_role("option", name="Admin Test - orga@test.it").click()
    checked = ["Organization", "Configuration", "Events", "Texts"]
    for s in checked:
        check_feature(page, s)
    submit_confirm(page)
    expect(page.locator('[id="u2"]')).to_contain_text(
        "Organization (Organization, Configuration), Events (Events), Appearance (Texts)"
    )
    page.locator('[id="u2"]').locator(".fa-edit").click()
    _check_checkboxes(checked, page)
