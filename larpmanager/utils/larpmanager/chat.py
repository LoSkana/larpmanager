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

import hashlib
import logging
import re

import anthropic
from django.conf import settings as conf_settings
from django.core.cache import cache
from django.utils.translation import gettext as _

from larpmanager.cache.wwyltd import get_content_preview, get_guides_cache, get_tutorials_cache
from larpmanager.models.larpmanager import LarpManagerGuide, LarpManagerTutorial

logger = logging.getLogger(__name__)

CHAT_MODEL = "claude-haiku-4-5-20251001"
CHAT_ANSWER_CACHE_TIMEOUT = 7 * 86400  # 7 days: repeated questions are answered for free
CHAT_MAX_CONTEXT_DOCS = 4
CHAT_MAX_DOC_LENGTH = 3000
CHAT_MAX_TOKENS = 500

_STOPWORDS = {
    "the",
    "a",
    "an",
    "to",
    "of",
    "and",
    "is",
    "are",
    "how",
    "do",
    "does",
    "did",
    "i",
    "can",
    "what",
    "in",
    "on",
    "for",
    "with",
    "my",
    "it",
    "this",
    "that",
    "be",
}
_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LENGTH = 2


def _tokenize(text: str) -> set[str]:
    """Extract lowercase content words from text, dropping stopwords and short tokens."""
    return {
        word for word in _WORD_PATTERN.findall(text.lower()) if word not in _STOPWORDS and len(word) > _MIN_TOKEN_LENGTH
    }


def _find_relevant_docs(question: str) -> list[tuple[int, str, str, str]]:
    """Rank cached guides/tutorials by keyword overlap with the question.

    Reuses the existing wwyltd guides/tutorials cache (already built and refreshed via
    signals) instead of a separate index, so retrieval costs no extra API calls or storage.

    Returns:
        List of (score, doc_type, slug, title) tuples, highest score first.

    """
    question_tokens = _tokenize(question)
    if not question_tokens:
        return []

    scores: dict[tuple[str, str], list] = {}

    for guide in get_guides_cache():
        overlap = len(question_tokens & _tokenize(f"{guide['title']} {guide['content_preview']}"))
        if overlap:
            key = ("guide", guide["slug"])
            entry = scores.setdefault(key, [0, guide["title"]])
            entry[0] += overlap

    for tutorial in get_tutorials_cache():
        text = f"{tutorial['title']} {tutorial['section_title']} {tutorial['content_preview']}"
        overlap = len(question_tokens & _tokenize(text))
        if overlap:
            key = ("tutorial", tutorial["slug"])
            entry = scores.setdefault(key, [0, tutorial["title"]])
            entry[0] += overlap

    ranked = sorted(
        ((score, doc_type, slug, title) for (doc_type, slug), (score, title) in scores.items()),
        key=lambda item: item[0],
        reverse=True,
    )
    return ranked[:CHAT_MAX_CONTEXT_DOCS]


def _get_doc_context(doc_type: str, slug: str, title: str) -> str:
    """Fetch and clean full document text from the database for a matched doc.

    Only called for the handful of top-ranked matches, so it stays a cheap targeted
    query instead of loading full guide/tutorial text into the shared cache.
    """
    if doc_type == "guide":
        guide = LarpManagerGuide.objects.filter(slug=slug, published=True).first()
        raw_text = guide.text if guide else ""
    else:
        tutorial = LarpManagerTutorial.objects.filter(slug=slug).first()
        raw_text = tutorial.descr if tutorial else ""

    return f"# {title}\n{get_content_preview(raw_text, CHAT_MAX_DOC_LENGTH)}"


def _call_anthropic(question: str, context_blocks: list[str]) -> str:
    """Send the question and retrieved doc excerpts to Claude, grounded-only."""
    if not conf_settings.ANTHROPIC_API_KEY:
        return str(_("Live chat is not configured."))

    system_prompt = (
        "You are the LarpManager support assistant. Answer the user's question using ONLY "
        "the documentation excerpts below. If they do not contain the answer, say you don't "
        "know and suggest opening a support ticket. Keep the answer short and concrete.\n\n"
        + "\n\n---\n\n".join(context_blocks)
    )

    client = anthropic.Anthropic(api_key=conf_settings.ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=CHAT_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": question}],
        )
    except anthropic.APIError:
        logger.exception("Anthropic chat request failed")
        return str(_("The assistant is temporarily unavailable, please try again later."))

    return "".join(block.text for block in message.content if block.type == "text").strip()


def get_chat_answer(question: str) -> str:
    """Answer a user question grounded in LarpManager guides/tutorials, cheaply.

    Retrieval is free keyword matching over the already-cached guides/tutorials summaries.
    The Anthropic call (the only paid step) only fires for the handful of top matches, and
    identical questions are served from cache afterwards without calling the API again.
    """
    question = (question or "").strip()
    if not question:
        return ""

    cache_key = "chat_answer_" + hashlib.sha256(question.lower().encode()).hexdigest()
    cached_answer = cache.get(cache_key)
    if cached_answer is not None:
        return cached_answer

    relevant_docs = _find_relevant_docs(question)
    if not relevant_docs:
        answer = str(
            _(
                """I could not find anything relevant in the documentation. Try asking in English, or open a support ticket."""
            )
        )
    else:
        context_blocks = [_get_doc_context(doc_type, slug, title) for _score, doc_type, slug, title in relevant_docs]
        answer = _call_anthropic(question, context_blocks)

    cache.set(cache_key, answer, timeout=CHAT_ANSWER_CACHE_TIMEOUT)
    return answer
