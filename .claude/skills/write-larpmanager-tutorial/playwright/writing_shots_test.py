"""Tutorial screenshots: factions and plots."""

import pytest
from lm_shots import (
    ORGA,
    PLAYER,
    Shooter,
    activate,
    refresh,
    row,
    row_label,
    seed_base,
    seed_characters,
    seed_factions,
    seed_registrations,
    set_config,
)

from larpmanager.models.writing import Plot, PlotCharacterRel

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _real_editor(settings) -> None:
    settings.TINYMCE_DISABLED = False


def test_factions(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 210, "factions")
    activate(sh, "character", "faction")
    characters = seed_characters(base["event"])
    seed_factions(base["event"], characters)
    seed_registrations(base["run"], base["members"], characters)

    page = sh.goto(sh.page(ORGA), "test/manage/factions/new/?frame=1")
    sh.shot(1, [row(page, "id_typ"), row(page, "id_characters")], "New faction form")

    page = sh.goto(sh.page(PLAYER), "test/gallery/")
    sh.shot(5, [page.locator("h1.title").first, page.locator(".gallery").nth(1)], "Gallery grouped by faction")

    set_config(base["event"], "writing_field_visibility", "True")
    page = sh.goto(sh.page(ORGA), "test/manage/event/?frame=1")
    sh.shot(2, row_label(page, "Factions"), "Faction fields visible to players")
    sh.close()


def test_characters(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 170, "characters")
    activate(sh, "character", "faction")
    characters = seed_characters(base["event"])
    seed_factions(base["event"], characters)
    seed_registrations(base["run"], base["members"], characters)

    page = sh.goto(sh.page(PLAYER), "test/gallery/")
    sh.shot(
        16,
        [
            page.locator("h1.title").first,
            page.locator("h1.title", has_text="Registrants").locator("xpath=following-sibling::*[1]"),
        ],
        "Character gallery",
    )

    page = sh.goto(sh.page(PLAYER), "test/search/")
    page.locator("a.my_toggle[tog='factions']").click()
    page.locator("#factions a", has_text="House Vane").click()
    page.wait_for_timeout(300)
    results = page.locator("#search-results")
    sh.shot(17, [page.locator("a.my_toggle[tog='istr']"), results], "Search with a faction filter", max_height=700)
    sh.close()


def test_plots(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 220, "plots")
    activate(sh, "character", "plot")
    characters = seed_characters(base["event"])
    seed_registrations(base["run"], base["members"], characters)

    page = sh.goto(sh.page(ORGA), "test/manage/plots/new/?frame=1")
    sh.shot(1, [row(page, "id_name"), row(page, "id_characters")], "New plot form")

    plot = Plot.objects.create(
        event=base["event"],
        number=1,
        name="The Stolen Crown",
        teaser="<p>The crown of Emberfall has vanished the night before the coronation.</p>",
        text="<p>Only a few know who took it, and why.</p>",
    )
    PlotCharacterRel.objects.create(
        plot=plot, character=characters[0], text="<p>You were the last to see the crown, and you lied about it.</p>"
    )
    refresh()

    page = sh.goto(sh.page(ORGA), f"test/manage/plots/{plot.uuid}/edit/?frame=1")
    role = page.locator("tr[id^='id_char_role_']:visible").first
    role.locator("a.my_toggle").first.click()
    sh.shot(2, [row(page, "id_characters"), role], "Plot with a character role")

    page = sh.goto(sh.page(ORGA), f"test/manage/characters/{characters[0].uuid}/edit/?frame=1")
    row_label(page, "The Stolen Crown").locator("a.my_toggle").first.click()
    sh.shot(3, row_label(page, "The Stolen Crown"), "Plot role in the character form")

    page = sh.goto(sh.page(PLAYER), f"test/character/{characters[0].uuid}/")
    title = page.locator("h1", has_text="The Stolen Crown")
    sh.shot(
        4,
        [title, title.locator("xpath=following-sibling::div[contains(@class,'plot')][1]")],
        "Plot shown in the character sheet",
    )
    sh.close()
