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

from larpmanager.tests.utils import go_to, login_orga, submit

pytestmark = pytest.mark.e2e


def test_exe_profile(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/manage/profile")
    page.locator("#id_gender").select_option("o")
    page.locator("#id_birth_place").select_option("m")
    page.locator("#id_document_type").select_option("m")
    page.locator("#id_diet").select_option("o")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/profile")
    page.get_by_role("textbox", name="Name (*)", exact=True).click()
    page.get_by_role("textbox", name="Name (*)", exact=True).press("End")
    page.get_by_role("textbox", name="Name (*)", exact=True).fill("Orga")
    page.get_by_role("textbox", name="Surname (*)").click()
    page.get_by_role("textbox", name="Surname (*)").press("End")
    page.get_by_role("textbox", name="Surname (*)").fill("Test")
    page.get_by_label("Gender").select_option("f")
    page.get_by_role("textbox", name="Diet").click()
    page.get_by_role("textbox", name="Diet").fill("sadsada")
    page.get_by_role("textbox", name="Diet").press("Shift+Home")
    page.get_by_role("textbox", name="Diet").fill("s")
    page.get_by_role("textbox", name="Diet").press("Shift+Home")
    page.get_by_role("textbox", name="Diet").fill("test")
    page.get_by_role("textbox", name="Birth place (*)").click()
    page.get_by_role("textbox", name="Diet").click()
    page.get_by_role("textbox", name="Diet").fill("")
    page.get_by_role("textbox", name="Birth place (*)").click()
    page.get_by_role("textbox", name="Birth place (*)").fill("test")
    page.get_by_label("Document type (*)").select_option("p")
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)
