import subprocess
from pathlib import Path

import polib

symbol = "?"

subprocess.run(["git", "stash", "--include-untracked", "--", "*.po"], check=True)

# 1: Generate .po files using makemessages
subprocess.run(
    [
        "django-admin",
        "makemessages",
        "-a",
        "--no-location",
        "--no-wrap",
        "--extension=py,html",
        "-i",
        "venv",
        "-i",
        "static",
        "-i",
        "locale",
        "--verbosity",
        "1",
    ],
    cwd="larpmanager",
    check=True,
)

# 2: Get untraslated
po_path = Path("larpmanager/locale/it/LC_MESSAGES/django.po")
po = polib.pofile(str(po_path))
untranslated = set([entry.msgid.lower() for entry in po if not entry.translated() or entry.fuzzy])

# 3: Git stash .po files
subprocess.run(["git", "stash", "--include-untracked", "--", "*.po"], check=True)

# 4: Locate all .po files in subdirectories
po_files = list(Path("larpmanager").rglob("*.po"))

# 5: Process each .po file
for po_file in po_files:
    print(f"processing: {po_file}")
    po = polib.pofile(str(po_file))
    changed = False
    for entry in po:
        if not entry.msgid.strip().endswith(symbol):
            continue

        new_msgid = entry.msgid.rstrip(symbol).rstrip()

        if new_msgid.lower() not in untranslated:
            continue

        new_msgstr = entry.msgstr.rstrip(symbol).rstrip()
        entry.msgid = new_msgid
        entry.msgstr = new_msgstr
        changed = True
    if changed:
        po.save()
