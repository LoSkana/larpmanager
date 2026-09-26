"""Helpers to capture tutorial screenshots with Playwright on the test live server."""

import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import F
from playwright.sync_api import Locator, Page

from larpmanager.cache.config import save_single_config
from larpmanager.models.association import Association
from larpmanager.models.base import Feature
from larpmanager.models.event import Event, Run
from larpmanager.models.form import RegistrationOption, RegistrationQuestion
from larpmanager.models.member import Member, Membership
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationQuota,
    RegistrationSection,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.writing import Character, Faction, FactionType
from larpmanager.tests.utils import _wait_lm_ready

OUT_DIR = Path(__file__).resolve().parents[4] / "tutorial_screenshots"
PASSWORD = "banana"  # noqa: S105
VIEWPORT = {"width": 1280, "height": 800}
MOBILE_VIEWPORT = {"width": 390, "height": 844}
SCALE = 2
PAD = 8

# Removes transient UI that should never appear in a tutorial screenshot
CLEAN_CSS = """
*, *::before, *::after { transition: none !important; animation: none !important; caret-color: transparent !important; }
:focus, :focus-visible { outline: none !important; box-shadow: none !important; }
#one .inner { opacity: 1 !important; }
.jq-toast-wrap, #djDebug, .tooltip, .tippy-box, #sidebar-collapse-btn { display: none !important; }
"""

HIGHLIGHT_CSS = "outline: 3px solid #d9822b !important; outline-offset: 3px !important; border-radius: 4px;"

# Demo cast: login email -> (name, surname, new email)
ORGA = "orga@test.it"
PLAYER = "user@test.it"
PEOPLE = {
    "orga@test.it": ("Anna", "Ferri", "anna.ferri@example.com"),
    "user@test.it": ("Elena", "Ricci", "elena.ricci@example.com"),
    "player@test.it": ("Marco", "Bellini", "marco.bellini@example.com"),
}
NEWCOMER = "paolo.greco@example.com"
EXTRA_PLAYERS = [
    ("Sofia", "Conti", "sofia.conti@example.com"),
    ("Luca", "Moretti", "luca.moretti@example.com"),
    ("Giulia", "Serra", "giulia.serra@example.com"),
    ("Paolo", "Greco", NEWCOMER),
]

ASSOCIATION_NAME = "Test Organization"
EVENT_NAME = "Test Event"
EVENT_START = date(2027, 6, 18)
EVENT_END = date(2027, 6, 20)


def seed_base() -> dict[str, Any]:
    """Rename the test fixtures into the demo setting, returning the main objects."""
    association = Association.objects.first()
    association.name = ASSOCIATION_NAME
    association.save()

    event = Event.objects.get(slug="test")
    event.name = EVENT_NAME
    event.save()

    run = Run.objects.get(event=event)
    run.start = EVENT_START
    run.end = EVENT_END
    run.save()

    members = {}
    for member in Member.objects.select_related("user"):
        login = member.user.email or member.user.username
        if login in PEOPLE:
            name, surname, email = PEOPLE[login]
            member.name, member.surname = name, surname
            member.save()
            member.user.email = email
            member.user.save()
            members[login] = member

    for name, surname, email in EXTRA_PLAYERS:
        user, _created = User.objects.get_or_create(username=email, defaults={"email": email})
        user.set_password(PASSWORD)
        user.save()
        member = Member.objects.get(user=user)
        member.name, member.surname = name, surname
        member.save()
        members[email] = member

    Membership.objects.update(compiled=True)
    refresh()
    return {"association": association, "event": event, "run": run, "members": members}


def set_config(obj: object, name: str, value: Any) -> None:
    """Store a config value on an event, association or member."""
    save_single_config(obj, name, value)
    refresh()


def refresh() -> None:
    """Drop every cached value so pages reflect data written through the ORM."""
    cache.clear()


class Shooter:
    """Captures cropped, retina screenshots for one tutorial."""

    def __init__(self, browser_type: Any, live_server: Any, order: int, slug: str, camera: Path | None = None) -> None:
        self.base_url = live_server.url
        self.prefix = f"{order:03d}_{slug}"
        # Fake camera, so QR scanners render a video preview
        self.browser = browser_type.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                *([f"--use-file-for-fake-video-capture={camera}"] if camera else []),
            ],
        )
        self.pages: dict[str, Page] = {}
        self.index: list[dict[str, Any]] = []
        OUT_DIR.mkdir(exist_ok=True)

    def page(self, login: str, *, mobile: bool = False) -> Page:
        """Return a logged-in page for the given user, creating it on first use."""
        key = f"{login}{'-m' if mobile else ''}"
        if key not in self.pages:
            context = self.browser.new_context(
                viewport=MOBILE_VIEWPORT if mobile else VIEWPORT,
                device_scale_factor=SCALE,
                reduced_motion="reduce",
                locale="en-US",
            )
            context.grant_permissions(["camera"])
            page = context.new_page()
            page.set_default_timeout(30_000)
            self.pages[key] = page
            self.goto(page, "/login/")
            page.locator("#id_username").fill(login)
            page.locator("#id_password").fill(PASSWORD)
            page.get_by_role("button", name="Submit").click()
            _wait_lm_ready(page, timeout=15_000)
        return self.pages[key]

    def goto(self, page: Page, path: str) -> Page:
        """Open a path and strip transient UI."""
        page.goto(f"{self.base_url}/{path.lstrip('/')}")
        _wait_lm_ready(page, timeout=15_000)
        page.add_style_tag(content=CLEAN_CSS)
        page.mouse.move(0, 0)
        return page

    def shot(
        self,
        num: int,
        targets: Locator | list[Locator],
        alt: str,
        *,
        highlight: Locator | None = None,
        pad: int = PAD,
        max_height: int | None = None,
    ) -> None:
        """Save a PNG of the targets (union of their boxes) plus padding, and record it in the index."""
        targets = targets if isinstance(targets, list) else [targets]
        page = targets[0].page
        if highlight is not None:
            highlight.evaluate(f"el => el.setAttribute('style', (el.getAttribute('style') || '') + ';{HIGHLIGHT_CSS}')")

        try:
            in_topbar = any(t.evaluate("el => !!el.closest('#topbar, #menu-mobile')", timeout=5_000) for t in targets)
        except Exception:
            (OUT_DIR / f"{self.prefix}_{num:02d}_FAILED.html").write_text(page.content())
            raise
        if not in_topbar:
            page.add_style_tag(content="#topbar, #menu-mobile { visibility: hidden !important; }")
        page.wait_for_timeout(500)
        viewport = page.viewport_size
        # Grow the viewport to the tallest scrolling area, so nothing is clipped by inner scrollbars
        tallest = page.evaluate("() => Math.max(...[...document.querySelectorAll('*')].map(e => e.scrollHeight))")
        page.set_viewport_size({"width": viewport["width"], "height": min(max(viewport["height"], tallest + 50), 8000)})
        page.evaluate(
            "() => { window.scrollTo(0, 0); document.querySelectorAll('*').forEach(e => { e.scrollTop = 0; }); }"
        )
        page.wait_for_timeout(300)
        try:
            box = self._union_box(targets)
        except Exception:
            fail = OUT_DIR / f"{self.prefix}_{num:02d}_FAILED.html"
            fail.write_text(page.content())
            page.set_viewport_size(viewport)
            raise

        size = page.viewport_size
        height = box["height"] if max_height is None else min(box["height"], max_height)
        x = max(0, box["x"] - pad)
        y = max(0, box["y"] - pad)
        width = min(size["width"] - x, box["width"] + 2 * pad)
        height = min(size["height"] - y, height + 2 * pad)

        name = f"{self.prefix}_{num:02d}.png"
        page.screenshot(path=str(OUT_DIR / name), clip={"x": x, "y": y, "width": width, "height": height})
        page.set_viewport_size(viewport)

        if highlight is not None:
            highlight.evaluate("el => { el.style.outline = ''; el.style.outlineOffset = ''; }")

        self.index.append({"file": name, "num": num, "width": round(width), "height": round(height), "alt": alt})

    @staticmethod
    def _union_box(targets: list[Locator]) -> dict[str, float]:
        """Bounding box covering all the targets, in viewport coordinates."""
        boxes = [b for b in (t.bounding_box(timeout=5_000) for t in targets) if b]
        if not boxes:
            msg = "No visible target"
            raise ValueError(msg)
        left = min(b["x"] for b in boxes)
        top = min(b["y"] for b in boxes)
        right = max(b["x"] + b["width"] for b in boxes)
        bottom = max(b["y"] + b["height"] for b in boxes)
        return {"x": left, "y": top, "width": right - left, "height": bottom - top}

    def close(self) -> None:
        """Write the index of captured images and close the browser."""
        index_path = OUT_DIR / f"{self.prefix}.json"
        # Merge with images captured by other tests of the same tutorial
        entries = {}
        if index_path.exists():
            entries = {item["num"]: item for item in json.loads(index_path.read_text())}
        entries.update({item["num"]: item for item in self.index})
        index_path.write_text(json.dumps(sorted(entries.values(), key=lambda x: x["num"]), indent=2))
        self.browser.close()


def open_select(select: Locator) -> None:
    """Show the options of a native select as an open dropdown, since native popups are not captured."""
    select.evaluate(
        """el => {
            const list = document.createElement('div');
            list.className = 'lm-shot-dropdown';
            const style = getComputedStyle(el);
            list.style.cssText = `width:${el.offsetWidth}px;margin-top:2px;border:1px solid #767676;background:#fff;`
                + `font-family:${style.fontFamily};font-size:${style.fontSize};color:#000;`;
            for (const opt of el.options) {
                const item = document.createElement('div');
                item.textContent = opt.textContent.trim();
                item.style.cssText = 'padding:4px 12px;' + (opt.selected ? 'background:#1967d2;color:#fff;' : '');
                list.appendChild(item);
            }
            el.insertAdjacentElement('afterend', list);
        }"""
    )


def modal_frame(page: Page) -> Any:
    """Return the frame of the currently open inline edit popup."""
    frame = page.locator("#lm-modal iframe")
    frame.wait_for(state="visible")
    content = frame.content_frame
    content.locator("body").wait_for()
    return content


def row(page: Page, field_id: str) -> Locator:
    """Form table row holding the given field."""
    return page.locator(f"#{field_id}_tr").filter(visible=True).first


def row_label(page: Page, label: str) -> Locator:
    """Form table row whose header matches the label."""
    return page.locator("tr").filter(has=page.locator("th", has_text=label)).filter(visible=True).first


CHARACTERS = [
    ("Aldric Vane", "Heir of House Vane, torn between duty and ambition."),
    ("Mira Solen", "Court astronomer who reads omens in the falling stars."),
    ("Tobias Reed", "Smuggler with a debt to the Ashen Guild."),
    ("Lysa Morrow", "Healer from the border villages, looking for her brother."),
    ("Kael Draven", "Captain of the city watch, loyal to whoever pays."),
    ("Nessa Holt", "Apprentice alchemist with a dangerous secret."),
]

FACTIONS = [
    ("House Vane", FactionType.PRIM, [0, 1, 4], "The ruling noble house of the city of Emberfall."),
    ("Ashen Guild", FactionType.PRIM, [2, 3, 5], "Merchants, smugglers and craftsmen of the lower city."),
    ("Scholars", FactionType.TRASV, [1, 5], "Those who study the old texts and the stars."),
    ("The Whisper", FactionType.SECRET, [2, 4], "A secret network trading in stolen letters."),
]


def seed_template(association: Association) -> Event:
    """Create an event template."""
    template, _created = Event.objects.get_or_create(
        association=association, template=True, defaults={"name": "Weekend larp", "slug": "weekendtemplate"}
    )
    refresh()
    return template


def seed_characters(event: Event) -> list[Character]:
    """Create the demo characters, renaming the fixture one into the first."""
    characters = []
    existing = list(Character.objects.filter(event=event).order_by("number"))
    for idx, (name, teaser) in enumerate(CHARACTERS):
        character = existing[idx] if idx < len(existing) else Character(event=event, number=idx + 1)
        character.name = name
        character.teaser = f"<p>{teaser}</p>"
        character.text = f"<p>Private background of {name}.</p>"
        character.save()
        characters.append(character)
    refresh()
    return characters


def seed_factions(event: Event, characters: list[Character]) -> list[Faction]:
    """Create the demo factions and assign their characters."""
    factions = []
    for idx, (name, typ, members, teaser) in enumerate(FACTIONS):
        faction, _created = Faction.objects.get_or_create(
            event=event, name=name, defaults={"number": idx + 1, "typ": typ, "teaser": f"<p>{teaser}</p>"}
        )
        faction.characters.set([characters[i] for i in members])
        factions.append(faction)
    refresh()
    return factions


def seed_registrations(
    run: Run, members: dict[str, Member], characters: list[Character], *, assign: bool = True
) -> list[Registration]:
    """Register the demo players, assigning the first characters in order."""
    ticket = RegistrationTicket.objects.filter(event=run.event).first()
    players = [members[PLAYER]] + [m for key, m in members.items() if key not in (PLAYER, ORGA, NEWCOMER)]
    registrations = []
    for idx, member in enumerate(players):
        registration, _created = Registration.objects.get_or_create(run=run, member=member, defaults={"ticket": ticket})
        if assign and idx < len(characters) - 2:
            RegistrationCharacterRel.objects.get_or_create(registration=registration, character=characters[idx])
            characters[idx].player = member
            characters[idx].save()
        registrations.append(registration)
    # Mark every registration as fully paid, so none is shown as provisional
    Registration.objects.filter(run=run).update(tot_payed=F("tot_iscr"))
    Membership.objects.update(compiled=True, status="a")
    refresh()
    return registrations


def activate(sh: Shooter, *slugs: str) -> None:
    """Activate features through their real activation URL, at organization or event scope."""
    page = sh.page(ORGA)
    for slug in slugs:
        overall = Feature.objects.get(slug=slug).overall
        sh.goto(page, f"manage/features/{slug}/on/" if overall else f"test/manage/features/{slug}/on/")
    refresh()


def banner(page: Page) -> Locator:
    """Page title."""
    return page.locator("#banner h1")


def content(page: Page) -> Locator:
    """Main content of a management or user page."""
    return page.locator("#one .inner > div[class*='page_']").first


def section(page: Page, key: str, *rows: str) -> list[Locator]:
    """Open a configuration section and return its title plus the given rows (or the whole section)."""
    link = page.locator(f"a.my_toggle[tog='sec_{key}']")
    if not link.count():
        link = page.locator("a.my_toggle.section-link", has_text=key).first
        try:
            key = link.get_attribute("tog", timeout=5_000).removeprefix("sec_")
        except Exception:
            (OUT_DIR / f"section_{key}_FAILED.html").write_text(page.content())
            raise
    body = page.locator(f".sec_{key}").first
    page.wait_for_timeout(800)
    if not body.is_visible():
        link.click()
        try:
            body.wait_for(state="visible", timeout=5_000)
        except Exception:
            (OUT_DIR / f"section_{key}_FAILED.html").write_text(page.content())
            raise
    if rows:
        return [link, *[row(page, r) for r in rows]]
    return [link, body]


def seed_tickets(event: Event) -> list[RegistrationTicket]:
    """Name the standard ticket and add a reduced and a patron one."""
    standard = RegistrationTicket.objects.filter(event=event, tier=TicketTier.STANDARD).first()
    standard.name = "Full weekend"
    standard.price = 120
    standard.description = "Three days of play, meals and lodging included"
    standard.save()
    tickets = [standard]
    for number, (name, tier, price) in enumerate(
        [("Reduced", TicketTier.REDUCED, 80), ("Patron", TicketTier.PATRON, 160)]
    ):
        ticket, _created = RegistrationTicket.objects.get_or_create(
            event=event, name=name, defaults={"tier": tier, "price": price, "number": number + 10}
        )
        tickets.append(ticket)
    refresh()
    return tickets


def seed_questions(event: Event, section: RegistrationSection | None = None) -> dict[str, RegistrationQuestion]:
    """Create one registration question per type, with options for the choice ones."""
    specs = {
        "t": ("Allergies", "List any food allergy or intolerance"),
        "p": ("Character wishes", "What would you like to experience during the game?"),
        "e": ("Backstory notes", "Anything the writers should know about your past games"),
        "l": ("Combat experience", "From 1 (never) to 5 (veteran)"),
        "s": ("Lodging", "Where would you like to sleep?"),
        "m": ("Extras", "Optional services"),
    }
    questions = {}
    for order, (typ, (name, descr)) in enumerate(specs.items()):
        question, _created = RegistrationQuestion.objects.get_or_create(
            event=event,
            name=name,
            defaults={
                "typ": typ,
                "description": descr,
                "status": "o",
                "order": 10 + order,
                "max_length": 5 if typ == "l" else 0,
            },
        )
        questions[typ] = question
    options = {
        "s": [
            ("Shared room", "Bunk beds, 6 people", 0, 0),
            ("Tent", "Bring your own tent", 0, 0),
            ("Private room", "", 40, 5),
        ],
        "m": [("Costume rental", "", 25, 0), ("Photo package", "", 10, 0)],
    }
    for typ, rows in options.items():
        for order, (name, descr, price, max_available) in enumerate(rows):
            RegistrationOption.objects.get_or_create(
                event=event,
                question=questions[typ],
                name=name,
                defaults={"description": descr, "price": price, "max_available": max_available, "order": order},
            )
    if section:
        RegistrationQuestion.objects.filter(pk__in=[questions["s"].pk, questions["m"].pk]).update(section=section)
    refresh()
    return questions


def seed_section(event: Event) -> RegistrationSection:
    """Create a registration form section."""
    section, _created = RegistrationSection.objects.get_or_create(
        event=event, name="Logistics", defaults={"description": "<p>Lodging and optional services.</p>", "order": 1}
    )
    refresh()
    return section


def seed_quotas(event: Event) -> None:
    """Create three dynamic payment rates."""
    for number, (quotas, days, surcharge) in enumerate([(1, 0, 0), (2, 45, 0), (3, 60, 10)], start=1):
        RegistrationQuota.objects.get_or_create(
            event=event, number=number, defaults={"quotas": quotas, "days_available": days, "surcharge": surcharge}
        )
    refresh()


def menu(page: Page, *labels: str) -> list[Locator]:
    """Sidebar entries with the given labels."""
    return [
        page.locator("#sidebar a").filter(has=page.locator("span", has_text=label)).filter(visible=True).first
        for label in labels
    ]


def qr_video(png: Path, out: Path) -> Path:
    """Turn a QR code image into a still y4m video, to feed the fake camera."""
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(png),
            "-t",
            "3",
            "-vf",
            "scale=360:360,pad=640:480:(ow-iw)/2:(oh-ih)/2:white,format=yuv420p",
            str(out),
        ],
        check=True,
    )
    return out
