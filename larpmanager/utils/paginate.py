from decimal import Decimal
from typing import Any, Union

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
    request: HttpRequest, ctx: dict[str, Any], typ: type[Model], template: str, view: str, exe: bool = True
) -> Union[HttpResponse, JsonResponse]:
    """Paginate objects for DataTables with support for both GET and POST requests.

    Args:
        request: The HTTP request object
        ctx: Template context dictionary containing pagination data
        typ: Django model class to paginate
        template: Template path for GET requests
        view: View name for generating edit URLs
        exe: Whether this is an organization-wide (True) or event-specific (False) view

    Returns:
        HttpResponse for GET requests (renders template)
        JsonResponse for POST requests (returns DataTables JSON format)
    """
    cls = typ.objects
    # Extract model name from Django model metadata for table naming
    # noinspection PyProtectedMember
    class_name = typ._meta.model_name

    # Handle GET requests - render template with table configuration
    if request.method != "POST":
        # Generate unique table name based on context type
        if exe:
            # Organization-wide table uses association ID
            ctx["table_name"] = f"{class_name}_{ctx['a_id']}"
        else:
            # Event-specific table uses run slug
            ctx["table_name"] = f"{class_name}_{ctx['run'].get_slug()}"

        return render(request, template, ctx)

    # Handle POST requests - return DataTables JSON response
    # Extract draw parameter for DataTables synchronization
    draw = int(request.POST.get("draw", 0))

    # Get filtered elements and count based on DataTables parameters
    elements, records_filtered = _get_elements_query(cls, ctx, request, typ, exe)

    # Get total count of all records (unfiltered)
    records_total = typ.objects.count()

    # Prepare localized edit button text
    edit = _("Edit")
    # Transform elements into DataTables-compatible JSON data
    data = _prepare_data_json(ctx, elements, view, edit, exe)

    # Return DataTables-formatted JSON response
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


def _set_filtering(ctx: dict, elements, filters: dict) -> object:
    """Apply filtering to elements based on provided filters and context.

    Args:
        ctx: Context dictionary containing fields and optional callbacks/afield
        elements: QuerySet or collection to filter
        filters: Dictionary mapping column indices to filter values

    Returns:
        Filtered elements collection
    """
    # Get field mapping configuration
    field_map = _get_field_map()

    # Process each filter column and value
    for column, value in filters.items():
        column_ix = int(column)

        # Validate column index bounds
        if column_ix >= len(ctx["fields"]):
            print(f"this shouldn't happen! _get_ordering {filters} {ctx['fields']}")

        # Extract field and name from context
        field, name = ctx["fields"][column_ix - 1]

        # Handle special 'run' field case with optional afield prefix
        if field == "run":
            field = "run__search"
            afield = ctx.get("afield")
            if afield:
                field = f"{afield}__{field}"
        # Skip fields that have custom callbacks defined
        elif field in ctx.get("callbacks", {}):
            continue

        # Map field to actual database fields (single or multiple)
        if field in field_map:
            field = field_map[field]
        else:
            field = [field]

        # Build OR query for all mapped fields with icontains lookup
        q_filter = Q()
        for el in field:
            q_filter |= Q(**{f"{el}__icontains": value})

        # Apply the filter to elements
        elements = elements.filter(q_filter)

    return elements


def _get_ordering(ctx: dict, order: list) -> list[str]:
    """
    Generate ordering list for database queries based on column specifications.

    Args:
        ctx: Context dictionary containing 'fields' list and optional 'callbacks' dict
        order: List of column indices as strings, negative values indicate descending order

    Returns:
        List of field names with optional '-' prefix for descending order

    Example:
        >>> ctx = {'fields': [('name', 'Name'), ('created', 'Created')]}
        >>> _get_ordering(ctx, ['1', '-2'])
        ['name', '-created']
    """
    ordering = []

    # Get field mapping for any field name transformations
    field_map = _get_field_map()

    # Process each column specification in the order list
    for column in order:
        column_ix = int(column)
        if not column_ix:
            continue

        # Determine sort direction from column index sign
        asc = True
        if column_ix < 0:
            asc = False
            column_ix = -column_ix

        # Validate column index is within bounds
        if column_ix >= len(ctx["fields"]):
            print(f"this shouldn't happen! _get_ordering {order} {ctx['fields']}")
        field, name = ctx["fields"][column_ix - 1]

        # Skip fields that have callback functions (non-database fields)
        if field in ctx.get("callbacks", {}):
            continue

        # Apply field mapping or use field as-is
        if field in field_map:
            field = field_map[field]
        else:
            field = [field]

        # Add ordering specification for each field element
        for el in field:
            if asc:
                ordering.append(el)
            else:
                ordering.append(f"-{el}")

    return ordering


def _get_field_map():
    field_map = {"member": ["member__surname", "member__name"]}
    return field_map


def _get_query_params(request: HttpRequest) -> tuple[int, int, list[str], dict[str, str]]:
    """Extract query parameters from DataTables request.

    Args:
        request: Django HttpRequest object containing POST data with DataTables parameters

    Returns:
        tuple: Contains (start, length, order, filters) where:
            - start: Starting record index for pagination
            - length: Number of records to return
            - order: List of column names with sort direction prefixes
            - filters: Dictionary mapping column names to search values
    """
    # Extract pagination parameters with defaults
    start = int(request.POST.get("start", 0))
    length = int(request.POST.get("length", 10))

    # Build ordering list from DataTables sort parameters
    order = []
    for i in range(len(request.POST.getlist("order[0][column]"))):
        col_idx = request.POST.get(f"order[{i}][column]")
        col_dir = request.POST.get(f"order[{i}][dir]")
        col_name = request.POST.get(f"columns[{col_idx}][data]")

        # Add descending prefix for Django ORM ordering
        prefix = "" if col_dir == "asc" else "-"
        order.append(prefix + col_name)

    # Extract column filters from search parameters
    filters = {}
    i = 0
    while True:
        col_name = request.POST.get(f"columns[{i}][data]")
        if col_name is None:
            break

        # Get fixed search term, skip function-based searches
        search_value = request.POST.get(f"columns[{i}][search][fixed][0][term]")
        if search_value and not search_value.startswith("function"):
            filters[col_name] = search_value
        i += 1

    return start, length, order, filters


def _prepare_data_json(ctx: dict, elements: list, view: str, edit: str, exe: bool = True) -> list[dict[str, str]]:
    """
    Prepare data for JSON response in DataTables format.

    Args:
        ctx: Context dictionary containing fields, callbacks, and run information
        elements: List of objects to process
        view: Name of the view for generating URLs
        edit: Tooltip text for edit links
        exe: If True, generate executive URLs; if False, generate organization URLs

    Returns:
        List of dictionaries with string keys and values for DataTables
    """
    data = []

    # Define field mapping functions for common object attributes
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

    # Override default field mappings with custom callbacks if provided
    if "callbacks" in ctx:
        field_map.update(ctx["callbacks"])

    # Process each element to create DataTables row data
    for row in elements:
        # Generate appropriate URL based on context (executive vs organization)
        if exe:
            url = reverse(view, args=[row.id])
        else:
            # For orga views, we need both slug and ID
            url = reverse(view, args=[ctx["run"].get_slug(), row.id])

        # Create edit link as first column (index "0")
        res = {"0": f'<a href="{url}" qtip="{edit}"><i class="fas fa-edit"></i></a>'}

        # Add data columns using field mappings
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
