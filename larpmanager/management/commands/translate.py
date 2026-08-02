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
from typing import Any

import deepl
import polib
from django.conf import settings as conf_settings
from django.core.management.base import BaseCommand

from larpmanager.management.commands.utils import check_virtualenv
from scripts.translation.translate import AgentTranslationError, translate_entries

# Languages supporting formality parameter
SUPPORTED_FORMALITY_LANGS = {"IT", "DE", "FR", "ES", "PT", "PT-BR", "PT-PT", "NL", "PL", "RU", "JA", "ZH"}


class DeepLLimitExceededError(Exception):
    """Raised when DeepL API usage limit is exceeded."""


class Command(BaseCommand):
    """Translate untranslated or fuzzy .po entries using an LLM agent or DeepL."""

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002
        """Handle the translation command by initializing translator and processing translations."""
        # Ensure we're running inside a virtual environment
        check_virtualenv()
        self.llm_agent = getattr(conf_settings, "LLM_TRANSLATION_AGENT", None)
        self.llm_model = getattr(conf_settings, "LLM_TRANSLATION_MODEL", None)
        self.llm_max_tokens = max(1, int(getattr(conf_settings, "LLM_TRANSLATION_MAX_TOKENS", 6000)))
        self.translator = None
        if self.llm_agent:
            self.stdout.write(f"Using {self.llm_agent} agent for translations.")
        else:
            self.translator = deepl.Translator(conf_settings.DEEPL_API_KEY)
            self.stdout.write(str(self.translator.get_usage()))

        # Set target language mappings for translation
        self.target = {"EN": "EN-GB", "PT": "PT-PT"}

        # Process .po files for translation
        self.go_polib()

        if self.translator:
            self.stdout.write(str(self.translator.get_usage()))

    def translate_entry(self, entry: polib.POEntry, target_language: str) -> None:
        """Translate a single entry using the configured LLM agent or DeepL.

        Args:
            entry: The POFile entry to translate
            target_language (str): Target language code (e.g., 'EN', 'PT')

        Raises:
            DeepLLimitExceededError: When DeepL API usage limit is exceeded
            deepl.exceptions.DeepLException: When DeepL API encounters an error
            AgentTranslationError: When the configured agent cannot translate

        """
        try:
            # Display the original text to be translated
            self.stdout.write(entry.msgid)

            if self.llm_agent:
                entry.msgstr = translate_entries([entry.msgid], target_language, self.llm_agent, self.llm_model)[0]
                self.stdout.write(f"-> {entry.msgstr}\n")
                return

            # Normalize target language code and apply any mappings
            usage = self.translator.get_usage()
            if usage.any_limit_reached:
                msg = "LIMIT EXCEEDED!"
                raise DeepLLimitExceededError(msg)
            target_language = target_language.upper()
            if target_language in self.target:
                target_language = self.target[target_language]

            # Perform the actual translation using DeepL API
            kwargs = {
                "source_lang": "EN",
                "target_lang": target_language,
            }
            if target_language in SUPPORTED_FORMALITY_LANGS:
                kwargs["formality"] = "less"

            translation_result = self.translator.translate_text(entry.msgid, **kwargs)
            entry.msgstr = str(translation_result)

            # Display the translated result and add delay for API rate limiting
            self.stdout.write(f"-> {entry.msgstr}\n")
            time.sleep(1)
        except (deepl.exceptions.DeepLException, AgentTranslationError) as exception:
            # Handle DeepL-specific exceptions and log the error
            self.stdout.write(exception)
            self.stdout.write(entry.msgid)

    @staticmethod
    def _estimate_translation_tokens(entry: polib.POEntry) -> int:
        """Estimate source JSON and response overhead at roughly four characters/token."""
        return len(entry.msgid) // 4 + 8

    def _llm_batches(self, entries: list[polib.POEntry]) -> list[list[polib.POEntry]]:
        """Split entries into ordered batches that fit the configured token budget."""
        batches: list[list[polib.POEntry]] = []
        batch: list[polib.POEntry] = []
        used_tokens = 0
        for entry in entries:
            entry_tokens = self._estimate_translation_tokens(entry)
            if batch and used_tokens + entry_tokens > self.llm_max_tokens:
                batches.append(batch)
                batch = []
                used_tokens = 0
            batch.append(entry)
            used_tokens += entry_tokens
        if batch:
            batches.append(batch)
        return batches

    def translate_llm_entries(self, entries: list[polib.POEntry], target_language: str) -> None:
        """Translate entries in token-bounded agent batches, preserving PO order."""
        for batch in self._llm_batches(entries):
            for entry in batch:
                self.stdout.write(entry.msgid)
            try:
                translations = translate_entries(
                    [entry.msgid for entry in batch], target_language, self.llm_agent, self.llm_model
                )
            except AgentTranslationError as exception:
                self.stdout.write(exception)
                continue

            for entry, translation in zip(batch, translations, strict=True):
                entry.msgstr = translation
                self.stdout.write(f"-> {entry.msgstr}\n")

    def go_polib(self) -> None:
        """Process translation files using polib and the configured translator.

        Iterates through all locale directories and translates untranslated
        msgid entries using the LLM agent or DeepL translation service.
        """
        locale_path = Path("larpmanager/locale")
        locale_directories = [directory.name for directory in locale_path.iterdir() if directory.is_dir()]

        for locale_code in locale_directories:
            if locale_code.lower() == "en":
                continue

            po_file_path = locale_path / locale_code / "LC_MESSAGES" / "django.po"

            with po_file_path.open() as file_input:
                file_lines = file_input.read().splitlines(keepends=True)
            first_empty_line_index = file_lines.index("\n")
            file_lines = file_lines[first_empty_line_index:]
            file_lines = ['msgid ""\n', 'msgstr ""\n', '"Content-Type: text/plain; charset=UTF-8"\n', *file_lines]
            with po_file_path.open("w") as file_output:
                file_output.writelines(file_lines)

            self.stdout.write(f"### LOCALE: {locale_code} ### ")

            po_file = polib.pofile(po_file_path)

            untranslated_entries = po_file.untranslated_entries()
            fuzzy_entries = po_file.fuzzy_entries()
            for entry in fuzzy_entries:
                entry.flags.remove("fuzzy")

            if self.llm_agent:
                self.translate_llm_entries([*untranslated_entries, *fuzzy_entries], locale_code)
            else:
                for entry in untranslated_entries:
                    self.translate_entry(entry, locale_code)

                for entry in fuzzy_entries:
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
