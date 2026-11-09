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

"""Test: Guides list search and video popup, and the video embed on the guide page."""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.models.larpmanager import LarpManagerGuide
from larpmanager.tests.utils import login_orga

pytestmark = pytest.mark.e2e


def test_guides_list(pw_page: Any) -> None:
    """Search filters the list, the popup loads the video and the guide page embeds it."""
    page, live_server, _context = pw_page

    # Drop the guides loaded from the fixture
    LarpManagerGuide.objects.all().delete()

    LarpManagerGuide.objects.create(
        number=1,
        title="Payments",
        slug="payments",
        group="Organization",
        description="Collect money",
        keywords="wire transfer",
        video_id="abc-DEF_123",
        text="<p>Text</p>",
        published=True,
    )
    LarpManagerGuide.objects.create(
        number=2, title="Writing", slug="writing", group="Story", text="<p>Text</p>", published=True
    )

    # Reach the main site, where the guides live
    login_orga(page, live_server)
    page.goto(f"{live_server}/debug/")
    page.goto(f"{live_server}/guides/")

    rows = page.locator(".guide-row")
    expect(rows).to_have_count(2)
    expect(page.locator(".guide-group h2")).to_have_text(["Organization", "Story"])

    # Search matches keywords and hides the groups left empty
    page.locator("#guide-search").fill("WIRE")
    expect(rows.filter(has_text="Payments")).to_be_visible()
    expect(rows.filter(has_text="Writing")).to_be_hidden()
    expect(page.locator(".guide-group h2", has_text="Story")).to_be_hidden()

    page.locator("#guide-search").fill("nothing here")
    expect(page.locator("#guide-no-results")).to_be_visible()

    page.locator("#guide-search").fill("")
    expect(rows.filter(has_text="Writing")).to_be_visible()
    expect(page.locator("#guide-no-results")).to_be_hidden()

    # Only guides with a video offer it, and the popup loads it on request
    expect(page.locator(".guide-watch")).to_have_count(1)
    frame = page.locator("#guide-video-frame")
    expect(frame).not_to_have_attribute("src", "https://www.youtube.com/embed/abc-DEF_123?autoplay=1")
    page.locator(".guide-watch").click()
    expect(page.locator("#guide-video-modal")).to_be_visible()
    expect(page.locator("#guide-video-title")).to_have_text("Payments")
    expect(frame).to_have_attribute("src", "https://www.youtube.com/embed/abc-DEF_123?autoplay=1")

    # Closing unloads the player
    page.locator("#guide-video-close").click()
    expect(page.locator("#guide-video-modal")).to_be_hidden()
    expect(frame).to_have_attribute("src", "about:blank")

    # The guide page embeds the video at its start
    page.locator(".guide-read").first.click()
    expect(page.locator("#article > iframe.guide-video")).to_have_attribute(
        "src", "https://www.youtube.com/embed/abc-DEF_123"
    )
