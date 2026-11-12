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

"""Guide video: control visibility and registrations, add a session and set up the organization."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from larpmanager.models.member import Member
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    create_event,
    feature_checkbox,
    open_menu,
    prepare_data,
    save_modal,
)
from larpmanager.tests.utils import fill_date, get_modal_iframe, login_orga

if TYPE_CHECKING:
    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Managing your event"
PACE = 0.55

ORGANIZATION = "Vaelmoor Chronicle"
EVENT = "Vaelmoor: The Sundering"
WEBSITE = "https://vaelmoor.example.com"
RUN_CARD = ".only_v22 .run-card"

STATUSES = (
    (0, "Hidden: in preparation, only staff and registered participants get in"),
    (1, "Visible: published on the homepage and calendar"),
    (2, "Cancelled: hidden from users and excluded from accounting"),
    (3, "Concluded: archived among past events, registrations frozen"),
)


def prepare_event(director: Director, start: dt.date) -> str:
    """Activate pre-registration and create the event, returning its slug."""
    page = director.page
    open_menu(director, "Features")
    feature_checkbox(page, "Pre-registration").check()
    page.get_by_role("button", name=CONFIRM).click()
    open_menu(director, "Events")
    slug = create_event(director, EVENT, start)
    director.goto(f"/{slug}/manage/")
    return slug


def test_manage_video(director: Director) -> None:
    """Record event status and registration status, a new session, organization features and configuration."""
    page = director.page
    start = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=60)
    prepare_data(ORGANIZATION)
    Member.objects.filter(surname="Test").update(name="Mira", surname="Hale")
    login_orga(page, director.base_url)
    director.goto("/manage")
    prepare_event(director, start)
    director.start()

    director.step("Step 1: choose who sees your event")
    director.say("The Event page holds its status")
    open_menu(director, "Event")
    status = page.locator("#id_form2-development_tr")
    director.click(status.locator(".sl-show"), settle=0.8)
    for index, caption in STATUSES:
        director.say(caption)
        director.spotlight(page.locator(f'label[for="id_form2-development_{index}"]'), 3.0)
    director.say("Keep it Hidden while you prepare")
    director.click(page.locator('label[for="id_form2-development_0"]'))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 2: publish it from the dashboard")
    director.say("Home opens your public calendar")
    director.hold(0.8)
    open_menu(director, "Home")
    director.say("Hidden: the event is gone from the calendar")
    expect(page.locator(RUN_CARD)).to_have_count(0)
    director.hold(2.0)

    director.say("The dashboard has a shortcut for each value")
    director.click(page.locator("#topbar").get_by_role("link", name="Admin"), settle=0.8)
    director.click(page.locator("#topbar").get_by_role("link", name=EVENT, exact=True), settle=0.8)
    director.click(page.locator('a[href$="/quick-development/"]'), settle=0.8)
    modal = get_modal_iframe(page)
    director.say("Publish the event with one click")
    director.click(modal.locator('label[for="id_development_1"]'))
    save_modal(director, modal)
    status_row = page.locator("tr", has_text="Status").filter(has_text="Visible")
    expect(status_row).to_be_visible()
    director.spotlight(status_row, 1.5)

    director.step("Step 3: choose when people register")
    director.say("Registrations work the same way, on the Event page too")
    director.hold(1.5)
    director.click(page.locator('a[href$="/quick-registration/"]'), settle=0.8)
    modal = get_modal_iframe(page)
    director.say("Closed stops signups, Open takes them right away")
    director.spotlight(modal.locator('label[for="id_registration_status_0"]'), 1.8)
    director.spotlight(modal.locator('label[for="id_registration_status_1"]'), 1.8)
    director.say("Pre-registration collects interest before you open")
    director.spotlight(modal.locator('label[for="id_registration_status_2"]'), 2.4)
    director.say("External site sends new participants to your link")
    director.click(modal.locator('label[for="id_registration_status_3"]'))
    expect(modal.locator("#id_register_link")).to_be_visible()
    director.spotlight(modal.locator("#id_register_link_tr"), 2.2)
    director.say("Open on date and Close on date switch by themselves")
    director.click(modal.locator('label[for="id_registration_status_4"]'))
    expect(modal.locator("#id_registration_open")).to_be_visible()
    fill_date(modal, "#id_registration_open", (start - dt.timedelta(days=30)).isoformat())
    director.spotlight(modal.locator("#id_registration_open_tr"), 2.2)
    save_modal(director, modal)
    registrations_row = page.locator("tr", has_text="Registrations").filter(has_text="Open on date")
    expect(registrations_row).to_be_visible()
    director.spotlight(registrations_row, 1.5)

    director.step("Step 4: add a new session")
    director.say("A session repeats the event on new dates")
    director.click(page.locator("#topbar").get_by_role("link", name=ORGANIZATION), settle=0.8)
    open_menu(director, "Events")
    director.click(page.get_by_role("link", name="New session"), settle=1.0)
    modal = get_modal_iframe(page)
    director.say("It shares tickets, form and features with the event")
    director.click(modal.locator("#select2-id_event-container"))
    director.fill(modal.get_by_role("searchbox"), EVENT[:8])
    director.click(modal.get_by_role("option", name=EVENT))
    second_start = start + dt.timedelta(days=28)
    fill_date(modal, "#id_start", second_start.isoformat())
    fill_date(modal, "#id_end", (second_start + dt.timedelta(days=2)).isoformat())
    director.say("Dates, registrations and accounting are its own")
    director.click(modal.locator('label[for="id_development_1"]'))
    director.hold(1.0)
    save_modal(director, modal)
    session = page.locator("tr[id]", has_text=second_start.strftime("%d/%m/%Y"))
    expect(session).to_be_visible()
    director.spotlight(session, 2.0)

    director.step("Step 5: set up your organization")
    director.say("Features add tools for your whole organization")
    director.hold(1.5)
    open_menu(director, "Features")
    director.say("Promotion publishes your events on external sites")
    director.check(feature_checkbox(page, "Promotion"))
    director.hold(1.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Its settings open next: choose what is shared")
    expect(page.locator("#id_publication_crew_tr")).to_be_visible()
    director.spotlight(page.locator("#id_publication_crew_tr"), 1.5)
    director.spotlight(page.locator("#id_publication_cast_tr"), 1.5)
    director.say("Interface chooses what the calendar shows for each event")
    director.click(page.locator("#main_form").get_by_role("link", name="Interface", exact=True))
    director.check(page.locator("#id_calendar_website"))
    director.hold(1.0)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Appearance and Texts shape your public pages")
    sidebar = page.locator("#sidebar")
    director.spotlight(sidebar.get_by_role("link", name="Appearance", exact=True), 1.3)
    director.spotlight(sidebar.get_by_role("link", name="Texts", exact=True), 1.3)
    director.say("The event now has a website field")
    director.click(page.locator("#topbar").get_by_role("link", name=EVENT, exact=True), settle=0.8)
    open_menu(director, "Event")
    director.type(page.locator('input[name$="website"]'), WEBSITE)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Both sessions now link your website")
    open_menu(director, "Home")
    link = page.locator(RUN_CARD).first.get_by_role("link", name="Website")
    expect(link).to_be_visible()
    director.spotlight(page.locator(RUN_CARD).first, 1.8)
    director.spotlight(page.locator(RUN_CARD).last, 1.8)

    director.stop()
