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

from django.conf import settings as conf_settings
from django.core.management.base import BaseCommand

from larpmanager.models.association import Association


class Command(BaseCommand):
    help = "List of all assocs mails"

    def handle(self, *args, **options):
        lst = Association.objects.filter(main_mail__isnull=False).exclude(main_mail="").exclude(demo=True)
        for el in lst.order_by("slug").values_list("slug", "main_mail"):
            if el[1]:
                self.stdout.write(f"{el[0]}@larpmanager.com {el[1]}")

        name, email = conf_settings.ADMINS[0]
        self.stdout.write(f"@larpmanager.com {email}")
