#!/bin/bash
# Check that test files follow naming conventions:
# - playwright tests must end with _test.py
# - unit tests must start with test_
# - __init__.py and base.py are excluded

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Counter for errors
errors=0

echo "Checking test file naming conventions..."

# Check playwright tests (must end with _test.py)
playwright_dir="larpmanager/tests/playwright"
if [ -d "$playwright_dir" ]; then
    while IFS= read -r -d '' file; do
        basename=$(basename "$file")

        # Skip __init__.py and base.py files
        if [ "$basename" = "__init__.py" ] || [ "$basename" = "base.py" ]; then
            continue
        fi

        # Check if file doesn't end with _test.py
        if [[ ! "$basename" =~ _test\.py$ ]]; then
            echo -e "${RED}ERROR: Playwright test file does not follow naming convention: $file${NC}"
            echo "       Expected: *_test.py (e.g., ${basename%.py}_test.py)"
            errors=$((errors + 1))
        fi
    done < <(find "$playwright_dir" -maxdepth 1 -type f -name "*.py" -print0)
fi

# Check unit tests (must start with test_)
unit_dir="larpmanager/tests/unit"
if [ -d "$unit_dir" ]; then
    while IFS= read -r -d '' file; do
        basename=$(basename "$file")

        # Skip __init__.py and base.py files
        if [ "$basename" = "__init__.py" ] || [ "$basename" = "base.py" ]; then
            continue
        fi

        # Check if file doesn't start with test_
        if [[ ! "$basename" =~ ^test_ ]]; then
            echo -e "${RED}ERROR: Unit test file does not follow naming convention: $file${NC}"
            echo "       Expected: test_*.py (e.g., test_${basename})"
            errors=$((errors + 1))
        fi
    done < <(find "$unit_dir" -maxdepth 1 -type f -name "*.py" -print0)
fi

if [ $errors -eq 0 ]; then
    echo -e "${GREEN}✓ All test files follow the naming convention${NC}"
    exit 0
else
    echo -e "${RED}✗ Found $errors test file(s) with incorrect naming${NC}"
    echo ""
    echo "Naming conventions:"
    echo "  - larpmanager/tests/playwright/ files must end with '_test.py'"
    echo "  - larpmanager/tests/unit/ files must start with 'test_'"
    echo "  - Exceptions: __init__.py and base.py"
    exit 1
fi
