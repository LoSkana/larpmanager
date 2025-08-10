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

import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.event import OrgaAppearanceForm, OrgaEventForm
from larpmanager.forms.miscellanea import OrganizerCopyForm
from larpmanager.models.access import EventRole
from larpmanager.models.accounting import Discount
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event, EventConfig, EventText
from larpmanager.models.form import RegistrationOption, RegistrationQuestion, WritingOption, WritingQuestion
from larpmanager.models.miscellanea import WorkshopModule, WorkshopOption, WorkshopQuestion
from larpmanager.models.registration import (
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSurcharge,
    RegistrationTicket,
)
from larpmanager.models.utils import generate_id
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    Faction,
    Handout,
    HandoutTemplate,
    Plot,
    PlotCharacterRel,
    Prologue,
    Relationship,
    SpeedLarp,
)
from larpmanager.utils.common import copy_class
from larpmanager.utils.event import check_event_permission


def correct_rels_many(e_id, cls_p, cls, field, rel_field="number"):
    cache_t = {}

    for obj in cls_p.objects.filter(event_id=e_id):
        rel_value = getattr(obj, rel_field)
        cache_t[rel_value] = obj.id

    for obj in cls.objects.filter(event_id=e_id):
        m2m_field = getattr(obj, field)
        m2m_data = list(m2m_field.all())
        new_values = []

        for old_rel in m2m_data:
            v = getattr(old_rel, rel_field)
            new_rel = cache_t[v]
            new_values.append(new_rel)

        m2m_field.set(new_values, clear=True)


def correct_rels(e_id, p_id, cls_p, cls, field, rel_field="number"):
    cache_f = {}
    cache_t = {}
    field = field + "_id"

    for obj in cls_p.objects.filter(event_id=p_id):
        rel_value = getattr(obj, rel_field)
        cache_f[obj.id] = rel_value

    for obj in cls_p.objects.filter(event_id=e_id):
        rel_value = getattr(obj, rel_field)
        cache_t[rel_value] = obj.id

    for obj in cls.objects.filter(event_id=e_id):
        v = getattr(obj, field)
        if v not in cache_f:
            continue
        v = cache_f[v]
        v = cache_t[v]
        setattr(obj, field, v)
        obj.save()


def correct_relationship(e_id, p_id):
    cache_f = {}
    cache_t = {}
    for obj in Character.objects.filter(event_id=p_id):
        cache_f[obj.id] = obj.number
    for obj in Character.objects.filter(event_id=e_id):
        cache_t[obj.number] = obj.id
    # ~ field = 'character_id'
    # ~ for obj in Registration.objects.filter(run_id=ctx['run'].id):
    # ~ v = getattr(obj, field)
    # ~ if v not in cache_f:
    # ~ continue
    # ~ v = cache_f[v]
    # ~ v = cache_t[v]
    # ~ setattr(obj, field, v)
    # ~ obj.save()

    # copy complicated
    # Relationship
    # print(cache_f)
    # print(cache_t)
    for rel in Relationship.objects.filter(source__event_id=p_id):
        # print(rel)

        v = rel.source_id
        # print(rel.source_id)
        v = cache_f[v]
        v = cache_t[v]
        rel.source_id = v

        v = rel.target_id
        v = cache_f[v]
        v = cache_t[v]
        rel.target_id = v

        if Relationship.objects.filter(source_id=rel.source_id, target_id=rel.target_id).count() > 0:
            continue

        rel.pk = None
        rel.save()


def correct_workshop(e_id, p_id):
    cache_f = {}
    cache_t = {}
    for obj in WorkshopModule.objects.filter(event_id=p_id):
        cache_f[obj.id] = obj.number
    for obj in WorkshopModule.objects.filter(event_id=e_id):
        cache_t[obj.number] = obj.id

    for el in WorkshopQuestion.objects.filter(module__event_id=p_id):
        v = el.module_id
        v = cache_f[v]
        v = cache_t[v]
        el.module_id = v

        el.pk = None
        el.save()

    cache_f = {}
    cache_t = {}
    for obj in WorkshopQuestion.objects.filter(module__event_id=p_id):
        cache_f[obj.id] = obj.number
    for obj in WorkshopQuestion.objects.filter(module__event_id=e_id):
        cache_t[obj.number] = obj.id

    for el in WorkshopOption.objects.filter(question__module__event_id=p_id):
        v = el.question_id
        v = cache_f[v]
        v = cache_t[v]
        el.question_id = v

        el.pk = None
        el.save()


def correct_plot_character(e_id, p_id):
    cache_c = {}
    for obj in Character.objects.values_list("id", "number").filter(event_id=p_id):
        n_obj = Character.objects.values_list("id").get(event_id=e_id, number=obj[1])[0]
        cache_c[obj[0]] = n_obj

    cache_p = {}
    for obj in Plot.objects.values_list("id", "number").filter(event_id=p_id):
        n_obj = Plot.objects.values_list("id").get(event_id=e_id, number=obj[1])[0]
        cache_p[obj[0]] = n_obj

    for el in PlotCharacterRel.objects.filter(character__event_id=p_id):
        n_c = cache_c[el.character.id]
        n_p = cache_p[el.plot.id]
        if PlotCharacterRel.objects.filter(character_id=n_c, plot_id=n_p).count() > 0:
            continue

        el.character_id = n_c
        el.plot_id = n_p
        el.pk = None
        el.save()


def copy_character_config(e_id, p_id):
    CharacterConfig.objects.filter(character__event_id=e_id).delete()
    cache = {}
    for obj in Character.objects.filter(event_id=e_id):
        cache[obj.number] = obj.id

    for obj in Character.objects.filter(event_id=p_id):
        new_id = cache[obj.number]
        for el in CharacterConfig.objects.filter(character=obj):
            for _idx in range(2):
                try:
                    with transaction.atomic():
                        cg, created = CharacterConfig.objects.update_or_create(
                            character_id=new_id, name=el.name, defaults={"value": el.value}
                        )
                    break
                except IntegrityError:
                    if _idx == 0:
                        continue
                    raise


def copy(request, ctx, parent, event, element):
    if not parent:
        return messages.error(request, _("Parent empty"))

    p_id = parent.id
    e_id = event.id

    if p_id == e_id:
        return messages.error(request, _("Can't copy from same event"))

    all = element == "all"

    copy_event(all, ctx, e_id, element, event, p_id, parent)

    copy_registration(all, e_id, element, p_id)

    copy_writing(all, e_id, element, p_id)

    event.save()

    messages.success(request, _("Copy done"))


def copy_event(all, ctx, e_id, element, event, p_id, parent):
    if all or element == "event":
        for s in get_all_fields_from_form(OrgaEventForm, ctx):
            if s == "slug":
                continue
            v = getattr(parent, s)
            setattr(event, s, v)

        event.name = "copy - " + event.name
    if all or element == "config":
        copy_class(e_id, p_id, EventConfig)
    if all or element == "appearance":
        for s in get_all_fields_from_form(OrgaAppearanceForm, ctx):
            if s == "event_css":
                copy_css(ctx, event, parent)
            else:
                v = getattr(parent, s)
                setattr(event, s, v)
    if all or element == "text":
        copy_class(e_id, p_id, EventText)
    if all or element == "role":
        copy_class(e_id, p_id, EventRole)
    if all or element == "features":
        # copy features
        for fn in parent.features.all():
            event.features.add(fn)
        event.save()


def copy_registration(all, e_id, element, p_id):
    if all or element == "ticket":
        copy_class(e_id, p_id, RegistrationTicket)
    if all or element == "question":
        copy_class(e_id, p_id, RegistrationQuestion)
        copy_class(e_id, p_id, RegistrationOption)
        correct_rels(e_id, p_id, RegistrationQuestion, RegistrationOption, "question", "name")
    if all or element == "discount":
        copy_class(e_id, p_id, Discount)
    if all or element == "quota":
        copy_class(e_id, p_id, RegistrationQuota)
    if all or element == "installment":
        copy_class(e_id, p_id, RegistrationInstallment)
        correct_rels_many(e_id, RegistrationTicket, RegistrationInstallment, "tickets", "name")
    if all or element == "surcharge":
        copy_class(e_id, p_id, RegistrationSurcharge)


def copy_writing(all, e_id, element, p_id):
    if all or element == "character":
        copy_class(e_id, p_id, Character)
        # correct relationship
        correct_relationship(e_id, p_id)
        # character fields
        copy_class(e_id, p_id, WritingQuestion)
        copy_class(e_id, p_id, WritingOption)
        copy_character_config(e_id, p_id)
        correct_rels(e_id, p_id, WritingQuestion, WritingOption, "question", "name")
    if all or element == "faction":
        copy_class(e_id, p_id, Faction)
    if all or element == "quest":
        copy_class(e_id, p_id, QuestType)
        copy_class(e_id, p_id, Quest)
        copy_class(e_id, p_id, Trait)
        correct_rels(e_id, p_id, QuestType, Quest, "typ")
        correct_rels(e_id, p_id, Quest, Trait, "quest")
    if all or element == "prologue":
        copy_class(e_id, p_id, Prologue)
    if all or element == "speedlarp":
        copy_class(e_id, p_id, SpeedLarp)
    if all or element == "plot":
        copy_class(e_id, p_id, Plot)
        # correct plotcharacterrels
        correct_plot_character(e_id, p_id)
    if all or element == "handout":
        copy_class(e_id, p_id, Handout)
        copy_class(e_id, p_id, HandoutTemplate)
    if all or element == "workshop":
        copy_class(e_id, p_id, WorkshopModule)
        # correct workshop
        correct_workshop(e_id, p_id)


def copy_css(ctx, event, parent):
    app_form = OrgaAppearanceForm(ctx=ctx)
    path = app_form.get_css_path(parent)
    if not os.path.exists(path):
        return
    value = default_storage.open(path).read().decode("utf-8")
    event.css_code = generate_id(32)
    npath = app_form.get_css_path(event)
    default_storage.save(npath, ContentFile(value))


@login_required
def orga_copy(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_copy")

    if request.method == "POST":
        form = OrganizerCopyForm(request.POST, request.FILES, ctx=ctx)
        if form.is_valid():
            pt = form.cleaned_data["parent"]
            el = form.cleaned_data["target"]
            parent = Event.objects.get(pk=pt, assoc_id=ctx["a_id"])
            event = ctx["event"]
            copy(request, ctx, parent, event, el)

    else:
        form = OrganizerCopyForm(ctx=ctx)

    ctx["form"] = form

    return render(request, "larpmanager/orga/copy.html", ctx)


def get_all_fields_from_form(instance, ctx):
    """
    Return names of all available fields from given Form instance.

    :arg instance: Form instance
    :returns list of field names
    :rtype: list
    """

    fields = list(instance(ctx=ctx).base_fields)

    for field in list(instance(ctx=ctx).declared_fields):
        if field not in fields:
            fields.append(field)

    for s in ["slug"]:
        if s in fields:
            fields.remove(s)

    return fields
