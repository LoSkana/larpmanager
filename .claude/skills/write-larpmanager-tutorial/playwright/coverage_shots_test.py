"""Tutorial screenshots: features added to existing tutorials, writing extras, event and organization tools."""

import pytest
from lm_shots import (
    ORGA,
    PLAYER,
    Shooter,
    activate,
    banner,
    content,
    refresh,
    section,
    seed_base,
    seed_characters,
    seed_factions,
    seed_registrations,
)

from larpmanager.models.writing import HandoutTemplate, PrologueType

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _real_editor(settings) -> None:
    settings.TINYMCE_DISABLED = False


def _world(sh: Shooter, *features: str) -> dict:
    base = seed_base()
    activate(sh, "character", *features)
    characters = seed_characters(base["event"])
    seed_factions(base["event"], characters)
    seed_registrations(base["run"], base["members"], characters)
    return base


def _form(sh: Shooter, num: int, path: str, alt: str) -> None:
    page = sh.goto(sh.page(ORGA), f"{path}?frame=1")
    rows = page.locator("form tr[id$='_tr']").filter(visible=True)
    sh.shot(num, [rows.first, rows.last], alt, max_height=700)


def test_writing_extras(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 223, "writing-extras")
    base = _world(sh, "prologue", "handout", "speedlarp", "workshop")
    _form(sh, 1, "test/manage/prologue_types/new/", "New prologue type")
    PrologueType.objects.create(event=base["event"], number=1, name="Act I")
    refresh()
    _form(sh, 2, "test/manage/prologues/new/", "New prologue")
    _form(sh, 3, "test/manage/handout_templates/new/", "New handout model")
    HandoutTemplate.objects.create(event=base["event"], number=1, name="Parchment letter")
    refresh()
    _form(sh, 4, "test/manage/handouts/new/", "New handout")
    _form(sh, 5, "test/manage/speedlarps/new/", "New speed larp scene")
    _form(sh, 6, "test/manage/workshops/modules/new/", "New workshop module")
    sh.close()


def test_event_tools(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 415, "event-tools")
    _world(sh, "problems", "milestones", "utils", "onetime_content", "copy")
    _form(sh, 1, "test/manage/problems/new/", "New problem")
    _form(sh, 2, "test/manage/milestones/new/", "New milestone")
    _form(sh, 3, "test/manage/utils/new/", "New hosted file")
    _form(sh, 4, "test/manage/onetimes/content/new/", "New one-time content")
    page = sh.goto(sh.page(ORGA), "test/manage/copy/")
    sh.shot(5, [banner(page), content(page)], "Copy elements from another event", max_height=640)
    sh.close()


def test_organization_tools(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 420, "organization-tools")
    _world(sh, "shuttle", "warehouse", "urlshortner", "app_integration", "logs")
    _form(sh, 1, "manage/urlshortner/new/", "New short URL")
    _form(sh, 2, "manage/warehouse/containers/new/", "New warehouse container")
    _form(sh, 3, "manage/warehouse/items/new/", "New warehouse item")
    page = sh.goto(sh.page(ORGA), "manage/config/app_integration/")
    sh.shot(4, section(page, "App Integration"), "App integration configuration")
    page = sh.goto(sh.page(PLAYER), "shuttle/new/")
    sh.shot(5, [banner(page), content(page)], "Shuttle request form", max_height=700)
    page = sh.goto(sh.page(ORGA), "manage/logs/")
    sh.shot(6, [banner(page), content(page)], "Activity log", max_height=560)
    sh.close()


def test_italian_associations(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 995, "italian-associations")
    _world(sh, "receipts", "volunteer_registry", "fiscal_code_check", "ita_balance", "centauri")
    page = sh.goto(sh.page(ORGA), "manage/config/receipts/")
    sh.shot(1, section(page, "Receipts"), "Receipts configuration")
    page = sh.goto(sh.page(ORGA), "manage/volunteer_registry/")
    sh.shot(2, [banner(page), content(page)], "Register of volunteers", max_height=560)
    page = sh.goto(sh.page(ORGA), "manage/config/centauri/")
    sh.shot(3, section(page, "Easter egg"), "Easter egg configuration")
    sh.close()


def test_feature_sections(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 900, "sections")
    _world(sh, "bring_friend", "treasurer", "translation", "badge", "vote", "new_player", "legal_notice")

    # Registration accounting: bring a friend
    page = sh.goto(sh.page(ORGA), "test/manage/config/bring_friend/")
    sh.shot(1, section(page, "Bring a friend"), "Bring a friend configuration")
    # Accounting: treasurer
    page = sh.goto(sh.page(ORGA), "manage/config/treasurer/")
    sh.shot(2, section(page, "Treasury"), "Treasury appointees")
    # Organization appearance: translations
    _form(sh, 3, "manage/translations/new/", "New custom translation")
    # Users: badges and vote
    _form(sh, 4, "manage/badges/new/", "New badge")
    page = sh.goto(sh.page(ORGA), "manage/config/vote/")
    sh.shot(5, section(page, "Voting"), "Voting configuration")
    sh.close()
