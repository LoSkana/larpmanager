from django.db.models import Case, IntegerField, OuterRef, Q, Subquery, Value, When
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.models.accounting import (
    AccountingItem,
    AccountingItemExpense,
    AccountingItemOther,
    PaymentInvoice,
    PaymentStatus,
    RefundRequest,
)
from larpmanager.models.member import Membership


def paginate(request, ctx, typ, template, view, exe=True):
    cls = typ.objects
    class_name = typ._meta.model_name

    if request.method != "POST":
        ctx["table_name"] = f"{class_name}_{ctx['a_id'] if exe else ctx['run'].id}"

        return render(request, template, ctx)

    draw = int(request.POST.get("draw", 0))

    elements = _get_elements_query(cls, ctx, request, typ)

    records_total = typ.objects.count()
    records_filtered = len(elements)

    edit = _("Edit")
    data = _prepare_data_json(ctx, elements, view, edit)

    return JsonResponse(
        {
            "draw": draw,
            "recordsTotal": records_total,
            "recordsFiltered": records_filtered,
            "data": data,
        }
    )


def _get_elements_query(cls, ctx, request, typ):
    start, length, order, filters = _get_query_params(request)

    elements = cls.filter(assoc_id=ctx["a_id"])

    # noinspection PyProtectedMember
    if "hide" in [f.name for f in typ._meta.get_fields()]:
        elements = elements.filter(hide=False)

    selrel = ctx.get("selrel")
    if selrel:
        for e in selrel:
            elements = elements.select_related(e)

    # elements, run = _apply_run_queries(ctx, elements, exe, run)

    elements = _apply_custom_queries(ctx, elements, typ)

    elements = _set_filtering(ctx, elements, filters)

    ordering = _get_ordering(ctx, order)
    elements = elements.order_by(*ordering)

    elements = elements[start : start + length]

    return elements


def _set_filtering(ctx, elements, filters):
    field_map = _get_field_map()

    for column, value in filters.items():
        column_ix = int(column)
        if column_ix >= len(ctx["fields"]):
            print(f"this shouldn't happen! _get_ordering {filters} {ctx['fields']}")
        field, name = ctx["fields"][column_ix - 1]

        if field in ctx.get("callbacks", {}):
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

    ordering.append("-created")
    return ordering


def _get_field_map():
    field_map = {"member": ["member__surname", "member__name"], "run": ["run__search"]}
    return field_map


def _get_query_params(request):
    start = int(request.POST.get("start", 0))
    length = int(request.POST.get("length", 10))

    order = []
    for i in range(len(request.POST.getlist("order[0][column]"))):
        col_idx = request.POST.get(f"order[{i}][column]")
        dir = request.POST.get(f"order[{i}][dir]")
        col_name = request.POST.get(f"columns[{col_idx}][data]")
        prefix = "" if dir == "asc" else "-"
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


def _prepare_data_json(ctx, elements, view, edit):
    # TODO apply changes based on fields
    data = []

    field_map = {
        "created": lambda row: row.created.strftime("%d/%m/%Y"),
        "payment_date": lambda row: row.created.strftime("%d/%m/%Y"),
        "member": lambda row: str(row.member),
        "run": lambda row: str(row.run) if row.run else "",
        "descr": lambda row: str(row.descr),
        "value": lambda row: int(row.value) if row.value == row.value.to_integral() else str(row.value),
    }

    if "callbacks" in ctx:
        field_map.update(ctx["callbacks"])

    for row in elements:
        url = reverse(view, args=[row.id])
        res = {"0": f'<a href="{url}" qtip="{edit}"><i class="fas fa-edit"></i></a>'}
        for idx, (field, _name) in enumerate(ctx["fields"], start=1):
            res[str(idx)] = field_map.get(field, lambda r: "")(row)
        data.append(res)

    return data


def _apply_run_queries(ctx, elements, exe, run):
    if not exe:
        run = ctx["run"].id
    afield = ctx.get("afield")
    if run >= 0:
        if run == 0:
            if afield:
                kwargs = {f"{afield}__run__isnull": True}
                elements = elements.filter(**kwargs)
            else:
                elements = elements.filter(run__isnull=True)
        elif afield:
            kwargs = {f"{afield}__run": run}
            elements = elements.filter(**kwargs)
        else:
            elements = elements.filter(run=run)
    return elements, run


def _apply_custom_queries(ctx, elements, typ):
    if issubclass(typ, AccountingItem):
        elements = elements.select_related("member")
    if issubclass(typ, AccountingItemExpense):
        elements = elements.select_related("member").order_by("is_approved", "-created")
    if issubclass(typ, PaymentInvoice):
        elements = elements.annotate(
            is_submitted=Case(
                When(status=PaymentStatus.SUBMITTED, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        elements = elements.order_by("is_submitted", "-created")
    if issubclass(typ, RefundRequest):
        elements = elements.prefetch_related("member__memberships")
        elements = elements.order_by("-status", "-updated")

        memberships = Membership.objects.filter(member_id=OuterRef("member_id"), assoc_id=ctx["a_id"]).order_by("id")[
            :1
        ]
        elements = elements.annotate(credits=Subquery(memberships.values("credit")))

    subtype = ctx.get("subtype")
    if subtype == "credits":
        elements = elements.filter(oth=AccountingItemOther.CREDIT)
    elif subtype == "tokens":
        elements = elements.filter(oth=AccountingItemOther.TOKEN)

    return elements


def exe_paginate(request, ctx, typ, template, view):
    return paginate(request, ctx, typ, template, view, True)


def orga_paginate(request, ctx, typ, template, view):
    return paginate(request, ctx, typ, template, view, False)
