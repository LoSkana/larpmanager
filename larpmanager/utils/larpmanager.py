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
from django.db.models import Max
from slugify import slugify

from larpmanager.models.larpmanager import LarpManagerFaq


def generate_tutorial_url_slug(tutorial) -> None:
    """Generate slug for tutorial if not already set.

    Args:
        tutorial: LarpManagerTutorial instance being saved

    """
    if not tutorial.slug:
        tutorial.slug = slugify(tutorial.name)


def auto_assign_faq_sequential_number(faq: LarpManagerFaq) -> None:
    """Assign number to FAQ if not already set.

    Automatically assigns a sequential number to an FAQ item based on its type.
    Numbers are assigned in increments of 10 (10, 20, 30, etc.) to allow for
    future insertions between existing items.

    Args:
        faq (LarpManagerFaq): FAQ instance to assign number to. Must have a 'typ'
            attribute to determine the sequence group.

    Returns:
        None: This function modifies the FAQ object in place.

    Note:
        If the FAQ already has a number assigned, no action is taken.
        The numbering starts at 1 for the first FAQ of each type.

    """
    # Skip assignment if FAQ already has a number
    if faq.number:
        return

    # Get the highest number for FAQs of the same type
    max_number = LarpManagerFaq.objects.filter(typ=faq.typ).aggregate(Max("number"))["number__max"]

    # Handle first FAQ of this type (no existing numbers)
    # Calculate next number in sequence (increments of 10)
    # Example: if max is 25, next will be 30
    next_number = 1 if not max_number else ((max_number // 10) + 1) * 10

    # Assign the calculated number to the FAQ
    faq.number = next_number
