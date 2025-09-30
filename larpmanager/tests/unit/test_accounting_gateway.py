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

import json
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.http import Http404
from django.test import RequestFactory, TestCase

from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.tests.unit.base import BaseTestCase


class TestSatispayGateway(TestCase, BaseTestCase):
    """Test Satispay payment gateway functions"""

    def setup_method(self):
        self.factory = RequestFactory()

    @patch("larpmanager.accounting.gateway.satispaython.create_payment")
    @patch("larpmanager.accounting.gateway.load_key")
    def test_get_satispay_form_success(self, mock_load_key, mock_create_payment):
        """Test successful Satispay payment form creation"""
        from larpmanager.accounting.gateway import get_satispay_form

        request = self.factory.get("/test/")
        ctx = {
            "satispay_key_id": "test_key",
            "payment_currency": "EUR",
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = json.dumps({"id": "SAT123456"}).encode()
        mock_create_payment.return_value = mock_response

        get_satispay_form(request, ctx, self.invoice(), 100.0)

        assert self.invoice().cod == "SAT123456"
        assert ctx["pay_id"] == "SAT123456"
        mock_create_payment.assert_called_once()

    @patch("larpmanager.accounting.gateway.satispaython.create_payment")
    @patch("larpmanager.accounting.gateway.load_key")
    @patch("larpmanager.accounting.gateway.notify_admins")
    def test_get_satispay_form_error(self, mock_notify, mock_load_key, mock_create_payment):
        """Test Satispay payment form creation error"""
        from larpmanager.accounting.gateway import get_satispay_form

        request = self.factory.get("/test/")
        ctx = {
            "satispay_key_id": "test_key",
            "payment_currency": "EUR",
        }

        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.content = b"Error"
        mock_create_payment.return_value = mock_response

        with pytest.raises(Http404):
            get_satispay_form(request, ctx, self.invoice(), 100.0)

        mock_notify.assert_called_once()

    @patch("larpmanager.accounting.gateway.satispaython.get_payment_details")
    @patch("larpmanager.accounting.gateway.load_key")
    @patch("larpmanager.accounting.gateway.invoice_received_money")
    def test_satispay_verify_accepted(self, mock_invoice_received, mock_load_key, mock_get_payment):
        """Test Satispay payment verification when accepted"""
        from larpmanager.accounting.gateway import satispay_verify

        request = self.factory.get("/test/")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = json.dumps(
            {
                "status": "ACCEPTED",
                "amount_unit": 10000,  # 100.00 EUR in cents
            }
        ).encode()
        mock_get_payment.return_value = mock_response

        mock_invoice = Mock()
        mock_invoice.method.slug = "satispay"
        mock_invoice.status = PaymentStatus.CREATED
        mock_invoice.cod = "SAT123456"

        with patch("larpmanager.accounting.gateway.PaymentInvoice.objects.get") as mock_get_invoice:
            mock_get_invoice.return_value = mock_invoice
            with patch("larpmanager.accounting.gateway.update_payment_details") as mock_update:

                def update_ctx(request, ctx):
                    ctx["satispay_key_id"] = "test_key_id"

                mock_update.side_effect = update_ctx

                satispay_verify(request, "SAT123456")

                mock_invoice_received.assert_called_once_with("SAT123456", 100.0)

    def test_satispay_verify_not_found(self):
        """Test Satispay verification with non-existent invoice"""
        from larpmanager.accounting.gateway import satispay_verify

        request = self.factory.get("/test/")

        with patch("larpmanager.accounting.gateway.PaymentInvoice.objects.get") as mock_get_invoice:
            mock_get_invoice.side_effect = PaymentInvoice.DoesNotExist()
            with patch("larpmanager.accounting.gateway.update_payment_details"):
                # Should not raise exception, just log warning
                satispay_verify(request, "NONEXISTENT")

    def test_satispay_webhook(self):
        """Test Satispay webhook handling"""
        from larpmanager.accounting.gateway import satispay_webhook

        request = self.factory.get("/webhook/", {"payment_id": "SAT123456"})

        with patch("larpmanager.accounting.gateway.satispay_verify") as mock_verify:
            satispay_webhook(request)
            mock_verify.assert_called_once_with(request, "SAT123456")


class TestPayPalGateway(TestCase, BaseTestCase):
    """Test PayPal payment gateway functions"""

    def setup_method(self):
        self.factory = RequestFactory()

    @patch("larpmanager.accounting.gateway.PayPalPaymentsForm")
    def test_get_paypal_form(self, mock_form_class):
        """Test PayPal form creation"""
        from larpmanager.accounting.gateway import get_paypal_form

        request = self.factory.get("/test/")
        ctx = {
            "paypal_id": "test@paypal.com",
            "payment_currency": "EUR",
        }

        mock_form = Mock()
        mock_form_class.return_value = mock_form

        get_paypal_form(request, ctx, self.invoice(), 100.0)

        assert ctx["paypal_form"] == mock_form
        mock_form_class.assert_called_once()

    @patch("larpmanager.accounting.gateway.invoice_received_money")
    def test_paypal_webhook_completed(self, mock_invoice_received):
        """Test PayPal webhook for completed payment"""
        from larpmanager.accounting.gateway import paypal_webhook

        mock_ipn = Mock()
        mock_ipn.payment_status = "Completed"
        mock_ipn.invoice = "TEST123"
        mock_ipn.mc_gross = Decimal("100.00")
        mock_ipn.mc_fee = Decimal("5.00")
        mock_ipn.txn_id = "TXN456"

        result = paypal_webhook(mock_ipn)

        mock_invoice_received.assert_called_once_with("TEST123", Decimal("100.00"), Decimal("5.00"), "TXN456")

    @patch("larpmanager.accounting.gateway.notify_admins")
    def test_paypal_ko_webhook(self, mock_notify):
        """Test PayPal invalid webhook handling"""
        from larpmanager.accounting.gateway import paypal_ko_webhook

        mock_ipn = Mock()
        mock_ipn.txn_id = "INVALID_TXN"

        paypal_ko_webhook(mock_ipn)

        mock_notify.assert_called_once()


class TestStripeGateway(TestCase, BaseTestCase):
    """Test Stripe payment gateway functions"""

    def setup_method(self):
        self.factory = RequestFactory()

    @patch("larpmanager.accounting.gateway.stripe.checkout.Session.create")
    @patch("larpmanager.accounting.gateway.stripe.Price.create")
    @patch("larpmanager.accounting.gateway.stripe.Product.create")
    def test_get_stripe_form(self, mock_product, mock_price, mock_session):
        """Test Stripe checkout session creation"""
        from larpmanager.accounting.gateway import get_stripe_form

        request = self.factory.get("/test/")
        ctx = {
            "stripe_sk_api": "sk_test_123",
            "payment_currency": "EUR",
        }

        # Create real mock objects with string IDs to avoid Django aggregate function issues
        mock_product_obj = Mock()
        mock_product_obj.id = "prod_123"
        mock_product.return_value = mock_product_obj

        mock_price_obj = Mock()
        mock_price_obj.id = "price_123"
        mock_price.return_value = mock_price_obj

        mock_session.return_value = Mock(id="cs_123")

        invoice = self.invoice()
        with patch("larpmanager.accounting.gateway.stripe") as mock_stripe:
            # Set up the stripe module mock
            mock_stripe.Product.create = mock_product
            mock_stripe.Price.create = mock_price
            mock_stripe.checkout.Session.create = mock_session

            get_stripe_form(request, ctx, invoice, 100.0)

            assert invoice.cod == "price_123"
            assert ctx["stripe_ck"] is not None
            mock_product.assert_called_once()
            mock_price.assert_called_once()
            mock_session.assert_called_once()

    @patch("larpmanager.accounting.gateway.stripe.Webhook.construct_event")
    @patch("larpmanager.accounting.gateway.stripe.checkout.Session.retrieve")
    @patch("larpmanager.accounting.gateway.invoice_received_money")
    def test_stripe_webhook_completed(self, mock_invoice_received, mock_retrieve, mock_construct):
        """Test Stripe webhook for completed payment"""
        from larpmanager.accounting.gateway import stripe_webhook

        request = self.factory.post(
            "/webhook/", data=json.dumps({"type": "checkout.session.completed"}), content_type="application/json"
        )
        request.META["HTTP_STRIPE_SIGNATURE"] = "test_sig"

        mock_event = {"type": "checkout.session.completed", "data": {"object": {"id": "cs_123"}}}
        mock_construct.return_value = mock_event

        mock_session = Mock()
        mock_session.line_items = {"data": [{"price": {"id": "price_123"}}]}
        mock_retrieve.return_value = mock_session

        with patch("larpmanager.accounting.gateway.def_user_ctx") as mock_ctx:
            with patch("larpmanager.accounting.gateway.update_payment_details"):
                stripe_webhook(request)

                mock_invoice_received.assert_called_once_with("price_123")


class TestSumUpGateway(TestCase, BaseTestCase):
    """Test SumUp payment gateway functions"""

    def setup_method(self):
        self.factory = RequestFactory()

    @patch("larpmanager.accounting.gateway.requests.request")
    def test_get_sumup_form(self, mock_request):
        """Test SumUp checkout creation"""
        from larpmanager.accounting.gateway import get_sumup_form

        request = self.factory.get("/test/")
        ctx = {
            "sumup_client_id": "client_123",
            "sumup_client_secret": "secret_123",
            "sumup_merchant_id": "merchant_123",
            "payment_currency": "EUR",
        }

        # Mock token response
        token_response = Mock()
        token_response.text = json.dumps({"access_token": "token_123"})

        # Mock checkout response
        checkout_response = Mock()
        checkout_response.text = json.dumps({"id": "checkout_123"})

        mock_request.side_effect = [token_response, checkout_response]

        get_sumup_form(request, ctx, self.invoice(), 100.0)

        assert self.invoice().cod == "checkout_123"
        assert ctx["sumup_checkout_id"] == "checkout_123"
        assert mock_request.call_count == 2

    @patch("larpmanager.accounting.gateway.invoice_received_money")
    def test_sumup_webhook_successful(self, mock_invoice_received):
        """Test SumUp webhook for successful payment"""
        from larpmanager.accounting.gateway import sumup_webhook

        request_data = json.dumps({"id": "checkout_123", "status": "SUCCESSFUL"})
        request = self.factory.post("/webhook/", data=request_data, content_type="application/json")

        result = sumup_webhook(request)

        mock_invoice_received.assert_called_once_with("checkout_123")

    def test_sumup_webhook_failed(self):
        """Test SumUp webhook for failed payment"""
        from larpmanager.accounting.gateway import sumup_webhook

        request_data = json.dumps({"id": "checkout_123", "status": "FAILED"})
        request = self.factory.post("/webhook/", data=request_data, content_type="application/json")

        result = sumup_webhook(request)

        assert result is False


class TestRedsysGateway(TestCase, BaseTestCase):
    """Test Redsys payment gateway functions"""

    def setup_method(self):
        self.factory = RequestFactory()

    @patch("larpmanager.accounting.gateway.RedSysClient")
    def test_get_redsys_form(self, mock_client_class):
        """Test Redsys form creation"""
        from larpmanager.accounting.gateway import get_redsys_form

        request = self.factory.get("/test/")
        request.assoc = {"name": "Test Association"}
        ctx = {
            "redsys_merchant_code": "MERCHANT123",
            "redsys_secret_key": "SECRET123",
            "redsys_merchant_currency": "978",
            "redsys_merchant_terminal": "1",
            "redsys_sandbox": "1",
        }

        mock_client = Mock()
        mock_client.redsys_generate_request.return_value = {
            "Ds_MerchantParameters": "params",
            "Ds_Signature": "signature",
        }
        mock_client_class.return_value = mock_client

        with patch("larpmanager.accounting.gateway.redsys_invoice_cod") as mock_cod:
            mock_cod.return_value = "REDSYS123"

            get_redsys_form(request, ctx, self.invoice(), 100.0)

            assert self.invoice().cod == "REDSYS123"
            assert ctx["redsys_form"] is not None
            mock_client.redsys_generate_request.assert_called_once()

    @patch("larpmanager.accounting.gateway.RedSysClient")
    @patch("larpmanager.accounting.gateway.invoice_received_money")
    def test_redsys_webhook(self, mock_invoice_received, mock_client_class):
        """Test Redsys webhook processing"""
        from larpmanager.accounting.gateway import redsys_webhook

        request = self.factory.post(
            "/webhook/", {"Ds_MerchantParameters": "encoded_params", "Ds_Signature": "signature"}
        )

        mock_client = Mock()
        mock_client.redsys_check_response.return_value = "ORDER123"
        mock_client_class.return_value = mock_client

        with patch("larpmanager.accounting.gateway.def_user_ctx") as mock_ctx:
            mock_ctx.return_value = {"redsys_merchant_code": "MERCHANT123", "redsys_secret_key": "SECRET123"}
            with patch("larpmanager.accounting.gateway.update_payment_details"):
                result = redsys_webhook(request)

                mock_invoice_received.assert_called_once_with("ORDER123")

    def test_redsys_invoice_cod(self):
        """Test Redsys invoice code generation"""
        from larpmanager.accounting.gateway import redsys_invoice_cod

        with patch("larpmanager.accounting.gateway.generate_number") as mock_number:
            mock_number.return_value = "12345"
            with patch("larpmanager.accounting.gateway.generate_id") as mock_id:
                mock_id.return_value = "ABCDEFG"
                with patch("larpmanager.accounting.gateway.PaymentInvoice.objects.filter") as mock_filter:
                    mock_filter.return_value.exists.return_value = False

                    result = redsys_invoice_cod()
                    assert result == "12345ABCDEFG"


class TestRedSysClient(TestCase, BaseTestCase):
    """Test RedSysClient utility class"""

    def test_decode_parameters(self):
        """Test decoding merchant parameters"""
        import base64

        from larpmanager.accounting.gateway import RedSysClient

        test_data = {"test": "value"}
        encoded = base64.b64encode(json.dumps(test_data).encode()).decode()

        result = RedSysClient.decode_parameters(encoded)
        assert result == test_data

    def test_encrypt_order(self):
        """Test order encryption"""
        import base64

        from larpmanager.accounting.gateway import RedSysClient

        # Create a valid 24-byte TDES key (3DES) with different parts
        valid_key = b"12345678abcdefgh87654321"  # 24 bytes with different 8-byte parts
        client = RedSysClient("MERCHANT123", base64.b64encode(valid_key).decode())

        result = client.encrypt_order("ORDER123")
        assert isinstance(result, bytes)
        assert len(result) >= 16  # Minimum block size

    def test_sign_hmac256(self):
        """Test HMAC SHA256 signature"""
        from larpmanager.accounting.gateway import RedSysClient

        encrypted_order = b"test_encrypted_order"
        merchant_params = b"test_merchant_params"

        result = RedSysClient.sign_hmac256(encrypted_order, merchant_params)
        assert isinstance(result, bytes)

    def test_redsys_generate_request(self):
        """Test generating Redsys request"""
        import base64

        from larpmanager.accounting.gateway import RedSysClient

        # Create a valid 24-byte TDES key (3DES) with different parts
        valid_key = b"12345678abcdefgh87654321"  # 24 bytes with different 8-byte parts
        client = RedSysClient("MERCHANT123", base64.b64encode(valid_key).decode())

        params = {
            "DS_MERCHANT_AMOUNT": 100.0,
            "DS_MERCHANT_ORDER": "ORDER123",
            "DS_MERCHANT_MERCHANTCODE": "MERCHANT123",
            "DS_MERCHANT_CURRENCY": 978,
            "DS_MERCHANT_TRANSACTIONTYPE": "0",
            "DS_MERCHANT_TERMINAL": "1",
            "DS_MERCHANT_URLOK": "http://example.com/ok",
            "DS_MERCHANT_URLKO": "http://example.com/ko",
            "DS_MERCHANT_MERCHANTURL": "http://example.com/webhook",
            "DS_MERCHANT_PRODUCTDESCRIPTION": "Test Product",
            "DS_MERCHANT_TITULAR": "Test User",
            "DS_MERCHANT_MERCHANTNAME": "Test Merchant",
        }

        result = client.redsys_generate_request(params)

        assert "Ds_MerchantParameters" in result
        assert "Ds_Signature" in result
        assert "Ds_SignatureVersion" in result
        assert "Ds_Redsys_Url" in result
