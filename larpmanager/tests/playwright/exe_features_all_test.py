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

from larpmanager.tests.utils import _checkboxes, add_links_to_visit, go_to, go_to_check, login_orga

pytestmark = pytest.mark.e2e


def test_exe_features_all(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/manage/features")
    _checkboxes(page, True)

    visit_all(page, live_server)

    go_to(page, live_server, "/manage/features")
    _checkboxes(page, False)


def visit_all(page, live_server):
    # Visit every link
    visited_links = set()
    links_to_visit = {live_server + "/manage/"}
    while links_to_visit:
        current_link = links_to_visit.pop()
        if current_link in visited_links:
            continue
        visited_links.add(current_link)

        go_to_check(page, current_link)

        add_links_to_visit(links_to_visit, page, visited_links)
