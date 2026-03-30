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

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

import larpmanager.models.utils


def create_default_systems_and_assign(apps, schema_editor):
    """Create a default SystemExp for each event with the experience feature, then assign all
    AbilityExp and DeliveryExp records to the corresponding system."""
    SystemExp = apps.get_model("larpmanager", "SystemExp")
    AbilityExp = apps.get_model("larpmanager", "AbilityExp")
    DeliveryExp = apps.get_model("larpmanager", "DeliveryExp")
    Event = apps.get_model("larpmanager", "Event")
    Feature = apps.get_model("larpmanager", "Feature")

    try:
        px_feature = Feature.objects.get(slug="px")
    except Feature.DoesNotExist:
        return

    # Find all events that have the experience feature enabled via the M2M relationship
    event_ids = (
        Event.objects.filter(
            features=px_feature,
            deleted__isnull=True,
        )
        .values_list("id", flat=True)
        .distinct()
    )

    for event_id in event_ids:
        system, _ = SystemExp.objects.get_or_create(
            event_id=event_id,
            number=1,
            defaults={
                "name": "XP",
                "uuid": larpmanager.models.utils.my_uuid_short(),
            },
        )
        AbilityExp.objects.filter(event_id=event_id, system__isnull=True).update(system=system)
        DeliveryExp.objects.filter(event_id=event_id, system__isnull=True).update(system=system)

    # Handle any remaining records whose events didn't have the px feature enabled
    orphan_ability_event_ids = (
        AbilityExp.objects.filter(system__isnull=True)
        .values_list("event_id", flat=True)
        .distinct()
    )
    for event_id in orphan_ability_event_ids:
        system, _ = SystemExp.objects.get_or_create(
            event_id=event_id,
            number=1,
            defaults={
                "name": "XP",
                "uuid": larpmanager.models.utils.my_uuid_short(),
            },
        )
        AbilityExp.objects.filter(event_id=event_id, system__isnull=True).update(system=system)

    orphan_delivery_event_ids = (
        DeliveryExp.objects.filter(system__isnull=True)
        .values_list("event_id", flat=True)
        .distinct()
    )
    for event_id in orphan_delivery_event_ids:
        system, _ = SystemExp.objects.get_or_create(
            event_id=event_id,
            number=1,
            defaults={
                "name": "XP",
                "uuid": larpmanager.models.utils.my_uuid_short(),
            },
        )
        DeliveryExp.objects.filter(event_id=event_id, system__isnull=True).update(system=system)


def rename_feature_slugs(apps, schema_editor):
    """Rename old pseudo-feature slugs to exp_ prefixed versions."""
    Feature = apps.get_model("larpmanager", "Feature")
    Event = apps.get_model("larpmanager", "Event")
    renames = {
        "px": "experience",
        "rules": "exp_rules",
        "modifiers": "exp_modifiers",
        "templates": "exp_templates",
    }
    for old_slug, new_slug in renames.items():
        if Feature.objects.filter(slug=new_slug).exists():
            # Target already exists: transfer M2M event associations then delete the old feature
            try:
                old_feature = Feature.objects.get(slug=old_slug)
                new_feature = Feature.objects.get(slug=new_slug)
                for event in Event.objects.filter(features=old_feature):
                    if not event.features.filter(pk=new_feature.pk).exists():
                        event.features.add(new_feature)
                old_feature.delete()
            except Feature.DoesNotExist:
                pass
        else:
            Feature.objects.filter(slug=old_slug).update(slug=new_slug)


def rename_event_permission_slugs(apps, schema_editor):
    """Update EventPermissions to point to renamed Feature slugs."""
    EventPermission = apps.get_model("larpmanager", "EventPermission")
    Feature = apps.get_model("larpmanager", "Feature")
    slug_map = {
        "rules": "exp_rules",
        "modifiers": "exp_modifiers",
        "templates": "exp_templates",
    }
    for old_slug, new_slug in slug_map.items():
        try:
            new_feature = Feature.objects.get(slug=new_slug)
            EventPermission.objects.filter(feature__slug=old_slug).update(feature=new_feature)
        except Feature.DoesNotExist:
            pass


def rename_event_configs(apps, schema_editor):
    """Rename EventConfig keys from px_ prefix to exp_ prefix."""
    EventConfig = apps.get_model("larpmanager", "EventConfig")
    config_renames = {
        "px_user": "exp_user",
        "px_start": "exp_start",
        "px_undo": "exp_undo",
        "px_templates": "exp_templates",
        "px_rules": "exp_rules",
        "px_modifiers": "exp_modifiers",
        "px_auto_buy": "exp_auto_buy",
        "px_multiple": "exp_systems",
    }
    for old_key, new_key in config_renames.items():
        EventConfig.objects.filter(name=old_key).update(name=new_key)


def rename_addit_keys(apps, schema_editor):
    """Rename px_ keys in Character.addit JSON field to exp_ prefix."""
    CharacterConfig = apps.get_model("larpmanager", "CharacterConfig")
    key_map = {
        "px_tot": "exp_tot",
        "px_used": "exp_used",
        "px_avail": "exp_avail",
    }
    for old_key, new_key in key_map.items():
        CharacterConfig.objects.filter(name=old_key).update(name=new_key)

class Migration(migrations.Migration):

    dependencies = [
        ("larpmanager", "0147_alter_discount_value"),
    ]

    operations = [
        # Step 1: Rename existing models
        migrations.RenameModel(old_name="AbilityPx", new_name="AbilityExp"),
        migrations.RenameModel(old_name="AbilityTemplatePx", new_name="AbilityTemplateExp"),
        migrations.RenameModel(old_name="AbilityTypePx", new_name="AbilityTypeExp"),
        migrations.RenameModel(old_name="DeliveryPx", new_name="DeliveryExp"),
        migrations.RenameModel(old_name="ModifierPx", new_name="ModifierExp"),
        migrations.RenameModel(old_name="RulePx", new_name="RuleExp"),
        # Step 2: Create SystemExp table
        migrations.CreateModel(
            name="SystemExp",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "uuid",
                    models.CharField(
                        db_index=True,
                        editable=False,
                        max_length=12,
                        unique=True,
                    ),
                ),
                ("deleted", models.DateTimeField(db_index=True, editable=False, null=True)),
                ("deleted_by_cascade", models.BooleanField(default=False, editable=False)),
                ("created", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("number", models.IntegerField()),
                ("name", models.CharField(max_length=150)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="larpmanager.event",
                    ),
                ),
            ],
            options={},
        ),
        migrations.AddConstraint(
            model_name="systemexp",
            constraint=models.UniqueConstraint(
                fields=("event", "number", "deleted"),
                name="unique_system_px_with_optional",
            ),
        ),
        migrations.AddConstraint(
            model_name="systemexp",
            constraint=models.UniqueConstraint(
                condition=models.Q(deleted=None),
                fields=("event", "number"),
                name="unique_system_px_without_optional",
            ),
        ),
        migrations.AddIndex(
            model_name="systemexp",
            index=models.Index(fields=["number", "event"], name="larpmanager_number_997e5b_idx"),
        ),
        # Step 3: Add nullable system FK to AbilityExp and DeliveryExp
        migrations.AddField(
            model_name="abilityexp",
            name="system",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="abilities",
                to="larpmanager.systemexp",
                verbose_name="Experience System",
            ),
        ),
        migrations.AddField(
            model_name="deliveryexp",
            name="system",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="deliveries",
                to="larpmanager.systemexp",
                verbose_name="Experience System",
            ),
        ),
        # Step 4: Data migration - create default systems and assign existing records
        migrations.RunPython(create_default_systems_and_assign, migrations.RunPython.noop),
        # Step 5: Make system non-nullable
        migrations.AlterField(
            model_name="abilityexp",
            name="system",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="abilities",
                to="larpmanager.systemexp",
                verbose_name="Experience System",
            ),
        ),
        migrations.AlterField(
            model_name="deliveryexp",
            name="system",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="deliveries",
                to="larpmanager.systemexp",
                verbose_name="Experience System",
            ),
        ),
        # Step 6: Rename Feature slugs (px→experience, rules/modifiers/templates→exp_*)
        migrations.RunPython(rename_feature_slugs, migrations.RunPython.noop),
        # Step 7: Update EventPermissions to point to new Feature slugs
        migrations.RunPython(rename_event_permission_slugs, migrations.RunPython.noop),
        # Step 8: Rename EventConfig keys from px_ to exp_
        migrations.RunPython(rename_event_configs, migrations.RunPython.noop),
        # Step 9: Rename px_ keys in Character.addit JSON
        migrations.RunPython(rename_addit_keys, migrations.RunPython.noop),
        # Step 10: Update related_names on AbilityExp and DeliveryExp (no SQL, metadata only)
        migrations.AlterField(
            model_name="abilityexp",
            name="prerequisites",
            field=models.ManyToManyField(
                blank=True,
                help_text="Indicate the prerequisite abilities, which must be possessed before one can acquire this",
                related_name="exp_ability_unlock",
                symmetrical=False,
                to="larpmanager.abilityexp",
                verbose_name="Pre-requisites",
            ),
        ),
        migrations.AlterField(
            model_name="abilityexp",
            name="characters",
            field=models.ManyToManyField(
                blank=True,
                related_name="exp_ability_list",
                to="larpmanager.character",
            ),
        ),
        migrations.AlterField(
            model_name="deliveryexp",
            name="characters",
            field=models.ManyToManyField(
                blank=True,
                related_name="exp_delivery_list",
                to="larpmanager.character",
            ),
        ),
        # Step 11: Rename indexes after model renames (auto-names depend on model name)
        migrations.RenameIndex(
            model_name="abilityexp",
            new_name="larpmanager_number_28e377_idx",
            old_name="larpmanager_number_e9171d_idx",
        ),
        migrations.RenameIndex(
            model_name="abilitytypeexp",
            new_name="larpmanager_number_26136f_idx",
            old_name="larpmanager_number_221191_idx",
        ),
        migrations.RenameIndex(
            model_name="deliveryexp",
            new_name="larpmanager_number_e5ef17_idx",
            old_name="larpmanager_number_9a1f75_idx",
        ),
        migrations.RenameIndex(
            model_name="modifierexp",
            new_name="larpmanager_number_7157a9_idx",
            old_name="larpmanager_number_cbb709_idx",
        ),
        migrations.AlterField(
            model_name='abilityexp',
            name='system',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='abilities',
                                    to='larpmanager.systemexp', verbose_name='System'),
        ),
        migrations.AlterField(
            model_name='deliveryexp',
            name='system',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='deliveries',
                                    to='larpmanager.systemexp', verbose_name='System'),
        )
    ]
