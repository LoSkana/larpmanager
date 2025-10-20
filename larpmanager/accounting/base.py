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
import json
import os

from cryptography.fernet import Fernet, InvalidToken

from larpmanager.cache.feature import get_event_features
from larpmanager.models.accounting import AccountingItemPayment, AccountingItemTransaction, Collection
from larpmanager.models.association import Association
from larpmanager.models.event import Event
from larpmanager.models.registration import Registration
from larpmanager.models.utils import get_payment_details_path
from larpmanager.utils.tasks import notify_admins


def is_reg_provisional(instance: Registration, event: Event | None = None, features: dict | None = None) -> bool:
    """Check if a registration is in provisional status.

    A registration is provisional if payment is enabled, has outstanding balance,
    and provisional payments are not disabled for the event.

    Args:
        instance: Registration instance to check
        event: Optional event instance, will be retrieved from instance.run.event if None
        features: Optional event features dict, will query if None

    Returns:
        bool: True if registration is provisional, False otherwise
    """
    # Get event from registration if not provided
    if not event:
        event = instance.run.event

    # Get event features if not provided
    if not features:
        features = get_event_features(event.id)

    # Check if provisional payments are disabled for this event
    if event.get_config("payment_no_provisional", False):
        return False

    # Check if payment feature is enabled and registration has outstanding balance
    if "payment" in features:
        # Registration is provisional if it has a positive total price but zero or negative payment
        if instance.tot_iscr > 0 >= instance.tot_payed:
            return True

    return False


def get_payment_details(assoc: Association) -> dict:
    """
    Decrypt and retrieve payment details for association.

    Reads encrypted payment details from file system, decrypts using association's
    encryption key, and returns the data as a dictionary. If decryption fails or
    file doesn't exist, returns empty dictionary.

    Args:
        assoc: Association instance containing encryption key for decryption

    Returns:
        dict: Decrypted payment details dictionary, empty dict if file missing
              or decryption fails

    Raises:
        None: All exceptions are caught and handled internally
    """
    # Initialize cipher with association's encryption key
    cipher = Fernet(assoc.key)

    # Get the path to encrypted payment details file
    encrypted_file_path = get_payment_details_path(assoc)

    # Return empty dict if encrypted file doesn't exist
    if not os.path.exists(encrypted_file_path):
        return {}

    # Read encrypted data from file
    with open(encrypted_file_path, "rb") as f:
        encrypted_data = f.read()

    # Attempt to decrypt and parse the data
    try:
        # Decrypt the binary data using Fernet cipher
        data_bytes = cipher.decrypt(encrypted_data)

        # Convert decrypted bytes to JSON dictionary
        decrypted_data = json.loads(data_bytes.decode("utf-8"))
        return decrypted_data
    except InvalidToken as err:
        # Notify administrators of decryption failure and return empty dict
        notify_admins(f"invalid token for {assoc.slug}", f"{err}")
        return {}


def handle_accounting_item_payment_pre_save(instance: AccountingItemPayment) -> None:
    """Update payment member and handle registration changes.

    This function is called before saving an AccountingItemPayment instance to:
    1. Ensure the payment has a member (defaults to registration member)
    2. Track if payment value changed for registration updates
    3. Update related transactions when registration changes

    Args:
        instance (AccountingItemPayment): The payment instance being saved

    Returns:
        None
    """
    # Set member from registration if not already set
    if not instance.member:
        instance.member = instance.reg.member

    # Skip further processing for new instances (no pk yet)
    if not instance.pk:
        return

    # Get previous state to detect changes
    prev = AccountingItemPayment.objects.get(pk=instance.pk)

    # Flag if value changed to trigger registration updates
    instance._update_reg = prev.value != instance.value

    # Update all related transactions if registration changed
    if prev.reg != instance.reg:
        for trans in AccountingItemTransaction.objects.filter(inv_id=instance.inv_id):
            trans.reg = instance.reg
            trans.save()


def handle_collection_pre_save(instance: Collection) -> None:
    """Generate unique codes and calculate collection totals.

    This function handles pre-save operations for Collection instances, including
    generating unique contribution and redemption codes for new instances, and
    calculating the total value from associated collection gifts for existing instances.

    Args:
        instance (Collection): The Collection instance being saved.

    Returns:
        None
    """
    # Handle new Collection instances - generate unique codes
    if not instance.pk:
        instance.unique_contribute_code()
        instance.unique_redeem_code()
        return

    # Reset total value for existing instances
    instance.total = 0

    # Calculate total from all associated collection gifts
    for el in instance.collection_gifts.all():
        instance.total += el.value


def handle_accounting_item_collection_post_save(instance):
    """Update collection total when items are added.

    Args:
        instance: AccountingItemCollection instance that was saved
    """
    if instance.collection:
        instance.collection.save()
