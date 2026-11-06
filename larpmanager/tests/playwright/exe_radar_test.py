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

"""Test: LARP Radar opt-in.
Verifies that the option is available only with the platform key, and that after
the opt-in the dashboard lists the visible upcoming runs not yet published.
"""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.utils import timezone
from playwright.sync_api import expect

from larpmanager.models.event import DevelopStatus, Run
from larpmanager.tests.utils import (
    go_to,
    login_orga,
)

pytestmark = pytest.mark.e2e


def test_exe_radar(pw_page: Any, settings: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/manage/features/publisher/on")

    # Without the platform key the option is not offered
    go_to(page, live_server, "/manage/config")
    expect(page.locator("#id_radar_enabled")).to_have_count(0)

    tomorrow = timezone.localdate() + timedelta(days=1)
    Run.objects.filter(event__slug="test").update(development=DevelopStatus.SHOW, start=tomorrow, end=tomorrow)

    settings.LARP_RADAR_API_KEY = "secret"
    with patch("larpmanager.utils.publication.radar.requests.put") as mock_put:
        go_to(page, live_server, "/manage/config/radar_enabled/on")
        expect(page.locator("#id_radar_enabled")).to_be_checked()

        # Without coordinates nothing is sent, and the dashboard asks to complete the event
        go_to(page, live_server, "/manage")
        expect(page.get_by_text("Not yet on LARP Radar")).to_be_visible()

    mock_put.assert_not_called()
