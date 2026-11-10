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

"""Guide video: logo, theme, colors, background, cover, font, texts and navigation of the public pages."""

from __future__ import annotations

import datetime as dt
import math
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from playwright.sync_api import expect

from larpmanager.models.association import Association
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    create_event,
    open_menu,
    open_new,
    prepare_data,
    save_modal,
)
from larpmanager.tests.utils import login_orga

if TYPE_CHECKING:
    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Your event's look"
PACE = 0.6
RICH_TEXT = True

ORGANIZATION = "Ironwood Larp Guild"
EVENT = "Ironwood: The Ember Court"
SANS_DIR = Path("/usr/share/fonts/truetype/dejavu")
TITLE_FONT = Path("/usr/share/fonts/truetype/gentium/Gentium-I.ttf")
ASSETS_DIR = Path(".guide_videos/appearance_assets")
RUN_CARD = ".only_v22 .run-card"

THEMES = (
    ("aurora", "Aurora is a full light theme"),
    ("eclipse", "Eclipse is a full dark theme"),
    ("nebula", "Nebula, the default, mixes dark and light"),
)
COLORS = (("id_pri_rgb", "#F5E6D3"), ("id_sec_rgb", "#2B1B24"), ("id_ter_rgb", "#F0A04B"))
WELCOME = "Welcome to the Ember Court! Read the rules before you sign up."
BUTTON_NAME = "Rulebook"
BUTTON_TOOLTIP = "Read the rules of the Ember Court"
BUTTON_LINK = "https://ironwood.example.com/rules"
BUTTON_ICON = "fa-solid fa-book"


def require_title_font() -> Path:
    """Return the title font file, failing the run when it is missing."""
    if not TITLE_FONT.exists():
        pytest.fail(f"Title font not found: {TITLE_FONT}. Install fonts-sil-gentium or change TITLE_FONT.")
    return TITLE_FONT


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    """Return a vertical gradient image."""
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for row in range(height):
        ratio = row / max(height - 1, 1)
        color = tuple(int(top[index] + (bottom[index] - top[index]) * ratio) for index in range(3))
        draw.line([(0, row), (width, row)], fill=color)
    return image


def _ember_logo(size: int) -> Image.Image:
    """Draw a round emblem with a flame inside a ring."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 16
    draw.ellipse(
        (margin, margin, size - margin, size - margin), fill=(34, 22, 30), outline=(214, 140, 60), width=size // 20
    )
    center = size / 2
    flame = []
    for step in range(120):
        angle = step / 120 * 2 * math.pi
        radius = size * 0.22 * (1 - 0.55 * math.sin(angle / 2) ** 6)
        flame.append((center + radius * math.sin(angle) * 0.8, center + size * 0.05 - radius * math.cos(angle) * 1.4))
    draw.polygon(flame, fill=(232, 120, 40))
    inner = [(center + (x - center) * 0.5, center + size * 0.1 + (y - center - size * 0.05) * 0.5) for x, y in flame]
    draw.polygon(inner, fill=(250, 200, 90))
    return image


def demo_assets() -> dict[str, Path]:
    """Create the logo, the event cover and a plain background, all fictional."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    bold = ImageFont.truetype(str(SANS_DIR / "DejaVuSerif-Bold.ttf"), 96)
    small = ImageFont.truetype(str(SANS_DIR / "DejaVuSerif.ttf"), 44)

    logo_path = ASSETS_DIR / "logo.png"
    _ember_logo(512).save(logo_path)

    cover = _gradient((1600, 1000), (60, 20, 40), (230, 110, 50))
    draw = ImageDraw.Draw(cover)
    draw.ellipse((620, 380, 980, 740), fill=(255, 196, 110))
    hills = [
        (0, 1000),
        (0, 720),
        (300, 640),
        (560, 700),
        (820, 610),
        (1100, 690),
        (1380, 620),
        (1600, 680),
        (1600, 1000),
    ]
    draw.polygon(hills, fill=(40, 18, 28))
    for left in (640, 760, 880):
        draw.rectangle((left, 520, left + 70, 700), fill=(40, 18, 28))
        draw.polygon([(left - 10, 520), (left + 35, 450), (left + 80, 520)], fill=(40, 18, 28))
    draw.text((800, 180), "THE EMBER COURT", font=bold, fill=(255, 236, 210), anchor="mm")
    draw.text((800, 280), ORGANIZATION, font=small, fill=(255, 220, 190), anchor="mm")
    cover_path = ASSETS_DIR / "cover.png"
    cover.save(cover_path)

    background = _gradient((1920, 1080), (30, 18, 26), (70, 34, 30))
    noise = Image.new("RGB", background.size)
    generator = random.Random(7)  # noqa: S311
    noise.putdata([(value, value, value) for value in (generator.randint(0, 40) for _unused in range(1920 * 1080))])
    background = Image.blend(background, noise.filter(ImageFilter.GaussianBlur(6)), 0.12)
    background_path = ASSETS_DIR / "background.jpg"
    background.save(background_path, quality=90)

    return {"logo": logo_path, "cover": cover_path, "background": background_path}


def test_appearance_video(director: Director) -> None:
    """Record the organization logo and theme, the event look, its texts and navigation, and the public pages."""
    page = director.page
    title_font = require_title_font()
    assets = demo_assets()
    prepare_data(ORGANIZATION)
    Association.objects.update(profile="")
    login_orga(page, director.base_url)
    director.goto("/manage/events")
    create_event(director, EVENT, dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=60))
    director.goto("/manage/")
    director.start()

    director.step("Step 1: add your logo")
    director.say("The logo belongs to the organization settings")
    open_menu(director, "Organization")
    director.upload(page.locator("#id_profile"), assets["logo"])
    director.hold(0.8)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("It now marks your organization in the top bar")
    logo = page.locator("#topbar .tv22-pill-img").first
    expect(logo).to_be_visible()
    director.spotlight(page.locator("#topbar .tv22-pill").first, 2.0)

    director.step("Step 2: pick a theme")
    director.say("Appearance styles every page of your organization")
    open_menu(director, "Appearance")
    theme = page.locator("#id_theme")
    for value, caption in THEMES:
        director.say(caption)
        director.select(theme, value)
        director.hold(2.0)

    director.step("Step 3: make it yours with Halo")
    director.say("Halo unlocks your own background and colors")
    director.select(theme, "halo")
    expect(page.locator("#id_background_tr")).to_be_visible()
    director.hold(1.0)
    director.say("Pick a calm background, with little detail")
    director.upload(page.locator("#id_background"), assets["background"])
    director.hold(0.6)
    director.say("Then the text, highlight and link colors")
    for field, color in COLORS:
        director.type(page.locator(f"#{field}"), color)
        director.click(page.locator(f"#lbl_{field}"), settle=0.4)
        director.hold(0.6)
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.5)
    saved = Association.objects.get(name=ORGANIZATION)
    assert [saved.pri_rgb.upper(), saved.sec_rgb.upper(), saved.ter_rgb.upper()] == [color for _field, color in COLORS]

    director.step("Step 4: give the event its own look")
    director.say("Each event can change the look of its own pages")
    director.click(page.locator("#topbar").get_by_role("link", name=EVENT, exact=True), settle=0.8)
    open_menu(director, "Appearance")
    director.say("The cover shows on the calendar and the event page")
    director.upload(page.locator("#id_cover"), assets["cover"])
    director.hold(0.6)
    director.say("A title font gives the event its own voice")
    director.upload(page.locator("#id_font"), title_font)
    director.hold(0.6)
    director.say("Event settings win over the organization ones")
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.5)

    director.step("Step 5: write your own texts")
    director.say("Texts add your words to pages and emails")
    open_menu(director, "Texts")
    modal = open_new(director)
    director.type(modal.frame_locator('iframe[id^="id_text"]').locator("body"), WELCOME)
    director.say("Its type sets where it appears: here, the registration page")
    director.select(modal.locator("#id_typ"), "r")
    director.hold(0.8)
    save_modal(director, modal)
    text_row = page.locator("tr", has_text="Registration form")
    expect(text_row).to_be_visible()
    director.spotlight(text_row, 1.5)

    director.step("Step 6: add a navigation button")
    director.say("Navigation adds your own links for participants")
    open_menu(director, "Navigation")
    modal = open_new(director)
    director.type(modal.locator("#id_name"), BUTTON_NAME)
    director.type(modal.locator("#id_tooltip"), BUTTON_TOOLTIP)
    director.type(modal.locator("#id_link"), BUTTON_LINK)
    director.select(modal.locator("#id_icon"), BUTTON_ICON)
    save_modal(director, modal)
    button_row = page.locator("tr", has_text=BUTTON_NAME)
    expect(button_row).to_be_visible()
    director.spotlight(button_row, 1.5)

    director.step("Step 7: see your public pages")
    director.say("Home shows the event card with its cover")
    open_menu(director, "Home")
    card = page.locator(RUN_CARD).first
    expect(card.locator("img.run-card-cover")).to_be_visible()
    director.spotlight(card, 2.2)
    director.say("The event page has its cover, colors and title font")
    director.click(card.locator(".run-card-cover-link"), settle=1.0)
    expect(page.locator(".event-cover-side")).to_be_visible()
    expect(page.locator("body")).to_have_class(re.compile(r"\btheme-halo\b"))
    director.hold(2.5)
    director.say("Your button joins the sidebar")
    sidebar_button = page.locator("#sidebar").get_by_role("link", name=BUTTON_NAME)
    expect(sidebar_button).to_be_visible()
    director.spotlight(sidebar_button, 1.8)
    director.say("And your text welcomes people as they register")
    open_menu(director, "Register")
    welcome = page.get_by_text(WELCOME)
    expect(welcome).to_be_visible()
    director.spotlight(welcome, 2.2)

    director.stop()
