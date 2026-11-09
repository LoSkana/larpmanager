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

"""Guide video: character sheet PDFs, from the standard sheet to a fully customized layout."""

from __future__ import annotations

import datetime as dt
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image, ImageDraw, ImageFilter
from playwright.sync_api import expect

from larpmanager.cache.config import get_event_config
from larpmanager.models.base import Feature
from larpmanager.models.event import Event
from larpmanager.models.writing import Character, Faction, FactionType, Relationship
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    create_event,
    feature_checkbox,
    open_menu,
    prepare_data,
)
from larpmanager.tests.utils import login_orga

if TYPE_CHECKING:
    from typing import Any

    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Character sheet PDFs"
PACE = 0.8

ORGANIZATION = "Greywater Larp Society"
EVENT = "The Silent Abbey"
CHARACTER = "Brother Anselm"
ASSETS_DIR = Path(".guide_videos/pdf_assets")
# SIL Open Font License fonts, from the fonts-sil-gentium-basic package
FONT_DIR = Path("/usr/share/fonts/truetype/gentium-basic")
TITLE_FONT = FONT_DIR / "GenBkBasBI.ttf"
TEXT_FONT = FONT_DIR / "GenBkBasR.ttf"

COLORS = (
    ("id_pdf_color_title", "#6B1F1F"),
    ("id_pdf_color_link", "#6B1F1F"),
    ("id_pdf_color_bold", "#6B1F1F"),
    ("id_pdf_color_border", "#8C6A3F"),
)
SHEET_URL = re.compile(r"/manage/characters/[^/]+/pdf/sheet/$")
CUSTOM_CSS = "#char_name { text-transform: uppercase; border-bottom: 2px solid #8C6A3F; }"

CHARACTERS = (
    (
        CHARACTER,
        "<p>Keeper of the abbey library, and of the books nobody is allowed to read.</p>",
        (
            "<p>For <b>thirty years</b> you have guarded the forbidden shelves of the abbey. "
            "The abbot trusts you more than anyone, and that trust is the only thing that "
            "keeps the old manuscripts away from the fire.</p>"
            "<p>Three nights ago a book went missing from the locked room. Only two keys exist: "
            "yours, and the one the abbot wears on his chest. You have told no one yet.</p>"
            "<p>You know Sister Maud has been reading by candlelight long after vespers. "
            "You also know that Brother Tomas owes money to the wrong people in the village.</p>"
        ),
    ),
    (
        "Sister Maud",
        "<p>The herbalist of the abbey, quiet, patient, and far too curious.</p>",
        "<p>You found a page torn from a forbidden book inside your herb basket.</p>",
    ),
    (
        "Brother Tomas",
        "<p>The cellarer, who keeps the wine, the grain, and a few secrets.</p>",
        "<p>A merchant from the village has been asking you about the library.</p>",
    ),
)
RELATIONSHIPS = (
    ("Sister Maud", "<p>She reads at night, and you pretend not to see the light under her door.</p>"),
    ("Brother Tomas", "<p>He laughs too loudly lately. Debts make men careless.</p>"),
)


def require_fonts() -> None:
    """Fail the run when the fonts are missing."""
    for font in (TITLE_FONT, TEXT_FONT):
        if not font.exists():
            pytest.fail(f"Font not found: {font}. Install fonts-sil-gentium-basic.")


def parchment() -> Path:
    """Draw a fictional parchment page with an ornamental frame."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    width, height = 1240, 1754
    page = Image.new("RGB", (width, height), (238, 224, 192))
    noise = Image.new("L", (width, height))
    generator = random.Random(11)  # noqa: S311
    noise.putdata([generator.randint(0, 255) for _unused in range(width * height)])
    stains = noise.filter(ImageFilter.GaussianBlur(18))
    page = Image.composite(Image.new("RGB", page.size, (214, 190, 146)), page, stains.point(lambda v: max(0, v - 120)))

    vignette = Image.new("L", (width, height), 0)
    ImageDraw.Draw(vignette).rectangle((90, 90, width - 90, height - 90), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(120))
    page = Image.composite(page, Image.new("RGB", page.size, (176, 140, 92)), vignette)

    draw = ImageDraw.Draw(page)
    frame = (110, 3), (130, 1)
    for inset, line in frame:
        draw.rectangle((inset, inset, width - inset, height - inset), outline=(120, 84, 48), width=line)
    for x, y in ((110, 110), (width - 110, 110), (110, height - 110), (width - 110, height - 110)):
        draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=(120, 84, 48))
    path = ASSETS_DIR / "parchment.jpg"
    page.save(path, quality=90)
    return path


def prepare_event(slug: str) -> None:
    """Enable the writing features, and write the characters of the abbey."""
    event = Event.objects.get(slug=slug)
    for feature in ("character", "faction", "relationships"):
        event.features.add(Feature.objects.get(slug=feature))
    characters = {
        name: Character.objects.create(event=event, name=name, teaser=teaser, text=text)
        for name, teaser, text in CHARACTERS
    }
    faction = Faction.objects.create(
        event=event,
        name="The Keepers of the Word",
        typ=FactionType.PRIM,
        teaser="<p>The monks entrusted with the library and its secrets.</p>",
    )
    faction.characters.set(characters.values())
    for target, text in RELATIONSHIPS:
        Relationship.objects.create(source=characters[CHARACTER], target=characters[target], text=text)
    event.save()


def open_sheet(director: Director, caption: str, seconds: float) -> None:
    """Open the complete sheet of the character in the browser PDF viewer, then come back."""
    page = director.page
    link = page.locator("a.link", has_text="Complete sheet (Pdf)")
    # The link downloads the file: without the attribute, the browser shows it instead
    link.evaluate("(element) => element.removeAttribute('download')")
    director.click(link, settle=2.5)
    director.say(caption)
    expect(page).to_have_url(SHEET_URL)
    director.hold(seconds)
    with director.off_camera():
        page.go_back()
        page.wait_for_load_state("load")
        expect(page.locator("#sheet_pdf")).to_be_visible()
        page.locator("#char").select_option(label=CHARACTER)


def wait_saved(page: Any) -> None:
    """Wait for the options to be saved by the page."""
    status = page.locator("#pdf_autosave")
    expect(status).to_have_text("Saved")
    page.wait_for_load_state("networkidle")


def test_pdf_video(director: Director) -> None:
    """Record the activation of the PDF sheets, the base options and the advanced customization."""
    page = director.page
    require_fonts()
    background = parchment()
    prepare_data(ORGANIZATION)
    login_orga(page, director.base_url)
    director.goto("/manage/events")
    slug = create_event(director, EVENT, dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=60))
    prepare_event(slug)
    director.goto(f"/{slug}/manage/")
    director.start()

    director.step("Step 1: turn on PDF generation")
    director.say("Activate PDF generation in the event features")
    open_menu(director, "Features")
    director.check(feature_checkbox(page, "PDF generation"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Sheets, gallery and profiles are now generated for you")
    expect(page.locator("#sheet_pdf")).to_be_visible()
    director.hold(2.0)

    director.step("Step 2: try the standard sheet")
    director.say("Pick a character to try the generation")
    director.select(page.locator("#char"), CHARACTER)
    director.hold(0.5)
    director.say("The complete sheet has everything the player should read")
    open_sheet(director, "Without any option, it is a clean standard layout", 4.0)

    director.step("Step 3: set the page layout")
    director.say("Choose the page format, and the margin in centimeters")
    director.select(page.locator("#id_pdf_page_size"), "a5")
    director.type(page.locator("#id_pdf_margin"), "2")
    director.say("Header and footer add names and page numbers")
    director.check(page.locator("#id_pdf_header"))
    director.check(page.locator("#id_pdf_footer"))
    director.say("Sizes are in percent of the standard one")
    director.type(page.locator("#id_pdf_size_title"), "130")
    director.type(page.locator("#id_pdf_size_text"), "105")
    director.say("Then the colors of titles, links, highlights and lines")
    for field, color in COLORS:
        # Typed one key at a time, the partial codes would be saved as invalid colors
        director.click(page.locator(f"#{field}"), settle=0.3)
        director.fill(page.locator(f"#{field}"), color)
        # A click outside closes the picker: the label would focus the field and open it again
        director.click(page.locator("tr").filter(has=page.locator(f"#{field}")).locator(".helptext"), settle=0.4)
    director.say("Every change is saved right away, no need to confirm")
    wait_saved(page)
    director.spotlight(page.locator("#pdf_autosave"), 1.5)
    director.say("Open the sheet again to see the result")
    open_sheet(director, "Same content, now with your layout", 3.5)

    director.step("Step 4: add a background and your fonts")
    director.say("The background image covers the whole page")
    director.upload(page.locator("#id_pdf_background"), background)
    director.say("Upload a TTF font for titles, and one for the text")
    director.upload(page.locator("#id_pdf_font_title"), TITLE_FONT)
    director.upload(page.locator("#id_pdf_font_text"), TEXT_FONT)
    wait_saved(page)
    director.hold(0.8)
    director.say("Fonts and background give the sheet the mood of your event")
    open_sheet(director, "A sheet that feels part of the game", 4.5)

    director.step("Step 5: fine-tune with your own CSS")
    director.say("CSS covers anything the options do not")
    director.type(page.locator("#id_page_css"), CUSTOM_CSS)
    director.click(page.locator('label[for="id_page_css"]'), settle=0.4)
    wait_saved(page)
    director.say("Here the name gets capitals and an underline")
    open_sheet(director, "Your CSS has the last word on every element", 3.5)

    director.step("Step 6: print and share the sheets")
    director.say("The lightweight sheet is a plain version, cheaper to print")
    director.spotlight(page.locator("a.link", has_text="Lightweight sheet (Pdf)"), 2.0)
    director.say("Download any set of sheets at once, or all of them as a ZIP")
    director.spotlight(page.locator("#sheet_pdf table").first, 2.5)
    director.say("Players download their own sheet from their character page")
    assert get_event_config(Event.objects.get(slug=slug).id, "page_css") == CUSTOM_CSS
    director.hold(2.5)

    director.stop()
