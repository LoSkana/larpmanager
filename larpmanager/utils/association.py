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


def generate_association_encryption_key(instance):
    """Generate Fernet encryption key for new associations.

    Args:
        instance: Association instance being saved
    """
    if not instance.key:
        instance.key = Fernet.generate_key()


def auto_assign_association_permission_number(assoc_permission):
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


def prepare_association_skin_features(instance: Association) -> None:
    """Prepare association skin features by applying default values from the skin.

    Updates the association instance with default values from its associated skin
    if this is a new association or if the skin has changed. Only applies defaults
    for fields that are currently empty/None.

    Args:
        instance: Association instance to update with skin defaults

    Returns:
        None
    """
    # Early return if no skin is associated
    if not instance.skin_id:
        return

    # Check if this is a new association or if the skin has changed
    # Only proceed if skin is new or different from previous value
    if instance.pk:
        try:
            prev = Association.objects.get(pk=instance.pk)
        except ObjectDoesNotExist:
            return
        # Skip if skin hasn't changed
        if instance.skin_id == prev.skin_id:
            return

    # Retrieve the skin object, return early if not found
    try:
        skin = instance.skin
    except ObjectDoesNotExist:
        return

    # Mark instance for skin feature updates
    instance._update_skin_features = True

    # Apply skin defaults only to empty/unset fields
    # Set default nationality if not already specified
    if not instance.nationality:
        instance.nationality = skin.default_nation

    # Set default optional fields configuration if not set
    if not instance.optional_fields:
        instance.optional_fields = skin.default_optional_fields

    # Set default mandatory fields configuration if not set
    if not instance.mandatory_fields:
        instance.mandatory_fields = skin.default_mandatory_fields


def apply_skin_features_to_association(instance: Association) -> None:
    """Handle association skin feature setup after saving.

    This function updates an association's features to match its skin's default
    features when the association has been modified to use a new skin.

    Args:
        instance: Association instance that was saved. Must have a skin attribute
                 with default_features and a features manager.

    Note:
        The function only executes if the instance has the _update_skin_features
        attribute set, which indicates that skin features should be updated.
        The actual feature update is deferred until after the current database
        transaction commits to ensure data consistency.
    """
    # Check if the instance is marked for skin feature updates
    if not hasattr(instance, "_update_skin_features"):
        return

    # Define the feature update operation to run after transaction commit
    def update_features():
        # Replace all current features with the skin's default features
        instance.features.set(instance.skin.default_features.all())

    # Schedule the feature update to run after the current transaction commits
    transaction.on_commit(update_features)
