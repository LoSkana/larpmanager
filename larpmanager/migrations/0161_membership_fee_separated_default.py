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
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary

from typing import Any

from django.db import migrations, models


def set_membership_fee_separated(apps: Any, schema_editor: Any) -> None:
    """Set membership_fee_separated=True for existing associations with membership feature.

    Preserves current behavior (separate payment) for all existing associations
    that already have the membership feature enabled, so they are unaffected by
    the new bundling option (which defaults to True = keep separate).
    """
    Association = apps.get_model("larpmanager", "Association")
    AssociationConfig = apps.get_model("larpmanager", "AssociationConfig")

    assoc_ids = (
        Association.objects.filter(features__slug="membership")
        .values_list("id", flat=True)
        .distinct()
    )

    for assoc_id in assoc_ids:
        AssociationConfig.objects.get_or_create(
            association_id=assoc_id,
            name="membership_fee_separated",
            deleted=None,
            defaults={"value": "True"},
        )


def reverse_membership_fee_separated(apps: Any, schema_editor: Any) -> None:
    """Remove membership_fee_separated config entries created by this migration."""
    AssociationConfig = apps.get_model("larpmanager", "AssociationConfig")
    AssociationConfig.objects.filter(name="membership_fee_separated", value="True").delete()


class Migration(migrations.Migration):
    """Data migration: set membership_fee_separated=True for existing membership associations."""

    dependencies: list = [
        ("larpmanager", "0160_larpmanagertext_value_htmlfield"),
    ]

    operations: list = [
        migrations.RunPython(set_membership_fee_separated, reverse_membership_fee_separated),
        migrations.AlterField(
            model_name="larpmanagertext",
            name="value",
            field=models.TextField(verbose_name="Value"),
        ),
        migrations.AlterField(
            model_name="paymentinvoice",
            name="causal",
            field=models.CharField(max_length=500),
        ),
        migrations.AddConstraint(
            model_name="accountingitemmembership",
            constraint=models.UniqueConstraint(
                condition=models.Q(deleted__isnull=True),
                fields=["member", "association", "year"],
                name="unique_active_membership_per_member_year",
            ),
        ),
    ]
