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

from larpmanager.tests.utils import go_to, load_image, login_user, submit_confirm

pytestmark = pytest.mark.e2e


def test_user_ticket(pw_page) -> None:
    page, live_server, _ = pw_page

    go_to(page, live_server, "/")

    # no member
    page.get_by_role("link", name="Technical Support").click()
    page.get_by_role("textbox", name="Email").click()
    page.get_by_role("textbox", name="Email").fill("dudi")
    page.get_by_role("textbox", name="Email").press("Tab")
    page.get_by_role("textbox", name="Request").fill("bibu")
    submit_confirm(page)
    page.get_by_role("textbox", name="Email").fill("dudi@sad.it")
    submit_confirm(page)

    # no member - screenshot
    page.get_by_role("link", name="Technical Support").click()
    page.get_by_role("textbox", name="Email").click()
    page.get_by_role("textbox", name="Email").fill("sadsa@sadsa.itsad")
    page.get_by_role("textbox", name="Request").click()
    page.get_by_role("textbox", name="Request").fill("sadsadsadsad")
    page.get_by_role("button", name="Screenshot").click()
    load_image(page, "#id_screenshot")
    submit_confirm(page)

    login_user(page, live_server)

    # user
    page.get_by_role("link", name="Technical Support").click()
    page.get_by_role("textbox", name="Email").click()
    page.get_by_role("textbox", name="Email").fill("wwww@ewew.itsa")
    page.get_by_role("textbox", name="Request").click()
    page.get_by_role("textbox", name="Request").fill("sadsadsa")
    submit_confirm(page)

    # user - screenshot
    page.get_by_role("link", name="Technical Support").click()
    page.get_by_role("textbox", name="Email").click()
    page.get_by_role("textbox", name="Email").fill("eee@re.it")
    page.get_by_role("textbox", name="Email").press("Tab")
    page.get_by_role("textbox", name="Request").fill("asdasdas")
    page.get_by_role("button", name="Screenshot").click()
    load_image(page, "#id_screenshot")
    submit_confirm(page)

    # change email
    page.get_by_role("link", name=" Profile").click()
    page.get_by_role("link", name="Would you like to change it?").click()
    page.get_by_role("textbox", name="Email").click()
    page.get_by_role("textbox", name="Email").fill("asdsa@dasasd.it")
    page.get_by_role("textbox", name="Request").click()
    page.get_by_role("textbox", name="Request").fill("sasadsadsa")
    submit_confirm(page)
