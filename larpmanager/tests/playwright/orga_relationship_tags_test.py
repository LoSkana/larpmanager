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

"""Test: Relationship tags.
Verifies relationship tags can be managed (create/edit/delete) and that applying a tag
to one character's relationship also applies it to the other character's relationship
(symmetric application), as needed for casting purposes. The feature is gated by a
config toggle (not a standalone Feature) that lives under the Relationships feature.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    check_feature,
    expect_normalized,
    fill_tinymce,
    get_modal_iframe,
    go_to,
    login_orga,
    save_modal,
    sidebar,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_relationship_tags(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Features")
    check_feature(page, "Characters")
    check_feature(page, "Relationships")
    submit_confirm(page)

    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Relationships")).click()
    page.locator("#id_writing_relationship_tags").check()
    submit_confirm(page)

    create_tag(page)

    create_relationship(live_server, page)

    apply_tag(page)

    check_symmetric(live_server, page)

    check_stats(live_server, page)

    create_relationship_with_tag(live_server, page)

    check_character_list_stats(live_server, page)

    check_tagged_empty_relationship_survives(live_server, page)

    remove_tag(page)

    check_removed_everywhere(live_server, page)


def tag_checkbox(edit_iframe: Any, tag_name: str) -> Any:
    """Return a tag checkbox, waiting for the relationship rows to be rendered first.

    For an existing relationship the row comes from the template, for a newly added one it is
    appended by the relationship helper script, so in both cases it has to be waited for.
    """
    checkbox = edit_iframe.get_by_label(tag_name)
    checkbox.wait_for(state="visible")
    return checkbox


def set_tag(edit_iframe: Any, tag_name: str, *, checked: bool) -> None:
    """Toggle a relationship tag, by clicking the label that wraps (and covers) the checkbox."""
    checkbox = tag_checkbox(edit_iframe, tag_name)
    if checkbox.is_checked() != checked:
        edit_iframe.locator("label.rel_tag_checkbox").filter(has_text=tag_name).click()
    expect(checkbox).to_be_checked(checked=checked)


def create_tag(page: Any) -> None:
    sidebar(page, "Relationship tags")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Love")
    save_modal(page, edit_iframe)
    expect_normalized(page, page.locator("#one"), "Love")


def create_relationship(live_server: Any, page: Any) -> None:
    # create second character with a direct relationship to the test character
    sidebar(page, "Characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("prova")
    edit_iframe.locator("#select2-new_rel_select-container").click()
    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.fill("tes")
    option = edit_iframe.get_by_role("option", name="Test Character")
    option.wait_for(state="visible")
    option.click()
    fill_tinymce(edit_iframe, "rel_u1", "ciaaoooooo")
    save_modal(page, edit_iframe)


def apply_tag(page: Any) -> None:
    # reopen the character, now the relationship exists so the tags checkbox is available
    sidebar(page, "Characters")
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)

    set_tag(edit_iframe, "Love", checked=True)

    save_modal(page, edit_iframe)


def check_symmetric(live_server: Any, page: Any) -> None:
    # tag must be checked when editing directly (prova -> Test Character)...
    sidebar(page, "Characters")
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(tag_checkbox(edit_iframe, "Love")).to_be_checked()

    # ...and mirrored onto the inverse relationship (Test Character -> prova)
    go_to(page, live_server, "/test/manage/characters/")
    page.locator('[id="u1"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(tag_checkbox(edit_iframe, "Love")).to_be_checked()


def check_stats(live_server: Any, page: Any) -> None:
    # the tag list shows a usage count: one relationship row per direction, both tagged
    go_to(page, live_server, "/test/manage/")
    sidebar(page, "Relationship tags")
    row = page.locator("#relationship_tags tbody tr").filter(has_text="Love")
    expect(row).to_have_count(1)
    expect_normalized(page, row, "Love")
    expect_normalized(page, row, "2")


def create_relationship_with_tag(live_server: Any, page: Any) -> None:
    # tags must be selectable while creating a brand-new relationship, before the first save
    sidebar(page, "Characters")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("terza")
    edit_iframe.locator("#select2-new_rel_select-container").click()
    searchbox = edit_iframe.get_by_role("searchbox")
    searchbox.fill("tes")
    option = edit_iframe.get_by_role("option", name="Test Character")
    option.wait_for(state="visible")
    option.click()

    set_tag(edit_iframe, "Love", checked=True)

    save_modal(page, edit_iframe)


def _tag_stat_cell(page: Any, row_uuid: str, tag_name: str) -> str:
    """Read the per-tag stats column value for a character row (column found by header text)."""
    return page.evaluate(
        """([rowUuid, tagName]) => {
            const row = document.getElementById(rowUuid);
            const cells = row.querySelectorAll('td');
            const headerRows = Array.from(document.querySelectorAll('table.writing_list thead tr'));
            const headerRow = headerRows.find(tr => tr.children.length === cells.length);
            if (!headerRow) return null;
            const colIndex = Array.from(headerRow.children).findIndex(th => {
                const title = th.querySelector('.dt-column-title') || th;
                return title.textContent.trim() === tagName;
            });
            const cell = cells[colIndex];
            return cell ? cell.textContent.trim() : null;
        }""",
        [row_uuid, tag_name],
    )


def check_character_list_stats(live_server: Any, page: Any) -> None:
    # per-tag stats column, reusing the "Relationships"+"Stats" toggle combo (like plots'
    # important/unimportant columns): new relationship (terza) and its mirror (Test Character)
    # must both show the tag count, right after creation
    go_to(page, live_server, "/test/manage/characters/")
    page.get_by_role("link", name="Relationships", exact=True).click()
    page.get_by_role("link", name="Stats", exact=True).click()
    assert _tag_stat_cell(page, "u3", "Love") == "1"
    assert _tag_stat_cell(page, "u1", "Love") == "2"


def check_tagged_empty_relationship_survives(live_server: Any, page: Any) -> None:
    # terza's relationship has no text, only a tag: re-saving it must keep it (and its mirror)
    # alive instead of dropping it as an empty relationship and creating a duplicate
    go_to(page, live_server, "/test/manage/characters/")
    page.locator('[id="u3"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(tag_checkbox(edit_iframe, "Love")).to_be_checked()
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/manage/characters/")
    page.get_by_role("link", name="Relationships", exact=True).click()
    page.get_by_role("link", name="Stats", exact=True).click()
    assert _tag_stat_cell(page, "u3", "Love") == "1"
    assert _tag_stat_cell(page, "u1", "Love") == "2"


def remove_tag(page: Any) -> None:
    # uncheck the tag on the direct side (prova -> Test Character)
    sidebar(page, "Characters")
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    set_tag(edit_iframe, "Love", checked=False)
    save_modal(page, edit_iframe)


def check_removed_everywhere(live_server: Any, page: Any) -> None:
    # the removed direct checkbox is unchecked...
    sidebar(page, "Characters")
    page.locator('[id="u2"]').locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    expect(tag_checkbox(edit_iframe, "Love")).not_to_be_checked()

    # ...the mirror is removed too, without touching the unrelated tag from terza's relationship
    # (also checks the other character's cached stats got refreshed, not just prova's)
    go_to(page, live_server, "/test/manage/characters/")
    page.get_by_role("link", name="Relationships", exact=True).click()
    page.get_by_role("link", name="Stats", exact=True).click()
    assert _tag_stat_cell(page, "u2", "Love") == "0"
    assert _tag_stat_cell(page, "u1", "Love") == "1"
