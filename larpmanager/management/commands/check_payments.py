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

import logging

from django.core.management.base import BaseCommand

from larpmanager.accounting.gateway import satispay_verify
from larpmanager.models.accounting import PaymentInvoice, PaymentStatus
from larpmanager.utils.tasks import notify_admins

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Django management command for periodic payment checks.

    This command should be run regularly (every 5 minutes) to check the status
    of pending payments across different payment gateways and update them if completed.
    Currently handles Satispay payments, with room for future payment gateway checks.
    """

    help = "Check status of pending payments across all payment gateways"

    def handle(self, *args, **options):
        """Main command entry point with exception handling.

        Args:
            *args: Command arguments
            **options: Command options
        """
        try:
            self.check_satispay_payments()
            # Future payment gateway checks can be added here
        except Exception as e:
            notify_admins("Check Payments", "Error checking payments", e)
            logger.error(f"Error in check_payments command: {e}")

    def check_satispay_payments(self) -> None:
        """Check all pending Satispay payments and verify their status.

        Queries all payment invoices with Satispay method and CREATED status,
        then verifies each one with the Satispay API to update their status.
        Logs warnings for any verification failures and reports the total
        number of successfully checked payments.

        Returns:
            None: Outputs results to stdout and logs any errors.
        """
        # Query all pending Satispay payment invoices
        pending_satispay_invoices = PaymentInvoice.objects.filter(
            method__slug="satispay",
            status=PaymentStatus.CREATED,
        )

        # Early return if no pending payments found
        if not pending_satispay_invoices.exists():
            self.stdout.write("No pending Satispay payments found.")
            return

        # Initialize counter for successfully checked payments
        successfully_verified_count = 0

        # Iterate through each pending payment invoice
        for payment_invoice in pending_satispay_invoices:
            try:
                # Create mock request object for satispay_verify function
                # The function only uses request.assoc_id for logging context
                mock_request = type("MockRequest", (), {"assoc": {"id": payment_invoice.assoc_id}})()

                # Verify payment status with Satispay API
                satispay_verify(mock_request, payment_invoice.cod)
                successfully_verified_count += 1

            except Exception as verification_error:
                # Log verification failures but continue processing other payments
                logger.warning(f"Failed to verify Satispay payment {payment_invoice.cod}: {verification_error}")

        # Report successful completion with count of checked payments
        self.stdout.write(
            self.style.SUCCESS(f"Successfully checked {successfully_verified_count} pending Satispay payments.")
        )
