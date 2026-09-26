"""Tutorial screenshots: organization and event setup (tutorials 1-85)."""

import pytest
from lm_shots import (
    NEWCOMER,
    ORGA,
    PLAYER,
    Shooter,
    activate,
    banner,
    content,
    refresh,
    row,
    section,
    seed_base,
    seed_characters,
    seed_factions,
    seed_registrations,
    seed_template,
    seed_tickets,
)

from larpmanager.models.event import Event, EventButton

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _real_editor(settings) -> None:
    settings.TINYMCE_DISABLED = False


def test_create_organization(browser_type, live_server) -> None:
    seed_base()
    sh = Shooter(browser_type, live_server, 1, "create-organization")

    # 1: the get-started page lives on the main site, keep the existing screenshot
    page = sh.goto(sh.page(ORGA), "manage/")
    sh.shot(2, page.locator("#tv22-user-pills"), "Organization and event selector")
    sh.shot(3, page.locator("#tv22-switch"), "User and Admin switch")
    sh.shot(
        4, [page.locator("#sidebar .sidebar-start"), page.locator("#sidebar a[title='Texts']")], "Management sidebar"
    )
    sh.shot(6, [page.locator("#sidebar .roles"), page.locator("#sidebar a[title='Tutorials']")], "Help links")

    page = sh.goto(sh.page(ORGA, mobile=True), "manage/")
    sh.shot(5, page.locator("#menu-mobile"), "Mobile navigation bar")
    sh.close()


def test_player_information(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 10, "player-information")
    activate(sh, "character")
    characters = seed_characters(base["event"])
    seed_registrations(base["run"], base["members"], characters)

    page = sh.goto(sh.page(ORGA), "manage/profile/")
    sh.shot(1, [banner(page), row(page, "id_first_aid")], "Profile fields")

    page = sh.goto(sh.page(ORGA), "test/manage/sensitive/")
    sh.shot(2, [banner(page), content(page).locator("tbody tr").nth(1)], "Users data of the event")

    page = sh.goto(sh.page(ORGA), "test/manage/registrations/")
    sh.shot(
        3,
        page.locator(".dt-container").first,
        "Registrations with the sensitive data icon",
        highlight=page.locator("i.fa-eye").first,
    )
    sh.close()


def test_organization_roles(browser_type, live_server) -> None:
    seed_base()
    sh = Shooter(browser_type, live_server, 20, "organization-roles")
    page = sh.goto(sh.page(ORGA), "manage/roles/")
    sh.shot(1, [banner(page), content(page)], "Organization roles")
    page = sh.goto(sh.page(ORGA), "manage/roles/new/?frame=1")
    sh.shot(2, [row(page, "id_name"), page.locator("tr[id^='id_perm_']").nth(3)], "New organization role")
    sh.close()


def test_organization_appearance(browser_type, live_server) -> None:
    seed_base()
    sh = Shooter(browser_type, live_server, 30, "organization-appearance")
    page = sh.goto(sh.page(ORGA), "manage/appearance/")
    sh.shot(1, [banner(page), content(page)], "Organization appearance")
    page = sh.goto(sh.page(ORGA), "manage/texts/new/?frame=1")
    sh.shot(2, page.locator("form table").first, "New organization text")
    page = sh.goto(sh.page(ORGA), "manage/config/interface/")
    sh.shot(3, section(page, "interface", "id_calendar_past_events", "id_calendar_tagline"), "Interface configuration")
    sh.close()


def test_advanced_features(browser_type, live_server) -> None:
    seed_base()
    sh = Shooter(browser_type, live_server, 40, "advanced-features")
    page = sh.goto(sh.page(ORGA), "manage/features/")
    sh.shot(1, [banner(page), content(page)], "Organization features", max_height=560)
    page = sh.goto(sh.page(ORGA), "test/manage/features/")
    sh.shot(2, [banner(page), content(page)], "Event features", max_height=560)
    sh.close()


def test_manage_events(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 50, "manage-events")
    activate(sh, "character", "template", "campaign")

    page = sh.goto(sh.page(ORGA), "manage/events/new/?frame=1")
    sh.shot(1, [row(page, "id_form1-name"), row(page, "id_form1-description")], "New event form")
    sh.shot(2, [row(page, "id_form2-start"), row(page, "id_form2-registration_status")], "Session dates and status")

    page = sh.goto(sh.page(ORGA), "test/manage/")
    sh.shot(3, page.locator("#orga_event_widget"), "Event card in the dashboard")

    page = sh.goto(sh.page(ORGA), "manage/runs/new/?frame=1")
    sh.shot(4, [row(page, "id_event"), row(page, "id_development")], "New session form")

    seed_template(base["association"])
    page = sh.goto(sh.page(ORGA), "manage/template/new/?frame=1")
    sh.shot(5, page.locator("form table").first, "New template form", max_height=620)
    page = sh.goto(sh.page(ORGA), "manage/template/")
    sh.shot(6, [banner(page), content(page)], "Templates list")

    page = sh.goto(sh.page(ORGA), "test/manage/event/?frame=1")
    sh.shot(7, row(page, "id_form1-parent"), "Parent campaign field")
    sh.close()


def test_event_roles(browser_type, live_server) -> None:
    seed_base()
    sh = Shooter(browser_type, live_server, 70, "event-roles")
    page = sh.goto(sh.page(ORGA), "test/manage/roles/")
    sh.shot(1, [banner(page), content(page)], "Event roles")
    page = sh.goto(sh.page(ORGA), "test/manage/roles/new/?frame=1")
    sh.shot(2, [row(page, "id_name"), page.locator("tr[id^='id_perm_']").nth(3)], "New event role")
    sh.close()


def test_event_appearance(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 80, "event-appearance")
    activate(sh, "character")
    characters = seed_characters(base["event"])
    seed_factions(base["event"], characters)

    page = sh.goto(sh.page(ORGA), "test/manage/appearance/")
    sh.shot(1, [banner(page), content(page)], "Event appearance")
    page = sh.goto(sh.page(ORGA), "test/manage/texts/new/?frame=1")
    sh.shot(2, page.locator("form table").first, "New event text")
    page = sh.goto(sh.page(ORGA), "test/manage/buttons/new/?frame=1")
    sh.shot(3, page.locator("form table").first, "New navigation button")

    EventButton.objects.create(
        event=base["event"],
        number=1,
        name="Rulebook",
        tooltip="Game rules",
        link="https://example.com/rules/",
        icon="fa-solid fa-book",
    )
    refresh()
    page = sh.goto(sh.page(PLAYER), "test/")
    sh.shot(4, page.locator("#sidebar .sidebar-section").first, "Navigation button in the event menu")

    page = sh.goto(sh.page(ORGA), "test/manage/config/gallery/")
    sh.shot(5, section(page, "gallery"), "Gallery configuration")
    sh.close()


def test_promotion(browser_type, live_server) -> None:
    seed_base()
    sh = Shooter(browser_type, live_server, 85, "promotion")
    activate(sh, "publisher")
    page = sh.goto(sh.page(ORGA), "manage/config/publication/")
    sh.shot(1, section(page, "promotion"), "Promotion configuration")
    page = sh.goto(sh.page(ORGA), "test/manage/promotion/")
    sh.shot(2, [banner(page), content(page)], "Event promotion data", max_height=600)
    sh.close()


def test_event_pages(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 50, "manage-events")
    seed_tickets(base["event"])
    Event.objects.filter(pk=base["event"].pk).update(
        description="<p>Three days in the city of Emberfall, the night before the coronation. The crown is missing.</p>"
    )
    refresh()

    page = sh.goto(sh.page(NEWCOMER), "")
    card = content(page).locator("[class*=run-card]").first
    sh.shot(8, [banner(page), card], "Upcoming events on the organization home page")
    page = sh.goto(sh.page(NEWCOMER), "test/")
    sh.shot(9, [banner(page), content(page)], "Event page for participants", max_height=620)
    page = sh.goto(sh.page(NEWCOMER), "test/register/")
    sh.shot(10, [banner(page), content(page)], "Registration page", max_height=620)
    sh.close()
