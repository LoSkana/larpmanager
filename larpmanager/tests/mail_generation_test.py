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
from pathlib import Path

import pytest

from larpmanager.tests.utils import check_download, fill_tinymce, go_to, login_orga, submit

pytestmark = pytest.mark.e2e


def test_mail_generation(pw_page):
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    chat(live_server, page)

    image_path = Path(__file__).parent / "image.jpg"

    badge(live_server, page, image_path)

    submit_membership(live_server, page, image_path)

    resubmit_membership(live_server, page)

    expense(image_path, live_server, page)


def expense(image_path, live_server, page):
    # approve it
    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Request").click()
    page.get_by_role("textbox", name="Response").fill("yeaaaa")
    page.get_by_role("button", name="Confirm").click()

    # expenses
    go_to(page, live_server, "/manage/features/106/on")
    go_to(page, live_server, "/test/1/manage/expenses/my")
    page.get_by_role("link", name="New").click()
    page.get_by_role("spinbutton", name="Value").click()
    page.get_by_role("spinbutton", name="Value").fill("10")
    page.locator("#id_invoice").set_input_files(str(image_path))
    page.get_by_label("Type").select_option("g")
    page.get_by_role("textbox", name="Descr").click()
    page.get_by_role("textbox", name="Descr").fill("dsadas")
    page.get_by_role("button", name="Confirm", exact=True).click()
    go_to(page, live_server, "/test/1/manage/expenses")
    page.get_by_role("link", name="Approve").click()


def resubmit_membership(live_server, page):
    # refute it
    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Request").click()
    page.locator("form").locator("#id_is_approved").click()
    page.locator("form").locator("#id_response").fill("nope")
    page.get_by_role("button", name="Confirm").click()
    # signup
    go_to(page, live_server, "/test/1/manage/registrations/tickets/")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.locator("#id_price").click()
    page.locator("#id_price").fill("100")
    page.get_by_role("button", name="Confirm", exact=True).click()

    go_to(page, live_server, "/test/1/register/")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    # Set membership fee
    go_to(page, live_server, "/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Members\s.+")).click()
    page.locator("#id_membership_fee").click()
    page.locator("#id_membership_fee").fill("10")
    page.locator("#id_membership_day").click()
    page.locator("#id_membership_day").fill("01-01")
    page.get_by_role("button", name="Confirm", exact=True).click()
    # update signup, go to membership
    go_to(page, live_server, "/test/1/register/")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    submit(page)
    page.locator("#id_confirm_1").check()
    page.locator("#id_confirm_2").check()
    page.locator("#id_confirm_3").check()
    page.locator("#id_confirm_4").check()
    submit(page)


def submit_membership(live_server, page, image_path):
    # Test membership
    go_to(page, live_server, "/manage/features/45/on")
    go_to(page, live_server, "/manage/texts")
    page.wait_for_timeout(2000)
    page.get_by_role("link", name="New").click()

    fill_tinymce(page, "id_text", "Ciao {{ member.name }}!")

    page.locator("#main_form").click()
    page.locator("#id_typ").select_option("m")
    page.get_by_role("button", name="Confirm", exact=True).click()
    go_to(page, live_server, "/membership")
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)

    check_download(page, "download it here")

    page.locator("#id_request").set_input_files(str(image_path))
    page.locator("#id_document").set_input_files(str(image_path))

    submit(page)
    page.locator("#id_confirm_1").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_2").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_3").check()
    page.locator("#id_confirm_4").check()
    submit(page)


def badge(live_server, page, image_path):
    # Test badge
    go_to(page, live_server, "/manage/features/65/on")
    go_to(page, live_server, "/manage/badges")
    page.get_by_role("link", name="New").click()
    page.locator("#id_name").click()
    page.locator("#id_name").fill("prova")
    page.locator("#id_name").press("Tab")
    page.locator("#id_name_eng").fill("prova")
    page.locator("#id_name_eng").press("Tab")
    page.locator("#id_descr").fill("asdsa")
    page.locator("#id_descr").press("Tab")
    page.locator("#id_descr_eng").fill("asdsadaasd")
    page.locator("#id_cod").click()
    page.locator("#id_cod").fill("asd")
    page.locator("#id_cod").click()
    page.locator("#id_cod").fill("asasdsadd")
    page.locator("#id_img").click()

    page.locator("#id_img").set_input_files(str(image_path))
    page.get_by_role("searchbox").fill("user")
    page.get_by_role("option", name="User Test - user@test.it").click()
    page.get_by_role("button", name="Confirm", exact=True).click()


def chat(live_server, page):
    # Test chat
    go_to(page, live_server, "/manage/features/52/on")
    go_to(page, live_server, "/public/3/")
    page.get_by_role("link", name="Chat").click()
    page.get_by_role("textbox").fill("ciao!")
    submit(page)
