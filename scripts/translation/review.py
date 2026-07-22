"""Translation QA pipeline for LarpManager .po files.

Parses .po files into a sqlite db, then hands chunks to Claude Code
itself for review against the curated Italian reference (no separate
API key/billing - runs on Claude Code's own session), and stores
verdicts back in the db for reporting.

Usage (inside a Claude Code session):
    python scripts/translation/review.py sync
    python scripts/translation/review.py next-chunk --lang fr
    # Claude reads the chunk file, reviews it per SYSTEM_PROMPT below,
    # writes the JSON array of verdicts to the configured result_path
    python scripts/translation/review.py ingest
    python scripts/translation/review.py report --lang fr

Fixed paths (db, chunk, state, result) and chunk size live in
scripts/review_config.json, override with --config.

.venv/bin/python scripts/translation/review.py sync                # parse .po -> db
.venv/bin/python scripts/translation/review.py next-chunk --lang fr # writes chunk_path + state_path
# Claude Code reads chunk_path, reviews per SYSTEM_PROMPT (in the script), writes result_path
.venv/bin/python scripts/translation/review.py ingest               # loads result_path into db, deletes chunk state
.venv/bin/python scripts/translation/review.py report --lang fr
"""

import argparse
import json
import sqlite3
from pathlib import Path

import polib

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "review_config.json"

SYSTEM_PROMPT = """You are a translation quality reviewer for a Django web application
(LarpManager, a LARP event management platform). For each entry you
receive, you are given three strings:

- msgid: the original English source string
- msgstr_it: an Italian translation, curated by a native speaker -
  treat this as a reliable reference, not just another translation.
  This field is empty when msgstr_target IS the Italian translation
  itself (Italian has no separate reference to check against) - in
  that case judge msgstr_target against msgid alone.
- msgstr_target: the translation in the target language, which you
  must review

Your job is to classify each entry and flag problems. Use both the
English source AND the Italian reference to judge meaning: if the
target translation differs from both, it is likely a real error. If
the English and Italian references themselves diverge in meaning or
implication, the source string is ambiguous - the target may have
simply chosen a different (still valid) reading. Distinguish these
two cases explicitly. When msgstr_it is empty, judge solely against
msgid.

Specific LARP terms: Award (refers to awarding XP, in italian "assegnazioni"), Badges (in the context of achievements),
Casting (assigning characters / roles to players / participants), Pools (character/resource pools),
Plot (quest/mission/storyline), Handout (setting/world-building knowledge), Safety (tieni termine inglese), Speed larp (tieni termine inglese)

Categories (status field):
- "ok": translation is accurate and natural
- "mistranslation": target meaning diverges from both EN and IT
  without justification
- "ambiguous_source": EN and IT references disagree or the source
  string permits multiple readings; target picked one of them
- "placeholder_issue": a variable/placeholder (e.g. %(name)s, {count},
  %s) is missing, altered, or reordered in the target string
- "tone_mismatch": meaning is correct but register/formality is off
  (e.g. informal where formal is expected, or vice versa)

Rules:
- Never invent problems. If a translation is a reasonable rendering,
  mark it "ok" even if the wording differs stylistically.
- For "ambiguous_source", the note MUST explain what the two possible
  readings are and which one the target chose.
- For "placeholder_issue", quote the exact placeholder that is
  affected.
- Preserve UI tone: LarpManager strings are for event organizers and
  players, generally informal-professional, not bureaucratic.
- Do not translate or alter any string yourself - only review.

Output: return ONLY a JSON array, no prose before or after, no
markdown code fences. Omit entries whose status is "ok" entirely -
do not include them in the array. Include only entries with a
problem, one object each:

{
  "msgid": "<copied from input>",
  "lang": "<copied from input>",
  "status": "mistranslation | ambiguous_source | placeholder_issue | tone_mismatch",
  "note": "<short explanation>",
  "suggested_fix": "<corrected msgstr_target>"
}

Any msgid from the input not present in your output array is assumed
"ok" - this is how you skip the "ok" cases.
"""

SEVERITY_ORDER = {
    "mistranslation": 0,
    "placeholder_issue": 0,
    "ambiguous_source": 1,
    "tone_mismatch": 2,
}


PATH_KEYS = ("db_path", "chunk_path", "state_path", "result_path")


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        config = json.load(f)
    for key in PATH_KEYS:
        config[key] = str((REPO_ROOT / config[key]).resolve())
    return config


def get_db(config: dict) -> sqlite3.Connection:
    conn = sqlite3.connect(config["db_path"])
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY,
            lang TEXT NOT NULL,
            po_file TEXT NOT NULL,
            msgid TEXT NOT NULL,
            msgstr_it TEXT,
            msgstr_target TEXT,
            status TEXT DEFAULT 'pending',
            note TEXT,
            suggested_fix TEXT,
            reviewed_at TIMESTAMP,
            model TEXT,
            UNIQUE(lang, po_file, msgid)
        )
    """)
    conn.commit()
    return conn


def cmd_sync(config: dict) -> None:
    conn = get_db(config)
    reference_lang = config["reference_lang"]

    reference_maps = {}
    for po_path in sorted((REPO_ROOT / "larpmanager" / "locale").rglob("*.po")):
        if po_path.parent.parent.name != reference_lang:
            continue
        rel = po_path.relative_to(REPO_ROOT / "larpmanager" / "locale" / reference_lang / "LC_MESSAGES")
        po = polib.pofile(str(po_path))
        reference_maps[str(rel)] = {e.msgid: e.msgstr for e in po if e.msgid}

    inserted = updated = reset = 0
    for po_path in sorted((REPO_ROOT / "larpmanager" / "locale").rglob("*.po")):
        lang = po_path.parent.parent.name
        rel = po_path.relative_to(REPO_ROOT / "larpmanager" / "locale" / lang / "LC_MESSAGES")
        # reference lang has no separate reference to check against - it IS the target
        ref_map = {} if lang == reference_lang else reference_maps.get(str(rel), {})
        po = polib.pofile(str(po_path))

        for entry in po:
            if not entry.msgid or not entry.msgstr or entry.fuzzy:
                continue
            row = conn.execute(
                "SELECT msgstr_target, status FROM entries WHERE lang=? AND po_file=? AND msgid=?",
                (lang, str(rel), entry.msgid),
            ).fetchone()
            msgstr_it = ref_map.get(entry.msgid, "")

            if row is None:
                conn.execute(
                    "INSERT INTO entries (lang, po_file, msgid, msgstr_it, msgstr_target, status) "
                    "VALUES (?, ?, ?, ?, ?, 'pending')",
                    (lang, str(rel), entry.msgid, msgstr_it, entry.msgstr),
                )
                inserted += 1
            elif row[0] != entry.msgstr:
                conn.execute(
                    "UPDATE entries SET msgstr_target=?, msgstr_it=?, status='pending', "
                    "note=NULL, suggested_fix=NULL, reviewed_at=NULL WHERE lang=? AND po_file=? AND msgid=?",
                    (entry.msgstr, msgstr_it, lang, str(rel), entry.msgid),
                )
                reset += 1
            else:
                conn.execute(
                    "UPDATE entries SET msgstr_it=? WHERE lang=? AND po_file=? AND msgid=?",
                    (msgstr_it, lang, str(rel), entry.msgid),
                )
                updated += 1

    conn.commit()
    conn.close()
    print(f"sync: inserted={inserted} reset_to_pending={reset} unchanged={updated}")


def _estimate_tokens(row) -> int:
    """Rough token estimate for an entry (~4 chars/token) plus JSON field overhead."""
    _id, msgid, msgstr_it, msgstr_target = row
    chars = len(msgid or "") + len(msgstr_it or "") + len(msgstr_target or "")
    return chars // 4 + 12


def cmd_next_chunk(config: dict, lang: str | None) -> None:
    """Write next pending batch to chunk_path, sized to fill target_tokens (capped at
    max_chunk_size entries), plus a state file mapping msgid -> row id for ingest."""
    conn = get_db(config)
    query = "SELECT lang, po_file FROM entries WHERE status='pending'"
    params: list = []
    if lang:
        query += " AND lang=?"
        params.append(lang)
    group = conn.execute(query + " GROUP BY lang, po_file ORDER BY lang, po_file LIMIT 1", params).fetchone()

    if group is None:
        conn.close()
        print("next-chunk: no pending entries")
        return

    group_lang, po_file = group
    max_chunk_size = config.get("max_chunk_size", config["chunk_size"])
    target_tokens = config.get("target_tokens")
    candidates = conn.execute(
        "SELECT id, msgid, msgstr_it, msgstr_target FROM entries "
        "WHERE lang=? AND po_file=? AND status='pending' ORDER BY id LIMIT ?",
        (group_lang, po_file, max_chunk_size),
    ).fetchall()
    conn.close()

    if target_tokens:
        rows = []
        used = 0
        for row in candidates:
            row_tokens = _estimate_tokens(row)
            if rows and used + row_tokens > target_tokens:
                break
            rows.append(row)
            used += row_tokens
    else:
        rows = candidates[: config["chunk_size"]]

    payload = [{"msgid": r[1], "msgstr_it": r[2], "msgstr_target": r[3], "lang": group_lang} for r in rows]
    Path(config["chunk_path"]).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    Path(config["state_path"]).write_text(
        json.dumps({"lang": group_lang, "po_file": po_file, "ids_by_msgid": {r[1]: r[0] for r in rows}})
    )

    print(f"next-chunk: wrote {len(rows)} entries ({group_lang}/{po_file}) to {config['chunk_path']}")
    print(f"next-chunk: review per the SYSTEM_PROMPT in this script, write verdicts to {config['result_path']}")
    print("next-chunk: then run: python scripts/translation/review.py ingest")


def cmd_ingest(config: dict) -> None:
    state_path = Path(config["state_path"])
    result_path = Path(config["result_path"])
    if not state_path.exists():
        raise SystemExit("ingest: no state file, run next-chunk first")
    if not result_path.exists():
        raise SystemExit(f"ingest: no result file at {result_path}")

    state = json.loads(state_path.read_text())
    results = json.loads(result_path.read_text())

    conn = get_db(config)
    updated = 0
    flagged_msgids = set()
    for result in results:
        row_id = state["ids_by_msgid"].get(result["msgid"])
        if row_id is None:
            continue
        flagged_msgids.add(result["msgid"])
        conn.execute(
            "UPDATE entries SET status=?, note=?, suggested_fix=?, reviewed_at=CURRENT_TIMESTAMP, model=? WHERE id=?",
            (result["status"], result.get("note", ""), result.get("suggested_fix", ""), config["model"], row_id),
        )
        updated += 1

    ok_ids = [row_id for msgid, row_id in state["ids_by_msgid"].items() if msgid not in flagged_msgids]
    if ok_ids:
        placeholders = ",".join("?" * len(ok_ids))
        conn.execute(
            f"UPDATE entries SET status='ok', note='', suggested_fix='', "
            f"reviewed_at=CURRENT_TIMESTAMP, model=? WHERE id IN ({placeholders})",
            (config["model"], *ok_ids),
        )
    conn.commit()
    conn.close()

    state_path.unlink()
    result_path.unlink()
    print(
        f"ingest: flagged {updated}, marked {len(ok_ids)} ok ({state['lang']}/{state['po_file']})"
    )


def cmd_pending_langs(config: dict) -> None:
    """Print distinct languages that still have pending entries, one per line, ordered by lang."""
    conn = get_db(config)
    rows = conn.execute("SELECT DISTINCT lang FROM entries WHERE status='pending' ORDER BY lang").fetchall()
    conn.close()
    for (lang,) in rows:
        print(lang)


def cmd_report(config: dict, lang: str | None, out: str | None) -> None:
    conn = get_db(config)
    query = "SELECT lang, po_file, msgid, msgstr_it, msgstr_target, status, note, suggested_fix FROM entries WHERE status NOT IN ('ok', 'pending')"
    params: list = []
    if lang:
        query += " AND lang=?"
        params.append(lang)
    rows = conn.execute(query, params).fetchall()
    conn.close()

    rows.sort(key=lambda r: SEVERITY_ORDER.get(r[5], 9))

    lines = [f"# Translation review report ({len(rows)} issues)\n"]
    for r in rows:
        lang_, po_file, msgid, msgstr_it, msgstr_target, status, note, suggested_fix = r
        lines.append(f"## [{status}] {lang_} - {po_file}")
        lines.append(f"- msgid: `{msgid}`")
        lines.append(f"- it: `{msgstr_it}`")
        lines.append(f"- target: `{msgstr_target}`")
        lines.append(f"- note: {note}")
        if suggested_fix:
            lines.append(f"- suggested_fix: `{suggested_fix}`")
        lines.append("")

    report = "\n".join(lines)
    if out:
        Path(out).write_text(report)
        print(f"report: written to {out}")
    else:
        print(report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="path to config json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sync", help="parse .po files into the db")

    p_chunk = sub.add_parser("next-chunk", help="write the next pending batch to chunk_path for Claude to review")
    p_chunk.add_argument("--lang", default=None, help="restrict to one language (default: first pending)")

    sub.add_parser("ingest", help="load result_path verdicts (written by Claude) back into the db")

    sub.add_parser("pending-langs", help="list languages that still have pending entries")

    p_report = sub.add_parser("report", help="print/save flagged entries")
    p_report.add_argument("--lang", default=None)
    p_report.add_argument("--out", default=None, help="output file (default: stdout)")

    args = parser.parse_args()
    config = load_config(Path(args.config))

    if args.command == "sync":
        cmd_sync(config)
    elif args.command == "next-chunk":
        cmd_next_chunk(config, args.lang)
    elif args.command == "ingest":
        cmd_ingest(config)
    elif args.command == "pending-langs":
        cmd_pending_langs(config)
    elif args.command == "report":
        cmd_report(config, args.lang, args.out)


if __name__ == "__main__":
    main()
