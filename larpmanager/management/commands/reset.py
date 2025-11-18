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
    """Django management command."""

    help = "Reset DB"

    # noinspection PyProtectedMember
    def handle(self, *args: tuple, **options: dict) -> None:  # noqa: ARG002
        """Database reset command with fixtures loading.

        Truncates all database tables and reloads initial fixtures. Supports
        both PostgreSQL and SQLite databases with appropriate reset strategies.

        Args:
            *args: Command line arguments passed to the management command
            **options: Dictionary of command options and flags

        Returns:
            None

        Raises:
            DatabaseError: If database operations fail during truncation
            CommandError: If fixture loading fails

        Side Effects:
            - Truncates all database tables
            - Resets auto-increment sequences
            - Loads initial fixtures via init_db command

        """
        # Ensure we're not running on main branch
        check_branch()

        self.stdout.write("Resetting database...")

        # Handle PostgreSQL database reset
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                # Truncate all tables with CASCADE to handle foreign keys
                for model in apps.get_models():
                    table = model._meta.db_table  # noqa: SLF001  # Django model metadata
                    cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')

        # Handle SQLite database reset
        elif connection.vendor == "sqlite":
            with transaction.atomic(), connection.cursor() as cursor:
                # Disable foreign key constraints for deletion
                cursor.execute("PRAGMA foreign_keys = OFF;")

                # Delete all data and reset auto-increment sequences
                for model in apps.get_models():
                    table = model._meta.db_table  # noqa: SLF001  # Django model metadata
                    cursor.execute(f'DELETE FROM "{table}";')  # noqa: S608
                    cursor.execute(f'DELETE FROM sqlite_sequence WHERE name="{table}";')  # noqa: S608

                # Re-enable foreign key constraints
                cursor.execute("PRAGMA foreign_keys = ON;")

        # Load initial fixtures and test data
        call_command("init_db")
