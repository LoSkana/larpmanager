#!/usr/bin/env python3
"""Optimized script to add type hints with minimal Claude credits usage.

Strategy:
1. Use ruff --unsafe-fixes to auto-fix simple type hints (FREE - ~730 fixes)
2. Update CSV to remove already fixed functions
3. Use Claude only for complex cases that ruff cannot handle
4. Use shorter, optimized prompts
"""

import subprocess
import sys
from pathlib import Path
from typing import Any


def run_ruff_autofixes() -> bool | None:
    """Run ruff with --unsafe-fixes to automatically add simple type hints."""
    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "ANN", "--unsafe-fixes", "--fix"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Parse output to see how many fixes were applied
        if "fixed" in result.stdout:
            pass
        else:
            pass

        return True
    except Exception:  # noqa: BLE001 - Refactoring tool must handle all parsing errors gracefully
        return False


def get_remaining_violations() -> Any:
    """Get list of functions that still have type hint violations after ruff fixes."""
    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "ANN", "--output-format=json"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode not in (0, 1):
            return None

        import json

        errors = json.loads(result.stdout)

        # Group by file and function
        violations = {}
        for error in errors:
            file_path = error.get("filename", "")
            line = error.get("location", {}).get("row", 0)

            key = f"{file_path}::{line}"
            if key not in violations:
                violations[key] = {"file": file_path, "line": line}

        return list(violations.values())

    except Exception:  # noqa: BLE001 - Refactoring tool must handle all parsing errors gracefully
        return None


def extract_function_name_at_line(file_path: Any, line_number: Any) -> Any:
    """Extract function name from source file at given line number."""
    try:
        with Path(file_path).open(encoding="utf-8") as f:
            lines = f.readlines()

        # Look backwards from target line to find function definition
        start_line = max(0, line_number - 10)
        relevant_lines = lines[start_line : line_number + 1]

        for i in range(len(relevant_lines) - 1, -1, -1):
            line = relevant_lines[i].strip()
            if line.startswith("def "):
                return line[4 : line.index("(")].strip()

        return None
    except Exception:  # noqa: BLE001 - Refactoring tool must handle all parsing errors gracefully
        return None


def update_csv_with_remaining(csv_path: Any, remaining_violations: Any) -> Any:
    """Update CSV to only include functions that still need type hints."""
    # Extract function names for remaining violations
    remaining_functions = []
    for violation in remaining_violations:
        func_name = extract_function_name_at_line(violation["file"], violation["line"])
        if func_name:
            remaining_functions.append({"file": violation["file"], "function": func_name})

    # Remove duplicates
    seen = set()
    unique_functions = []
    for func in remaining_functions:
        key = f"{func['file']}::{func['function']}"
        if key not in seen:
            seen.add(key)
            unique_functions.append(func)

    # Write to CSV
    with Path(csv_path).open("w", encoding="utf-8") as f:
        f.write("file,function\n")
        for func in unique_functions:
            f.write(f"{func['file']},{func['function']}\n")

    return len(unique_functions)


def main() -> None:
    """Run the optimization process."""
    # Step 1: Run ruff auto-fixes
    if not run_ruff_autofixes():
        sys.exit(1)


    # Step 2: Get remaining violations
    remaining = get_remaining_violations()

    if remaining is None:
        sys.exit(1)


    # Step 3: Update CSV
    csv_path = Path.cwd() / "refactor" / "missing_type_hints.csv"
    if csv_path.exists():
        update_csv_with_remaining(csv_path, remaining)

    else:
        pass


if __name__ == "__main__":
    main()
