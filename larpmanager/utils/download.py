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


def _temp_csv_file(keys: list[str], vals: list[list]) -> str:
    """Create CSV content from keys and values.

    Args:
        keys (list[str]): Column headers for the CSV file.
        vals (list[list]): Data rows where each inner list represents a row of data.

    Returns:
        str: CSV formatted string with headers and data.

    Example:
        >>> keys = ['Name', 'Age']
        >>> vals = [['Alice', 25], ['Bob', 30]]
        >>> csv_content = _temp_csv_file(keys, vals)
    """
    # Create DataFrame with provided data and column headers
    df = pd.DataFrame(vals, columns=keys)

    # Initialize string buffer to capture CSV output
    buffer = io.StringIO()

    # Write DataFrame to buffer in CSV format without row indices
    df.to_csv(buffer, index=False)

    # Reset buffer position to beginning for reading
    buffer.seek(0)

    # Return the complete CSV content as string
    return buffer.getvalue()


def zip_exports(ctx: dict, exports: list[tuple[str, list, list]], filename: str) -> HttpResponse:
    """Create ZIP file containing multiple CSV exports.

    Args:
        ctx: Context dictionary containing run information and metadata.
        exports: List of tuples where each tuple contains (name, keys, values)
                for CSV export. Name is the CSV filename, keys are column headers,
                values are row data.
        filename: Base filename for the ZIP archive (without extension).

    Returns:
        HttpResponse: ZIP file download response with appropriate headers set
                     for file attachment download.

    Note:
        Empty exports (no keys or values) are automatically skipped.
        The final ZIP filename includes the run information from context.
    """
    # Create in-memory buffer for ZIP file construction
    zip_buffer = io.BytesIO()

    # Build ZIP archive with CSV files
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # Process each export tuple
        for name, key, vals in exports:
            # Skip empty exports to avoid creating invalid CSV files
            if not key or not vals:
                continue
            # Add CSV file to ZIP archive with proper naming
            zip_file.writestr(f"{name}.csv", _temp_csv_file(key, vals))

    # Reset buffer position for reading
    zip_buffer.seek(0)

    # Create HTTP response with ZIP content
    response = HttpResponse(zip_buffer.read(), content_type="application/zip")
    # Set download headers with contextual filename
    response["Content-Disposition"] = f"attachment; filename={str(ctx['run'])} - {filename}.zip"
    return response


def download(ctx: dict, typ: type, nm: str) -> HttpResponse:
    """Generate downloadable ZIP export for model type.

    Creates a ZIP file containing exported data for the specified model type
    and returns it as an HTTP download response.

    Args:
        ctx: Context dictionary containing event data and configuration
        typ: Model class to export data from
        nm: Name prefix for the generated file

    Returns:
        HttpResponse: ZIP file download response with exported data

    Example:
        >>> download(context_dict, EventModel, "events")
    """
    # Export data from the specified model type using context
    exports = export_data(ctx, typ)

    # Create and return ZIP file response with capitalized filename
    return zip_exports(ctx, exports, nm.capitalize())


def export_data(ctx: dict, typ: type, member_cover: bool = False) -> list[tuple[str, list, list]]:
    """Export model data to structured format with questions and answers.

    Processes data export for various model types with question handling,
    answer processing, and cover image support for members when specified.

    Args:
        ctx: Context dictionary containing export configuration and features
        typ: Model class to export data from
        member_cover: Whether to include member cover images in export

    Returns:
        List of tuples containing (model_name, headers, data_rows) for export
    """
    # Initialize query and prepare basic export data
    query = typ.objects.all()
    get_event_cache_all(ctx)
    model = typ.__name__.lower()

    # Apply filters and prepare query based on model type
    query = _download_prepare(ctx, model, query, typ)
    _prepare_export(ctx, model, query)

    # Process each record to extract data rows
    key = None
    vals = []
    for el in query:
        # Handle applicable records or registration-specific processing
        if ctx["applicable"] or model == "registration":
            val, key = _get_applicable_row(ctx, el, model, member_cover)
        else:
            val, key = _get_standard_row(ctx, el)
        vals.append(val)

    # Sort data by appropriate column (adjust for member cover offset)
    order_column = 0
    if member_cover:
        order_column = 1
    vals = sorted(vals, key=lambda x: x[order_column])

    # Build base export structure
    exports = [(model, key, vals)]

    # Add plot relationships if exporting plot data
    if model == "plot":
        exports.extend(export_plot_rels(ctx))

    # Add character relationships if feature is enabled
    if model == "character":
        if "relationships" in ctx["features"]:
            exports.extend(export_relationships(ctx))

    return exports


def export_plot_rels(ctx: dict) -> list[tuple[str, list[str], list[list[str]]]]:
    """Export plot-character relationships.

    Extracts and formats plot-character relationship data from the database
    for export purposes. Retrieves all relationships for plots within the
    specified event context.

    Args:
        ctx: Context dictionary containing event data with 'event' key
            that has get_class_parent method

    Returns:
        List containing a single tuple with:
        - Export type identifier ('plot_rels')
        - Column headers list ['plot', 'character', 'text']
        - Data rows as list of lists containing plot name, character name, and relationship text
    """
    # Define the column headers for the export
    keys = ["plot", "character", "text"]
    vals = []

    # Get the event ID for filtering plot relationships
    event_id = ctx["event"].get_class_parent(Plot)

    # Query plot-character relationships for the event with optimized prefetching
    for rel in (
        PlotCharacterRel.objects.filter(plot__event_id=event_id).prefetch_related("plot", "character").order_by("order")
    ):
        # Extract relationship data: plot name, character name, and relationship text
        vals.append([rel.plot.name, rel.character.name, rel.text])

    return [("plot_rels", keys, vals)]


def export_relationships(ctx: dict) -> list[tuple[str, list[str], list[list[str]]]]:
    """Export character relationships for the given event context.

    Extracts all relationships between characters in the event and formats them
    for export with source character name, target character name, and relationship text.

    Args:
        ctx: Context dictionary containing event data with 'event' key that has
             a get_class_parent method to retrieve the event ID for Character model

    Returns:
        List containing a single tuple with:
        - 'relationships' as the export type identifier
        - List of column headers: ['source', 'target', 'text']
        - List of relationship data rows, each containing [source_name, target_name, text]
    """
    # Define column headers for the export
    keys = ["source", "target", "text"]
    vals = []

    # Get the event ID for filtering characters
    event_id = ctx["event"].get_class_parent(Character)

    # Query all relationships for characters in this event
    # Use prefetch_related to optimize database queries for source/target characters
    for rel in Relationship.objects.filter(source__event_id=event_id).prefetch_related("source", "target"):
        # Extract relationship data: source name, target name, and relationship text
        vals.append([rel.source.name, rel.target.name, rel.text])

    # Return formatted export data as expected by the export system
    return [("relationships", keys, vals)]


def _prepare_export(ctx: dict, model: str, query: QuerySet) -> None:
    """Prepare data for export operations.

    Processes questions, choices, and answers for data export functionality,
    organizing the data by question type and element relationships for
    registration and character model exports.

    Args:
        ctx: Context dictionary containing export configuration and data.
            Will be modified in-place to include prepared export data structures.
        model: String identifier for the Django model to export data from.
            Expected values: "registration", "character", or other model names.
        query: QuerySet containing the filtered data to export.

    Returns:
        None: Function modifies ctx in-place, adding the following keys:
            - applicable: Question applicability filter
            - answers: Dictionary mapping question_id -> element_id -> answer_text
            - choices: Dictionary mapping question_id -> element_id -> [choice_names]
            - questions: List of applicable questions for the model
            - assignments: (character model only) character_id -> member mapping
    """
    # Determine applicable question types for the model
    # noinspection PyProtectedMember
    applicable = QuestionApplicable.get_applicable(model)

    # Initialize data structures for export organization
    choices: dict[int, dict[int, list[str]]] = {}
    answers: dict[int, dict[int, str]] = {}
    questions: list = []

    # Process questions, choices, and answers if applicable or for registration model
    if applicable or model == "registration":
        # Determine model-specific classes and field names
        is_reg = model == "registration"
        question_cls = RegistrationQuestion if is_reg else WritingQuestion
        choices_cls = RegistrationChoice if is_reg else WritingChoice
        answers_cls = RegistrationAnswer if is_reg else WritingAnswer
        ref_field = "reg_id" if is_reg else "element_id"

        # Extract element IDs from query for filtering related objects
        el_ids = {el.id for el in query}

        # Get applicable questions for the event and features
        questions = question_cls.get_instance_questions(ctx["event"], ctx["features"])
        if model != "registration":
            questions = questions.filter(applicable=applicable)

        # Extract question IDs for efficient database filtering
        que_ids = {que.id for que in questions}
        filter_kwargs = {"question_id__in": que_ids, f"{ref_field}__in": el_ids}

        # Process multiple choice answers and organize by question and element
        que_choice = choices_cls.objects.filter(**filter_kwargs)
        for choice in que_choice.select_related("option"):
            element_id = getattr(choice, ref_field)
            # Initialize nested dictionaries as needed
            if choice.question_id not in choices:
                choices[choice.question_id] = {}
            if element_id not in choices[choice.question_id]:
                choices[choice.question_id][element_id] = []
            choices[choice.question_id][element_id].append(choice.option.name)

        # Process text answers and organize by question and element
        que_answer = answers_cls.objects.filter(**filter_kwargs)
        for answer in que_answer:
            element_id = getattr(answer, ref_field)
            # Initialize nested dictionary as needed
            if answer.question_id not in answers:
                answers[answer.question_id] = {}
            answers[answer.question_id][element_id] = answer.text

    # Special handling for character model: build character-to-member assignments
    if model == "character":
        ctx["assignments"] = {}
        for rcr in RegistrationCharacterRel.objects.filter(reg__run=ctx["run"]).select_related("reg", "reg__member"):
            ctx["assignments"][rcr.character.id] = rcr.reg.member

    # Update context with all prepared export data
    ctx["applicable"] = applicable
    ctx["answers"] = answers
    ctx["choices"] = choices
    ctx["questions"] = questions


def _get_applicable_row(ctx: dict, el: object, model: str, member_cover: bool = False) -> tuple[list, list]:
    """Build row data for export with question answers and element information.

    This function constructs export data by combining element metadata with
    question-specific answers and choices based on the applicable context type.

    Parameters
    ----------
    ctx : dict
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
    val = []
    key = []

    # Build base headers and values for the element
    _row_header(ctx, el, key, member_cover, model, val)

    # Add context-specific fields based on applicable type
    if ctx["applicable"] == QuestionApplicable.QUEST:
        key.append("typ")
        val.append(el.typ.name)
    elif ctx["applicable"] == QuestionApplicable.TRAIT:
        key.append("quest")
        val.append(el.quest.name)

    # Extract answers and choices from context
    answers = ctx["answers"]
    choices = ctx["choices"]

    # Process each question and extract corresponding values
    for que in ctx["questions"]:
        key.append(que.name)

        # Get element-specific value mapping for special question types
        mapping = _get_values_mapping(el)
        value = ""

        # Handle mapped question types (direct element attributes)
        if que.typ in mapping:
            value = mapping[que.typ]()
        # Handle text-based question types (paragraph, text, email)
        elif que.typ in {"p", "t", "e"}:
            if que.id in answers and el.id in answers[que.id]:
                value = answers[que.id][el.id]
        # Handle choice-based question types (single, multiple)
        elif que.typ in {"s", "m"}:
            if que.id in choices and el.id in choices[que.id]:
                value = ", ".join(choices[que.id][el.id])

        # Clean value for export format (remove tabs, convert newlines)
        value = value.replace("\t", "").replace("\n", "<br />")
        val.append(value)

    return val, key


def _row_header(ctx: dict, el: object, key: list, member_cover: bool, model: str, val: list) -> None:
    """Build header row data with member information and basic element data.

    Constructs header rows for export tables by extracting member data, profile images,
    and model-specific information like ticket details for registrations.

    Args:
        ctx: Context dictionary containing assignments data and other export context
        el: Element instance to process (registration or character object)
        key: List to append header column names to
        member_cover: Whether to include member profile image column
        model: Model type identifier ('registration' or 'character')
        val: List to append corresponding values to

    Returns:
        None: Function modifies key and val lists in place
    """
    # Extract member based on model type
    member = None
    if model == "registration":
        member = el.member
    elif model == "character":
        # Check if character has assignment in context
        if el.id in ctx["assignments"]:
            member = ctx["assignments"][el.id]

    # Add profile image column if requested
    if member_cover:
        key.append("")
        profile = ""
        if member and member.profile:
            profile = member.profile_thumb.url
        val.append(profile)

    # Add participant and email columns for relevant models
    if model in ["registration", "character"]:
        # Add participant display name
        key.append(_("Participant"))
        display = ""
        if member:
            display = member.display_real()
        val.append(display)

        # Add participant email
        key.append(_("Email"))
        email = ""
        if member:
            email = member.email
        val.append(email)

    # Add registration-specific columns
    if model == "registration":
        # Add ticket information
        val.append(el.ticket.name if el.ticket is not None else "")
        key.append(_("Ticket"))

        # Process additional registration headers
        _header_regs(ctx, el, key, val)


def _expand_val(val, el, field):
    if hasattr(el, field):
        value = getattr(el, field)
        if value:
            val.append(value)
            return

    val.append("")


def _header_regs(ctx: dict, el: object, key: list, val: list) -> None:
    """Generate header row data for registration download with feature-based columns.

    This function dynamically builds column headers and values for registration data
    export based on enabled features in the context. It appends data to the provided
    key and val lists in-place.

    Args:
        ctx: Context dictionary containing features configuration and feature names
        el: Registration element object with registration data and relationships
        key: List to append column headers to (modified in-place)
        val: List to append column values to (modified in-place)

    Returns:
        None: Function modifies key and val lists in-place
    """
    # Handle character-related data if character feature is enabled
    if "character" in ctx["features"]:
        key.append(_("Characters"))
        val.append(", ".join([row.character.name for row in el.rcrs.all()]))

    # Add pay-what-you-want pricing if enabled
    if "pay_what_you_want" in ctx["features"]:
        val.append(el.pay_what)
        key.append("PWYW")

    # Include surcharge information if feature is active
    if "surcharge" in ctx["features"]:
        val.append(el.surcharge)
        key.append(_("Surcharge"))

    # Add quota information for installment or quota-based registrations
    if "reg_quotas" in ctx["features"] or "reg_installments" in ctx["features"]:
        val.append(el.quota)
        key.append(_("Next quota"))

    # Core payment and deadline information (always included)
    val.append(el.deadline)
    key.append(_("Deadline"))

    val.append(el.remaining)
    key.append(_("Owing"))

    val.append(el.tot_payed)
    key.append(_("Payed"))

    val.append(el.tot_iscr)
    key.append(_("Total"))

    # VAT-related pricing breakdown if VAT feature is enabled
    if "vat" in ctx["features"]:
        val.append(el.ticket_price)
        key.append(_("Ticket"))

        val.append(el.options_price)
        key.append(_("Options"))

    # Token and credit payment methods if token credit feature is enabled
    if "token_credit" in ctx["features"]:
        _expand_val(val, el, "pay_a")
        key.append(_("Money"))

        _expand_val(val, el, "pay_b")
        key.append(ctx.get("credit_name", _("Credits")))

        _expand_val(val, el, "pay_c")
        key.append(ctx.get("token_name", _("Credits")))


def _get_standard_row(ctx, el):
    val = []
    key = []
    for k, v in el.show_complete().items():
        _writing_field(ctx, k, key, v, val)

    return val, key


def _writing_field(ctx: dict, k: str, key: list, v: any, val: list) -> None:
    """Process writing field for export with feature-based filtering.

    Filters and formats writing fields based on enabled features,
    handling special cases like factions and custom fields. Modifies
    the key and val lists in-place by appending processed field data.

    Args:
        ctx: Context dictionary containing features and factions data
        k: Field name/key to process
        key: List to append field names to (modified in-place)
        v: Field value to process
        val: List to append processed values to (modified in-place)

    Returns:
        None: Function modifies key and val lists in-place
    """
    new_val = v

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
    if k in skip_fields:
        return

    # Skip custom fields (prefixed with "custom_")
    if k.startswith("custom_"):
        return

    # Check if title field is enabled in features
    if k in ["title"]:
        if k not in ctx["features"]:
            return

    # Handle faction field processing
    if k == "factions":
        # Skip if faction feature is not enabled
        if "faction" not in ctx["features"]:
            return

        # Convert faction IDs to names and join with commas
        aux = [ctx["factions"][int(el)]["name"] for el in v]
        new_val = ", ".join(aux)

    # Clean the processed value and append to output lists
    clean = _clean(new_val)
    val.append(clean)
    key.append(k)


def _clean(new_val):
    soup = BeautifulSoup(str(new_val), features="lxml")
    clean = soup.get_text("\n").replace("\n", " ")
    return clean


def _download_prepare(ctx: dict, nm: str, query, typ: dict):
    """Prepare and filter query for CSV download based on type and context.

    This function applies various filters and optimizations to a Django queryset
    based on the model type and context configuration. It handles event/run filtering,
    ordering, and model-specific optimizations for CSV export.

    Args:
        ctx: Context dictionary containing event/run information and other metadata
        nm: Name/type of the model being downloaded (e.g., 'character', 'registration')
        query: Initial Django queryset to filter and optimize
        typ: Type configuration dictionary containing field specifications for filtering

    Returns:
        QuerySet: Filtered and optimized queryset ready for CSV export with appropriate
                 select_related/prefetch_related optimizations applied

    Note:
        For registration queries, this function also enriches objects with accounting
        data from _orga_registrations_acc and filters out cancelled registrations.
    """
    # Apply event-based filtering if event field is configured
    if check_field(typ, "event"):
        query = query.filter(event=ctx["event"])

    # Apply run-based filtering if run field is configured
    elif check_field(typ, "run"):
        query = query.filter(run=ctx["run"])

    # Apply number-based ordering if number field is configured
    if check_field(typ, "number"):
        query = query.order_by("number")

    # Optimize character queries with related data prefetching
    if nm == "character":
        query = query.prefetch_related("factions_list").select_related("player")

    # Handle registration-specific filtering and accounting data enrichment
    if nm == "registration":
        # Filter out cancelled registrations and optimize with ticket data
        query = query.filter(cancellation_date__isnull=True).select_related("ticket")

        # Fetch accounting data for registrations
        resp = _orga_registrations_acc(ctx, query)

        # Enrich each registration object with accounting information
        for el in query:
            if el.id not in resp:
                continue
            for key, value in resp[el.id].items():
                setattr(el, key, value)

    return query


def get_writer(ctx, nm):
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="{}-{}.csv"'.format(ctx["event"], nm)},
    )
    writer = csv.writer(response, delimiter="\t")
    return response, writer


def orga_registration_form_download(ctx):
    return zip_exports(ctx, export_registration_form(ctx), "Registration form")


def export_registration_form(ctx: dict) -> list[tuple[str, list, list]]:
    """Export registration data to Excel format.

    Exports registration questions and options from an event to Excel-compatible format,
    including proper column mappings and ordered data structure.

    Args:
        ctx: Context dictionary containing event and form data with required keys:
            - event: Event instance with registration data
            - columns: List of column definitions for export

    Returns:
        List of tuples where each tuple contains:
            - Sheet name (str): Name for the Excel sheet
            - Headers (list): Column headers for the sheet
            - Data (list): Rows of data for the sheet

    Note:
        Function processes two sheets: registration_questions and registration_options,
        with proper ordering and type/status mappings applied.
    """
    # Initialize type and status mappings for data transformation
    mappings = {
        "typ": BaseQuestionType.get_mapping(),
        "status": QuestionStatus.get_mapping(),
    }

    # Set context type and extract column information
    ctx["typ"] = "registration_form"
    _get_column_names(ctx)

    # Process registration questions sheet
    key = ctx["columns"][0].keys()
    que = get_ordered_registration_questions(ctx)
    vals = _extract_values(key, que, mappings)

    # Initialize exports list with registration questions data
    exports = [("registration_questions", key, vals)]

    # Process registration options sheet with modified column names
    key = list(ctx["columns"][1].keys())
    new_key = key.copy()
    new_key[0] = f"{new_key[0]}__name"

    # Get registration options with proper ordering and relationships
    que = ctx["event"].get_elements(RegistrationOption).select_related("question")
    que = que.order_by(F("question__order"), "order")
    vals = _extract_values(new_key, que, mappings)

    # Add registration options sheet to exports
    exports.append(("registration_options", key, vals))
    return exports


def _extract_values(key: list[str], que: any, mappings: dict[str, dict[any, any]]) -> list[list[any]]:
    """Extract and transform values from a queryset using field mappings.

    Args:
        key: List of field names to extract from the queryset.
        que: Django queryset or similar object with values() method.
        mappings: Dictionary mapping field names to value transformation dictionaries.
                 Format: {field_name: {old_value: new_value, ...}, ...}

    Returns:
        List of lists containing extracted and transformed values for each row.
        Each inner list corresponds to one row with transformed field values.
    """
    all_vals = []

    # Iterate through each row in the queryset values
    for row in que.values(*key):
        vals = []

        # Process each field-value pair in the current row
        for field, value in row.items():
            # Apply mapping transformation if field and value exist in mappings
            if field in mappings and value in mappings[field]:
                new_value = mappings[field][value]
            else:
                new_value = value
            vals.append(new_value)

        # Add the processed row to the result
        all_vals.append(vals)

    return all_vals


def orga_character_form_download(ctx):
    return zip_exports(ctx, export_character_form(ctx), "Character form")


def export_character_form(ctx: dict) -> list[tuple[str, list, list]]:
    """
    Export character form questions and options to CSV format.

    Processes writing questions and their associated options from an event,
    converting them into a structured format suitable for CSV export.

    Args:
        ctx: Context dictionary containing:
            - event: Event object to extract questions from
            - columns: Column configuration for export formatting

    Returns:
        List of export tuples in format (name, keys, values) where:
            - name: Export section identifier ('writing_questions' or 'writing_options')
            - keys: Column headers for the CSV
            - values: Data rows for the CSV
    """
    # Define mappings for enum fields to human-readable values
    mappings = {
        "typ": BaseQuestionType.get_mapping(),
        "status": QuestionStatus.get_mapping(),
        "applicable": QuestionApplicable.get_mapping(),
        "visibility": QuestionVisibility.get_mapping(),
    }

    # Set context type and extract column configuration
    ctx["typ"] = "character_form"
    _get_column_names(ctx)

    # Extract and process writing questions
    key = ctx["columns"][0].keys()
    que = ctx["event"].get_elements(WritingQuestion).order_by("applicable", "order")
    vals = _extract_values(key, que, mappings)

    # Initialize exports list with writing questions data
    exports = [("writing_questions", key, vals)]

    # Process writing options with question relationship
    key = list(ctx["columns"][1].keys())
    new_key = key.copy()
    new_key[0] = f"{new_key[0]}__name"  # Modify key to include question name

    # Query writing options with related question data, ordered by question and option order
    que = ctx["event"].get_elements(WritingOption).select_related("question")
    que = que.order_by(F("question__order"), "order")
    vals = _extract_values(new_key, que, mappings)

    # Add writing options data to exports
    exports.append(("writing_options", key, vals))
    return exports


def _orga_registrations_acc(ctx: dict, regs: list = None) -> dict:
    """Process registration accounting data for organizer reports.

    This function retrieves and processes cached registration accounting data,
    optionally filtering for specific registrations if provided.

    Args:
        ctx: Context dictionary containing event and feature information.
             Must include 'run' key with the current event run.
        regs: Optional list of registration objects to process.
              If None, returns all cached registration data.

    Returns:
        Dictionary containing processed accounting data keyed by registration ID.
        Each value contains the accounting information for that registration.

    Example:
        >>> ctx = {'run': event_run}
        >>> data = _orga_registrations_acc(ctx)
        >>> # Returns all cached accounting data
        >>>
        >>> filtered_data = _orga_registrations_acc(ctx, [reg1, reg2])
        >>> # Returns data only for reg1 and reg2
    """
    # Retrieve cached accounting data for the current event run
    # This avoids expensive database queries for repeated access
    cached_data = get_registration_accounting_cache(ctx["run"])

    # Filter cached data if specific registrations are requested
    if regs:
        res = {}
        # Iterate through requested registrations and extract their data
        for r in regs:
            # Only include registrations that exist in the cache
            if r.id in cached_data:
                res[r.id] = cached_data[r.id]
        return res

    # Return all cached data if no specific registrations requested
    return cached_data


def _orga_registrations_acc_reg(reg, ctx: dict, cache_aip: dict) -> dict:
    """
    Process registration accounting data for organizer downloads.

    Calculates payment breakdowns, remaining balances, and ticket pricing
    information for registration accounting reports.

    Args:
        reg: Registration instance containing payment and ticket data
        ctx: Context dictionary containing:
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
    if "token_credit" in ctx["features"]:
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
    if reg.ticket_id in ctx["reg_tickets"]:
        t = ctx["reg_tickets"][reg.ticket_id]
        dt["ticket_price"] = t.price
        # Add pay-what-you-want amount to base ticket price
        if reg.pay_what:
            dt["ticket_price"] += reg.pay_what
        # Calculate options price as difference between total and ticket
        dt["options_price"] = reg.tot_iscr - dt["ticket_price"]

    return dt


def _get_column_names(ctx: dict) -> None:
    """Define column mappings and field types for different export contexts.

    Sets up comprehensive dictionaries mapping form fields to export columns
    based on context type (registration, tickets, abilities, etc.). This function
    generates the appropriate column headers and field definitions for CSV templates
    used in bulk upload/download operations.

    Args:
        ctx: Context dictionary containing export configuration including:
            - typ: Export type ('registration', 'registration_ticket', 'px_abilitie',
                   'registration_form', 'character_form', or writing element types)
            - features: Set of available features for the export context
            - event: Event instance for question lookups (for registration types)

    Side Effects:
        Modifies ctx in-place, adding:
        - columns: List of dicts with column names and descriptions
        - fields: Dict mapping field names to types (for registration type)
        - name: Name of the export type (for px_abilitie type)
    """
    # Handle registration data export with participant, ticket, and question columns
    if ctx["typ"] == "registration":
        # Define core registration columns with participant email and ticket assignment
        ctx["columns"] = [
            {
                "email": _("The participant's email"),
                "ticket": _("The name of the ticket")
                + " <i>("
                + (_("if it doesn't exist, it will be created"))
                + ")</i>",
                # Optional character assignment for automatic character linking
                "characters": _("(Optional) The character names to assign to the player, separated by commas"),
                "donation": _("(Optional) The amount of a voluntary donation"),
            }
        ]

        # Build field type mapping from registration questions for validation
        que = get_ordered_registration_questions(ctx).values("name", "typ")
        ctx["fields"] = {el["name"]: el["typ"] for el in que}

        # Remove donation column if pay-what-you-want feature is disabled
        if "pay_what_you_want" not in ctx["features"]:
            del ctx["columns"][0]["donation"]

    # Handle ticket tier definition export
    elif ctx["typ"] == "registration_ticket":
        # Define ticket configuration columns for tier management
        ctx["columns"] = [
            {
                "name": _("The ticket's name"),
                "tier": _("The tier of the ticket"),
                "description": _("(Optional) The ticket's description"),
                # Price and availability controls for ticket management
                "price": _("(Optional) The cost of the ticket"),
                "max_available": _("(Optional) Maximun number of spots available"),
            }
        ]

    # Handle ability/experience system export
    elif ctx["typ"] == "px_abilitie":
        # Define ability system columns for character progression
        ctx["columns"] = [
            {
                "name": _("The name ability"),
                "cost": _("Cost of the ability"),
                "typ": _("Ability type"),
                "descr": _("(Optional) The ability description"),
                # Define ability dependencies and character requirements
                "prerequisites": _("(Optional) Other ability as prerequisite, comma-separated"),
                "requirements": _("(Optional) Character options as requirements, comma-separated"),
            }
        ]
        # Set export name for ability context
        ctx["name"] = "Ability"

    # Handle registration form (questions + options) export
    elif ctx["typ"] == "registration_form":
        # Define question and option columns for registration form configuration
        # First dict: Question definitions with name, type, status
        # Second dict: Option definitions linked to questions
        ctx["columns"] = [
            {
                "name": _("The question name"),
                # Define allowed question types for form validation
                "typ": _("The question type, allowed values are")
                + ": 'single-choice', 'multi-choice', 'short-text', 'long-text', 'advanced'",
                "description": _("Optional - Extended description (displayed in small gray text)"),
                # Define question visibility and requirement levels
                "status": _("The question status, allowed values are")
                + ": 'optional', 'mandatory', 'disabled', 'hidden'",
                "max_length": _(
                    "Optional - For text questions, maximum number of characters; For multiple options, maximum number of options (0 = no limit)"
                ),
            },
            {
                # Link options to their parent questions
                "question": _("The name of the question this option belongs to")
                + " <i>("
                + (_("If not found, the option will be skipped"))
                + ")</i>",
                "name": _("The name of the option"),
                "description": _("Optional – Additional information about the option, displayed below the question"),
                # Define pricing and availability constraints for options
                "price": _("Optional – Amount added to the registration fee if selected (0 = no extra cost)"),
                "max_available": _(
                    "Optional – Maximum number of times it can be selected across all registrations (0 = unlimited)"
                ),
            },
        ]

    # Handle character/writing form (questions + options) export
    elif ctx["typ"] == "character_form":
        # Define character form columns with extended question types for writing elements
        # Similar to registration form but with additional fields for writing elements
        ctx["columns"] = [
            {
                "name": _("The question name"),
                # Extended question types including writing-specific types
                "typ": _("The question type, allowed values are")
                + ": 'single-choice', 'multi-choice', 'short-text', 'long-text', 'advanced', 'name', 'teaser', 'text'",
                "description": _("Optional - Extended description (displayed in small gray text)"),
                "status": _("The question status, allowed values are")
                + ": 'optional', 'mandatory', 'disabled', 'hidden'",
                # Define which writing elements this question applies to
                "applicable": _("The writing element this question applies to, allowed values are")
                + ": 'character', 'plot', 'faction', 'quest', 'trait'",
                # Control question visibility to different user groups
                "visibility": _("The question visibility to participants, allowed values are")
                + ": 'searchable', 'public', 'private', 'hidden'",
                "max_length": _(
                    "Optional - For text questions, maximum number of characters; For multiple options, maximum number of options (0 = no limit)"
                ),
            },
            {
                # Option definitions for character form questions
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
        if "wri_que_requirements" in ctx["features"]:
            ctx["columns"][1]["requirements"] = _("Optional - Other options as requirements, comma-separated")

    # Handle writing element types (character, plot, faction, quest, trait)
    else:
        # Delegate to specialized function for writing element column definitions
        _get_writing_names(ctx)


def _get_writing_names(ctx: dict) -> None:
    """Get writing field names and types for download context.

    Populates the provided context dictionary with writing field information
    including applicable question types, field definitions, column configurations,
    and allowed field names for data export functionality.

    Args:
        ctx: Context dictionary containing event, typ, and features data.
             Will be modified in-place with additional writing field information:
             - writing_typ: Applicable question type
             - fields: Dictionary mapping field names to their types
             - field_name: Name field identifier (if present)
             - columns: List of column configuration dictionaries
             - allowed: List of allowed field names for export

    Returns:
        None: Function modifies ctx dictionary in-place
    """
    # Determine the applicable writing question type based on context
    ctx["writing_typ"] = QuestionApplicable.get_applicable(ctx["typ"])
    ctx["fields"] = {}

    # Retrieve and process writing questions for the event
    que = ctx["event"].get_elements(WritingQuestion).filter(applicable=ctx["writing_typ"])
    for field in que.order_by("order").values("name", "typ"):
        ctx["fields"][field["name"]] = field["typ"]
        # Store the name field for special handling
        if field["typ"] == "name":
            ctx["field_name"] = field["name"]

    # Initialize base column configuration
    ctx["columns"] = [{}]

    # Configure character-specific fields and columns
    if ctx["writing_typ"] == QuestionApplicable.CHARACTER:
        ctx["fields"]["player"] = "skip"
        ctx["fields"]["email"] = "skip"

        # Add relationship columns if feature is enabled
        if "relationships" in ctx["features"]:
            ctx["columns"].append(
                {
                    "source": _("First character in the relationship (origin)"),
                    "target": _("Second character in the relationship (destination)"),
                    "text": _("Description of the relationship from source to target"),
                }
            )

    # Configure plot-specific columns
    elif ctx["writing_typ"] == QuestionApplicable.PLOT:
        ctx["columns"].append(
            {
                "plot": _("Name of the plot"),
                "character": _("Name of the character"),
                "text": _("Description of the role of the character in the plot"),
            }
        )

    # Configure quest-specific columns
    elif ctx["writing_typ"] == QuestionApplicable.QUEST:
        ctx["columns"][0]["typ"] = _("Name of quest type")

    # Configure trait-specific columns
    elif ctx["writing_typ"] == QuestionApplicable.TRAIT:
        ctx["columns"][0]["quest"] = _("Name of quest")

    # Build the list of allowed field names for export validation
    ctx["allowed"] = list(ctx["columns"][0].keys())
    ctx["allowed"].extend(ctx["fields"].keys())


def orga_tickets_download(ctx):
    return zip_exports(ctx, export_tickets(ctx), "Tickets")


def export_tickets(ctx: dict) -> list[tuple[str, list[str], list]]:
    """Export registration tickets data for the given event context.

    Args:
        ctx: Context dictionary containing event and related data

    Returns:
        List containing a single tuple with:
        - Table name ("tickets")
        - Column headers list
        - Data values list
    """
    # Define field mappings for data transformation
    mappings = {
        "tier": TicketTier.get_mapping(),
    }

    # Specify which fields to extract from the tickets
    keys = ["name", "tier", "description", "price", "max_available"]

    # Query registration tickets for the event, ordered by number
    que = ctx["event"].get_elements(RegistrationTicket).order_by("number")

    # Extract and transform the values using the defined mappings
    vals = _extract_values(keys, que, mappings)

    return [("tickets", keys, vals)]


def export_event(ctx: dict) -> list[tuple[str, list[str], list[tuple]]]:
    """Export event configuration and features data.

    This function extracts configuration settings and features from an event,
    its associated run, and the parent association, formatting them for export.

    Args:
        ctx: Context dictionary containing event and run information.
             Must include 'event' and 'run' keys with corresponding model instances.

    Returns:
        A list of tuples where each tuple contains:
        - Export type name (str)
        - Column headers (list of str)
        - Data rows (list of tuples)

        Example:
            [
                ("configuration", ["name", "value"], [("setting1", "value1"), ...]),
                ("features", ["name", "slug"], [("feature1", "slug1"), ...])
            ]
    """
    # Prepare configuration export structure
    keys = ["name", "value"]
    vals = []

    # Get the association for the current event
    assoc = Association.objects.get(pk=ctx["event"].assoc_id)

    # Extract configuration from event, run, and association
    for element in [ctx["event"], ctx["run"], assoc]:
        for name, value in get_configs(element).items():
            vals.append((name, value))

    # Create configuration export entry
    exports = [("configuration", keys, vals)]

    # Prepare features export structure
    keys = ["name", "slug"]
    vals = []

    # Extract features from event and association
    for element in [ctx["event"], assoc]:
        for feature in element.features.all():
            vals.append((feature.name, feature.slug))

    # Add features export entry and return complete exports
    exports.append(("features", keys, vals))

    return exports


def export_abilities(ctx: dict) -> list[tuple[str, list[str], list[list]]]:
    """Export abilities data for an event.

    Extracts ability information from the event context and formats it for export.
    Each ability includes its name, cost, type, description, prerequisites, and requirements.

    Args:
        ctx: Context dictionary containing event information with 'event' key
             that has a get_elements method for querying AbilityPx objects

    Returns:
        Single-item list containing a tuple with:
        - "abilities": Export type identifier
        - keys: List of column headers for the exported data
        - values: List of lists, each containing ability data in column order
    """
    # Define column headers for the export
    keys = ["name", "cost", "typ", "descr", "prerequisites", "requirements"]

    # Query abilities for the event, ordered by number with related data prefetched
    que = (
        ctx["event"]
        .get_elements(AbilityPx)
        .order_by("number")
        .select_related("typ")
        .prefetch_related("requirements", "prerequisites")
    )

    # Process each ability and build data rows
    vals = []
    for el in que:
        # Basic ability information
        val = [el.name, el.cost, el.typ.name, el.descr]

        # Convert related objects to comma-separated strings
        val.append(", ".join([prereq.name for prereq in el.prerequisites.all()]))
        val.append(", ".join([req.name for req in el.requirements.all()]))

        vals.append(val)

    return [("abilities", keys, vals)]
