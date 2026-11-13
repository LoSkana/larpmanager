#!/bin/bash
# Fail if Git LFS files used at runtime are still pointers (git-lfs missing or not pulled)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

POINTERS=$(grep -rlI "^version https://git-lfs.github.com/spec" "$DIR/larpmanager/static/tutorials" 2>/dev/null)
if [ -n "$POINTERS" ]; then
    echo "ERROR: Git LFS files not downloaded, run: git lfs install && git lfs pull"
    echo "$POINTERS" | head -5
    exit 1
fi
