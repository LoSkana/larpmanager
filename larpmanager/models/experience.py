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
from decimal import Decimal

from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils.translation import gettext_lazy as _
from tinymce.models import HTMLField

from larpmanager.cache.config import save_all_element_configs
from larpmanager.models.event import BaseConceptModel
from larpmanager.models.form import QuestionType, WritingAnswer, WritingOption, WritingQuestion
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

class AbilityTemplatePx(BaseConceptModel):

    name = models.CharField(max_length=150)
    descr = HTMLField(max_length=5000, blank=True, null=True, verbose_name=_("Description"))

    rank = models.PositiveIntegerField(default=1, verbose_name=_("Rank"))

    def __str__(self):
        if self.rank > 1:
            return f"{self.name} {self.rank}"
        return self.name

    def get_full_name(self):
        return self.name


class AbilityPx(BaseConceptModel):
    typ = models.ForeignKey(
        AbilityTypePx, on_delete=models.CASCADE, blank=True, null=True, related_name="abilities", verbose_name=_("Type")
    )

    cost = models.IntegerField()

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

    dependents = models.ManyToManyField(
        WritingOption,
        related_name="abilities",
        blank=True,
        verbose_name=_("Options required"),
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

    def display(self):
        return f"{name} ({self.cost})"

    def get_description(self):
        return self.template.descr if self.template_id else self.descr


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

    def display(self):
        return f"{self.name} ({self.amount})"


def update_px(char):
    start = char.event.get_config("px_start", 0)

    addit = {
        "px_tot": int(start) + sum(char.px_delivery_list.values_list("amount", flat=True)),
        "px_used": sum(char.px_ability_list.values_list("cost", flat=True)),
    }
    addit["px_avail"] = addit["px_tot"] - addit["px_used"]

    save_all_element_configs(char, addit)

    # save computed field
    event = char.event
    computed_ques = event.get_elements(WritingQuestion).filter(typ=QuestionType.COMPUTED)
    values = {question.id: Decimal(0) for question in computed_ques}

    # apply rules
    ability_ids = char.px_ability_list.values_list("pk", flat=True)
    rules = (
        event.get_elements(RulePx)
        .filter(Q(abilities__isnull=True) | Q(abilities__in=ability_ids))
        .distinct()
        .order_by("order")
    )

    ops = {
        Operation.ADDITION: lambda x, y: x + y,
        Operation.SUBTRACTION: lambda x, y: x - y,
        Operation.MULTIPLICATION: lambda x, y: x * y,
        Operation.DIVISION: lambda x, y: x / y if y != 0 else x,
    }

    for rule in rules:
        f_id = rule.field.id
        values[f_id] = ops.get(rule.operation, lambda x, y: x)(values[f_id], rule.amount)

    for question_id, value in values.items():
        (qa, created) = WritingAnswer.objects.get_or_create(question_id=question_id, element_id=char.id)
        qa.text = format(value, "f").rstrip("0").rstrip(".")
        qa.save()


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
            "If no abilities are chosen, the rule is applied to all characters."
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
