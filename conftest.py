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
from django.core.management import call_command
from django.db import connection

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
    from django.core.cache import cache

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
def _db_teardown_between_tests(django_db_blocker):
    yield
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        with django_db_blocker.unblock():
            _truncate_app_tables()


@pytest.fixture(autouse=True)
def load_fixtures(django_db_blocker):
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        with django_db_blocker.unblock():
            call_command("init_db", verbosity=0)


def psql(params, env):
    subprocess.run(params, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, text=True)


def pytest_sessionstart(session):
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        return

    env = os.environ.copy()
    env["PGPASSWORD"] = settings.DATABASES["default"]["PASSWORD"]
    name = settings.DATABASES["default"]["NAME"]
    host = settings.DATABASES["default"].get("HOST") or "localhost"
    user = settings.DATABASES["default"]["USER"]

    clean_db(host, env, name, user)
    sql_path = os.path.join(os.path.dirname(__file__), "larpmanager", "tests", "test_db.sql")
    psql(["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-h", host, "-d", name, "-f", sql_path], env)


def clean_db(host, env, name, user):
    psql(["psql", "-U", user, "-h", host, "-d", name, "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"], env)


@pytest.fixture(scope="session")
def django_db_setup():
    # normal behaviour in CI
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        return
    # don't touch the db in local
    pass
