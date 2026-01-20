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
Test: Simple registration workflow with pre-registration and help system.
Verifies basic signup flow, profile confirmation, pre-registration feature,
help question submission and answering, and email notifications.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import just_wait, go_to, load_image, login_orga, submit_confirm, expect_normalized

pytestmark = pytest.mark.e2e


def test_user_signup_simple(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    pre_register(live_server, page)

    signup(live_server, page)

    help_questions(live_server, page)


def signup(live_server: Any, page: Any) -> None:
    # deactivate registration open
    go_to(page, live_server, "/test/manage/features/registration_open/off")

    # sign up
    go_to(page, live_server, "/")
    expect_normalized(page, page.locator("#one"), "Registration is open!")
    page.get_by_role("link", name="Registration is open!").click()
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # test mails
    go_to(page, live_server, "/debug/mail")

    # delete sign up
    go_to(page, live_server, "/test/manage/registrations")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.get_by_role("link", name="Delete").click()
    just_wait(page)
    page.get_by_role("button", name="Confirmation delete").click()

    # sign up, confirm profile
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    go_to(page, live_server, "/test/register")
    expect_normalized(page, page.locator("#one"), "Registration confirmed")
    expect_normalized(page, page.locator("#one"), "please fill in your profile.")

    page.locator("#one").get_by_role("table").get_by_role("link", name="please fill in your profile.").click()
    page.get_by_role("checkbox", name="Authorisation").check()
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "Registration confirmed (Standard)")

    # test update of signup with no payments
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    expect(page.locator("#banner")).not_to_contain_text("Register")


def help_questions(live_server: Any, page: Any) -> None:
    # test help
    go_to(page, live_server, "/manage/features/help/on")
    page.get_by_role("link", name="Need help?").click()
    page.get_by_role("textbox", name="Text").click()
    page.get_by_role("textbox", name="Text").fill("please help me")
    load_image(page, "#id_attachment")
    page.get_by_label("Event").select_option("u1")
    submit_confirm(page)

    # check questions
    expect_normalized(page, page.locator("#one"), "[Test Larp] - please help me (Attachment)")
    go_to(page, live_server, "/manage/questions")
    expect_normalized(page, page.locator("#one"), "please help me")

    page.get_by_role("link", name="Answer", exact=True).click()
    page.get_by_role("textbox", name="Text").click()
    page.get_by_role("textbox", name="Text").fill("aasadsada")
    submit_confirm(page)
    page.get_by_role("link", name="Need help?").click()
    page.get_by_role("textbox", name="Text").click()
    page.get_by_role("textbox", name="Text").fill("e adessoooo")
    submit_confirm(page)

    go_to(page, live_server, "/manage/questions")
    page.get_by_role("link", name="Close").click()
    page.get_by_role("link", name="Show questions already").click()
    submit_confirm(page)


def pre_register(live_server: Any, page: Any) -> None:
    # Set email send
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_cc").check()
    page.locator("#id_mail_signup_new").check()
    page.locator("#id_mail_signup_update").check()
    page.locator("#id_mail_signup_del").check()
    page.locator("#id_mail_payment").check()

    # Activate pre-register
    go_to(page, live_server, "/manage/features/pre_register/on")
    # Activate registration open
    go_to(page, live_server, "/test/manage/features/registration_open/on")

    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Pre-registration\s.+")).click()
    page.locator("#id_pre_register_active").check()
    submit_confirm(page)

    go_to(page, live_server, "/")
    expect_normalized(page, page.locator("#one"), "Pre-register to the event!")
    page.get_by_role("link", name="Pre-register to the event!").click()

    submit_confirm(page)
    page.get_by_role("link", name="Delete").click()
    page.get_by_role("textbox", name="Informations").click()
    page.get_by_role("textbox", name="Informations").fill("bauuu")
    page.get_by_label("Event").select_option("u1")
    submit_confirm(page)
    expect_normalized(page, page.locator("#one"), "bauuu")

    # disable preregistration, sign up really
    go_to(page, live_server, "/test/manage/config")
    page.get_by_role("link", name=re.compile(r"^Pre-registration\s.+")).click()
    page.locator("#id_pre_register_active").uncheck()
    submit_confirm(page)
