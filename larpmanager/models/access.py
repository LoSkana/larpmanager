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

from larpmanager.models.association import Association
from larpmanager.models.base import AlphanumericValidator, BaseModel, Feature
from larpmanager.models.event import BaseConceptModel
from larpmanager.models.member import Member


class AssocPermission(BaseModel):
    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], blank=True)

    number = models.IntegerField(blank=True)

    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="assoc_permissions")

    descr = models.CharField(max_length=1000)

    hidden = models.BooleanField(default=False)

    config = models.TextField(max_length=100, blank=True, null=True)

    def module(self):
        # noinspection PyUnresolvedReferences
        return self.feature.module

    def __str__(self):
        return self.name


class AssocRole(BaseModel):
    name = models.CharField(max_length=100)

    assoc = models.ForeignKey(Association, on_delete=models.CASCADE, related_name="roles", null=True)

    number = models.IntegerField()

    members = models.ManyToManyField(Member, related_name="assoc_roles")

    permissions = models.ManyToManyField(AssocPermission, related_name="assoc_roles", blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["assoc", "number", "deleted"],
                name="unique_assoc_role_with_optional",
            ),
            UniqueConstraint(
                fields=["assoc", "number"],
                condition=Q(deleted=None),
                name="unique_assoc_role_without_optional",
            ),
        ]


def get_assoc_executives(assoc):
    exe = AssocRole.objects.get(assoc=assoc, number=1)
    return exe.members.all()


def get_assoc_inners(assoc):
    lst = []
    already = {}
    for role in AssocRole.objects.filter(assoc=assoc).exclude(number=1):
        for mb in role.members.all():
            if mb.id in already:
                continue
            already[mb.id] = 1
            lst.append(mb)
    return lst


class EventPermission(BaseModel):
    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], blank=True)

    number = models.IntegerField(blank=True)

    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="event_permissions")

    descr = models.CharField(max_length=1000)

    hidden = models.BooleanField(default=False)

    config = models.TextField(max_length=100, blank=True, null=True)

    def module(self):
        # noinspection PyUnresolvedReferences
        return self.feature.module

    def __str__(self):
        return self.name

    def get_display_name(self):
        return self.name


class EventRole(BaseConceptModel):
    members = models.ManyToManyField(Member, related_name="event_roles")

    permissions = models.ManyToManyField(EventPermission, related_name="roles", blank=True)

    _clone_m2m_fields = ["permissions"]

    class Meta:
        indexes = [models.Index(fields=["number", "event"])]
        constraints = [
            UniqueConstraint(
                fields=["event", "number", "deleted"],
                name="unique_event_role_with_optional",
            ),
            UniqueConstraint(
                fields=["event", "number"],
                condition=Q(deleted=None),
                name="unique_event_role_without_optional",
            ),
        ]


def get_event_organizers(event):
    (orga, cr) = EventRole.objects.get_or_create(event=event, number=1)
    return orga.members.all()


def get_event_staffers(event):
    lst = []
    already = {}
    for role in EventRole.objects.filter(event=event):
        for mb in role.members.all():
            if mb.id in already:
                continue
            already[mb.id] = 1
            lst.append(mb)
    return lst
