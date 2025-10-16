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
from django.http import JsonResponse
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


def paginate(request, ctx, typ, template, view, exe=True):
    cls = typ.objects
    # noinspection PyProtectedMember
    class_name = typ._meta.model_name

    if request.method != "POST":
        if exe:
            ctx["table_name"] = f"{class_name}_{ctx['a_id']}"
        else:
            ctx["table_name"] = f"{class_name}_{ctx['run'].get_slug()}"

        return render(request, template, ctx)

    draw = int(request.POST.get("draw", 0))

    elements, records_filtered = _get_elements_query(cls, ctx, request, typ, exe)

    records_total = typ.objects.count()

    edit = _("Edit")
    data = _prepare_data_json(ctx, elements, view, edit, exe)

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


def _set_filtering(ctx, elements, filters):
    field_map = _get_field_map()

    for column, value in filters.items():
        column_ix = int(column)
        if column_ix >= len(ctx["fields"]):
            print(f"this shouldn't happen! _get_ordering {filters} {ctx['fields']}")
        field, name = ctx["fields"][column_ix - 1]

        if field == "run":
            field = "run__search"
            afield = ctx.get("afield")
            if afield:
                field = f"{afield}__{field}"
        elif field in ctx.get("callbacks", {}):
            continue

        if field in field_map:
            field = field_map[field]
        else:
            field = [field]

        q_filter = Q()
        for el in field:
            q_filter |= Q(**{f"{el}__icontains": value})

        elements = elements.filter(q_filter)

    return elements


def _get_ordering(ctx, order):
    ordering = []

    field_map = _get_field_map()

    for column in order:
        column_ix = int(column)
        if not column_ix:
            continue

        asc = True
        if column_ix < 0:
            asc = False
            column_ix = -column_ix

        if column_ix >= len(ctx["fields"]):
            print(f"this shouldn't happen! _get_ordering {order} {ctx['fields']}")
        field, name = ctx["fields"][column_ix - 1]

        if field in ctx.get("callbacks", {}):
            continue

        if field in field_map:
            field = field_map[field]
        else:
            field = [field]

        for el in field:
            if asc:
                ordering.append(el)
            else:
                ordering.append(f"-{el}")

    return ordering


def _get_field_map():
    field_map = {"member": ["member__surname", "member__name"]}
    return field_map


def _get_query_params(request):
    start = int(request.POST.get("start", 0))
    length = int(request.POST.get("length", 10))

    order = []
    for i in range(len(request.POST.getlist("order[0][column]"))):
        col_idx = request.POST.get(f"order[{i}][column]")
        col_dir = request.POST.get(f"order[{i}][dir]")
        col_name = request.POST.get(f"columns[{col_idx}][data]")
        prefix = "" if col_dir == "asc" else "-"
        order.append(prefix + col_name)

    filters = {}
    i = 0
    while True:
        col_name = request.POST.get(f"columns[{i}][data]")
        if col_name is None:
            break

        search_value = request.POST.get(f"columns[{i}][search][fixed][0][term]")
        if search_value and not search_value.startswith("function"):
            filters[col_name] = search_value
        i += 1

    return start, length, order, filters


def _prepare_data_json(ctx, elements, view, edit, exe=True):
    data = []

    field_map = {
        "created": lambda obj: obj.created.strftime("%d/%m/%Y"),
        "payment_date": lambda obj: obj.created.strftime("%d/%m/%Y"),
        "member": lambda obj: str(obj.member),
        "run": lambda obj: str(obj.run) if obj.run else "",
        "descr": lambda obj: str(obj.descr),
        "value": lambda obj: int(obj.value) if obj.value == obj.value.to_integral() else str(obj.value),
        "details": lambda obj: str(obj.details),
        "credits": lambda obj: int(obj.credits) if obj.credits == obj.credits.to_integral() else str(obj.credits),
        "info": lambda obj: str(obj.info) if obj.info else "",
        "vat_ticket": lambda obj: round(float(obj.vat_ticket), 2),
        "vat_options": lambda obj: round(float(obj.vat_options), 2),
    }

    if "callbacks" in ctx:
        field_map.update(ctx["callbacks"])

    for row in elements:
        if exe:
            url = reverse(view, args=[row.id])
        else:
            # For orga views, we need both slug and ID
            url = reverse(view, args=[ctx["run"].get_slug(), row.id])
        res = {"0": f'<a href="{url}" qtip="{edit}"><i class="fas fa-edit"></i></a>'}
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
