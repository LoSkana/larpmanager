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
from larpmanager.models.writing import Character, Writing


class QuestType(Writing):
    def __str__(self):
        return self.name

    def show(self):
        js = super().show()
        # ~ js['quests'] = [t.show_red() for t in self.quests.filter(hide=False)]
        return js

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]


class Quest(Writing):
    typ = models.ForeignKey(QuestType, on_delete=models.CASCADE, null=True, related_name="quests")
    open_show = models.BooleanField(default=False, help_text=_("Show all the traits to those present?"))

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

    def show(self):
        js = super().show()
        if self.typ:
            js["typ"] = self.typ.number
        # js['traits'] = [t.show() for t in self.traits.filter(hide=False)]
        js["open"] = self.open_show
        return js


class Trait(Writing):
    quest = models.ForeignKey(Quest, on_delete=models.CASCADE, null=True, related_name="traits")

    role = models.CharField(
        max_length=100,
        help_text=_("Does the character have a public role/archetype? If not, leave blank"),
        blank=True,
        null=True,
    )
    safety = models.CharField(
        max_length=500,
        help_text=_("Indicates accurate safety information"),
        blank=True,
        null=True,
    )
    traits = models.ManyToManyField("self", symmetrical=False)
    gender = models.CharField(
        max_length=1,
        choices=Character.GENDER_CHOICES,
        default=None,
        verbose_name=_("Gender"),
        help_text=_("Select the character's gender"),
        null=True,
    )
    keywords = models.CharField(
        max_length=500,
        help_text=_("Select the character's key words"),
        blank=True,
        null=True,
    )
    hide = models.BooleanField(default=False)

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

    # def show_red(self):
    # js = super().show_red()
    # try:
    # at = AssignmentTrait.objects.get(run=run, trait=self)
    # js['char'] = Registration.objects.get(run=run, member=at.member).character
    # except Exception as e:
    # pass
    # return js

    def show(self):
        js = super().show()
        for s in ["role", "gender", "keywords", "safety"]:
            self.upd_js_attr(js, s)
        if self.quest:
            js["quest"] = self.quest.id

            if self.quest.open_show:
                js["open"] = True
                js["traits"] = [t.show_red() for t in self.quest.traits.filter(hide=False)]
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
