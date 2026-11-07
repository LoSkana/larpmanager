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

"""Steps shared by the guide video storyboards."""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from larpmanager.models.association import Association
from larpmanager.models.event import Event
from larpmanager.models.member import Member, Membership
from larpmanager.tests.utils import fill_date, fill_tinymce, get_modal_iframe, logout

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from larpmanager.tests.playwright.guide_videos.director import Director

CONFIRM = re.compile(r"^\s*(Confirm|Submit)\s*$", re.IGNORECASE)


def prepare_data(organization: str) -> None:
    """Replace test labels that would be visible on camera."""
    Association.objects.update(name=organization)
    Event.objects.get(slug="test").delete()
    Member.objects.filter(user__email="user@test.it").update(name="Alice", surname="Stone")
    Membership.objects.filter(member__user__email="user@test.it").update(compiled=True)


def feature_checkbox(page: Any, name: str) -> Any:
    """Return the checkbox of a feature."""
    return page.locator(".feature_checkbox").filter(has=page.get_by_text(name, exact=True)).get_by_role("checkbox")


def create_event(director: Director, name: str, start: dt.date, *, parent: str | None = None) -> str:
    """Create an event with open registrations, returning the slug computed by the form.

    The first event of an organization opens its registrations by itself.
    """
    page = director.page
    director.click(page.get_by_role("link", name="New event"), settle=1.0)
    modal = get_modal_iframe(page)
    director.type(modal.locator("#id_form1-name"), name)
    if parent:
        director.say("Link it to the first event of the campaign")
        director.click(modal.locator("#select2-id_form1-parent-container"))
        director.type(modal.get_by_role("searchbox"), parent[:6])
        director.click(modal.get_by_role("option", name=parent, exact=True))
        director.hold(1.5)
        director.click(modal.locator('label[for="id_form2-development_1"]'))
        director.click(modal.locator('label[for="id_form2-registration_status_1"]'))
    fill_date(modal, "#id_form2-start", start.isoformat())
    fill_date(modal, "#id_form2-end", (start + dt.timedelta(days=2)).isoformat())
    slug_field = modal.locator("#slug")
    expect(slug_field).not_to_have_value("")
    slug = slug_field.input_value()
    director.confirm(modal.get_by_role("button", name=CONFIRM))
    page.locator("#lm-modal").wait_for(state="hidden")
    director.hold(1.5)
    return slug


def open_new(director: Director) -> Any:
    """Open the creation modal of the current list."""
    director.click(director.page.get_by_role("link", name="New"), settle=0.8)
    return get_modal_iframe(director.page)


def save_modal(director: Director, modal: Any) -> None:
    """Confirm a modal and wait for it to close."""
    director.confirm(modal.get_by_role("button", name=CONFIRM))
    director.page.locator("#lm-modal").wait_for(state="hidden")
    director.hold(0.4)


def pick_character(director: Director, modal: Any, name: str) -> None:
    """Search a character in a dual list and move it to the selected ones."""
    director.type(modal.locator(".char-dual-available .char-dual-search").first, name[:4])
    director.click(modal.locator(".char-dual-avail-list .char-dual-item").filter(has_text=name).first)


def open_menu(director: Director, name: str) -> None:
    """Open a page from the sidebar."""
    director.click(director.page.locator("#sidebar").get_by_role("link", name=name, exact=True))


def register(director: Director) -> None:
    """Complete the registration form, ending on the event page."""
    page = director.page
    director.confirm(page.get_by_role("button", name="Continue"), settle=1.0)
    director.confirm(page.locator("#register_go"), settle=1.0)


def open_character_form(director: Director, name: str) -> None:
    """Open the character creation form from the sidebar and type the name."""
    page = director.page
    director.click(page.locator("#sidebar").get_by_role("link", name=re.compile("Create your character")))
    director.type(page.locator("#id_name"), name)
    director.hold(0.5)


def submit_character(director: Director, teaser: str, text: str) -> None:
    """Fill the rich text off camera, keeping the raw editors out of sight, and save the character."""
    page = director.page
    with director.off_camera():
        for field, value in (("id_teaser", teaser), ("id_text", text)):
            fill_tinymce(page, field, value)
            page.locator(f'a.my_toggle[tog="f_{field}"]').click()
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.5)


def create_character(director: Director, name: str, teaser: str, text: str) -> None:
    """Create a character from the sidebar with only the default fields."""
    open_character_form(director, name)
    submit_character(director, teaser, text)


def login_as(director: Director, login: Callable[[Any, str], None], path: str) -> Callable[[], None]:
    """Return the off-camera steps that change the logged user."""

    def switch() -> None:
        logout(director.page)
        login(director.page, director.base_url)
        director.goto(path)

    return switch
