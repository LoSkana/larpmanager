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

from typing import TYPE_CHECKING, Any

from larpmanager.cache.config import get_configs
from larpmanager.models.association import Association
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Character, Faction, Plot
from larpmanager.utils.io.download.core import zip_exports
from larpmanager.utils.io.download.experience import (
    export_abilities,
    export_character_configs,
    export_criterions,
    export_deliveries,
)
from larpmanager.utils.io.download.forms import (
    export_character_form,
    export_registration_form,
    export_tickets,
)
from larpmanager.utils.io.download.writing import export_data

if TYPE_CHECKING:
    from django.http import HttpResponse


def export_event(context: Any) -> Any:
    """Export event configuration and features data.

    Args:
        context: Context dictionary containing event and run information

    Returns:
        list: List of tuples containing configuration and features export data

    """
    association = Association.objects.get(pk=context["event"].association_id)

    column_names = ["source", "name", "value"]
    configuration_values = []
    for source, element in [("event", context["event"]), ("run", context["run"]), ("association", association)]:
        for config_name, config_value in get_configs(element).items():
            configuration_values.append((source, config_name, config_value))
    export_data_rows = [("configuration", column_names, configuration_values)]

    column_names = ["source", "name", "slug"]
    feature_values = [
        (source, feature.name, feature.slug)
        for source, element in [("event", context["event"]), ("association", association)]
        for feature in element.features.all()
    ]
    export_data_rows.append(("features", column_names, feature_values))

    return export_data_rows


def prepare_backup(context: dict) -> HttpResponse:
    """Prepare comprehensive event data backup by exporting various components.

    Creates a ZIP file containing exported event data including registrations,
    characters, factions, plots, abilities, and quest builder components based
    on enabled features.

    Args:
        context: Context dictionary containing:
            - event: Event object to backup
            - features: Dict of enabled feature flags
            - Other context data required by export functions

    Returns:
        HttpResponse: ZIP file response containing all exported event data

    Raises:
        KeyError: If required context keys are missing
        Exception: If export or ZIP creation fails

    """
    export_files = []

    # Export core event data
    export_files.extend(export_event(context))

    # Export registration-related data
    export_files.extend(export_data(context, Registration))
    export_files.extend(export_registration_form(context))
    export_files.extend(export_tickets(context))

    # Export character data if feature is enabled
    if "character" in context["features"]:
        export_files.extend(export_data(context, Character))
        export_files.extend(export_character_form(context))
        export_files.extend(export_character_configs(context))

    # Export faction data if feature is enabled
    if "faction" in context["features"]:
        export_files.extend(export_data(context, Faction))

    # Export plot data if feature is enabled
    if "plot" in context["features"]:
        export_files.extend(export_data(context, Plot))

    # Export experience/abilities data if feature is enabled
    if "experience" in context["features"]:
        export_files.extend(export_abilities(context))
        export_files.extend(export_deliveries(context))
        # Exported regardless of the criterions config, so that backup and restore stay symmetric
        export_files.extend(export_criterions(context))

    # Export quest builder data if feature is enabled
    if "questbuilder" in context["features"]:
        export_files.extend(export_data(context, QuestType))
        export_files.extend(export_data(context, Quest))
        export_files.extend(export_data(context, Trait))

    # Create and return ZIP file with all exports
    return zip_exports(context, export_files, "backup")
