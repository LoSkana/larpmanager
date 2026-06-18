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
Test: Plot progress step preservation and $unimportant stats.
Verifies that editing a plot does not reset its progress step (Bug 1) and that
the $unimportant prefix is correctly reflected in the plot list Important column (Bug 2).
"""

import re
from typing import Any

import pytest

from larpmanager.tests.utils import (
    check_feature,
    fill_tinymce,
    go_to,
    just_wait,
    login_orga,
    sidebar,
    submit_confirm,
    get_modal_iframe, save_modal,
)

pytestmark = pytest.mark.e2e


def test_plot_progress_preservation(pw_page: Any) -> None:
    """Editing a plot must not reset its progress step to the first step."""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "test/1/manage")

    # Enable Plots and Progress features
    sidebar(page, "Features")
    check_feature(page, "Characters")
    check_feature(page, "Plots")
    check_feature(page, "Progress")
    submit_confirm(page)

    # Add a "progress" question to the plot sheet
    sidebar(page, "Sheet")
    page.get_by_role("link", name="Plot", exact=True).click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("progress")
    edit_iframe.locator("#id_name").fill("Status")
    save_modal(page, edit_iframe)

    # Create two progress steps so we can pick a non-first step
    sidebar(page, "Progress")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Draft")
    save_modal(page, edit_iframe)
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Final")
    save_modal(page, edit_iframe)

    # Create a plot and set progress to "Final" (the second step)
    sidebar(page, "Plots")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Progress Test Plot")
    edit_iframe.locator("#id_progress").select_option(label="2 - Final")
    save_modal(page, edit_iframe)

    # Edit the plot (name change only) and save
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    just_wait(edit_iframe)

    progress_before = edit_iframe.locator("#id_progress").evaluate(
        "el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : ''"
    )
    assert "Final" in progress_before, f"Expected 'Final' selected before edit, got '{progress_before}'"

    edit_iframe.locator("#id_name").fill("Progress Test Plot Renamed")
    save_modal(page, edit_iframe)

    # Re-open the edit form and verify progress is still "Final"
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    just_wait(edit_iframe)

    progress_after = edit_iframe.locator("#id_progress").evaluate(
        "el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : ''"
    )
    assert "Final" in progress_after, f"Expected 'Final' after name-only edit, got '{progress_after}'"


def test_plot_unimportant_stats(pw_page: Any) -> None:
    """$unimportant prefix must reduce the Important count in the plot list."""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    go_to(page, live_server, "test/1/manage")

    # Enable Characters and Plots features
    sidebar(page, "Features")
    check_feature(page, "Characters")
    check_feature(page, "Plots")
    submit_confirm(page)

    # Enable the "Unimportant" writing config
    page.get_by_role("link", name="Configuration").first.click()
    page.get_by_role("link", name=re.compile(r"^Characters")).click()
    page.locator("#id_writing_unimportant").check()
    submit_confirm(page)

    # Create a second character (first already exists as "Test Character")
    sidebar(page, "Characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Minor NPC")
    save_modal(page, edit_iframe)

    # Create a plot with two characters:
    # - Test Character: important role
    # - Minor NPC: $unimportant role
    sidebar(page, "Plots")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Stats Test Plot")

    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.fill("Test")
    option = edit_iframe.get_by_role("option", name="Test Character")
    option.wait_for(state="visible")
    option.click()
    edit_iframe.wait_for_timeout(3000)
    fill_tinymce(edit_iframe, "ch_1", "important role")

    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.fill("Minor")
    option = edit_iframe.get_by_role("option", name="Minor NPC")
    option.wait_for(state="visible")
    option.click()
    edit_iframe.wait_for_timeout(3000)
    fill_tinymce(edit_iframe, "ch_2", "$unimportant minor role")

    save_modal(page, edit_iframe)

    # Show Characters column then Stats to make stats-characters cells visible in DOM
    page.locator("#one").get_by_role("link", name="Characters").click()
    just_wait(page)
    page.locator("#one").get_by_role("link", name="Stats").click()
    just_wait(page)

    # Verify count = 2 and important = 1
    stats_cells = page.locator("#one td.stats")
    count_text = (
        page.locator("table.writing_list tbody tr")
        .nth(0)
        .locator("td")
        .nth(8)
        .inner_text()
    )
    important_text = (
        page.locator("table.writing_list tbody tr")
        .nth(0)
        .locator("td")
        .nth(9)
        .inner_text()
    )

    assert count_text == "2", f"Expected count=2, got '{count_text}'"
    assert important_text == "1", f"Expected important=1, got '{important_text}'"
