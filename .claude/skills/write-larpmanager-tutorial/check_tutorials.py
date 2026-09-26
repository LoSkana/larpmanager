"""Check a tutorials JSON export against the writing rules in SKILL.md.

Usage: .venv/bin/python .claude/skills/write-larpmanager-tutorial/check_tutorials.py [export.json] [--slug SLUG]

Reports, per tutorial:
- bold labels not found among the English UI strings (label drift);
- redirect links whose URL does not resolve, or without the "Event >" / "Organization >" scope;
- links to other tutorials or sections that do not exist;
- images without alt text or size, and old-style screenshots outside /media/tutorial_screenshots/;
- banned wording ("the system", "X panel", typos seen before) and editor leftovers.
"""

import argparse
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PO_FILE = ROOT / "larpmanager" / "locale" / "en" / "LC_MESSAGES" / "django.po"

BANNED = {
    "the system": r"\b[Tt]he system\b",
    "X panel": r"\b\w+ panel\b",
    "typo": r"\b(informations|payed|Payed|manuall|WYSISWYG|Organiazion|an page|these number|the have)\b|it's (page|private|edit)",
    "sign up as noun": r"\b(a|the|new|their|each|every|all) sign-?ups?\b",
    "player (use participant)": r"\bplayers?\b",
    "run (use session)": r"\bruns?\b",
}

LEFTOVERS = {
    "&nbsp;": r"&nbsp;",
    "inline style": r'style="',
    "styled span": r"<span",
    "editor attributes": r"data-(start|end|is-last-node)",
    "typographic entity": r"&(rsquo|lsquo|ldquo|rdquo|mdash|ndash);",
    "field list with <br>": r"<p><strong>[^<]+</strong>:?[^<]*<br>",
    "empty paragraph": r"<p>\s*</p>",
    "image inside heading": r"<h2>\s*<img",
}

# Bold terms checked by hand: untranslated labels, examples, external names
ACCEPTED_LABELS = {
    "get started", "association css", "event css", "larpdatabase", "larpradar", "ildb - api key", "ildb - team id",
    "lightweight sheet", "xhtml2pdf documentation", "single-session", "hit points", "concept", "mind", "muscle",
    "inactive (e)", "inactive (j)", "inactive (u)", "pending sync", "promote to admin", "remove admin",
    "remove from guild",
}

# Screenshots kept from the previous set on purpose (see screenshots.md)
ACCEPTED_OLD_SCREENSHOTS = {
    "20260819112015_232dde853e514ce7b74ec23385d73ff4", "20260915140908_71a29ba58dbc470b847fb34fc",
    "20260915141140_76757d84a0cb4233833e69189", "20260915155308_69a6126f7d3147cd96c5dcd45",
    "20260915141502_fb87da03918a48dcb1ba8faa3", "20260401112817_7353d0e8456a473180f424f68",
    "20260401113010_8844731d33db45fb88d9eb4c5",
}

# Tutorials quoted from external authors: wording rules are not applied
QUOTED_TUTORIALS = {"ensemble"}

# UI labels and feature names containing words otherwise flagged by BANNED
PROTECTED_PHRASES = ["New player", "Player relationships", "Player selection", "Publish players", "runs an algorithm",
                     "runs a simulation", 'called "runs"', "organization runs", "how to run"]

# Bold terms that are examples or concepts, not UI labels
LABEL_ALLOWLIST_PATTERNS = [r'^".*"$', r"^#", r"^@", r"^\^", r"^\d"]


def slugify(text: str) -> str:
    """Anchor id generated client-side from an h2 text."""
    text = unicodedata.normalize("NFD", html.unescape(re.sub(r"<[^>]+>", "", text)))
    text = re.sub(r"[̀-ͯ]", "", text).lower().strip()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^\w\-]+", "", text)
    return re.sub(r"-+", "-", text).strip("-")


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def ui_strings() -> set[str]:
    """English UI strings, plus model field names shown as-is when they have no translated verbose name."""
    po = PO_FILE.read_text(encoding="utf-8")
    strings = {m.lower().strip() for m in re.findall(r'msgid "(.*?)"', po)}
    from django.apps import apps  # noqa: PLC0415

    for model in apps.get_app_config("larpmanager").get_models():
        for model_field in model._meta.get_fields():  # noqa: SLF001
            name = getattr(model_field, "verbose_name", None)
            if name:
                strings.add(str(name).lower().strip())
    return strings


def resolver():  # noqa: ANN201
    """Return a function telling whether a redirect path resolves in the Django URLconf."""
    sys.path.insert(0, str(ROOT))
    import os  # noqa: PLC0415

    import django  # noqa: PLC0415

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
    django.setup()
    from django.urls import Resolver404, resolve  # noqa: PLC0415

    def resolves(path: str) -> bool:
        if path.startswith("event/"):
            path = "test/" + path.removeprefix("event/")
        try:
            resolve("/" + path)
        except Resolver404:
            return False
        return True

    return resolves


def check(tutorials: list[dict], only: str | None) -> int:
    resolves = resolver()
    strings = ui_strings()
    by_slug = {t["slug"]: t for t in tutorials if not t.get("deleted")}
    anchors = {slug: {slugify(h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", t["descr"], re.S)} for slug, t in by_slug.items()}
    total = 0
    for tutorial in sorted(by_slug.values(), key=lambda t: int(t["order"])):
        if only and tutorial["slug"] != only:
            continue
        descr = tutorial["descr"]
        text = plain(descr)
        issues = []

        # Tutorial names in links to other tutorials are not UI labels
        labels_descr = re.sub(r'<a href="https://larpmanager\.com/tutorials/[^"]*"[^>]*>.*?</a>', "", descr, flags=re.S)
        for term in re.findall(r"<strong>(.*?)</strong>", labels_descr):
            label = plain(term).strip(":,. ")
            if not label or ">" in label or len(label) > 40:
                continue
            if any(re.match(p, label) for p in LABEL_ALLOWLIST_PATTERNS):
                continue
            if label.lower() not in strings and label.lower() not in ACCEPTED_LABELS:
                issues.append(f"label not in UI strings: {label!r}")

        for href, label in re.findall(r'<a href="https://larpmanager\.com/redirect/([^"]*)"[^>]*>(.*?)</a>', descr, re.S):
            if not resolves(href):
                issues.append(f"redirect does not resolve: {href}")
            label = plain(label)
            if "/features/" not in href and not label.startswith(("Event >", "Organization >")):
                issues.append(f"link without scope: {label!r} -> {href}")

        for slug, anchor in re.findall(r'larpmanager\.com/tutorials/([\w-]+)/(?:#([\w-]+))?"', descr):
            if slug not in by_slug:
                issues.append(f"link to missing tutorial: {slug}")
            elif anchor and anchor not in anchors[slug]:
                issues.append(f"link to missing section: {slug}#{anchor}")

        for img in re.findall(r"<img[^>]*>", descr):
            if 'alt=""' in img or "alt=" not in img:
                issues.append(f"image without alt: {img[:80]}")
            if "width=" not in img or "height=" not in img:
                issues.append(f"image without size: {img[:80]}")
            if "/media/tutorial_screenshots/" not in img and not any(k in img for k in ACCEPTED_OLD_SCREENSHOTS):
                issues.append(f"old screenshot: {img[:80]}")
        if "[SCREENSHOT" in descr:
            issues.append("screenshot placeholder left")

        checked_text = text
        for phrase in PROTECTED_PHRASES:
            checked_text = re.sub(re.escape(phrase), "", checked_text, flags=re.I)
        for name, pattern in BANNED.items():
            if tutorial["slug"] in QUOTED_TUTORIALS:
                break
            found = sorted({m.group(0) for m in re.finditer(pattern, checked_text)})
            if found:
                issues.append(f"{name}: {', '.join(found[:5])} ({len(re.findall(pattern, checked_text))})")
        for name, pattern in LEFTOVERS.items():
            count = len(re.findall(pattern, descr))
            if count:
                issues.append(f"{name}: {count}")

        headings = [plain(h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", descr, re.S)]
        for heading in headings:
            words = heading.split()
            if len(words) > 1 and any(w[0].isupper() and not w.isupper() for w in words[1:] if w.isalpha() and w not in PROPER_NOUNS):
                issues.append(f"heading not in sentence case: {heading!r}")
        if len(text.split()) > 250 and not headings:
            issues.append("no sections (h2)")
        if "<hr>" not in descr:
            issues.append("no <hr> separators")
        if "Related tutorials" not in text:
            issues.append("no related tutorials")

        if issues:
            print(f"\n== {tutorial['order']} {tutorial['slug']} ({len(issues)})")
            for issue in issues:
                print(f"   - {issue}")
            total += len(issues)
    print(f"\nTotal issues: {total}")
    return total


# Words that keep their capital letter in sentence-case headings
PROPER_NOUNS = {
    "LarpManager", "PDF", "QR", "XP", "CSS", "ILDB", "VAT", "Ensemble", "Google", "URL", "CSV", "SSO", "JWT", "API",
    "Stripe", "PayPal", "SumUp", "Satispay", "Redsys", "LarpDatabase", "LarpRadar", "Italian", "RUNTS", "LAOG",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("export", nargs="?", default=str(Path(__file__).resolve().parent / "LarpManagerTutorial-2026-09-26.json"))
    parser.add_argument("--slug")
    args = parser.parse_args()
    tutorials = json.loads(Path(args.export).read_text(encoding="utf-8"))
    check(tutorials, args.slug)


if __name__ == "__main__":
    main()
