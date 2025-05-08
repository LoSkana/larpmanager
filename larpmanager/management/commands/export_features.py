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

from larpmanager.models.access import AssocPermission, EventPermission
from larpmanager.models.base import Feature, FeatureModule, PaymentMethod


class Command(BaseCommand):
    help = "Export features to yaml"

    def handle(self, *args, **options):
        models = {
            "module": (FeatureModule, ("id", "name", "descr", "order", "default")),
            "feature": (Feature, ("id", "name", "descr", "slug", "overall", "module", "placeholder", "order")),
            "assoc_permission": (AssocPermission, ("id", "name", "slug", "number", "feature")),
            "event_permission": (EventPermission, ("id", "name", "slug", "number", "feature")),
            "payment_methods": (PaymentMethod, ("id", "name", "slug", "instructions", "fields", "profile")),
        }

        for model, value in models.items():
            (typ, fields) = value
            data = []
            for el in typ.objects.values(*fields).order_by("pk"):
                entry = {
                    "model": typ._meta.app_label + "." + typ._meta.model_name,
                    "pk": el["id"],
                    "fields": {field: el[field] for field in fields if field != "id"},
                }
                data.append(entry)

            with open(f"larpmanager/fixtures/{model}.yaml", "w") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
