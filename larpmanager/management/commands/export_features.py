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
from typing import Any

import yaml
from django.core.management.base import BaseCommand
from django.db.models import ForeignKey, ImageField

from larpmanager.models.access import AssocPermission, EventPermission, PermissionModule
from larpmanager.models.association import AssociationSkin
from larpmanager.models.base import Feature, FeatureModule, PaymentMethod


class Command(BaseCommand):
    help = "Export features to yaml"

    # noinspection PyProtectedMember
    def handle(self, *args: tuple[Any, ...], **options: dict[str, Any]) -> None:
        """Export features and related data to YAML fixture files.

        This Django management command exports system configuration data including
        features, permissions, skins, modules, and payment methods to YAML fixture
        files for migration or backup purposes.

        Args:
            *args: Positional arguments from Django management command framework (unused).
            **options: Command line options from Django management command framework (unused).

        Side Effects:
            Creates YAML fixture files in larpmanager/fixtures/ directory:
            - skin.yaml: AssociationSkin configurations
            - module.yaml: FeatureModule definitions
            - feature.yaml: Feature configurations
            - permission_module.yaml: PermissionModule definitions
            - assoc_permission.yaml: AssocPermission configurations
            - event_permission.yaml: EventPermission configurations
            - payment_methods.yaml: PaymentMethod configurations
        """
        # Define models to export with their respective fields for serialization
        export_models = {
            "skin": (
                AssociationSkin,
                (
                    "id",
                    "name",
                    "domain",
                    "default_features",
                    "default_css",
                    "default_nation",
                    "default_mandatory_fields",
                    "default_optional_fields",
                ),
            ),
            "module": (FeatureModule, ("name", "slug", "order", "icon")),
            "feature": (
                Feature,
                (
                    "name",
                    "descr",
                    "slug",
                    "overall",
                    "module",
                    "placeholder",
                    "order",
                    "after_text",
                    "after_link",
                    "hidden",
                ),
            ),
            "permission_module": (PermissionModule, ("name", "slug", "order", "icon")),
            "assoc_permission": (
                AssocPermission,
                ("name", "descr", "slug", "number", "feature", "config", "hidden", "module"),
            ),
            "event_permission": (
                EventPermission,
                ("name", "descr", "slug", "number", "feature", "config", "hidden", "module"),
            ),
            "payment_methods": (PaymentMethod, ("name", "slug", "instructions", "fields", "profile")),
        }

        # Process each model type and export to YAML fixture files
        for model_name, model_config in export_models.items():
            model_class, field_names = model_config
            data = []

            # Categorize fields by Django field type for proper serialization handling
            m2m_fields = [f.name for f in model_class._meta.many_to_many if f.name in field_names]
            fk_fields = [
                f.name for f in model_class._meta.fields if isinstance(f, ForeignKey) and f.name in field_names
            ]
            img_fields = [
                f.name for f in model_class._meta.fields if isinstance(f, ImageField) and f.name in field_names
            ]

            # Regular fields are all remaining fields except 'id' which is handled separately
            regular_fields = [
                f
                for f in field_names
                if f not in m2m_fields and f not in fk_fields and f not in img_fields and f != "id"
            ]

            # Iterate through all model instances and build fixture data
            for obj in model_class.objects.all().order_by("pk"):
                entry_fields = {}

                # Export regular scalar fields with direct value assignment
                for field in regular_fields:
                    entry_fields[field] = getattr(obj, field)

                # Handle foreign key relationships by extracting slug or string representation
                for field in fk_fields:
                    rel_obj = getattr(obj, field)
                    if rel_obj is None:
                        entry_fields[field] = None
                    else:
                        # Try to get slug from related object, fallback to string representation
                        slug_val = getattr(rel_obj, "slug", None)
                        if slug_val is None and hasattr(rel_obj, "get_slug") and callable(rel_obj.get_slug):
                            slug_val = rel_obj.get_slug()
                        if slug_val is None:
                            try:
                                slug_val = str(rel_obj)
                            except Exception:
                                # Final fallback to foreign key ID
                                slug_val = getattr(obj, f"{field}_id")
                        entry_fields[field] = slug_val

                # Handle image fields by storing file path or None
                for field in img_fields:
                    image = getattr(obj, field)
                    entry_fields[field] = image.name if image else None

                # Handle many-to-many relationships as lists of primary keys
                for field in m2m_fields:
                    entry_fields[field] = list(getattr(obj, field).values_list("pk", flat=True))

                # Build Django fixture format entry with model identifier
                entry = {
                    "model": f"{model_class._meta.app_label}.{model_class._meta.model_name}",
                    "fields": entry_fields,
                }
                data.append(entry)

            # Write fixture data to YAML file with readable formatting
            fixture_path = f"larpmanager/fixtures/{model_name}.yaml"
            with open(fixture_path, "w") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
