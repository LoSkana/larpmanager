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
from larpmanager.models.accounting import AccountingItemPayment, AccountingItemTransaction
from larpmanager.models.utils import get_payment_details_path
from larpmanager.utils.tasks import notify_admins


def is_reg_provisional(instance, features=None):
    """Check if a registration is in provisional status.

    A registration is provisional if payment is enabled, has outstanding balance,
    and provisional payments are not disabled for the event.

    Args:
        instance: Registration instance to check
        features: Optional event features dict, will query if None

    Returns:
        bool: True if registration is provisional, False otherwise
    """
    if not features:
        features = get_event_features(instance.run.event_id)

    # check if provisional disabled
    if instance.run.event.get_config("payment_no_provisional", False):
        return False

    # check if the registration has a total price higher than 0, and lower than the amount payed
    if "payment" in features:
        if instance.tot_iscr > 0 >= instance.tot_payed:
            return True

    return False


def get_payment_details(assoc):
    """
    Decrypt and retrieve payment details for association.

    Args:
        assoc: Association instance with encryption key

    Returns:
        dict: Decrypted payment details dictionary
    """
    cipher = Fernet(assoc.key)
    encrypted_file_path = get_payment_details_path(assoc)
    if not os.path.exists(encrypted_file_path):
        return {}
    with open(encrypted_file_path, "rb") as f:
        encrypted_data = f.read()
    try:
        data_bytes = cipher.decrypt(encrypted_data)
        decrypted_data = json.loads(data_bytes.decode("utf-8"))
        return decrypted_data
    except InvalidToken as err:
        notify_admins(f"invalid token for {assoc.slug}", f"{err}")
        return {}


def handle_accounting_item_payment_pre_save(instance):
    """Update payment member and handle registration changes.

    Args:
        instance: AccountingItemPayment instance being saved
    """
    if not instance.member:
        instance.member = instance.reg.member

    if not instance.pk:
        return

    prev = AccountingItemPayment.objects.get(pk=instance.pk)
    instance._update_reg = prev.value != instance.value

    if prev.reg != instance.reg:
        for trans in AccountingItemTransaction.objects.filter(inv_id=instance.inv_id):
            trans.reg = instance.reg
            trans.save()


def handle_collection_pre_save(instance):
    """Generate unique codes and calculate collection totals.

    Args:
        instance: Collection instance being saved
    """
    if not instance.pk:
        instance.unique_contribute_code()
        instance.unique_redeem_code()
        return
    instance.total = 0
    for el in instance.collection_gifts.all():
        instance.total += el.value


def handle_accounting_item_collection_post_save(instance):
    """Update collection total when items are added.

    Args:
        instance: AccountingItemCollection instance that was saved
    """
    if instance.collection:
        instance.collection.save()
