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

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import fill_tinymce, go_to, login_orga, submit_confirm, expect_normalized

pytestmark = pytest.mark.e2e


def test_translations_text(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # set up texts
    go_to(page, live_server, "/manage")
    page.get_by_role("link", name="Texts").click()
    page.get_by_role("link", name="New").click()
    fill_tinymce(page, "id_text", "Hello", show=False)
    page.locator("#id_typ").select_option("h")
    page.get_by_text("After confirmation, add").click()
    submit_confirm(page)

    fill_tinymce(page, "id_text", "BUONGIORNO", show=False)
    page.locator("#id_language").select_option("it")
    page.locator("#id_default").uncheck()
    page.locator("#id_typ").select_option("h")
    page.get_by_text("After confirmation, add").click()
    submit_confirm(page)

    fill_tinymce(page, "id_text", "bonjour", show=False)
    page.locator("#id_language").select_option("fr")
    page.locator("#id_typ").select_option("h")
    page.locator("#id_default").uncheck()
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Home fr bonjour Home it BUONGIORNO Home en Hello")

    # test languages
    go_to(page, live_server, "/")
    expect_normalized(page, page.locator("#one"), "Hello")

    go_to(page, live_server, "/language")
    page.get_by_label("Select Language:").select_option("it")
    page.get_by_label("Select Language:").click()
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "BUONGIORNO")
    expect_normalized(page, page.locator("#topbar"), "Profilo Contabilità")

    go_to(page, live_server, "/language")
    page.get_by_label("Seleziona la lingua:").select_option("fr")
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "bonjour")
    expect_normalized(page, page.locator("#topbar"), "Profil Comptabilité")

    go_to(page, live_server, "/language")
    page.get_by_label("Sélectionner la langue :").select_option("de")
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Hello")
