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


def handle_tutorial_slug_generation(instance):
    """Generate slug for tutorial if not already set.

    Args:
        instance: LarpManagerTutorial instance being saved
    """
    if not instance.slug:
        instance.slug = slugify(instance.name)


def assign_faq_number(faq):
    """Assign number to FAQ if not already set.

    Args:
        faq: LarpManagerFaq instance to assign number to
    """
    if faq.number:
        return
    n = LarpManagerFaq.objects.filter(typ=faq.typ).aggregate(Max("number"))["number__max"]
    if not n:
        n = 1
    else:
        n = ((n / 10) + 1) * 10
    faq.number = n
