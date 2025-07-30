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

import re

from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils.translation import gettext_lazy as _

from larpmanager.models.base import BaseModel
from larpmanager.models.event import Run
from larpmanager.models.member import Member
from larpmanager.models.writing import Writing


class QuestType(Writing):
    def __str__(self):
        return self.name

    def show(self, run=None):
        js = super().show(run)
        # ~ js['quests'] = [t.show_red() for t in self.quests.filter(hide=False)]
        return js

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]


class Quest(Writing):
    typ = models.ForeignKey(
        QuestType, on_delete=models.CASCADE, null=True, related_name="quests", verbose_name=_("Type")
    )

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
            UniqueConstraint(fields=["event", "number", "deleted"], name="unique_quest_with_optional"),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_quest_without_optional",
            ),
        ]

    def __str__(self):
        return f"Q{self.number} {self.name}"

    def show(self, run=None):
        js = super().show(run)
        if self.typ:
            # noinspection PyUnresolvedReferences
            js["typ"] = self.typ.number
        # noinspection PyUnresolvedReferences
        js["traits"] = [t.show() for t in self.traits.filter(hide=False)]
        return js


class Trait(Writing):
    quest = models.ForeignKey(Quest, on_delete=models.CASCADE, null=True, related_name="traits")

    traits = models.ManyToManyField("self", symmetrical=False, blank=True)

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
            UniqueConstraint(fields=["event", "number", "deleted"], name="unique_trait_with_optional"),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_trait_without_optional",
            ),
        ]

    def __str__(self):
        return f"T{self.number} {self.name}"

    def show(self, run=None):
        js = super().show(run)
        for s in ["role", "keywords", "safety"]:
            self.upd_js_attr(js, s)
        if self.quest:
            # noinspection PyUnresolvedReferences
            js["quest"] = self.quest.id
        return js


class AssignmentTrait(BaseModel):
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="assignments", blank=True, null=True)

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="assignments",
        blank=True,
        null=True,
    )

    trait = models.ForeignKey(
        Trait,
        on_delete=models.CASCADE,
        related_name="assignments",
        blank=True,
        null=True,
    )

    typ = models.IntegerField()

    def __str__(self):
        return f"{self.run} ({self.member}) {self.trait}"


class Casting(BaseModel):
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="castings", blank=True, null=True)

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="castings", blank=True, null=True)

    element = models.IntegerField()

    pref = models.IntegerField()

    typ = models.IntegerField(default=0)

    nope = models.BooleanField(default=False)

    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.run} ({self.member}) {self.element} {self.pref} {self.nope}"


class CastingAvoid(BaseModel):
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        related_name="casting_avoids",
        blank=True,
        null=True,
    )

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="casting_avoids",
        blank=True,
        null=True,
    )

    typ = models.IntegerField(default=0)

    text = models.TextField(max_length=5000)


def update_traits_text(instance):
    trait_search = re.findall(r"#([\d]+)", instance.text, re.IGNORECASE)
    traits = []
    for pid in set(trait_search):
        try:
            trait = Trait.objects.get(event=instance.event, number=pid)
            traits.append(trait)
        except Exception as e:
            print(e)

    trait_search = re.findall(r"@([\d]+)", instance.text, re.IGNORECASE)
    for pid in set(trait_search):
        try:
            trait = Trait.objects.get(event=instance.event, number=pid)
        except Exception as e:
            print(e)

    return traits


def update_traits_all(instance):
    if instance.id is None:
        return

    if instance.temp:
        return

    pgs = update_traits_text(instance)
    if hasattr(instance, "traits"):
        for el in instance.traits.all():
            if el not in pgs:
                instance.traits.remove(el)
        for ch in pgs:
            instance.traits.add(ch)
