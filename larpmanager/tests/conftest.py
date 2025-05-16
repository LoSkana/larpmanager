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


def pytest_sessionstart(session):
    env = os.environ.copy()
    env["PGPASSWORD"] = "larpmanager"

    sql_path = os.path.join(os.path.dirname(__file__), "test_db.sql")

    # stop connections to db
    subprocess.run(
        [
            "psql",
            "-U",
            "larpmanager",
            "-h",
            "localhost",
            "-d",
            "postgres",
            "-c",
            (
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = 'test_larpmanager' AND pid <> pg_backend_pid();"
            ),
        ],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # drop db
    subprocess.run(
        ["dropdb", "test_larpmanager", "-U", "larpmanager", "-h", "localhost"],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # create db
    subprocess.run(
        ["createdb", "test_larpmanager", "-U", "larpmanager", "-h", "localhost"],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # load db
    subprocess.run(
        [
            "psql",
            "-q",  # quiet mode
            "-X",  # no config
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "larpmanager",
            "-h",
            "localhost",
            "-d",
            "test_larpmanager",
            "-f",
            sql_path,
        ],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
