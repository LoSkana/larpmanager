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

    def handle(self, *args, **options) -> None:
        """Handle the command to list association emails.

        This command retrieves all non-demo associations that have a main email
        address and prints their slug and email in a formatted manner. It also
        prints the admin email from settings.

        Args:
            *args: Variable length argument list passed to the command.
            **options: Arbitrary keyword arguments passed to the command.

        Returns:
            None: This method outputs to stdout and doesn't return a value.
        """
        # Filter associations with valid main emails, excluding demo accounts
        lst = Association.objects.filter(main_mail__isnull=False).exclude(main_mail="").exclude(demo=True)

        # Iterate through associations ordered by slug and output formatted email info
        for el in lst.order_by("slug").values_list("slug", "main_mail"):
            if el[1]:
                self.stdout.write(f"{el[0]}@larpmanager.com {el[1]}")

        # Get admin email from settings and output it
        name, email = conf_settings.ADMINS[0]
        self.stdout.write(f"@larpmanager.com {email}")
