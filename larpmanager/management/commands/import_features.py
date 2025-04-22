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


class Command(BaseCommand):
    help = "Reload features from yaml"

    def handle(self, *args, **options):
        for fixture in ["module", "feature", "assoc_permission", "event_permission", "payment_methods"]:
            fixture_path = os.path.join(conf_settings.BASE_DIR, "..", "larpmanager", "fixtures", f"{fixture}.yaml")
            with open(fixture_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for obj in data:
                model_label = obj["model"]
                Model = apps.get_model(model_label)

                pk = obj["pk"]
                fields = obj["fields"]

                for s in ["feature", "module"]:
                    if s in fields:
                        fields[f"{s}_id"] = fields.pop(s)

                Model.objects.update_or_create(pk=pk, defaults=fields)
