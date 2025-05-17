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

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from larpmanager.management.commands.utils import check_branch


class Command(BaseCommand):
    help = "Reset DB"

    def handle(self, *args, **options):
        check_branch()

        self.stdout.write("Resetting database...")

        # Truncate all tables
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                for model in apps.get_models():
                    table = model._meta.db_table
                    cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')
        elif connection.vendor == "sqlite":
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA foreign_keys = OFF;")
                    for model in apps.get_models():
                        table = model._meta.db_table
                        cursor.execute(f'DELETE FROM "{table}";')
                        cursor.execute(f'DELETE FROM sqlite_sequence WHERE name="{table}";')  # reset AUTOINCREMENT
                    cursor.execute("PRAGMA foreign_keys = ON;")

        # Load fixtures
        call_command("init_db")
