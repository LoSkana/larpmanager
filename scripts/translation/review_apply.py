"""Bulk-apply high-confidence fixes from a translation_review.py markdown report.

Parses the "## [status] lang — po_file" blocks produced by
`translation_review.py report`, and for entries whose status is
"mistranslation", "placeholder_issue", or "tone_mismatch" and that
carry a `suggested_fix`, overwrites the matching entry's msgstr
directly in the target .po file. Entries without a suggested_fix, or
with status "ambiguous_source" (needs human review), are skipped and
listed at the end.

Usage:
    .venv/bin/python scripts/translation_review_apply.py path/to/review.md [--dry-run]

After applying, recompile catalogs (e.g. `python manage.py compilemessages`)
and re-run `translation_review.py sync` to reset the touched entries to
pending for re-verification.
"""

import argparse
import re
import sys
from pathlib import Path

import polib

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOCALE_ROOT = REPO_ROOT / "larpmanager" / "locale"

APPLICABLE_STATUSES = {"mistranslation", "placeholder_issue", "tone_mismatch"}

HEADER_RE = re.compile(r"^## \[(?P<status>\w+)\] (?P<lang>\S+) . (?P<po_file>\S+)$")
FIELD_RE = re.compile(r"^- (?P<key>\w+): `(?P<value>.*)`$")


def parse_report(text: str) -> list[dict]:
    blocks = re.split(r"\n(?=## \[)", text)
    entries = []
    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue
        header = HEADER_RE.match(lines[0])
        if not header:
            continue
        entry = header.groupdict()
        for line in lines[1:]:
            field = FIELD_RE.match(line)
            if not field:
                continue
            entry[field.group("key")] = field.group("value")
        entries.append(entry)
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", help="path to the review markdown report")
    parser.add_argument("--dry-run", action="store_true", help="print what would change, write nothing")
    args = parser.parse_args()

    entries = parse_report(Path(args.report).read_text())

    by_po: dict[tuple[str, str], list[dict]] = {}
    skipped_status = 0
    skipped_no_fix = 0
    for entry in entries:
        if entry["status"] not in APPLICABLE_STATUSES:
            skipped_status += 1
            continue
        if not entry.get("suggested_fix"):
            skipped_no_fix += 1
            continue
        by_po.setdefault((entry["lang"], entry["po_file"]), []).append(entry)

    applied = 0
    not_found = 0
    for (lang, po_file), fixes in sorted(by_po.items()):
        po_path = LOCALE_ROOT / lang / "LC_MESSAGES" / po_file
        if not po_path.exists():
            print(f"warn: missing {po_path}, skipping {len(fixes)} fixes", file=sys.stderr)
            not_found += len(fixes)
            continue

        po = polib.pofile(str(po_path))
        by_msgid = {e.msgid: e for e in po}
        changed = False
        for fix in fixes:
            po_entry = by_msgid.get(fix["msgid"])
            if po_entry is None:
                print(f"warn: msgid not found in {po_file} ({lang}): {fix['msgid']!r}", file=sys.stderr)
                not_found += 1
                continue
            if args.dry_run:
                print(f"{lang}/{po_file}: {po_entry.msgstr!r} -> {fix['suggested_fix']!r}")
            else:
                po_entry.msgstr = fix["suggested_fix"]
            applied += 1
            changed = True

        if changed and not args.dry_run:
            po.save(str(po_path))

    print(
        f"apply: {applied} applied, {not_found} not found, "
        f"{skipped_status} skipped (ambiguous), {skipped_no_fix} skipped (no suggested_fix)"
    )


if __name__ == "__main__":
    main()
