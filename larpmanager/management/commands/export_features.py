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

import yaml
from django.core.management.base import BaseCommand
from django.db.models import ForeignKey, ImageField

from larpmanager.models.access import AssocPermission, EventPermission
from larpmanager.models.association import AssociationSkin
from larpmanager.models.base import Feature, FeatureModule, PaymentMethod


class Command(BaseCommand):
    help = "Export features to yaml"

    # noinspection PyProtectedMember
    def handle(self, *args, **options):
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
            "module": (FeatureModule, ("id", "name", "descr", "order", "default", "icon")),
            "feature": (
                Feature,
                (
                    "id",
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
            "assoc_permission": (AssocPermission, ("id", "name", "descr", "slug", "number", "feature", "hidden")),
            "event_permission": (EventPermission, ("id", "name", "descr", "slug", "number", "feature", "hidden")),
            "payment_methods": (PaymentMethod, ("id", "name", "slug", "instructions", "fields", "profile")),
        }

        for model, value in export_models.items():
            typ, fields = value
            data = []

            m2m_fields = [f.name for f in typ._meta.many_to_many if f.name in fields]
            fk_fields = [f.name for f in typ._meta.fields if isinstance(f, ForeignKey) and f.name in fields]
            img_fields = [f.name for f in typ._meta.fields if isinstance(f, ImageField) and f.name in fields]
            regular_fields = [
                f for f in fields if f not in m2m_fields and f not in fk_fields and f not in img_fields and f != "id"
            ]

            for obj in typ.objects.all().order_by("pk"):
                entry_fields = {}

                for field in regular_fields:
                    entry_fields[field] = getattr(obj, field)

                for field in fk_fields:
                    entry_fields[field] = getattr(obj, field + "_id")

                for field in img_fields:
                    image = getattr(obj, field)
                    entry_fields[field] = image.name if image else None

                for field in m2m_fields:
                    entry_fields[field] = list(getattr(obj, field).values_list("pk", flat=True))

                entry = {
                    "model": typ._meta.app_label + "." + typ._meta.model_name,
                    "pk": obj.pk,
                    "fields": entry_fields,
                }

                data.append(entry)

            with open(f"larpmanager/fixtures/{model}.yaml", "w") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
