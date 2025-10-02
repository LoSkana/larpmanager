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

import logging
import os
import subprocess

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection, connections

logging.getLogger("faker.factory").setLevel(logging.ERROR)
logging.getLogger("faker.providers").setLevel(logging.ERROR)


@pytest.fixture(autouse=True, scope="session")
def _env_for_tests():
    os.environ.setdefault("PYTHONHASHSEED", "0")
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture(autouse=True)
def _fast_password_hashers(settings):
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def _email_backend(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture(autouse=True)
def _cache_isolation(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-for-pytest",
        }
    }
    cache.clear()


@pytest.fixture
def reset_sequences(request):
    marker = request.node.get_closest_marker("django_db_reset_sequences")
    if marker:
        pass


@pytest.fixture
def pw_page(pytestconfig, browser_type, live_server):
    headed = pytestconfig.getoption("--headed") or os.getenv("PYCHARM_DEBUG", "0") == "1"

    browser = browser_type.launch(headless=not headed, slow_mo=50)
    context = browser.new_context(
        storage_state=None,
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()
    base_url = live_server.url
    page.set_default_timeout(60000)

    page.on("dialog", lambda dialog: dialog.accept())

    def on_response(response):
        error_status = 500
        if response.status == error_status:
            raise AssertionError(f"HTTP 500 su {response.url}")

    page.on("response", on_response)

    yield page, base_url, context

    context.close()
    browser.close()


def _truncate_app_tables():
    with connection.cursor() as cur:
        cur.execute(r"""
        DO $$
        DECLARE r RECORD;
        BEGIN
          FOR r IN
            SELECT format('%I.%I', n.nspname, c.relname) AS fq
            FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public'
              AND c.relkind='r'
              AND c.relname NOT LIKE 'django\_%'
              AND c.relname NOT LIKE 'authtoken\_%'
              AND c.relname NOT LIKE 'sessions\_%'
              AND c.relname NOT LIKE 'admin\_%'
          LOOP
            EXECUTE 'TRUNCATE TABLE ' || r.fq || ' RESTART IDENTITY CASCADE';
          END LOOP;
        END$$;""")


@pytest.fixture(autouse=True, scope="function")
def _db_teardown_between_tests(django_db_blocker, request):
    yield
    # For e2e tests (Playwright), truncate tables to reset the database
    # Unit tests use transactions which are automatically rolled back
    marker = request.node.get_closest_marker("e2e")
    if marker:
        with django_db_blocker.unblock():
            _truncate_app_tables()
            # Reload fixtures after truncation
            call_command("init_db")


@pytest.fixture(autouse=True, scope="session")
def load_fixtures(django_db_blocker, request):
    # Fixtures are loaded via SQL dump in django_db_setup
    pass


def psql(params, env):
    result = subprocess.run(params, check=False, env=env, text=True, capture_output=True)
    if result.returncode != 0:
        print(f"PSQL ERROR: {result.stderr}")
        print(f"PSQL OUTPUT: {result.stdout}")
        raise subprocess.CalledProcessError(result.returncode, params, result.stdout, result.stderr)


def pytest_sessionstart(session):
    # Skip if running in a xdist worker
    if hasattr(session.config, "workerinput"):
        return

    # Skip if xdist is being used (check for -n option)
    if session.config.getoption("numprocesses", default=None) is not None:
        return

    # Only run for local development without xdist
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.DATABASES["default"]["PASSWORD"]
    name = settings.DATABASES["default"]["NAME"]
    host = settings.DATABASES["default"].get("HOST") or "localhost"
    user = settings.DATABASES["default"]["USER"]

    clean_db(host, env, name, user)
    sql_path = os.path.join(os.path.dirname(__file__), "larpmanager", "tests", "test_db.sql")
    psql(["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-h", host, "-d", name, "-f", sql_path], env)


def clean_db(host, env, name, user):
    psql(
        [
            "psql",
            "-U",
            user,
            "-h",
            host,
            "-d",
            name,
            "-c",
            """
        DROP SCHEMA IF EXISTS public CASCADE;
        CREATE SCHEMA IF NOT EXISTS public AUTHORIZATION larpmanager;
    """,
        ],
        env,
    )


def pytest_configure(config):
    """Configure pytest-django to create databases for xdist workers."""
    if hasattr(config, "workerinput"):
        # We're in a xdist worker
        # Get the worker ID (gw0, gw1, etc.)
        worker_id = config.workerinput["workerid"]

        # Modify the database name to include the worker ID
        db_name = settings.DATABASES["default"]["NAME"]
        settings.DATABASES["default"]["NAME"] = f"{db_name}_{worker_id}"

        # Enable database creation
        config.option.create_db = True


@pytest.fixture(scope="session")
def django_db_setup(request, django_db_blocker):
    in_xdist_worker = hasattr(request.config, "workerinput")

    # If running with xdist, create and load worker database
    if in_xdist_worker:
        with django_db_blocker.unblock():
            worker_db_name = connections["default"].settings_dict["NAME"]
            db_cfg = connections.databases["default"]

            env = os.environ.copy()
            env["PGPASSWORD"] = db_cfg["PASSWORD"]
            host = db_cfg.get("HOST") or "localhost"
            user = db_cfg["USER"]

            # Drop and recreate the database
            psql(
                [
                    "psql",
                    "-U",
                    user,
                    "-h",
                    host,
                    "-d",
                    "postgres",
                    "-c",
                    f"DROP DATABASE IF EXISTS {worker_db_name}",
                ],
                env,
            )

            psql(
                [
                    "psql",
                    "-U",
                    user,
                    "-h",
                    host,
                    "-d",
                    "postgres",
                    "-c",
                    f"CREATE DATABASE {worker_db_name} OWNER {user}",
                ],
                env,
            )

            # Load the test database SQL
            sql_path = os.path.join(os.path.dirname(__file__), "larpmanager", "tests", "test_db.sql")
            psql(["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-h", host, "-d", worker_db_name, "-f", sql_path], env)
        return

    # Without xdist: database is already set up in pytest_sessionstart
    pass
