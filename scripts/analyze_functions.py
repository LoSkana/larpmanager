#!/usr/bin/env python3
"""Analyze Python codebase and extract function statistics.

Outputs a CSV file with function name, file path, and line count, sorted by line count.
"""

import ast
import csv
from pathlib import Path
from typing import Any


def count_function_lines(node: Any) -> int:
    """Count the number of lines in a function definition."""
    if hasattr(node, "end_lineno") and hasattr(node, "lineno"):
        return node.end_lineno - node.lineno + 1
    return 0


def analyze_file(file_path: Any) -> list:
    """Extract all functions from a Python file with their line counts."""
    functions = []

    try:
        with Path(file_path).open(encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                line_count = count_function_lines(node)
                functions.append({"name": node.name, "path": str(file_path), "lines": line_count})
    except (SyntaxError, UnicodeDecodeError):
        # Skip files that can't be parsed
        pass

    return functions


def analyze_codebase(root_dir: str = ".") -> list:
    """Analyze all Python files in the codebase."""
    all_functions = []
    root_path = Path(root_dir)

    # Find all Python files, excluding common directories
    exclude_dirs = {"venv", ".venv", "env", "node_modules", ".git", "__pycache__", "migrations"}

    for py_file in root_path.rglob("*.py"):
        # Skip excluded directories
        if any(excluded in py_file.parts for excluded in exclude_dirs):
            continue

        functions = analyze_file(py_file)
        all_functions.extend(functions)

    return all_functions


def main() -> None:
    """Run the main analysis."""
    # Get the project root (parent of scripts directory)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Analyze codebase
    functions = analyze_codebase(project_root)

    # Sort by line count descending
    functions.sort(key=lambda x: x["lines"], reverse=True)

    # Write to CSV
    output_file = project_root / "function_analysis.csv"
    with output_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "path", "lines"])
        writer.writeheader()
        writer.writerows(functions)


    # Print top 10
    for _i, _func in enumerate(functions[:10], 1):
        pass


if __name__ == "__main__":
    main()
