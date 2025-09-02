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


class PoolTypeCI(BaseConceptModel):
    name = models.CharField(max_length=150)


class PoolBalanceCI(BaseConceptModel):
    inventory = models.ForeignKey("CharacterInventory", on_delete=models.CASCADE, related_name="pools")
    pool_type = models.ForeignKey(PoolTypeCI, on_delete=models.CASCADE, related_name="balances")
    amount = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("inventory", "pool_type")