from django.db.models import Case, IntegerField, OuterRef, Subquery, Value, When
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
    cls = typ
    if hasattr(typ, "objects"):
        cls = typ.objects
        class_name = typ._meta.model_name
    else:
        typ = typ.model
        class_name = typ._meta.model_name

    if request.method != "POST":
        if exe:
            ctx["table_name"] = f"{class_name}_{ctx['a_id']}"
        else:
            ctx["table_name"] = f"{class_name}_{ctx['run'].id}"

        return render(request, template, ctx)

    draw = int(request.POST.get("draw", 0))
    start = int(request.POST.get("start", 0))
    length = int(request.POST.get("length", 10))
    search_value = request.POST.get("search[value]", "")
    order = []
    for i in range(len(request.POST.getlist("order[0][column]"))):
        col_idx = request.POST.get(f"order[{i}][column]")
        dir = request.POST.get(f"order[{i}][dir]")
        col_name = request.POST.get(f"columns[{col_idx}][data]")
        prefix = "" if dir == "asc" else "-"
        order.append(prefix + col_name)

    elements = cls.filter(assoc_id=ctx["a_id"])

    # noinspection PyProtectedMember
    if "hide" in [f.name for f in typ._meta.get_fields()]:
        elements = elements.filter(hide=False)

    selrel = ctx.get("selrel")
    if selrel:
        for e in selrel:
            elements = elements.select_related(e)
    if search_value:
        elements = elements.filter(search__icontains=search_value)

    if order:
        for column in order:
            column_ix = int(column)
            if not column_ix:
                continue
            # TODO ordering on fields
            # especially run
            # elements = elements.order_by(*order)

    run = 0  # TODO fix
    # elements, run = _apply_run_queries(ctx, elements, exe, run)

    elements = _apply_custom_queries(ctx, elements, typ)

    elements = elements.order_by("-created")
    elements = elements[start : start + length]

    records_total = typ.objects.count()
    records_filtered = len(elements)

    values = [el[0] for el in ctx["fields"]]

    # TODO apply changes based on fields
    data = []
    edit = _("Edit")
    for row in elements:
        url = reverse(view, args=[row.id])
        res = {"0": f'<a href="{url}" qtip="{edit}"><i class="fas fa-edit"></i></a>'}
        cnt = 1
        for field, name in ctx["fields"]:
            idx = str(cnt)
            if field == "created":
                res[idx] = row.created.strftime("%d/%m/%Y")
            elif field == "member":
                res[idx] = str(row.member)
            elif field == "run":
                res[idx] = str(row.run)
            elif field == "descr":
                res[idx] = str(row.descr)
            elif field == "value":
                val = row.value
                res[idx] = int(val) if val == val.to_integral() else str(val)
            cnt += 1
        data.append(res)

    return JsonResponse(
        {
            "draw": draw,
            "recordsTotal": records_total,
            "recordsFiltered": records_filtered,
            "data": data,
        }
    )


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
