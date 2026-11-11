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

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings

from larpmanager.cache.config import save_single_config
from larpmanager.cache.feature import clear_event_features_cache
from larpmanager.models.access import EventPermission, PermissionModule
from larpmanager.models.base import Feature
from larpmanager.models.event import Event
from larpmanager.models.larpmanager import LarpManagerChatLog, LarpManagerGuide, LarpManagerTutorial
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.base import add_intro_driver
from larpmanager.utils.core.context_processors import cache_association
from larpmanager.utils.larpmanager.chat import (
    CHAT_MAX_QUESTION_LENGTH,
    CHAT_MAX_TOOL_ROUNDS,
    build_chat_context,
    clean_history,
    get_chat_answer,
)
from larpmanager.utils.larpmanager.query import _tutorial_doc, get_tutorial_doc, search_guides, search_tutorials
from larpmanager.utils.services.association import get_activation_checklist
from larpmanager.views.larpmanager import _get_chat_run, chat_ask, concepts
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


def _response(stop_reason: str, *blocks: SimpleNamespace) -> SimpleNamespace:
    """Build a fake Anthropic response."""
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def _text(text: str) -> SimpleNamespace:
    """Build a fake text block."""
    return SimpleNamespace(type="text", text=text)


def _tool_use(name: str, **tool_input: str) -> SimpleNamespace:
    """Build a fake tool call block."""
    return SimpleNamespace(type="tool_use", id=f"call_{name}", name=name, input=tool_input)


@override_settings(ANTHROPIC_API_KEY="key")
class TestChat(BaseTestCase):
    """Answers of the chat assistant."""

    def setUp(self) -> None:
        """Create the documentation, with empty caches and a mocked Anthropic client."""
        super().setUp()
        cache.clear()
        LarpManagerTutorial.objects.create(name="Tickets", slug="tickets", descr=TICKET_TUTORIAL)
        client_patcher = patch("larpmanager.utils.larpmanager.chat.anthropic.Anthropic")
        self.client_class = client_patcher.start()
        self.create = self.client_class.return_value.beta.messages.create
        self.addCleanup(client_patcher.stop)
        self.create.return_value = _response("end_turn", _text("ok"))

    def _sent_text(self, call_index: int = 0) -> str:
        """Return the text of the last message sent in an API call."""
        return str(self.create.call_args_list[call_index].kwargs["messages"][-1]["content"])

    def test_tools_read_the_docs(self) -> None:
        """The model searches the tutorials, and the sections it cites become sources."""
        self.create.side_effect = [
            _response("tool_use", _tool_use("search_docs", query="lottery")),
            _response("end_turn", _text("Use the [lottery](/tutorials/tickets/#lottery).")),
        ]
        result = get_chat_answer("How does the lottery for seats work?")
        self.assertIn("drawn among", self._sent_text(1))
        self.assertEqual(result["sources"], [{"title": "Tickets - Lottery", "url": "/tutorials/tickets/#lottery"}])

    def test_read_doc_unknown_reference(self) -> None:
        """A wrong reference is reported to the model as an error."""
        self.create.side_effect = [
            _response("tool_use", _tool_use("read_doc", ref="missing")),
            _response("end_turn", _text("ok")),
        ]
        get_chat_answer("lottery")
        tool_result = self.create.call_args_list[1].kwargs["messages"][-1]["content"][0]
        self.assertTrue(tool_result["is_error"])

    def test_tool_rounds_are_limited(self) -> None:
        """After the last allowed round the model must answer without tools."""
        self.create.side_effect = [_response("tool_use", _tool_use("search_docs", query="lottery"))] * (
            CHAT_MAX_TOOL_ROUNDS
        ) + [_response("end_turn", _text("final"))]
        self.assertEqual(get_chat_answer("lottery")["answer"], "final")
        self.assertEqual(self.create.call_args_list[-1].kwargs["tool_choice"], {"type": "none"})

    def test_knowledge_is_cached_in_the_system_prompt(self) -> None:
        """Features with their pages and the configuration options are in the cached system prompt."""
        Feature.objects.create(name="Lottery", slug="lottery_test", descr="Draw seats among candidates")
        get_chat_answer("lottery")
        system = self.create.call_args.kwargs["system"]
        self.assertEqual(system[-1]["cache_control"], {"type": "ephemeral"})
        self.assertIn("Lottery (event feature, slug lottery_test)", system[-1]["text"])
        self.assertIn("[writing_field_visibility]", system[-1]["text"])
        self.assertIn("Tickets [tickets]: Manage tickets; Waiting list; Lottery", system[-1]["text"])

    def test_event_state_sent_and_links_resolved(self) -> None:
        """Active features and configs of the event are sent, and event links point to it."""
        run = self.get_run()
        run.event.slug = "chatevent"
        feature = Feature.objects.create(name="Lottery", slug="lottery_test")
        run.event.features.add(feature)
        save_single_config(run.event, "writing_field_visibility", value=True)
        clear_event_features_cache(run.event_id)
        self.create.return_value = _response("end_turn", _text("Open [Event > Tickets](/{event}/manage/tickets/)"))

        result = get_chat_answer("lottery", build_chat_context(run=run))
        self.assertIn("lottery_test", self._sent_text())
        self.assertIn("writing_field_visibility", self._sent_text())
        self.assertIn(f"(/{run.get_slug()}/manage/tickets/)", result["answer"])

        self.assertIn("(/redirect/event/manage/tickets/)", get_chat_answer("other question")["answer"])

    def test_page_tutorial_sent(self) -> None:
        """The tutorial of the current page is sent with the question."""
        feature = Feature.objects.create(name="Tickets", slug="tickets_feature", tutorial="tickets#waiting-list")
        permission_module = PermissionModule.objects.create(
            name="Registrations", slug="registrations_perms", icon="tag"
        )
        EventPermission.objects.create(
            name="Tickets",
            slug="orga_registration_tickets",
            descr="Manage tickets",
            feature=feature,
            module=permission_module,
        )
        get_chat_answer("lottery", build_chat_context("orga_registration_tickets_edit"))
        self.assertIn("Participants wait for a free seat", self._sent_text())
        self.assertIn("Current page: Tickets: Manage tickets", self._sent_text())

    def test_answer_cached_per_context(self) -> None:
        """A repeated question is free in the same context, not in another one or within a conversation."""
        get_chat_answer("lottery")
        get_chat_answer("Lottery")
        self.assertEqual(self.create.call_count, 1)
        get_chat_answer("lottery", build_chat_context(run=self.get_run()))
        self.assertEqual(self.create.call_count, 2)
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        get_chat_answer("lottery", history=history)
        get_chat_answer("lottery", history=history)
        self.assertEqual(self.create.call_count, 4)

    @patch("larpmanager.utils.larpmanager.chat.notify_admins")
    def test_anthropic_failure_alerts_and_is_not_cached(self, notify: object) -> None:
        """A failed request alerts the admins and is retried on the next question."""
        self.create.side_effect = anthropic.APIConnectionError(request=MagicMock())
        self.assertIn("temporarily unavailable", get_chat_answer("lottery")["answer"])
        notify.assert_called_once()

        self.create.side_effect = None
        self.assertEqual(get_chat_answer("lottery")["answer"], "ok")

    def test_refusal_and_empty_answers_are_not_cached(self) -> None:
        """A refused or empty reply counts as a failure and is retried."""
        self.create.return_value = _response("refusal")
        self.assertIn("temporarily unavailable", get_chat_answer("lottery")["answer"])
        self.create.return_value = _response("end_turn")
        self.assertIn("temporarily unavailable", get_chat_answer("lottery")["answer"])
        self.create.return_value = _response("end_turn", _text("ok"))
        self.assertEqual(get_chat_answer("lottery")["answer"], "ok")

    @patch("larpmanager.utils.larpmanager.chat.notify_admins")
    def test_missing_key_alerts(self, notify: object) -> None:
        """A missing API key alerts the admins without calling the API."""
        with self.settings(ANTHROPIC_API_KEY=""):
            self.assertIn("temporarily unavailable", get_chat_answer("lottery")["answer"])
        notify.assert_called_once()
        self.create.assert_not_called()

    def test_local_login_without_key(self) -> None:
        """In development the local "ant auth login" credentials can replace the key."""
        with self.settings(ANTHROPIC_API_KEY=None, ANTHROPIC_USE_LOCAL_LOGIN=True):
            self.assertEqual(get_chat_answer("lottery")["answer"], "ok")
        self.assertNotIn("api_key", self.client_class.call_args.kwargs)

    def test_history_validation(self) -> None:
        """Only well-formed alternating exchanges are kept, the most recent ones."""
        exchange = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
        self.assertEqual(clean_history(json.dumps(exchange * 5)), (exchange * 3))
        self.assertEqual(clean_history(json.dumps([*exchange, {"role": "user", "content": "q"}])), exchange)
        self.assertEqual(clean_history(json.dumps([{"role": "assistant", "content": "a"}])), [])
        self.assertEqual(clean_history(json.dumps([{"role": "system", "content": "x"}])), [])
        self.assertEqual(clean_history("not json"), [])

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

    def test_run_context_requires_a_role(self) -> None:
        """The event is used as context only for users with a role on it."""
        run = self.get_run()
        Event.objects.filter(pk=run.event_id).update(slug="chatevent")
        run.event.slug = "chatevent"
        request = RequestFactory().post("/")
        request.user = self.get_user()
        request.association = {"id": run.event.association_id}
        context = {"association_id": run.event.association_id, "event_role": {}, "association_role": {}}
        with patch("larpmanager.views.larpmanager.has_event_permission", return_value=False):
            self.assertIsNone(_get_chat_run(request, context, run.get_slug()))
        with patch("larpmanager.views.larpmanager.has_event_permission", return_value=True):
            self.assertEqual(_get_chat_run(request, context, run.get_slug()), run)
            self.assertIsNone(_get_chat_run(request, context, "missing-x"))


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

    def test_dashboard_ask_bar_only_on_the_larpmanager_skin(self) -> None:
        """The ask bar of the dashboards is shown where the chat is served."""
        template = "larpmanager/manage/widgets/ask_bar.html"
        self.assertNotIn("dashboard-ask-bar", render_to_string(template, {}))
        html = render_to_string(template, {"is_larpmanager_skin": True, "chat_max_question_length": 10})
        self.assertIn("dashboard-ask-bar", html)
        self.assertIn('maxlength="10"', html)

    def test_replay_targets_the_dashboard(self) -> None:
        """The replay link reloads the current dashboard."""
        self.assertIn("?tour=1", self._render())
