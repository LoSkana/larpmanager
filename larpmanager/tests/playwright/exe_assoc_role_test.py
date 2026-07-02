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
Test: Organization role-based permissions.
Verifies creation of organization roles, permission assignment, access control,
and role deletion with permission revocation.
"""

from typing import Any

import pytest

from larpmanager.tests.utils import (check_feature,
                                     delete_modal,
                                     go_to,
                                     login_orga,
                                     login_user,
                                     logout,
                                     expect_normalized,
                                     get_modal_iframe, save_modal,
                                     )

pytestmark = pytest.mark.e2e


def test_exe_association_role(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_user(page, live_server)

    go_to(page, live_server, "/manage/")
    expect_normalized(page, page.locator("#banner"), "Access denied")

    login_orga(page, live_server)

    go_to(page, live_server, "/manage/roles")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("test role")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.get_by_role("searchbox").fill("us")
    edit_iframe.get_by_role("option", name="User Test -").click()
    check_feature(edit_iframe, "Configuration")
    check_feature(edit_iframe, "Accounting")
    save_modal(page, edit_iframe)
    expect_normalized(page, page.locator('[id="u2"]'), "Organization (Configuration), Accounting (Accounting)")

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/manage/accounting/")
    expect_normalized(page, page.locator("#banner"), "Accounting - Organization")

    logout(page)
    login_orga(page, live_server)

    # Delete the role
    go_to(page, live_server, "/manage/roles")
    delete_modal(page, page.locator('#u2 .fa-trash'))

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/manage/")
    expect_normalized(page, page.locator("#banner"), "Access denied")
