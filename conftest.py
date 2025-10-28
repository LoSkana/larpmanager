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
from pathlib import Path

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection

from larpmanager.models.access import AssociationRole
from larpmanager.models.association import Association, AssociationSkin

logging.getLogger("faker.factory").setLevel(logging.ERROR)
logging.getLogger("faker.providers").setLevel(logging.ERROR)

# Track database initialization state per worker
_DB_INITIALIZED = {}


@pytest.fixture(autouse=True, scope="session")
def _env_for_tests():
    os.environ.setdefault("PYTHONHASHSEED", "0")
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


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


def psql(params, env):
    subprocess.run(params, check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, env=env, text=True)


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


def _database_has_tables():
    """Check if database has any application tables."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND c.relname NOT LIKE 'django_%'
        """)
        count = cursor.fetchone()[0]
        return count > 0


def _load_test_db_sql():
    """Load test database from SQL file."""
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.DATABASES["default"]["PASSWORD"]
    name = settings.DATABASES["default"]["NAME"]
    host = settings.DATABASES["default"].get("HOST") or "localhost"
    user = settings.DATABASES["default"]["USER"]

    sql_path = Path(__file__).parent / "larpmanager" / "tests" / "test_db.sql"

    if not sql_path.exists():
        raise FileNotFoundError(f"Test database SQL file not found: {sql_path}")

    # Clean the database first
    clean_db(host, env, name, user)

    # Load the SQL dump
    psql(["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-h", host, "-d", name, "-f", str(sql_path)], env)


def _reload_fixtures():
    _truncate_app_tables()
    call_command("init_db")


@pytest.fixture(autouse=True, scope="function")
def _e2e_db_setup(request, django_db_blocker):
    """Setup database for e2e tests with single database per worker."""

    with django_db_blocker.unblock():
        if not _database_has_tables():
            # No tables - load from SQL dump
            _load_test_db_sql()
        elif "playwright" in str(request.node.fspath):
            # Tables exist - truncate and init
            _reload_fixtures()

    yield


@pytest.fixture(autouse=True)
def _ensure_association_skin(db):
    """Ensure default AssociationSkin and AssociationRole exist for tests."""
    if not AssociationSkin.objects.filter(pk=1).exists():
        AssociationSkin.objects.create(pk=1, name="LarpManager", domain="larpmanager.com")

    # Ensure AssociationRole with number=1 exists for all associations
    for association in Association.objects.all():
        if not AssociationRole.objects.filter(association=association, number=1).exists():
            AssociationRole.objects.create(association=association, number=1, name="Executive")
