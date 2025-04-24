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

# Get text from features, assoc permission, event permission
trans_path = "larpmanager/templates/trans.html"

with open(trans_path, "w") as f:
    f.writelines("{% load i18n %}\n")

    for fixture in ["module", "feature", "assoc_permission", "event_permission"]:
        with open(f"larpmanager/fixtures/{fixture}.yaml", encoding="utf-8") as fixture_file:
            data = yaml.safe_load(fixture_file)

            for el in data:
                for s in ["name", "descr"]:
                    if s not in el["fields"] or not el["fields"][s]:
                        continue
                    f.writelines("{% blocktrans %}" + el["fields"][s] + "{% endblocktrans %}\n")
