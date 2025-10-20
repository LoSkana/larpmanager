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

    # noinspection PyProtectedMember
    def handle(self, *args: tuple, **options: dict) -> None:
        """Database reset command with fixtures loading.

        This command truncates all database tables and reloads initial fixtures.
        It handles both PostgreSQL and SQLite databases with appropriate SQL commands.

        Args:
            *args: Variable length argument list from command line
            **options: Arbitrary keyword arguments containing command options

        Returns:
            None

        Raises:
            DatabaseError: If database operations fail
            CommandError: If fixture loading fails

        Side Effects:
            - Truncates all database tables
            - Resets auto-increment sequences
            - Loads initial fixtures via init_db command
        """
        # Verify we're not on main branch before proceeding
        check_branch()

        self.stdout.write("Resetting database...")

        # Handle PostgreSQL database truncation
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                # Iterate through all models and truncate their tables
                for model in apps.get_models():
                    table = model._meta.db_table
                    # RESTART IDENTITY resets sequences, CASCADE handles foreign keys
                    cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')

        # Handle SQLite database truncation
        elif connection.vendor == "sqlite":
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Temporarily disable foreign key constraints
                    cursor.execute("PRAGMA foreign_keys = OFF;")

                    # Delete all data from each table and reset sequences
                    for model in apps.get_models():
                        table = model._meta.db_table
                        cursor.execute(f'DELETE FROM "{table}";')
                        # Reset AUTOINCREMENT counter for the table
                        cursor.execute(f'DELETE FROM sqlite_sequence WHERE name="{table}";')

                    # Re-enable foreign key constraints
                    cursor.execute("PRAGMA foreign_keys = ON;")

        # Load initial fixtures and test data
        call_command("init_db")
