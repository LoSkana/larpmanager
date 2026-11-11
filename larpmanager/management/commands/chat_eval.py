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

from pathlib import Path
from typing import Any

import yaml
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import translation

from larpmanager.cache.config import reset_event_configs
from larpmanager.cache.feature import clear_event_features_cache
from larpmanager.models.base import Feature
from larpmanager.models.event import EventConfig, Run
from larpmanager.utils.larpmanager.chat import CHAT_KNOWLEDGE_CACHE_KEY, build_chat_context, get_chat_answer

DEFAULT_CASES = Path(__file__).resolve().parents[2] / "tests" / "resources" / "chat_eval.yaml"


class Command(BaseCommand):
    """Evaluate the chat assistant on a set of questions, calling the paid Anthropic API."""

    help = "Ask the chat assistant the evaluation questions and check the expected terms in the answers"

    def add_arguments(self, parser: Any) -> None:
        """Add the cases file, run and language options."""
        parser.add_argument("--cases", default=str(DEFAULT_CASES), help="YAML file of evaluation cases")
        parser.add_argument("--run", type=int, help="Id of the run used as context (default: the first one)")
        parser.add_argument("--language", default="it", help="Active language while answering")

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002
        """Run every case in a rolled back transaction, printing the answers and a final score."""
        cases = yaml.safe_load(Path(options["cases"]).read_text())
        run = Run.objects.select_related("event").filter(pk=options["run"]).first() if options["run"] else None
        run = run or Run.objects.select_related("event").order_by("pk").first()
        if not run:
            msg = "No run available as context"
            raise CommandError(msg)

        cache.delete(CHAT_KNOWLEDGE_CACHE_KEY)
        translation.activate(options["language"])
        passed = 0
        for case in cases:
            ok = self._evaluate(case, run)
            passed += ok
        self.stdout.write(f"\nPassed {passed}/{len(cases)}")

    def _evaluate(self, case: dict, run: Run) -> bool:
        """Answer one case with its features and configs enabled, without keeping the changes."""
        with transaction.atomic():
            for feature in Feature.objects.filter(slug__in=case.get("features", [])):
                run.event.features.add(feature)
            for config in case.get("configs", []):
                EventConfig.objects.update_or_create(event=run.event, name=config, defaults={"value": "True"})
            clear_event_features_cache(run.event_id)
            reset_event_configs(run.event_id)

            context = build_chat_context(run=run, association_id=run.event.association_id)
            result = get_chat_answer(case["question"], context, use_cache=False)
            transaction.set_rollback(True)

        clear_event_features_cache(run.event_id)
        reset_event_configs(run.event_id)

        answer = result["answer"].lower()
        missing = [group for group in case.get("expect", []) if not any(term.lower() in answer for term in group)]
        status = "PASS" if not missing else f"FAIL (missing one of: {missing})"
        self.stdout.write(f"\n=== {case['question']}\n{result['answer']}\nSources: {result['sources']}\n{status}")
        return not missing
