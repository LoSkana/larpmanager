#!/usr/bin/env bash

# Records and composes one guide video: ./scripts/guide_video.sh campaign
# Uses its own test database. Outputs to .guide_videos/output/<slug>/
set -euo pipefail

SLUG="${1:?usage: guide_video.sh <storyboard slug>}"
PYTHON_BIN="${VENV_PYTHON:-.venv/bin/python}"
STORYBOARD_DIR="larpmanager/tests/playwright/guide_videos"
MUSIC=".guide_videos/music/Inspired.mp3"
MUSIC_URL="https://incompetech.com/music/royalty-free/mp3-royaltyfree/Inspired.mp3"

if [[ ! -f "$MUSIC" ]]; then
  mkdir -p "$(dirname "$MUSIC")"
  curl -sSLf -o "$MUSIC" "$MUSIC_URL"
fi

POSTGRES_DB=guide_videos PYTEST_XDIST_WORKER=vid xvfb-run -a -s "-screen 0 1920x1080x24" \
  "$PYTHON_BIN" -m pytest "$STORYBOARD_DIR/${SLUG}_storyboard.py" -x -q -p no:cacheprovider

"$PYTHON_BIN" "$STORYBOARD_DIR/compose.py" ".guide_videos/output/$SLUG" "$MUSIC" larpmanager/static/lm_logo.png

echo "Done: .guide_videos/output/$SLUG/guide.mp4"
