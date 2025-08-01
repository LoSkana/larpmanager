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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles.finders import find
from django.http import Http404
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
from larpmanager.models.access import EventRole
from larpmanager.models.base import Feature
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event, EventButton, EventText
from larpmanager.models.form import QuestionApplicable, QuestionType, WritingQuestion
from larpmanager.models.registration import Registration
from larpmanager.models.writing import Character, Faction, Plot
from larpmanager.utils.common import clear_messages, get_feature
from larpmanager.utils.deadlines import check_run_deadlines
from larpmanager.utils.download import export_character_form, export_data, export_registration_form, zip_exports
from larpmanager.utils.edit import backend_edit, orga_edit
from larpmanager.utils.event import check_event_permission, get_index_event_permissions


@login_required
def orga_event(request, s, n):
    return orga_edit(request, s, n, "orga_event", OrgaEventForm, None, "manage", add_ctx={"add_another": False})


@login_required
def orga_roles(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_roles")
    ctx["list"] = list(EventRole.objects.filter(event=ctx["event"]).order_by("number"))
    if not ctx["list"]:
        ctx["list"].append(EventRole.objects.create(event=ctx["event"], number=1, name="Organizer"))
    return render(request, "larpmanager/orga/roles.html", ctx)


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
    return orga_edit(request, s, n, "orga_run", OrgaRunForm, run, "manage", add_ctx={"add_another": False})


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
    return render(request, "larpmanager/orga/upload.html", ctx)


def _get_column_names(ctx):
    if ctx["typ"] == "registration":
        ctx["columns"] = [
            {
                "player": _("The player's email (if not found in the system, a new user will be created)"),
                "ticket": _("The name of the ticket") + "<i>" + (_("if it doesn't exist, it will be created")) + "</i>",
                "character": _("(Optional) The character name to assign to the player"),
                "donation": _("(Optional) The amount of a voluntary donation"),
            }
        ]
    elif ctx["typ"] == "registration_form":
        ctx["columns"] = [
            {
                "display": _("The question name"),
                "typ": _("The question type, allowed values are")
                + ": 'single-choice', 'multi-choice', 'short-text', 'long-text', 'advanced'",
                "description": _("Optional - Extended description (displayed in small gray text)"),
                "status": _("The question status, allowed values are")
                + ": 'optional', 'mandatory', 'disabled', 'hidden'",
                "max_length": _(
                    "Optional - For text questions, maximum number of characters; For multiple options, maximum number of options (0 = no limit)"
                ),
            },
            {
                "question": _("The name of the question this option belongs to")
                + "<i>"
                + (_("If not found, the option will be skipped"))
                + "</i>",
                "name": _("The name of the option"),
                "description": _("Optional – Additional information about the option, displayed below the question"),
                "price": _("Optional – Amount added to the registration fee if selected (0 = no extra cost)"),
                "max_available": _(
                    "Optional – Maximum number of times it can be selected across all registrations (0 = unlimited)"
                ),
            },
        ]
    elif ctx["typ"] == "character_form":
        ctx["columns"] = [
            {
                "name": _("The question name"),
                "typ": _("The question type, allowed values are")
                + ": 'single-choice', 'multi-choice', 'short-text', 'long-text', 'advanced', 'name', 'teaser', 'text'",
                "description": _("Optional - Extended description (displayed in small gray text)"),
                "status": _("The question status, allowed values are")
                + ": 'optional', 'mandatory', 'disabled', 'hidden'",
                "applicable": _("The writing element this question applies to, allowed values are")
                + ": 'character', 'plot', 'faction', 'quest', 'trait'",
                "visibility": _("The question visibility to players, allowed values are")
                + ": 'searchable', 'public', 'private', 'hidden'",
                "max_length": _(
                    "Optional - For text questions, maximum number of characters; For multiple options, maximum number of options (0 = no limit)"
                ),
            },
            {
                "question": _("The name of the question this option belongs to")
                + "<i>"
                + (_("If not found, the option will be skipped"))
                + "</i>",
                "name": _("The name of the option"),
                "description": _("Optional – Additional information about the option, displayed below the question"),
                "max_available": _("Optional – Maximum number of times it can be selected (0 = unlimited)"),
            },
        ]


@login_required
def orga_upload_template(request, s, n, typ):
    ctx = check_event_permission(request, s, n)
    writing_typ = QuestionApplicable.get_applicable(typ)
    if writing_typ:
        # Dynamically create template file
        fields = (
            ctx["event"]
            .get_elements(WritingQuestion)
            .filter(applicable=writing_typ, typ__in=QuestionType.get_def_types())
            .order_by("order")
        )
        keys = []
        vals = []
        for field in fields:
            keys.append(field.name)
            if field.typ == QuestionType.NAME:
                vals.append("Element name")
            else:
                vals.append("some text")

    else:
        # Return static file
        filename = f"{typ}-template.csv"
        path = find(filename)
        if not path:
            raise Http404(f"Static file '{filename}' not found")

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            keys = reader.fieldnames
            rows = list(reader)
            vals = rows[0]

    return zip_exports(ctx, (f"{typ} - template", keys, [vals]), f"{str(ctx['run'])} - template")
