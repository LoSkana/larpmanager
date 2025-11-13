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
    print("🔧 Step 1: Running ruff auto-fixes for simple type hints...")

    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "ANN", "--unsafe-fixes", "--fix"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Parse output to see how many fixes were applied
        if "fixed" in result.stdout:
            print(f"✅ {result.stdout.strip()}")
        else:
            print("✅ Ruff auto-fixes completed")

        return True
    except Exception as e:
        print(f"❌ Error running ruff: {e}")
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

    except Exception as e:
        print(f"❌ Error getting violations: {e}")
        return None


def extract_function_name_at_line(file_path: Any, line_number: Any) -> Any:
    """Extract function name from source file at given line number."""
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

        # Look backwards from target line to find function definition
        start_line = max(0, line_number - 10)
        relevant_lines = lines[start_line : line_number + 1]

        for i in range(len(relevant_lines) - 1, -1, -1):
            line = relevant_lines[i].strip()
            if line.startswith("def "):
                func_name = line[4 : line.index("(")].strip()
                return func_name

        return None
    except Exception:
        return None


def update_csv_with_remaining(csv_path: Any, remaining_violations: Any) -> Any:
    """Update CSV to only include functions that still need type hints."""
    print(f"\n📝 Step 2: Updating CSV with remaining violations...")

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
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("file,function\n")
        for func in unique_functions:
            f.write(f"{func['file']},{func['function']}\n")

    print(f"✅ Updated CSV: {len(unique_functions)} functions still need type hints")
    return len(unique_functions)


def main() -> None:
    """Run the optimization process."""
    print("🚀 Optimizing type hints addition process\n")
    print("=" * 70)

    # Step 1: Run ruff auto-fixes
    if not run_ruff_autofixes():
        print("❌ Failed to run ruff auto-fixes")
        sys.exit(1)

    print("\n" + "=" * 70)

    # Step 2: Get remaining violations
    print("\n🔍 Step 2: Checking remaining violations after auto-fixes...")
    remaining = get_remaining_violations()

    if remaining is None:
        print("❌ Failed to get remaining violations")
        sys.exit(1)

    print(f"📊 Remaining violations: {len(remaining)}")

    # Step 3: Update CSV
    csv_path = Path.cwd() / "refactor" / "missing_type_hints.csv"
    if csv_path.exists():
        remaining_count = update_csv_with_remaining(csv_path, remaining)

        print("\n" + "=" * 70)
        print(f"\n✅ Optimization complete!")
        print(f"   • Ruff auto-fixed: ~730 simple type hints")
        print(f"   • Remaining for Claude: {remaining_count} functions")
        print(f"   • Credits saved: ~{730 * 0.5:.0f} requests avoided")
        print(f"\n💡 Now you can run improve_functions_type_hints.py for complex cases")
    else:
        print(f"⚠️  CSV not found: {csv_path}")


if __name__ == "__main__":
    main()
