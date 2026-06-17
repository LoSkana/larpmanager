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
Test: Organization registration and creation.
Verifies new user registration, organization creation with automatic slug generation,
profile picture upload, and organization dashboard access.
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import expect_normalized, get_modal_iframe, go_to, just_wait, load_image, login_orga, \
    submit, submit_confirm, save_modal

pytestmark = pytest.mark.e2e


def test_exe_join(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/debug")

    go_to(page, live_server, "/register")
    page.get_by_role("textbox", name="Email address").click()
    page.get_by_role("textbox", name="Email address").fill("orga@prova.it")
    page.get_by_role("textbox", name="Email address").press("Tab")
    page.get_by_role("textbox", name="Password", exact=True).fill("banana1234!")
    page.get_by_role("textbox", name="Password", exact=True).press("Tab")
    page.get_by_role("textbox", name="Password confirmation").fill("banana1234!")
    page.get_by_role("textbox", name="Name", exact=True).click()
    page.get_by_role("textbox", name="Name", exact=True).fill("prova")
    page.get_by_role("cell", name="Yes, keep me posted! Do you").click()
    page.get_by_label("Newsletter").select_option("o")
    page.get_by_role("textbox", name="Surname").click()
    page.get_by_role("textbox", name="Surname").fill("orga")
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)

    go_to(page, live_server, "/debug")
    go_to(page, live_server, "/join")

    # check auto slug
    name_input = page.get_by_role("textbox", name="Organization name", exact=True)
    name_input.fill("prova°°à!* cs")
    expect(page.locator("#slug")).to_have_value("provaacs")
    page.locator("#slug").click()
    page.locator("#slug").fill("proaacs")
    name_input.click()
    name_input.fill("prova°    °à!* cs")
    expect(page.locator("#slug")).to_have_value("proaacs")

    name_input.click()
    name_input.fill("Prova Larp")
    page.locator("#id_profile").wait_for(state="visible")
    load_image(page, "#id_profile")
    page.locator("#slug").fill("prova")
    submit(page)

    just_wait(page)
    go_to(page, live_server, "/debug/prova")

    expect_normalized(page, page.locator("#banner"), "prova larp")

    select_language(live_server, page, "it")

    go_to(page, live_server, "manage/activation/")
    expect_normalized(page, page.locator("#banner h1"), "Attivazione")
    expect(page.get_by_role("cell", name="Creazione eventi")).to_be_visible()
    expect(page.get_by_role("cell", name="Metodi pagamento")).to_be_visible()
    expect(page.get_by_role("cell", name="Biglietti di iscrizione")).to_be_visible()
    expect(page.get_by_role("cell", name="Form iscrizione")).to_be_visible()
    expect(page.get_by_role("cell", name="Prima iscrizione")).to_be_visible()

    # Step 1: create event
    go_to(page, live_server, "manage/events")
    page.get_by_role("link", name="Nuovo evento").click()
    page.locator("#id_form1-name").fill("Prova Event")
    page.locator("#slug").fill("prova")
    page.locator("#id_form1-max_pg").fill("10")
    page.locator("#id_form2-development").select_option("1")
    page.locator("#id_form2-registration_status").select_option("o")
    page.locator("#id_form2-start").fill("2055-06-11")
    just_wait(page)
    page.locator("#id_form2-start").click()
    page.locator("#id_form2-end").fill("2055-06-13")
    just_wait(page)
    page.locator("#id_form2-end").click()
    just_wait(page)
    submit_confirm(page)

    go_to(page, live_server, "manage/activation/")
    expect(page.locator("tr", has_text="Creazione eventi")).to_contain_text("Fatto")

    # Step 2: payment methods
    go_to(page, live_server, "manage/methods")
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").fill("test wire")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_payee").fill("test beneficiary")
    page.locator("#id_wire_iban").fill("test iban")
    page.locator("#id_wire_bic").fill("test iban")
    submit_confirm(page)

    go_to(page, live_server, "manage/activation/")
    expect(page.locator("tr", has_text="Metodi pagamento")).to_contain_text("Fatto")

    # Step 3: registration ticket
    go_to(page, live_server, "prova/manage/tickets/")
    page.wait_for_selector("table.go_datatable")
    page.locator(".fa-edit").first.click(force=True)
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_price").fill("10.00")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "manage/activation/")
    expect(page.locator("tr", has_text="Biglietti di iscrizione")).to_contain_text("Fatto")

    # Step 4: registration form question
    go_to(page, live_server, "prova/manage/form/")
    page.get_by_role("link", name="Nuovo").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_typ").select_option("t")
    edit_iframe.locator("#id_name").fill("Dietary restrictions")
    save_modal(page, edit_iframe)

    go_to(page, live_server, "manage/activation/")
    expect(page.locator("tr", has_text="Form iscrizione")).to_contain_text("Fatto")

    # Step 5: first registration
    go_to(page, live_server, "prova/register")
    page.get_by_role("button", name="Continua").click()
    submit_confirm(page)

    go_to(page, live_server, "manage/activation/")
    expect(page.locator("tr", has_text="Prima iscrizione")).to_contain_text("Fatto")

    # Step 6: first character

    select_language(live_server, page, "en")

    go_to(page, live_server, "prova/manage/characters/")
    page.get_by_role("link", name="New").click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.locator("#id_name").fill("Test Character")
    save_modal(page, edit_iframe)

    select_language(live_server, page, "it")

    go_to(page, live_server, "manage/activation/")
    expect(page.locator("tr", has_text="Primo personaggio")).to_contain_text("Fatto")

    # Step 7: first assignment
    go_to(page, live_server, "prova/manage/registrations/")
    page.locator(".fa-edit").first.click()
    edit_iframe = get_modal_iframe(page)
    edit_iframe.get_by_role("searchbox").fill("Test")
    edit_iframe.get_by_role("option", name="Test Character").click()
    save_modal(page, edit_iframe)

    go_to(page, live_server, "manage/activation/")
    expect(page.locator("tr", has_text="Prima assegnazione")).to_contain_text("Fatto")

    # Final activation
    page.get_by_role("button", name="Attiva la modalità avanzata").click()
    just_wait(page)

    # New sidebar items visible after activation
    expect(page.locator("#exe_features")).to_be_visible()
    expect(page.locator("#exe_config")).to_be_visible()
    expect(page.locator("#exe_roles")).to_be_visible()
    expect(page.locator("#exe_appearance")).to_be_visible()


def select_language(live_server, page, lang):
    go_to(page, live_server, "/language")
    page.locator("#id_language").select_option(lang)
    submit_confirm(page)
