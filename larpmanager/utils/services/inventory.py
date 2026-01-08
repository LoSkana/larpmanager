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
from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from larpmanager.cache.feature import get_event_features
from larpmanager.models.inventory import Inventory, InventoryTransfer, PoolBalanceCI, PoolTypeCI

if TYPE_CHECKING:
    from larpmanager.models.member import Member
    from larpmanager.models.writing import Character


def perform_transfer(
    actor: Member,
    pool_type: PoolTypeCI,
    amount: int,
    source: Inventory | None = None,
    target: Inventory | None = None,
    reason: str = "",
) -> None:
    """Perform a resource transfer between inventories or from/to the NPC bank.

    Args:
        actor: Member performing the transfer
        pool_type: Type of pool resource being transferred
        amount: Amount of resource to transfer
        source: Source inventory (None means NPC bank)
        target: Target inventory (None means NPC bank)
        reason: Reason for transfer

    Raises:
        ValueError: If amount is not positive or source lacks resources
    """
    if amount <= 0:
        msg = "Amount must be positive"
        raise ValueError(msg)

    with transaction.atomic():
        # Subtract from source (if not Bank)
        if source:
            balance, _ = PoolBalanceCI.objects.select_for_update().get_or_create(
                inventory=source,
                pool_type=pool_type,
                defaults={"amount": 0, "event": source.event, "number": 1},
            )
            if balance.amount < amount:
                msg = "Not enough resources"
                raise ValueError(msg)
            balance.amount -= amount
            balance.save()

        # Add to target (if not Bank)
        if target:
            balance, _ = PoolBalanceCI.objects.select_for_update().get_or_create(
                inventory=target,
                pool_type=pool_type,
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


def generate_base_inventories(instance: Character) -> None:
    """Create a personal inventory for newly created characters.

    Checks if inventory already exists to avoid duplicates.
    """
    event_features = get_event_features(instance.event_id)
    if "inventory" not in event_features:
        return

    inventory_name = f"{instance.name}'s Personal Storage"
    # Check if the character already has a personal inventory
    if Inventory.objects.filter(owners=instance, event=instance.event, name=inventory_name).exists():
        return

    inventory = Inventory.objects.create(name=inventory_name, event=instance.event)
    inventory.owners.add(instance)
    inventory.save()
