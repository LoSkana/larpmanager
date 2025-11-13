import ast
import csv
import os
from collections import defaultdict
from typing import Any


def get_function_length(node: Any) -> int:
    if not hasattr(node, "body") or not node.body:
        return 0
    last_line = node.body[-1].lineno if hasattr(node.body[-1], "lineno") else node.lineno
    return last_line - node.lineno + 1


def has_docstring(node: Any) -> bool:
    """Check if a function has a docstring."""
    if not node.body:
        return False
    first_stmt = node.body[0]
    return (
        isinstance(first_stmt, ast.Expr)
        and isinstance(first_stmt.value, ast.Constant)
        and isinstance(first_stmt.value.value, str)
    )


def analyze_file(filepath: Any) -> list:
    with open(filepath, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return []

    results = []
    function_counts = defaultdict(int)  # Track count of each function name

    # Collect all function definitions first, sorted by line number
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions.append(node)

    # Sort by line number to maintain file order
    functions.sort(key=lambda n: n.lineno)

    for node in functions:
        # Count occurrence of this function name (for all functions)
        function_counts[node.name] += 1
        function_number = function_counts[node.name]

        # Only include functions WITHOUT docstrings
        if not has_docstring(node):
            length = get_function_length(node)
            results.append((node.name, filepath, length, function_number))

    return results


def main(folder: str = ".") -> None:
    all_results = []
    for root, _dirs, files in os.walk(folder):
        if any(excluded in root for excluded in ("venv", "tests", "migrations")):
            continue
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                all_results.extend(analyze_file(path))

    with open("refactor/function_pydocs.csv", "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["name", "path", "length", "number"])
        writer.writerows(all_results)


if __name__ == "__main__":
    main("larpmanager")
