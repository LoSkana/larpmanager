"""Script to analyze Python files and count function invocations.

This script walks through all .py files in the larpmanager codebase, identifies all function
definitions, and counts how many times each function is called from within other
functions in the same codebase. Only functions defined in larpmanager and invoked
at least once are included in the output.

Output format: CSV file with columns: name, path, invocation_count, function_number
"""

import ast
import os
from collections import defaultdict
from pathlib import Path


class FunctionAnalyzer(ast.NodeVisitor):
    """AST visitor to collect function definitions and their invocations."""

    def __init__(self, path):
        self.path = path
        self.functions = []  # List of (function_name, function_number) tuples
        self.function_counts = defaultdict(int)  # Track count of each function name
        self.invocations = []  # List of function names called in this file
        self.current_function = None

    def visit_FunctionDef(self, node):
        """Visit function definitions."""
        # Count occurrence of this function name in this file
        self.function_counts[node.name] += 1
        function_number = self.function_counts[node.name]

        # Store function definition with its number
        self.functions.append((node.name, function_number))

        # Track we're inside a function to count invocations
        previous_function = self.current_function
        self.current_function = node.name

        # Continue visiting child nodes
        self.generic_visit(node)

        # Restore previous function context
        self.current_function = previous_function

    def visit_AsyncFunctionDef(self, node):
        """Visit async function definitions."""
        self.visit_FunctionDef(node)

    def visit_Call(self, node):
        """Visit function calls."""
        # Only count calls that happen inside a function
        if self.current_function is not None:
            # Get the function name being called
            func_name = None

            if isinstance(node.func, ast.Name):
                # Direct function call: foo()
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                # Method call: obj.method()
                # We track the method name
                func_name = node.func.attr

            if func_name:
                self.invocations.append(func_name)

        # Continue visiting child nodes
        self.generic_visit(node)


def analyze_file(path):
    """Analyze a single Python file for function definitions and invocations.

    Args:
        path: Path to the Python file

    Returns:
        tuple: (functions set, invocations list) or (None, None) if parsing fails

    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content, filename=str(path))
        analyzer = FunctionAnalyzer(str(path))
        analyzer.visit(tree)

        return analyzer.functions, analyzer.invocations
    except (SyntaxError, UnicodeDecodeError, Exception) as e:
        # Silently skip files that can't be parsed
        return None, None


def find_python_files(root_dir):
    """Find all Python files in the larpmanager directory.

    Args:
        root_dir: Root directory to search

    Yields:
        Path objects for each .py file found in larpmanager/

    """
    root_path = Path(root_dir)
    larpmanager_dir = root_path / "larpmanager"

    if not larpmanager_dir.exists():
        print(f"Warning: larpmanager directory not found at {larpmanager_dir}")
        return

    # Directories to skip
    skip_dirs = {
        "__pycache__", ".pytest_cache", "migrations", "staticfiles",
        ".tox", "dist", "build", ".eggs", "tests"
    }

    for py_file in larpmanager_dir.rglob("*.py"):
        # Skip files in excluded directories
        if any(skip_dir in py_file.parts for skip_dir in skip_dirs):
            continue
        yield py_file


def main():
    """Main function to run the analysis."""
    # Get the project root (parent of refactor directory)
    script_dir = Path.cwd()
    project_root = script_dir

    print(f"Analyzing Python files in larpmanager/")

    # First pass: collect all function definitions
    all_defined_functions = {}  # func_name -> list of (path, rel_path, function_number)
    all_invocations = []  # list of (func_name, from_file)

    file_count = 0
    for py_file in find_python_files(project_root):
        functions, invocations = analyze_file(py_file)

        if functions is None:
            continue

        file_count += 1
        rel_path = str(py_file.relative_to(project_root))

        # Store function definitions with their numbers
        for func_name, func_number in functions:
            if func_name not in all_defined_functions:
                all_defined_functions[func_name] = []
            all_defined_functions[func_name].append((str(py_file), rel_path, func_number))

        # Store invocations
        for func_name in invocations:
            all_invocations.append((func_name, rel_path))

    print(f"Analyzed {file_count} Python files in larpmanager/")
    print(f"Found {len(all_defined_functions)} unique function names defined in larpmanager")

    # Second pass: count invocations only for functions defined in larpmanager
    invocation_counts = defaultdict(int)

    for func_name, from_file in all_invocations:
        # Only count if this function is defined in larpmanager
        if func_name in all_defined_functions:
            invocation_counts[func_name] += 1

    # Prepare results - only functions with at least 1 invocation
    results = []

    for func_name, count in invocation_counts.items():
        if count >= 1:
            # A function might be defined in multiple files (same name)
            for abs_path, rel_path, func_number in all_defined_functions[func_name]:
                results.append({
                    "name": func_name,
                    "path": rel_path,
                    "invocation_count": count,
                    "function_number": func_number
                })

    # Sort by invocation count (descending), then by function name
    results.sort(key=lambda x: (-x["invocation_count"], x["name"], x["path"]))

    # Write results to CSV file
    output_file = Path("refactor/function_invocations.csv")
    with open(output_file, "w", encoding="utf-8") as f:
        # Write header
        f.write("name,path,invocation_count,function_number\n")

        # Write data
        for result in results:
            # Escape file path if it contains commas
            path = result["path"]
            if "," in path:
                path = f'"{path}"'

            f.write(f"{result['name']},{path},{result['invocation_count']},{result['function_number']}\n")

    print(f"\nResults written to: {output_file}")
    print(f"Total larpmanager functions with at least 1 invocation: {len(results)}")

    # Print top 20 most invoked functions
    print("\nTop 20 most invoked larpmanager functions:")
    for i, result in enumerate(results[:20], 1):
        print(f"{i}. {result['name']} ({result['path']}) #{result['function_number']}: {result['invocation_count']} invocations")


if __name__ == "__main__":
    main()
