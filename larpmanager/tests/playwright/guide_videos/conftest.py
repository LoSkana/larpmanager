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

"""Browser fixture for guide video storyboards, run on a virtual display."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from larpmanager.tests.playwright.guide_videos.director import (
    CURSOR_SCRIPT,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    Director,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import BrowserType

UI_SCALE = 1.25
ACTION_TIMEOUT_MS = 30_000
BROWSER_PREFERENCES = {"credentials_enable_service": False, "profile": {"password_manager_enabled": False}}


@pytest.fixture(autouse=True)
def _rich_text(request: pytest.FixtureRequest, settings: Any) -> None:
    """Render the real text editor for storyboards setting RICH_TEXT, instead of plain textareas."""
    if getattr(request.module, "RICH_TEXT", False):
        settings.TINYMCE_DISABLED = False


@pytest.fixture
def director(
    request: pytest.FixtureRequest, browser_type: BrowserType, live_server: Any, tmp_path: Path
) -> Generator[Director]:
    """Open a full-screen browser and yield a Director writing to GUIDE_VIDEO_OUTPUT."""
    output_root = Path(os.environ.get("GUIDE_VIDEO_OUTPUT", ".guide_videos/output"))
    slug = request.node.path.stem.removesuffix("_storyboard")
    title = getattr(request.module, "TITLE", slug)

    profile_dir = tmp_path / "profile"
    (profile_dir / "Default").mkdir(parents=True)
    (profile_dir / "Default" / "Preferences").write_text(json.dumps(BROWSER_PREFERENCES))

    # A persistent context is needed: kiosk mode only applies to the default browser window
    context = browser_type.launch_persistent_context(
        profile_dir,
        headless=False,
        no_viewport=True,
        bypass_csp=True,
        locale="en-US",
        args=[
            "--kiosk",
            "--no-first-run",
            "--disable-infobars",
            "--hide-scrollbars",
            f"--force-device-scale-factor={UI_SCALE}",
            f"--window-size={int(SCREEN_WIDTH / UI_SCALE)},{int(SCREEN_HEIGHT / UI_SCALE)}",
            "--window-position=0,0",
        ],
    )
    context.add_init_script(CURSOR_SCRIPT)
    page = context.pages[0]
    page.set_default_timeout(ACTION_TIMEOUT_MS)

    guide = Director(page, live_server.url, output_root / slug, title, getattr(request.module, "PACE", 1.0))
    yield guide

    guide.abort()
    context.close()
