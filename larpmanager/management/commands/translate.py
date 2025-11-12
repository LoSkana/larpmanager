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
from pathlib import Path

import deepl
import polib
from django.conf import settings as conf_settings
from django.core.management.base import BaseCommand


class DeepLLimitExceededError(Exception):
    """Raised when DeepL API usage limit is exceeded."""


class Command(BaseCommand):
    """Translate elements in .po file untraslated, or with fuzzy translation, using deepl."""

    def handle(self, *args, **options) -> None:  # noqa: ARG002
        """Handle the translation command by initializing translator and processing translations."""
        # Initialize DeepL translator and display initial usage
        self.translator = deepl.Translator(conf_settings.DEEPL_API_KEY)
        self.stdout.write(str(self.translator.get_usage()))

        # Set target language mappings for translation
        self.target = {"EN": "EN-GB", "PT": "PT-PT"}

        # Process .po files for translation
        self.go_polib()

        # Display final usage statistics
        self.stdout.write(str(self.translator.get_usage()))

    def translate_entry(self, entry, target_language: str) -> None:
        """Translate a single entry using DeepL API.

        Args:
            entry: The POFile entry to translate
            target_language (str): Target language code (e.g., 'EN', 'PT')

        Raises:
            DeepLLimitExceededError: When DeepL API usage limit is exceeded
            deepl.exceptions.DeepLException: When DeepL API encounters an error

        """
        # Check if DeepL API usage limit has been reached
        usage = self.translator.get_usage()
        if usage.any_limit_reached:
            msg = "LIMIT EXCEEDED!"
            raise DeepLLimitExceededError(msg)

        try:
            # Display the original text to be translated
            self.stdout.write(entry.msgid)

            # Normalize target language code and apply any mappings
            target_language = target_language.upper()
            if target_language in self.target:
                target_language = self.target[target_language]

            # Perform the actual translation using DeepL API
            translation_result = self.translator.translate_text(
                entry.msgid,
                source_lang="EN",
                target_lang=target_language,
            )
            entry.msgstr = str(translation_result)

            # Display the translated result and add delay for API rate limiting
            self.stdout.write(f"-> {entry.msgstr}\n")
            time.sleep(1)
        except deepl.exceptions.DeepLException as exception:
            # Handle DeepL-specific exceptions and log the error
            self.stdout.write(exception)
            self.stdout.write(entry.msgid)

    def go_polib(self) -> None:
        """Process translation files using polib and DeepL API for automatic translation.

        Iterates through all locale directories and translates untranslated
        msgid entries using the DeepL translation service.
        """
        locale_path = Path("larpmanager/locale")
        locale_directories = [directory.name for directory in locale_path.iterdir() if directory.is_dir()]

        for locale_code in locale_directories:
            if locale_code.lower() == "en":
                continue

            po_file_path = locale_path / locale_code / "LC_MESSAGES" / "django.po"

            with open(po_file_path) as file_input:
                file_lines = file_input.read().splitlines(keepends=True)
            first_empty_line_index = file_lines.index("\n")
            file_lines = file_lines[first_empty_line_index:]
            file_lines = ['msgid ""\n', 'msgstr ""\n', '"Content-Type: text/plain; charset=UTF-8"\n', *file_lines]
            with open(po_file_path, "w") as file_output:
                file_output.writelines(file_lines)

            self.stdout.write(f"### LOCALE: {locale_code} ### ")

            po_file = polib.pofile(po_file_path)

            punctuation_symbols = (".", "?", "!", ",")
            has_changed = False
            for entry in po_file:
                if entry.msgstr and entry.msgstr.endswith(punctuation_symbols):
                    if not entry.msgid.endswith(punctuation_symbols):
                        if "fuzzy" in entry.flags:
                            entry.flags.remove("fuzzy")
                        entry.msgstr = entry.msgstr.rstrip(".?!,")
                        has_changed = True

            if has_changed:
                self.save_po(po_file, po_file_path)
                po_file = polib.pofile(po_file_path)

            for entry in po_file.untranslated_entries():
                self.translate_entry(entry, locale_code)

            for entry in po_file.fuzzy_entries():
                entry.flags.remove("fuzzy")
                self.translate_entry(entry, locale_code)

            self.save_po(po_file, po_file_path)

    @staticmethod
    def save_po(po: polib.POFile, po_path: str) -> None:
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
