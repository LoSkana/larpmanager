"""Dump HTML and a viewport screenshot of pages, to find selectors for new capture steps.

Usage: DUMP_FEATURES="character,faction" DUMP_URLS="orga:test/manage/event/?frame=1,player:test/gallery/" pytest dump_test.py
"""

import os
from pathlib import Path

import pytest
from lm_shots import ORGA, PLAYER, Shooter, activate, seed_base, seed_characters, seed_factions, seed_registrations

pytestmark = pytest.mark.e2e

DUMP_DIR = Path(os.environ.get("DUMP_DIR", "/tmp/lm_dump"))


def test_dump(browser_type, live_server, settings) -> None:
    settings.TINYMCE_DISABLED = False
    base = seed_base()
    sh = Shooter(browser_type, live_server, 0, "dump")
    activate(sh, *filter(None, os.environ.get("DUMP_FEATURES", "").split(",")))
    characters = seed_characters(base["event"])
    seed_factions(base["event"], characters)
    seed_registrations(base["run"], base["members"], characters)
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    for idx, spec in enumerate(filter(None, os.environ.get("DUMP_URLS", "").split(","))):
        who, path = spec.split(":", 1)
        login = {"orga": ORGA, "player": PLAYER}.get(who, who)
        page = sh.goto(sh.page(login), path)
        (DUMP_DIR / f"{idx:02d}.html").write_text(page.content())
        page.screenshot(path=str(DUMP_DIR / f"{idx:02d}.png"), full_page=True)
    sh.browser.close()
