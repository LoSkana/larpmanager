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
                                     go_to,
                                     login_orga,
                                     login_user,
                                     logout,
                                     submit_confirm,
                                     expect_normalized,
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
    page.locator("#id_name").click()
    page.locator("#id_name").fill("test role")
    page.locator("#id_name").press("Tab")
    page.get_by_role("searchbox").fill("us")
    page.get_by_role("option", name="User Test -").click()
    check_feature(page, "Configuration")
    check_feature(page, "Accounting")
    submit_confirm(page)
    expect_normalized(page, page.locator('[id="u2"]'), "Organization (Configuration), Accounting (Accounting)")

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/manage/accounting/")
    expect_normalized(page, page.locator("#banner"), "Accounting - Organization")

    logout(page)
    login_orga(page, live_server)

    # Delete the role
    go_to(page, live_server, "/manage/roles")
    page.locator('#u2 .fa-trash').click()

    logout(page)
    login_user(page, live_server)

    go_to(page, live_server, "/manage/")
    expect_normalized(page, page.locator("#banner"), "Access denied")
