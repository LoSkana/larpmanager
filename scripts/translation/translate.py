"""Translate LarpManager UI strings through a configured agent CLI.

The module is also imported by ``manage.py translate``. It uses the same
Codex/Claude CLI approach as ``review.py`` so authentication is managed by
the selected CLI rather than by the Django command. Strings are sent in small
batches to avoid repeating the prompt for every translation.
"""

import argparse
import json
import subprocess
from pathlib import Path

try:
    from .prompt_settings import translation_context
except ImportError:  # Direct execution: python scripts/translation/translate.py
    from prompt_settings import translation_context


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SYSTEM_PROMPT = """You translate UI strings for LarpManager, a LARP event
management platform. Translate the supplied English source string into the
requested target language.

{context}

Rules:
- Preserve every placeholder exactly, including Python placeholders such as
  %(name)s and %s, brace placeholders such as {{count}}, HTML tags, URLs, and
  line breaks.
- Translate only each source string; do not add explanations or punctuation
  that is not warranted by its source.
- Return only a JSON array of translations, with no Markdown fences. Its items
  must be in exactly the same order as the input strings.
""".format(context=translation_context())


class AgentTranslationError(RuntimeError):
    """Raised when the configured agent cannot produce a translation."""


def _agent_command(agent: str, prompt: str, model: str | None) -> list[str]:
    if agent == "codex":
        command = ["codex", "exec", "--cd", str(REPO_ROOT), "--sandbox", "read-only"]
        if model:
            command.extend(["--model", model])
        return [*command, prompt]
    if agent == "claude":
        command = ["claude", "-p", prompt, "--allowedTools", "Read", "--permission-mode", "bypassPermissions"]
        if model:
            command.extend(["--model", model])
        return command
    raise AgentTranslationError(f"Unsupported translation agent {agent!r}; choose codex or claude.")


def translate_entries(sources: list[str], target_language: str, agent: str, model: str | None = None) -> list[str]:
    """Translate an ordered batch of source strings using Codex or Claude."""
    if not sources:
        return []

    prompt = (
        f"{SYSTEM_PROMPT}\nTarget language: {target_language}\n"
        f"Source strings: {json.dumps(sources, ensure_ascii=False, separators=(',', ':'))}"
    )
    try:
        completed = subprocess.run(
            _agent_command(agent, prompt, model), check=True, capture_output=True, text=True
        )
    except FileNotFoundError as exc:
        raise AgentTranslationError(f"{agent} CLI not found; install it and ensure `{agent}` is on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise AgentTranslationError(f"{agent} CLI failed with exit code {exc.returncode}.") from exc

    try:
        response = json.loads(completed.stdout)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AgentTranslationError(f"{agent} did not return a valid translation JSON array.") from exc

    if not isinstance(response, list):
        raise AgentTranslationError(f"{agent} did not return a JSON array.")
    if len(response) != len(sources) or not all(isinstance(translation, str) for translation in response):
        raise AgentTranslationError(f"{agent} did not return exactly one string translation per input entry.")
    return response


def translate_text(source: str, target_language: str, agent: str, model: str | None = None) -> str:
    """Translate one source string; retained for callers that need one result."""
    return translate_entries([source], target_language, agent, model)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_language", help="target locale code, e.g. fr")
    parser.add_argument("source", nargs="+", help="one or more English source strings to translate")
    parser.add_argument("--agent", choices=("codex", "claude"), default="codex")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    print(json.dumps(translate_entries(args.source, args.target_language, args.agent, args.model), ensure_ascii=False))


if __name__ == "__main__":
    main()
