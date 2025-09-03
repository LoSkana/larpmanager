# LarpManager - https://larpmanager.com
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
from django.db import transaction

from larpmanager.models.characterinventory import PoolBalanceCI, InventoryTransfer


def perform_transfer(actor, pool_type, amount, source=None, target=None, reason=""):
    if amount <= 0:
        raise ValueError("Amount must be positive")

    with transaction.atomic():
        # Subtract from source (if not Bank)
        if source:
            balance, _ = PoolBalanceCI.objects.select_for_update().get_or_create(
                inventory=source, pool_type=pool_type,
                defaults={"amount": 0, "event": source.event, "number": 1},
            )
            if balance.amount < amount:
                raise ValueError("Not enough resources")
            balance.amount -= amount
            balance.save()

        # Add to target (if not Bank)
        if target:
            balance, _ = PoolBalanceCI.objects.select_for_update().get_or_create(
                inventory=target, pool_type=pool_type,
                defaults={"amount": 0, "event": target.event, "number": 1},
            )
            balance.amount += amount
            balance.save()

        # Record transfer
        InventoryTransfer.objects.create(
            source_inventory=source,
            target_inventory=target,
            pool_type=pool_type,
            amount=amount,
            actor=actor,
            reason=reason,
        )
