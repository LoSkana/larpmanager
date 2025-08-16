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


from playwright.sync_api import sync_playwright

from larpmanager.tests.utils import (
    _checkboxes,
    add_links_to_visit,
    go_to,
    go_to_check,
    handle_error,
    login_orga,
    page_start,
)


def test_orga_features_all(live_server):
    with sync_playwright() as p:
        browser, context, page = page_start(p)
        try:
            orga_features_all(live_server, page)

        except Exception as e:
            handle_error(page, e, "orga_features_all")

        finally:
            context.close()
            browser.close()


def orga_features_all(live_server, page):
    login_orga(page, live_server)

    go_to(page, live_server, "/test/1/manage/features")
    _checkboxes(page, True)

    visit_all(page, live_server)

    go_to(page, live_server, "/test/1/manage/features")
    _checkboxes(page, False)


def visit_all(page, live_server):
    # Visit every link
    visited_links = set()
    links_to_visit = {live_server.url + "/manage/"}
    while links_to_visit:
        current_link = links_to_visit.pop()
        if current_link in visited_links:
            continue
        visited_links.add(current_link)

        go_to_check(page, current_link)

        add_links_to_visit(links_to_visit, page, visited_links)
