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

"""Guide video: write characters, then organize them with factions and plots."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    create_event,
    feature_checkbox,
    open_menu,
    open_new,
    pick_character,
    prepare_data,
    save_modal,
)
from larpmanager.tests.utils import login_orga

if TYPE_CHECKING:
    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Character fields, factions and plots"
PACE = 0.7
RICH_TEXT = True

EVENT = "Vaelmoor: The Sundering"
FIELD = "Court Title"
PUBLIC_VISIBILITY = "c"
FIRST_CHARACTER = "Lucian Thorne"
SECOND_CHARACTER = "Aurelio Vance"
TITLE_INPUT = 'input[id^="id_que_"], textarea[id^="id_que_"]'
FIRST_TITLE = "High Lord of Ashblood"
SECOND_TITLE = "Heir of Ashblood"
CHARACTER_TEXT = "You have ruled the Ashblood Court for three centuries."
FACTION = "The Ashblood Court"
FACTION_TEXT = "The oldest court of Vaelmoor, ruled by blood."
PLOT = "The Succession"
PLOT_TEXT = "The Ashblood Court must choose an heir before dawn."
FIRST_ROLE = "Aurelio plans to challenge you tonight."
SECOND_ROLE = "Tonight you finally claim the throne."


def write_rich_text(director: Director, modal: Any, field: str, text: str, index: int = 0) -> None:
    """Open a collapsed text editor, found by the start of its id, and type into it."""
    director.click(modal.locator(f'a.my_toggle[tog^="f_{field}"]').nth(index), settle=0.8)
    director.type(modal.frame_locator(f'iframe[id^="{field}"]').nth(index).locator("body"), text)


def test_writing_video(director: Director) -> None:
    """Record character writing, factions and plots from the organizer side."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=30)
    prepare_data("Vaelmoor Chronicle")
    login_orga(page, director.base_url)
    director.goto("/manage/events")
    director.start()

    director.step("Step 1: create the event")
    director.say("Create the event: character tools are ready")
    create_event(director, EVENT, start)

    director.step("Step 2: enable factions and plots")
    director.say("Activate them in the event features")
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "Factions"))
    director.check(feature_checkbox(page, "Plots"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 3: design the character form")
    director.say("Add fields, and choose who can see each one")
    open_menu(director, "Sheet")
    modal = open_new(director)
    director.select(modal.locator("#id_typ"), "t")
    director.type(modal.locator("#id_name"), FIELD)
    director.select(modal.locator("#id_visibility"), PUBLIC_VISIBILITY)
    save_modal(director, modal)
    director.say("Drag a field to change its position")
    rows = page.locator("#character_questions tbody tr")
    new_field = rows.filter(has_text=FIELD)
    expect(new_field).to_be_visible()
    director.drag(new_field.locator("td.reorder-handle"), rows.nth(1))
    expect(rows.nth(1)).to_contain_text(FIELD)
    director.spotlight(rows.nth(1), 2.0)

    director.step("Step 4: write characters")
    director.say("Fill in the fields of each character")
    open_menu(director, "Characters")
    modal = open_new(director)
    expect(modal.locator('label[id^="lbl_id_"]').nth(1)).to_contain_text(FIELD)
    director.type(modal.locator("#id_name"), FIRST_CHARACTER)
    director.type(modal.locator(TITLE_INPUT), FIRST_TITLE)
    director.say("Write directly in the system, with automatic saving")
    write_rich_text(director, modal, "id_text", CHARACTER_TEXT)
    save_modal(director, modal)
    modal = open_new(director)
    director.fill(modal.locator("#id_name"), SECOND_CHARACTER)
    director.type(modal.locator(TITLE_INPUT), SECOND_TITLE)
    save_modal(director, modal)
    director.say("Every saved text stays available as a version")
    expect(page.locator("tr", has_text=SECOND_CHARACTER)).to_be_visible()
    first_row = page.locator("tr", has_text=FIRST_CHARACTER)
    director.click(first_row.locator(".fa-file-alt"), settle=1.0)
    expect(page.locator("#one")).to_contain_text(CHARACTER_TEXT)
    director.hold(2.5)

    director.step("Step 5: create factions")
    director.say("Group characters into factions")
    open_menu(director, "Factions")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), FACTION)
    write_rich_text(director, modal, "id_text", FACTION_TEXT)
    pick_character(director, modal, FIRST_CHARACTER)
    pick_character(director, modal, SECOND_CHARACTER)
    save_modal(director, modal)
    expect(page.locator("tr", has_text=FACTION)).to_be_visible()
    director.hold(2.0)

    director.step("Step 6: create plots")
    director.say("Create a plot for the event")
    open_menu(director, "Plots")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), PLOT)
    director.say("Plot text is shared by every linked character")
    write_rich_text(director, modal, "id_text", PLOT_TEXT)
    director.say("Link characters to plots, with their role in each")
    pick_character(director, modal, FIRST_CHARACTER)
    pick_character(director, modal, SECOND_CHARACTER)
    write_rich_text(director, modal, "ch_", FIRST_ROLE, index=0)
    write_rich_text(director, modal, "ch_", SECOND_ROLE, index=1)
    save_modal(director, modal)
    plot_row = page.locator("tr", has_text=PLOT)
    expect(plot_row).to_be_visible()
    director.say("Each plot shows the characters involved")
    director.click(page.locator("a.table_toggle", has_text="Characters"), settle=1.0)
    expect(plot_row).to_contain_text(FIRST_CHARACTER)
    expect(plot_row).to_contain_text(SECOND_CHARACTER)
    director.spotlight(plot_row, 2.5)

    director.say("The sheet combines fields, texts, factions and plots")
    open_menu(director, "Characters")
    first_row = page.locator("tr", has_text=FIRST_CHARACTER)
    director.click(first_row.locator(".fa-book-open"), settle=1.0)
    sheet = page.locator(".sheet")
    for content in (FIRST_TITLE, CHARACTER_TEXT, FACTION, FACTION_TEXT, PLOT, PLOT_TEXT, FIRST_ROLE):
        expect(sheet).to_contain_text(content)
    director.spotlight(sheet, 4.0)

    director.stop()
