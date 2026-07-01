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
from django.db.models import QuerySet

from larpmanager.models.base import BaseModel, UuidMixin
from larpmanager.models.event import BaseConceptModel
from larpmanager.models.member import Member
from larpmanager.models.writing import Character


class InventoryType(UuidMixin, BaseConceptModel):
    """Inventory type for character inventories.

    Defines which pool types are available for inventories of this type.
    When restrict_pools is False (default), all pool types are shown regardless
    of the pool_types M2M
    """

    restrict_pools = models.BooleanField(
        default=False,
        help_text="If enabled, only pool types belonging to the selected labels will appear in inventories of this type.",
    )

    labels = models.ManyToManyField(
        "PoolLabel",
        related_name="inventory_types",
        blank=True,
        help_text="Labels whose pool types are available to inventories of this type (only used when restrict_pools is enabled).",
    )

    class Meta(BaseConceptModel.Meta):
        pass


class Inventory(UuidMixin, BaseConceptModel):
    """Character inventory model for managing shared or personal resource storage."""

    name = models.CharField(max_length=150)

    owners = models.ManyToManyField(Character, related_name="inventory", blank=True)

    inventory_type = models.ForeignKey(
        InventoryType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventories",
        help_text="Optional type that controls which pool types are available. "
        "If unset, all pool types are shown (backward compatible).",
    )

    def _get_active_pool_types(self) -> QuerySet:
        """Return the queryset of pool types to show for this inventory.

        Rules:
        - No type assigned, all pool types for the event (legacy behaviour).
        - Type assigned, restrict_pools=False, all pool types (safe default).
        - Type assigned, restrict_pools=True, only the type's explicit pool_types.
        """
        all_pools = self.event.get_elements(PoolType).order_by("number")
        if self.inventory_type_id is None:
            return all_pools
        if not self.inventory_type.restrict_pools:
            return all_pools
        allowed_ids = PoolType.objects.filter(labels__in=self.inventory_type.labels.all()).values_list("id", flat=True)
        return all_pools.filter(id__in=allowed_ids)

    def get_pool_balances(self) -> list[dict[str, Any]]:
        """Return a list of dicts with PoolType and corresponding PoolBalance.

        Automatically creates a PoolBalance if it doesn't exist.
        """
        pool_balances = []
        for pool_type in self._get_active_pool_types():
            # Get or create the balance
            balance, _created = PoolBalance.objects.get_or_create(
                inventory=self,
                pool_type=pool_type,
                defaults={"amount": 0, "event": self.event, "number": 1},
            )
            pool_balances.append({"type": pool_type, "balance": balance})
        return pool_balances


class PoolLabel(UuidMixin, BaseConceptModel):
    """Label for grouping pool types within a character inventory view.

    A pool type can belong to multiple labels. Labels are event-scoped
    and used for collapsible grouping in the inventory UI.
    """

    pool_types = models.ManyToManyField(
        "PoolType",
        related_name="labels",
        blank=True,
        help_text="Pool types that belong to this label.",
    )

    class Meta(BaseConceptModel.Meta):
        pass


class PoolTypeCommon(UuidMixin, BaseConceptModel):
    """Abstract pool type that other apps can extend."""

    name = models.CharField(max_length=150)

    class Meta:
        abstract = True


class PoolType(PoolTypeCommon):
    """Pool type model for character inventory resource types."""


class PoolBalanceCommon(UuidMixin, BaseConceptModel):
    """Abstract pool balance to be subclassed by context-specific balances."""

    amount = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True


class PoolBalance(PoolBalanceCommon):
    """Pool balance model for tracking resources in character inventories."""

    inventory = models.ForeignKey("Inventory", on_delete=models.CASCADE, related_name="pools")

    pool_type = models.ForeignKey(PoolType, on_delete=models.CASCADE, related_name="balances")

    class Meta(PoolBalanceCommon.Meta):
        unique_together = ("inventory", "pool_type")


class InventoryTransfer(BaseModel):
    """Transfer log model for tracking inventory resource movements."""

    source_inventory = models.ForeignKey(
        "Inventory", on_delete=models.CASCADE, null=True, blank=True, related_name="outgoing_transfers"
    )

    target_inventory = models.ForeignKey(
        "Inventory", on_delete=models.CASCADE, null=True, blank=True, related_name="incoming_transfers"
    )

    pool_type = models.ForeignKey("PoolType", on_delete=models.CASCADE)

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
        return f"{self.amount} {self.pool_type.name} {src} -> {tgt}"
