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
Test: v21 delete confirmation modal.
Verifies that clicking the trash icon on a manage list opens an iframe confirmation
modal showing the element name, that Cancel keeps the element, and that Confirm
deletes it and refreshes the listing without a full page reload.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    delete_modal,
    get_modal_iframe,
    go_to,
    login_orga,
    save_modal,
)

pytestmark = pytest.mark.e2e


def test_delete_modal(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Create a role to delete
    go_to(page, live_server, "/test/manage/roles")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Disposable Role")
    save_modal(page, edit_iframe)
    expect(page.locator('[id="u2"]')).to_contain_text("Disposable Role")

    # Cancel the deletion: modal opens, shows the name, pressing ESC keeps the element
    page.locator('#u2 .fa-trash').click(force=True)
    cancel_iframe = get_modal_iframe(page)
    expect(cancel_iframe.locator(".delete-confirm-message")).to_contain_text("Disposable Role")
    page.keyboard.press("Escape")
    page.locator("#lm-modal").wait_for(state="hidden")
    expect(page.locator('[id="u2"]')).to_contain_text("Disposable Role")

    # Confirm the deletion: element removed after refresh, no full navigation
    url_before = page.url
    delete_modal(page, page.locator('#u2 .fa-trash'), name="Disposable Role")
    assert page.url == url_before
    expect(page.locator("#one")).not_to_contain_text("Disposable Role")
