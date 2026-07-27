#!/bin/bash
# Drives review.py end-to-end: next-chunk -> configured headless agent CLI
# review -> ingest, looped until pending entries run out or a limit is hit.
# Each iteration is a real agent CLI turn, billed to the CLI session/plan.
#
# Without --lang, round-robins one chunk per pending language per pass
# (cs, de, es, ... then back to cs) instead of draining one language first.
#
# Usage:
#   scripts/translation_review_run.sh [--agent AGENT] [--lang LANG] [--max-chunks N] [--model MODEL]
#
# Env overrides: CONFIG (path to translation_review_config.json)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
CONFIG="${CONFIG:-$SCRIPT_DIR/review_config.json}"
TR="$PYTHON $SCRIPT_DIR/review.py"

LANG_FILTER=""
MAX_CHUNKS=0
MODEL=""
AGENT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --agent) AGENT="$2"; shift 2 ;;
    --lang) LANG_FILTER="$2"; shift 2 ;;
    --max-chunks) MAX_CHUNKS="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

process_one_chunk() {
  local lang="$1"
  out=$($TR next-chunk --lang "$lang")
  echo "$out"
  if echo "$out" | grep -q "no pending entries"; then
    return 1
  fi

  local review_args=()
  if [ -n "$AGENT" ]; then
    review_args+=(--agent "$AGENT")
  fi
  if [ -n "$MODEL" ]; then
    review_args+=(--model "$MODEL")
  fi
  $TR review "${review_args[@]}"

  $TR ingest
  return 0
}

count=0

if [ -n "$LANG_FILTER" ]; then
  # single-language mode: drain that language chunk by chunk
  while true; do
    if [ "$MAX_CHUNKS" -gt 0 ] && [ "$count" -ge "$MAX_CHUNKS" ]; then
      echo "run: reached --max-chunks=$MAX_CHUNKS, stopping"
      break
    fi
    process_one_chunk "$LANG_FILTER" || break
    count=$((count + 1))
  done
else
  # round-robin mode: one chunk per pending language per pass
  while true; do
    if [ "$MAX_CHUNKS" -gt 0 ] && [ "$count" -ge "$MAX_CHUNKS" ]; then
      echo "run: reached --max-chunks=$MAX_CHUNKS, stopping"
      break
    fi

    mapfile -t langs < <($TR pending-langs)
    if [ "${#langs[@]}" -eq 0 ]; then
      echo "run: no pending entries in any language"
      break
    fi

    for lang in "${langs[@]}"; do
      if [ "$MAX_CHUNKS" -gt 0 ] && [ "$count" -ge "$MAX_CHUNKS" ]; then
        echo "run: reached --max-chunks=$MAX_CHUNKS, stopping"
        break 2
      fi
      process_one_chunk "$lang" && count=$((count + 1))
    done
  done
fi

echo "run: done, $count chunks processed"
