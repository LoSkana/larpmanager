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
Test: Member profile field configuration.
Verifies that, for a newly created organization, all configurable member
profile fields can be marked optional, filled in from the user profile page,
and then re-marked mandatory while the previously saved data is preserved.
"""

from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, just_wait, load_image, load_image_hidden, login_orga, submit, submit_confirm

pytestmark = pytest.mark.e2e


def _set_all_profile_fields(page: Any, value: str) -> None:
    """Set every configurable member field select on the exe profile config page."""
    selects = page.locator("table select")
    for i in range(selects.count()):
        selects.nth(i).select_option(value)


def _fill_profile_form(page: Any, round_num: int) -> dict:
    """Fill in every available field on the user profile page with test data.

    round_num distinguishes the value set used (1st pass vs 2nd pass), so the
    2nd pass changes every value rather than re-submitting the same data.
    Returns a map of element id -> expected value, to be checked after reload.
    """
    expected: dict = {}
    checked: list = []

    text_value = "Test value" if round_num == 1 else "Updated value"
    text_area_value = "Test text" if round_num == 1 else "Updated text"
    date_value = "2000-01-01" if round_num == 1 else "2001-02-02"
    phone_value = "+12025550123" if round_num == 1 else "+12025550199"
    residence_value = "a" if round_num == 1 else "b"

    # Photo upload (avatar widget), present only if the "profile" field is enabled
    image_input = page.locator("#id_image")
    if image_input.count() > 0 and round_num == 1:
        load_image_hidden(page, "#id_image")
        just_wait(page)

    # Phone contact needs a syntactically valid phone number
    phone_input = page.locator("#id_phone_contact")
    if phone_input.count() > 0:
        phone_input.fill(phone_value)
        expected["id_phone_contact"] = phone_value

    # Residence address (country + province compound widget)
    country_select = page.locator("#id_residence_address_0")
    if country_select.count() > 0:
        country_options = country_select.locator("option")
        country_select.select_option(index=_pick_different_index(country_select, country_options, round_num))
        just_wait(page)
        expected["id_residence_address_0"] = country_select.input_value()

        province_select = page.locator("#id_residence_address_1")
        province_options = province_select.locator("option")
        if province_options.count() > 1:
            province_select.select_option(index=_pick_different_index(province_select, province_options, round_num))
            expected["id_residence_address_1"] = province_select.input_value()

        for idx in range(2, 6):
            page.locator(f"#id_residence_address_{idx}").fill(residence_value)
            expected[f"id_residence_address_{idx}"] = residence_value

    # Plain text/date inputs
    inputs = page.locator("table input")
    for i in range(inputs.count()):
        el = inputs.nth(i)
        input_id = el.get_attribute("id") or ""
        if not input_id or "residence_address" in input_id or "phone_contact" in input_id:
            continue
        input_type = el.get_attribute("type")
        if input_type in ("hidden", "file", "submit"):
            continue
        if input_type == "checkbox":
            if not el.is_checked():
                el.check()
            checked.append(input_id)
            continue
        value = date_value if input_type == "date_p" else text_value
        el.fill(value)
        expected[input_id] = value
        just_wait(page)
        el.click()

    # Textareas
    textareas = page.locator("table textarea")
    for i in range(textareas.count()):
        el = textareas.nth(i)
        textarea_id = el.get_attribute("id") or ""
        el.fill(text_area_value)
        if textarea_id:
            expected[textarea_id] = text_area_value

    # Selects (residence address already handled above)
    selects = page.locator("table select")
    for i in range(selects.count()):
        el = selects.nth(i)
        select_id = el.get_attribute("id") or ""
        if not select_id or "residence_address" in select_id:
            continue
        options = el.locator("option")
        if options.count() > 1:
            el.select_option(index=_pick_different_index(el, options, round_num))
            expected[select_id] = el.input_value()

    return {"values": expected, "checked": checked}


def _pick_different_index(select_locator: Any, options_locator: Any, round_num: int) -> int:
    """Pick an option index, choosing one different from the current value on the 2nd round."""
    if round_num == 1:
        return 1
    current = select_locator.input_value()
    count = options_locator.count()
    for i in range(count):
        value = options_locator.nth(i).get_attribute("value")
        if value not in (None, "", current):
            return i
    return 1


def _verify_profile_form(page: Any, expected: dict) -> None:
    """Check that every previously filled field still holds the expected value."""
    for element_id, value in expected["values"].items():
        locator = page.locator(f"#{element_id}")
        if locator.count() > 0:
            expect(locator).to_have_value(value)

    for element_id in expected["checked"]:
        locator = page.locator(f"#{element_id}")
        if locator.count() > 0:
            expect(locator).to_be_checked()


def test_user_profile_fields(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    go_to(page, live_server, "/debug")

    go_to(page, live_server, "/register")
    page.get_by_role("textbox", name="Email address").click()
    page.get_by_role("textbox", name="Email address").fill("profile@prova.it")
    page.get_by_role("textbox", name="Email address").press("Tab")
    page.get_by_role("textbox", name="Password", exact=True).fill("banana1234!")
    page.get_by_role("textbox", name="Password", exact=True).press("Tab")
    page.get_by_role("textbox", name="Password confirmation").fill("banana1234!")
    page.get_by_role("textbox", name="Name", exact=True).click()
    page.get_by_role("textbox", name="Name", exact=True).fill("profile")
    page.get_by_label("Newsletter").select_option("o")
    page.get_by_role("textbox", name="Surname").click()
    page.get_by_role("textbox", name="Surname").fill("test")
    page.get_by_role("checkbox", name="Authorisation").check()
    submit(page)

    go_to(page, live_server, "/debug")
    go_to(page, live_server, "/join")

    name_input = page.get_by_role("textbox", name="Organization name", exact=True)
    name_input.fill("Profile Test")
    page.locator("#id_profile").wait_for(state="visible")
    load_image(page, "#id_profile")
    page.locator("#slug").fill("profiletest")
    submit(page)

    just_wait(page)
    go_to(page, live_server, "/debug/profiletest")
    expect(page.locator("#banner")).to_contain_text("Profile Test")

    # Mark every configurable profile field as optional
    go_to(page, live_server, "/manage/profile")
    _set_all_profile_fields(page, "o")
    submit_confirm(page)

    # Fill in every available profile field from the user profile page
    go_to(page, live_server, "/profile")
    just_wait(page)
    expected_optional = _fill_profile_form(page, round_num=1)
    submit(page)
    expect(page.locator(".errorlist")).to_have_count(0)

    # Reload and verify the saved values match what was entered
    go_to(page, live_server, "/profile")
    just_wait(page)
    _verify_profile_form(page, expected_optional)

    # Mark every configurable profile field as mandatory, and re-save
    go_to(page, live_server, "/manage/profile")
    _set_all_profile_fields(page, "m")
    submit_confirm(page)

    # Reload and verify every field config has actually been updated to mandatory
    go_to(page, live_server, "/manage/profile")
    selects = page.locator("table select")
    for i in range(selects.count()):
        expect(selects.nth(i)).to_have_value("m")

    # Change every value and re-save, now that the fields are mandatory
    go_to(page, live_server, "/profile")
    just_wait(page)
    expected_mandatory = _fill_profile_form(page, round_num=2)
    submit(page)
    expect(page.locator(".errorlist")).to_have_count(0)

    # Reload and verify every field has actually been updated
    go_to(page, live_server, "/profile")
    just_wait(page)
    _verify_profile_form(page, expected_mandatory)
