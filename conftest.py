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

import pytest


@pytest.fixture(scope="session", autouse=True)
def preload_test_db(django_db_setup, django_db_blocker):
    # Do not repeat if multiple xdist workers
    if os.environ.get("PYTEST_XDIST_WORKER", "gw0") != "gw0":
        return

    env = os.environ.copy()
    env["PGPASSWORD"] = "larpmanager"

    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        host = "postgres"
    else:
        host = "localhost"
        clean_db(env)

    sql_path = os.path.join(os.path.dirname(__file__), "larpmanager", "tests", "test_db.sql")

    with django_db_blocker.unblock():
        subprocess.run(
            [
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "larpmanager",
                "-h",
                host,
                "-d",
                "test_larpmanager",
                "-f",
                sql_path,
            ],
            check=True,
            env=env,
        )


def clean_db(env):
    host = "localhost"

    # stop connections to db
    subprocess.run(
        [
            "psql",
            "-U",
            "larpmanager",
            "-h",
            host,
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
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.DEVNULL,
    )

    # drop db
    subprocess.run(
        ["psql", "-U", "larpmanager", "-h", host, "-d", "postgres", "-c", "DROP DATABASE IF EXISTS test_larpmanager;"],
        check=True,
        env=env,
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.DEVNULL,
    )

    # create db
    subprocess.run(
        ["createdb", "test_larpmanager", "-U", "larpmanager", "-h", host],
        check=True,
        env=env,
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.DEVNULL,
    )
