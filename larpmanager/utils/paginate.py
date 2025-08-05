from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, OuterRef, Subquery, Value, When
from django.utils.translation import gettext_lazy as _

from larpmanager.models.accounting import (
    AccountingItem,
    AccountingItemExpense,
    AccountingItemOther,
    PaymentInvoice,
    PaymentStatus,
    RefundRequest,
)
from larpmanager.models.event import Run
from larpmanager.models.member import Membership


def paginate(request, ctx, typ, exe, selrel, show_runs, afield, subtype):
    cls = typ
    if hasattr(typ, "objects"):
        cls = typ.objects
    else:
        typ = typ.model

    elements = cls.filter(assoc_id=ctx["a_id"])

    # noinspection PyProtectedMember
    if "hide" in [f.name for f in typ._meta.get_fields()]:
        elements = elements.filter(hide=False)

    run = -1
    page = 1
    search = ""
    size = 20

    if request.method == "POST":
        run = int(request.POST.get("run", "-1"))
        page = int(request.POST.get("page", 0))
        search = request.POST.get("search", "")
        size = int(request.POST.get("size", 20))

    elements, run = _apply_run_queries(afield, ctx, elements, exe, run)

    elements = _apply_custom_queries(ctx, elements, subtype, typ)

    if selrel:
        for e in selrel:
            elements = elements.select_related(e)
    if search:
        elements = elements.filter(search__icontains=search)

    elements = elements.order_by("-created")

    size = 1000
    paginator = Paginator(elements, per_page=size)
    page = min(page, paginator.num_pages)

    ctx["exe"] = exe

    ctx["pagin"] = paginator
    ctx["page"] = page
    ctx["size"] = size
    ctx["size_range"] = [20, 50, 100, 150, 200, 250, 500, 1000, 2000, 5000]

    if page > 0:
        ctx["list"] = paginator.page(page)
    else:
        ctx["list"] = elements.all()

    ctx["search"] = search

    if exe:
        ctx["show_runs"] = show_runs
        ctx["runs"] = [(-1, _("All")), (0, "Assoc")] + [
            (r.id, str(r))
            for r in Run.objects.filter(event__assoc_id=ctx["a_id"], end__isnull=False)
            .select_related("event")
            .order_by("-end")
        ]
        ctx["run_sel"] = run


def _apply_run_queries(afield, ctx, elements, exe, run):
    if not exe:
        run = ctx["run"].id
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


def _apply_custom_queries(ctx, elements, subtype, typ):
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
    if subtype == "credits":
        elements = elements.filter(oth=AccountingItemOther.CREDIT)

    elif subtype == "tokens":
        elements = elements.filter(oth=AccountingItemOther.TOKEN)
    return elements


def exe_paginate(request, ctx, typ, selrel=None, show_runs=True, afield=None, subtype=None):
    paginate(request, ctx, typ, True, selrel, show_runs, afield, subtype)


def orga_paginate(request, ctx, typ, selrel=None, show_runs=False, afield=None, subtype=None):
    paginate(request, ctx, typ, False, selrel, show_runs, afield, subtype)
