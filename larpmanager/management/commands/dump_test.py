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
import subprocess

from django.core.management import BaseCommand, call_command

from larpmanager.management.commands.utils import check_branch


class Command(BaseCommand):
    help = "Dump test db"

    def handle(self, *args, **kwargs):
        check_branch()

        call_command("reset", verbosity=0)
        call_command("migrate", verbosity=0)

        self.stdout.write("Dumping database to test_db.sql...")
        env = os.environ.copy()
        env["PGPASSWORD"] = "larpmanager"
        dump_cmd = [
            "pg_dump",
            "-U",
            "larpmanager",
            "-h",
            "localhost",
            "-d",
            "larpmanager",
            "--inserts",
            "--no-owner",
            "--no-privileges",
            "-f",
            "larpmanager/tests/test_db.sql",
        ]
        try:
            subprocess.run(dump_cmd, check=True, env=env)
            self.stdout.write(self.style.SUCCESS("Database dump completed: test_db.sql"))
        except subprocess.CalledProcessError as e:
            self.stderr.write(self.style.ERROR(f"Dump failed: {e}"))
