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
import traceback
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Prefetch
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import reset_run
from larpmanager.cache.run import get_cache_run
from larpmanager.forms.event import (
    OrgaAppearanceForm,
    OrgaConfigForm,
    OrgaEventButtonForm,
    OrgaEventForm,
    OrgaEventRoleForm,
    OrgaEventTextForm,
    OrgaFeatureForm,
    OrgaPreferencesForm,
    OrgaQuickSetupForm,
    OrgaRunForm,
)
from larpmanager.forms.writing import UploadElementsForm
from larpmanager.models.access import EventPermission, EventRole
from larpmanager.models.base import Feature
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event, EventButton, EventText
from larpmanager.models.form import QuestionApplicable, QuestionType
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Character, Faction, Plot
from larpmanager.utils.common import clear_messages, get_feature
from larpmanager.utils.deadlines import check_run_deadlines
from larpmanager.utils.download import (
    _get_column_names,
    export_character_form,
    export_data,
    export_registration_form,
    zip_exports,
)
from larpmanager.utils.edit import backend_edit, orga_edit
from larpmanager.utils.event import check_event_permission, get_index_event_permissions
from larpmanager.utils.upload import go_upload


@login_required
def orga_event(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_event")
    return full_event_edit(ctx, request, ctx["event"], ctx["run"], exe=False)


def full_event_edit(ctx, request, event, run, exe=False):
    if request.method == "POST":
        form_event = OrgaEventForm(request.POST, request.FILES, instance=event, ctx=ctx, prefix="form1")
        form_run = OrgaRunForm(request.POST, request.FILES, instance=run, ctx=ctx, prefix="form2")
        if form_event.is_valid() and form_run.is_valid():
            form_event.save()
            form_run.save()
            messages.success(request, _("Operation completed") + "!")
            if exe:
                return redirect("manage")
            else:
                return redirect("manage", s=event.slug, n=run.number)
    else:
        form_event = OrgaEventForm(instance=event, ctx=ctx, prefix="form1")
        form_run = OrgaRunForm(instance=run, ctx=ctx, prefix="form2")

    ctx["form1"] = form_event
    ctx["form2"] = form_run

    return render(request, "larpmanager/orga/edit_multi.html", ctx)


@login_required
def orga_roles(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_roles")

    def def_callback(ctx):
        return EventRole.objects.create(event=ctx["event"], number=1, name="Organizer")

    prepare_roles_list(ctx, EventPermission, EventRole.objects.filter(event=ctx["event"]), def_callback)

    return render(request, "larpmanager/orga/roles.html", ctx)


def prepare_roles_list(ctx, permission_typ, role_query, def_callback):
    qs_perm = permission_typ.objects.select_related("feature", "feature__module").order_by(
        F("feature__module__order").asc(nulls_last=True),
        F("feature__order").asc(nulls_last=True),
        "feature__name",
        "name",
    )
    roles = role_query.order_by("number").prefetch_related(Prefetch("permissions", queryset=qs_perm))
    ctx["list"] = []
    if not roles:
        ctx["list"].append(def_callback(ctx))
    for role in roles:
        role.members_list = ", ".join([str(mb) for mb in role.members.all()])
        if role.number == "1":
            role.perms_list = "All"
        else:
            buckets = defaultdict(list)
            for p in role.permissions.all():
                buckets[p.feature.module].append(p)

            modules = sorted(
                buckets.keys(),
                key=lambda m: (
                    float("inf") if m is None else (m.order if m.order is not None else float("inf")),
                    "" if m is None else m.name,
                ),
            )

            aux = []
            for module in modules:
                perms_sorted = sorted(buckets[module], key=lambda p: p.number)
                perms = ", ".join([str(_(ep.name)) for ep in perms_sorted])
                aux.append(f"<b>{module}</b> ({perms})")
            role.perms_list = ", ".join(aux)

        ctx["list"].append(role)


@login_required
def orga_roles_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_roles", OrgaEventRoleForm, num)


@login_required
def orga_appearance(request, s, n):
    return orga_edit(
        request, s, n, "orga_appearance", OrgaAppearanceForm, None, "manage", add_ctx={"add_another": False}
    )


@login_required
def orga_run(request, s, n):
    run = get_cache_run(request.assoc["id"], s, n)
    return orga_edit(request, s, n, "orga_event", OrgaRunForm, run, "manage", add_ctx={"add_another": False})


@login_required
def orga_texts(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_texts")
    ctx["list"] = EventText.objects.filter(event_id=ctx["event"].id).order_by("typ", "default", "language")
    return render(request, "larpmanager/orga/texts.html", ctx)


@login_required
def orga_texts_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_texts", OrgaEventTextForm, num)


@login_required
def orga_buttons(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_buttons")
    ctx["list"] = EventButton.objects.filter(event_id=ctx["event"].id).order_by("number")
    return render(request, "larpmanager/orga/buttons.html", ctx)


@login_required
def orga_buttons_edit(request, s, n, num):
    return orga_edit(request, s, n, "orga_buttons", OrgaEventButtonForm, num)


@login_required
def orga_config(request, s, n, section=None):
    add_ctx = {"jump_section": section} if section else {}
    add_ctx["add_another"] = False
    return orga_edit(request, s, n, "orga_config", OrgaConfigForm, None, "manage", add_ctx=add_ctx)


@login_required
def orga_features(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_features")
    ctx["add_another"] = False
    if backend_edit(request, ctx, OrgaFeatureForm, None, afield=None, assoc=False):
        ctx["new_features"] = Feature.objects.filter(pk__in=ctx["form"].added_features, after_link__isnull=False)
        if not ctx["new_features"]:
            return redirect("manage", s=ctx["event"].slug, n=ctx["run"].number)
        for el in ctx["new_features"]:
            el.follow_link = _orga_feature_after_link(el, s, n)
        if len(ctx["new_features"]) == 1:
            feature = ctx["new_features"][0]
            msg = _("Feature %(name)s activated") % {"name": feature.name} + "! " + feature.after_text
            clear_messages(request)
            messages.success(request, msg)
            return redirect(feature.follow_link)

        get_index_event_permissions(ctx, request, s)
        return render(request, "larpmanager/manage/features.html", ctx)
    return render(request, "larpmanager/orga/edit.html", ctx)


def orga_features_go(request, ctx, num, on=True):
    get_feature(ctx, num)
    feat_id = list(ctx["event"].features.values_list("id", flat=True))
    f_id = ctx["feature"].id
    reset_run(ctx["run"])
    if on:
        if f_id not in feat_id:
            ctx["event"].features.add(f_id)
            msg = _("Feature %(name)s activated") + "!"
        else:
            msg = _("Feature %(name)s already activated") + "!"
    elif f_id not in feat_id:
        msg = _("Feature %(name)s already deactivated") + "!"
    else:
        ctx["event"].features.remove(f_id)
        msg = _("Feature %(name)s deactivated") + "!"

    ctx["event"].save()
    # update cached event features, for itself, and the events for which they are parent
    for ev in Event.objects.filter(parent=ctx["event"]):
        ev.save()

    msg = msg % {"name": _(ctx["feature"].name)}
    if ctx["feature"].after_text:
        msg += " " + ctx["feature"].after_text
    messages.success(request, msg)

    return ctx["feature"]


def _orga_feature_after_link(feature, s, n):
    after_link = feature.after_link
    if after_link and after_link.startswith("orga"):
        return reverse(after_link, kwargs={"s": s, "n": n})
    return reverse("manage", kwargs={"s": s, "n": n}) + (after_link or "")


@login_required
def orga_features_on(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_features")
    feature = orga_features_go(request, ctx, num, on=True)
    return redirect(_orga_feature_after_link(feature, s, n))


@login_required
def orga_features_off(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_features")
    orga_features_go(request, ctx, num, on=False)
    return redirect("manage", s=s, n=n)


@login_required
def orga_deadlines(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_deadlines")
    ctx["res"] = check_run_deadlines([ctx["run"]])[0]
    return render(request, "larpmanager/orga/deadlines.html", ctx)


@login_required
def orga_quick(request, s, n):
    return orga_edit(request, s, n, "orga_quick", OrgaQuickSetupForm, None, "manage", add_ctx={"add_another": False})


@login_required
def orga_preferences(request, s, n):
    return orga_edit(
        request,
        s,
        n,
        "orga_preferences",
        OrgaPreferencesForm,
        request.user.member.id,
        "manage",
        add_ctx={"add_another": False},
    )


@login_required
def orga_backup(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_event")

    return _prepare_backup(ctx)


def _prepare_backup(ctx):
    exports = []

    exports.extend(export_data(ctx, Registration))
    exports.extend(export_registration_form(ctx))

    if "character" in ctx["features"]:
        exports.extend(export_data(ctx, Character))
        exports.extend(export_character_form(ctx))

    if "faction" in ctx["features"]:
        exports.extend(export_data(ctx, Faction))

    if "plot" in ctx["features"]:
        exports.extend(export_data(ctx, Plot))

    if "questbuilder" in ctx["features"]:
        exports.extend(export_data(ctx, QuestType))
        exports.extend(export_data(ctx, Quest))
        exports.extend(export_data(ctx, Trait))

    return zip_exports(ctx, exports, "backup")


@login_required
def orga_upload(request, s, n, typ):
    ctx = check_event_permission(request, s, n, f"orga_{typ}")
    ctx["typ"] = typ.rstrip("s")
    _get_column_names(ctx)

    if request.POST:
        form = UploadElementsForm(request.POST, request.FILES)
        redr = reverse(f"orga_{typ}", args=[ctx["event"].slug, ctx["run"].number])
        if form.is_valid():
            try:
                # print(request.FILES)
                ctx["logs"] = go_upload(request, ctx, form)
                ctx["redr"] = redr
                messages.success(request, _("Elements uploaded") + "!")
                return render(request, "larpmanager/orga/uploads.html", ctx)

            except Exception as exp:
                print(traceback.format_exc())
                messages.error(request, _("Unknow error on upload") + f": {exp}")
            return HttpResponseRedirect(redr)
    else:
        form = UploadElementsForm()

    ctx["form"] = form

    return render(request, "larpmanager/orga/upload.html", ctx)


@login_required
def orga_upload_template(request, s, n, typ):
    ctx = check_event_permission(request, s, n)
    ctx["typ"] = typ
    _get_column_names(ctx)
    value_mapping = {
        QuestionType.SINGLE: "option name",
        QuestionType.MULTIPLE: "option names (comma separated)",
        QuestionType.TEXT: "field text",
        QuestionType.PARAGRAPH: "field long text",
        QuestionType.EDITOR: "field html text",
        QuestionType.NAME: "element name",
        QuestionType.TEASER: "element presentation",
        QuestionType.SHEET: "element text",
        QuestionType.COVER: "element cover (utils path)",
        QuestionType.FACTIONS: "faction names (comma separated)",
        QuestionType.TITLE: "title short text",
        QuestionType.MIRROR: "name of mirror character",
        QuestionType.HIDE: "hide (true or false)",
        QuestionType.PROGRESS: "name of progress step",
        QuestionType.ASSIGNED: "name of assigned staff",
    }
    if ctx.get("writing_typ"):
        exports = _writing_template(ctx, typ, value_mapping)
    elif typ == "registration":
        exports = _reg_template(ctx, typ, value_mapping)
    else:
        exports = _form_template(ctx)

    return zip_exports(ctx, exports, "template")


def _form_template(ctx):
    exports = []
    defs = {
        "name": "Question Name",
        "typ": "multi-choice",
        "description": "Question Description",
        "status": "optional",
        "applicable": "character",
        "visibility": "public",
        "max_length": "1",
    }
    keys = list(ctx["columns"][0].keys())
    vals = []
    for field, value in defs.items():
        if field not in keys:
            continue
        vals.append(value)
    exports.append(("questions", keys, [vals]))
    defs = {
        "question": "Question Name",
        "name": "Option Name",
        "description": "Option description",
        "max_available": "2",
        "price": "10",
    }
    keys = list(ctx["columns"][1].keys())
    vals = []
    for field, value in defs.items():
        if field not in keys:
            continue
        vals.append(value)
    exports.append(("options", keys, [vals]))
    return exports


def _reg_template(ctx, typ, value_mapping):
    keys = list(ctx["columns"][0].keys())
    vals = []
    defs = {"player": "user@test.it", "ticket": "Standard", "character": "Test Character", "donation": "5"}
    for field, value in defs.items():
        if field not in keys:
            continue
        vals.append(value)
    keys.extend(ctx["fields"])
    for _field, field_typ in ctx["fields"].items():
        vals.append(value_mapping[field_typ])
    exports = [(f"{typ} - template", keys, [vals])]
    return exports


def _writing_template(ctx, typ, value_mapping):
    keys = list(ctx["fields"].keys())
    vals = [value_mapping[field_typ] for _field, field_typ in ctx["fields"].items()]

    if ctx["writing_typ"] == QuestionApplicable.QUEST:
        keys.insert(0, "typ")
        vals.insert(0, "name of quest type")
    elif ctx["writing_typ"] == QuestionApplicable.TRAIT:
        keys.insert(0, "quest")
        vals.insert(0, "name of quest")

    exports = [(f"{typ} - template", keys, [vals])]

    if ctx["writing_typ"] == QuestionApplicable.CHARACTER and "relationships" in ctx["features"]:
        exports.append(
            (
                "relationships - template",
                list(ctx["columns"][1].keys()),
                [["Test Character", "Another Character", "Super pals"]],
            )
        )
    if ctx["writing_typ"] == QuestionApplicable.PLOT:
        exports.append(
            (
                "roles - template",
                list(ctx["columns"][1].keys()),
                [["Test Plot", "Test Character", "Gonna be a super star"]],
            )
        )
    return exports
