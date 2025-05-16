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

from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright

from larpmanager.tests.utils import _checkboxes, go_to, go_to_check, handle_error, login_orga, page_start


@pytest.mark.django_db(transaction=True)
def test_exe_features_all(live_server):
    with sync_playwright() as p:
        browser, context, page = page_start(p)
        try:
            exe_features_all(live_server, page)

        except Exception as e:
            handle_error(page, e, "exe_features")

        finally:
            context.close()
            browser.close()


def exe_features_all(live_server, page):
    login_orga(page, live_server)

    go_to(page, live_server, "/manage/features")
    _checkboxes(page, True)

    visit_all(page, live_server)

    go_to(page, live_server, "/manage/features")
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

        new_links = page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")
        for link in new_links:
            if "logout" in link:
                continue
            if link.endswith(("#", "#menu", "#sidebar", "print")):
                continue
            if any(s in link for s in ["features", "pdf"]):
                continue
            parsed_url = urlparse(link)
            if parsed_url.hostname not in ("localhost", "127.0.0.1"):
                continue
            if link not in visited_links:
                links_to_visit.add(link)
