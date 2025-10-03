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
import pytest

from larpmanager.tests.utils import check_download, go_to, login_orga, submit_confirm

pytestmark = pytest.mark.e2e


def test_user_pdf(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # activate characters
    go_to(page, live_server, "/test/1/manage/features/character/on")

    # activate relationships
    go_to(page, live_server, "/test/1/manage/features/relationships/on")

    # activate pdf
    go_to(page, live_server, "/test/1/manage/features/print_pdf/on")

    # signup
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Assign character
    go_to(page, live_server, "/test/manage/registrations")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.get_by_role("searchbox").click()
    page.get_by_role("searchbox").fill("te")
    page.get_by_role("option", name="#1 Test Character").click()
    submit_confirm(page)

    # Go to character, test download pdf
    go_to(page, live_server, "/test/character/1")

    check_download(page, "Portraits (PDF)")

    check_download(page, "Profiles (PDF)")

    check_download(page, "Download complete sheet")

    check_download(page, "Download light sheet")

    check_download(page, "Download relationships")
