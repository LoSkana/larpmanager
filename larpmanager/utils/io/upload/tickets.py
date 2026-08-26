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

from typing import TYPE_CHECKING

import pandas as pd

from larpmanager.models.member import LogOperationType
from larpmanager.models.registration import RegistrationTicket, TicketTier
from larpmanager.utils.edit.backend import save_log
from larpmanager.utils.io.upload.constants import MAX_CSV_ROWS
from larpmanager.utils.io.upload.csv_file import _get_file
from larpmanager.utils.io.upload.parsing import _get_row_name, _to_decimal, _to_int, invert_dict

if TYPE_CHECKING:
    from django.forms import Form


def tickets_load(context: dict, form: Form) -> list[str]:
    """Load tickets from uploaded file data."""
    # Extract and validate file data from form
    (uploaded_dataframe, log_messages) = _get_file(context, form.cleaned_data["first"], 0)

    # Process each row if data frame is valid
    if uploaded_dataframe is not None:
        if len(uploaded_dataframe) > MAX_CSV_ROWS:
            return [f"ERR - File too large: {len(uploaded_dataframe)} rows exceeds limit of {MAX_CSV_ROWS}"]
        # Convert dataframe to dictionary records and process each ticket
        for ticket_row in uploaded_dataframe.to_dict(orient="records"):
            log_messages.append(_ticket_load(context, ticket_row))
    return log_messages


def _ticket_load(context: dict, csv_row: dict) -> str:
    """Load ticket data from CSV row for bulk import.

    Creates or updates RegistrationTicket objects with proper validation,
    price handling, and relationship setup for event registration.

    Args:
        context: Context dictionary containing event and other bulk import data
        csv_row: Dictionary representing a single CSV row with ticket data

    Returns:
        str: Status message indicating success ("OK - Created/Updated") or error ("ERR - ...")

    Raises:
        ValueError: When numeric conversion fails for max_available or price fields

    """
    name, err = _get_row_name(csv_row)
    if err:
        return err

    # Get or create ticket object for the event
    (ticket, was_created) = RegistrationTicket.objects.get_or_create(event=context["event"], name=name)

    # Define field mappings for enumeration values
    field_value_mappings = {
        "tier": invert_dict(TicketTier.get_mapping()),
    }

    # Process each field in the CSV row
    for field_name, field_value in csv_row.items():
        # Skip empty values, NaN values, and the name field (already processed)
        if not field_value or pd.isna(field_value) or field_name in ["name"]:
            continue

        processed_value = field_value

        # Handle mapped enumeration fields
        if field_name in field_value_mappings:
            processed_value = processed_value.lower().strip()
            if processed_value not in field_value_mappings[field_name]:
                return f"ERR - unknow value {field_value} for field {field_name}"
            processed_value = field_value_mappings[field_name][processed_value]

        # Convert numeric fields to appropriate types
        if field_name == "max_available":
            processed_value = _to_int(field_value)
        if field_name == "price":
            processed_value = _to_decimal(field_value)

        # Set the field value on the ticket object
        setattr(ticket, field_name, processed_value)

    # Save the ticket and log the operation
    ticket.save()
    save_log(context, RegistrationTicket, ticket, operation_type=LogOperationType.UPLOAD)

    # Return appropriate success message
    return f"OK - Created {ticket}" if was_created else f"OK - Updated {ticket}"
