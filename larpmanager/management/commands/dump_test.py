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
import re
import subprocess
from pathlib import Path

from django.core.management import BaseCommand, call_command

from larpmanager.management.commands.utils import check_branch, check_virtualenv


class Command(BaseCommand):
    """Django management command."""

    help = "Dump test db"

    def normalize_dates(self, file_path: str) -> None:
        """Normalize dynamic dates in SQL dump to fixed reference dates.

        This function replaces all occurrences of dynamic timestamps (current date,
        migration dates, etc.) with fixed reference dates to ensure the dump file
        remains stable across multiple generations.

        Args:
            file_path: Path to the SQL dump file to normalize

        """
        self.stdout.write("Normalizing dates in SQL dump...")

        # Read the SQL file
        with Path(file_path).open(encoding="utf-8") as f:
            content = f.read()

        # Replace all timestamps with a fixed reference timestamp
        # Pattern: YYYY-MM-DD HH:MM:SS.microseconds+timezone
        # Microseconds can be 1-6 digits
        # Replace with: 2025-01-01 00:00:00.000000+01
        content = re.sub(
            r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+\d{2}",
            "2025-01-01 00:00:00.000000+01",
            content,
        )

        # Write the normalized content back
        with Path(file_path).open("w", encoding="utf-8") as f:
            f.write(content)

    def handle(self, *args: tuple, **kwargs: dict) -> None:  # noqa: ARG002
        """Django management command handler to dump test database.

        This function resets the database, applies migrations, and creates a clean
        SQL dump file for testing purposes. The dump is cleaned of PostgreSQL-specific
        commands that may cause issues during test restoration.

        Args:
            *args: Command line arguments passed to the management command
            **kwargs: Command line keyword arguments passed to the management command

        Raises:
            subprocess.CalledProcessError: If database dump or cleaning operations fail

        """
        # Ensure we're running inside a virtual environment
        check_virtualenv()

        # Verify we're on the correct branch before proceeding
        check_branch()

        # Reset database to clean state and apply all migrations
        call_command("reset", verbosity=0)

        # Configure environment for PostgreSQL authentication
        self.stdout.write("Dumping database to test_db.sql...")
        env = os.environ.copy()
        env["PGPASSWORD"] = "larpmanager"

        sql_file = Path("larpmanager/tests/test_db.sql")

        # Build pg_dump command with required parameters for test database
        dump_cmd = [
            "pg_dump",
            "-U",
            "larpmanager",
            "-h",
            "localhost",
            "-d",
            "larpmanager",
            "--inserts",  # Use INSERT statements instead of COPY
            "--no-owner",  # Skip ownership commands
            "--no-privileges",  # Skip privilege commands
            "-f",
            str(sql_file),
        ]

        # Execute database dump with error handling
        try:
            subprocess.run(dump_cmd, check=True, env=env)  # noqa: S603
        except subprocess.CalledProcessError as e:
            self.stderr.write(self.style.ERROR(f"Dump failed: {e}"))

        # Normalize dates to fixed reference dates for stable dumps
        self.normalize_dates(str(sql_file))

        # Clean up PostgreSQL-specific commands that may cause test issues
        clean_cmd = [
            "sed",
            "-i",
            r"/^--/d;"
            r"/^SET /d;"
            r"/^\\restrict/d;"
            r"/^\\unrestrict/d;"
            r"/^COMMENT ON SCHEMA public/d",
            str(sql_file),
        ]
        subprocess.run(clean_cmd, check=True, env=env)  # noqa: S603

        # Remove double lines
        clean_cmd = [
            "sed",
            "-i",
            r"/^$/N;/^\n$/D",
            str(sql_file),
        ]
        subprocess.run(clean_cmd, check=True, env=env)  # noqa: S603

        # Add schema version marker for test script validation
        migrations_dir = Path("larpmanager/migrations")
        migration_files = sorted(migrations_dir.glob("[0-9]*.py"), key=lambda p: p.name)

        if migration_files:
            latest_migration = migration_files[-1].stem  # Get filename without .py

            self.stdout.write(f"Adding schema marker: {latest_migration}...")

            # Append schema version comment to end of file
            with sql_file.open("a", encoding="utf-8") as f:
                f.write(f"\n-- LARPMANAGER_SCHEMA_VERSION: {latest_migration}\n")

        self.stdout.write(self.style.SUCCESS("All done!"))
