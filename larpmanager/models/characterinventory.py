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
from django.db import models

from larpmanager.models.event import BaseConceptModel
from larpmanager.models.writing import Character

class CharacterInventory(BaseConceptModel):
    name = models.CharField(max_length=150)
    owners = models.ManyToManyField(Character, related_name="character_inventory", blank=True)

    def get_pool_balances(self):
        """
        Returns a list of dicts: each with a PoolTypeCI and the corresponding PoolBalanceCI.
        Automatically creates a PoolBalanceCI if it doesn't exist.
        """
        pool_balances = []
        for pool_type in self.event.get_elements(PoolTypeCI).order_by("number"):
            # Get or create the balance
            balance, created = PoolBalanceCI.objects.get_or_create(
                inventory=self,
                pool_type=pool_type,
                defaults={"amount": 0, "event": self.event, "number": 1},
            )
            pool_balances.append({"type": pool_type, "balance": balance})
        return pool_balances


class PoolTypeCI(BaseConceptModel):
    name = models.CharField(max_length=150)


class PoolBalanceCI(BaseConceptModel):
    inventory = models.ForeignKey("CharacterInventory", on_delete=models.CASCADE, related_name="pools")
    pool_type = models.ForeignKey(PoolTypeCI, on_delete=models.CASCADE, related_name="balances")
    amount = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("inventory", "pool_type")