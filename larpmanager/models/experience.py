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

from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils.translation import gettext_lazy as _
from tinymce.models import HTMLField

from larpmanager.models.event import BaseConceptModel
from larpmanager.models.form import WritingOption, WritingQuestion
from larpmanager.models.writing import Character


class AbilityTypePx(BaseConceptModel):
    name = models.CharField(max_length=150, blank=True)

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_ability_type_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_ability_type_without_optional",
            ),
        ]


class AbilityPx(BaseConceptModel):
    typ = models.ForeignKey(
        AbilityTypePx,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="abilities",
        verbose_name=_("Type"),
    )

    cost = models.IntegerField(default=0, help_text=_("Note that if the cost is 0, it will be automatically assigned"))

    descr = HTMLField(max_length=5000, blank=True, null=True, verbose_name=_("Description"))

    visible = models.BooleanField(
        default=True,
        help_text=_("Indicate whether the ability is visible to users, and can be freely purchased"),
    )

    prerequisites = models.ManyToManyField(
        "self",
        related_name="px_ability_unlock",
        blank=True,
        symmetrical=False,
        verbose_name=_("Pre-requisites"),
        help_text=_("Indicate the prerequisite abilities, which must be possessed before one can acquire this"),
    )

    requirements = models.ManyToManyField(
        WritingOption,
        related_name="abilities",
        blank=True,
        verbose_name=_("Requirements"),
        help_text=_("Indicate the character options, which must be selected to make the skill available"),
    )

    characters = models.ManyToManyField(Character, related_name="px_ability_list", blank=True)

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_ability_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_ability_without_optional",
            ),
        ]

    def display(self) -> str:
        """Return formatted display string with name and cost."""
        return f"{self.name} ({self.cost})"


class DeliveryPx(BaseConceptModel):
    amount = models.IntegerField()

    characters = models.ManyToManyField(Character, related_name="px_delivery_list", blank=True)

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_delivery_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_delivery_without_optional",
            ),
        ]

    def display(self) -> str:
        """Return formatted display string with name and amount."""
        return f"{self.name} ({self.amount})"


class Operation(models.TextChoices):
    ADDITION = "ADD", _("Addition")
    SUBTRACTION = "SUB", _("Subtraction")
    MULTIPLICATION = "MUL", _("Multiplication")
    DIVISION = "DIV", _("Division")


class RulePx(BaseConceptModel):
    abilities = models.ManyToManyField(
        AbilityPx,
        related_name="rules",
        blank=True,
        help_text=_(
            "The rule will be applied, only one time, if the character has any of the abilities. "
            "If no abilities are chosen, the rule is applied to all characters.",
        ),
    )

    field = models.ForeignKey(
        WritingQuestion,
        on_delete=models.CASCADE,
        help_text=_("The character field of computed type that will be updated"),
    )

    operation = models.CharField(
        max_length=3,
        choices=Operation.choices,
        default=Operation.ADDITION,
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    order = models.IntegerField(default=0)


class ModifierPx(BaseConceptModel):
    abilities = models.ManyToManyField(AbilityPx, related_name="modifiers_abilities", blank=True)

    cost = models.IntegerField(default=0, help_text=_("Note that if the cost is 0, it will be automatically assigned"))

    prerequisites = models.ManyToManyField(
        AbilityPx,
        related_name="modifiers_prerequisites",
        blank=True,
        verbose_name=_("Pre-requisites"),
        help_text=_("Indicate the prerequisite abilities"),
    )

    requirements = models.ManyToManyField(
        WritingOption,
        related_name="modifiers_requirements",
        blank=True,
        verbose_name=_("Requirements"),
        help_text=_("Indicate the required character options"),
    )

    order = models.IntegerField()

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_modifier_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_modifier_without_optional",
            ),
        ]

    def display(self) -> str:
        """Return display name with cost."""
        return f"{self.name} ({self.cost})"
