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

from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from larpmanager.utils.validators import FileTypeValidator


class TestFileTypeValidator:
    """Test file type validation utility"""

    def test_init_with_valid_types(self):
        """Test validator initialization with valid mime types"""
        validator = FileTypeValidator(["image/jpeg", "application/pdf"])

        assert "image/jpeg" in validator.allowed_mimes
        assert "application/pdf" in validator.allowed_mimes
        assert validator.input_allowed_types == ["image/jpeg", "application/pdf"]

    def test_init_with_wildcard_types(self):
        """Test validator initialization with wildcard mime types"""
        validator = FileTypeValidator(["image/*", "application/*"])

        assert "image" in validator.allowed_mimes
        assert "application" in validator.allowed_mimes

    def test_init_with_extensions(self):
        """Test validator initialization with file extensions"""
        validator = FileTypeValidator(["image/jpeg"], [".jpg", ".jpeg"])

        assert validator.allowed_exts == [".jpg", ".jpeg"]

    def test_init_with_invalid_mime_type(self):
        """Test validator initialization with invalid mime type format"""
        with pytest.raises(ValidationError) as exc_info:
            FileTypeValidator(["invalid-mime-type"])

        assert "is not a valid type" in str(exc_info.value)

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_call_with_allowed_image_type(self, mock_magic):
        """Test validation with allowed image type"""
        mock_magic.return_value = "image/jpeg"

        validator = FileTypeValidator(["image/jpeg"])

        # Create mock file
        file_content = b"fake jpeg content"
        mock_file = Mock()
        mock_file.read.return_value = file_content
        mock_file.name = "test.jpg"
        mock_file.seek = Mock()

        # Should not raise exception
        validator(mock_file)

        mock_file.read.assert_called_once_with(2048)
        mock_file.seek.assert_called_once_with(0)

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_call_with_wildcard_type(self, mock_magic):
        """Test validation with wildcard mime type"""
        mock_magic.return_value = "image/png"

        validator = FileTypeValidator(["image/*"])

        mock_file = Mock()
        mock_file.read.return_value = b"fake png content"
        mock_file.name = "test.png"
        mock_file.seek = Mock()

        # Should not raise exception
        validator(mock_file)

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_call_with_disallowed_type(self, mock_magic):
        """Test validation with disallowed file type"""
        mock_magic.return_value = "application/executable"

        validator = FileTypeValidator(["image/jpeg"])

        mock_file = Mock()
        mock_file.read.return_value = b"fake exe content"
        mock_file.name = "malware.exe"
        mock_file.seek = Mock()

        with pytest.raises(ValidationError) as exc_info:
            validator(mock_file)

        assert "File type" in str(exc_info.value)
        assert "is not allowed" in str(exc_info.value)

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_call_with_disallowed_extension(self, mock_magic):
        """Test validation with disallowed file extension"""
        mock_magic.return_value = "image/jpeg"

        validator = FileTypeValidator(["image/jpeg"], [".jpg"])

        mock_file = Mock()
        mock_file.read.return_value = b"fake jpeg content"
        mock_file.name = "test.jpeg"  # .jpeg not in allowed .jpg
        mock_file.seek = Mock()

        with pytest.raises(ValidationError) as exc_info:
            validator(mock_file)

        assert "File extension" in str(exc_info.value)
        assert "is not allowed" in str(exc_info.value)

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_office_document_detection_word(self, mock_magic):
        """Test MS Office Word document detection"""
        # First call returns generic office type
        # Second call (in _check_word_or_excel) returns detailed type
        mock_magic.side_effect = ["application/vnd.ms-office", "Microsoft Word Document"]

        validator = FileTypeValidator(["application/msword"])

        mock_file = Mock()
        mock_file.read.return_value = b"fake word content"
        mock_file.name = "document.doc"
        mock_file.seek = Mock()

        # Should not raise exception after detection
        validator(mock_file)

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_office_document_detection_excel(self, mock_magic):
        """Test MS Office Excel document detection"""
        mock_magic.side_effect = ["application/octet-stream", "Microsoft Excel Worksheet"]

        validator = FileTypeValidator(["application/vnd.ms-excel"])

        mock_file = Mock()
        mock_file.read.return_value = b"fake excel content"
        mock_file.name = "spreadsheet.xls"
        mock_file.seek = Mock()

        # Should not raise exception after detection
        validator(mock_file)

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_ooxml_document_detection_by_extension(self, mock_magic):
        """Test OOXML document detection using file extension"""
        mock_magic.side_effect = ["application/vnd.ms-office", "Microsoft OOXML"]

        validator = FileTypeValidator(["application/msword"])

        mock_file = Mock()
        mock_file.read.return_value = b"fake docx content"
        mock_file.name = "document.docx"  # Extension determines type
        mock_file.seek = Mock()

        # Should not raise exception
        validator(mock_file)

    def test_normalize_wildcard_types(self):
        """Test normalization of wildcard mime types"""
        validator = FileTypeValidator(["text/*", "image/*", "application/pdf"])

        assert "text" in validator.allowed_mimes
        assert "image" in validator.allowed_mimes
        assert "application/pdf" in validator.allowed_mimes

    def test_normalize_bytes_input(self):
        """Test normalization handles bytes input"""
        validator = FileTypeValidator([b"image/jpeg"])

        assert "image/jpeg" in validator.allowed_mimes

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_real_file_validation(self, mock_magic):
        """Test validation with real Django uploaded file"""
        mock_magic.return_value = "text/plain"

        validator = FileTypeValidator(["text/plain"])

        # Create a real uploaded file
        file_content = b"This is test content"
        uploaded_file = SimpleUploadedFile(name="test.txt", content=file_content, content_type="text/plain")

        # Should not raise exception
        validator(uploaded_file)

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_validation_with_empty_extensions_list(self, mock_magic):
        """Test validation when no extensions are specified"""
        mock_magic.return_value = "image/jpeg"

        validator = FileTypeValidator(["image/jpeg"], [])

        mock_file = Mock()
        mock_file.read.return_value = b"fake jpeg content"
        mock_file.name = "test.exe"  # Wrong extension but should be ignored
        mock_file.seek = Mock()

        # Should not raise exception as no extensions specified
        validator(mock_file)

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_case_insensitive_extension_check(self, mock_magic):
        """Test that extension checking is case insensitive"""
        mock_magic.return_value = "image/jpeg"

        validator = FileTypeValidator(["image/jpeg"], [".jpg"])

        mock_file = Mock()
        mock_file.read.return_value = b"fake jpeg content"
        mock_file.name = "TEST.JPG"  # Uppercase extension
        mock_file.seek = Mock()

        # Should not raise exception
        validator(mock_file)

    def test_multiple_allowed_types_and_extensions(self):
        """Test validator with multiple allowed types and extensions"""
        validator = FileTypeValidator(["image/jpeg", "image/png", "application/pdf"], [".jpg", ".jpeg", ".png", ".pdf"])

        assert len(validator.allowed_mimes) == 3
        assert len(validator.allowed_exts) == 4

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_validation_error_messages(self, mock_magic):
        """Test that validation error messages contain proper information"""
        mock_magic.return_value = "application/executable"

        validator = FileTypeValidator(["image/jpeg", "application/pdf"])

        mock_file = Mock()
        mock_file.read.return_value = b"fake exe content"
        mock_file.name = "malware.exe"
        mock_file.seek = Mock()

        with pytest.raises(ValidationError) as exc_info:
            validator(mock_file)

        error_message = str(exc_info.value)
        assert "application/executable" in error_message
        assert "image/jpeg" in error_message
        assert "application/pdf" in error_message

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_extension_validation_error_message(self, mock_magic):
        """Test extension validation error message"""
        mock_magic.return_value = "image/jpeg"

        validator = FileTypeValidator(["image/jpeg"], [".jpg", ".png"])

        mock_file = Mock()
        mock_file.read.return_value = b"fake jpeg content"
        mock_file.name = "test.gif"
        mock_file.seek = Mock()

        with pytest.raises(ValidationError) as exc_info:
            validator(mock_file)

        error_message = str(exc_info.value)
        assert ".gif" in error_message
        assert ".jpg" in error_message
        assert ".png" in error_message

    def test_deconstructible_decorator(self):
        """Test that validator can be deconstructed for migrations"""
        validator = FileTypeValidator(["image/jpeg"], [".jpg"])

        # Should have the necessary attributes for Django migrations
        assert hasattr(validator, "__module__")
        assert hasattr(validator, "__qualname__")


class TestFileTypeValidatorIntegration:
    """Integration tests for FileTypeValidator"""

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_pdf_validation_workflow(self, mock_magic):
        """Test complete PDF validation workflow"""
        mock_magic.return_value = "application/pdf"

        validator = FileTypeValidator(["application/pdf"], [".pdf"])

        # Simulate PDF file upload
        pdf_content = b"%PDF-1.4 fake pdf content"
        mock_file = Mock()
        mock_file.read.return_value = pdf_content
        mock_file.name = "document.pdf"
        mock_file.seek = Mock()

        # Should validate successfully
        validator(mock_file)

        # Verify file was read and reset properly
        mock_file.read.assert_called_once_with(2048)
        mock_file.seek.assert_called_once_with(0)

    @patch("larpmanager.utils.validators.magic.from_buffer")
    def test_mixed_type_validation(self, mock_magic):
        """Test validation with mixed allowed types"""
        mock_magic.return_value = "text/csv"

        validator = FileTypeValidator(["image/*", "application/pdf", "text/csv"])

        mock_file = Mock()
        mock_file.read.return_value = b"col1,col2\nval1,val2"
        mock_file.name = "data.csv"
        mock_file.seek = Mock()

        # Should validate successfully
        validator(mock_file)
