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

from typing import Any

from larpmanager.models.form import RegistrationQuestionApplicable
from larpmanager.utils.io.upload.experience import (
    abilities_load,
    ability_types_load,
    criterions_load,
    deliveries_load,
    modifiers_load,
    rules_load,
)
from larpmanager.utils.io.upload.forms import form_load
from larpmanager.utils.io.upload.registration import registrations_load
from larpmanager.utils.io.upload.tickets import tickets_load
from larpmanager.utils.io.upload.writing import writing_load


def go_upload(context: dict, upload_form_data: Any) -> Any:
    """Route uploaded files to appropriate processing functions.

    Args:
        context: Context dictionary with upload type and settings
        upload_form_data: Uploaded file form data

    Returns:
        list: Result messages from processing function

    """
    upload_type = context["typ"]

    dispatch = {
        "registration_form": lambda: form_load(
            context, upload_form_data, is_registration=True, applicable=RegistrationQuestionApplicable.REGISTRATION
        ),
        "matchmaker_form": lambda: form_load(
            context, upload_form_data, is_registration=True, applicable=RegistrationQuestionApplicable.MATCHMAKER
        ),
        "character_form": lambda: form_load(context, upload_form_data, is_registration=False),
        "registration": lambda: registrations_load(context, upload_form_data),
        "exp_abilitie": lambda: abilities_load(context, upload_form_data),
        "exp_ability_type": lambda: ability_types_load(context, upload_form_data),
        "exp_rule": lambda: rules_load(context, upload_form_data),
        "exp_modifier": lambda: modifiers_load(context, upload_form_data),
        "exp_criterion": lambda: criterions_load(context, upload_form_data),
        "exp_deliverie": lambda: deliveries_load(context, upload_form_data),
        "registration_ticket": lambda: tickets_load(context, upload_form_data),
    }
    handler = dispatch.get(upload_type)
    if handler:
        return handler()
    return writing_load(context, upload_form_data)
