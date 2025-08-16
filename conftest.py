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
import pathlib

import pytest
from django.core.management import call_command


@pytest.fixture(autouse=True, scope="session")
def _env_for_tests():
    os.environ.setdefault("PYTHONHASHSEED", "0")
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture(autouse=True)
def _fast_password_hashers(settings):
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
def pw_page(browser, live_server):
    context = browser.new_context(storage_state=None, viewport={"width": 1280, "height": 800})
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    base_url = live_server.url
    page.set_default_timeout(5000)

    page.on("dialog", lambda dialog: dialog.accept())

    def on_response(response):
        error_code = 500
        if response.status == error_code:
            raise Exception(f"500 on {response.url}")

    page.on("response", on_response)

    yield page, base_url, context

    failed = any(getattr(rep, "failed", False) for rep in getattr(page, "_pytest_outcomes", []))
    artifacts_dir = pathlib.Path("artifacts/playwright")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    if failed:
        context.tracing.stop(path=str(artifacts_dir / f"{page._guid}_trace.zip"))
        try:
            page.screenshot(path=str(artifacts_dir / f"{page._guid}_failed.png"), full_page=True)
        except Exception:
            pass
    else:
        try:
            context.tracing.stop()
        except Exception:
            pass
    context.close()


def pytest_runtest_makereport(item, call):
    if call.when == "call":
        page = item.funcargs.get("pw_page", None)
        if page:
            p, _, _ = page
            outcomes = getattr(p, "_pytest_outcomes", [])
            outcomes.append(call)
            p._pytest_outcomes = outcomes


@pytest.fixture(autouse=True)
def _baseline_unit(db, django_db_blocker, request):
    if "live_server" in request.fixturenames:
        return
    with django_db_blocker.unblock():
        # Il comando deve essere idempotente
        call_command("init_db", verbosity=0, interactive=False)


@pytest.fixture(autouse=True)
def _baseline_e2e(transactional_db, django_db_blocker, request):
    if "live_server" not in request.fixturenames:
        return
    with django_db_blocker.unblock():
        call_command("init_db", verbosity=0, interactive=False)
