import ast
import csv
import os


def get_function_length(node):
    if not hasattr(node, "body") or not node.body:
        return 0
    last_line = node.body[-1].lineno if hasattr(node.body[-1], "lineno") else node.lineno
    return last_line - node.lineno + 1


def analyze_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return []
    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            length = get_function_length(node)
            results.append((node.name, filepath, length))
    return results


def main(folder="."):
    all_results = []
    for root, _dirs, files in os.walk(folder):
        if any(excluded in root for excluded in ("venv", "tests", "migrations")):
            continue
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                all_results.extend(analyze_file(path))

    with open("function_analysis.csv", "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["function_name", "file_path", "length"])
        writer.writerows(all_results)


if __name__ == "__main__":
    main("larpmanager")
