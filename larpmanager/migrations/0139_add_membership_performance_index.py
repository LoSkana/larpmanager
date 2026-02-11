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

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    """Add composite index for membership queries performance.

    This index optimizes queries in AssociationMemberS2Widget that filter by
    association_id, status, and member_id. The previous indexes covered only
    (association, member) or (association, status), but not all three fields
    together, causing slow queries when rendering forms with member selectors.
    """

    dependencies = [
        ('larpmanager', '0138_add_uuid_to_volunteerregistry'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='membership',
            index=models.Index(
                fields=['association', 'status', 'member'],
                condition=Q(deleted__isnull=True),
                name='memb_assoc_stat_mem_act',
            ),
        ),
    ]
