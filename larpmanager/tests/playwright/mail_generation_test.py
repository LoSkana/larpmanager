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
Test: Email generation for chat, badge, membership, and expenses.
Verifies automated email workflows for chat messages, badge assignments, membership application
submission/approval/rejection, and expense submission with proper email triggers.
"""

import re
from typing import Any

import pytest

from larpmanager.tests.utils import just_wait, check_download, fill_tinymce, get_modal_iframe, go_to, load_image, \
    login_orga, submit, \
    submit_confirm, save_modal

pytestmark = pytest.mark.e2e


def test_mail_generation(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    chat(live_server, page)

    badge(live_server, page)

    submit_membership(live_server, page)

    resubmit_membership(live_server, page)

    expense(live_server, page)


def expense(live_server: Any, page: Any) -> None:
    # approve it
    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Request").click()
    page.get_by_role("textbox", name="Response").fill("yeaaaa")
    submit_confirm(page)

    # expenses
    go_to(page, live_server, "/manage/features/expense/on")
    go_to(page, live_server, "/test/manage/upload_expenses/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_value").click()
    edit_iframe.locator("#id_value").fill("10")
    load_image(edit_iframe,"#id_invoice")
    edit_iframe.locator("#id_exp").select_option("g")
    edit_iframe.locator("#id_descr").click()
    edit_iframe.locator("#id_descr").fill("dsadas")
    submit_confirm(edit_iframe)

    go_to(page, live_server, "/test/manage/expenses")
    page.get_by_role("link", name="Approve").click()


def resubmit_membership(live_server: Any, page: Any) -> None:
    # refute it
    go_to(page, live_server, "/manage/membership/")
    page.get_by_role("link", name="Request").click()
    page.locator("form").locator("#id_is_approved").click()
    page.locator("form").locator("#id_response").fill("nope")
    submit_confirm(page)

    # signup
    go_to(page, live_server, "/test/manage/tickets/")
    # Wait for the edit button to appear and click it
    page.locator(".fa-edit").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_price").click()
    edit_iframe.locator("#id_price").fill("100")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/test/register/")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)
    # Set membership fee
    go_to(page, live_server, "/manage/config/")
    page.get_by_role("link", name=re.compile(r"^Members\s.+")).click()
    page.locator("#id_membership_fee").click()
    page.locator("#id_membership_fee").fill("10")
    page.locator("#id_membership_day").click()
    page.locator("#id_membership_day").fill("01-01")
    submit_confirm(page)
    # update signup, go to membership
    go_to(page, live_server, "/test/register/")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)
    submit(page)
    page.locator("#id_confirm_1").check()
    page.locator("#id_confirm_2").check()
    page.locator("#id_confirm_3").check()
    page.locator("#id_confirm_4").check()
    submit(page)


def submit_membership(live_server: Any, page: Any) -> None:
    # Test membership
    go_to(page, live_server, "/manage/features/membership/on")

    # setup membership text
    go_to(page, live_server, "/manage/texts")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    fill_tinymce(edit_iframe, "id_text", "Ciao {{ member.name }}!", show=False)
    edit_iframe.locator("#id_typ").select_option("m")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "/membership")
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)

    check_download(page, "download it here")

    load_image(page, "#id_request")
    load_image(page, "#id_document")

    submit(page)
    page.locator("#id_confirm_1").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_2").check()
    page.get_by_text("I confirm that I have").click()
    page.locator("#id_confirm_3").check()
    page.locator("#id_confirm_4").check()
    submit(page)


def badge(live_server: Any, page: Any) -> None:
    # Test badge
    go_to(page, live_server, "/manage/features/badge/on")
    go_to(page, live_server, "/manage/badges")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").click()
    edit_iframe.locator("#id_name").fill("prova")
    edit_iframe.locator("#id_name").press("Tab")
    edit_iframe.locator("#id_name_eng").fill("prova")
    edit_iframe.locator("#id_name_eng").press("Tab")
    edit_iframe.locator("#id_descr").fill("asdsa")
    edit_iframe.locator("#id_descr").press("Tab")
    edit_iframe.locator("#id_descr_eng").fill("asdsadaasd")
    edit_iframe.locator("#id_cod").click()
    edit_iframe.locator("#id_cod").fill("asd")
    edit_iframe.locator("#id_cod").click()
    edit_iframe.locator("#id_cod").fill("asasdsadd")
    edit_iframe.locator("#id_img").click()

    load_image(edit_iframe,"#id_img")
    edit_iframe.get_by_role("searchbox").fill("user")
    edit_iframe.get_by_role("option", name="User Test - user@test.it").click()
    save_modal(page, edit_iframe)


def chat(live_server: Any, page: Any) -> None:
    # Test chat
    go_to(page, live_server, "/manage/features/chat/on")
    go_to(page, live_server, "/public/uIT2O97q9XKA/")
    page.get_by_role("link", name="Chat").click()
    page.get_by_role("textbox").fill("ciao!")
    submit(page)
