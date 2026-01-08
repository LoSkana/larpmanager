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
from typing import Any, ClassVar

from django.db import models

from larpmanager.models.base import UuidMixin
from larpmanager.models.event import BaseConceptModel
from larpmanager.models.member import Member
from larpmanager.models.writing import Character


class Inventory(UuidMixin, BaseConceptModel):
    """Character inventory model for managing shared or personal resource storage."""

    name = models.CharField(max_length=150)

    owners = models.ManyToManyField(Character, related_name="inventory", blank=True)

    def get_pool_balances(self) -> list[dict[str, Any]]:
        """Return a list of dicts with PoolTypeCI and corresponding PoolBalanceCI.

        Automatically creates a PoolBalanceCI if it doesn't exist.
        """
        pool_balances = []
        for pool_type in self.event.get_elements(PoolTypeCI).order_by("number"):
            # Get or create the balance
            balance, _created = PoolBalanceCI.objects.get_or_create(
                inventory=self,
                pool_type=pool_type,
                defaults={"amount": 0, "event": self.event, "number": 1},
            )
            pool_balances.append({"type": pool_type, "balance": balance})
        return pool_balances


class PoolTypeCommon(UuidMixin, BaseConceptModel):
    """Abstract pool type that other apps can extend."""

    name = models.CharField(max_length=150)

    class Meta:
        abstract = True


class PoolTypeCI(PoolTypeCommon):
    """Pool type model for character inventory resource types."""


class PoolBalanceCommon(UuidMixin, BaseConceptModel):
    """Abstract pool balance to be subclassed by context-specific balances."""

    amount = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True


class PoolBalanceCI(PoolBalanceCommon):
    """Pool balance model for tracking resources in character inventories."""

    inventory = models.ForeignKey("Inventory", on_delete=models.CASCADE, related_name="pools")

    pool_type = models.ForeignKey(PoolTypeCI, on_delete=models.CASCADE, related_name="balances")

    class Meta(PoolBalanceCommon.Meta):
        unique_together = ("inventory", "pool_type")


class InventoryTransfer(BaseConceptModel):
    """Transfer log model for tracking inventory resource movements."""

    source_inventory = models.ForeignKey(
        "Inventory", on_delete=models.CASCADE, null=True, blank=True, related_name="outgoing_transfers"
    )

    target_inventory = models.ForeignKey(
        "Inventory", on_delete=models.CASCADE, null=True, blank=True, related_name="incoming_transfers"
    )

    pool_type = models.ForeignKey("PoolTypeCI", on_delete=models.CASCADE)

    amount = models.IntegerField()

    timestamp = models.DateTimeField(auto_now_add=True)

    actor = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True)

    reason = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-timestamp"]

    def __str__(self) -> str:
        """Return string representation of the transfer."""
        src = self.source_inventory or "Bank"
        tgt = self.target_inventory or "Bank"
        return f"{self.amount} {self.pool_type.name} {src} → {tgt}"
