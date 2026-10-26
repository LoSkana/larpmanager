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

"""Payment gateway integrations, one module per provider (PayPal, Stripe, Sumup, Redsys, Satispay)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.html import escape

if TYPE_CHECKING:
    from django.http import HttpRequest

    from larpmanager.models.accounting import PaymentInvoice

# Payment gateways typically require amounts in smallest currency unit (cents for EUR/USD)
CURRENCY_TO_CENTS_MULTIPLIER = 100

# Payment methods kept only for the associations that still use them
LEGACY_PAYMENT_METHODS = ("paypal",)

# Payment details keys that must be set for each gateway to work
GATEWAY_REQUIRED_KEYS = {
    "paypal": ("paypal_id",),
    "paypal_v2": ("paypal_v2_client_id", "paypal_v2_secret", "paypal_v2_webhook_id"),
    "stripe": ("stripe_sk_api", "stripe_webhook_secret"),
    "sumup": ("sumup_merchant_id", "sumup_client_id", "sumup_client_secret"),
    "redsys": ("redsys_merchant_code", "redsys_merchant_terminal", "redsys_merchant_currency", "redsys_secret_key"),
    "satispay": ("satispay_key_id",),
}


class GatewayError(Exception):
    """Raised when a payment gateway cannot start a payment."""


def missing_gateway_keys(payment_method_slug: str, payment_details: dict) -> list[str]:
    """Return the required payment details keys of a gateway that are not configured."""
    return [key for key in GATEWAY_REQUIRED_KEYS.get(payment_method_slug, ()) if not payment_details.get(key)]


def payment_error_info(
    request: HttpRequest,
    payment_details: dict,
    invoice: PaymentInvoice | None,
    gateway_error: str | None,
) -> str:
    """Collect request, member, invoice and gateway details useful to debug a failed payment."""
    member = request.user.member
    lines = [
        f"Association: {request.association['slug']} ({request.association['id']})",
        f"Member: {member} - {request.user.email} ({member.id})",
        f"Path: {request.get_full_path()}",
        f"Referer: {request.META.get('HTTP_REFERER', '')}",
        f"User agent: {request.META.get('HTTP_USER_AGENT', '')}",
        f"Language: {request.META.get('HTTP_ACCEPT_LANGUAGE', '')}",
    ]

    if gateway_error:
        lines += ["", f"Gateway error: {gateway_error}"]

    if invoice:
        lines += [
            "",
            f"Invoice: {invoice.uuid} - created {invoice.created}",
            f"Status: {invoice.get_status_display()}",
            f"Method: {invoice.method.slug}",
            f"Type: {invoice.get_typ_display()}",
            f"Amount: {invoice.mc_gross}",
            f"Causal: {invoice.causal}",
            f"Cod: {invoice.cod}",
            f"Registration: {invoice.registration_id}",
        ]

    # Gateway configuration, without exposing secrets
    stripe_key = payment_details.get("stripe_sk_api") or ""
    stripe_mode = "live" if stripe_key.startswith(("sk_live", "rk_live")) else "test" if stripe_key else "missing"
    lines += [
        "",
        f"Currency: {payment_details.get('payment_currency', '')}",
        f"Stripe key: {stripe_mode}",
        f"Stripe webhook secret: {'set' if payment_details.get('stripe_webhook_secret') else 'missing'}",
        f"PayPal id: {payment_details.get('paypal_id', '')}",
        f"PayPal v2 client id: {payment_details.get('paypal_v2_client_id', '')}",
    ]
    return "<br />\n".join(escape(line) for line in lines)
