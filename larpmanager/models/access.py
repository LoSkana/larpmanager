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
from django.db.models import Q, QuerySet, UniqueConstraint

from larpmanager.models.association import Association
from larpmanager.models.base import AlphanumericValidator, BaseModel, Feature
from larpmanager.models.event import BaseConceptModel, Event
from larpmanager.models.member import Member


class PermissionModule(BaseModel):
    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], db_index=True, unique=True)

    icon = models.CharField(max_length=100)

    order = models.IntegerField()


class AssocPermission(BaseModel):
    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], blank=True, unique=True)

    number = models.IntegerField(blank=True)

    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="assoc_permissions")

    module = models.ForeignKey(PermissionModule, on_delete=models.CASCADE, related_name="assoc_permissions")

    descr = models.CharField(max_length=1000)

    hidden = models.BooleanField(default=False)

    config = models.TextField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        indexes = [
            models.Index(fields=["slug"], condition=Q(deleted__isnull=True), name="aperm_slug_act"),
        ]


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


def get_assoc_executives(assoc: Association) -> QuerySet[Member]:
    """Get all executive members of an association.

    Args:
        assoc (Association): The association instance to get executives from.

    Returns:
        QuerySet[Member]: A queryset containing all members with executive role
            (role number 1) for the specified association.

    Raises:
        AssocRole.DoesNotExist: If no executive role (number=1) exists for the association.
    """
    # Get the executive role (number 1) for the association
    exe = AssocRole.objects.get(assoc=assoc, number=1)

    # Return all members assigned to the executive role
    return exe.members.all()


def get_assoc_inners(assoc: Association) -> list[Member]:
    """Get all non-executive members with association roles.

    Retrieves all members that have roles in the given association, excluding
    executive members (role number 1). Ensures each member appears only once
    in the returned list, even if they have multiple roles.

    Args:
        assoc (Association): The association instance to get members from.

    Returns:
        list[Member]: List of unique Member instances with non-executive roles
            in the association. Returns empty list if no qualifying members found.

    Example:
        >>> assoc = Association.objects.get(name="My Association")
        >>> members = get_assoc_inners(assoc)
        >>> len(members)
        5
    """
    lst = []
    already = {}

    # Get all non-executive roles (exclude role number 1) for this association
    for role in AssocRole.objects.filter(assoc=assoc).exclude(number=1):
        # Iterate through all members assigned to this role
        for mb in role.members.all():
            # Skip if member already processed to avoid duplicates
            if mb.id in already:
                continue
            # Mark member as processed and add to results
            already[mb.id] = 1
            lst.append(mb)
    return lst


class EventPermission(BaseModel):
    name = models.CharField(max_length=100)

    slug = models.SlugField(max_length=100, validators=[AlphanumericValidator], blank=True, unique=True)

    number = models.IntegerField(blank=True)

    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="event_permissions")

    module = models.ForeignKey(PermissionModule, on_delete=models.CASCADE, related_name="event_permissions")

    descr = models.CharField(max_length=1000)

    hidden = models.BooleanField(default=False)

    config = models.TextField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name

    def get_display_name(self):
        return self.name

    class Meta:
        indexes = [
            models.Index(fields=["slug"], condition=Q(deleted__isnull=True), name="eperm_slug_act"),
        ]


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


def get_event_organizers(event: Event) -> QuerySet[Member]:
    """Get all organizer members of an event.

    Retrieves the event organizer role (role number 1) and returns all members
    assigned to that role. Creates the organizer role if it doesn't exist.

    Args:
        event (Event): The event instance to get organizers for.

    Returns:
        QuerySet[Member]: QuerySet containing all members with event organizer
            role (role number 1).

    Note:
        This function uses get_or_create to ensure the organizer role exists,
        so it may create a new EventRole if none exists for this event.
    """
    # Get or create the event organizer role (role number 1)
    (orga, cr) = EventRole.objects.get_or_create(event=event, number=1)

    # Return all members assigned to the organizer role
    return orga.members.all()


def get_event_staffers(event: Event) -> list:
    """Get all non-organizer staff members of an event.

    Retrieves all unique members who have roles in the specified event,
    excluding organizers. Uses prefetch_related for optimized database queries.

    Args:
        event: Event instance to get staff members for

    Returns:
        List of Member instances with non-organizer event roles, with duplicates removed

    Note:
        Members with multiple roles in the same event are only included once
    """
    # Fetch all event roles with their associated members in a single query
    roles = EventRole.objects.filter(event=event).prefetch_related("members")

    # Initialize result list and tracking dictionary for unique members
    lst = []
    already = {}

    # Iterate through each role in the event
    for role in roles:
        # Process each member assigned to the current role
        for mb in role.members.all():
            # Skip if member already processed to avoid duplicates
            if mb.id in already:
                continue

            # Mark member as processed and add to result list
            already[mb.id] = 1
            lst.append(mb)

    return lst
