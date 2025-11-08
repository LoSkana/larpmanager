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

import csv
import io
import zipfile

import pandas as pd
from bs4 import BeautifulSoup
from django.db.models import F, QuerySet
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.registration import round_to_nearest_cent
from larpmanager.cache.accounting import get_registration_accounting_cache
from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.config import get_configs
from larpmanager.models.association import Association
from larpmanager.models.experience import AbilityPx
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    QuestionVisibility,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    get_ordered_registration_questions,
)
from larpmanager.models.registration import RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, Plot, PlotCharacterRel, Relationship
from larpmanager.utils.common import check_field
from larpmanager.utils.edit import _get_values_mapping


def _temp_csv_file(column_headers, data_rows):
    """Create CSV content from keys and values.

    Args:
        column_headers: Column headers
        data_rows: Data rows

    Returns:
        str: CSV formatted string

    """
    df = pd.DataFrame(data_rows, columns=column_headers)
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer.getvalue()


def zip_exports(context, exports, filename):
    """Create ZIP file containing multiple CSV exports.

    Args:
        context: Context dictionary with run information
        exports: List of (name, keys, values) tuples
        filename: Base filename for ZIP

    Returns:
        HttpResponse: ZIP file download response

    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for export_name, csv_headers, csv_rows in exports:
            if not csv_headers or not csv_rows:
                continue
            zip_file.writestr(f"{export_name}.csv", _temp_csv_file(csv_headers, csv_rows))
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type="application/zip")
    response["Content-Disposition"] = f"attachment; filename={str(context['run'])} - {filename}.zip"
    return response


def download(context, typ, nm):
    """Generate downloadable ZIP export for model type.

    Args:
        context: Context dictionary with event data
        typ: Model class to export
        nm: Name prefix for file

    Returns:
        HttpResponse: ZIP download response

    """
    exports = export_data(context, typ)
    return zip_exports(context, exports, nm.capitalize())


def export_data(context: dict, model_type: type, member_cover: bool = False) -> list[tuple[str, list, list]]:
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
            row_data, headers = _get_applicable_row(context, record, model_name, member_cover)
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
    if model_name == "character":
        if "relationships" in context["features"]:
            exports.extend(export_relationships(context))

    return exports


def export_plot_rels(context):
    """Export plot-character relationships.

    Args:
        context: Context dictionary with event data

    Returns:
        list: Export tuple with plot relationship data

    """
    column_keys = ["plot", "character", "text"]
    relationship_values = []

    event_id = context["event"].get_class_parent(Plot)

    for plot_character_relationship in (
        PlotCharacterRel.objects.filter(plot__event_id=event_id).prefetch_related("plot", "character").order_by("order")
    ):
        relationship_values.append(
            [
                plot_character_relationship.plot.name,
                plot_character_relationship.character.name,
                plot_character_relationship.text,
            ]
        )

    return [("plot_rels", column_keys, relationship_values)]


def export_relationships(context):
    """Export character relationships.

    Args:
        context: Context dictionary with event data

    Returns:
        list: Export tuple with relationship data

    """
    column_headers = ["source", "target", "text"]
    relationship_rows = []

    event_id = context["event"].get_class_parent(Character)

    for relationship in Relationship.objects.filter(source__event_id=event_id).prefetch_related("source", "target"):
        relationship_rows.append([relationship.source.name, relationship.target.name, relationship.text])

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
        question_class = RegistrationQuestion if is_registration_model else WritingQuestion
        choices_class = RegistrationChoice if is_registration_model else WritingChoice
        answers_class = RegistrationAnswer if is_registration_model else WritingAnswer
        reference_field_name = "reg_id" if is_registration_model else "element_id"

        # Extract element IDs from query for filtering related objects
        element_ids = {element.id for element in query}

        # Get applicable questions for the event and features
        applicable_question_list = question_class.get_instance_questions(context["event"], context["features"])
        if model != "registration":
            applicable_question_list = applicable_question_list.filter(applicable=applicable_questions)

        # Extract question IDs for efficient database filtering
        question_ids = {question.id for question in applicable_question_list}
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
        for registration_character_relation in RegistrationCharacterRel.objects.filter(
            reg__run=context["run"]
        ).select_related("reg", "reg__member"):
            context["assignments"][registration_character_relation.character_id] = (
                registration_character_relation.reg.member
            )

    # Update context with all prepared export data
    context["applicable"] = applicable_questions
    context["answers"] = answers_by_question_and_element
    context["choices"] = choices_by_question_and_element
    context["questions"] = applicable_question_list


def _get_applicable_row(context: dict, el: object, model: str, member_cover: bool = False) -> tuple[list, list]:
    """Build row data for export with question answers and element information.

    This function constructs export data by combining element metadata with
    question-specific answers and choices based on the applicable context type.

    Parameters
    ----------
    context : dict
        Context dictionary containing:
        - questions: List of question objects
        - answers: Dict mapping question IDs to element answers
        - choices: Dict mapping question IDs to element choice selections
        - applicable: QuestionApplicable enum value
    el : object
        Element instance (registration, character, etc.) to extract data from
    model : str
        Model type identifier ('registration', 'character', etc.)
    member_cover : bool, optional
        Whether to include member profile images in export, by default False

    Returns
    -------
    tuple[list, list]
        Tuple containing (values_list, headers_list) for the export row

    """
    row_values = []
    column_headers = []

    # Build base headers and values for the element
    _row_header(context, el, column_headers, member_cover, model, row_values)

    # Add context-specific fields based on applicable type
    if context["applicable"] == QuestionApplicable.QUEST:
        column_headers.append("typ")
        row_values.append(el.typ.name if el.typ else "")
    elif context["applicable"] == QuestionApplicable.TRAIT:
        column_headers.append("quest")
        row_values.append(el.quest.name if el.quest else "")

    # Extract answers and choices from context
    question_answers = context["answers"]
    question_choices = context["choices"]

    # Process each question and extract corresponding values
    for question in context["questions"]:
        column_headers.append(question.name)

        # Get element-specific value mapping for special question types
        question_type_mapping = _get_values_mapping(el)
        cell_value = ""

        # Handle mapped question types (direct element attributes)
        if question.typ in question_type_mapping:
            cell_value = question_type_mapping[question.typ]()
        # Handle text-based question types (paragraph, text, email)
        elif question.typ in {"p", "t", "e"}:
            if question.id in question_answers and el.id in question_answers[question.id]:
                cell_value = question_answers[question.id][el.id]
        # Handle choice-based question types (single, multiple)
        elif question.typ in {"s", "m"}:
            if question.id in question_choices and el.id in question_choices[question.id]:
                cell_value = ", ".join(question_choices[question.id][el.id])

        # Clean value for export format (remove tabs, convert newlines)
        cell_value = cell_value.replace("\t", "").replace("\n", "<br />")
        row_values.append(cell_value)

    return row_values, column_headers


def _row_header(
    context: dict, el: object, header_columns: list, member_cover: bool, model: str, row_values: list
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
    elif model == "character":
        # Check if character has assignment in context
        if el.id in context["assignments"]:
            member = context["assignments"][el.id]

    # Add profile image column if requested
    if member_cover:
        header_columns.append("")
        profile_url = ""
        if member and member.profile:
            profile_url = member.profile_thumb.url
        row_values.append(profile_url)

    # Add participant and email columns for relevant models
    if model in ["registration", "character"]:
        # Add participant display name
        header_columns.append(_("Participant"))
        display_name = ""
        if member:
            display_name = member.display_real()
        row_values.append(display_name)

        # Add participant email
        header_columns.append(_("Email"))
        email_address = ""
        if member:
            email_address = member.email
        row_values.append(email_address)

    # Add registration-specific columns
    if model == "registration":
        # Add ticket information
        row_values.append(el.ticket.name if el.ticket is not None else "")
        header_columns.append(_("Ticket"))

        # Process additional registration headers
        _header_regs(context, el, header_columns, row_values)


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


def _header_regs(context: dict, registration: object, column_headers: list, column_values: list) -> None:
    """Generate header row data for registration download with feature-based columns.

    This function dynamically builds column headers and values for registration data
    export based on enabled features in the context. It appends data to the provided
    key and val lists in-place.

    Args:
        context: Context dictionary containing features configuration and feature names
        registration: Registration element object with registration data and relationships
        column_headers: List to append column headers to (modified in-place)
        column_values: List to append column values to (modified in-place)

    Returns:
        None: Function modifies key and val lists in-place

    """
    # Handle character-related data if character feature is enabled
    if "character" in context["features"]:
        column_headers.append(_("Characters"))
        column_values.append(", ".join([row.character.name for row in registration.rcrs.all()]))

    # Add pay-what-you-want pricing if enabled
    if "pay_what_you_want" in context["features"]:
        column_values.append(registration.pay_what)
        column_headers.append("PWYW")

    # Include surcharge information if feature is active
    if "surcharge" in context["features"]:
        column_values.append(registration.surcharge)
        column_headers.append(_("Surcharge"))

    # Add quota information for installment or quota-based registrations
    if "reg_quotas" in context["features"] or "reg_installments" in context["features"]:
        column_values.append(registration.quota)
        column_headers.append(_("Next quota"))

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
        column_headers.append(_("Ticket"))

        column_values.append(registration.options_price)
        column_headers.append(_("Options"))

    # Token and credit payment methods if token credit feature is enabled
    if "token_credit" in context["features"]:
        _expand_val(column_values, registration, "pay_a")
        column_headers.append(_("Money"))

        _expand_val(column_values, registration, "pay_b")
        column_headers.append(context.get("credit_name", _("Credits")))

        _expand_val(column_values, registration, "pay_c")
        column_headers.append(context.get("token_name", _("Credits")))


def _get_standard_row(context: dict, element: object) -> tuple[list, list]:
    """Extract values and keys from element's complete data.

    Args:
        context: Context dictionary for processing
        element: Element object with show_complete method

    Returns:
        Tuple of (values list, keys list)

    """
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
        "owner_id",
        "owner",
        "player",
        "player_full",
        "player_id",
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
    if field_name in ["title"]:
        if field_name not in context["features"]:
            return

    # Handle faction field processing
    if field_name == "factions":
        # Skip if faction feature is not enabled
        if "faction" not in context["features"]:
            return

        # Convert faction IDs to names and join with commas
        faction_names = [context["factions"][int(faction_id)]["name"] for faction_id in field_value]
        processed_value = ", ".join(faction_names)

    # Clean the processed value and append to output lists
    cleaned_value = _clean(processed_value)
    field_values.append(cleaned_value)
    field_names.append(field_name)


def _clean(html_content: str | None) -> str:
    """Strip HTML tags and normalize whitespace."""
    soup = BeautifulSoup(str(html_content), features="lxml")
    cleaned_text = soup.get_text("\n").replace("\n", " ")
    return cleaned_text


def _download_prepare(context: dict, model_name: str, queryset, type_config: dict) -> object:
    """Prepare and filter query for CSV download based on type and context.

    Processes a queryset by applying appropriate filters based on the model type
    and context, optimizes database queries with prefetch/select operations,
    and enriches registration data with accounting information.

    Args:
        context: Context dictionary containing event/run information and request data
        model_name: Name/type of the model being downloaded (e.g., 'character', 'registration')
        queryset: Initial Django queryset to filter and optimize
        type_config: Type configuration dictionary containing filtering rules and field specifications

    Returns:
        Filtered and optimized Django queryset ready for CSV export with all
        necessary related data loaded and additional computed fields attached

    """
    # Apply event-based filtering if specified in type configuration
    if check_field(type_config, "event"):
        queryset = queryset.filter(event=context["event"])

    # Apply run-based filtering if specified in type configuration
    elif check_field(type_config, "run"):
        queryset = queryset.filter(run=context["run"])

    # Apply number-based ordering if specified in type configuration
    if check_field(type_config, "number"):
        queryset = queryset.order_by("number")

    # Optimize character queries by prefetching factions and selecting player data
    if model_name == "character":
        queryset = queryset.prefetch_related("factions_list").select_related("player")

    # Handle registration-specific filtering and data enrichment
    if model_name == "registration":
        # Filter out cancelled registrations and optimize ticket queries
        queryset = queryset.filter(cancellation_date__isnull=True).select_related("ticket")

        # Get accounting data for all registrations in the queryset
        accounting_data = _orga_registrations_acc(context, queryset)

        # Attach accounting information as dynamic attributes to each registration
        for registration in queryset:
            if registration.id not in accounting_data:
                continue
            for key, value in accounting_data[registration.id].items():
                setattr(registration, key, value)

    return queryset


def get_writer(context: dict, nm: str) -> tuple[HttpResponse, csv.writer]:
    """Create CSV writer with proper headers for file download.

    Args:
        context: Context dictionary containing event information
        nm: Name component for the filename

    Returns:
        Tuple of HTTP response and CSV writer objects

    """
    # Create HTTP response with CSV content type and download headers
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="{}-{}.csv"'.format(context["event"], nm)},
    )

    # Initialize CSV writer with tab delimiter
    writer = csv.writer(response, delimiter="\t")
    return response, writer


def orga_registration_form_download(context: dict) -> HttpResponse:
    """Download registration form data as a ZIP archive."""
    return zip_exports(context, export_registration_form(context), "Registration form")


def export_registration_form(context: dict) -> list[tuple[str, list, list]]:
    """Export registration data to Excel format.

    Extracts registration questions and options from the event context and formats
    them for Excel export with proper column mappings and ordered data.

    Args:
        context: Context dictionary containing event and form data. Must include
            'event' key with an Event object that has get_elements method.

    Returns:
        List of tuples where each tuple contains:
            - str: Sheet name for Excel export
            - list: Column headers
            - list: Data rows for the sheet

    """
    # Initialize mappings for question types and status values
    mappings = {
        "typ": BaseQuestionType.get_mapping(),
        "status": QuestionStatus.get_mapping(),
    }

    # Set export type and extract column names from context
    context["typ"] = "registration_form"
    _get_column_names(context)

    # Extract registration questions data
    column_headers = context["columns"][0].keys()
    questions = get_ordered_registration_questions(context)
    question_values = _extract_values(column_headers, questions, mappings)

    # Initialize exports list with registration questions sheet
    excel_exports = [("registration_questions", column_headers, question_values)]

    # Prepare registration options data with modified key for relation
    option_headers = list(context["columns"][1].keys())
    modified_option_headers = option_headers.copy()
    modified_option_headers[0] = f"{modified_option_headers[0]}__name"

    # Query registration options ordered by question order and option order
    options_queryset = context["event"].get_elements(RegistrationOption).select_related("question")
    options_queryset = options_queryset.order_by(F("question__order"), "order")
    option_values = _extract_values(modified_option_headers, options_queryset, mappings)

    # Add registration options sheet to exports
    excel_exports.append(("registration_options", option_headers, option_values))
    return excel_exports


def _extract_values(field_names: list, queryset: object, field_mappings: dict) -> list[list]:
    """Extract and transform values from queryset based on field mappings.

    Args:
        field_names: List of field names to extract from queryset
        queryset: Django queryset object to extract values from
        field_mappings: Dictionary mapping field names to value transformation dictionaries

    Returns:
        List of lists containing extracted and transformed values for each row

    """
    all_values = []

    # Iterate through each row in the queryset values
    for row in queryset.values(*field_names):
        row_values = []

        # Process each field-value pair in the current row
        for field_name, field_value in row.items():
            # Apply mapping transformation if field and value exist in mappings
            if field_name in field_mappings and field_value in field_mappings[field_name]:
                transformed_value = field_mappings[field_name][field_value]
            else:
                transformed_value = field_value
            row_values.append(transformed_value)

        # Add processed row to results
        all_values.append(row_values)

    return all_values


def orga_character_form_download(context: dict) -> HttpResponse:
    """Generate and download character forms as a zip archive."""
    return zip_exports(context, export_character_form(context), "Character form")


def export_character_form(context: dict) -> list[tuple[str, list, list]]:
    """Export character form questions and options to CSV format.

    This function extracts writing questions and their associated options from an event
    and formats them for CSV export. It processes question metadata (type, status,
    applicability, visibility) and organizes the data into exportable tuples.

    Args:
        context: Context dictionary containing:
            - event: Event object with writing questions and options
            - columns: Column configuration for export formatting

    Returns:
        List of export tuples, each containing:
            - name (str): Export section name ('writing_questions' or 'writing_options')
            - keys (list): Column headers for CSV export
            - values (list): Data rows for CSV export

    Note:
        The function exports two sections:
        1. Writing questions with their metadata
        2. Writing options linked to their parent questions

    """
    # Define mappings for enum fields to human-readable values
    field_mappings = {
        "typ": BaseQuestionType.get_mapping(),
        "status": QuestionStatus.get_mapping(),
        "applicable": QuestionApplicable.get_mapping(),
        "visibility": QuestionVisibility.get_mapping(),
    }

    # Set context type and prepare column configuration
    context["typ"] = "character_form"
    _get_column_names(context)

    # Extract and export writing questions
    column_headers = context["columns"][0].keys()
    questions_queryset = context["event"].get_elements(WritingQuestion).order_by("applicable", "order")
    question_values = _extract_values(column_headers, questions_queryset, field_mappings)

    # Initialize exports list with writing questions data
    exports = [("writing_questions", column_headers, question_values)]

    # Prepare column configuration for writing options
    option_headers = list(context["columns"][1].keys())
    modified_option_headers = option_headers.copy()
    # Modify first column to include question name relationship
    modified_option_headers[0] = f"{modified_option_headers[0]}__name"

    # Extract and export writing options with related question data
    options_queryset = context["event"].get_elements(WritingOption).select_related("question")
    options_queryset = options_queryset.order_by(F("question__order"), "order")
    option_values = _extract_values(modified_option_headers, options_queryset, field_mappings)

    # Add writing options data to exports
    exports.append(("writing_options", option_headers, option_values))
    return exports


def _orga_registrations_acc(context, registrations=None):
    """Process registration accounting data for organizer reports.

    Args:
        context: Context dictionary with event and feature information
        registrations: Optional list of registrations to process (defaults to all active registrations)

    Returns:
        dict: Processed accounting data keyed by registration ID

    """
    # Use cached accounting data for efficiency
    cached_data = get_registration_accounting_cache(context["run"])

    # If specific registrations are requested, filter the cached data
    if registrations:
        result = {}
        for registration in registrations:
            if registration.id in cached_data:
                result[registration.id] = cached_data[registration.id]
        return result

    return cached_data


def _orga_registrations_acc_reg(reg, context: dict, cache_aip: dict) -> dict:
    """Process registration accounting data for organizer downloads.

    Calculates payment breakdowns, remaining balances, and ticket pricing
    information for registration accounting reports.

    Args:
        reg: Registration instance containing payment and ticket data
        context: Context dictionary containing:
            - features: Available feature flags
            - reg_tickets: Ticket information by ID
        cache_aip: Cached accounting payment data indexed by member_id
            containing payment type breakdown ('b', 'c' payment types)

    Returns:
        dict: Processed accounting data containing:
            - Payment amounts (tot_payed, tot_iscr, quota, etc.)
            - Payment type breakdown (pay_a, pay_b, pay_c) if token_credit enabled
            - Remaining balance calculation
            - Ticket and options pricing breakdown

    """
    dt = {}

    # Maximum rounding threshold for balance calculations
    max_rounding = 0.05

    # Round all monetary values to nearest cent
    for k in ["tot_payed", "tot_iscr", "quota", "deadline", "pay_what", "surcharge"]:
        dt[k] = round_to_nearest_cent(getattr(reg, k, 0))

    # Process payment breakdown if token credit feature is enabled
    if "token_credit" in context["features"]:
        if reg.member_id in cache_aip:
            # Extract payment types 'b' and 'c' from cache
            for pay in ["b", "c"]:
                v = 0
                if pay in cache_aip[reg.member_id]:
                    v = cache_aip[reg.member_id][pay]
                dt["pay_" + pay] = float(v)
            # Calculate remaining payment type 'a' as difference
            dt["pay_a"] = dt["tot_payed"] - (dt["pay_b"] + dt["pay_c"])
        else:
            # If no cached data, all payment is type 'a'
            dt["pay_a"] = dt["tot_payed"]

    # Calculate remaining balance with rounding tolerance
    dt["remaining"] = dt["tot_iscr"] - dt["tot_payed"]
    if abs(dt["remaining"]) < max_rounding:
        dt["remaining"] = 0

    # Calculate ticket and options pricing breakdown
    if reg.ticket_id in context["reg_tickets"]:
        t = context["reg_tickets"][reg.ticket_id]
        dt["ticket_price"] = t.price
        # Add pay-what-you-want amount to base ticket price
        if reg.pay_what:
            dt["ticket_price"] += reg.pay_what
        # Calculate options price as difference between total and ticket
        dt["options_price"] = reg.tot_iscr - dt["ticket_price"]

    return dt


def _get_column_names(context: dict) -> None:
    """Define column mappings and field types for different export contexts.

    Sets up comprehensive dictionaries mapping form fields to export columns
    based on context type (registration, tickets, abilities, etc.). This function
    generates the appropriate column headers and field definitions for CSV templates
    used in bulk upload/download operations.

    Args:
        context: Context dictionary containing export configuration including:
            - typ: Export type ('registration', 'registration_ticket', 'px_abilitie',
                   'registration_form', 'character_form', or writing element types)
            - features: Set of available features for the export context
            - event: Event instance for question lookups (for registration types)

    Side effects:
        Modifies context in-place, adding:
        - columns: List of dicts with column names and descriptions
        - fields: Dict mapping field names to types (for registration type)
        - name: Name of the export type (for px_abilitie type)

    """
    # Handle registration data export with participant, ticket, and question columns
    if context["typ"] == "registration":
        context["columns"] = [
            {
                "email": _("The participant's email"),
                "ticket": _("The name of the ticket")
                + " <i>("
                + (_("if it doesn't exist, it will be created"))
                + ")</i>",
                "characters": _("(Optional) The character names to assign to the player, separated by commas"),
                "donation": _("(Optional) The amount of a voluntary donation"),
            }
        ]
        # Build field type mapping from registration questions for validation
        questions = get_ordered_registration_questions(context).values("name", "typ")
        context["fields"] = {question["name"]: question["typ"] for question in questions}

        # Remove donation column if pay-what-you-want feature is disabled
        if "pay_what_you_want" not in context["features"]:
            del context["columns"][0]["donation"]

    # Handle ticket tier definition export
    elif context["typ"] == "registration_ticket":
        context["columns"] = [
            {
                "name": _("The ticket's name"),
                "tier": _("The tier of the ticket"),
                "description": _("(Optional) The ticket's description"),
                "price": _("(Optional) The cost of the ticket"),
                "max_available": _("(Optional) Maximun number of spots available"),
            }
        ]

    # Handle ability/experience system export
    elif context["typ"] == "px_abilitie":
        context["columns"] = [
            {
                "name": _("The name ability"),
                "cost": _("Cost of the ability"),
                "typ": _("Ability type"),
                "descr": _("(Optional) The ability description"),
                "prerequisites": _("(Optional) Other ability as prerequisite, comma-separated"),
                "requirements": _("(Optional) Character options as requirements, comma-separated"),
            }
        ]
        context["name"] = "Ability"

    # Handle registration form (questions + options) export
    elif context["typ"] == "registration_form":
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
                    "Optional - For text questions, maximum number of characters; For multiple options, maximum number of options (0 = no limit)"
                ),
            },
            {
                "question": _("The name of the question this option belongs to")
                + " <i>("
                + (_("If not found, the option will be skipped"))
                + ")</i>",
                "name": _("The name of the option"),
                "description": _("Optional – Additional information about the option, displayed below the question"),
                "price": _("Optional – Amount added to the registration fee if selected (0 = no extra cost)"),
                "max_available": _(
                    "Optional – Maximum number of times it can be selected across all registrations (0 = unlimited)"
                ),
            },
        ]

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
                    "Optional - For text questions, maximum number of characters; For multiple options, maximum number of options (0 = no limit)"
                ),
            },
            {
                "question": _("The name of the question this option belongs to")
                + " <i>("
                + (_("If not found, the option will be skipped"))
                + ")</i>",
                "name": _("The name of the option"),
                "description": _("Optional – Additional information about the option, displayed below the question"),
                "max_available": _("Optional – Maximum number of times it can be selected (0 = unlimited)"),
            },
        ]

        # Add requirements column if the feature is enabled
        if "wri_que_requirements" in context["features"]:
            context["columns"][1]["requirements"] = _("Optional - Other options as requirements, comma-separated")

    # Handle writing element types (character, plot, faction, quest, trait)
    else:
        _get_writing_names(context)


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
    writing_questions = context["event"].get_elements(WritingQuestion).filter(applicable=context["writing_typ"])
    for field in writing_questions.order_by("order").values("name", "typ"):
        context["fields"][field["name"]] = field["typ"]
        # Store the name field for special handling
        if field["typ"] == "name":
            context["field_name"] = field["name"]

    # Initialize base column configuration
    context["columns"] = [{}]

    # Configure character-specific fields and columns
    if context["writing_typ"] == QuestionApplicable.CHARACTER:
        context["fields"]["player"] = "skip"
        context["fields"]["email"] = "skip"

        # Add relationship columns if feature is enabled
        if "relationships" in context["features"]:
            context["columns"].append(
                {
                    "source": _("First character in the relationship (origin)"),
                    "target": _("Second character in the relationship (destination)"),
                    "text": _("Description of the relationship from source to target"),
                }
            )

    # Configure plot-specific columns
    elif context["writing_typ"] == QuestionApplicable.PLOT:
        context["columns"].append(
            {
                "plot": _("Name of the plot"),
                "character": _("Name of the character"),
                "text": _("Description of the role of the character in the plot"),
            }
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


def orga_tickets_download(request_context: dict) -> HttpResponse:
    """Download tickets as a ZIP archive."""
    return zip_exports(request_context, export_tickets(request_context), "Tickets")


def export_tickets(context: dict) -> list[tuple[str, list[str], list]]:
    """Export ticket data for the given event context.

    Args:
        context: Event context dictionary containing the event object.

    Returns:
        List containing tuple of (table_name, headers, data_rows).

    """
    # Define field mappings for data transformation
    mappings = {
        "tier": TicketTier.get_mapping(),
    }

    # Specify fields to extract from ticket objects
    field_keys = ["name", "tier", "description", "price", "max_available"]

    # Get all registration tickets for the event, ordered by number
    tickets_queryset = context["event"].get_elements(RegistrationTicket).order_by("number")

    # Extract and transform values using the defined mappings
    extracted_values = _extract_values(field_keys, tickets_queryset, mappings)

    return [("tickets", field_keys, extracted_values)]


def export_event(context):
    """Export event configuration and features data.

    Args:
        context: Context dictionary containing event and run information

    Returns:
        list: List of tuples containing configuration and features export data

    """
    column_names = ["name", "value"]
    configuration_values = []
    association = Association.objects.get(pk=context["event"].association_id)
    for element in [context["event"], context["run"], association]:
        for config_name, config_value in get_configs(element).items():
            configuration_values.append((config_name, config_value))
    export_data = [("configuration", column_names, configuration_values)]

    column_names = ["name", "slug"]
    feature_values = []
    for element in [context["event"], association]:
        for feature in element.features.all():
            feature_values.append((feature.name, feature.slug))
    export_data.append(("features", column_names, feature_values))

    return export_data


def export_abilities(context):
    """Export abilities data for an event.

    Args:
        context: Context dictionary containing event information

    Returns:
        list: Single-item list containing tuple of ("abilities", keys, values)
              where keys are column headers and values are ability data rows

    """
    column_headers = ["name", "cost", "typ", "descr", "prerequisites", "requirements"]

    ability_queryset = (
        context["event"]
        .get_elements(AbilityPx)
        .order_by("number")
        .select_related("typ")
        .prefetch_related("requirements", "prerequisites")
    )
    ability_rows = []
    for ability in ability_queryset:
        row_data = [ability.name, ability.cost, ability.typ.name if ability.typ else "", ability.descr]
        row_data.append(", ".join([prereq.name for prereq in ability.prerequisites.all()]))
        row_data.append(", ".join([req.name for req in ability.requirements.all()]))
        ability_rows.append(row_data)

    return [("abilities", column_headers, ability_rows)]
