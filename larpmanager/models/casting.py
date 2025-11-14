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
from __future__ import annotations

import logging
import re
from typing import ClassVar

from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils.translation import gettext_lazy as _

from larpmanager.models.base import BaseModel
from larpmanager.models.event import Run
from larpmanager.models.member import Member
from larpmanager.models.writing import Writing

logger = logging.getLogger(__name__)


class QuestType(Writing):
    """Represents QuestType model."""

    def __str__(self) -> str:
        """Return string representation."""

        return self.name

    def show(self, run: Run | None = None) -> dict:
        """Return serialized data excluding commented quest list."""
        # Return base serialized data (commented quest list excluded)
        return super().show(run)

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["number", "event"]),
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="qtype_evt_act"),
        ]


class Quest(Writing):
    """Represents Quest model."""

    typ = models.ForeignKey(
        QuestType,
        on_delete=models.CASCADE,
        null=True,
        related_name="quests",
        verbose_name=_("Type"),
    )

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["number", "event"]),
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="quest_evt_act"),
        ]
        constraints: ClassVar[list] = [
            UniqueConstraint(fields=["event", "number", "deleted"], name="unique_quest_with_optional"),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_quest_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Text version of quest."""
        return f"Q{self.number} {self.name}"

    def show(self, run: Run | None = None) -> dict:
        """Return serialized representation with traits and type information.

        Args:
            run: Optional run instance for context

        Returns:
            Dictionary with base data, type number, and visible traits

        """
        # Get base serialized data from parent class
        js = super().show(run)

        # Add type number if type exists
        if self.typ:
            # noinspection PyUnresolvedReferences
            js["typ"] = self.typ.number

        # Serialize visible traits
        # noinspection PyUnresolvedReferences
        js["traits"] = [t.show() for t in self.traits.filter(hide=False)]

        return js


class Trait(Writing):
    """Represents Trait model."""

    quest = models.ForeignKey(Quest, on_delete=models.CASCADE, null=True, related_name="traits")

    traits = models.ManyToManyField("self", symmetrical=False, blank=True)

    class Meta:
        indexes: ClassVar[list] = [
            models.Index(fields=["number", "event"]),
            models.Index(fields=["event"], condition=Q(deleted__isnull=True), name="trait_evt_act"),
        ]
        constraints: ClassVar[list] = [
            UniqueConstraint(fields=["event", "number", "deleted"], name="unique_trait_with_optional"),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_trait_without_optional",
            ),
        ]

    def __str__(self) -> str:
        """Return formatted tier representation with number and name."""
        return f"T{self.number} {self.name}"

    def show(self, run: Run | None = None) -> dict:
        """Generate JSON representation with role, keywords, safety, and quest data."""
        js = super().show(run)

        # Add role, keywords, and safety attributes to JSON
        for s in ["role", "keywords", "safety"]:
            self.upd_js_attr(js, s)

        # Add quest ID if quest exists
        if self.quest:
            # noinspection PyUnresolvedReferences
            js["quest"] = self.quest.id

        return js


class AssignmentTrait(BaseModel):
    """Represents AssignmentTrait model."""

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

    def __str__(self) -> str:
        """Return string representation."""

        return f"{self.run} ({self.member}) {self.trait}"


class Casting(BaseModel):
    """Represents Casting model."""

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="castings", blank=True, null=True)

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="castings", blank=True, null=True)

    element = models.IntegerField()

    pref = models.IntegerField()

    typ = models.IntegerField(default=0)

    nope = models.BooleanField(default=False)

    active = models.BooleanField(default=True)

    def __str__(self) -> str:
        """Return string representation with run, member, element, preference, and rejection status."""
        return f"{self.run} ({self.member}) {self.element} {self.pref} {self.nope}"


class CastingAvoid(BaseModel):
    """Represents CastingAvoid model."""

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


def update_traits_text(instance: AssignmentTrait) -> list:
    """Extract and return trait references from instance text using pattern matching.

    Parses text content to find trait references in two formats:
    - #number: Traits to be returned in the result list
    - @number: Traits to be validated but not returned

    Args:
        instance: Model instance with event and text attributes containing trait references.
                 Must have 'event_id' and 'text' attributes.

    Returns:
        list: List of Trait objects found by parsing #number patterns in text.
              Only includes traits that exist in the database for the given event.

    Note:
        @number patterns are validated but not included in the return value.
        Invalid trait references are logged as warnings but don't raise exceptions.

    """
    # Extract all #number patterns from text and find corresponding traits
    trait_numbers_to_return = re.findall(r"#([\d]+)", instance.text, re.IGNORECASE)
    traits = []

    # Process each unique trait number found with # prefix
    for trait_number in set(trait_numbers_to_return):
        try:
            trait = Trait.objects.get(event_id=instance.event_id, number=trait_number)
            traits.append(trait)
        except Trait.DoesNotExist as error:  # noqa: PERF203 - Need per-item error handling to log warnings and continue
            logger.warning("Error getting trait %s: %s", trait_number, error)

    # Extract all @number patterns for validation (not added to return list)
    trait_numbers_to_validate = re.findall(r"@([\d]+)", instance.text, re.IGNORECASE)

    # Validate each unique trait number found with @ prefix
    for trait_number in set(trait_numbers_to_validate):
        try:
            trait = Trait.objects.get(event_id=instance.event_id, number=trait_number)
        except Trait.DoesNotExist as error:  # noqa: PERF203 - Need per-item error handling to log warnings and continue
            logger.warning("Error getting trait %s in assignment: %s", trait_number, error)

    return traits


def refresh_all_instance_traits(instance) -> None:
    """Refresh traits for an instance by updating and synchronizing with calculated traits."""
    if instance.id is None:
        return

    if instance.temp:
        return

    # Calculate updated traits for the instance
    calculated_traits = update_traits_text(instance)

    # Synchronize instance traits with calculated traits
    if hasattr(instance, "traits"):
        for existing_trait in instance.traits.all():
            if existing_trait not in calculated_traits:
                instance.traits.remove(existing_trait)
        for calculated_trait in calculated_traits:
            instance.traits.add(calculated_trait)
