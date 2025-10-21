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
import time
from os import listdir
from os.path import isdir, join
from typing import Any

import deepl
import polib
from django.conf import settings as conf_settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Translate elements in .po file untraslated, or with fuzzy translation, using deepl"""

    def handle(self, *args: Any, **options: Any) -> None:
        """Handle the translation command execution.

        Initializes the DeepL translator, configures target languages,
        and processes PO files for translation.

        Args:
            *args: Variable length argument list passed to the command
            **options: Arbitrary keyword arguments passed to the command

        Returns:
            None
        """
        # Initialize DeepL translator with API key from settings
        self.translator = deepl.Translator(conf_settings.DEEPL_API_KEY)

        # Display initial API usage statistics
        self.stdout.write(str(self.translator.get_usage()))

        # Configure target language mappings for specific locales
        self.target = {"EN": "EN-GB", "PT": "PT-PT"}

        # Process all PO files for translation
        self.go_polib()

        # Display final API usage statistics after processing
        self.stdout.write(str(self.translator.get_usage()))

    def translate_entry(self, entry, tgt: str) -> None:
        """Translate a single entry using DeepL API.

        Args:
            entry: The POFile entry to translate
            tgt (str): Target language code (e.g., 'EN', 'PT')

        Raises:
            Exception: When DeepL API usage limit is exceeded
            deepl.exceptions.DeepLException: When DeepL API encounters an error
        """
        # Check if DeepL API usage limit has been reached
        usage = self.translator.get_usage()
        if usage.any_limit_reached:
            raise Exception("LIMIT EXCEEDED!")

        try:
            # Display the original text to be translated
            self.stdout.write(entry.msgid)

            # Normalize target language code and apply any mappings
            tgt = tgt.upper()
            if tgt in self.target:
                tgt = self.target[tgt]

            # Perform the actual translation using DeepL API
            result = self.translator.translate_text(entry.msgid, source_lang="EN", target_lang=tgt)
            entry.msgstr = str(result)

            # Display the translated result and add delay for API rate limiting
            self.stdout.write(f"-> {entry.msgstr}\n")
            time.sleep(1)
        except deepl.exceptions.DeepLException as e:
            # Handle DeepL-specific exceptions and log the error
            self.stdout.write(e)
            self.stdout.write(entry.msgid)

    def go_polib(self):
        """Process translation files using polib and DeepL API for automatic translation.

        Iterates through all locale directories and translates untranslated
        msgid entries using the DeepL translation service.
        """
        loc_path = "larpmanager/locale"
        locales = [f for f in listdir(loc_path) if isdir(join(loc_path, f))]

        for loc in locales:
            if loc.lower() == "en":
                continue

            po_path = join(loc_path, loc, "LC_MESSAGES", "django.po")

            with open(po_path) as fin:
                data = fin.read().splitlines(True)
            lm = data.index("\n")
            data = data[lm:]
            data = ['msgid ""\n', 'msgstr ""\n', '"Content-Type: text/plain; charset=UTF-8"\n'] + data
            with open(po_path, "w") as fout:
                fout.writelines(data)

            self.stdout.write(f"### LOCALE: {loc} ### ")

            po = polib.pofile(po_path)

            symbols = (".", "?", "!", ",")
            changed = False
            for entry in po:
                if entry.msgstr:
                    if entry.msgstr.endswith(symbols):
                        if not entry.msgid.endswith(symbols):
                            if "fuzzy" in entry.flags:
                                entry.flags.remove("fuzzy")
                            entry.msgstr = entry.msgstr.rstrip(".?!,")
                            changed = True

            if changed:
                self.save_po(po, po_path)
                po = polib.pofile(po_path)

            for entry in po.untranslated_entries():
                self.translate_entry(entry, loc)

            for entry in po.fuzzy_entries():
                entry.flags.remove("fuzzy")
                self.translate_entry(entry, loc)

            self.save_po(po, po_path)

    def save_po(self, po: polib.POFile, po_path: str) -> None:
        """Save a PO file with sorted and deduplicated entries.

        Args:
            po: The PO file object to process
            po_path: Path where the processed PO file will be saved
        """
        # Create new ordered po file with original metadata
        sorted_po = polib.POFile()
        sorted_po.metadata = po.metadata

        # Sort entries by message ID length first, then alphabetically
        sorted_entries = sorted(po, key=lambda element: (len(element.msgid), element.msgid))

        # Use set to track already processed message IDs for deduplication
        cache = set()
        for entry in sorted_entries:
            # Skip duplicate entries based on message ID
            if entry.msgid in cache:
                continue
            cache.add(entry.msgid)
            sorted_po.append(entry)

        # Save the processed PO file to the specified path
        sorted_po.save(po_path)
