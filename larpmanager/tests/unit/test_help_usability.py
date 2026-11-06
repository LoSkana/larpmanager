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

"""Tests for the in-app help: dashboard tours, activation checklist, search and chat."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import deepl
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import RequestFactory

from larpmanager.cache.config import save_single_config
from larpmanager.models.access import EventPermission, PermissionModule
from larpmanager.models.base import Feature
from larpmanager.models.larpmanager import LarpManagerChatLog, LarpManagerGuide, LarpManagerTutorial
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.base import add_intro_driver
from larpmanager.utils.core.context_processors import cache_association
from larpmanager.utils.larpmanager.chat import CHAT_MAX_QUESTION_LENGTH, get_chat_answer
from larpmanager.utils.larpmanager.query import _tutorial_doc, get_tutorial_doc, search_guides, search_tutorials
from larpmanager.utils.services.association import get_activation_checklist
from larpmanager.views.larpmanager import chat_ask, concepts
from larpmanager.views.manage import WhatWouldYouLikeForm

TICKET_TUTORIAL = """
<h2>Manage tickets</h2><p>Create a ticket with a price for your participants.</p>
<h3>Waiting list</h3><p>Participants wait for a free seat.</p>
<h2>Lottery</h2><p>Seats drawn among the candidates.</p>
"""


class TestIntroDriver(BaseTestCase):
    """Selection of the tour shown on the dashboards."""

    def setUp(self) -> None:
        """Run as outside pytest, where the tours are disabled."""
        super().setUp()
        env_patcher = patch.dict(os.environ)
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        os.environ.pop("PYTEST_CURRENT_TEST", None)

    def _pick(self, **query: str) -> dict:
        """Run the selection for the test member and return the context."""
        context = {"member": self.get_member(), "association_id": self.get_association().id}
        add_intro_driver(SimpleNamespace(GET=query), context)
        return context

    def test_pending_tour_shown_once(self) -> None:
        """A pending tour is consumed by the dashboard showing it."""
        save_single_config(self.get_association(), "intro_driver", "first_event")
        self.assertEqual(self._pick()["intro_driver"], "first_event")
        self.assertNotIn("intro_driver", self._pick())

    def test_replay_on_request(self) -> None:
        """The tour is replayed on request, and only then."""
        self.assertNotIn("intro_driver", self._pick())
        self.assertEqual(self._pick(tour="1")["intro_driver"], "overview")

    def test_pending_tour_wins_over_replay(self) -> None:
        """A pending tour is not lost to a replay."""
        save_single_config(self.get_association(), "intro_driver", "welcome")
        self.assertEqual(self._pick(tour="1")["intro_driver"], "welcome")


class TestActivationChecklist(BaseTestCase):
    """Help attached to the activation checklist."""

    def test_every_step_has_a_tutorial_section(self) -> None:
        """Each step links a section of a tutorial."""
        checklist, _progress = get_activation_checklist(self.get_association().id)
        self.assertTrue(checklist)
        for item in checklist:
            self.assertIn("/#", item["tutorial"])


class TestLiteModeSearch(BaseTestCase):
    """Search entries available in lite mode."""

    def test_configs_are_left_out(self) -> None:
        """Lite mode hides the configuration, so search does not offer it."""
        context = {"lite_mode": True, "exe_page": 1, "association_id": self.get_association().id, "name": "Org"}
        with patch("larpmanager.views.manage.get_exe_configs_cache") as configs:
            WhatWouldYouLikeForm(context=context)
        configs.assert_not_called()


class TestSearch(BaseTestCase):
    """Full-text search over the documentation."""

    def setUp(self) -> None:
        """Create the documentation."""
        super().setUp()
        self.tutorial = LarpManagerTutorial.objects.create(name="Tickets", slug="tickets", descr=TICKET_TUTORIAL)

    def test_section_found_past_its_opening(self) -> None:
        """Sections match on their whole text and link to their anchor."""
        results = search_tutorials("lottery")
        self.assertEqual([result["section"] for result in results], ["Lottery"])
        self.assertTrue(results[0]["url"].endswith("/tickets/#lottery"))
        self.assertIn("drawn", results[0]["text"])

    def test_guide_narrowed_to_best_section(self) -> None:
        """A guide returns the section matching the search."""
        LarpManagerGuide.objects.create(
            title="Guide",
            slug="guide",
            published=True,
            text="<h2>Intro</h2><p>Hello</p><h2>Refunds</h2><p>Money back</p>",
        )
        self.assertEqual(search_guides("refunds")[0]["section"], "Refunds")

    def test_tutorial_reference(self) -> None:
        """A reference names a tutorial, optionally narrowed to a section."""
        self.assertEqual(get_tutorial_doc("tickets/#lottery")["section"], "Lottery")
        self.assertEqual(get_tutorial_doc("tickets/")["section"], "")
        self.assertIsNone(get_tutorial_doc("missing"))

    def test_heading_keeps_its_spaces(self) -> None:
        """Inline markup in a heading does not garble its title or anchor."""
        self.tutorial.descr = "<h2>Create <em>event</em> now</h2><p>Body</p>"
        self.tutorial.save()
        doc = get_tutorial_doc("tickets#create-event-now")
        self.assertEqual(doc["section"], "Create event now")
        self.assertTrue(doc["url"].endswith("#create-event-now"))

    def test_anchor_matches_the_tutorial_page(self) -> None:
        """Anchors follow the slugs the tutorial page gives its headings."""
        for heading, anchor in (
            ("What's new", "whats-new"),
            ("Tickets/Tiers", "ticketstiers"),
            ("Q&A", "qa"),
            ("Citta & Caffe - due", "citta-caffe-due"),
        ):
            self.assertTrue(_tutorial_doc(self.tutorial, heading, "")["url"].endswith(f"#{anchor}"))

    def test_section_includes_its_subsections(self) -> None:
        """An H2 with only H3 subsections carries their text."""
        self.tutorial.descr = (
            "<h2>Manage</h2><h3>Add</h3><p>Adding</p><h3>Edit</h3><p>Editing</p><h2>Next</h2><p>Other</p>"
        )
        self.tutorial.save()
        text = get_tutorial_doc("tickets#manage")["text"]
        self.assertIn("Adding", text)
        self.assertIn("Editing", text)
        self.assertNotIn("Other", text)
        self.assertEqual(get_tutorial_doc("tickets#add")["text"], "Adding")

    def test_search_prefers_the_subsection(self) -> None:
        """A match inside an H3 returns that H3, not the H2 above it."""
        html = "<h2>Manage</h2><p>Intro lottery</p><h3>Add</h3><p>Filler</p><h3>Draw</h3><p>Lottery lottery</p>"
        self.tutorial.descr = html
        self.tutorial.save()
        results = {result["section"]: result["text"] for result in search_tutorials("lottery")}
        self.assertEqual(results, {"Manage": "Intro lottery", "Draw": "Lottery lottery"})

        LarpManagerGuide.objects.create(title="Guide", slug="guide", text=html, published=True)
        self.assertEqual(search_guides("lottery")[0]["section"], "Draw")

    def test_empty_section_falls_back_to_the_tutorial(self) -> None:
        """A section without text is skipped in favour of the whole tutorial."""
        self.tutorial.descr = "<h2>Empty</h2><h2>Full</h2><p>Body</p>"
        self.tutorial.save()
        doc = get_tutorial_doc("tickets#empty")
        self.assertEqual(doc["section"], "")
        self.assertIn("Body", doc["text"])


class TestChat(BaseTestCase):
    """Answers of the chat assistant."""

    def setUp(self) -> None:
        """Create the documentation, with an empty answer cache."""
        super().setUp()
        cache.clear()
        LarpManagerTutorial.objects.create(name="Tickets", slug="tickets", descr=TICKET_TUTORIAL)

    @patch("larpmanager.utils.larpmanager.chat._call_anthropic", return_value="Use the lottery")
    def test_question_matches_on_any_word(self, call: object) -> None:
        """A natural question reaches the section, whose link is returned as source."""
        result = get_chat_answer("How does the lottery for seats work?")
        self.assertEqual(result["answer"], "Use the lottery")
        self.assertEqual(result["sources"][0]["title"], "Tickets - Lottery")
        self.assertIn("drawn among", call.call_args.args[1][0])

    @patch("larpmanager.utils.larpmanager.chat._translate_to_english", side_effect=lambda text: text)
    @patch("larpmanager.utils.larpmanager.chat._call_anthropic")
    def test_no_match_skips_the_api(self, call: object, _translate: object) -> None:
        """Without documentation the paid API is not called."""
        result = get_chat_answer("zzzqqq")
        call.assert_not_called()
        self.assertEqual(result["sources"], [])

    @patch("larpmanager.utils.larpmanager.chat._translate_to_english", return_value="lottery")
    @patch("larpmanager.utils.larpmanager.chat._call_anthropic", return_value="ok")
    def test_question_translated_when_unmatched(self, _call: object, translate: object) -> None:
        """An unmatched question is searched again in English."""
        result = get_chat_answer("zzzqqq")
        translate.assert_called_once()
        self.assertEqual(result["sources"][0]["title"], "Tickets - Lottery")

    @patch("larpmanager.utils.larpmanager.chat._call_anthropic", return_value="ok")
    def test_page_gives_context(self, call: object) -> None:
        """The tutorial of the current page comes first, and the page is described."""
        feature = Feature.objects.create(name="Tickets", slug="tickets_feature", tutorial="tickets#waiting-list")
        permission_module = PermissionModule.objects.create(
            name="Registrations", slug="registrations_perms", icon="tag"
        )
        permission = EventPermission.objects.create(
            name="Tickets",
            slug="orga_registration_tickets",
            descr="Manage tickets",
            feature=feature,
            module=permission_module,
        )

        result = get_chat_answer("lottery", "orga_registration_tickets_edit")
        self.assertEqual(result["sources"][0]["title"], "Tickets - Waiting list")
        self.assertIn(permission.name, call.call_args.args[2])

    @patch("larpmanager.utils.larpmanager.chat._call_anthropic", return_value="ok")
    def test_answer_cached_per_page(self, call: object) -> None:
        """A repeated question is free across views of a page, not across pages."""
        feature = Feature.objects.create(name="Tickets", slug="tickets_feature", tutorial="tickets")
        permission_module = PermissionModule.objects.create(
            name="Registrations", slug="registrations_perms", icon="tag"
        )
        EventPermission.objects.create(
            name="Tickets", slug="orga_registration_tickets", descr="Tickets", feature=feature, module=permission_module
        )

        get_chat_answer("lottery", "orga_registration_tickets")
        get_chat_answer("lottery", "orga_registration_tickets_edit")
        self.assertEqual(call.call_count, 1)
        get_chat_answer("lottery", "unknown_page")
        get_chat_answer("lottery", "another_unknown_page")
        self.assertEqual(call.call_count, 2)

    @patch("larpmanager.utils.larpmanager.chat.notify_admins")
    @patch("larpmanager.utils.larpmanager.chat.anthropic.Anthropic")
    def test_anthropic_failure_alerts_and_is_not_cached(self, client: object, notify: object) -> None:
        """A failed request alerts the admins and is retried on the next question."""
        client.return_value.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())
        with self.settings(ANTHROPIC_API_KEY="key"):
            result = get_chat_answer("lottery")
            self.assertEqual(result["sources"], [])
            notify.assert_called_once()

            client.return_value.messages.create.side_effect = None
            client.return_value.messages.create.return_value = SimpleNamespace(
                content=[SimpleNamespace(type="text", text="Recovered")]
            )
            self.assertEqual(get_chat_answer("lottery")["answer"], "Recovered")

    @patch("larpmanager.utils.larpmanager.chat.anthropic.Anthropic")
    def test_prompt_allows_not_knowing(self, client: object) -> None:
        """The assistant is told to admit when the excerpts lack the answer."""
        client.return_value.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")]
        )
        with self.settings(ANTHROPIC_API_KEY="key"):
            get_chat_answer("lottery")
        self.assertIn("say you don't know", client.return_value.messages.create.call_args.kwargs["system"])

    @patch("larpmanager.utils.larpmanager.chat.notify_admins")
    def test_missing_key_alerts_and_is_not_cached(self, notify: object) -> None:
        """A missing API key alerts the admins, and the answer recovers once it is set."""
        with self.settings(ANTHROPIC_API_KEY=""):
            get_chat_answer("lottery")
        notify.assert_called_once()
        with patch("larpmanager.utils.larpmanager.chat._call_anthropic", return_value="ok"):
            self.assertEqual(get_chat_answer("lottery")["answer"], "ok")

    @patch("larpmanager.utils.larpmanager.chat.notify_admins")
    @patch("larpmanager.utils.larpmanager.chat.deepl.Translator")
    def test_translation_failure_alerts_and_is_not_cached(self, translator: object, notify: object) -> None:
        """A failed translation alerts the admins and its outcome is not cached."""
        translator.return_value.translate_text.side_effect = deepl.DeepLException("down")
        with self.settings(DEEPL_API_KEY="key"):
            result = get_chat_answer("zzzqqq")
            self.assertEqual(result["sources"], [])
            self.assertIn("temporarily unavailable", result["answer"])
            notify.assert_called_once()

            translator.return_value.translate_text.side_effect = None
            translator.return_value.translate_text.return_value = "lottery"
            with patch("larpmanager.utils.larpmanager.chat._call_anthropic", return_value="ok"):
                self.assertEqual(get_chat_answer("zzzqqq")["answer"], "ok")

    def test_empty_answer_is_not_cached(self) -> None:
        """A reply without text counts as a failure and is retried."""
        with patch("larpmanager.utils.larpmanager.chat._call_anthropic", return_value=""):
            self.assertIn("temporarily unavailable", get_chat_answer("lottery")["answer"])
        with patch("larpmanager.utils.larpmanager.chat._call_anthropic", return_value="ok"):
            self.assertEqual(get_chat_answer("lottery")["answer"], "ok")

    def test_input_limit_follows_the_server_one(self) -> None:
        """The chat input is limited to the length the server accepts."""
        request = RequestFactory().get("/")
        request.user = self.get_user()
        request.enviro = "test"
        request.association = {"id": self.get_association().id, "main_domain": "larpmanager.com"}
        html = render_to_string("elements/dashboard/chat.html", cache_association(request), request=request)
        self.assertIn(f'maxlength="{CHAT_MAX_QUESTION_LENGTH}"', html)

    def test_long_question_rejected(self) -> None:
        """An oversized question is refused before it is logged or answered."""
        request = RequestFactory().post("/", {"question": "a" * (CHAT_MAX_QUESTION_LENGTH + 1)})
        request.user = self.get_user()
        request.association = {"main_domain": "larpmanager.com"}
        with patch("larpmanager.views.larpmanager.get_chat_answer") as answer:
            response = chat_ask(request)
        self.assertEqual(response.status_code, 400)
        answer.assert_not_called()
        self.assertFalse(LarpManagerChatLog.objects.exists())


class TestConcepts(BaseTestCase):
    """Page of the key concepts."""

    @patch("larpmanager.views.larpmanager.render")
    @patch("larpmanager.views.larpmanager.get_context", side_effect=lambda *_args, **_kwargs: {})
    def test_marketing_texts_only_on_the_main_site(self, get_context: object, render: object) -> None:
        """Organization sites do not get the LarpManager landing texts."""
        request = RequestFactory().get("/")
        request.association = {"id": 0}
        concepts(request)
        self.assertIn("texts", render.call_args.args[2])

        request.association = {"id": self.get_association().id}
        concepts(request)
        self.assertNotIn("texts", render.call_args.args[2])


class TestHelpMenu(BaseTestCase):
    """Entries of the topbar help menu."""

    def _render(self, **context: object) -> str:
        """Render the menu with the base context."""
        return render_to_string("elements/structure/help-menu.html", {"association": {"skin_id": 1}, **context})

    def test_search_and_chat_only_on_the_larpmanager_skin(self) -> None:
        """Search and chat are served on the main platform only."""
        self.assertNotIn("wwyltd-open-trigger", self._render())
        self.assertIn("wwyltd-open-trigger", self._render(is_larpmanager_skin=True))

    def test_replay_targets_the_dashboard(self) -> None:
        """The replay link reloads the current dashboard."""
        self.assertIn("?tour=1", self._render())
