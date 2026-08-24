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
Test: Handout and handout template creation and visualization.
Tests HandoutTemplate creation (name, css), Handout creation (name, text, template
assignment), organizer preview rendering, and the public external-access PDF link.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    check_feature,
    fill_tinymce,
    get_modal_iframe,
    go_to,
    login_orga,
    logout,
    save_modal,
    sidebar,
    submit_confirm,
)

pytestmark = pytest.mark.e2e


def test_orga_handout(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    # ========== SECTION 1: Enable feature ==========
    login_orga(page, live_server)
    go_to(page, live_server, "test/manage")
    sidebar(page, "Features")
    check_feature(page, "Characters")
    check_feature(page, "Handout")
    submit_confirm(page)

    # ========== SECTION 2: Create Handout Template ==========
    go_to(page, live_server, "test/manage/handout_templates/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Template One")
    edit_iframe.locator("#id_css").fill("body { color: red; }")
    save_modal(page, edit_iframe)

    expect(page.locator("#one")).to_contain_text("Template One")

    # ========== SECTION 3: Create Handout, assigned to the template ==========
    go_to(page, live_server, "test/manage/handouts/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_template").select_option(label="Template One")
    edit_iframe.locator("#id_name").fill("Handout One")
    fill_tinymce(edit_iframe, "id_text", "Handout One content")
    save_modal(page, edit_iframe)

    expect(page.locator("#one")).to_contain_text("Handout One")

    # ========== SECTION 4: Visualize the handout as organizer (PDF view) ==========
    row = page.locator("#handouts tbody tr").filter(has_text="Handout One")
    view_href = row.locator('a[qtip="View"]').get_attribute("href")
    external_href = row.locator('a[qtip="External access"]').get_attribute("href")

    response = page.request.get(f"{live_server}{view_href}")
    assert response.ok
    assert "pdf" in response.headers.get("content-type", "")

    # ========== SECTION 5: Visualize the handout via the public external-access link ==========
    logout(page)
    response = page.request.get(f"{live_server}{external_href}")
    assert response.ok
    assert "pdf" in response.headers.get("content-type", "")
