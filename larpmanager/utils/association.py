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
from cryptography.fernet import Fernet
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Max

from larpmanager.models.access import AssocPermission
from larpmanager.models.association import Association


def handle_association_fernet_key_generation(instance):
    """Generate Fernet encryption key for new associations.

    Args:
        instance: Association instance being saved
    """
    if not instance.key:
        instance.key = Fernet.generate_key()


def assign_assoc_permission_number(assoc_permission):
    """Assign number to association permission if not set.

    Args:
        assoc_permission: AssocPermission instance to assign number to
    """
    if not assoc_permission.number:
        n = AssocPermission.objects.filter(feature__module=assoc_permission.feature.module).aggregate(Max("number"))[
            "number__max"
        ]
        if not n:
            n = 1
        assoc_permission.number = n + 10


def handle_association_skin_features_pre_save(instance):
    if not instance.skin_id:
        return

    # execute if new association, or if changed skin
    if instance.pk:
        try:
            prev = Association.objects.get(pk=instance.pk)
        except ObjectDoesNotExist:
            return
        if instance.skin_id == prev.skin_id:
            return

    try:
        skin = instance.skin
    except ObjectDoesNotExist:
        return

    instance._update_skin_features = True
    if not instance.nationality:
        instance.nationality = skin.default_nation

    if not instance.optional_fields:
        instance.optional_fields = skin.default_optional_fields

    if not instance.mandatory_fields:
        instance.mandatory_fields = skin.default_mandatory_fields


def handle_association_skin_features_post_save(instance):
    """Handle association skin feature setup after saving.

    Args:
        instance: Association instance that was saved
    """
    if not hasattr(instance, "_update_skin_features"):
        return

    def update_features():
        instance.features.set(instance.skin.default_features.all())

    transaction.on_commit(update_features)
