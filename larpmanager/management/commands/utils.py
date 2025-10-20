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

from django.core.management.base import CommandError


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
    branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()

    # Raise error if on main branch
    if branch == "main":
        raise CommandError("This command cannot be executed while on 'main'")
