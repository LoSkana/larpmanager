#!/usr/bin/env python3
"""
Script to automatically improve functions from function_analysis.csv using Claude Code CLI.
Processes each function: adds type hints, improves docstrings, adds comments.
"""

import ast
import csv
import subprocess
import tempfile
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


def improve_function_with_claude_code(function_name: str, file_path: Path, start_line: int, end_line: int) -> bool:
    """
    Call Claude Code CLI to improve the function.
    Returns True if successful, False otherwise.
    """
    # Create the prompt for Claude Code
    prompt = f"""Per la funzione `{function_name}` nel file {file_path} (righe {start_line}-{end_line}):

1. Aggiungi type hints alla definizione (parametri e return type)
2. Migliora il pydoc (docstring) seguendo lo stile Google/NumPy
3. Aggiungi commenti ogni 4-5 linee, oppure ogni blocco logico

NON aggiungere spiegazioni, fai solo le modifiche richieste.
"""

    try:
        # Write prompt to a temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write(prompt)
            tmp_path = tmp.name

        # Call Claude Code with the prompt via stdin
        result = subprocess.run(
            ["claude"],
            check=False,
            input=prompt,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
        )

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        # Check if successful
        if result.returncode == 0:
            return True
        else:
            print(f"  ❌ Claude Code returned error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("  ❌ Claude Code timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"  ❌ Error calling Claude Code: {e}")
        return False


def get_function_line_range(file_path: Path, function_name: str) -> tuple[int, int] | None:
    """
    Get the line range of a function in a file.
    Returns (start_line, end_line) or None if not found.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)

        # Find the function in the AST
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    return node.lineno, node.end_lineno

        return None
    except Exception as e:
        print(f"  ⚠️  Error parsing file: {e}")
        return None


def main():
    csv_path = Path.cwd() / "function_analysis.csv"

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

        print(f"\nProcessing: {function_name} in {csv_file_path}")

        # Convert path
        file_path = convert_path(csv_file_path)

        success = False

        if not file_path.exists():
            print(f"  ⚠️  File not found: {file_path}")
            success = True  # Skip this entry
        else:
            # Get function line range
            line_range = get_function_line_range(file_path, function_name)
            if not line_range:
                print(f"  ⚠️  Function {function_name} not found in {file_path}")
                success = True  # Skip this entry
            else:
                start_line, end_line = line_range
                print(f"  📝 Found function at lines {start_line}-{end_line}")

                # Call Claude Code to improve
                print("  🤖 Calling Claude Code...")
                if improve_function_with_claude_code(function_name, file_path, start_line, end_line):
                    print(f"  ✅ Successfully processed {function_name}")
                    success = True
                else:
                    print(f"  ❌ Failed to process {function_name}")

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


if __name__ == "__main__":
    main()
