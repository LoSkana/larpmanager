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

from argparse import ArgumentParser
from pathlib import Path

from django.core.management import BaseCommand
from django.utils import timezone

from larpmanager.cache.feature import get_event_features
from larpmanager.models.event import DevelopStatus, Run
from larpmanager.utils.base import prepare_run
from larpmanager.views.orga.event import _prepare_backup


class Command(BaseCommand):
    """Django management command."""

    help = "Backup events"

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add command line arguments for the backup command."""
        parser.add_argument("--path", type=str, required=True, help="Backup path")

    def handle(self, *args: tuple, **options: dict) -> None:  # noqa: ARG002
        """Database backup command with compression.

        Creates compressed backup files for all active runs (non-DONE, non-CANCELLED)
        in an organized directory structure by event ID and date.

        Args:
            *args: Variable length argument list from command line
            **options: Keyword arguments from command options, must include 'path' key
                      for the output directory path

        Returns:
            None

        Side Effects:
            - Creates directory structure: {path}/{event_id}/{year}/{month}/{day}/
            - Writes compressed ZIP backup files for each active run
            - Creates intermediate directories as needed

        """
        # Get current date for organizing backup files by date
        now_date = timezone.now().date()

        # Process all runs that are not done or cancelled
        for run in Run.objects.exclude(development__in=[DevelopStatus.DONE, DevelopStatus.CANC]):
            # Prepare context with run, event, and feature information
            context = {"run": run, "event": run.event, "features": get_event_features(run.event_id)}
            prepare_run(context)

            # Generate the backup content
            resp = _prepare_backup(context)

            # Build hierarchical path: base_path/event_id/year/month/day/run_name.zip
            path = Path(
                options["path"],
                str(run.event_id),
                str(now_date.year),
                str(now_date.month).zfill(2),
                str(now_date.day).zfill(2),
                f"{run!s}.zip",
            )

            # Create directory structure if it doesn't exist
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write the compressed backup file to disk
            path.write_bytes(resp.content)
