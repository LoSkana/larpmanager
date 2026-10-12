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

from larpmanager.cache.discount import get_discount_reservations, get_member_reservations
from larpmanager.models.accounting import AccountingItemDiscount, Discount, DiscountType
from larpmanager.models.registration import Registration

if TYPE_CHECKING:
    from larpmanager.models.event import Event, Run
    from larpmanager.models.member import Member


def get_member_discounts(member: Member, run: Run) -> list[Discount]:
    """Return the discounts confirmed on the member active registrations or reserved by the member for the run."""
    confirmed_ids = set(
        AccountingItemDiscount.objects.filter(
            registration__run=run,
            registration__member=member,
            registration__cancellation_date__isnull=True,
        ).values_list("disc_id", flat=True)
    )
    run_discount_ids = list(run.discounts.values_list("id", flat=True))
    reserved_ids = set(get_member_reservations(run.id, run_discount_ids, member.id))
    return list(Discount.objects.filter(id__in=confirmed_ids | reserved_ids))


def count_discount_redemptions(discount: Discount, run: Run, exclude_member_id: int | None = None) -> int:
    """Count confirmed redemptions plus active reservations of a discount on a run."""
    confirmed = AccountingItemDiscount.objects.filter(
        disc=discount,
        registration__run=run,
        registration__cancellation_date__isnull=True,
    ).count()
    reservations = get_discount_reservations(run.id, discount.id)
    reservations.pop(exclude_member_id, None)
    return confirmed + len(reservations)


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

    member_discounts = get_member_discounts(member, run)

    if any(member_discount.id == discount.id for member_discount in member_discounts):
        return _("Code already used")

    if any(member_discount.typ == discount.typ for member_discount in member_discounts):
        return _("Non-cumulative code")

    if discount.max_redeem > 0 and count_discount_redemptions(discount, run, member.id) >= discount.max_redeem:
        return _("This discount code has reached its limit.")

    if not _validate_exclusive_logic(discount, member, run, event, member_discounts):
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


def _validate_exclusive_logic(
    discount: Discount, member: Member, run: Run, event: Event, member_discounts: list[Discount]
) -> bool:
    """Validate exclusive discount logic for member registrations.

    Ensures that PLAYAGAIN discounts are mutually exclusive with other discounts
    and validates eligibility requirements.

    Args:
        discount: The discount to validate
        member: The member applying for the discount
        run: The specific run for this registration
        event: The event containing multiple runs
        member_discounts: Discounts already confirmed or reserved by the member for the run

    Returns:
        True if the discount can be applied, False otherwise

    """
    # For PLAYAGAIN discount: no other discounts and has another registration
    if discount.typ == DiscountType.PLAYAGAIN:
        # Check if member already has any discount for this run
        if member_discounts:
            return False

        # Verify member has an active registration in another run of the same event
        if not (
            Registration.objects.filter(member=member, run__event=event, cancellation_date__isnull=True, pending=False)
            .exclude(run=run)
            .exists()
        ):
            return False

    # If PLAYAGAIN discount was already applied, no other allowed
    elif any(member_discount.typ == DiscountType.PLAYAGAIN for member_discount in member_discounts):
        return False

    return True
