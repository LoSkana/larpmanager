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

"""Tests for the PayPal Orders v2 gateway and the gateway configuration check"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import RequestFactory
from django.urls import reverse

from larpmanager.accounting.gateway import GatewayError, missing_gateway_keys
from larpmanager.accounting.gateway.paypal_v2 import (
    PaypalV2AlreadyPaidError,
    PaypalV2CaptureRejectedError,
    get_paypal_v2_cancel_error,
    get_paypal_v2_form,
    is_paypal_v2_pending,
    paypal_v2_amount,
    paypal_v2_capture,
    paypal_v2_redirect_url,
    paypal_v2_webhook,
    set_paypal_v2_pending,
)
from larpmanager.accounting.payment import _prepare_gateway_form, get_payment_form
from larpmanager.forms.accounting import ExePaymentSettingsForm
from larpmanager.mail.accounting import notify_gateway_not_configured
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.models.base import PaymentMethod
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.views.user.accounting import _get_cancelled_invoice, accounting_paypal_go

PAYPAL_MODULE = "larpmanager.accounting.gateway.paypal_v2"


def _response(status_code: int, data: dict | None = None) -> MagicMock:
    """Build a fake requests response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = data or {}
    response.text = json.dumps(data or {})
    return response


def _token_response() -> MagicMock:
    """Build a fake OAuth token response."""
    return _response(200, {"access_token": "token", "expires_in": 32400})


def _capture(status: str = "COMPLETED", value: str = "100.00", currency: str = "EUR") -> dict:
    """Build a PayPal capture resource."""
    return {
        "id": "CAPTURE1",
        "status": status,
        "invoice_id": "PAYPALV2COD",
        "amount": {"currency_code": currency, "value": value},
        "seller_receivable_breakdown": {"paypal_fee": {"currency_code": currency, "value": "3.75"}},
    }


def _method(slug: str) -> PaymentMethod:
    """Return the payment method with the given slug, creating it if missing."""
    method, _created = PaymentMethod.objects.get_or_create(slug=slug, defaults={"name": slug})
    return method


def _order(capture: dict) -> dict:
    """Build a PayPal order containing a capture."""
    return {"id": "ORDER1", "status": "COMPLETED", "purchase_units": [{"payments": {"captures": [capture]}}]}


class TestPaypalV2(BaseTestCase):
    """Test the PayPal Orders v2 gateway"""

    def setUp(self) -> None:
        """Prepare a paypal_v2 invoice and its payment configuration"""
        super().setUp()
        cache.clear()
        self.invoice = self.payment_invoice(
            method=_method("paypal_v2"), cod="PAYPALV2COD", txn_id="ORDER1", mc_fee=Decimal(0), key="REG_1"
        )
        self.invoice.save()
        self.context = {
            "association_id": self.invoice.association_id,
            "payment_currency": "EUR",
            "paypal_v2_client_id": "client",
            "paypal_v2_secret": "secret",
            "paypal_v2_webhook_id": "webhook",
        }

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_form_creates_order(self, mock_post: Any, mock_request: Any) -> None:
        """Test order creation stores the order id and the approval url"""
        mock_post.return_value = _token_response()
        mock_request.return_value = _response(
            200,
            {"id": "ORDER2", "links": [{"rel": "payer-action", "href": "https://paypal.test/approve"}]},
        )
        request = RequestFactory().get("/")

        get_paypal_v2_form(request, self.context, self.invoice, Decimal(100))

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.txn_id, "ORDER2")
        self.assertEqual(self.context["paypal_url"], reverse("accounting_paypal_go", args=[self.invoice.uuid]))
        self.assertEqual(paypal_v2_redirect_url(self.invoice.uuid), "https://paypal.test/approve")
        payload = mock_request.call_args.kwargs["json"]
        self.assertRegex(payload["purchase_units"][0]["invoice_id"], r"^PAYPALV2COD-[0-9a-f]{8}$")
        self.assertEqual(payload["purchase_units"][0]["custom_id"], str(self.invoice.uuid))
        self.assertEqual(payload["purchase_units"][0]["amount"], {"currency_code": "EUR", "value": "100.00"})

    def test_amount_currency_decimals(self) -> None:
        """Test amounts use the decimals PayPal requires for the currency"""
        self.assertEqual(paypal_v2_amount(Decimal("100.5"), "EUR"), "100.50")
        self.assertEqual(paypal_v2_amount(Decimal(5000), "JPY"), "5000")

    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_form_auth_failure_raises(self, mock_post: Any) -> None:
        """Test invalid credentials raise a gateway error"""
        mock_post.return_value = _response(401, {"error": "invalid_client"})

        with self.assertRaises(GatewayError):
            get_paypal_v2_form(RequestFactory().get("/"), self.context, self.invoice, Decimal(100))

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_capture_completed(self, mock_post: Any, mock_request: Any) -> None:
        """Test a completed capture marks the invoice as checked"""
        mock_post.return_value = _token_response()
        mock_request.return_value = _response(201, _order(_capture()))

        status = paypal_v2_capture(self.context, self.invoice)

        self.assertEqual(status, "COMPLETED")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CHECKED)
        self.assertEqual(self.invoice.txn_id, "CAPTURE1")
        self.assertEqual(self.invoice.mc_fee, Decimal("3.75"))

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_capture_returned_order(self, mock_post: Any, mock_request: Any) -> None:
        """Test the order returned by PayPal is captured when it belongs to the invoice"""
        mock_post.return_value = _token_response()
        order = {"id": "ORDER0", "purchase_units": [{"custom_id": str(self.invoice.uuid)}]}
        mock_request.side_effect = [_response(200, order), _response(201, _order(_capture()))]

        status = paypal_v2_capture(self.context, self.invoice, "ORDER0")

        self.assertEqual(status, "COMPLETED")
        self.assertIn("/v2/checkout/orders/ORDER0/capture", mock_request.call_args.args[1])

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_capture_foreign_order(self, mock_post: Any, mock_request: Any) -> None:
        """Test an order created for another invoice is not captured"""
        mock_post.return_value = _token_response()
        mock_request.return_value = _response(200, {"id": "ORDER9", "purchase_units": [{"custom_id": "other"}]})

        with self.assertRaises(GatewayError):
            paypal_v2_capture(self.context, self.invoice, "ORDER9")

        mock_request.assert_called_once()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CREATED)

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_capture_currency_mismatch(self, mock_post: Any, mock_request: Any) -> None:
        """Test a capture in a different currency is rejected"""
        mock_post.return_value = _token_response()
        mock_request.return_value = _response(201, _order(_capture(currency="USD")))

        with self.assertRaises(PaypalV2CaptureRejectedError):
            paypal_v2_capture(self.context, self.invoice)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CREATED)

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_capture_underpaid(self, mock_post: Any, mock_request: Any) -> None:
        """Test a capture lower than the invoice amount is rejected"""
        mock_post.return_value = _token_response()
        mock_request.return_value = _response(201, _order(_capture(value="10.00")))

        with self.assertRaises(PaypalV2CaptureRejectedError):
            paypal_v2_capture(self.context, self.invoice)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CREATED)

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_capture_already_captured(self, mock_post: Any, mock_request: Any) -> None:
        """Test an already captured order is read back and registered"""
        mock_post.return_value = _token_response()
        already_captured = _response(422, {"details": [{"issue": "ORDER_ALREADY_CAPTURED"}]})
        mock_request.side_effect = [already_captured, _response(200, _order(_capture()))]

        status = paypal_v2_capture(self.context, self.invoice)

        self.assertEqual(status, "COMPLETED")
        self.assertEqual(mock_request.call_args.args[0], "GET")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CHECKED)

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_capture_pending(self, mock_post: Any, mock_request: Any) -> None:
        """Test a pending capture leaves the invoice to be confirmed by the webhook"""
        mock_post.return_value = _token_response()
        mock_request.return_value = _response(201, _order(_capture(status="PENDING")))

        status = paypal_v2_capture(self.context, self.invoice)

        self.assertEqual(status, "PENDING")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CREATED)
        self.assertTrue(is_paypal_v2_pending(self.invoice))

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_capture_completed_releases_pending(self, mock_post: Any, mock_request: Any) -> None:
        """Test a previously pending capture that settles on return lets the invoice key be paid again"""
        mock_post.return_value = _token_response()
        mock_request.return_value = _response(201, _order(_capture()))
        set_paypal_v2_pending(self.invoice)

        paypal_v2_capture(self.context, self.invoice)

        self.assertFalse(is_paypal_v2_pending(self.invoice))

    def test_redirect_url_missing(self) -> None:
        """Test no approval url is returned for an invoice without a PayPal order"""
        self.assertIsNone(paypal_v2_redirect_url(self.invoice.uuid))

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_cancel_error_quick_return_after_redirect(self, mock_post: Any, mock_request: Any) -> None:
        """Test a return right after the redirect to PayPal is reported as a gateway error"""
        mock_post.return_value = _token_response()
        created = (datetime.now(UTC) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        mock_request.return_value = _response(200, {"id": "ORDER1", "status": "CREATED", "create_time": created})
        cache.set(f"paypal_v2_approve_{self.invoice.uuid}", "https://paypal.test/approve")
        paypal_v2_redirect_url(self.invoice.uuid)

        error = get_paypal_v2_cancel_error(self.context, self.invoice)

        self.assertIn("after redirect", error)

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_cancel_by_user(self, mock_post: Any, mock_request: Any) -> None:
        """Test a return long after the order creation, without a recorded redirect, is a user cancellation"""
        mock_post.return_value = _token_response()
        created = (datetime.now(UTC) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        mock_request.return_value = _response(200, {"id": "ORDER1", "status": "CREATED", "create_time": created})

        self.assertIsNone(get_paypal_v2_cancel_error(self.context, self.invoice))

    @patch("larpmanager.accounting.payment.get_stripe_form")
    def test_payment_blocked_while_capture_pending(self, mock_form: Any) -> None:
        """Test a pending capture blocks any payment method on the same invoice key"""
        set_paypal_v2_pending(self.invoice)
        stripe_invoice = PaymentInvoice.objects.create(
            member_id=self.invoice.member_id,
            association_id=self.invoice.association_id,
            method=_method("stripe"),
            typ=self.invoice.typ,
            cod="STRIPECOD",
            key="REG_1",
        )
        context = {"stripe_sk_api": "sk", "stripe_webhook_secret": "whsec"}

        _prepare_gateway_form(MagicMock(), context, stripe_invoice, Decimal(100), "stripe", require_receipt=False)

        self.assertTrue(context["payment_pending"])
        mock_form.assert_not_called()

    def test_pending_flag_expires(self) -> None:
        """Test a pending capture flag expires after the timeout"""
        with patch(f"{PAYPAL_MODULE}.cache") as mock_cache:
            set_paypal_v2_pending(self.invoice)

        self.assertEqual(mock_cache.set.call_args.kwargs["timeout"], int(timedelta(days=7).total_seconds()))

    def test_pending_flag_long_key(self) -> None:
        """Test a pending capture can be flagged on an arbitrarily long invoice key"""
        self.invoice.key = "k" * 500

        set_paypal_v2_pending(self.invoice)

        self.assertTrue(is_paypal_v2_pending(self.invoice))

    def _webhook_request(self, event_type: str = "PAYMENT.CAPTURE.COMPLETED", capture: dict | None = None) -> Any:
        """Build a PayPal webhook request for a capture event."""
        event = {"event_type": event_type, "resource": {"custom_id": str(self.invoice.uuid), **(capture or _capture())}}
        return RequestFactory().post(
            "/accounting/webhook/paypal",
            data=json.dumps(event),
            content_type="application/json",
            HTTP_PAYPAL_TRANSMISSION_ID="transmission",
            HTTP_PAYPAL_TRANSMISSION_SIG="signature",
            HTTP_PAYPAL_CERT_URL="https://api.paypal.com/v1/notifications/certs/CERT-1",
        )

    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_webhook_missing_signature_headers(self, mock_post: Any, mock_context: Any, _mock_update: Any) -> None:
        """Test a webhook without the PayPal signature headers is rejected without calling PayPal"""
        mock_context.return_value = self.context
        request = RequestFactory().post("/accounting/webhook/paypal", data="{}", content_type="application/json")

        self.assertFalse(paypal_v2_webhook(request))
        mock_post.assert_not_called()

    @patch(f"{PAYPAL_MODULE}.notify_admins")
    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_webhook_invalid_signature(
        self, mock_post: Any, mock_context: Any, _mock_update: Any, mock_notify: Any
    ) -> None:
        """Test a webhook with an invalid signature is ignored and reported to admins once a day"""
        mock_context.return_value = self.context
        mock_post.side_effect = [
            _token_response(),
            _response(200, {"verification_status": "FAILURE"}),
            _response(200, {"verification_status": "FAILURE"}),
        ]

        self.assertFalse(paypal_v2_webhook(self._webhook_request()))
        self.assertFalse(paypal_v2_webhook(self._webhook_request()))

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CREATED)
        mock_notify.assert_called_once()

    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_webhook_other_event(self, mock_post: Any, mock_context: Any, _mock_update: Any) -> None:
        """Test a verified webhook of another event type is acknowledged without changes"""
        mock_context.return_value = self.context
        mock_post.side_effect = [_token_response(), _response(200, {"verification_status": "SUCCESS"})]

        self.assertTrue(paypal_v2_webhook(self._webhook_request("PAYMENT.CAPTURE.REFUNDED")))

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CREATED)

    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_webhook_missing_credentials(self, mock_post: Any, mock_context: Any, _mock_update: Any) -> None:
        """Test a webhook is rejected without calling PayPal when the credentials are incomplete"""
        del self.context["paypal_v2_secret"]
        mock_context.return_value = self.context

        self.assertFalse(paypal_v2_webhook(self._webhook_request()))
        mock_post.assert_not_called()

    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    def test_webhook_invalid_encoding(self, mock_context: Any, _mock_update: Any) -> None:
        """Test a webhook body that is not utf-8 is rejected"""
        mock_context.return_value = self.context
        request = RequestFactory().post(
            "/accounting/webhook/paypal",
            data=b"\xff\xfe",
            content_type="application/json",
            HTTP_PAYPAL_TRANSMISSION_ID="transmission",
            HTTP_PAYPAL_TRANSMISSION_SIG="signature",
        )

        self.assertFalse(paypal_v2_webhook(request))

    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_webhook_completed(self, mock_post: Any, mock_context: Any, _mock_update: Any) -> None:
        """Test a verified capture webhook marks the invoice as checked and releases its pending flag"""
        mock_context.return_value = self.context
        mock_post.side_effect = [_token_response(), _response(200, {"verification_status": "SUCCESS"})]
        set_paypal_v2_pending(self.invoice)

        self.assertTrue(paypal_v2_webhook(self._webhook_request()))

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CHECKED)
        self.assertFalse(is_paypal_v2_pending(self.invoice))
        verify_body = json.loads(mock_post.call_args.kwargs["data"])
        self.assertEqual(verify_body["webhook_id"], "webhook")
        self.assertEqual(verify_body["webhook_event"]["resource"]["id"], "CAPTURE1")

    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_webhook_denied_releases_pending(self, mock_post: Any, mock_context: Any, _mock_update: Any) -> None:
        """Test a denied capture webhook lets the invoice key be paid again"""
        mock_context.return_value = self.context
        mock_post.side_effect = [_token_response(), _response(200, {"verification_status": "SUCCESS"})]
        set_paypal_v2_pending(self.invoice)

        self.assertTrue(paypal_v2_webhook(self._webhook_request("PAYMENT.CAPTURE.DENIED", _capture(status="DECLINED"))))

        self.assertFalse(is_paypal_v2_pending(self.invoice))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CREATED)

    @patch(f"{PAYPAL_MODULE}.notify_admins")
    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_webhook_invoice_not_found(
        self, mock_post: Any, mock_context: Any, _mock_update: Any, mock_notify: Any
    ) -> None:
        """Test a capture of an unknown invoice is acknowledged and reported to admins"""
        mock_context.return_value = self.context
        mock_post.side_effect = [_token_response(), _response(200, {"verification_status": "SUCCESS"})]
        capture = {**_capture(), "custom_id": "UNKNOWNUUID"}

        self.assertTrue(paypal_v2_webhook(self._webhook_request(capture=capture)))

        mock_notify.assert_called_once()
        self.assertIn("CAPTURE1", mock_notify.call_args.args[0])
        self.assertIn("UNKNOWNUUID", mock_notify.call_args.args[1])

    @patch(f"{PAYPAL_MODULE}.notify_admins")
    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_webhook_rejected_capture(
        self, mock_post: Any, mock_context: Any, _mock_update: Any, mock_notify: Any
    ) -> None:
        """Test a capture in another currency is acknowledged and reported, so PayPal does not retry it"""
        mock_context.return_value = self.context
        mock_post.side_effect = [_token_response(), _response(200, {"verification_status": "SUCCESS"})]

        self.assertTrue(paypal_v2_webhook(self._webhook_request(capture=_capture(currency="USD"))))

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CREATED)
        mock_notify.assert_called_once()

    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_webhook_foreign_cert_url(self, mock_post: Any, mock_context: Any, _mock_update: Any) -> None:
        """Test a webhook with a certificate url outside PayPal is rejected without calling PayPal"""
        mock_context.return_value = self.context
        request = self._webhook_request()
        request.META["HTTP_PAYPAL_CERT_URL"] = "https://paypal.com.evil.example/cert"

        self.assertFalse(paypal_v2_webhook(request))
        mock_post.assert_not_called()

    @patch(f"{PAYPAL_MODULE}.notify_admins")
    @patch(f"{PAYPAL_MODULE}.update_payment_details")
    @patch(f"{PAYPAL_MODULE}.get_context")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_webhook_capture_without_custom_id(
        self, mock_post: Any, mock_context: Any, _mock_update: Any, mock_notify: Any
    ) -> None:
        """Test a capture without custom id, from another integration, is ignored without notifying admins"""
        mock_context.return_value = self.context
        mock_post.side_effect = [_token_response(), _response(200, {"verification_status": "SUCCESS"})]
        capture = {**_capture(), "custom_id": ""}

        self.assertTrue(paypal_v2_webhook(self._webhook_request(capture=capture)))

        mock_notify.assert_not_called()

    @patch(f"{PAYPAL_MODULE}.requests.request")
    @patch(f"{PAYPAL_MODULE}.requests.post")
    def test_capture_skipped_when_key_already_paid(self, mock_post: Any, mock_request: Any) -> None:
        """Test an approved order is not captured when the invoice key was paid with another invoice"""
        PaymentInvoice.objects.create(
            member_id=self.invoice.member_id,
            association_id=self.invoice.association_id,
            method=_method("wire"),
            typ=self.invoice.typ,
            cod="WIRECOD",
            key=self.invoice.key,
            status=PaymentStatus.CHECKED,
        )

        with self.assertRaises(PaypalV2AlreadyPaidError):
            paypal_v2_capture(self.context, self.invoice)

        mock_post.assert_not_called()
        mock_request.assert_not_called()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PaymentStatus.CREATED)

    def test_go_blocked_while_capture_pending(self) -> None:
        """Test the redirect to PayPal is refused while a capture of the invoice key is pending"""
        set_paypal_v2_pending(self.invoice)
        request = RequestFactory().get("/")
        request.user = self.invoice.member.user
        request.association = {"id": self.invoice.association_id}
        request._messages = MagicMock()

        response = accounting_paypal_go(request, self.invoice.uuid)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounting"))


class TestGatewayConfiguration(BaseTestCase):
    """Test the check of gateways enabled without their credentials"""

    def test_missing_gateway_keys(self) -> None:
        """Test missing and empty keys are reported, manual methods need none"""
        self.assertEqual(
            missing_gateway_keys("stripe", {"stripe_sk_api": "sk", "stripe_webhook_secret": ""}),
            ["stripe_webhook_secret"],
        )
        self.assertEqual(
            missing_gateway_keys("paypal_v2", {"paypal_v2_client_id": "id"}),
            ["paypal_v2_secret", "paypal_v2_webhook_id"],
        )
        self.assertEqual(missing_gateway_keys("wire", {}), [])

    @patch("larpmanager.accounting.payment.notify_gateway_not_configured", return_value=False)
    @patch("larpmanager.accounting.payment.payment_error_info", return_value="info")
    @patch("larpmanager.accounting.payment.notify_admins")
    def test_unconfigured_gateway_notifies_admins_once(
        self, mock_notify: Any, _mock_info: Any, _mock_notify_exe: Any
    ) -> None:
        """Test admins are not notified again of a gateway already reported today"""
        invoice = self.payment_invoice(method=_method("stripe"))
        request = MagicMock()
        request.association = {"slug": "test", "id": invoice.association_id}
        context = {"stripe_sk_api": "sk"}

        _prepare_gateway_form(request, context, invoice, Decimal(100), "stripe", require_receipt=False)

        self.assertTrue(context["gateway_error"])
        mock_notify.assert_not_called()

    @patch("larpmanager.accounting.payment.notify_gateway_not_configured")
    @patch("larpmanager.accounting.payment.get_stripe_form")
    @patch("larpmanager.accounting.payment.payment_error_info", return_value="info")
    @patch("larpmanager.accounting.payment.notify_admins")
    def test_unconfigured_gateway_notifies_admins(
        self, mock_notify: Any, _mock_info: Any, mock_form: Any, mock_notify_exe: Any
    ) -> None:
        """Test a gateway without credentials notifies admins instead of failing"""
        invoice = self.payment_invoice(method=_method("stripe"))
        request = MagicMock()
        request.association = {"slug": "test", "id": invoice.association_id}
        context = {"stripe_sk_api": "sk"}

        _prepare_gateway_form(request, context, invoice, Decimal(100), "stripe", require_receipt=False)

        self.assertTrue(context["gateway_error"])
        mock_form.assert_not_called()
        mock_notify.assert_called_once()
        self.assertIn("stripe", mock_notify.call_args.args[0])
        mock_notify_exe.assert_called_once_with(invoice, ["stripe_webhook_secret"])

    @patch("larpmanager.mail.accounting.my_send_mail")
    @patch("larpmanager.mail.accounting.get_association_executives")
    def test_unconfigured_gateway_notifies_executives_once(self, mock_executives: Any, mock_send: Any) -> None:
        """Test executives are told which settings are missing, at most once a day."""
        cache.clear()
        executive = self.get_member()
        mock_executives.return_value = [executive]
        invoice = self.payment_invoice(method=_method("paypal_v2"))

        notify_gateway_not_configured(invoice, ["paypal_v2_secret", "paypal_v2_webhook_id"])
        notify_gateway_not_configured(invoice, ["paypal_v2_secret", "paypal_v2_webhook_id"])

        mock_send.assert_called_once()
        subject, body, recipient = mock_send.call_args.args[:3]
        self.assertIn("Payment method not configured", str(subject))
        self.assertIn("secret, webhook_id", str(body))
        self.assertEqual(recipient, executive)

    @patch("larpmanager.accounting.payment.get_paypal_v2_form", side_effect=GatewayError("invalid_client"))
    @patch("larpmanager.accounting.payment.payment_error_info", return_value="info")
    @patch("larpmanager.accounting.payment.notify_admins")
    def test_gateway_error_notifies_admins(self, mock_notify: Any, mock_info: Any, _mock_form: Any) -> None:
        """Test a gateway refusing the payment notifies admins instead of failing"""
        invoice = self.payment_invoice(method=_method("paypal_v2"))
        request = MagicMock()
        request.association = {"slug": "test", "id": invoice.association_id}
        context = {"paypal_v2_client_id": "id", "paypal_v2_secret": "secret", "paypal_v2_webhook_id": "webhook"}

        _prepare_gateway_form(request, context, invoice, Decimal(100), "paypal_v2", require_receipt=False)

        self.assertTrue(context["gateway_error"])
        mock_notify.assert_called_once()
        self.assertEqual(mock_info.call_args.args[3], "invalid_client")


class TestPaymentSettingsLegacyMethods(BaseTestCase):
    """Test legacy payment methods are offered only to associations already using them"""

    def _offered_slugs(self, association: Any) -> set[str]:
        """Return the slugs of the payment methods offered by the settings form."""
        form = ExePaymentSettingsForm(instance=association, context={"association_id": association.id})
        return set(form.fields["payment_methods"].queryset.values_list("slug", flat=True))

    def test_legacy_paypal_hidden_when_not_enabled(self) -> None:
        """Test legacy PayPal is not offered to associations without it"""
        association = self.get_association()
        _method("paypal")
        _method("paypal_v2")
        association.payment_methods.remove(*association.payment_methods.filter(slug="paypal"))

        offered = self._offered_slugs(association)

        self.assertNotIn("paypal", offered)
        self.assertIn("paypal_v2", offered)

    def test_legacy_paypal_offered_when_enabled(self) -> None:
        """Test legacy PayPal stays offered to associations that have it enabled"""
        association = self.get_association()
        association.payment_methods.add(_method("paypal"))

        self.assertIn("paypal", self._offered_slugs(association))


@patch("larpmanager.accounting.payment._prepare_gateway_form")
@patch("larpmanager.accounting.payment.get_association_config", return_value=False)
@patch("larpmanager.accounting.payment.update_invoice_gross_fee", return_value=Decimal(100))
@patch("larpmanager.accounting.payment.set_data_invoice")
@patch("larpmanager.accounting.payment.update_payment_details")
class TestInvoiceReuse(BaseTestCase):
    """Test invoices are reused by key only for the same payment method"""

    def _payment_invoice(self, method_slug: str) -> Any:
        """Run the payment form for the method and return the invoice it prepared."""
        member = self.get_member()
        form = MagicMock()
        form.cleaned_data = {"amount": Decimal(100), "method": method_slug}
        context = {"association_id": self.get_association().id, "member": member}
        get_payment_form(MagicMock(), form, "r", context, "REG_1")
        return context["invoice"]

    def test_same_method_reuses_invoice(self, *_mocks: Any) -> None:
        """Test a retry with the same method maps to the same invoice"""
        invoice = self.payment_invoice(method=_method("paypal_v2"), key="REG_1")
        invoice.save()

        self.assertEqual(self._payment_invoice("paypal_v2").pk, invoice.pk)

    def test_other_method_gets_new_invoice(self, *_mocks: Any) -> None:
        """Test switching method does not take over the invoice of the previous method"""
        invoice = self.payment_invoice(method=_method("paypal_v2"), key="REG_1")
        invoice.save()
        _method("stripe")

        new_invoice = self._payment_invoice("stripe")

        self.assertNotEqual(new_invoice.pk, invoice.pk)
        invoice.refresh_from_db()
        self.assertEqual(invoice.method.slug, "paypal_v2")


class TestCancelledInvoice(BaseTestCase):
    """Test the invoice inspected on a cancelled payment"""

    def _request(self, query: str = "") -> Any:
        """Build a cancelled payment request of the test member."""
        request = RequestFactory().get(f"/accounting/cancelled/{query}")
        request.user = self.get_member().user
        request.association = {"id": self.get_association().id}
        return request

    def test_invoice_from_url(self) -> None:
        """Test the invoice named in the url is returned"""
        invoice = self.payment_invoice(method=_method("stripe"))
        invoice.save()

        self.assertEqual(_get_cancelled_invoice(self._request(f"?invoice={invoice.uuid}")), invoice)

    def test_no_invoice_without_url(self) -> None:
        """Test no pending invoice is guessed when the url does not name one"""
        self.payment_invoice(method=_method("stripe")).save()

        self.assertIsNone(_get_cancelled_invoice(self._request()))
