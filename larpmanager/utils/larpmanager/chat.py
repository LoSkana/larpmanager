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
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic
from django.conf import settings as conf_settings
from django.core.cache import cache
from django.urls import NoReverseMatch, reverse
from django.utils.translation import get_language, gettext as _, override

from larpmanager.cache.basic import get_association_basic_cache
from larpmanager.cache.config import get_element_configs
from larpmanager.cache.feature import get_event_features
from larpmanager.forms.association import ExeConfigForm
from larpmanager.forms.event import OrgaConfigForm
from larpmanager.models.access import AssociationPermission, EventPermission
from larpmanager.models.association import Association, AssociationPlan
from larpmanager.models.base import Feature
from larpmanager.models.event import Event, Run
from larpmanager.utils.larpmanager.query import (
    get_guides_markdown,
    get_tutorial_doc,
    get_tutorial_index,
    search_guides,
    search_tutorials,
)
from larpmanager.utils.larpmanager.tasks import notify_admins

CHAT_MODEL = "claude-sonnet-5-5"
CHAT_BETAS = ["server-side-fallback-2026-07-01"]
CHAT_EFFORT = "medium"
CHAT_ANSWER_CACHE_TIMEOUT = 7 * 86400  # 7 days: repeated questions are answered for free
CHAT_KNOWLEDGE_CACHE_TIMEOUT = 3600
CHAT_KNOWLEDGE_CACHE_KEY = "chat_knowledge_prompt"
CHAT_MAX_TOKENS = 8000
CHAT_MAX_TOOL_ROUNDS = 4
CHAT_MAX_SEARCH_RESULTS = 6
CHAT_MAX_DOC_LENGTH = 6000
CHAT_MAX_PAGE_LENGTH = 100
CHAT_MAX_QUESTION_LENGTH = 1000
CHAT_MAX_HISTORY_MESSAGES = 6
CHAT_MAX_HISTORY_LENGTH = 4000
CHAT_TIMEOUT = 90.0
CHAT_MAX_CONFIG_VALUE_LENGTH = 40
CHAT_FREE_DAILY_LIMIT = 5

# Placeholder of the current event slug in the page paths given to the model
EVENT_PLACEHOLDER = "{event}"
_EVENT_PATH_PLACEHOLDER = "EVENTPLACEHOLDER"

CHAT_INSTRUCTIONS = """You are the support assistant of LarpManager, a web platform to organize LARP events. \
You help organizers and participants use the platform.

How to answer:
- Base every answer on the documentation: the catalog and guides below, and the tutorials you can search \
with search_docs and read with read_doc. Before giving steps that the guides do not cover, read the relevant \
tutorial section. Never invent pages, fields or options: if the documentation does not cover the question, \
say so and suggest opening a support ticket at {ticket_url}.
- Users often use other words than the documentation (for example "early registrations" may mean the \
pre-registration feature or a secret registration link; "make character texts visible to players" may mean \
field visibility, publishing or character sheets). Map the question to the features in the catalog. When it is \
ambiguous, briefly cover the likely meanings.
- Use the user context sent with the question: the page they are on, and the features active on their event \
and organization. If the answer needs a feature that is not active, say so and link the page that activates it. \
If it is already active, go straight to where it is configured.
- Name pages as "Event > Page" or "Organization > Page" and link them with the paths in the catalog. Keep the \
{event} placeholder in event paths exactly as written: it is replaced with the user's event.
- Reply in the language of the question. Be concise: one or two sentences, then numbered steps if there are \
steps. Use Markdown: **bold**, lists and [links](/path/). No headings, no tables, no code blocks.
"""

CHAT_TOOLS = [
    {
        "name": "search_docs",
        "description": (
            "Full-text search over the LarpManager tutorials and guides, which are in English. Returns the best "
            "matching sections, each with its text, its reference for read_doc and its URL. Use precise English "
            "terms, preferably the feature and page names of the catalog."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "English keywords; supports OR between alternatives and quoted phrases.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "read_doc",
        "description": (
            "Read the full text of a tutorial, or of one of its sections, by reference: 'tutorial-slug' or "
            "'tutorial-slug#section-slug', as given in the tutorial index or in search results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Tutorial reference, like 'tickets#waiting-list'."},
            },
            "required": ["ref"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


@dataclass
class ChatContext:
    """What the assistant knows about the user asking: their page, event and organization."""

    page_label: str = ""
    page_tutorial: str = ""
    run_slug: str = ""
    event_state: list[str] = field(default_factory=list)
    association_features: list[str] = field(default_factory=list)
    association_configs: str = ""

    def describe(self) -> str:
        """Render the context as the text block sent along with the question."""
        lines = []
        if self.page_label:
            lines.append(f"Current page: {self.page_label}")
        lines.extend(self.event_state)
        if self.association_features:
            lines.append("Active organization features: " + ", ".join(self.association_features))
        if self.association_configs:
            lines.append(f"Organization configuration set: {self.association_configs}")
        if not self.event_state and not self.association_features:
            lines.append("No event or organization data available: answer in general terms.")
        return "\n".join(lines)


def _page_path(slug: str, *, is_event: bool) -> str:
    """Return the path of a management page, with the event placeholder for event pages."""
    try:
        if is_event:
            return reverse(slug, args=[_EVENT_PATH_PLACEHOLDER]).replace(_EVENT_PATH_PLACEHOLDER, EVENT_PLACEHOLDER)
        return reverse(slug)
    except NoReverseMatch:
        return ""


def _feature_catalog() -> str:
    """Describe every feature with its pages, the map from user words to where things are configured."""
    pages_by_feature: dict[int, list[str]] = {}
    for model, is_event in ((EventPermission, True), (AssociationPermission, False)):
        prefix = "Event" if is_event else "Organization"
        for permission in model.objects.filter(hidden=False).order_by("module__order", "number", "slug"):
            path = _page_path(permission.slug, is_event=is_event)
            descr = f": {permission.descr}" if permission.descr else ""
            pages_by_feature.setdefault(permission.feature_id, []).append(
                f"  - {prefix} > {permission.name} ({path}){descr}"
            )

    lines = [
        "# Feature catalog",
        (
            f"Event features are turned on in Event > Features ({_page_path('orga_features', is_event=True)}), "
            f"or directly at /{EVENT_PLACEHOLDER}/activate/<feature-slug>/. Organization features are turned on "
            f"in Organization > Features ({_page_path('exe_features', is_event=False)}), or directly at "
            "/activate/<feature-slug>/. Features marked 'always active' need no activation."
        ),
    ]
    current_module = None
    for feature in Feature.objects.filter(hidden=False).select_related("module").order_by("module__order", "order"):
        module_name = feature.module.name if feature.module else "Base"
        if module_name != current_module:
            lines.append(f"\n## {module_name}")
            current_module = module_name
        scope = "organization" if feature.overall else "event"
        status = "always active" if feature.placeholder else f"slug {feature.slug}"
        tutorial = f" Tutorial: {feature.tutorial}." if feature.tutorial else ""
        lines.append(f"- {feature.name} ({scope} feature, {status}): {feature.descr}{tutorial}")
        lines.extend(pages_by_feature.get(feature.id, []))
    return "\n".join(lines)


class _AllFeatures:
    """Stands for a feature set containing every feature, to list all the configuration options."""

    def __contains__(self, item: object) -> bool:
        return True

    def __getitem__(self, key: str) -> int:
        return 1

    def get(self, _key: str, _default: object = None) -> int:
        return 1


def _config_fields(form_class: type, instance: object) -> list[dict]:
    """Return the configuration options a config form offers when every feature is active."""
    form = object.__new__(form_class)
    form.instance = instance
    form.params = {"features": _AllFeatures(), "association_id": 0}
    form.collect_configs()
    return form.config_fields


def _config_catalog() -> str:
    """Describe every configuration option, with the page and section where it is set."""
    lines = [
        "# Configuration catalog",
        (
            "Options are grouped by section; the options of a section exist only when its feature is active. "
            "Option keys are in brackets."
        ),
    ]
    for prefix, form_class, instance, slug, is_event in (
        ("Event", OrgaConfigForm, Event(), "orga_config", True),
        ("Organization", ExeConfigForm, Association(), "exe_config", False),
    ):
        lines.append(f"\n## {prefix} > Configuration")
        current_section = None
        for config in _config_fields(form_class, instance):
            if config["section"] != current_section:
                current_section = config["section"]
                path = _page_path(slug, is_event=is_event).rstrip("/") + f"/{config['section_slug']}/"
                lines.append(f"### {prefix} > Configuration > {current_section} ({path})")
            lines.append(f"- {config['label']} [{config['key']}]: {config['help_text']}")
    return "\n".join(lines)


def _enabled_configs(element_id: int, model_name: str) -> str:
    """List the configuration options set on an event or organization, with short values."""
    enabled = []
    for key, value in sorted(get_element_configs(element_id, model_name).items()):
        text = str(value).strip()
        if not text or text.lower() in {"false", "0", "none"}:
            continue
        enabled.append(key if text.lower() == "true" else f"{key}={text[:CHAT_MAX_CONFIG_VALUE_LENGTH]}")
    return ", ".join(enabled) or "none"


def _tutorial_index() -> str:
    """List the tutorials with their sections, so the model knows what read_doc can open."""
    lines = ["# Tutorial index (open with read_doc)"]
    for slug, name, sections in get_tutorial_index():
        lines.append(f"- {name} [{slug}]: " + "; ".join(sections))
    return "\n".join(lines)


def _guides_text() -> str:
    """Return the full text of the guides, the step-by-step walkthroughs of the main flows."""
    blocks = ["# Guides"]
    blocks.extend(f"## {title} ({url})\n{text}" for title, url, text in get_guides_markdown())
    return "\n\n".join(blocks)


def get_chat_knowledge() -> str:
    """Return the static part of the system prompt, identical across requests so it is prompt-cached."""
    knowledge = cache.get(CHAT_KNOWLEDGE_CACHE_KEY)
    if knowledge is None:
        with override("en"):
            sections = (_feature_catalog(), _config_catalog(), _tutorial_index(), _guides_text())
            knowledge = "\n\n".join(sections)
        cache.set(CHAT_KNOWLEDGE_CACHE_KEY, knowledge, timeout=CHAT_KNOWLEDGE_CACHE_TIMEOUT)
    return knowledge


def _get_page_context(page_slug: str) -> tuple[str, str]:
    """Return the label and the tutorial reference of a management page, if it is one."""
    slug = page_slug.removesuffix("_edit").removesuffix("_new")
    for model in (EventPermission, AssociationPermission):
        permission = model.objects.filter(slug=slug).select_related("feature").first()
        if permission:
            return f"{permission.name}: {permission.descr}", permission.feature.tutorial
    return "", ""


def _active_feature_slugs(features: dict | list) -> list[str]:
    """Return the sorted slugs of the real features among the given enabled ones."""
    return sorted(Feature.objects.filter(slug__in=list(features)).values_list("slug", flat=True))


def get_event_state(run: Run) -> list[str]:
    """Describe the status of a run and the features active on its event."""
    return [
        f"Current event: {run.event.name}, session {run.number}",
        f"Event status: {run.get_development_display()}",
        f"Registrations: {run.get_registration_status_display()}",
        f"Registration opening date: {run.registration_open or 'not set'}",
        f"Secret registration link: {'set' if run.registration_secret else 'not set'}",
        "Active event features: " + (", ".join(_active_feature_slugs(get_event_features(run.event_id))) or "none"),
        "Event configuration set: " + _enabled_configs(run.event.parent_id or run.event_id, "event"),
    ]


def build_chat_context(
    page_slug: str = "",
    run: Run | None = None,
    association_id: int | None = None,
    association_features: dict | list | None = None,
) -> ChatContext:
    """Collect the context of a question: the page, and the event or organization the user manages.

    Organization data is included only when association_id is given, for users with an organization role.
    """
    page_label, page_tutorial = _get_page_context(page_slug[:CHAT_MAX_PAGE_LENGTH])
    return ChatContext(
        page_label=page_label,
        page_tutorial=page_tutorial,
        run_slug=run.get_slug() if run else "",
        event_state=get_event_state(run) if run else [],
        association_features=_active_feature_slugs(association_features or []) if association_id else [],
        association_configs=_enabled_configs(association_id, "association") if association_id else "",
    )


def clean_history(raw_history: str) -> list[dict[str, str]]:
    """Validate the previous exchanges sent by the client, keeping the last complete ones."""
    try:
        history = json.loads(raw_history or "[]")
    except ValueError:
        return []
    if not isinstance(history, list):
        return []

    messages = []
    expected_role = "user"
    for item in history:
        if not isinstance(item, dict):
            return []
        role, content = item.get("role"), item.get("content")
        if role != expected_role or not isinstance(content, str) or not content.strip():
            return []
        messages.append({"role": role, "content": content.strip()[:CHAT_MAX_HISTORY_LENGTH]})
        expected_role = "assistant" if role == "user" else "user"

    # Keep only complete exchanges, the most recent ones
    if len(messages) % 2:
        messages.pop()
    return messages[-CHAT_MAX_HISTORY_MESSAGES:]


def _format_doc(doc: dict[str, str]) -> str:
    """Format a documentation section as a tool result entry."""
    title = f"{doc['title']} - {doc['section']}" if doc["section"] else doc["title"]
    ref = f"ref: {doc['ref']} | " if doc.get("ref") else ""
    return f"### {title}\n{ref}url: {doc['url']}\n{doc['text'][:CHAT_MAX_DOC_LENGTH]}"


def _run_tool(name: str, tool_input: dict, docs: dict[str, dict]) -> tuple[str, bool]:
    """Execute a tool call, collecting the documents it returns.

    Returns:
        The tool result text, and whether it is an error.

    """
    if name == "search_docs":
        query = str(tool_input.get("query", "")).strip()
        if not query:
            return "Empty query.", True
        results = (search_tutorials(query) + search_guides(query))[:CHAT_MAX_SEARCH_RESULTS]
        if not results:
            return "No results. Try other terms, or the feature names of the catalog.", False
        for doc in results:
            docs.setdefault(doc["url"], doc)
        return "\n\n".join(_format_doc(doc) for doc in results), False

    if name == "read_doc":
        doc = get_tutorial_doc(str(tool_input.get("ref", "")).strip())
        if not doc:
            return "No tutorial with this reference: check the tutorial index.", True
        docs.setdefault(doc["url"], doc)
        return _format_doc(doc), False

    return f"Unknown tool {name}.", True


def _call_anthropic(messages: list[dict], docs: dict[str, dict]) -> str | None:
    """Run the assistant on the conversation, executing its documentation lookups.

    Alerts the admins and returns None on failure.
    """
    api_key = conf_settings.ANTHROPIC_API_KEY
    use_local_login = getattr(conf_settings, "ANTHROPIC_USE_LOCAL_LOGIN", False)
    if not api_key and not use_local_login:
        notify_admins("Chat assistant: Anthropic API key not configured")
        return None

    system = [
        {"type": "text", "text": CHAT_INSTRUCTIONS.format(ticket_url=reverse("ticket"), event=EVENT_PLACEHOLDER)},
        {"type": "text", "text": get_chat_knowledge(), "cache_control": {"type": "ephemeral"}},
    ]
    # Without a key, the SDK uses the local "ant auth login" credentials
    client_kwargs = {"api_key": api_key} if api_key else {}
    client = anthropic.Anthropic(**client_kwargs, timeout=CHAT_TIMEOUT, max_retries=1)
    messages = list(messages)

    try:
        for tool_round in range(CHAT_MAX_TOOL_ROUNDS + 1):
            response = client.beta.messages.create(
                model=CHAT_MODEL,
                max_tokens=CHAT_MAX_TOKENS,
                betas=CHAT_BETAS,
                fallbacks="default",
                output_config={"effort": CHAT_EFFORT},
                system=system,
                tools=CHAT_TOOLS,
                # On the last round, no more lookups: the model must answer with what it has
                tool_choice={"type": "none"} if tool_round == CHAT_MAX_TOOL_ROUNDS else {"type": "auto"},
                messages=messages,
            )
            if response.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                text, is_error = _run_tool(block.name, block.input or {}, docs)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": is_error})
            messages.append({"role": "user", "content": results})
    except anthropic.APIError as error:
        notify_admins("Chat assistant: Anthropic request failed", str(error), error)
        return None

    if response.stop_reason == "refusal":
        return None
    return "".join(block.text for block in response.content if block.type == "text").strip()


def _resolve_links(answer: str, run_slug: str) -> str:
    """Point the event page links of an answer to the user's event, or to the event chooser."""
    target = f"/{run_slug}/" if run_slug else "/redirect/event/"
    return answer.replace(f"/{EVENT_PLACEHOLDER}/", target)


def _unavailable_answer() -> dict:
    """Build the answer given when a service failure prevents a real one."""
    return {
        "answer": str(_("The assistant is temporarily unavailable, please try again later.")),
        "sources": [],
        "unavailable": True,
    }


def get_chat_answer(
    question: str, context: ChatContext | None = None, history: list | None = None, *, use_cache: bool = True
) -> dict:
    """Answer a user question from the LarpManager documentation and the state of their event.

    The model gets the feature catalog and the guides in a prompt-cached system prompt, the user
    context with the question, and tools to search and read the tutorials. Answers to first
    questions are cached per question and context; failed answers are not cached.

    Args:
        question: The user's question.
        context: The page, event and organization of the user.
        history: Previous exchanges of the conversation, as user/assistant messages.
        use_cache: Whether to reuse and store cached answers.

    Returns:
        Dict with the Markdown "answer" and the "sources" list of {"title", "url"} it relied on;
        "unavailable" is set when a service failure prevented a real answer.

    """
    question = (question or "").strip()
    if not question:
        return {"answer": "", "sources": []}

    context = context or ChatContext()
    history = history or []

    page_doc = get_tutorial_doc(context.page_tutorial) if context.page_tutorial else None
    context_text = context.describe()
    cache_input = f"{get_language()}|{context.page_tutorial}|{context_text}|{question.lower()}"
    cache_key = "chat_answer_" + hashlib.sha256(cache_input.encode()).hexdigest()
    use_cache = use_cache and not history
    if use_cache:
        cached_answer = cache.get(cache_key)
        if cached_answer is not None:
            return _with_links(cached_answer, context.run_slug)

    user_content = f"<user_context>\n{context_text}\n</user_context>\n\n"
    if page_doc:
        user_content += f"<current_page_tutorial>\n{_format_doc(page_doc)}\n</current_page_tutorial>\n\n"
    user_content += f"Question: {question}"

    docs: dict[str, dict] = {}
    answer = _call_anthropic([*history, {"role": "user", "content": user_content}], docs)
    if not answer:
        return _unavailable_answer()

    result = {
        "answer": answer,
        "sources": [
            {"title": f"{doc['title']} - {doc['section']}" if doc["section"] else doc["title"], "url": url}
            for url, doc in docs.items()
            if url.split("#")[0] in answer
        ],
    }
    if use_cache:
        cache.set(cache_key, result, timeout=CHAT_ANSWER_CACHE_TIMEOUT)
    return _with_links(result, context.run_slug)


def _with_links(result: dict, run_slug: str) -> dict:
    """Return a copy of an answer with its event links resolved for the user."""
    return {**result, "answer": _resolve_links(result["answer"], run_slug)}


def get_chat_quota_key(association_id: int) -> tuple[str, int] | None:
    """Return the cache key and timeout of today's answer counter, or None if the association has no quota.

    Only free plan associations have a daily quota, which resets at midnight in their timezone.
    """
    if not association_id:
        return None

    plan = Association.objects.filter(pk=association_id).values_list("plan", flat=True).first()
    if plan != AssociationPlan.FREE:
        return None

    timezone_name = get_association_basic_cache(association_id).get("timezone") or "UTC"
    try:
        now = datetime.now(ZoneInfo(timezone_name))
    except (KeyError, ValueError):
        now = datetime.now(ZoneInfo("UTC"))
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return f"chat_quota_{association_id}_{now.date().isoformat()}", int((midnight - now).total_seconds()) + 60


def is_chat_quota_reached(quota_key: tuple[str, int] | None) -> bool:
    """Return whether the daily answers of the quota are all used."""
    return quota_key is not None and (cache.get(quota_key[0]) or 0) >= CHAT_FREE_DAILY_LIMIT


def count_chat_answer(quota_key: tuple[str, int] | None) -> None:
    """Count an answer given against the daily quota."""
    if quota_key is None:
        return
    cache_key, timeout = quota_key
    cache.add(cache_key, 0, timeout=timeout)
    try:
        cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=timeout)
