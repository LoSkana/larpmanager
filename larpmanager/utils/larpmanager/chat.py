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
import re

import anthropic
import deepl
from django.conf import settings as conf_settings
from django.core.cache import cache
from django.utils.translation import get_language, gettext as _

from larpmanager.models.access import AssociationPermission, EventPermission
from larpmanager.utils.larpmanager.query import get_tutorial_doc, search_guides, search_tutorials
from larpmanager.utils.larpmanager.tasks import notify_admins

CHAT_MODEL = "claude-haiku-4-5-20251001"
CHAT_ANSWER_CACHE_TIMEOUT = 7 * 86400  # 7 days: repeated questions are answered for free
CHAT_MAX_CONTEXT_DOCS = 4
CHAT_MAX_TUTORIAL_SECTIONS = 3
CHAT_MAX_GUIDES = 1
CHAT_MAX_DOC_LENGTH = 3000
CHAT_MAX_TOKENS = 500
CHAT_MAX_PAGE_LENGTH = 100
CHAT_MAX_QUESTION_LENGTH = 1000

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


def _find_relevant_docs(question: str) -> list[dict[str, str]]:
    """Find the tutorial and guide sections matching any content word of the question."""
    search_text = " or ".join(sorted(_tokenize(question)))
    if not search_text:
        return []

    return search_tutorials(search_text)[:CHAT_MAX_TUTORIAL_SECTIONS] + search_guides(search_text)[:CHAT_MAX_GUIDES]


def _translate_to_english(text: str) -> str | None:
    """Translate text to English, the language of the documentation, alerting admins and returning None on failure."""
    api_key = getattr(conf_settings, "DEEPL_API_KEY", None)
    if not api_key:
        return text

    try:
        return str(deepl.Translator(api_key).translate_text(text, target_lang="EN-US"))
    except deepl.DeepLException as error:
        notify_admins("Chat assistant: DeepL translation failed", str(error), error)
        return None


def _search_docs(question: str) -> tuple[list[dict[str, str]], bool]:
    """Search the documentation, translating the question when it is likely not in English.

    Returns:
        The documents found, and whether the search was complete: False if the translation failed.

    """
    docs = _find_relevant_docs(question) if (get_language() or "en").startswith("en") else []
    if docs:
        return docs, True

    translated_question = _translate_to_english(question)
    if translated_question is None:
        return _find_relevant_docs(question), False

    return _find_relevant_docs(translated_question), True


def _unavailable_answer() -> dict:
    """Build the answer given when a service failure prevents a real one."""
    return {
        "answer": str(_("The assistant is temporarily unavailable, please try again later.")),
        "sources": [],
    }


def _get_page_context(page_slug: str) -> tuple[str, str]:
    """Return the label and the tutorial reference of a management page, if it is one."""
    slug = page_slug.removesuffix("_edit").removesuffix("_new")
    for model in (EventPermission, AssociationPermission):
        permission = model.objects.filter(slug=slug).select_related("feature").first()
        if permission:
            return f"{permission.name}: {permission.descr}", permission.feature.tutorial
    return "", ""


def _collect_docs(question: str, page_tutorial: str) -> tuple[list[dict[str, str]], bool]:
    """Gather the documents for a question, the tutorial of the current page first.

    Returns:
        The documents, and whether the search behind them was complete.

    """
    page_doc = get_tutorial_doc(page_tutorial) if page_tutorial else None
    found_docs, search_complete = _search_docs(question)
    docs = ([page_doc] if page_doc else []) + found_docs

    unique_docs: dict[str, dict[str, str]] = {}
    for doc in docs:
        unique_docs.setdefault(doc["url"], doc)
    return list(unique_docs.values())[:CHAT_MAX_CONTEXT_DOCS], search_complete


def _doc_title(doc: dict[str, str]) -> str:
    """Return the title of a document, including its section if any."""
    return f"{doc['title']} - {doc['section']}" if doc["section"] else doc["title"]


def _format_doc(doc: dict[str, str]) -> str:
    """Format a document as a titled excerpt for the system prompt."""
    return f"# {_doc_title(doc)}\n{doc['text'][:CHAT_MAX_DOC_LENGTH]}"


def _call_anthropic(question: str, context_blocks: list[str], page_label: str = "") -> str | None:
    """Send the question and retrieved doc excerpts to Claude, alerting admins and returning None on failure."""
    if not conf_settings.ANTHROPIC_API_KEY:
        notify_admins("Chat assistant: Anthropic API key not configured")
        return None

    page_hint = f"The user is on this page of the management interface: {page_label}.\n" if page_label else ""
    system_prompt = (
        "You are the LarpManager support assistant. Answer the user's question using ONLY "
        "the documentation excerpts below. If they do not contain the answer, say you don't know "
        "and suggest opening a support ticket. Keep the answer short and concrete. "
        "The excerpts are in English: reply in the language of the user's question.\n"
        + page_hint
        + "\n"
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
    except anthropic.APIError as error:
        notify_admins("Chat assistant: Anthropic request failed", str(error), error)
        return None

    return "".join(block.text for block in message.content if block.type == "text").strip()


def get_chat_answer(question: str, page_slug: str = "") -> dict:
    """Answer a user question grounded in LarpManager guides/tutorials, cheaply.

    Retrieval is free full-text search over the guides and tutorials. The Anthropic call
    (the only paid step) receives just the matching sections, and identical questions with
    the same page context are served from cache afterwards without calling the API again.
    Answers affected by a failure are not cached, so they recover with the service.

    Args:
        question: The user's question.
        page_slug: Name of the view the user is on, used to give the answer context.

    Returns:
        Dict with the "answer" text and the "sources" list of {"title", "url"} it is based on.

    """
    question = (question or "").strip()
    if not question:
        return {"answer": "", "sources": []}

    page_label, page_tutorial = _get_page_context(page_slug[:CHAT_MAX_PAGE_LENGTH])
    cache_input = f"{get_language()}|{page_label}|{page_tutorial}|{question.lower()}"
    cache_key = "chat_answer_" + hashlib.sha256(cache_input.encode()).hexdigest()
    cached_answer = cache.get(cache_key)
    if cached_answer is not None:
        return cached_answer

    docs, search_complete = _collect_docs(question, page_tutorial)
    if not docs:
        if not search_complete:
            return _unavailable_answer()
        result = {
            "answer": str(_("I could not find anything relevant in the documentation. Try opening a support ticket.")),
            "sources": [],
        }
    else:
        answer = _call_anthropic(question, [_format_doc(doc) for doc in docs], page_label)
        if not answer:
            return _unavailable_answer()
        result = {
            "answer": answer,
            "sources": [{"title": _doc_title(doc), "url": doc["url"]} for doc in docs],
        }

    if search_complete:
        cache.set(cache_key, result, timeout=CHAT_ANSWER_CACHE_TIMEOUT)
    return result
