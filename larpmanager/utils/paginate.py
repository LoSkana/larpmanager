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


def paginate(
    request: HttpRequest, ctx: dict, typ: type[Model], template: str, view: str, exe: bool = True
) -> HttpResponse | JsonResponse:
    """
    Handle pagination for DataTables AJAX requests and initial page renders.

    Args:
        request: The HTTP request object
        ctx: Context dictionary containing template variables
        typ: Django model class to paginate
        template: Template path for initial render
        view: View name for generating edit URLs
        exe: Whether this is an organization-wide view (True) or event-specific (False)

    Returns:
        HttpResponse for GET requests (initial page render)
        JsonResponse for POST requests (DataTables AJAX data)
    """
    cls = typ.objects
    # Extract model name for table identification
    # noinspection PyProtectedMember
    class_name = typ._meta.model_name

    # Handle initial page load (GET request)
    if request.method != "POST":
        # Set unique table name based on context type
        if exe:
            ctx["table_name"] = f"{class_name}_{ctx['a_id']}"
        else:
            ctx["table_name"] = f"{class_name}_{ctx['run'].get_slug()}"

        return render(request, template, ctx)

    # Handle DataTables AJAX request (POST)
    # Extract draw parameter for DataTables synchronization
    draw = int(request.POST.get("draw", 0))

    # Get filtered elements and count based on search/filter criteria
    elements, records_filtered = _get_elements_query(cls, ctx, request, typ, exe)

    # Get total record count (unfiltered)
    records_total = typ.objects.count()

    # Prepare localized strings for UI
    edit = _("Edit")

    # Transform model instances into JSON-serializable data
    data = _prepare_data_json(ctx, elements, view, edit, exe)

    # Return DataTables-compatible JSON response
    return JsonResponse(
        {
            "draw": draw,
            "recordsTotal": records_total,
            "recordsFiltered": records_filtered,
            "data": data,
        }
    )


def _get_elements_query(cls, ctx: dict, request, typ, exe: bool = True) -> tuple[any, int]:
    """
    Get filtered and paginated query elements based on context and request parameters.

    Args:
        cls: The model class to query
        ctx: Context dictionary containing association ID, run, event, and other filters
        request: HTTP request object containing query parameters
        typ: Model type for field inspection
        exe: Whether this is an executive (organization-wide) view or event-specific view

    Returns:
        tuple: (filtered_elements_queryset, total_filtered_count)
    """
    # Extract pagination and filtering parameters from request
    start, length, order, filters = _get_query_params(request)

    # Start with base queryset filtered by association
    elements = cls.filter(assoc_id=ctx["a_id"])

    # Apply event-specific filtering for non-executive views
    if not exe and "run" in ctx:
        # Check which relation field exists on the model to filter by run/event
        # noinspection PyProtectedMember
        field_names = [f.name for f in typ._meta.get_fields()]
        if "run" in field_names:
            elements = elements.filter(run=ctx["run"])
        elif "reg" in field_names:
            elements = elements.filter(reg__run=ctx["run"])
        elif "event" in field_names:
            elements = elements.filter(event=ctx["event"])

    # Filter out hidden elements if the model supports it
    # noinspection PyProtectedMember
    if "hide" in [f.name for f in typ._meta.get_fields()]:
        elements = elements.filter(hide=False)

    # Apply select_related optimization if specified in context
    selrel = ctx.get("selrel")
    if selrel:
        for e in selrel:
            elements = elements.select_related(e)

    # Apply any custom query modifications defined in context
    elements = _apply_custom_queries(ctx, elements, typ)

    # Apply user-defined filters from the request
    elements = _set_filtering(ctx, elements, filters)

    # Count filtered records before applying pagination
    records_filtered = elements.count()

    # Apply ordering if specified in context
    ordering = _get_ordering(ctx, order)
    if ordering:
        elements = elements.order_by(*ordering)

    # Apply pagination using slice notation
    elements = elements[start : start + length]

    return elements, records_filtered


def _set_filtering(ctx: dict, elements: QuerySet, filters: dict) -> QuerySet:
    """
    Apply filtering to a QuerySet based on provided filters and field mappings.

    Args:
        ctx: Context dictionary containing fields, callbacks, and optional afield
        elements: Django QuerySet to filter
        filters: Dictionary mapping column indices to filter values

    Returns:
        Filtered QuerySet with applied filters

    Note:
        Handles special cases for 'run' fields and callback fields. Uses field
        mappings for complex field relationships and applies case-insensitive
        filtering with OR conditions for multiple mapped fields.
    """
    # Get field mapping configuration for complex field relationships
    field_map = _get_field_map()

    # Process each filter by column index and value
    for column, value in filters.items():
        column_ix = int(column)

        # Validate column index against available fields
        if column_ix >= len(ctx["fields"]):
            print(f"this shouldn't happen! _get_ordering {filters} {ctx['fields']}")

        # Extract field name and display name from context
        field, name = ctx["fields"][column_ix - 1]

        # Handle special case for 'run' field with search optimization
        if field == "run":
            field = "run__search"
            afield = ctx.get("afield")
            # Apply additional field prefix if available
            if afield:
                field = f"{afield}__{field}"
        # Skip fields that have callback handlers
        elif field in ctx.get("callbacks", {}):
            continue

        # Apply field mapping or use single field as list
        if field in field_map:
            field = field_map[field]
        else:
            field = [field]

        # Build OR query for multiple field mappings with case-insensitive search
        q_filter = Q()
        for el in field:
            q_filter |= Q(**{f"{el}__icontains": value})

        # Apply the constructed filter to the QuerySet
        elements = elements.filter(q_filter)

    return elements


def _get_ordering(ctx: dict, order: list) -> list[str]:
    """Get database ordering fields from DataTables column order specification.

    Args:
        ctx: Context dictionary containing 'fields' list and optional 'callbacks' dict
        order: List of column indices as strings, negative values indicate descending order

    Returns:
        List of Django ORM ordering field names with '-' prefix for descending order
    """
    ordering = []

    # Get field mapping for any field name transformations
    field_map = _get_field_map()

    for column in order:
        # Convert column index to integer, skip if invalid
        column_ix = int(column)
        if not column_ix:
            continue

        # Determine sort direction from sign of column index
        asc = True
        if column_ix < 0:
            asc = False
            column_ix = -column_ix

        # Validate column index is within bounds
        if column_ix >= len(ctx["fields"]):
            print(f"this shouldn't happen! _get_ordering {order} {ctx['fields']}")
        field, name = ctx["fields"][column_ix - 1]

        # Skip callback fields as they can't be used for database ordering
        if field in ctx.get("callbacks", {}):
            continue

        # Map field name if transformation exists, otherwise use as-is
        if field in field_map:
            field = field_map[field]
        else:
            field = [field]

        # Add ordering fields with proper direction prefix
        for el in field:
            if asc:
                ordering.append(el)
            else:
                ordering.append(f"-{el}")

    return ordering


def _get_field_map():
    field_map = {"member": ["member__surname", "member__name"]}
    return field_map


def _get_query_params(request) -> tuple[int, int, list[str], dict[str, str]]:
    """Extract and parse DataTables query parameters from POST request.

    Parses DataTables AJAX request parameters including pagination,
    ordering, and column filtering information.

    Args:
        request: HTTP request object containing POST data

    Returns:
        A tuple containing:
            - start: Starting record number for pagination
            - length: Number of records to return
            - order: List of column names with direction prefixes
            - filters: Dictionary mapping column names to filter values
    """
    # Extract pagination parameters
    start = int(request.POST.get("start", 0))
    length = int(request.POST.get("length", 10))

    # Parse ordering configuration
    order = []
    for i in range(len(request.POST.getlist("order[0][column]"))):
        col_idx = request.POST.get(f"order[{i}][column]")
        col_dir = request.POST.get(f"order[{i}][dir]")

        # Get column name and apply direction prefix
        col_name = request.POST.get(f"columns[{col_idx}][data]")
        prefix = "" if col_dir == "asc" else "-"
        order.append(prefix + col_name)

    # Extract column filters
    filters = {}
    i = 0
    while True:
        # Check if column exists at current index
        col_name = request.POST.get(f"columns[{i}][data]")
        if col_name is None:
            break

        # Get search term and validate it's not a function
        search_value = request.POST.get(f"columns[{i}][search][fixed][0][term]")
        if search_value and not search_value.startswith("function"):
            filters[col_name] = search_value
        i += 1

    return start, length, order, filters


def _prepare_data_json(ctx: dict, elements: list, view: str, edit: str, exe: bool = True) -> list[dict[str, str]]:
    """Prepare data for JSON response in DataTables format.

    Args:
        ctx: Context dictionary containing fields, callbacks, and optionally run
        elements: List of model objects to process
        view: View name for generating edit URLs
        edit: Tooltip text for edit links
        exe: Whether to use executive view URLs (True) or organization view URLs (False)

    Returns:
        List of dictionaries where each dict represents a row with string keys
        corresponding to column indices and HTML/text values
    """
    data = []

    # Map field names to lambda functions for data extraction and formatting
    field_map = {
        "created": lambda obj: obj.created.strftime("%d/%m/%Y"),
        "payment_date": lambda obj: obj.created.strftime("%d/%m/%Y"),
        "member": lambda obj: str(obj.member),
        "run": lambda obj: str(obj.run) if obj.run else "",
        "descr": lambda obj: str(obj.descr),
        # Convert decimal values to int if they're whole numbers, otherwise keep as string
        "value": lambda obj: int(obj.value) if obj.value == obj.value.to_integral() else str(obj.value),
        "details": lambda obj: str(obj.details),
        "credits": lambda obj: int(obj.credits) if obj.credits == obj.credits.to_integral() else str(obj.credits),
        "info": lambda obj: str(obj.info) if obj.info else "",
        "vat_ticket": lambda obj: round(float(obj.vat_ticket), 2),
        "vat_options": lambda obj: round(float(obj.vat_options), 2),
    }

    # Allow custom field callbacks to override default mappings
    if "callbacks" in ctx:
        field_map.update(ctx["callbacks"])

    # Process each element and build row data
    for row in elements:
        # Generate appropriate URL based on view type (exe vs orga)
        if exe:
            url = reverse(view, args=[row.id])
        else:
            # For orga views, we need both slug and ID
            url = reverse(view, args=[ctx["run"].get_slug(), row.id])

        # Start each row with edit link in column 0
        res = {"0": f'<a href="{url}" qtip="{edit}"><i class="fas fa-edit"></i></a>'}

        # Add data for each configured field, starting from column 1
        for idx, (field, _name) in enumerate(ctx["fields"], start=1):
            res[str(idx)] = field_map.get(field, lambda r: "")(row)

        data.append(res)

    return data


def _apply_custom_queries(ctx: dict[str, Any], elements: QuerySet, typ: type[Model]) -> QuerySet:
    """Apply custom queries and optimizations based on model type.

    Args:
        ctx: Context dictionary containing request data and parameters
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
            )
        )
        elements = elements.order_by("is_submitted", "-created")

    # Handle RefundRequest with membership prefetch and credit annotation
    elif issubclass(typ, RefundRequest):
        elements = elements.prefetch_related("member__memberships")
        elements = elements.order_by("-status", "-updated")

        # Subquery to get the latest membership credit for each member
        memberships = Membership.objects.filter(member_id=OuterRef("member_id"), assoc_id=ctx["a_id"]).order_by("id")[
            :1
        ]
        elements = elements.annotate(credits=Subquery(memberships.values("credit")))

    # Handle AccountingItemPayment with transaction calculations
    elif issubclass(typ, AccountingItemPayment):
        # Get field definition for proper decimal handling
        # noinspection PyUnresolvedReferences, PyProtectedMember
        val_field = AccountingItemPayment._meta.get_field("value")
        dec = DecimalField(max_digits=val_field.max_digits, decimal_places=val_field.decimal_places)

        # Define zero value with proper decimal field type
        zero = Value(Decimal("0"), output_field=dec)

        # Subquery to calculate total transaction value per invoice
        subq_base = (
            AccountingItemTransaction.objects.filter(inv_id=OuterRef("inv_id"))
            .values("inv_id")
            .annotate(total=Coalesce(Cast(F("value"), output_field=dec), zero))
            .values("total")[:1]
        )

        subq = Subquery(subq_base, output_field=dec)

        # Annotate with transaction totals and net calculations
        elements = elements.annotate(
            trans=Coalesce(subq, zero),
            net=ExpressionWrapper(F("value") - Coalesce(subq, zero), output_field=dec),
        )
    # Default ordering for other model types
    else:
        elements = elements.order_by("-created")

    # Apply subtype-specific filters based on context
    subtype = ctx.get("subtype")
    if subtype == "credits":
        elements = elements.filter(oth=OtherChoices.CREDIT)
    elif subtype == "tokens":
        elements = elements.filter(oth=OtherChoices.TOKEN)

    return elements


def exe_paginate(request, ctx, typ, template, view):
    return paginate(request, ctx, typ, template, view, True)


def orga_paginate(request, ctx, typ, template, view):
    return paginate(request, ctx, typ, template, view, False)
