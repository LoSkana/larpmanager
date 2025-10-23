#!/usr/bin/env python3
"""
Script to automatically improve functions using Claude Code CLI.
Can accept a specific function as input or process from function_pydocs.csv.
Processes each function: adds type hints, improves docstrings, adds comments.
"""

import argparse
import ast
import csv
import re
import subprocess
import sys
import time
from pathlib import Path


def convert_path(csv_path: str) -> Path:
    """Convert CSV path to current project path."""
    parts = csv_path.split("larpmanager/")
    if len(parts) >= max_parts():
        relative = "larpmanager/" + parts[-1]
        return Path.cwd() / relative
    return Path(csv_path)


def max_parts():
    return 2


def extract_function_from_file(file_path: Path, function_name: str, function_number: int = 1) -> str | None:
    """Extract the source code of a specific function from a file.

    Args:
        file_path: Path to the Python file
        function_name: Name of the function to extract
        function_number: Which occurrence of the function to extract (1-based)
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

        tree = ast.parse("".join(lines))

        # Collect all function definitions with the matching name
        matching_functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    matching_functions.append(node)

        # Sort by line number to maintain file order
        matching_functions.sort(key=lambda n: n.lineno)

        # Check if the requested function number exists
        if function_number > len(matching_functions) or function_number < 1:
            return None

        # Get the requested function (convert to 0-based index)
        target_function = matching_functions[function_number - 1]
        start_line = target_function.lineno - 1  # Convert to 0-based
        end_line = target_function.end_lineno
        return "".join(lines[start_line:end_line])

    except Exception as e:
        print(f"  ⚠️  Error extracting function: {e}")
        return None


def improve_function_with_claude_code(
    function_name: str, file_path: Path, function_source: str = None
) -> tuple[bool, str | None]:
    """
    Call Claude Code CLI to improve the function.
    Returns (success, improved_function_source).
    """
    if function_source is None:
        function_source = extract_function_from_file(file_path, function_name)
        if function_source is None:
            return False, None

    # Create the prompt for Claude Code
    prompt = f"""Migliora questa funzione Python:

```python
{function_source}
```

1. Aggiungi type hints alla definizione della funzione (parametri e return type), non usare single o double quote per le classi
2. Migliora il docstring seguendo lo stile Google/NumPy. Se la funzione è più corta di 10 linee, tieni un docstring molto conciso
3. Aggiungi commenti inline ogni 4-5 linee o per ogni blocco logico

IMPORTANTE:
- Restituisci SOLO il codice della funzione migliorata, senza spiegazioni aggiuntive
- NON aggiungere MAI import statements
- MANTIENI esattamente la stessa indentazione della funzione originale
- Non modificare l'indentazione esistente del codice
- Non modificare in NESSUN MODO la logica del codice originale
"""

    try:
        # Call Claude Code with --print flag for non-interactive mode
        result = subprocess.run(
            ["claude", "--print"],
            check=False,
            input=prompt,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
        )

        # Check if successful
        if result.returncode == 0:
            output = result.stdout.strip()

            # Extract code blocks from the output
            code_match = re.search(r"```python\n(.*?)\n```", output, re.DOTALL)
            if code_match:
                improved_code = code_match.group(1)
                return True, improved_code
            elif output and "def " in output:
                # Sometimes Claude returns code without markdown blocks
                return True, output
            else:
                print("  ⚠️  Claude Code returned but no valid code found")
                return False, None
        else:
            print(f"  ❌ Claude Code returned error (code {result.returncode})")
            if result.stderr:
                print(f"  ❌ Error details: {result.stderr}")
            return False, None

    except subprocess.TimeoutExpired:
        print("  ❌ Claude Code timed out after 5 minutes")
        return False, None
    except Exception as e:
        print(f"  ❌ Error calling Claude Code: {e}")
        return False, None


def get_function_line_range(file_path: Path, function_name: str, function_number: int = 1) -> tuple[int, int] | None:
    """
    Get the line range of a function in a file.

    Args:
        file_path: Path to the Python file
        function_name: Name of the function to find
        function_number: Which occurrence of the function to find (1-based)

    Returns:
        (start_line, end_line) or None if not found.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)

        # Collect all function definitions with the matching name
        matching_functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    matching_functions.append(node)

        # Sort by line number to maintain file order
        matching_functions.sort(key=lambda n: n.lineno)

        # Check if the requested function number exists
        if function_number > len(matching_functions) or function_number < 1:
            return None

        # Get the requested function (convert to 0-based index)
        target_function = matching_functions[function_number - 1]
        return target_function.lineno, target_function.end_lineno

    except Exception as e:
        print(f"  ⚠️  Error parsing file: {e}")
        return None


def get_function_indentation(function_source: str) -> str:
    """Extract the base indentation of a function from its source code."""
    lines = function_source.split("\n")
    for line in lines:
        if line.strip().startswith("def ") or line.strip().startswith("async def "):
            # Count leading whitespace
            return line[: len(line) - len(line.lstrip())]
    return ""


def normalize_function_indentation(improved_code: str, original_indentation: str) -> str:
    """Ensure the improved function maintains the original indentation."""
    lines = improved_code.split("\n")
    if not lines:
        return improved_code

    # Remove any leading/trailing empty lines
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        return improved_code

    # Find the current indentation of the function definition
    def_line = None
    for line in lines:
        if line.strip().startswith("def ") or line.strip().startswith("async def "):
            def_line = line
            break

    if not def_line:
        return improved_code

    current_indentation = def_line[: len(def_line) - len(def_line.lstrip())]

    # If indentations are the same, return as is
    if current_indentation == original_indentation:
        return "\n".join(lines)

    # Adjust indentation
    adjusted_lines = []
    for line in lines:
        if line.strip():  # Non-empty line
            if line.startswith(current_indentation):
                # Replace current indentation with original indentation
                adjusted_line = original_indentation + line[len(current_indentation) :]
                adjusted_lines.append(adjusted_line)
            else:
                # Line doesn't start with expected indentation, keep as is
                adjusted_lines.append(line)
        else:
            # Empty line
            adjusted_lines.append(line)

    return "\n".join(adjusted_lines)


def replace_function_in_file(
    file_path: Path, function_name: str, new_function_code: str, original_function: str, function_number: int = 1
) -> bool:
    """Replace a function in a file with improved code, maintaining original indentation.

    Args:
        file_path: Path to the Python file
        function_name: Name of the function to replace
        new_function_code: The improved function code
        original_function: The original function source
        function_number: Which occurrence of the function to replace (1-based)
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

        tree = ast.parse("".join(lines))

        # Collect all function definitions with the matching name
        matching_functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    matching_functions.append(node)

        # Sort by line number to maintain file order
        matching_functions.sort(key=lambda n: n.lineno)

        # Check if the requested function number exists
        if function_number > len(matching_functions) or function_number < 1:
            return False

        # Get the requested function (convert to 0-based index)
        target_function = matching_functions[function_number - 1]
        start_line = target_function.lineno - 1  # Convert to 0-based
        end_line = target_function.end_lineno

        # Get original indentation and normalize the improved code
        original_indentation = get_function_indentation(original_function)
        normalized_code = normalize_function_indentation(new_function_code, original_indentation)

        # Replace the function
        new_lines = lines[:start_line] + [normalized_code + "\n"] + lines[end_line:]

        # Write back to file
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        return True

    except Exception as e:
        print(f"  ⚠️  Error replacing function: {e}")
        return False


def improve_single_function(file_path: str, function_name: str) -> bool:
    """Improve a single function specified by the user."""
    file_path = Path(file_path)

    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return False

    print(f"🔍 Extracting function '{function_name}' from {file_path}")

    # Extract original function
    original_function = extract_function_from_file(file_path, function_name)
    if original_function is None:
        print(f"❌ Function '{function_name}' not found in {file_path}")
        return False

    print("📄 Original function:")
    print("-" * 60)
    print(original_function)
    print("-" * 60)

    # Improve function
    print("🤖 Calling Claude Code to improve function...")
    success, improved_function = improve_function_with_claude_code(function_name, file_path, original_function)

    if not success or not improved_function:
        print("❌ Failed to improve function")
        return False

    print("✨ Improved function:")
    print("-" * 60)
    print(improved_function)
    print("-" * 60)

    # Ask user for confirmation
    response = input("🔄 Replace the function in the file? (y/N): ").lower().strip()
    if response == "y":
        if replace_function_in_file(file_path, function_name, improved_function, original_function):
            print(f"✅ Successfully replaced function '{function_name}' in {file_path}")
            return True
        else:
            print("❌ Failed to replace function in file")
            return False
    else:
        print("ℹ️  Function not replaced")
        return False


def process_csv_batch():
    """Process functions from CSV file in batch mode."""
    csv_path = Path.cwd() / "refactor/function_pydocs.csv"

    while True:
        # Read all rows from CSV
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                print("\n✅ All functions processed!")
                break
            fieldnames = reader.fieldnames

        # Process first row
        row = rows[0]
        function_name = row["name"]
        csv_file_path = row["path"]
        function_number = int(row.get("number", 1))  # Default to 1 for backward compatibility

        print(f"\nProcessing: {function_name} #{function_number} in {csv_file_path}")

        # Convert path
        file_path = convert_path(csv_file_path)

        success = False

        if not file_path.exists():
            print(f"  ⚠️  File not found: {file_path}")
            success = True  # Skip this entry
        else:
            # Get function line range
            line_range = get_function_line_range(file_path, function_name, function_number)
            if not line_range:
                print(f"  ⚠️  Function {function_name} #{function_number} not found in {file_path}")
                success = True  # Skip this entry
            else:
                start_line, end_line = line_range
                print(f"  📝 Found function at lines {start_line}-{end_line}")

                # Call Claude Code to improve
                print("  🤖 Calling Claude Code...")
                original_function = extract_function_from_file(file_path, function_name, function_number)
                success, improved_code = improve_function_with_claude_code(function_name, file_path)
                if success and improved_code and original_function:
                    if replace_function_in_file(file_path, function_name, improved_code, original_function, function_number):
                        print(f"  ✅ Successfully processed {function_name} #{function_number}")
                        success = True
                    else:
                        print(f"  ❌ Failed to replace {function_name} #{function_number}")
                        success = False
                else:
                    print(f"  ❌ Failed to improve {function_name} #{function_number}")

        # Remove processed row from CSV if successful or skipped
        if success:
            remaining_rows = rows[1:]
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(remaining_rows)
            print(f"  🗑️  Removed from CSV ({len(remaining_rows)} remaining)")
        else:
            print("  ⏳  Wait 5 minutes before trying again...")
            time.sleep(5 * 60)


def main():
    parser = argparse.ArgumentParser(description="Improve Python functions using Claude Code CLI")
    parser.add_argument("--file", help="Path to Python file containing the function")
    parser.add_argument("--function", help="Name of the function to improve")

    args = parser.parse_args()

    if args.file and args.function:
        # Single function mode
        if not improve_single_function(args.file, args.function):
            sys.exit(1)
    else:
        # CSV batch mode
        if args.file or args.function:
            print("❌ Both --file and --function are required for single function mode")
            sys.exit(1)
        process_csv_batch()


if __name__ == "__main__":
    main()
