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
Test: Multilingual support and custom texts.
Verifies custom text management in multiple languages (English, Italian, French, German),
language switching, and translation of interface elements.
"""

from typing import Any

import pytest

from larpmanager.tests.utils import fill_tinymce, go_to, login_orga, submit_confirm, expect_normalized, \
    get_modal_iframe, save_modal, topbar

pytestmark = pytest.mark.e2e


def test_translations_text(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    # set up texts
    go_to(page, live_server, "/manage")
    page.get_by_role("link", name="Texts").click()
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    fill_tinymce(edit_iframe, "id_text", "Hello", show=False)
    edit_iframe.locator("#id_typ").select_option("h")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    fill_tinymce(edit_iframe, "id_text", "BUONGIORNO", show=False)
    edit_iframe.locator("#id_language").select_option("it")
    edit_iframe.locator("#id_default").uncheck()
    edit_iframe.locator("#id_typ").select_option("h")
    save_modal(page, edit_iframe)

    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    fill_tinymce(edit_iframe, "id_text", "bonjour", show=False)
    edit_iframe.locator("#id_language").select_option("fr")
    edit_iframe.locator("#id_typ").select_option("h")
    edit_iframe.locator("#id_default").uncheck()
    save_modal(page, edit_iframe)
    expect_normalized(page, page.locator("#one"), "Home fr bonjour Home it BUONGIORNO Home en Hello")

    # test languages
    go_to(page, live_server, "/")
    expect_normalized(page, page.locator("#one"), "Hello")

    go_to(page, live_server, "/language")
    page.get_by_label("Select Language").select_option("it")
    page.get_by_label("Select Language").click()
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "BUONGIORNO")
    topbar(page, "Profilo")
    expect_normalized(page, page.locator("#sidebar"), "Dati personali")


    go_to(page, live_server, "/language")
    page.get_by_label("Seleziona la lingua").select_option("fr")
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "bonjour")
    topbar(page, "Profil")
    expect_normalized(page, page.locator("#sidebar"), "Informations personnelles")

    go_to(page, live_server, "/language")
    page.get_by_label("Sélectionner la langue").select_option("de")
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Hello")
    topbar(page, "Profil")
    expect_normalized(page, page.locator("#sidebar"), "IPersönliche Angaben")
