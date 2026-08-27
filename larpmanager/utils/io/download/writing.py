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

from bs4 import BeautifulSoup
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.accounting import get_registration_accounting_cache
from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.config import get_event_config
from larpmanager.cache.question import get_cached_registration_questions, get_cached_writing_questions
from larpmanager.models.form import (
    QuestionApplicable,
    RegistrationAnswer,
    RegistrationChoice,
    WritingAnswer,
    WritingChoice,
)
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character, Plot, PlotCharacterRel, Relationship, get_event_class_parent
from larpmanager.utils.core.common import check_field
from larpmanager.utils.edit.backend import _get_values_mapping
from larpmanager.utils.io.download.columns import _get_reg_type_names

if TYPE_CHECKING:
    from django.db.models import QuerySet


def export_data(context: dict, model_type: type, *, member_cover: bool = False) -> list[tuple[str, list, list]]:
    """Export model data to structured format with questions and answers.

    Processes data export for various model types with question handling,
    answer processing, and cover image support for members when specified.

    Args:
        context: Context dictionary containing export configuration and features
        model_type: Model class to export data from
        member_cover: Whether to include member cover images in export

    Returns:
        List of tuples containing (model_name, headers, data_rows) for export

    """
    # Initialize query and prepare basic export data
    queryset = model_type.objects.all()
    get_event_cache_all(context)
    model_name = model_type.__name__.lower()

    # Apply filters and prepare query based on model type
    queryset = _download_prepare(context, model_name, queryset, model_type)
    _prepare_export(context, model_name, queryset)

    # Process each record to extract data rows
    headers = None
    data_rows = []
    for record in queryset:
        # Handle applicable records or registration-specific processing
        if context["applicable"] or model_name == "registration":
            row_data, headers = _get_applicable_row(context, record, model_name, member_cover=member_cover)
        else:
            row_data, headers = _get_standard_row(context, record)
        data_rows.append(row_data)

    # Sort data by appropriate column (adjust for member cover offset)
    sort_column_index = 0
    if member_cover:
        sort_column_index = 1
    data_rows = sorted(data_rows, key=lambda x: x[sort_column_index])

    # Build base export structure
    exports = [(model_name, headers, data_rows)]

    # Add plot relationships if exporting plot data
    if model_name == "plot":
        exports.extend(export_plot_rels(context))

    # Add character relationships if feature is enabled
    if model_name == "character" and "relationships" in context["features"]:
        exports.extend(export_relationships(context))

    return exports


def export_plot_rels(context: Any) -> Any:
    """Export plot-character relationships.

    Args:
        context: Context dictionary with event data

    Returns:
        list: Export tuple with plot relationship data

    """
    column_keys = ["plot", "character", "text"]

    event_id = get_event_class_parent(context["event"].id, Plot, context=context)

    relationship_values = [
        [
            plot_character_relationship.plot.name,
            plot_character_relationship.character.name,
            plot_character_relationship.text,
        ]
        for plot_character_relationship in PlotCharacterRel.objects.filter(plot__event_id=event_id)
        .prefetch_related("plot", "character")
        .order_by("order")
    ]

    return [("plot_rels", column_keys, relationship_values)]


def export_relationships(context: Any) -> Any:
    """Export character relationships.

    Args:
        context: Context dictionary with event data

    Returns:
        list: Export tuple with relationship data

    """
    column_headers = ["source", "target", "text"]

    event_id = get_event_class_parent(context["event"].id, Character, context=context)

    relationship_rows = [
        [relationship.source.name, relationship.target.name, relationship.text]
        for relationship in Relationship.objects.filter(source__event_id=event_id).prefetch_related("source", "target")
    ]

    return [("relationships", column_headers, relationship_rows)]


def _prepare_export(context: dict, model: str, query: QuerySet) -> None:
    """Prepare data for export operations.

    Processes questions, choices, and answers for data export functionality,
    organizing the data by question type and element relationships for
    registration and character model exports.

    Args:
        context: Context dictionary containing export configuration and data.
            Will be modified in-place to include prepared export data structures.
        model: String identifier for the Django model to export data from.
            Expected values: "registration", "character", or other model names.
        query: QuerySet containing the filtered data to export.

    Returns:
        None: Function modifies context in-place, adding the following keys:
            - applicable: Question applicability filter
            - answers: Dictionary mapping question_id -> element_id -> answer_text
            - choices: Dictionary mapping question_id -> element_id -> [choice_names]
            - questions: List of applicable questions for the model
            - assignments: (character model only) character_id -> member mapping

    """
    # Determine applicable question types for the model
    # noinspection PyProtectedMember
    applicable_questions = QuestionApplicable.get_applicable(model)

    # Initialize data structures for export organization
    choices_by_question_and_element: dict[int, dict[int, list[str]]] = {}
    answers_by_question_and_element: dict[int, dict[int, str]] = {}
    applicable_question_list: list = []

    # Process questions, choices, and answers if applicable or for registration model
    if applicable_questions or model == "registration":
        # Determine model-specific classes and field names
        is_registration_model = model == "registration"
        choices_class = RegistrationChoice if is_registration_model else WritingChoice
        answers_class = RegistrationAnswer if is_registration_model else WritingAnswer
        reference_field_name = "registration_id" if is_registration_model else "element_id"

        # Extract element IDs from query for filtering related objects
        element_ids = {element.id for element in query}

        # Get applicable questions for the event
        if is_registration_model:
            applicable_question_list = get_cached_registration_questions(context["event"].id)
        else:
            applicable_question_list = get_cached_writing_questions(context["event"].id, applicable_questions)

        # Extract question IDs for efficient database filtering
        question_ids = {question["id"] for question in applicable_question_list}
        filter_kwargs = {"question_id__in": question_ids, f"{reference_field_name}__in": element_ids}

        # Process multiple choice answers and organize by question and element
        question_choices = choices_class.objects.filter(**filter_kwargs)
        for choice in question_choices.select_related("option"):
            element_id = getattr(choice, reference_field_name)
            # Initialize nested dictionaries as needed
            if choice.question_id not in choices_by_question_and_element:
                choices_by_question_and_element[choice.question_id] = {}
            if element_id not in choices_by_question_and_element[choice.question_id]:
                choices_by_question_and_element[choice.question_id][element_id] = []
            choices_by_question_and_element[choice.question_id][element_id].append(choice.option.name)

        # Process text answers and organize by question and element
        question_answers = answers_class.objects.filter(**filter_kwargs)
        for answer in question_answers:
            element_id = getattr(answer, reference_field_name)
            # Initialize nested dictionary as needed
            if answer.question_id not in answers_by_question_and_element:
                answers_by_question_and_element[answer.question_id] = {}
            answers_by_question_and_element[answer.question_id][element_id] = answer.text

    # Special handling for character model: build character-to-member assignments
    if model == "character":
        context["assignments"] = {}
        for relation in RegistrationCharacterRel.objects.filter(
            registration__run=context["run"],
        ).select_related("registration", "registration__member"):
            context["assignments"][relation.character_id] = relation.registration.member

    # Update context with all prepared export data
    context["applicable"] = applicable_questions
    context["answers"] = answers_by_question_and_element
    context["choices"] = choices_by_question_and_element
    context["questions"] = applicable_question_list


def _get_applicable_row(context: dict, element: object, model: str, *, member_cover: bool = False) -> tuple[list, list]:
    """Build row data for export with question answers and element information.

    This function constructs export data by combining element metadata with
    question-specific answers and choices based on the applicable context type.

    Args:
        context: Context dictionary containing:
            - questions: List of question objects
            - answers: Dict mapping question IDs to element answers
            - choices: Dict mapping question IDs to element choice selections
            - applicable: QuestionApplicable enum value
        element: Element instance (registration, character, etc.) to extract data from
        model: Model type identifier ('registration', 'character', etc.)
        member_cover: Whether to include member profile images in export, by default False

    Returns:
        tuple[list, list]: Tuple containing (values_list, headers_list) for the export row

    """
    row_values = []
    column_headers = []

    # Build base headers and values for the element
    _row_header(context, element, column_headers, model, row_values, member_cover=member_cover)

    # Add context-specific fields based on applicable type
    if context["applicable"] == QuestionApplicable.QUEST:
        column_headers.append("typ")
        row_values.append(element.typ.name if element.typ else "")
    elif context["applicable"] == QuestionApplicable.TRAIT:
        column_headers.append("quest")
        row_values.append(element.quest.name if element.quest else "")

    # Extract answers and choices from context
    question_answers = context["answers"]
    question_choices = context["choices"]

    # Registration question types that are already handled
    handled_reg_types = {"ticket", "additional_tickets", "pay_what_you_want", "reg_quotas", "reg_surcharges"}

    # Process each question and extract corresponding values
    for question in context["questions"]:
        if model == "registration" and question["typ"] in handled_reg_types:
            continue
        column_headers.append(question["name"])

        # Get element-specific value mapping for special question types
        question_type_mapping = _get_values_mapping(element)
        cell_value = ""

        # Handle mapped question types (direct element attributes)
        if question["typ"] in question_type_mapping:
            cell_value = question_type_mapping[question["typ"]]()
        # Handle text-based question types (paragraph, text, email, computed)
        elif question["typ"] in {"p", "t", "e", "c"}:
            if element.id in question_answers.get(question["id"], {}):
                cell_value = question_answers[question["id"]][element.id]
        # Handle choice-based question types (single, multiple)
        elif (
            question["typ"] in {"s", "m"}
            and question["id"] in question_choices
            and element.id in question_choices[question["id"]]
        ):
            cell_value = ", ".join(question_choices[question["id"]][element.id])

        # Clean value for export format (remove tabs, convert newlines)
        cell_value = cell_value.replace("\t", "").replace("\n", "<br />")
        row_values.append(cell_value)

    return row_values, column_headers


def _row_header(  # noqa: C901, PLR0912
    context: dict,
    el: object,
    header_columns: list,
    model: str,
    row_values: list,
    *,
    member_cover: bool,
) -> None:
    """Build header row data with member information and basic element data.

    Constructs header rows for export tables by extracting member data, profile images,
    and model-specific information like ticket details for registrations.

    Args:
        context: Context dictionary containing assignments data and other export context
        el: Element instance to process (registration or character object)
        header_columns: List to append header column names to
        member_cover: Whether to include member profile image column
        model: Model type identifier ('registration' or 'character')
        row_values: List to append corresponding values to

    Returns:
        None: Function modifies header_columns and row_values lists in place

    """
    # Extract member based on model type
    member = None
    if model == "registration":
        member = el.member
    # Check if character has assignment in context
    elif model == "character" and el.id in context["assignments"]:
        member = context["assignments"][el.id]

    # Add profile image column if requested
    if member_cover:
        header_columns.append("")
        profile_url = ""
        if member and member.profile:
            profile_url = member.profile_thumb.url
        row_values.append(profile_url)

    # Add character number column if writing_number config is enabled
    if model == "character" and get_event_config(context["event"].id, "writing_number"):
        header_columns.append("number")
        row_values.append(el.number)

    # Add participant and email columns for registrations
    if model in ["registration"]:
        # Add participant display name
        header_columns.append("Participant")
        display_name = ""
        if member:
            display_name = member.display_real()
        row_values.append(display_name)

        # Add participant email
        header_columns.append("Email")
        email_address = ""
        if member:
            email_address = member.email
        row_values.append(email_address)

    # Add player email column for characters if character creation is active
    elif model == "character" and "user_character" in context.get("features", {}):
        header_columns.append("player")
        player_email = ""
        if member:
            player_email = member.email
        row_values.append(player_email)

    # Add status column if character approval is enabled
    if model == "character" and context.get("user_character_approval", False):
        header_columns.append("status")
        row_values.append(el.status if hasattr(el, "status") else "")

    # Add assigned orga email if assigned feature is enabled
    if model == "character" and "assigned" in context.get("features", {}):
        header_columns.append("assigned")
        row_values.append(el.assigned.user.email if el.assigned else "")

    # Add registration-specific columns
    if model == "registration":
        type_names = _get_reg_type_names(context.get("questions", []))

        # Add ticket information
        row_values.append(el.ticket.name if el.ticket is not None else "")
        header_columns.append(type_names.get("ticket", _("Ticket")))

        # Process additional registration headers
        _header_regs(context, el, header_columns, row_values, type_names)


def _expand_val(values: list, element: object, field_name: str) -> None:
    """Append field value from element to list, or empty string if not found."""
    # Check if element has the specified field attribute
    if hasattr(element, field_name):
        value = getattr(element, field_name)
        # Append value if it exists (truthy)
        if value:
            values.append(value)
            return

    # Append empty string if field doesn't exist or value is falsy
    values.append("")


def _header_regs(
    context: dict,
    registration: object,
    column_headers: list,
    column_values: list,
    type_names: dict | None = None,
) -> None:
    """Generate header row data for registration download with feature-based columns.

    This function dynamically builds column headers and values for registration data
    export based on enabled features in the context. It appends data to the provided
    key and val lists in-place.

    Args:
        context: Context dictionary containing features configuration and feature names
        registration: Registration element object with registration data and relationships
        column_headers: List to append column headers to (modified in-place)
        column_values: List to append column values to (modified in-place)
        type_names: Mapping of special question type to question name (modified in-place)

    Returns:
        None: Function modifies key and val lists in-place

    """
    if type_names is None:
        type_names = {}

    # Add additional registrations if question exists
    if "additional_tickets" in type_names:
        column_headers.append(type_names.get("additional_tickets", _("Additional tickets")))
        column_values.append(registration.additionals)

    # Handle character-related data if character feature is enabled
    if "character" in context["features"]:
        column_headers.append(_("Characters"))
        column_values.append(", ".join([row.character.name for row in registration.rcrs.all()]))

    # Add pay-what-you-want pricing if enabled
    if "pay_what_you_want" in context["features"]:
        column_values.append(registration.pay_what)
        column_headers.append(type_names.get("pay_what_you_want", "PWYW"))

    # Include surcharge information if feature is active
    if "surcharge" in context["features"]:
        column_values.append(registration.surcharge)
        column_headers.append(type_names.get("reg_surcharges", _("Surcharge")))

    # Add quota information for installment or quota-based registrations
    if "reg_quotas" in context["features"] or "reg_installments" in context["features"]:
        column_values.append(registration.quota)
        column_headers.append(type_names.get("reg_quotas", _("Next quota")))

    # Core payment and deadline information (always included)
    column_values.append(registration.deadline)
    column_headers.append(_("Deadline"))

    column_values.append(registration.remaining)
    column_headers.append(_("Owing"))

    column_values.append(registration.tot_payed)
    column_headers.append(_("Payed"))

    column_values.append(registration.tot_iscr)
    column_headers.append(_("Total"))

    # VAT-related pricing breakdown if VAT feature is enabled
    if "vat" in context["features"]:
        column_values.append(registration.ticket_price)
        column_headers.append(_("Ticket price"))

        column_values.append(registration.options_price)
        column_headers.append(_("Options price"))

    # Token and credit payment methods if tokens or credits feature is enabled
    _expand_val(column_values, registration, "pay_a")
    column_headers.append(_("Money"))

    if "tokens" in context["features"]:
        _expand_val(column_values, registration, "pay_b")
        column_headers.append(context.get("credits_name", _("Credits")))

    if "tokens" in context["features"]:
        _expand_val(column_values, registration, "pay_c")
        column_headers.append(context.get("tokens_name", _("Tokens")))


def _get_standard_row(context: dict, element: object) -> tuple[list, list]:
    """Extract values and keys from element's complete data."""
    values = []
    keys = []

    # Process each key-value pair from element's complete data
    for field_key, field_value in element.show_complete().items():
        _writing_field(context, field_key, keys, field_value, values)

    return values, keys


def _writing_field(context: dict, field_name: str, field_names: list, field_value: any, field_values: list) -> None:
    """Process writing field for export with feature-based filtering.

    Filters and formats writing fields based on enabled features,
    handling special cases like factions and custom fields. Modifies
    the key and val lists in-place by appending processed field data.

    Args:
        context: Context dictionary containing features and factions data
        field_name: Field name/key to process
        field_names: List to append field names to (modified in-place)
        field_value: Field value to process
        field_values: List to append processed values to (modified in-place)

    Returns:
        None: Function modifies key and val lists in-place

    """
    processed_value = field_value

    # Define fields that should be skipped from export
    skip_fields = [
        "id",
        "show",
        "owner_uuid",
        "owner",
        "player",
        "player_full",
        "player_uuid",
        "first_aid",
        "player_prof",
        "profile",
        "cover",
        "thumb",
    ]

    # Skip processing if field is in exclusion list
    if field_name in skip_fields:
        return

    # Skip custom fields (prefixed with "custom_")
    if field_name.startswith("custom_"):
        return

    # Check if title field is enabled in features
    if field_name in ["title"] and field_name not in context["features"]:
        return

    # Handle faction field processing
    if field_name == "factions":
        # Skip if faction feature is not enabled
        if "faction" not in context["features"]:
            return

        # Convert faction IDs to names and join with commas
        faction_names = [
            context["factions"][int(faction_id)]["name"]
            for faction_id in field_value
            if int(faction_id) in context["factions"]
        ]
        processed_value = " | ".join(faction_names)

    # Clean the processed value and append to output lists
    cleaned_value = _clean(processed_value)
    field_values.append(cleaned_value)
    field_names.append(field_name)


def _clean(html_content: str | None) -> str:
    """Strip HTML tags and normalize whitespace."""
    soup = BeautifulSoup(str(html_content), features="lxml")
    return soup.get_text("\n").replace("\n", " ")


def _download_prepare(context: dict, model_name: str, queryset: QuerySet[Any], model_type: type) -> QuerySet[Any]:
    """Prepare and filter query for CSV download based on type and context.

    Processes a queryset by applying appropriate filters based on the model type
    and context, optimizes database queries with prefetch/select operations,
    and enriches registration data with accounting information.

    Args:
        context: Context dictionary containing event/run information and request data
        model_name: Name/type of the model being downloaded (e.g., 'character', 'registration')
        queryset: Initial Django queryset to filter and optimize
        model_type: Type configuration dictionary containing filtering rules and field specifications

    Returns:
        Filtered and optimized Django queryset ready for CSV export with all
        necessary related data loaded and additional computed fields attached

    """
    # Apply event-based filtering if specified in type configuration
    if check_field(model_type, "event"):
        queryset = queryset.filter(event=get_event_class_parent(context["event"].id, model_name, context=context))

    # Apply run-based filtering if specified in type configuration
    elif check_field(model_type, "run"):
        queryset = queryset.filter(run=context["run"])

    # Apply number-based ordering if specified in type configuration
    if check_field(model_type, "number"):
        queryset = queryset.order_by("number")

    # Optimize character queries by prefetching factions and selecting player data
    if model_name == "character":
        queryset = queryset.prefetch_related("factions_list").select_related("player", "assigned")

    # Handle registration-specific filtering and data enrichment
    if model_name == "registration":
        # Filter out cancelled and pending registrations and optimize ticket queries
        queryset = queryset.filter(cancellation_date__isnull=True, pending=False).select_related("ticket")

        # Get accounting data for all registrations in the queryset
        accounting_data = _orga_registrations_acc(context, queryset)

        # Attach accounting information as dynamic attributes to each registration
        for registration in queryset:
            uuid_str = str(registration.uuid)
            if uuid_str not in accounting_data:
                continue
            for key, value in accounting_data[uuid_str].items():
                setattr(registration, key, value)

    return queryset


def _orga_registrations_acc(context: Any, registrations: Any = None) -> Any:
    """Process registration accounting data for organizer reports.

    Args:
        context: Context dictionary with event and feature information
        registrations: Optional list of registrations to process (defaults to all active registrations)

    Returns:
        dict: Processed accounting data keyed by registration ID

    """
    # Use cached accounting data for efficiency
    cached_data = get_registration_accounting_cache(context["run"].id, context["run"].event_id)

    # If specific registrations are requested, filter the cached data
    if registrations:
        result = {}
        for registration in registrations:
            # Use string UUID for consistency with cache keys
            uuid_str = str(registration.uuid)
            if uuid_str in cached_data:
                result[uuid_str] = cached_data[uuid_str]
        return result

    return cached_data
