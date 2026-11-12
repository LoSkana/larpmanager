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

"""Guide video: create a staff role, invite a collaborator, and add them to an organization role."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from larpmanager.models.access import RoleInvite
from larpmanager.models.association import Association
from larpmanager.models.event import Event
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.tests.playwright.guide_videos.director import COLLABORATOR, ORGANIZER
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    feature_checkbox,
    login_as,
    open_menu,
    open_new,
    save_modal,
)
from larpmanager.tests.utils import login_orga, logout

if TYPE_CHECKING:
    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Staff and roles"
PACE = 0.7

ORGANIZATION = "Vaelmoor Chronicle"
EVENT = "Vaelmoor: The Sundering"
EVENT_ROLE = "Registrations"
EVENT_PERMISSIONS = ("Registrations", "Tickets", "Form")
ORGANIZATION_ROLE = "Treasurer"
COLLABORATOR_EMAIL = "elena.marsh@vaelmoor.example"
COLLABORATOR_NAME = "Elena Marsh"
PASSWORD = "banana"


def prepare_data() -> None:
    """Rename test labels, and turn the test user into a collaborator who never shared data with the organization."""
    Association.objects.update(name=ORGANIZATION)
    event = Event.objects.get(slug="test")
    event.name = EVENT
    event.save()
    for run in event.runs.all():
        run.save()
    Member.objects.filter(user__email="orga@test.it").update(name="Mira", surname="Hale")
    User.objects.filter(email="user@test.it").update(username=COLLABORATOR_EMAIL, email=COLLABORATOR_EMAIL)
    Member.objects.filter(user__email=COLLABORATOR_EMAIL).update(
        name="Elena", surname="Marsh", email=COLLABORATOR_EMAIL
    )
    Membership.objects.filter(member__user__email=COLLABORATOR_EMAIL).update(
        status=MembershipStatus.EMPTY, compiled=True
    )


def open_invite(director: Director) -> None:
    """Log out and open the link of the invitation email, which asks to log in first."""
    token = RoleInvite.objects.get(email=COLLABORATOR_EMAIL).token
    logout(director.page)
    director.goto(f"/invite/role/{token}/")


def test_roles_video(director: Director) -> None:
    """Record an event role with an invite accepted by a collaborator, then an organization role."""
    page = director.page
    sidebar = page.locator("#sidebar")
    prepare_data()
    login_orga(page, director.base_url)
    director.goto("/test/manage/")
    director.start()

    director.play_as(ORGANIZER)
    director.step("Step 1: open the event roles")
    director.say("Roles decide who manages what in your event")
    director.hold(1.0)
    open_menu(director, "Roles")
    organizer = page.locator("tr", has_text="Organizer")
    director.say("The Organizer role comes with every permission")
    director.spotlight(organizer, 2.5)

    director.step("Step 2: create a role and pick its permissions")
    director.say("Name the role after the job it covers")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), EVENT_ROLE)
    director.say("Check only the pages this team needs")
    for name in EVENT_PERMISSIONS:
        director.check(feature_checkbox(modal, name))
    director.say("More permissions appear as you activate features")
    director.hold(1.5)
    save_modal(director, modal)
    role_row = page.locator("tr", has_text=EVENT_ROLE).filter(has_text="Tickets")
    expect(role_row).to_be_visible()
    director.spotlight(role_row, 2.0)

    director.step("Step 3: invite a collaborator by email")
    director.say("Not in the list yet? Invite them with the envelope")
    director.click(role_row.locator(".fa-envelope"), settle=0.8)
    director.type(page.locator("#email"), COLLABORATOR_EMAIL)
    director.confirm(page.get_by_role("button", name="Send invitation"), settle=1.0)
    pending = page.locator("tr", has_text=EVENT_ROLE).get_by_text("Pending invites")
    expect(pending).to_be_visible()
    director.say("The invite stays pending until it is accepted")
    director.spotlight(pending, 2.5)

    director.play_as(COLLABORATOR, lambda: open_invite(director))
    director.step("Step 4: the collaborator accepts")
    director.say("The link in the email asks to log in first")
    director.type(page.locator("#id_username"), COLLABORATOR_EMAIL)
    director.type(page.locator("#id_password"), PASSWORD)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Accepting shares their profile with your organization")
    director.hold(1.5)
    director.check(page.locator('input[name="data_sharing_consent"]'))
    director.confirm(page.get_by_role("button", name="Accept invitation"), settle=1.2)
    director.say("They see only the pages of their role")
    expect(sidebar.get_by_role("link", name="Accounting", exact=True)).to_have_count(0)
    for name in EVENT_PERMISSIONS:
        link = sidebar.get_by_role("link", name=name, exact=True)
        expect(link).to_be_visible()
        director.spotlight(link, 1.1)

    director.play_as(ORGANIZER, login_as(director, login_orga, "/test/manage/roles/"))
    member_row = page.locator("tr", has_text=EVENT_ROLE).filter(has_text=COLLABORATOR_NAME)
    expect(member_row).to_be_visible()
    director.say("Back in Roles, the invite is now a member")
    director.spotlight(member_row, 2.5)

    director.step("Step 5: give organization wide access")
    director.say("Organization roles cover every event, like accounting")
    director.click(page.locator("#topbar").get_by_role("link", name=ORGANIZATION), settle=0.8)
    open_menu(director, "Roles")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), ORGANIZATION_ROLE)
    director.say("Once someone shares their data, add them directly")
    director.type(modal.get_by_role("searchbox"), COLLABORATOR_NAME[:5])
    director.click(modal.get_by_role("option", name=f"{COLLABORATOR_NAME} - {COLLABORATOR_EMAIL}"))
    director.check(feature_checkbox(modal, "Accounting"))
    director.hold(1.0)
    save_modal(director, modal)
    treasurer = page.locator("tr", has_text=ORGANIZATION_ROLE).filter(has_text=COLLABORATOR_NAME)
    expect(treasurer).to_be_visible()
    director.say("Permissions add up across all their roles")
    director.spotlight(treasurer, 3.0)

    director.stop()
