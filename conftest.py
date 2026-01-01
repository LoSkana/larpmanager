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

"""Pytest configuration and fixtures for LarpManager test suite."""

import logging
import os
import re
import subprocess
from collections.abc import Generator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection, transaction
from django.test.utils import ContextList
from playwright.sync_api import BrowserContext, BrowserType, Page, Response
from pytest_django.fixtures import SettingsWrapper

from larpmanager.models.access import AssociationRole
from larpmanager.models.association import Association, AssociationSkin

logging.getLogger("faker.factory").setLevel(logging.ERROR)
logging.getLogger("faker.providers").setLevel(logging.ERROR)

# Track database initialization state per worker
_DB_INITIALIZED = {}
_DB_SCHEMA_CHECKED = {}


@pytest.fixture(autouse=True, scope="session")
def _env_for_tests() -> None:
    os.environ.setdefault("PYTHONHASHSEED", "0")
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture(autouse=True)
def _email_backend(settings: SettingsWrapper) -> None:
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture(autouse=True)
def _cache_isolation(settings: SettingsWrapper) -> None:
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-for-pytest",
        }
    }
    cache.clear()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator[None, Any, None]:  # noqa: ARG001
    """Hook to capture test results and make them available to fixtures."""
    outcome = yield
    rep = outcome.get_result()

    # Store test result in the item for fixture access
    setattr(item, f"rep_{rep.when}", rep)


def _save_screenshot(page: Page, base_filename: str, screenshot_dir: Path) -> None:
    """Save screenshot of the page."""
    screenshot_path = screenshot_dir / f"{base_filename}.png"
    logger = logging.getLogger(__name__)
    try:
        page.screenshot(path=str(screenshot_path))
        logger.info("Screenshot saved: %s", screenshot_path)
    except (OSError, RuntimeError) as e:
        logger.warning("Failed to save screenshot: %s", e)


def _save_html_content(page: Page, base_filename: str, screenshot_dir: Path) -> None:
    """Save HTML content of the page."""
    html_path = screenshot_dir / f"{base_filename}.html"
    logger = logging.getLogger(__name__)
    try:
        html_content = page.content()
        html_path.write_text(html_content, encoding="utf-8")
        logger.info("HTML content saved: %s", html_path)
    except (OSError, RuntimeError) as e:
        logger.warning("Failed to save HTML content: %s", e)


def _save_video(video_obj: Any, base_filename: str, screenshot_dir: Path) -> None:
    """Move and save the video recording."""
    logger = logging.getLogger(__name__)
    try:
        video_path = video_obj.path()
        if video_path and Path(video_path).exists():
            video_dest = screenshot_dir / f"{base_filename}.webm"
            Path(video_path).rename(video_dest)
            logger.info("Video saved: %s", video_dest)
    except (OSError, RuntimeError) as e:
        logger.warning("Failed to save video: %s", e)


def _capture_test_artifacts(
    request: pytest.FixtureRequest,
    page: Page,
    *,
    is_ci: bool,
    video_dir: Path | None,
) -> Any:
    """Capture screenshot, HTML and video if test failed.

    Returns video object if available and test failed, None otherwise.
    """
    if not (hasattr(request.node, "rep_call") and request.node.rep_call.failed):
        return None

    screenshot_dir = Path(__file__).parent / "test_screenshots"
    screenshot_dir.mkdir(exist_ok=True)

    # Generate filename with timestamp and test name
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    test_name = request.node.name
    base_filename = f"{timestamp}_{test_name}"

    # Save screenshot and HTML
    _save_screenshot(page, base_filename, screenshot_dir)
    _save_html_content(page, base_filename, screenshot_dir)

    # Get video object before closing (only if not in CI)
    video_obj = None
    if not is_ci and video_dir:
        logger = logging.getLogger(__name__)
        try:
            video_obj = page.video
        except (OSError, RuntimeError) as e:
            logger.warning("Failed to get video object: %s", e)

    return (video_obj, base_filename) if video_obj else None


@pytest.fixture
def pw_page(
    request: pytest.FixtureRequest,
    pytestconfig: pytest.Config,
    browser_type: BrowserType,
    live_server: ContextList,
) -> Generator[tuple[Page, str, BrowserContext], None, None]:
    """Prepares browser, context and finally page, for playwright tests."""
    headed = pytestconfig.getoption("--headed") or os.getenv("PYCHARM_DEBUG", "0") == "1"

    # Check if running in CI/GitHub Actions
    is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

    # Configure video recording (only if not in CI)
    video_dir = None
    if not is_ci:
        video_dir = Path(__file__).parent / "test_videos"
        video_dir.mkdir(exist_ok=True)

    browser = browser_type.launch(headless=not headed, slow_mo=50)
    context = browser.new_context(
        storage_state=None,
        viewport={"width": 1280, "height": 800},
        record_video_dir=str(video_dir) if video_dir else None,
        record_video_size={"width": 1280, "height": 800} if video_dir else None,
    )
    page = context.new_page()
    base_url = live_server.url
    page.set_default_timeout(60000)

    page.on("dialog", lambda dialog: dialog.accept())

    def on_response(response: Response) -> None:
        error_status = 500
        if response.status == error_status:
            msg = f"HTTP 500 su {response.url}"
            raise AssertionError(msg)

    page.on("response", on_response)

    yield page, base_url, context

    # Capture test artifacts if test failed
    video_info = _capture_test_artifacts(request, page, is_ci=is_ci, video_dir=video_dir)

    # Close context (this finalizes the video)
    context.close()
    browser.close()

    # Save video after context is closed (only if test failed and not in CI)
    if video_info:
        video_obj, base_filename = video_info
        screenshot_dir = Path(__file__).parent / "test_screenshots"
        _save_video(video_obj, base_filename, screenshot_dir)


def _truncate_app_tables() -> None:
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


def psql(params: list[str], env: Mapping[str, str]) -> None:
    """Performs a query on the db."""
    subprocess.run(params, check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, env=env, text=True)  # noqa: S603


def clean_db(host: str, env: Mapping[str, str], name: str, user: str) -> None:
    """Drop the schema and recreate it."""
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


def _database_has_tables() -> bool:
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


def _get_dump_schema_version() -> str | None:
    """Get schema version from test_db.sql dump file marker.

    Returns the migration name from the LARPMANAGER_SCHEMA_VERSION comment
    at the end of the SQL dump, or None if not found.
    """
    sql_path = Path(__file__).parent / "larpmanager" / "tests" / "test_db.sql"
    if not sql_path.exists():
        return None

    try:
        # Read last 500 bytes to find the version marker
        with sql_path.open("rb") as f:
            f.seek(max(0, sql_path.stat().st_size - 500))
            tail = f.read().decode("utf-8", errors="ignore")

        # Look for version marker
        match = re.search(r"-- LARPMANAGER_SCHEMA_VERSION:\s*(\S+)", tail)
        if match:
            return match.group(1)
    except (OSError, UnicodeDecodeError) as e:
        logger = logging.getLogger(__name__)
        logger.debug("Failed to read schema version from dump: %s", e)

    return None


def _get_latest_migration() -> str | None:
    """Get the name of the latest migration file."""
    migrations_dir = Path(__file__).parent / "larpmanager" / "migrations"
    if not migrations_dir.exists():
        return None

    # Get all numbered migration files and sort them
    migration_files = sorted(migrations_dir.glob("[0-9]*.py"))
    if migration_files:
        return migration_files[-1].stem

    return None


def _get_expected_migrations() -> set[str]:
    """Get list of all migration files that should be applied."""
    migrations_dir = Path(__file__).parent / "larpmanager" / "migrations"
    if not migrations_dir.exists():
        return set()

    # Get all migration files (exclude __init__.py and __pycache__)
    migration_files = set()
    for migration_file in migrations_dir.glob("*.py"):
        if migration_file.name != "__init__.py":
            # Remove .py extension to get migration name
            migration_files.add(migration_file.stem)

    return migration_files


def _get_applied_migrations() -> set[str]:
    """Get list of migrations that have been applied to the database."""
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("""
                SELECT name
                FROM django_migrations
                WHERE app = 'larpmanager'
            """)
            return {row[0] for row in cursor.fetchall()}
    except (OSError, RuntimeError) as e:
        # If query fails, return empty set (schema needs reload)
        logger = logging.getLogger(__name__)
        logger.debug("Failed to get applied migrations: %s", e)
        return set()


def _database_has_correct_schema() -> bool:
    """Check if database has all required migrations applied.

    Uses two-tier check:
    1. Fast check: Compare dump schema version marker with latest migration
    2. Full check: Compare all migration files with django_migrations table

    Returns True if all migration files in larpmanager/migrations/ are present
    in the database's django_migrations table.
    """
    # FAST PATH: Check if dump version marker matches latest migration
    # This avoids DB queries if the dump is already up-to-date
    dump_version = _get_dump_schema_version()
    latest_migration = _get_latest_migration()

    if dump_version and latest_migration and dump_version == latest_migration:
        # Dump is up-to-date, assume DB is correct
        return True

    # FULL CHECK: Query database to verify all migrations are applied
    expected_migrations = _get_expected_migrations()
    applied_migrations = _get_applied_migrations()

    # If we couldn't get applied migrations (error/no table), schema is wrong
    if not applied_migrations and expected_migrations:
        return False

    # Check if all expected migrations have been applied
    missing_migrations = expected_migrations - applied_migrations

    if missing_migrations:
        # Log which migrations are missing for debugging
        logger = logging.getLogger(__name__)
        logger.warning(
            "Missing %d migrations. First 5: %s",
            len(missing_migrations),
            sorted(missing_migrations)[:5],
        )
        return False

    return True


def _load_test_db_sql() -> None:
    """Load test database from SQL file."""
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.DATABASES["default"]["PASSWORD"]
    name = settings.DATABASES["default"]["NAME"]
    host = settings.DATABASES["default"].get("HOST") or "localhost"
    user = settings.DATABASES["default"]["USER"]

    sql_path = Path(__file__).parent / "larpmanager" / "tests" / "test_db.sql"

    if not sql_path.exists():
        msg = f"Test database SQL file not found: {sql_path}"
        raise FileNotFoundError(msg)

    # Clean the database first
    clean_db(host, env, name, user)

    # Load the SQL dump
    psql(["psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-h", host, "-d", name, "-f", str(sql_path)], env)


def _reload_fixtures() -> None:
    _truncate_app_tables()
    call_command("init_db")


@pytest.fixture(autouse=True)
def _e2e_db_setup(request: pytest.FixtureRequest, django_db_blocker: Any) -> None:
    """Set up database for e2e tests with single database per worker.

    This fixture runs once per worker to ensure the database schema is correct.
    Uses a global flag to avoid reloading the schema multiple times per worker.
    """
    logger = logging.getLogger(__name__)

    # Get worker ID for xdist parallel execution
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")

    with django_db_blocker.unblock():
        # Only check/load schema once per worker
        if worker_id not in _DB_SCHEMA_CHECKED:
            # Log database name for this worker
            db_name = settings.DATABASES["default"]["NAME"]
            logger.info("Using test database: %s", db_name)

            if not _database_has_tables():
                # No tables - load from SQL dump
                _load_test_db_sql()
            elif not _database_has_correct_schema():
                # Tables exist but schema is outdated (missing UUID columns)
                # This can happen with --reuse-db when schema has changed
                _load_test_db_sql()
            _DB_SCHEMA_CHECKED[worker_id] = True

        # For playwright tests, reload fixtures each time
        if "playwright" in str(request.node.fspath):
            _reload_fixtures()


@pytest.fixture(autouse=True)
def _ensure_association_skin(db: Any, _e2e_db_setup: Any) -> None:  # noqa: ARG001
    """Ensure default AssociationSkin and AssociationRole exist for tests.

    Depends on _e2e_db_setup to ensure database schema is loaded first.
    """
    if not AssociationSkin.objects.filter(pk=1).exists():
        AssociationSkin.objects.create(pk=1, name="LarpManager", domain="larpmanager.com")

    # Ensure AssociationRole with number=1 exists for all associations
    for association in Association.objects.all():
        if not AssociationRole.objects.filter(association=association, number=1).exists():
            AssociationRole.objects.create(association=association, number=1, name="Executive")
