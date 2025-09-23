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

import os

import yaml
from django.apps import apps
from django.conf import settings as conf_settings
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Reload features from yaml"

    def handle(self, *args, **options):
        """Import feature system fixtures from YAML files.

        Loads modules, features, permissions, and other system configuration
        from YAML fixtures with proper handling of foreign keys and many-to-many relations.
        """
        for fixture in [
            "module",
            "feature",
            "permission_module",
            "assoc_permission",
            "event_permission",
            "payment_methods",
            "skin",
        ]:
            fixture_path = os.path.join(conf_settings.BASE_DIR, "..", "larpmanager", "fixtures", f"{fixture}.yaml")
            with open(fixture_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for obj in data:
                model_label = obj["model"]
                Model = apps.get_model(model_label)

                pk = obj["pk"]
                fields = obj["fields"]

                m2m_fields = {}
                for key in list(fields.keys()):
                    value = fields[key]
                    if isinstance(value, list):  # assume m2m
                        m2m_fields[key] = value
                        fields.pop(key)
                    elif key in ["feature", "module"]:  # rename foreign key
                        fields[f"{key}_id"] = fields.pop(key)

                with transaction.atomic():
                    instance, _ = Model.objects.update_or_create(pk=pk, defaults=fields)

                    for field, ids in m2m_fields.items():
                        getattr(instance, field).set(ids)
