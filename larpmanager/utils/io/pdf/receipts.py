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
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from django.conf import settings as conf_settings
from django.db import transaction

from larpmanager.cache.config import get_association_config
from larpmanager.models.accounting import AccountingItemDonation, AccountingItemMembership, AccountingItemPayment
from larpmanager.models.association import AssociationConfig
from larpmanager.utils.io.pdf.engine import xhtml_pdf


def generate_payment_receipt(accounting_item: Any) -> tuple[str, str]:
    """Generate a non-fiscal italian receipt PDF for the given accounting item.

    Atomically increments the per-year receipt counter, then renders the
    receipt template and writes the PDF to disk.

    Returns a tuple of (absolute filesystem path, user-facing attachment filename).
    The on-disk filename uses the internal cod; the attachment name uses a human-readable format.
    """
    year = accounting_item.created.year
    receipt_number_key = f"receipt_last_number_{year}"

    with transaction.atomic():
        config_obj, _ = AssociationConfig.objects.select_for_update().get_or_create(
            association_id=accounting_item.association_id,
            name=receipt_number_key,
            deleted=None,
            defaults={"value": "0"},
        )
        receipt_number = int(config_obj.value or 0) + 1
        config_obj.value = str(receipt_number)
        config_obj.save(update_fields=["value"])

    causal = ""
    if isinstance(accounting_item, AccountingItemMembership):
        causal = f"Quota associativa annuale anno {accounting_item.year}"
    elif isinstance(accounting_item, AccountingItemDonation):
        causal = "Erogazione liberale a sostegno delle attività istituzionali Art. 83 D.Lgs 117/17"
    elif isinstance(accounting_item, AccountingItemPayment):
        causal = f"Contributo per partecipazione all'attività '{accounting_item.registration.run}' riservato ai soci"

    invoice = accounting_item.inv
    association_id = accounting_item.association_id
    pdf_context = {
        "accounting_item": accounting_item,
        "member": accounting_item.member,
        "association": accounting_item.association,
        "receipt_number": receipt_number,
        "year": year,
        "method": invoice.method.name if invoice else None,
        "causal": causal,
        "receipt_legal_name": get_association_config(association_id, "receipt_legal_name"),
        "receipt_sede_legale": get_association_config(association_id, "receipt_sede_legale"),
        "receipt_codice_fiscale": get_association_config(association_id, "receipt_codice_fiscale"),
        "receipt_runts": get_association_config(association_id, "receipt_runts"),
        "is_donation": isinstance(accounting_item, AccountingItemDonation),
    }

    receipts_dir = Path(conf_settings.MEDIA_ROOT) / "receipts" / str(association_id)
    receipts_dir.mkdir(mode=0o770, parents=True, exist_ok=True)
    file_path = str(receipts_dir / f"{accounting_item.id}.pdf")

    xhtml_pdf(pdf_context, "pdf/receipt.html", file_path)

    assoc_name = re.sub(r"[^\w]", "_", str(accounting_item.association.name))
    file_name = f"{assoc_name}_Ricevuta_{receipt_number:05d}_{year}.pdf"

    return file_path, file_name
