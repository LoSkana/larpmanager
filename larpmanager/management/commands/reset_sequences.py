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
from __future__ import annotations

from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    """Django management command to reset PostgreSQL sequences."""

    help = "Reset PostgreSQL sequences for all tables to prevent duplicate key violations"

    def add_arguments(self, parser: Any) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--tables",
            nargs="+",
            help="Specific table names to reset (default: all larpmanager tables)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show SQL that would be executed without running it",
        )

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002
        """Reset sequences for PostgreSQL tables.

        This command fixes the issue where PostgreSQL sequences get out of sync
        with the actual data when records are inserted with explicit IDs (e.g., from fixtures).
        """
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING("This command only works with PostgreSQL databases"))
            return

        # Get all models from larpmanager app
        larpmanager_models = apps.get_app_config("larpmanager").get_models()

        # Filter to specific tables if provided
        if options.get("tables"):
            table_names = options["tables"]
            models = [m for m in larpmanager_models if m._meta.db_table in table_names]  # noqa: SLF001
        else:
            models = larpmanager_models

        if not models:
            self.stdout.write(self.style.WARNING("No matching tables found"))
            return

        sql_statements = []

        for model in models:
            table_name = model._meta.db_table  # noqa: SLF001

            # Only reset tables with auto-incrementing primary keys
            pk_field = model._meta.pk  # noqa: SLF001
            if not pk_field or pk_field.get_internal_type() not in ("AutoField", "BigAutoField"):
                continue

            # Generate SQL to reset the sequence
            sequence_name = f"{table_name}_{pk_field.column}_seq"
            sql = f"SELECT setval('{sequence_name}', COALESCE((SELECT MAX({pk_field.column}) FROM {table_name}), 1));"  # noqa: S608
            sql_statements.append((table_name, sql))

        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING("DRY RUN - SQL that would be executed:"))
            for table_name, sql in sql_statements:
                self.stdout.write(f"\n-- {table_name}")
                self.stdout.write(sql)
        else:
            with connection.cursor() as cursor:
                for table_name, sql in sql_statements:
                    try:
                        cursor.execute(sql)
                        self.stdout.write(
                            self.style.SUCCESS(f"✓ Reset sequence for {table_name}"),
                        )
                    except Exception as e:  # noqa: BLE001, PERF203
                        self.stdout.write(
                            self.style.ERROR(f"✗ Failed to reset sequence for {table_name}: {e}"),
                        )

            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully reset {len(sql_statements)} sequences"))
