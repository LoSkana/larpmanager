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

from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_event_config
from larpmanager.cache.experience import has_multiple_exp_systems
from larpmanager.cache.question import get_cached_registration_questions, get_cached_writing_questions
from larpmanager.models.form import QuestionApplicable


def _add_system_column(context: dict, columns: dict) -> None:
    """Add the experience system column, only when multiple systems are configured.

    With a single system the column is not offered, but it is still accepted on upload,
    so that backups taken from an event with several systems can be restored.
    """
    if has_multiple_exp_systems(context["event"].id):
        columns["system"] = _("Name of the experience system")
    else:
        context["extra_columns"] = ["system"]


_EXP_SYSTEM_TYPES = ("exp_abilitie", "exp_criterion", "exp_deliverie")


def _exp_column_names(context: dict) -> None:
    """Define column mappings for the experience types owning an experience system."""
    if context["typ"] == "exp_abilitie":
        columns = {
            "name": _("The name ability"),
            "cost": _("(Optional) Cost of the ability"),
            "typ": _("Ability type"),
            "descr": _("(Optional) The ability description"),
            "prerequisites": _("(Optional) Other abilities as prerequisite, comma-separated"),
            "requirements": _("(Optional) Character options as requirements, comma-separated"),
            "visible": _("(Optional) Whether the ability is visible to users: true or false"),
        }
        context["name"] = "Ability"
    elif context["typ"] == "exp_criterion":
        columns = {
            "number": _("The criterion's number (unique identifier)"),
            "name": _("The criterion's name"),
            "operation": _("Operation: ADD, SUB, MUL, DIV"),
            "amount": _("Transaction amount"),
            "prerequisites": _("(Optional) Prerequisite ability names, comma-separated"),
            "requirements": _("(Optional) Character options as requirements, comma-separated"),
            "factions": _("(Optional) Faction names, comma-separated"),
            "order": _("(Optional) Display order"),
        }
        context["name"] = "Criterion"
    else:
        columns = {
            "number": _("(Optional) The delivery's number, assigned automatically if missing or already taken"),
            "name": _("The delivery's name"),
            "amount": _("Amount of experience points delivered"),
            "characters": _("(Optional) Character names it was awarded to, comma-separated"),
            "order": _("(Optional) Display order"),
        }
        context["name"] = "Delivery"

    _add_system_column(context, columns)
    context["columns"] = [columns]


_EXP_SIMPLE_TYPES = ("exp_rule", "exp_modifier", "exp_ability_type")


def _exp_simple_column_names(context: dict) -> None:
    """Define column mappings for the experience types with a fixed, system-less column set."""
    if context["typ"] == "exp_rule":
        columns = {
            "number": _("The rule's number (unique identifier)"),
            "abilities": _("(Optional) Ability names, comma-separated - rule applies if character has any"),
            "field": _("The character field of computed type to update"),
            "operation": _("Operation: ADD, SUB, MUL, DIV"),
            "amount": _("Transaction amount"),
            "order": _("(Optional) Display order"),
        }
        context["name"] = "Rule"
    elif context["typ"] == "exp_modifier":
        columns = {
            "number": _("The modifier's number (unique identifier)"),
            "abilities": _("(Optional) Ability names, comma-separated"),
            "cost": _("(Optional) Cost (0 = auto assigned)"),
            "prerequisites": _("(Optional) Prerequisite ability names, comma-separated"),
            "requirements": _("(Optional) Character options as requirements, comma-separated"),
            "order": _("(Optional) Display order"),
        }
        context["name"] = "Modifier"
    else:
        columns = {"name": _("The ability type's name")}
        context["name"] = "Ability type"

    context["columns"] = [columns]


def _get_reg_type_names(questions: list) -> dict[str, str]:
    """Return mapping of special registration question type to question name."""
    special_types = {"ticket", "additional_tickets", "pay_what_you_want", "reg_quotas", "reg_surcharges"}
    return {q["typ"]: q["name"] for q in questions if q["typ"] in special_types}


def _get_column_names(context: dict) -> None:
    """Define column mappings and field types for different export contexts.

    Sets up comprehensive dictionaries mapping form fields to export columns
    based on context type (registration, tickets, abilities, etc.). This function
    generates the appropriate column headers and field definitions for CSV templates
    used in bulk upload/download operations.

    Args:
        context: Context dictionary containing export configuration including:
            - typ: Export type ('registration', 'registration_ticket', 'exp_abilitie',
                   'registration_form', 'character_form', or writing element types)
            - features: Set of available features for the export context
            - event: Event instance for question lookups (for registration types)

    Side effects:
        Modifies context in-place, adding:
        - columns: List of dicts with column names and descriptions
        - fields: Dict mapping field names to types (for registration type)
        - name: Name of the export type (for exp_abilitie type)
        - extra_columns: List of columns accepted on upload but not shown in the template

    """
    # Reset the columns accepted without being shown, so that they never survive another type
    context["extra_columns"] = []

    # Handle registration data export with participant, ticket, and question columns
    if context["typ"] == "registration":
        _registration_column_names(context)

    # Handle ticket tier definition export
    elif context["typ"] == "registration_ticket":
        context["columns"] = [
            {
                "name": _("The ticket's name"),
                "tier": _("The tier of the ticket"),
                "description": _("(Optional) The ticket's description"),
                "price": _("(Optional) The cost of the ticket"),
                "max_available": _("(Optional) Maximum number of spots available"),
            },
        ]

    # Handle ability/experience system export
    elif context["typ"] in _EXP_SYSTEM_TYPES:
        _exp_column_names(context)

    # Handle experience rule/modifier/ability type export
    elif context["typ"] in _EXP_SIMPLE_TYPES:
        _exp_simple_column_names(context)

    # Handle registration form (questions + options) export; matchmaker questions share
    # the same RegistrationQuestion fields, just scoped to a different "applicable" value
    elif context["typ"] in ("registration_form", "matchmaker_form"):
        # First dict: Question definitions with name, type, status
        # Second dict: Option definitions linked to questions
        context["columns"] = [
            {
                "name": _("The question name"),
                "typ": _("The question type, allowed values are")
                + ": 'single-choice', 'multi-choice', 'short-text', 'long-text', 'advanced'",
                "description": _("Optional - Extended description (displayed in small gray text)"),
                "status": _("The question status, allowed values are")
                + ": 'optional', 'mandatory', 'disabled', 'hidden'",
                "max_length": _(
                    "Optional - For text questions, maximum number of characters; For multiple options, maximum number of options (0 = no limit)",
                ),
            },
            {
                "question": _("The name of the question this option belongs to")
                + " <i>("
                + (_("If not found, the option will be skipped"))
                + ")</i>",
                "name": _("The name of the option"),
                "description": _("Optional - Additional information about the option, displayed below the question"),
                "price": _("Optional - Amount added to the registration fee if selected (0 = no extra cost)"),
                "max_available": _(
                    "Optional - Maximum number of times it can be selected across all registrations (0 = unlimited)",
                ),
            },
        ]

        # Matchmaker options carry no registration fee, drop the irrelevant column
        if context["typ"] == "matchmaker_form":
            del context["columns"][1]["price"]

    # Handle character/writing form (questions + options) export
    elif context["typ"] == "character_form":
        # Similar to registration form but with additional fields for writing elements
        context["columns"] = [
            {
                "name": _("The question name"),
                "typ": _("The question type, allowed values are")
                + ": 'single-choice', 'multi-choice', 'short-text', 'long-text', 'advanced', 'name', 'teaser', 'text'",
                "description": _("Optional - Extended description (displayed in small gray text)"),
                "status": _("The question status, allowed values are")
                + ": 'optional', 'mandatory', 'disabled', 'hidden'",
                "applicable": _("The writing element this question applies to, allowed values are")
                + ": 'character', 'plot', 'faction', 'quest', 'trait'",
                "visibility": _("The question visibility to participants, allowed values are")
                + ": 'searchable', 'public', 'private', 'hidden'",
                "max_length": _(
                    "Optional - For text questions, maximum number of characters; For multiple options, maximum number of options (0 = no limit)",
                ),
            },
            {
                "question": _("The name of the question this option belongs to")
                + " <i>("
                + (_("If not found, the option will be skipped"))
                + ")</i>",
                "name": _("The name of the option"),
                "description": _("Optional - Additional information about the option, displayed below the question"),
                "max_available": _("Optional - Maximum number of times it can be selected (0 = unlimited)"),
            },
        ]

        # Add requirements column if the feature is enabled
        if "wri_que_requirements" in context["features"]:
            context["columns"][1]["requirements"] = _("Optional - Other options as requirements, comma-separated")

    # Handle writing element types (character, plot, faction, quest, trait)
    else:
        _get_writing_names(context)


def _registration_column_names(context: dict) -> None:
    """Build field type mapping from registration questions for validation."""
    questions = get_cached_registration_questions(context["event"].id)
    context["fields"] = {question["name"]: question["typ"] for question in questions}

    # Build mapping of special question type to question name
    type_names = _get_reg_type_names(questions)

    # Build columns dict dynamically using question names where available
    ticket_key = type_names.get("ticket", "ticket")
    columns = {
        "email": _("The participant's email"),
        ticket_key: _("(Optional) The name of the ticket"),
    }

    if "additional_tickets" in type_names:
        columns[type_names["additional_tickets"]] = _("(Optional) The number of additional registrations")

    columns["characters"] = _("(Optional) The character names to assign to the player, separated by commas")

    if "pay_what_you_want" in context["features"] and "pay_what_you_want" in type_names:
        columns[type_names["pay_what_you_want"]] = _("(Optional) The amount of voluntary donation")

    if "surcharge" in context["features"] and "reg_surcharges" in type_names:
        columns[type_names["reg_surcharges"]] = _("(Optional) The surcharge amount")

    if "reg_quotas" in context["features"] and "reg_quotas" in type_names:
        columns[type_names["reg_quotas"]] = _("(Optional) The number of quotas")

    context["columns"] = [columns]


def _get_writing_names(context: dict) -> None:
    """Get writing field names and types for download context.

    Populates the provided context dictionary with writing field information
    including applicable question types, field definitions, column configurations,
    and allowed field names for data export functionality.

    Args:
        context: Context dictionary containing event, typ, and features data.
             Will be modified in-place with additional writing field information:
             - writing_typ: Applicable question type
             - fields: Dictionary mapping field names to their types
             - field_name: Name field identifier (if present)
             - columns: List of column configuration dictionaries
             - allowed: List of allowed field names for export

    Returns:
        None: Function modifies context dictionary in-place

    """
    # Determine the applicable writing question type based on context
    context["writing_typ"] = QuestionApplicable.get_applicable(context["typ"])
    context["fields"] = {}

    # Retrieve and process writing questions for the event
    writing_questions = get_cached_writing_questions(context["event"].id, context["writing_typ"])
    for question in writing_questions:
        context["fields"][question["name"]] = question["typ"]
        # Store the name field for special handling
        if question["typ"] == "name":
            context["field_name"] = question["name"]

    # Initialize base column configuration
    context["columns"] = [{}]

    # Configure character-specific fields and columns
    if context["writing_typ"] == QuestionApplicable.CHARACTER:
        context["fields"]["player"] = "skip"
        context["fields"]["email"] = "skip"

        # Add status field if approval feature is enabled
        if get_event_config(context["event"].id, "user_character_approval"):
            context["fields"]["status"] = "character_status"

        # Add assigned field if assigned feature is enabled
        if "assigned" in context["features"]:
            context["fields"]["assigned"] = "character_assigned"

        # Add relationship columns if feature is enabled
        if "relationships" in context["features"]:
            context["columns"].append(
                {
                    "source": _("First character in the relationship (origin)"),
                    "target": _("Second character in the relationship (destination)"),
                    "text": _("Description of the relationship from source to target"),
                },
            )

    # Configure plot-specific columns
    elif context["writing_typ"] == QuestionApplicable.PLOT:
        context["columns"].append(
            {
                "plot": _("Plot name"),
                "character": _("Character name"),
                "text": _("Description of the role of the character in the plot"),
            },
        )

    # Configure quest-specific columns
    elif context["writing_typ"] == QuestionApplicable.QUEST:
        context["columns"][0]["typ"] = _("Name of quest type")

    # Configure trait-specific columns
    elif context["writing_typ"] == QuestionApplicable.TRAIT:
        context["columns"][0]["quest"] = _("Name of quest")

    # Build the list of allowed field names for export validation
    context["allowed"] = list(context["columns"][0].keys())
    context["allowed"].extend(context["fields"].keys())
