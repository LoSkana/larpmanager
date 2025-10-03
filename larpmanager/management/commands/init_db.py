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


from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from larpmanager.management.commands.utils import check_branch
from larpmanager.models.association import Association, AssociationSkin
from larpmanager.models.base import Feature


class Command(BaseCommand):
    help = "Init DB"

    def handle(self, *args, **options):
        check_branch()

        # Load fixtures
        call_command("import_features")
        call_command("loaddata", "test.yaml", verbosity=0)

        # Re-hash user passwords
        user_model = get_user_model()
        for user in user_model.objects.all():
            user.set_password("banana")
            user.is_active = True
            user.save()

        # Add exe_events to skin and assoc
        feature = Feature.objects.get(slug="exe_events")
        for skin in AssociationSkin.objects.all():
            skin.default_features.add(feature)
            skin.save()

        for assoc in Association.objects.all():
            assoc.features.add(feature)
            assoc.save()

        self.stdout.write("All done.")
