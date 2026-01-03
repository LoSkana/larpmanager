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
import sys

from django.core.management.base import CommandError


def check_virtualenv() -> None:
    """Ensure the command is running inside a virtual environment.

    This function checks if the current Python interpreter is running inside
    a virtual environment. If not, it raises an error unless running in a
    CI/production environment (GitHub Actions, Docker, or other CI systems).
    This helps prevent accidental execution of management commands outside
    of the proper development environment.

    Raises:
        CommandError: If not in a virtual environment and not in CI/production.

    """
    # Skip check if running in CI or production environment
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("DOCKER") == "true":
        return

    # Check if running in a virtual environment
    # Python sets sys.prefix != sys.base_prefix when in a virtualenv
    in_virtualenv = hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)

    if not in_virtualenv:
        msg = (
            "This command must be run inside a virtual environment.\n"
            "Please activate your virtual environment first:\n"
            "  source venv/bin/activate  # Linux/Mac\n"
            "  venv\\Scripts\\activate     # Windows"
        )
        raise CommandError(msg)


def check_branch() -> None:
    """Prevent dangerous operations from running on main branch.

    This function checks if the current git branch is 'main' and raises an error
    if so, unless running in a CI environment (GitHub Actions or other CI systems).
    This helps prevent accidental destructive operations on the main branch during
    local development.

    Raises:
        CommandError: If current git branch is 'main' and not in CI environment.

    """
    # Skip check if running in CI environment
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        return

    # Get current git branch name
    current_branch_name = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()  # noqa: S607

    # Raise error if on main branch
    if current_branch_name == "main":
        msg = "This command cannot be executed while on 'main'"
        raise CommandError(msg)
