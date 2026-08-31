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
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _

from larpmanager.models.accounting import AccountingItemDiscount, Discount, DiscountType
from larpmanager.models.registration import Registration

if TYPE_CHECKING:
    from larpmanager.models.event import Event, Run
    from larpmanager.models.member import Member


def _check_discount(discount: Any, member: Any, run: Any, event: Any) -> Any:
    """Validate if a discount can be applied to a member's registration.

    Args:
        discount: Discount object to validate
        member: Member attempting to use discount
        run: Event run instance
        event: Event instance

    Returns:
        str or None: Error message if invalid, None if valid

    """
    if _is_discount_invalid_for_registration(discount, member, run):
        return _("Discounts only applicable with new registrations")

    if _is_discount_already_used(discount, member, run):
        return _("Code already used")

    if _is_type_already_used(discount.typ, member, run):
        return _("Non-cumulative code")

    if discount.max_redeem > 0 and _is_discount_maxed(discount, run):
        return _("This discount code has reached its limit.")

    if not _validate_exclusive_logic(discount, member, run, event):
        return _("Discount not combinable with other benefits.")

    return None


def _is_discount_invalid_for_registration(discount: Discount, member: Member, run: Run) -> bool:
    """Check if discount is invalid due to existing registration.

    Returns True if discount is registration-only and member already registered.
    """
    # Discount not limited to registration-only
    if not discount.only_reg:
        return False

    # Check if member has active registration for this run
    return Registration.objects.filter(member=member, run=run, cancellation_date__isnull=True).exists()


def _is_discount_already_used(discount: Discount, member: Member, run: Run) -> bool:
    """Check if discount has already been used by member for run."""
    return AccountingItemDiscount.objects.filter(disc=discount, member=member, run=run).exists()


def _is_type_already_used(
    discount_type: DiscountType,
    member: Member,
    run: Run,
) -> bool:
    """Check if a discount type has already been used by a member for a run."""
    return AccountingItemDiscount.objects.filter(disc__typ=discount_type, member=member, run=run).exists()


def _is_discount_maxed(discount: Discount, run: Run) -> bool:
    """Check if discount has exceeded maximum redemptions for a run."""
    redemption_count = AccountingItemDiscount.objects.filter(disc=discount, run=run).count()
    return redemption_count > discount.max_redeem


def _validate_exclusive_logic(discount: Discount, member: Member, run: Run, event: Event) -> bool:
    """Validate exclusive discount logic for member registrations.

    Ensures that PLAYAGAIN discounts are mutually exclusive with other discounts
    and validates eligibility requirements.

    Args:
        discount: The discount to validate
        member: The member applying for the discount
        run: The specific run for this registration
        event: The event containing multiple runs

    Returns:
        True if the discount can be applied, False otherwise

    """
    # For PLAYAGAIN discount: no other discounts and has another registration
    if discount.typ == DiscountType.PLAYAGAIN:
        # Check if member already has any discount for this run
        if AccountingItemDiscount.objects.filter(member=member, run=run).exists():
            return False

        # Verify member has an active registration in another run of the same event
        if not (
            Registration.objects.filter(member=member, run__event=event, cancellation_date__isnull=True, pending=False)
            .exclude(run=run)
            .exists()
        ):
            return False

    # If PLAYAGAIN discount was already applied, no other allowed
    elif AccountingItemDiscount.objects.filter(member=member, run=run, disc__typ=DiscountType.PLAYAGAIN).exists():
        return False

    return True
