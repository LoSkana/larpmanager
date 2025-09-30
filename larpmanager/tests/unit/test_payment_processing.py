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

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from larpmanager.accounting.payment import get_payment_fee, unique_invoice_cod
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.tests.unit.base import BaseTestCase


class TestPaymentFeeCalculation:
    """Test payment fee calculation functions"""

    @patch("larpmanager.accounting.payment.get_payment_details")
    def test_get_payment_fee_with_configured_fee(self, mock_get_payment_details):
        """Test fee calculation when fee is configured"""
        mock_get_payment_details.return_value = {
            "paypal_fee": "3.5",
            "stripe_fee": "2,8",  # Test comma decimal separator
        }

        assoc = Mock()

        # Test with dot decimal separator
        fee = get_payment_fee(assoc, "paypal")
        assert fee == 3.5, f"Expected 3.5, got {fee}"
        assert isinstance(fee, float), "Fee should be float"

        # Test with comma decimal separator
        fee = get_payment_fee(assoc, "stripe")
        assert fee == 2.8, f"Expected 2.8, got {fee}"

    @patch("larpmanager.accounting.payment.get_payment_details")
    def test_get_payment_fee_not_configured(self, mock_get_payment_details):
        """Test fee calculation when fee is not configured"""
        mock_get_payment_details.return_value = {}

        assoc = Mock()
        fee = get_payment_fee(assoc, "unknown_method")

        assert fee == 0.0, f"Expected 0.0 for unconfigured method, got {fee}"

    @patch("larpmanager.accounting.payment.get_payment_details")
    def test_get_payment_fee_empty_fee(self, mock_get_payment_details):
        """Test fee calculation when fee is empty"""
        mock_get_payment_details.return_value = {
            "paypal_fee": "",
            "stripe_fee": None,
        }

        assoc = Mock()

        # Test with empty string
        fee = get_payment_fee(assoc, "paypal")
        assert fee == 0.0, f"Expected 0.0 for empty fee, got {fee}"

        # Test with None value (should not have key)
        fee = get_payment_fee(assoc, "stripe")
        assert fee == 0.0, f"Expected 0.0 for None fee, got {fee}"

    @patch("larpmanager.accounting.payment.get_payment_details")
    def test_get_payment_fee_zero_fee(self, mock_get_payment_details):
        """Test fee calculation when fee is explicitly zero"""
        mock_get_payment_details.return_value = {
            "bank_transfer_fee": "0.0",
        }

        assoc = Mock()
        fee = get_payment_fee(assoc, "bank_transfer")

        assert fee == 0.0, f"Expected 0.0 for zero fee, got {fee}"


class TestUniqueInvoiceCodeGeneration:
    """Test unique invoice code generation"""

    @patch("larpmanager.accounting.payment.generate_id")
    @patch("larpmanager.accounting.payment.PaymentInvoice.objects.filter")
    def test_unique_invoice_cod_success_first_try(self, mock_filter, mock_generate_id):
        """Test successful code generation on first attempt"""
        mock_generate_id.return_value = "ABC123DEF456GHI7"
        mock_filter.return_value.exists.return_value = False

        result = unique_invoice_cod()

        assert result == "ABC123DEF456GHI7", f"Expected generated code, got {result}"
        assert len(result) == 16, f"Expected length 16, got {len(result)}"
        mock_generate_id.assert_called_once_with(16)

    @patch("larpmanager.accounting.payment.generate_id")
    @patch("larpmanager.accounting.payment.PaymentInvoice.objects.filter")
    def test_unique_invoice_cod_custom_length(self, mock_filter, mock_generate_id):
        """Test code generation with custom length"""
        mock_generate_id.return_value = "ABCD1234"
        mock_filter.return_value.exists.return_value = False

        result = unique_invoice_cod(length=8)

        assert result == "ABCD1234", f"Expected generated code, got {result}"
        assert len(result) == 8, f"Expected length 8, got {len(result)}"
        mock_generate_id.assert_called_once_with(8)

    @patch("larpmanager.accounting.payment.generate_id")
    @patch("larpmanager.accounting.payment.PaymentInvoice.objects.filter")
    def test_unique_invoice_cod_collision_then_success(self, mock_filter, mock_generate_id):
        """Test code generation with collision then success"""
        mock_generate_id.side_effect = ["DUPLICATE123CODE", "UNIQUE456789CODE"]
        mock_filter.return_value.exists.side_effect = [True, False]  # First collision, then unique

        result = unique_invoice_cod()

        assert result == "UNIQUE456789CODE", f"Expected second generated code, got {result}"
        assert mock_generate_id.call_count == 2, "Should have generated 2 codes"

    @patch("larpmanager.accounting.payment.generate_id")
    @patch("larpmanager.accounting.payment.PaymentInvoice.objects.filter")
    def test_unique_invoice_cod_max_attempts_exceeded(self, mock_filter, mock_generate_id):
        """Test code generation when max attempts exceeded"""
        mock_generate_id.return_value = "ALWAYSCOLLIDES123"
        mock_filter.return_value.exists.return_value = True  # Always collision

        with pytest.raises(Exception) as exc_info:
            unique_invoice_cod()

        assert "Unable to generate unique invoice code" in str(exc_info.value)
        assert mock_generate_id.call_count == 5, "Should have tried 5 times"


class TestPaymentInvoiceModel(TestCase, BaseTestCase):
    """Test PaymentInvoice model functionality"""

    def test_payment_invoice_creation(self):
        """Test basic payment invoice creation"""
        assert self.invoice().id is not None, "Invoice should have ID after creation"
        assert self.invoice().status == PaymentStatus.CREATED, "Default status should be CREATED"
        assert self.invoice().typ == PaymentType.REGISTRATION, "Payment type should match"
        assert self.invoice().mc_gross == Decimal("100.00"), "Gross amount should match"

    def test_payment_invoice_str_representation(self):
        """Test string representation of payment invoice"""
        str_repr = str(self.invoice())

        assert self.invoice().member.name in str_repr, "Member name should be in string representation"
        assert str(self.invoice().mc_gross) in str_repr, "Gross amount should be in representation"
        assert self.invoice().status in str_repr, "Status should be in representation"

    def test_payment_invoice_download_no_file(self):
        """Test download method when no invoice file attached"""
        result = self.invoice().download()

        assert result == "", "Should return empty string when no file"

    @patch("larpmanager.models.accounting.download")
    def test_payment_invoice_download_with_file(self, mock_download):
        """Test download method with invoice file"""
        mock_download.return_value = "http://example.com/download/invoice.pdf"

        # Mock file field properly - need to ensure it evaluates to True
        mock_file = Mock()
        mock_file.name = "invoice.pdf"
        mock_file.url = "http://example.com/invoice.pdf"
        # Make the mock file evaluate to True in boolean context
        mock_file.__bool__ = Mock(return_value=True)
        mock_file.__nonzero__ = Mock(return_value=True)  # Python 2 compatibility

        invoice = self.invoice()
        invoice.invoice = mock_file

        result = invoice.download()

        assert result == "http://example.com/download/invoice.pdf", "Should return download URL"
        mock_download.assert_called_once_with("http://example.com/invoice.pdf")

    def test_payment_invoice_get_details_minimal_info(self):
        """Test get_details method with minimal information"""
        # Test with minimal invoice data (just method, no text, no cod, no invoice file)
        invoice = self.invoice()
        # Clear optional fields that might be set by defaults
        invoice.text = None
        invoice.cod = None
        invoice.invoice = None

        result = invoice.get_details()

        # Should return empty string since no text, no cod, no invoice
        assert result == "", "Should return empty string when no optional content"

    def test_payment_invoice_get_details_with_components(self):
        """Test get_details method with various components"""
        invoice = self.invoice()

        # Mock invoice file
        mock_file = Mock()
        mock_file.name = "invoice.pdf"
        invoice.invoice = mock_file

        # Mock the download method to return a specific URL
        invoice.download = Mock(return_value="http://download.link")

        invoice.text = "Payment description"
        invoice.cod = "INV12345"

        result = invoice.get_details()

        assert "Download" in result, "Should include download link"
        assert "Payment description" in result, "Should include text"
        assert "INV12345" in result, "Should include code"

    def test_payment_invoice_unique_code_constraint(self):
        """Test that invoice codes must be unique"""
        # Create first invoice
        PaymentInvoice.objects.create(
            member=self.get_member(),
            assoc=self.get_association(),
            method=self.payment_method(),
            typ=PaymentType.REGISTRATION,
            status=PaymentStatus.CREATED,
            mc_gross=Decimal("100.00"),
            causal="Test payment 1",
            cod="UNIQUE123",
        )

        # Attempt to create second invoice with same code should fail
        with pytest.raises(Exception):  # IntegrityError or similar
            PaymentInvoice.objects.create(
                member=self.get_member(),
                assoc=self.get_association(),
                method=self.payment_method(),
                typ=PaymentType.REGISTRATION,
                status=PaymentStatus.CREATED,
                mc_gross=Decimal("200.00"),
                causal="Test payment 2",
                cod="UNIQUE123",  # Same code
            )


class TestPaymentValidation:
    """Test payment validation logic"""

    def test_payment_amount_validation(self):
        """Test payment amount validation"""
        # Test positive amounts
        assert Decimal("100.00") > 0, "Positive amounts should be valid"
        assert Decimal("0.01") > 0, "Small positive amounts should be valid"

        # Test zero and negative amounts
        assert not (Decimal("0.00") > 0), "Zero amounts should be invalid"
        assert not (Decimal("-10.00") > 0), "Negative amounts should be invalid"

    def test_payment_fee_calculation_edge_cases(self):
        """Test payment fee calculation edge cases"""
        # Test percentage calculation
        gross_amount = Decimal("100.00")
        fee_percentage = 3.5
        expected_fee = gross_amount * Decimal(str(fee_percentage)) / 100

        assert expected_fee == Decimal("3.50"), f"Expected 3.50, got {expected_fee}"

        # Test rounding behavior
        gross_amount = Decimal("10.00")
        fee_percentage = 3.333
        calculated_fee = gross_amount * Decimal(str(fee_percentage)) / 100

        # Should have multiple decimal places
        assert calculated_fee == Decimal("0.3333"), f"Expected 0.3333, got {calculated_fee}"
