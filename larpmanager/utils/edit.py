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

import time

from django.contrib import messages
from django.core.cache import cache
from django.db.models import Max
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import _get_fkey_config
from larpmanager.forms.utils import EventCharacterS2Widget
from larpmanager.models.association import Association
from larpmanager.models.form import QuestionApplicable, WritingAnswer, WritingChoice, WritingQuestion
from larpmanager.models.member import Log
from larpmanager.models.writing import Plot, PlotCharacterRel, Relationship, TextVersion
from larpmanager.utils.base import check_assoc_permission
from larpmanager.utils.common import html_clean
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.exceptions import NotFoundError


def save_log(member, cls, el, dl=False):
    Log.objects.create(member=member, cls=cls.__name__, eid=el.id, dl=dl, dct=el.as_dict())


def save_version(el, tp, mb, dl=False):
    n = TextVersion.objects.filter(tp=tp, eid=el.id).aggregate(Max("version"))["version__max"]
    if n is None:
        n = 1
    else:
        n += 1
    tv = TextVersion()
    tv.eid = el.id
    tv.tp = tp
    tv.version = n
    tv.member = mb
    tv.dl = dl

    if tp in QuestionApplicable.values:
        texts = []
        query = el.event.get_elements(WritingQuestion)
        for que in query.filter(applicable=tp).order_by("order"):
            value = _get_field_value(el, que)
            if not value:
                continue
            value = html_clean(value)
            texts.append(f"{que.name}: {value}")

        tv.text = "\n".join(texts)
    else:
        tv.text = el.text

    if tp == QuestionApplicable.CHARACTER:
        rels = Relationship.objects.filter(source=el)
        if rels:
            tv.text += "\nRelationships\n"
            for rel in rels:
                tv.text += f"{rel.target}: {html_clean(rel.text)}\n"

    if tp == QuestionApplicable.PLOT:
        chars = PlotCharacterRel.objects.filter(plot=el)
        if chars:
            tv.text += "\nCharacters\n"
            for rel in chars:
                tv.text += f"{rel.character}: {html_clean(rel.text)}\n"

    tv.save()


def _get_field_value(el, que):
    mapping = _get_values_mapping(el)

    if que.typ in mapping:
        return mapping[que.typ]()

    if que.typ in {"p", "t", "e"}:
        answers = WritingAnswer.objects.filter(question=que, element_id=el.id)
        if answers:
            return answers.first().text
        return ""

    if que.typ in {"s", "m"}:
        return ", ".join(c.option.name for c in WritingChoice.objects.filter(question=que, element_id=el.id))

    return None


def _get_values_mapping(el):
    mapping = {
        "text": lambda: el.text,
        "teaser": lambda: el.teaser,
        "name": lambda: el.name,
        "title": lambda: el.title,
        "faction": lambda: ", ".join([fac.name for fac in el.factions_list.all()]),
    }
    return mapping


def check_run(el, ctx, afield=None):
    if "run" not in ctx:
        return

    if afield:
        el = getattr(el, afield)

    if hasattr(el, "run") and el.run != ctx["run"]:
        raise Http404("not your run")

    if hasattr(el, "event"):
        is_child = ctx["event"].parent_id is not None
        event_matches = el.event_id == ctx["event"].id
        parent_matches = el.event_id == ctx["event"].parent_id

        if (not is_child and not event_matches) or (is_child and not event_matches and not parent_matches):
            raise Http404("not your event")


def check_assoc(el, ctx, afield=None):
    if afield:
        el = getattr(el, afield)

    if not hasattr(el, "assoc"):
        return

    if el.assoc.id != ctx["a_id"]:
        raise Http404("not your association")


def user_edit(request, ctx, form_type, nm, eid):
    if request.method == "POST":
        form = form_type(request.POST, request.FILES, instance=ctx[nm], ctx=ctx)

        if form.is_valid():
            p = form.save()
            messages.success(request, _("Operation completed") + "!")

            dl = "delete" in request.POST and request.POST["delete"] == "1"
            save_log(request.user.member, form_type, p, dl)
            if dl:
                p.delete()

            ctx["saved"] = p

            return True
    else:
        form = form_type(instance=ctx[nm], ctx=ctx)

    ctx["form"] = form
    ctx["num"] = eid
    if eid != 0:
        ctx["name"] = str(ctx[nm])

    return False


def backend_get(ctx, typ, eid, afield=None):
    try:
        el = typ.objects.get(pk=eid)
    except Exception as err:
        raise NotFoundError() from err
    ctx["el"] = el
    check_run(el, ctx, afield)
    check_assoc(el, ctx, afield)
    ctx["name"] = str(el)


def backend_edit(request, ctx, form_type, eid, afield=None, assoc=False):
    typ = form_type.Meta.model
    ctx["elementTyp"] = typ
    ctx["request"] = request

    if assoc:
        ctx["exe"] = True
        if eid is None:
            eid = request.assoc["id"]
            ctx["nonum"] = True

    elif eid is None:
        eid = ctx["event"].id
        ctx["nonum"] = True

    if eid != 0:
        backend_get(ctx, typ, eid, afield)
    else:
        ctx["el"] = None

    ctx["num"] = eid
    if request.method == "POST":
        ctx["form"] = form_type(request.POST, request.FILES, instance=ctx["el"], ctx=ctx)

        if ctx["form"].is_valid():
            p = ctx["form"].save()
            messages.success(request, _("Operation completed") + "!")

            dl = "delete" in request.POST and request.POST["delete"] == "1"
            save_log(request.user.member, form_type, p, dl)
            if dl:
                p.delete()

            ctx["saved"] = p

            return True
    else:
        ctx["form"] = form_type(instance=ctx["el"], ctx=ctx)

    if eid != 0:
        ctx["name"] = str(ctx["el"])

    ctx["add_another"] = "add_another" not in ctx or ctx["add_another"]
    if ctx["add_another"]:
        ctx["continue_add"] = "continue" in request.POST

    return False


def orga_edit(request, s, n, perm, form_type, eid, red=None, add_ctx=None):
    ctx = check_event_permission(request, s, n, perm)
    if add_ctx:
        ctx.update(add_ctx)
    if backend_edit(request, ctx, form_type, eid, afield=None, assoc=False):
        set_suggestion(ctx, perm)
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, s=ctx["event"].slug, n=ctx["run"].number, num=0)
        if not red:
            red = perm
        return redirect(red, s=ctx["event"].slug, n=ctx["run"].number)
    return render(request, "larpmanager/orga/edit.html", ctx)


def exe_edit(request, form_type, eid, perm, red=None, afield=None, add_ctx=None):
    ctx = check_assoc_permission(request, perm)
    if add_ctx:
        ctx.update(add_ctx)
    if backend_edit(request, ctx, form_type, eid, afield=afield, assoc=True):
        set_suggestion(ctx, perm)
        if "continue" in request.POST:
            return redirect(request.resolver_match.view_name, num=0)
        if not red:
            red = perm
        return redirect(red)
    return render(request, "larpmanager/exe/edit.html", ctx)


def set_suggestion(ctx, perm):
    if "event" in ctx:
        obj = ctx["event"]
    else:
        obj = Association.objects.get(pk=ctx["a_id"])

    key = f"{perm}_suggestion"
    suggestion = obj.get_config(key, False)
    if suggestion:
        return

    fk_field = _get_fkey_config(obj)
    (config, created) = obj.configs.model.objects.get_or_create(**{fk_field: obj, "name": key})
    config.value = True
    config.save()


def writing_edit(request, ctx, form_type, nm, tp, redr=None):
    ctx["elementTyp"] = form_type.Meta.model
    if nm in ctx:
        ctx["eid"] = ctx[nm].id
        ctx["name"] = str(ctx[nm])
    else:
        ctx[nm] = None

    ctx["type"] = ctx["elementTyp"].__name__.lower()

    if request.method == "POST":
        form = form_type(request.POST, request.FILES, instance=ctx[nm], ctx=ctx)
        if form.is_valid():
            return _writing_save(ctx, form, form_type, nm, redr, request, tp)
    else:
        form = form_type(instance=ctx[nm], ctx=ctx)

    ctx["nm"] = nm
    ctx["form"] = form
    ctx["add_another"] = True
    ctx["continue_add"] = "continue" in request.POST
    ctx["auto_save"] = not ctx["event"].get_config("writing_disable_auto", False)

    _setup_char_finder(ctx)

    return render(request, "larpmanager/orga/writing/writing.html", ctx)


def _setup_char_finder(ctx):
    ctx["disable_char_finder"] = ctx["event"].get_config("writing_disable_char_finder", False)
    if not ctx["disable_char_finder"]:
        widget = EventCharacterS2Widget(attrs={"id": "char_finder"})
        widget.set_event(ctx["event"])
        ctx["char_finder"] = widget.render(name="char_finder", value="")
        ctx["char_finder_media"] = widget.media


def _writing_save(ctx, form, form_type, nm, redr, request, tp):
    # Auto save ajax
    if "ajax" in request.POST:
        if nm in ctx:
            return writing_edit_save_ajax(form, request, ctx)
        else:
            return JsonResponse({"res": "ko"})

    # Normal save
    p = form.save(commit=False)
    p.temp = False
    p.save()
    dl = "delete" in request.POST and request.POST["delete"] == "1"
    if tp:
        save_version(p, tp, request.user.member, dl)
    else:
        save_log(request.user.member, form_type, p)

    if dl:
        p.delete()

    messages.success(request, _("Operation completed") + "!")

    if "continue" in request.POST:
        return redirect(request.resolver_match.view_name, s=ctx["event"].slug, n=ctx["run"].number, num=0)

    if redr:
        ctx["element"] = p
        return redr(ctx)

    return redirect("orga_" + nm + "s", s=ctx["event"].slug, n=ctx["run"].number)


def writing_edit_cache_key(eid, typ):
    return f"orga_edit_{eid}_{typ}"


def writing_edit_save_ajax(form, request, ctx):
    res = {"res": "ok"}
    if request.user.is_superuser:
        return JsonResponse(res)

    eid = int(request.POST["eid"])
    if eid <= 0:
        return res

    tp = request.POST["type"]
    token = request.POST["token"]
    msg = writing_edit_working_ticket(request, tp, eid, token)
    if msg:
        res["warn"] = msg
        return JsonResponse(res)

    p = form.save(commit=False)
    p.temp = True
    p.save()

    return JsonResponse(res)


def writing_edit_working_ticket(request, tp, eid, token):
    # working ticket also for related characters
    if tp == "plot":
        obj = Plot.objects.get(pk=eid)
        for char_id in obj.characters.values_list("pk", flat=True):
            msg = writing_edit_working_ticket(request, "character", char_id, token)
            if msg:
                return msg

    now = int(time.time())
    key = writing_edit_cache_key(eid, tp)
    ticket = cache.get(key)
    if not ticket:
        ticket = {}
    others = []
    ticket_time = 15
    for idx, el in ticket.items():
        (name, tm) = el
        if idx != token and now - tm < ticket_time:
            others.append(name)

    msg = ""
    if len(others) > 0:
        msg = _("Warning! Other users are editing this item") + "."
        msg += " " + _("You cannot work on it at the same time: the work of one of you would be lost") + "."
        msg += " " + _("List of other users") + ": " + ", ".join(others)

    ticket[token] = (str(request.user.member), now)
    cache.set(key, ticket, ticket_time)

    return msg
