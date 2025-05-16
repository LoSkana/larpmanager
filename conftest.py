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
from django.core.management import call_command


@pytest.fixture(autouse=True, scope="function")
def load_fixtures(db):
    print("<<<< LOAD FIXTURE >>>>")
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        call_command("flush", interactive=False)
        call_command("init_db")


def psql(params, env):
    subprocess.run(params, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, text=True)


def pytest_sessionstart(session):
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        return

    env = os.environ.copy()
    env["PGPASSWORD"] = "larpmanager"

    host = "localhost"
    clean_db(host, env)

    sql_path = os.path.join(os.path.dirname(__file__), "larpmanager", "tests", "test_db.sql")

    psql(
        ["psql", "-v", "ON_ERROR_STOP=1", "-U", "larpmanager", "-h", host, "-d", "test_larpmanager", "-f", sql_path],
        env,
    )


def clean_db(host, env):
    psql(
        [
            "psql",
            "-U",
            "larpmanager",
            "-h",
            host,
            "-d",
            "test_larpmanager",
            "-c",
            "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
        ],
        env,
    )
