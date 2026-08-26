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

import logging
from typing import TYPE_CHECKING

from larpmanager.models.base import Feature
from larpmanager.models.event import EventConfig
from larpmanager.models.form import WritingQuestionType

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


def _get_feature_from_question_type(question_type: str) -> str | None:
    """Get feature slug required for a WritingQuestionType."""
    question_type_to_feature = {
        WritingQuestionType.FACTIONS: "faction",
        WritingQuestionType.MIRROR: "casting",
    }
    return question_type_to_feature.get(question_type)


def _get_config_from_question_type(question_type: str) -> str | None:
    """Get config name required for a WritingQuestionType."""
    question_type_to_config = {
        WritingQuestionType.TITLE: "character_title",
        WritingQuestionType.PROGRESS: "character_progress",
        WritingQuestionType.ASSIGNED: "character_assigned",
    }
    return question_type_to_config.get(question_type)


def _activate_features_from_columns(context: dict, column_names: list[str], writing_questions: QuerySet) -> None:
    """Activate features and configs automatically based on uploaded column names.

    Detects which features and configurations are required by the uploaded columns
    and activates them on the event if not already enabled.

    Args:
        context: Context dictionary with event information
        column_names: List of column names from uploaded CSV
        writing_questions: QuerySet of WritingQuestion objects for the event

    """
    # Build mapping of question names to question types
    question_name_to_type = {q["name"].lower(): q["typ"] for q in writing_questions}

    # Collect features and configs that need to be activated
    features_to_activate = set()
    configs_to_activate = set()

    # Check each column to see if it requires a feature or config
    for column_name in column_names:
        column_lower = column_name.lower()

        # Check if column matches a writing question
        if column_lower in question_name_to_type:
            question_type = question_name_to_type[column_lower]

            # Check if this question type requires a feature
            feature_slug = _get_feature_from_question_type(question_type)
            if feature_slug:
                features_to_activate.add(feature_slug)

            # Check if this question type requires a config
            config_name = _get_config_from_question_type(question_type)
            if config_name:
                configs_to_activate.add(config_name)

    activate_features(context, features_to_activate)

    activate_configs(context, configs_to_activate)


def activate_features(context: dict, features_to_activate: set) -> None:
    """Activate features if not already enabled."""
    if not features_to_activate:
        return

    # Get currently enabled features
    enabled_features = set(context["event"].features.values_list("slug", flat=True))

    # Find features that need to be activated
    features_to_add = features_to_activate - enabled_features

    if features_to_add:
        # Get Feature objects for the slugs that need to be added
        features = Feature.objects.filter(slug__in=features_to_add)

        # Add features to the event
        for feature in features:
            context["event"].features.add(feature)
            logger.info("Auto-activated feature '%s' for event %s", feature.slug, context["event"])


def activate_configs(context: dict, configs_to_activate: set) -> None:
    """Activate configs if not already enabled."""
    if not configs_to_activate:
        return

    # Get currently enabled configs
    enabled_configs = set(
        EventConfig.objects.filter(event=context["event"], name__in=configs_to_activate).values_list("name", flat=True)
    )

    # Find configs that need to be activated
    configs_to_add = configs_to_activate - enabled_configs

    if configs_to_add:
        # Create config entries with True value
        for config_name in configs_to_add:
            EventConfig.objects.create(event=context["event"], name=config_name, value="True")
            logger.info("Auto-activated config '%s' for event %s", config_name, context["event"])
