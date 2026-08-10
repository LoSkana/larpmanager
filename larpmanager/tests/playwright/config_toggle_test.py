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
Test: Direct activation and deactivation of configuration options.
Verifies that the organization and event config on/off links set the option value.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    go_to,
    login_orga,
)

pytestmark = pytest.mark.e2e


def test_config_toggle(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # Organization option, activated then deactivated
    go_to(page, live_server, "/manage/config/calendar_past_events/on")
    expect(page.locator("#id_calendar_past_events")).to_be_checked()
    go_to(page, live_server, "/manage/config/calendar_past_events/off")
    expect(page.locator("#id_calendar_past_events")).not_to_be_checked()

    # Event option, activated then deactivated
    go_to(page, live_server, "/test/manage/config/show_export/on")
    expect(page.locator("#id_show_export")).to_be_checked()
    go_to(page, live_server, "/test/manage/config/show_export/off")
    expect(page.locator("#id_show_export")).not_to_be_checked()
