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
"""Tests for ZIP file security validation."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import pytest

from larpmanager.utils.security import ZipSecurityError, safe_extract_zip


class TestZipSecurityValidation:
    """Test ZIP security validation and safe extraction."""

    def test_safe_extraction_valid_zip(self, tmp_path: Path) -> None:
        """Test that valid ZIP files extract successfully."""
        # Create a test ZIP file
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "Hello World")
            zf.writestr("subdir/file.txt", "Nested file")

        # Extract to a safe location
        extract_path = tmp_path / "extracted"
        safe_extract_zip(zip_path, extract_path)

        # Verify files were extracted
        assert (extract_path / "test.txt").exists()
        assert (extract_path / "subdir" / "file.txt").exists()
        assert (extract_path / "test.txt").read_text() == "Hello World"

    def test_path_traversal_absolute_path(self, tmp_path: Path) -> None:
        """Test that absolute paths in ZIP are rejected."""
        zip_path = tmp_path / "malicious.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Create a malicious ZIP with absolute path
            zf.writestr("/etc/passwd", "malicious content")

        extract_path = tmp_path / "extracted"

        with pytest.raises(ZipSecurityError, match="Absolute path detected"):
            safe_extract_zip(zip_path, extract_path)

    def test_path_traversal_relative_parent(self, tmp_path: Path) -> None:
        """Test that parent directory traversal is rejected."""
        zip_path = tmp_path / "malicious.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Create a malicious ZIP with ../ traversal
            zf.writestr("../../etc/passwd", "malicious content")

        extract_path = tmp_path / "extracted"

        with pytest.raises(ZipSecurityError, match="Directory traversal detected"):
            safe_extract_zip(zip_path, extract_path)

    def test_path_traversal_symlink_escape(self, tmp_path: Path) -> None:
        """Test that symlinks attempting to escape are rejected."""
        zip_path = tmp_path / "malicious.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Create entry that would resolve outside extraction dir
            zf.writestr("valid/../../outside.txt", "malicious content")

        extract_path = tmp_path / "extracted"

        with pytest.raises(ZipSecurityError, match="traversal"):
            safe_extract_zip(zip_path, extract_path)

    def test_zip_bomb_file_count(self, tmp_path: Path) -> None:
        """Test that ZIP with too many files is rejected."""
        zip_path = tmp_path / "bomb.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Create more files than allowed (MAX_FILE_COUNT = 1000)
            for i in range(1001):
                zf.writestr(f"file{i}.txt", "content")

        extract_path = tmp_path / "extracted"

        with pytest.raises(ZipSecurityError, match="too many files"):
            safe_extract_zip(zip_path, extract_path)

    def test_zip_bomb_file_size(self, tmp_path: Path) -> None:
        """Test that ZIP with oversized file is rejected."""
        zip_path = tmp_path / "bomb.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
            # Create a file larger than MAX_FILE_SIZE (50 MB)
            large_content = b"A" * (51 * 1024 * 1024)  # 51 MB
            zf.writestr("large.bin", large_content)

        extract_path = tmp_path / "extracted"

        with pytest.raises(ZipSecurityError, match="File too large"):
            safe_extract_zip(zip_path, extract_path)

    def test_zip_bomb_total_size(self, tmp_path: Path) -> None:
        """Test that ZIP exceeding total size limit is rejected."""
        zip_path = tmp_path / "bomb.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
            # Create multiple files totaling more than MAX_ARCHIVE_SIZE (100 MB)
            for i in range(3):
                content = b"B" * (40 * 1024 * 1024)  # 40 MB each = 120 MB total
                zf.writestr(f"file{i}.bin", content)

        extract_path = tmp_path / "extracted"

        with pytest.raises(ZipSecurityError, match="total uncompressed size too large"):
            safe_extract_zip(zip_path, extract_path)

    def test_zip_bomb_compression_ratio(self, tmp_path: Path) -> None:
        """Test that highly compressed files (potential ZIP bombs) are rejected."""
        zip_path = tmp_path / "bomb.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Create highly compressible content (all zeros)
            # This will have a very high compression ratio
            content = b"\x00" * (10 * 1024 * 1024)  # 10 MB of zeros compresses to ~10 KB
            zf.writestr("compressible.bin", content)

        extract_path = tmp_path / "extracted"

        with pytest.raises(ZipSecurityError, match="Suspicious compression ratio"):
            safe_extract_zip(zip_path, extract_path)

    def test_extraction_creates_directory(self, tmp_path: Path) -> None:
        """Test that extraction creates target directory if it doesn't exist."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        extract_path = tmp_path / "new_dir" / "nested" / "extracted"
        safe_extract_zip(zip_path, extract_path)

        assert extract_path.exists()
        assert (extract_path / "test.txt").exists()

    def test_relative_extraction_path_rejected(self, tmp_path: Path) -> None:
        """Test that relative extraction paths are rejected."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        with pytest.raises(ValueError, match="must be absolute"):
            safe_extract_zip(zip_path, "relative/path")

    def test_zipfile_object_extraction(self, tmp_path: Path) -> None:
        """Test extraction using ZipFile object instead of path."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        extract_path = tmp_path / "extracted"

        # Open and pass ZipFile object
        with zipfile.ZipFile(zip_path, "r") as zf:
            safe_extract_zip(zf, extract_path)

        assert (extract_path / "test.txt").exists()

    def test_empty_zip(self, tmp_path: Path) -> None:
        """Test that empty ZIP files are handled correctly."""
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w"):
            pass  # Create empty ZIP

        extract_path = tmp_path / "extracted"
        safe_extract_zip(zip_path, extract_path)

        # Should create directory but not fail
        assert extract_path.exists()

    def test_zip_with_directories_only(self, tmp_path: Path) -> None:
        """Test ZIP containing only directory entries."""
        zip_path = tmp_path / "dirs.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Add directory entries
            zf.writestr("dir1/", "")
            zf.writestr("dir1/dir2/", "")

        extract_path = tmp_path / "extracted"
        safe_extract_zip(zip_path, extract_path)

        assert extract_path.exists()
