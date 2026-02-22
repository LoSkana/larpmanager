#!/bin/bash

# Check for non-ASCII characters in staged files
# Excludes binary files, migrations, and certain allowed files

set -e

# Get list of staged files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)

if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

# Files and patterns to exclude
EXCLUDE_PATTERNS=(
    "*.pyc"
    "*.mo"
    "*.po"
    "*.pot"
    "*.json"
    "**/migrations/**"
    "**/static/**"
    "*.svg"
    "*.png"
    "*.jpg"
    "*.jpeg"
    "*.gif"
    "*.ico"
    "*.woff"
    "*.woff2"
    "*.ttf"
    "*.eot"
    "*.otf"
    "*.pdf"
    "*.zip"
    "*.tar"
    "*.gz"
    "*.db"
    "*.sqlite3"
)

# Build exclude arguments for grep
GREP_EXCLUDE=""
for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    GREP_EXCLUDE="$GREP_EXCLUDE --exclude=$pattern"
done

FOUND_NON_ASCII=0

# Check each staged file
for file in $STAGED_FILES; do
    # Skip if file doesn't exist (deleted files)
    if [ ! -f "$file" ]; then
        continue
    fi

    # Skip binary files
    if file "$file" | grep -q "binary"; then
        continue
    fi

    # Check if file should be excluded based on patterns
    SKIP=0
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        if [[ "$file" == $pattern ]] || [[ "$file" == *"$pattern"* ]]; then
            SKIP=1
            break
        fi
    done

    if [ $SKIP -eq 1 ]; then
        continue
    fi

    # Check for non-ASCII characters (excluding currency symbols)
    # Currency symbols to allow: € £ ¥ ¢ ₹ ₽ ₩ ₪ ₦ ₨ ₱ ₴ ₵ ₸ ₺ ₼ ₾
    if grep -P -n '[^\x00-\x7F]' "$file" | grep -Pv '[€£¥¢₹₽₩₪₦₨₱₴₵₸₺₼₾]' > /dev/null 2>&1; then
        echo "Non-ASCII characters found in: $file"
        grep -P -n '[^\x00-\x7F]' "$file" | grep -Pv '[€£¥¢₹₽₩₪₦₨₱₴₵₸₺₼₾]' | head -5
        if [ $(grep -P -c '[^\x00-\x7F]' "$file" | grep -Pv '[€£¥¢₹₽₩₪₦₨₱₴₵₸₺₼₾]') -gt 5 ]; then
            echo "   ... and more"
        fi
        FOUND_NON_ASCII=1
    fi
done

if [ $FOUND_NON_ASCII -eq 1 ]; then
    echo ""
    echo "   Non-ASCII characters detected in staged files."
    echo "   Please remove non-ASCII characters or update the exclusion list in scripts/check-ascii.sh"
    exit 1
fi

exit 0
