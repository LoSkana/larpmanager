#!/usr/bin/env python3
"""Script to analyze uncommitted git changes and filter out pydoc/comment-only changes.
Prints only substantial code changes.
"""

import subprocess
import re
import sys
from typing import List, Tuple, Dict


def run_git_command(cmd: List[str]) -> str:
    """Run a git command and return its output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running git command: {e}", file=sys.stderr)
        return ""


def is_docstring_or_comment_line(line: str) -> bool:
    """Check if a line is a docstring, comment, or whitespace-only change."""
    stripped = line.strip()

    # Skip empty lines
    if not stripped:
        return True

    # Skip git diff markers
    if stripped.startswith(("@@", "+++", "---", "index", "diff --git")):
        return True

    # Get the actual content without +/- prefix
    if stripped.startswith(("+", "-")):
        content = stripped[1:].strip()
    else:
        content = stripped

    # Skip empty content
    if not content:
        return True

    # Check for function definitions
    if content.startswith("def "):
        return True

    # Check for comments
    if content.startswith("#"):
        return True

    # Check for docstrings (triple quotes)
    if ('"""' in content or "'''" in content):
        return True

    # Check for single-line string literals that look like docstrings
    # (often used as docstrings at the start of functions/classes)
    if re.match(r'^["\'].*["\']$', content):
        return True

    # Check for type hints and annotations (often just documentation)
    if re.match(r"^\s*->\s*.*:", content):
        return True

    # Check for docstring content (common patterns)
    docstring_patterns = [
        r"^\s*Args:\s*$",
        r"^\s*Returns:\s*$",
        r"^\s*Raises:\s*$",
        r"^\s*Note:\s*$",
        r"^\s*Example:\s*$",
        r"^\s*\w+\s*\([^)]*\):\s*.*$",  # Args descriptions
        r"^\s*\w+:\s+.*$",  # Parameter descriptions
    ]

    for pattern in docstring_patterns:
        if re.match(pattern, content, re.IGNORECASE):
            return True

    return False


def analyze_file_changes(file_diff: str) -> Tuple[bool, List[str]]:
    """Analyze changes in a file and determine if they're substantial.
    Returns (has_substantial_changes, substantial_lines).
    """
    lines = file_diff.split("\n")
    substantial_lines = []
    in_docstring = False
    docstring_delimiter = None

    for line in lines:
        stripped = line.strip()

        # Track if we're entering/exiting a docstring
        if '"""' in stripped or "'''" in stripped:
            # Count occurrences to handle single-line docstrings
            triple_double = stripped.count('"""')
            triple_single = stripped.count("'''")

            if triple_double > 0:
                if triple_double == 2:
                    # Single-line docstring (opening and closing on same line)
                    # Consider it as docstring content
                    if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                        continue  # Skip this line, it's a docstring
                elif not in_docstring:
                    # Starting a multi-line docstring
                    in_docstring = True
                    docstring_delimiter = '"""'
                    continue  # Skip the opening line
                elif in_docstring and docstring_delimiter == '"""':
                    # Closing a multi-line docstring
                    in_docstring = False
                    docstring_delimiter = None
                    continue  # Skip the closing line

            if triple_single > 0:
                if triple_single == 2:
                    # Single-line docstring
                    if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                        continue
                elif not in_docstring:
                    # Starting a multi-line docstring
                    in_docstring = True
                    docstring_delimiter = "'''"
                    continue
                elif in_docstring and docstring_delimiter == "'''":
                    # Closing a multi-line docstring
                    in_docstring = False
                    docstring_delimiter = None
                    continue

        # If we're inside a docstring, skip all changes
        if in_docstring:
            continue

        # Check for substantial changes outside of docstrings
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            if not is_docstring_or_comment_line(line):
                substantial_lines.append(line)

    return len(substantial_lines) > 0, substantial_lines


def main() -> None:
    """Main function to analyze git changes."""
    print("Analyzing uncommitted changes for substantial (non-documentation) modifications...\n")

    # Get list of modified files
    modified_files = run_git_command(["git", "diff", "--name-only", "HEAD"]).strip().split("\n")
    modified_files = [f for f in modified_files if f and f.endswith(".py")]

    if not modified_files:
        print("No Python files with uncommitted changes found.")
        return

    substantial_changes_found = False
    files_with_substantial_changes = []

    for file_path in modified_files:
        # Get diff for this file
        file_diff = run_git_command(["git", "diff", "HEAD", "--", file_path])

        if not file_diff:
            continue

        has_substantial, substantial_lines = analyze_file_changes(file_diff)

        if has_substantial:
            substantial_changes_found = True
            files_with_substantial_changes.append((file_path, substantial_lines))

    # Only print files with substantial changes
    for file_path, substantial_lines in files_with_substantial_changes:
        print(f"{'='*60}")
        print(f"Analyzing: {file_path}")
        print(f"{'='*60}")
        print(f"✗ SUBSTANTIAL CHANGES DETECTED ({len(substantial_lines)} lines)")
        print("\nSubstantial changes:")
        for line in substantial_lines[:20]:  # Limit to first 20 lines
            print(f"  {line}")
        if len(substantial_lines) > 20:
            print(f"  ... and {len(substantial_lines) - 20} more lines")
        print()

    print(f"{'='*60}")
    print("SUMMARY:")
    print(f"{'='*60}")

    if substantial_changes_found:
        print("❌ FILES WITH SUBSTANTIAL CHANGES FOUND!")
        print("The following files contain changes beyond documentation/comments.")
        print("Review these changes carefully before committing.")
    else:
        print("✅ ALL CHANGES APPEAR TO BE DOCUMENTATION/COMMENTS ONLY")
        print("These changes look safe to commit as documentation improvements.")


if __name__ == "__main__":
    main()
