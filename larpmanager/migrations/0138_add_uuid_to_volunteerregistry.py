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

from larpmanager.models.utils import my_uuid_short


def populate_volunteer_registry_uuids(apps, schema_editor):
    """Generate UUIDs for existing VolunteerRegistry records."""
    VolunteerRegistry = apps.get_model("larpmanager", "VolunteerRegistry")

    for volunteer in VolunteerRegistry.objects.filter(uuid__isnull=True):
        # Generate unique UUID with retry logic
        attempts = 0
        max_attempts = 10
        while attempts < max_attempts:
            volunteer.uuid = my_uuid_short()
            try:
                volunteer.save()
                break
            except Exception:
                attempts += 1
                if attempts >= max_attempts:
                    raise


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0137_performance_indexes"),
    ]

    operations = [
        # Step 1: Add uuid field as nullable (no index yet to avoid duplication)
        migrations.AddField(
            model_name="volunteerregistry",
            name="uuid",
            field=models.CharField(
                editable=False,
                max_length=12,
                null=True,
            ),
        ),
        # Step 2: Populate UUIDs for existing records
        migrations.RunPython(
            populate_volunteer_registry_uuids,
            reverse_code=migrations.RunPython.noop,
        ),
        # Step 3: Make uuid field non-nullable and unique (with index)
        migrations.AlterField(
            model_name="volunteerregistry",
            name="uuid",
            field=models.CharField(
                db_index=True,
                editable=False,
                max_length=12,
                unique=True,
            ),
        ),
    ]
