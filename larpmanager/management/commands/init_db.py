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

    def handle(self, *args: tuple, **options: dict) -> None:  # noqa: ARG002
        """Handle the reset command to load test fixtures and configure test environment.

        This command resets the database with test data, including:
        - Loading feature fixtures and test data
        - Resetting all user passwords to 'banana' and activating accounts
        - Adding exe_events feature to all association skins and associations

        Args:
            *args: Positional arguments passed to the command
            **options: Keyword arguments passed to the command

        Returns:
            None

        """
        # Ensure we're not running on main branch
        check_branch()

        # Load fixtures - import features first, then test data
        call_command("import_features")
        call_command("loaddata", "test.yaml", verbosity=0)

        # Re-hash user passwords to consistent test password
        # and ensure all users are active for testing
        user_model = get_user_model()
        for user in user_model.objects.all():
            user.set_password("banana")
            user.is_active = True
            user.save()

        # Add exe_events feature to all association skins
        # This enables event management functionality by default
        feature = Feature.objects.get(slug="exe_events")
        for skin in AssociationSkin.objects.all():
            skin.default_features.add(feature)
            skin.save()

        # Add exe_events feature to all existing associations
        # Ensures all test organizations have event management enabled
        for association in Association.objects.all():
            association.features.add(feature)
            association.save()

        self.stdout.write("All done.")
