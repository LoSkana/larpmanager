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

from django.core.management import BaseCommand
from django.utils import timezone

from larpmanager.cache.feature import get_event_features
from larpmanager.models.event import DevelopStatus, Run
from larpmanager.utils.event import prepare_run
from larpmanager.views.orga.event import _prepare_backup


class Command(BaseCommand):
    help = "Backup events"

    def add_arguments(self, parser):
        parser.add_argument("--path", type=str, required=True, help="Backup path")

    def handle(self, *args, **options):
        now_date = timezone.now().date()
        for run in Run.objects.exclude(development__in=[DevelopStatus.DONE, DevelopStatus.CANC]):
            ctx = {"run": run, "event": run.event, "features": get_event_features(run.event_id)}
            prepare_run(ctx)
            resp = _prepare_backup(ctx)
            path = os.path.join(
                options["path"],
                str(run.event_id),
                str(now_date.year),
                str(now_date.month).zfill(2),
                str(now_date.day).zfill(2),
                f"{str(run)}.zip",
            )
            dir_path = os.path.dirname(path)
            os.makedirs(dir_path, exist_ok=True)
            with open(path, "wb") as f:
                f.write(resp.content)
