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

import pytest
from django.core.management import call_command
from django.db import connection


@pytest.fixture(scope="session")
def django_db_setup(django_db_blocker):
    with django_db_blocker.unblock():
        call_command("migrate", interactive=False, run_syncdb=True, verbosity=0)


EXCLUDE_PREFIXES = ("django_", "auth_", "authtoken_", "sessions_", "admin_")


def truncate_app_tables():
    with connection.cursor() as cur:
        cur.execute("""
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
              AND c.relname NOT LIKE 'auth\_%'
              AND c.relname NOT LIKE 'authtoken\_%'
              AND c.relname NOT LIKE 'sessions\_%'
              AND c.relname NOT LIKE 'admin\_%'
          LOOP
            EXECUTE 'TRUNCATE TABLE ' || r.fq || ' RESTART IDENTITY CASCADE';
          END LOOP;
        END$$;""")


@pytest.fixture(autouse=True, scope="function")
def ui_db_reset(django_db_blocker):
    yield
    with django_db_blocker.unblock():
        truncate_app_tables()


@pytest.fixture
def load_fixtures(django_db_blocker):
    with django_db_blocker.unblock():
        call_command("init_db", verbosity=0)
