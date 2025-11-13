from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db.models import (
    Case,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    Model,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.models.accounting import (
    AccountingItem,
    AccountingItemExpense,
    AccountingItemPayment,
    AccountingItemTransaction,
    OtherChoices,
    PaymentInvoice,
    PaymentStatus,
    RefundRequest,
)
from larpmanager.models.member import Membership

logger = logging.getLogger(__name__)


def paginate(
    request: HttpRequest,
    context: dict,
    pagination_model: type[Model],
    template_name: str,
    view_name: str,
    *,
    is_executive: bool = True,
) -> HttpResponse | JsonResponse:
    """Handle pagination for DataTables AJAX requests and initial page rendering.

    This function serves dual purposes:
    1. Renders the initial template with table configuration for GET requests
    2. Returns JSON data for DataTables AJAX pagination for POST requests

    Args:
        request: The HTTP request object containing method and POST data
        context: Template context dictionary containing association/run data
        pagination_model: The Django model class to paginate
        template_name: Template path for initial page rendering
        view_name: View name used for generating edit URLs
        is_executive: Whether this is an organization-wide view (True) or event-specific (False)

    Returns:
        HttpResponse: Rendered template for GET requests
        JsonResponse: DataTables-formatted JSON for POST requests

    """
    model_queryset = pagination_model.objects
    # Extract model name for table identification
    # noinspection PyProtectedMember
    model_name = pagination_model._meta.model_name  # noqa: SLF001  # Django model metadata

    # Handle initial page load (GET request)
    if request.method != "POST":
        # Generate unique table name based on context
        if is_executive:
            context["table_name"] = f"{model_name}_{context['association_id']}"
        else:
            context["table_name"] = f"{model_name}_{context['run'].get_slug()}"

        return render(request, template_name, context)

    # Handle DataTables AJAX request (POST)
    # Extract draw parameter for DataTables synchronization
    datatables_draw = int(request.POST.get("draw", 0))

    # Get filtered elements and count based on search/filter criteria
    filtered_elements, filtered_records_count = _get_elements_query(
        model_queryset,
        context,
        request,
        pagination_model,
        is_executive=is_executive,
    )

    # Get total count of all records (unfiltered)
    total_records_count = pagination_model.objects.count()

    # Prepare localized edit button text
    edit_label = _("Edit")
    # Transform elements into DataTables-compatible format
    datatables_rows = _prepare_data_json(context, filtered_elements, view_name, edit_label, is_executive=is_executive)

    # Return DataTables-expected JSON response
    return JsonResponse(
        {
            "draw": datatables_draw,
            "recordsTotal": total_records_count,
            "recordsFiltered": filtered_records_count,
            "data": datatables_rows,
        },
    )


def _get_elements_query(cls, context: dict, request, model_type, *, is_executive: bool = True) -> tuple[any, int]:
    """Get filtered and paginated query elements based on context and request parameters.

    Args:
        cls: The model class to query
        context: Context dictionary containing association ID, run, event, and other filters
        request: HTTP request object containing query parameters
        model_type: Model type for field inspection
        is_executive: Whether this is an executive (organization-wide) view or event-specific view

    Returns:
        tuple: (filtered_elements_queryset, total_filtered_count)

    """
    # Extract pagination and filtering parameters from request
    start_index, page_length, order_params, filter_params = _get_query_params(request)

    # Start with base queryset filtered by association
    query_elements = cls.filter(association_id=context["association_id"])

    # Apply event-specific filtering for non-executive views
    if not is_executive and "run" in context:
        # Check which relation field exists on the model to filter by run/event
        # noinspection PyProtectedMember
        field_names = [f.name for f in model_type._meta.get_fields()]  # noqa: SLF001  # Django model metadata
        if "run" in field_names:
            query_elements = query_elements.filter(run=context["run"])
        elif "reg" in field_names:
            query_elements = query_elements.filter(reg__run=context["run"])
        elif "event" in field_names:
            query_elements = query_elements.filter(event=context["event"])

    # Filter out hidden elements if the model supports it
    # noinspection PyProtectedMember
    if "hide" in [f.name for f in model_type._meta.get_fields()]:  # noqa: SLF001  # Django model metadata
        query_elements = query_elements.filter(hide=False)

    # Apply select_related optimization if specified in context
    select_related_fields = context.get("selrel")
    if select_related_fields:
        for field in select_related_fields:
            query_elements = query_elements.select_related(field)

    # Apply any custom query modifications defined in context
    query_elements = _apply_custom_queries(context, query_elements, model_type)

    # Apply user-defined filters from the request
    query_elements = _set_filtering(context, query_elements, filter_params)

    # Count filtered records before applying pagination
    filtered_records_count = query_elements.count()

    # Apply ordering if specified in context
    ordering = _get_ordering(context, order_params)
    if ordering:
        query_elements = query_elements.order_by(*ordering)

    # Apply pagination using slice notation
    query_elements = query_elements[start_index : start_index + page_length]

    return query_elements, filtered_records_count


def _set_filtering(context: dict, queryset, column_filters: dict):
    """Apply filtering to queryset elements based on provided filters.

    Args:
        context: Context dictionary containing fields and optional callbacks/afield
        queryset: Django queryset to filter
        column_filters: Dictionary mapping column indices to filter values

    Returns:
        Filtered queryset with applied search conditions

    """
    # Get field mapping configuration for search operations
    field_map = _get_field_map()

    # Process each filter condition from the request
    for index, filter_value in column_filters.items():
        column_index = int(index)

        # Validate column index is within bounds
        if column_index >= len(context["fields"]):
            logger.error("Column index out of bounds in _get_ordering: %s %s", column_filters, context["fields"])

        # Extract field and name from context fields
        field_name, _display_name = context["fields"][column_index - 1]

        # Handle special case for run field with search capability
        if field_name == "run":
            field_name = "run__search"
            additional_field = context.get("afield")
            if additional_field:
                field_name = f"{additional_field}__{field_name}"
        # Skip fields that have custom callback handlers
        elif field_name in context.get("callbacks", {}):
            continue

        # Map field to search fields using field_map or use as single field
        search_fields = field_map.get(field_name, [field_name])

        # Build OR query for all mapped fields with case-insensitive search
        q_filter = Q()
        for search_field in search_fields:
            q_filter |= Q(**{f"{search_field}__icontains": filter_value})

        # Apply the filter to the queryset
        queryset = queryset.filter(q_filter)

    return queryset


def _get_ordering(context: dict, column_order: list) -> list[str]:
    """Get database ordering fields from DataTables column order specification.

    Args:
        context: Context dictionary containing 'fields' list and optional 'callbacks' dict
        column_order: List of column indices as strings, negative values indicate descending order

    Returns:
        List of Django ORM ordering field names with '-' prefix for descending order

    """
    ordering_fields = []

    # Get field mapping for any field name transformations
    field_map = _get_field_map()

    for column_index in column_order:
        # Convert column index to integer, skip if invalid
        column_index_int = int(column_index)
        if not column_index_int:
            continue

        # Determine sort direction from sign of column index
        is_ascending = True
        if column_index_int < 0:
            is_ascending = False
            column_index_int = -column_index_int

        # Validate column index is within bounds
        if column_index_int >= len(context["fields"]):
            logger.error("Column index out of bounds in _get_ordering: %s %s", column_order, context["fields"])
        field_name, _display_name = context["fields"][column_index_int - 1]

        # Skip callback fields as they can't be used for database ordering
        if field_name in context.get("callbacks", {}):
            continue

        # Map field name if transformation exists, otherwise use as-is
        mapped_fields = field_map.get(field_name, [field_name])

        # Add ordering fields with proper direction prefix
        for mapped_field in mapped_fields:
            if is_ascending:
                ordering_fields.append(mapped_field)
            else:
                ordering_fields.append(f"-{mapped_field}")

    return ordering_fields


def _get_field_map() -> dict[str, list[str]]:
    """Return field mapping for member-related queries."""
    return {"member": ["member__surname", "member__name"]}


def _get_query_params(request: HttpRequest) -> tuple[int, int, list[str], dict[str, str]]:
    """Extract pagination, ordering, and filtering parameters from DataTables request.

    Args:
        request: HTTP request object containing POST data from DataTables.

    Returns:
        A tuple containing:
            - start: Starting record index for pagination
            - length: Number of records to return
            - order: List of column names with ordering prefixes ('-' for desc)
            - filters: Dictionary mapping column names to search values

    """
    # Extract pagination parameters
    start = int(request.POST.get("start", 0))
    length = int(request.POST.get("length", 10))

    # Build ordering list from DataTables order parameters
    order = []
    for order_index in range(len(request.POST.getlist("order[0][column]"))):
        column_index = request.POST.get(f"order[{order_index}][column]")
        column_direction = request.POST.get(f"order[{order_index}][dir]")
        column_name = request.POST.get(f"columns[{column_index}][data]")

        # Add descending prefix if needed
        direction_prefix = "" if column_direction == "asc" else "-"
        order.append(direction_prefix + column_name)

    # Extract column-specific search filters
    filters = {}
    column_index = 0
    while True:
        column_name = request.POST.get(f"columns[{column_index}][data]")
        if column_name is None:
            break

        # Get fixed search term for this column
        search_value = request.POST.get(f"columns[{column_index}][search][fixed][0][term]")
        if search_value and not search_value.startswith("function"):
            filters[column_name] = search_value
        column_index += 1

    return start, length, order, filters


def _prepare_data_json(
    context: dict, elements: list, view: str, edit: str, *, is_executive: bool = True
) -> list[dict[str, str]]:
    """Prepare data for JSON response in DataTables format.

    Args:
        context: Context dictionary containing fields, callbacks, and optionally run
        elements: List of model objects to process
        view: View name for generating edit URLs
        edit: Tooltip text for edit links
        is_executive: Whether to use executive view URLs (True) or organization view URLs (False)

    Returns:
        List of dictionaries where each dict represents a row with string keys
        corresponding to column indices and HTML/text values

    """
    table_rows_data = []

    # Map field names to lambda functions for data extraction and formatting
    field_to_formatter = {
        "created": lambda model_object: model_object.created.strftime("%d/%m/%Y"),
        "payment_date": lambda model_object: model_object.created.strftime("%d/%m/%Y"),
        "member": lambda model_object: str(model_object.member),
        "run": lambda model_object: str(model_object.run) if model_object.run else "",
        "descr": lambda model_object: str(model_object.descr),
        # Convert decimal values to int if they're whole numbers, otherwise keep as string
        "value": lambda model_object: int(model_object.value)
        if model_object.value == model_object.value.to_integral()
        else str(model_object.value),
        "details": lambda model_object: str(model_object.details),
        "credits": lambda model_object: int(model_object.credits)
        if model_object.credits == model_object.credits.to_integral()
        else str(model_object.credits),
        "info": lambda model_object: str(model_object.info) if model_object.info else "",
        "vat_ticket": lambda model_object: round(float(model_object.vat_ticket), 2),
        "vat_options": lambda model_object: round(float(model_object.vat_options), 2),
    }

    # Allow custom field callbacks to override default mappings
    if "callbacks" in context:
        field_to_formatter.update(context["callbacks"])

    # Process each element and build row data
    for model_object in elements:
        # Generate appropriate URL based on view type (exe vs orga)
        if is_executive:
            edit_url = reverse(view, args=[model_object.id])
        else:
            # For orga views, we need both slug and ID
            edit_url = reverse(view, args=[context["run"].get_slug(), model_object.id])

        # Start each row with edit link in column 0
        row_data = {"0": f'<a href="{edit_url}" qtip="{edit}"><i class="fas fa-edit"></i></a>'}

        # Add data for each configured field, starting from column 1
        for column_index, (field_name, _field_label) in enumerate(context["fields"], start=1):
            row_data[str(column_index)] = field_to_formatter.get(field_name, lambda _model_object: "")(model_object)

        table_rows_data.append(row_data)

    return table_rows_data


def _apply_custom_queries(context: dict[str, Any], elements: QuerySet, typ: type[Model]) -> QuerySet:
    """Apply custom queries and optimizations based on model type.

    Args:
        context: Context dictionary containing request data and parameters
        elements: Base queryset to apply modifications to
        typ: Model class type to determine which optimizations to apply

    Returns:
        Modified queryset with applied select_related, prefetch_related,
        annotations, and ordering based on the model type

    """
    # Apply select_related optimization for AccountingItem and subclasses
    if issubclass(typ, AccountingItem):
        elements = elements.select_related("member")

    # Handle AccountingItemExpense with member relation and approval-based ordering
    if issubclass(typ, AccountingItemExpense):
        elements = elements.select_related("member").order_by("is_approved", "-created")

    # Handle PaymentInvoice with submission status annotation and ordering
    elif issubclass(typ, PaymentInvoice):
        elements = elements.annotate(
            is_submitted=Case(
                When(status=PaymentStatus.SUBMITTED, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        elements = elements.order_by("is_submitted", "-created")

    # Handle RefundRequest with membership prefetch and credit annotation
    elif issubclass(typ, RefundRequest):
        elements = elements.prefetch_related("member__memberships")
        elements = elements.order_by("-status", "-updated")

        # Subquery to get the latest membership credit for each member
        latest_membership_subquery = Membership.objects.filter(
            member_id=OuterRef("member_id"),
            association_id=context["association_id"],
        ).order_by("id")[:1]
        elements = elements.annotate(credits=Subquery(latest_membership_subquery.values("credit")))

    # Handle AccountingItemPayment with transaction calculations
    elif issubclass(typ, AccountingItemPayment):
        # Get field definition for proper decimal handling
        # noinspection PyUnresolvedReferences, PyProtectedMember
        value_field = AccountingItemPayment._meta.get_field("value")  # noqa: SLF001  # Django model metadata
        decimal_field = DecimalField(max_digits=value_field.max_digits, decimal_places=value_field.decimal_places)

        # Define zero value with proper decimal field type
        zero_value = Value(Decimal(0), output_field=decimal_field)

        # Subquery to calculate total transaction value per invoice
        transaction_total_subquery = (
            AccountingItemTransaction.objects.filter(inv_id=OuterRef("inv_id"))
            .values("inv_id")
            .annotate(total=Coalesce(Cast(F("value"), output_field=decimal_field), zero_value))
            .values("total")[:1]
        )

        transaction_total = Subquery(transaction_total_subquery, output_field=decimal_field)

        # Annotate with transaction totals and net calculations
        elements = elements.annotate(
            trans=Coalesce(transaction_total, zero_value),
            net=ExpressionWrapper(F("value") - Coalesce(transaction_total, zero_value), output_field=decimal_field),
        )
    # Default ordering for other model types
    else:
        elements = elements.order_by("-created")

    # Apply subtype-specific filters based on context
    subtype = context.get("subtype")
    if subtype == "credits":
        elements = elements.filter(oth=OtherChoices.CREDIT)
    elif subtype == "tokens":
        elements = elements.filter(oth=OtherChoices.TOKEN)

    return elements


def exe_paginate(
    request: HttpRequest,
    context: dict[str, Any],
    pagination_model: type[Model],
    template_name: str,
    view_name: str,
) -> HttpResponse:
    """Paginate content for organization-wide executive views."""
    return paginate(request, context, pagination_model, template_name, view_name, is_executive=True)


def orga_paginate(
    request: HttpRequest,
    context: dict,
    pagination_model: type[Model],
    template_name: str,
    view_name: str,
) -> HttpResponse:
    """Paginate items for organization views."""
    return paginate(request, context, pagination_model, template_name, view_name, is_executive=False)
