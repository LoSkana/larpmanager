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
from unittest.mock import patch

from django.core.cache import cache
from django.template.loader import render_to_string

from larpmanager.cache.config import save_single_config
from larpmanager.models.access import EventPermission, PermissionModule
from larpmanager.models.base import Feature
from larpmanager.models.larpmanager import LarpManagerGuide, LarpManagerTutorial
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.core.base import add_intro_driver
from larpmanager.utils.larpmanager.chat import get_chat_answer
from larpmanager.utils.larpmanager.query import get_tutorial_doc, search_guides, search_tutorials
from larpmanager.utils.services.association import get_activation_checklist
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
        permission_module = PermissionModule.objects.create(name="Registrations", slug="registrations_perms", icon="tag")
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
        """A repeated question is free, on the same page only."""
        get_chat_answer("lottery", "page_one")
        get_chat_answer("lottery", "page_one")
        self.assertEqual(call.call_count, 1)
        get_chat_answer("lottery", "page_two")
        self.assertEqual(call.call_count, 2)


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
