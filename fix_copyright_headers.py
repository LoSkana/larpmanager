#!/usr/bin/env python3
"""Script to restore copyright headers to files that had them removed.

This script compares files between the current branch and the target branch,
identifies files where copyright headers were removed, and restores them.
"""
import subprocess
import sys
from pathlib import Path

COPYRIGHT_HEADER = """# LarpManager - https://larpmanager.com
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
"""

def file_has_copyright(filepath: Path) -> bool:
    """Check if a file has the copyright header."""
    if not filepath.exists():
        return False

    content = filepath.read_text(encoding="utf-8")
    return "# LarpManager - https://larpmanager.com" in content[:500]

def get_files_from_branch(branch: str) -> list[str]:
    """Get list of Python files modified in the branch."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", f"origin/{branch}"],
            capture_output=True,
            text=True,
            check=True
        )
        files = [f for f in result.stdout.strip().split("\n") if f.endswith(".py")]
        return files
    except subprocess.CalledProcessError as e:
        print(f"Error getting files from branch: {e}")
        return []

def file_had_copyright_in_head(filepath: str) -> bool:
    """Check if the file had copyright header in HEAD."""
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{filepath}"],
            capture_output=True,
            text=True,
            check=True
        )
        return "# LarpManager - https://larpmanager.com" in result.stdout[:500]
    except subprocess.CalledProcessError:
        return False

def add_copyright_header(filepath: Path) -> bool:
    """Add copyright header to a file."""
    try:
        content = filepath.read_text(encoding="utf-8")

        # If file starts with "from __future__ import annotations", place header before it
        if content.startswith("from __future__ import annotations"):
            new_content = COPYRIGHT_HEADER + content
        else:
            new_content = COPYRIGHT_HEADER + content

        filepath.write_text(new_content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"Error adding copyright to {filepath}: {e}")
        return False

def main():
    """Main function to restore copyright headers."""
    branch = "claude/remove-pyproject-rules-011CV616bpqZBuLAB1wtakTb"

    print(f"Analyzing files from branch: {branch}")
    files = get_files_from_branch(branch)

    print(f"Found {len(files)} Python files modified in branch")

    files_fixed = 0
    files_to_fix = []

    # First, identify files that need fixing
    for filepath_str in files:
        filepath = Path(filepath_str)

        if not filepath.exists():
            continue

        # Check if file had copyright in HEAD but doesn't have it now
        had_copyright = file_had_copyright_in_head(filepath_str)
        has_copyright = file_has_copyright(filepath)

        if had_copyright and not has_copyright:
            files_to_fix.append(filepath)

    print(f"\nFiles missing copyright headers: {len(files_to_fix)}")

    if files_to_fix:
        print("\nFiles to fix:")
        for f in files_to_fix[:10]:
            print(f"  - {f}")
        if len(files_to_fix) > 10:
            print(f"  ... and {len(files_to_fix) - 10} more")

        response = input("\nRestore copyright headers to these files? (y/n): ")
        if response.lower() == "y":
            for filepath in files_to_fix:
                if add_copyright_header(filepath):
                    files_fixed += 1
                    print(f"✓ Fixed: {filepath}")

            print(f"\nRestored copyright headers to {files_fixed} files")
        else:
            print("Cancelled")
    else:
        print("\nNo files need copyright header restoration")

    return 0 if files_fixed > 0 or len(files_to_fix) == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
