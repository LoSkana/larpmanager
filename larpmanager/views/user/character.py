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
import ast
import json
import os
import time
from uuid import uuid4

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from PIL import Image

from larpmanager.cache.character import get_character_element_fields, get_event_cache_all
from larpmanager.cache.config import save_single_config
from larpmanager.forms.character import (
    CharacterForm,
)
from larpmanager.forms.member import (
    AvatarForm,
)
from larpmanager.forms.registration import (
    RegistrationCharacterRelForm,
)
from larpmanager.forms.writing import (
    PlayerRelationshipForm,
)
from larpmanager.models.event import EventTextType
from larpmanager.models.form import (
    QuestionApplicable,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.miscellanea import (
    PlayerRelationship,
)
from larpmanager.models.registration import (
    RegistrationCharacterRel,
)
from larpmanager.models.writing import (
    Character,
    CharacterStatus,
)
from larpmanager.templatetags.show_tags import get_tooltip
from larpmanager.utils.character import get_char_check, get_character_relationships, get_character_sheet
from larpmanager.utils.common import (
    get_player_relationship,
)
from larpmanager.utils.edit import user_edit
from larpmanager.utils.event import get_event_run
from larpmanager.utils.experience import get_available_ability_px
from larpmanager.utils.registration import (
    check_assign_character,
    check_character_maximum,
    get_player_characters,
    registration_find,
)
from larpmanager.utils.text import get_event_text
from larpmanager.utils.writing import char_add_addit
from larpmanager.views.user.casting import casting_details, get_casting_preferences
from larpmanager.views.user.registration import init_form_submitted


def character(request, s, n, num):
    ctx = get_event_run(request, s, n, status=True)
    get_char_check(request, ctx, num)

    return _character_sheet(request, ctx)


def _character_sheet(request, ctx):
    ctx["screen"] = True

    if "check" not in ctx and not ctx["show_character"]:
        messages.warning(request, _("Characters are not visible at the moment"))
        return redirect("gallery", s=ctx["event"].slug, n=ctx["run"].number)

    if "check" not in ctx and ctx["char"]["hide"]:
        messages.warning(request, _("Character not visible"))
        return redirect("gallery", s=ctx["event"].slug, n=ctx["run"].number)

    show_private = "check" in ctx
    if show_private:
        get_character_sheet(ctx)
        get_character_relationships(ctx)
        ctx["intro"] = get_event_text(ctx["event"].id, EventTextType.INTRO)
    else:
        ctx["char"].update(get_character_element_fields(ctx, ctx["char"]["id"], only_visible=True))

    casting_details(ctx, 0)
    if ctx["casting_show_pref"] and not ctx["char"]["player_id"]:
        ctx["pref"] = get_casting_preferences(ctx["char"]["id"], ctx, 0)

    ctx["approval"] = ctx["event"].get_config("user_character_approval", False)

    return render(request, "larpmanager/event/character.html", ctx)


def character_external(request, s, n, code):
    ctx = get_event_run(request, s, n)

    if not ctx["event"].get_config("writing_external_access", False):
        raise Http404("external access not active")

    try:
        char = ctx["event"].get_elements(Character).get(access_token=code)
    except ObjectDoesNotExist as err:
        raise Http404("invalid code") from err

    get_event_cache_all(ctx)
    if char.number not in ctx["chars"]:
        messages.warning(request, _("Character not found"))
        return redirect("/")

    ctx["char"] = ctx["chars"][char.number]
    ctx["character"] = char
    ctx["check"] = 1

    return _character_sheet(request, ctx)


def character_your_link(ctx, char, p=None):
    url = reverse(
        "character",
        kwargs={
            "s": ctx["event"].slug,
            "n": ctx["run"].number,
            "num": char.number,
        },
    )
    if p:
        url += p
    return url


@login_required
def character_your(request, s, n, p=None):
    ctx = get_event_run(request, s, n, signup=True, status=True)

    rcrs = ctx["run"].reg.rcrs.all()

    if rcrs.count() == 0:
        messages.error(request, _("You don't have a character assigned for this event") + "!")
        return redirect("home")

    if rcrs.count() == 1:
        char = rcrs.first().character
        url = character_your_link(ctx, char, p)
        return HttpResponseRedirect(url)

    ctx["urls"] = []
    for el in rcrs:
        url = character_your_link(ctx, el.character, p)
        char = el.character.name
        if el.custom_name:
            char = el.custom_name
        ctx["urls"].append((char, url))
    return render(request, "larpmanager/event/character/your.html", ctx)


def character_form(request, ctx, s, n, instance, form_class):
    get_options_dependencies(ctx)
    ctx["elementTyp"] = Character

    if request.method == "POST":
        form = form_class(request.POST, request.FILES, instance=instance, ctx=ctx)
        if form.is_valid():
            if instance:
                mes = _("Informations saved") + "!"
            else:
                mes = _("New character created") + "!"

            element = form.save(commit=False)
            mes = _update_character(ctx, element, form, mes, request)
            element.save()

            if mes:
                messages.success(request, mes)

            check_assign_character(request, ctx)

            number = None
            if isinstance(element, Character):
                number = element.number
            elif isinstance(element, RegistrationCharacterRel):
                number = element.character.number
            return redirect("character", s=s, n=n, num=number)
    else:
        form = form_class(instance=instance, ctx=ctx)

    ctx["form"] = form
    init_form_submitted(ctx, form, request)

    ctx["hide_unavailable"] = ctx["event"].get_config("character_form_hide_unavailable", False)

    return render(request, "larpmanager/event/character/edit.html", ctx)


def _update_character(ctx, element, form, mes, request):
    if not isinstance(element, Character):
        return

    if not element.player:
        element.player = request.user.member

    if ctx["event"].get_config("user_character_approval", False):
        if element.status in [CharacterStatus.CREATION, CharacterStatus.REVIEW] and form.cleaned_data["propose"]:
            element.status = CharacterStatus.PROPOSED
            mes = _(
                "The character has been proposed to the staff, who will examine it and approve it "
                "or request changes if necessary."
            )
    return mes


@login_required
def character_customize(request, s, n, num):
    ctx = get_event_run(request, s, n, signup=True, status=True)

    get_char_check(request, ctx, num, True)

    try:
        rgr = RegistrationCharacterRel.objects.get(reg=ctx["run"].reg, character__number=num)
        if rgr.custom_profile:
            ctx["custom_profile"] = rgr.profile_thumb.url

        if ctx["event"].get_config("custom_character_profile", False):
            ctx["avatar_form"] = AvatarForm()

        return character_form(request, ctx, s, n, rgr, RegistrationCharacterRelForm)
    except ObjectDoesNotExist as err:
        raise Http404("not your char!") from err


@login_required
def character_profile_upload(request, s, n, num):
    if not request.method == "POST":
        return JsonResponse({"res": "ko"})

    form = AvatarForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"res": "ko"})

    ctx = get_event_run(request, s, n, signup=True)
    registration_find(ctx["run"], request.user)
    get_char_check(request, ctx, num, True)

    try:
        rgr = RegistrationCharacterRel.objects.get(reg=ctx["run"].reg, character__number=num)
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko"})

    img = form.cleaned_data["image"]
    ext = img.name.split(".")[-1]

    n_path = f"registration/{rgr.pk}_{uuid4().hex}.{ext}"
    path = default_storage.save(n_path, ContentFile(img.read()))

    rgr.custom_profile = path
    rgr.save()

    return JsonResponse({"res": "ok", "src": rgr.profile_thumb.url})


@login_required
def character_profile_rotate(request, s, n, num, r):
    ctx = get_event_run(request, s, n, signup=True, status=True)
    get_char_check(request, ctx, num, True)

    try:
        rgr = RegistrationCharacterRel.objects.get(reg=ctx["run"].reg, character__number=num)
    except ObjectDoesNotExist:
        return JsonResponse({"res": "ko"})

    path = str(rgr.custom_profile)
    if not path:
        return JsonResponse({"res": "ko"})

    path = os.path.join(conf_settings.MEDIA_ROOT, path)
    im = Image.open(path)
    if r == 1:
        out = im.rotate(90)
    else:
        out = im.rotate(-90)

    ext = path.split(".")[-1]
    n_path = f"{os.path.dirname(path)}/{rgr.pk}_{uuid4().hex}.{ext}"
    out.save(n_path)

    rgr.custom_profile = n_path
    rgr.save()

    return JsonResponse({"res": "ok", "src": rgr.profile_thumb.url})


@login_required
def character_list(request, s, n):
    ctx = get_event_run(request, s, n, status=True, signup=True, slug="user_character")

    ctx["list"] = get_player_characters(request.user.member, ctx["event"])
    # add character configs
    char_add_addit(ctx)
    for el in ctx["list"]:
        if "character" in ctx["features"]:
            res = get_character_element_fields(ctx, el.id, only_visible=True)
            el.fields = res["fields"]
            ctx.update(res)

    ctx["char_maximum"] = check_character_maximum(ctx["event"], request.user.member)
    ctx["approval"] = ctx["event"].get_config("user_character_approval", False)
    ctx["assigned"] = RegistrationCharacterRel.objects.filter(reg_id=ctx["run"].reg.id).count()
    return render(request, "larpmanager/event/character/list.html", ctx)


@login_required
def character_create(request, s, n):
    ctx = get_event_run(request, s, n, status=True, signup=True, slug="user_character")

    if check_character_maximum(ctx["event"], request.user.member):
        messages.success(request, _("You have reached the maximum number of characters that can be created"))
        return redirect("character_list", s=s, n=n)

    ctx["class_name"] = "character"
    return character_form(request, ctx, s, n, None, CharacterForm)


@login_required
def character_edit(request, s, n, num):
    ctx = get_event_run(request, s, n, status=True, signup=True)
    get_char_check(request, ctx, num, True)
    return character_form(request, ctx, s, n, ctx["character"], CharacterForm)


def get_options_dependencies(ctx):
    ctx["dependencies"] = {}
    if "character" not in ctx["features"]:
        return

    que = ctx["event"].get_elements(WritingQuestion).order_by("order")
    que = que.filter(applicable=QuestionApplicable.CHARACTER)
    question_idxs = que.values_list("id", flat=True)

    que = ctx["event"].get_elements(WritingOption).filter(question_id__in=question_idxs)
    for el in que.filter(dependents__isnull=False).distinct():
        ctx["dependencies"][el.id] = list(el.dependents.values_list("id", flat=True))


@login_required
def character_assign(request, s, n, num):
    ctx = get_event_run(request, s, n, signup=True, status=True)
    get_char_check(request, ctx, num, True)
    if RegistrationCharacterRel.objects.filter(reg_id=ctx["run"].reg.id).count():
        messages.warning(request, _("You already have an assigned character"))
    else:
        RegistrationCharacterRel.objects.create(reg_id=ctx["run"].reg.id, character=ctx["character"])
        messages.success(request, _("Assigned character!"))

    return redirect("character_list", s=s, n=n)


@login_required
def character_abilities(request, s, n, num):
    ctx = check_char_abilities(n, num, request, s)

    ctx["available"] = get_available_ability_px(ctx["character"])

    ctx["sheet_abilities"] = {}
    for el in ctx["character"].px_ability_list.all():
        if el.typ.name not in ctx["sheet_abilities"]:
            ctx["sheet_abilities"][el.typ.name] = []
        ctx["sheet_abilities"][el.typ.name].append(el)

    if request.method == "POST":
        _save_character_abilities(ctx, request)
        return redirect(request.path_info)

    ctx["type_available"] = {
        typ_id: data["name"] for typ_id, data in sorted(ctx["available"].items(), key=lambda x: x[1]["order"])
    }

    ctx["undo_abilities"] = get_undo_abilities(ctx, request)

    return render(request, "larpmanager/event/character/abilities.html", ctx)


def check_char_abilities(n, num, request, s):
    ctx = get_event_run(request, s, n, signup=True, status=True)

    event = ctx["event"]
    if event.parent:
        event = event.parent

    # check the user can select abilities
    if not event.get_config("px_user", False):
        raise Http404("ehm.")

    get_char_check(request, ctx, num, True)

    return ctx


@login_required
def character_abilities_del(request, s, n, num, id_del):
    ctx = check_char_abilities(n, num, request, s)
    undo_abilities = get_undo_abilities(ctx, request)
    if id_del not in undo_abilities:
        raise Http404("ability out of undo window")

    ctx["character"].px_ability_list.remove(id_del)
    ctx["character"].save()
    messages.success(request, _("Ability removed") + "!")

    return redirect("character_abilities", s=ctx["event"].slug, n=ctx["run"].number, num=ctx["character"].number)


def _save_character_abilities(ctx, request):
    selected_type = request.POST.get("ability_type")
    if not selected_type:
        messages.error(request, _("Ability type missing"))
        return

    selected_type = int(selected_type)
    selected_id = request.POST.get("ability_select")
    if not selected_id:
        messages.error(request, _("Ability missing"))
        return

    selected_id = int(selected_id)
    if selected_type not in ctx["available"] or selected_id not in ctx["available"][selected_type]["list"]:
        messages.error(request, _("Selezione non valida"))
        return

    ctx["character"].px_ability_list.add(selected_id)
    ctx["character"].save()
    messages.success(request, _("Ability acquired") + "!")

    get_undo_abilities(ctx, request, selected_id)


def get_undo_abilities(ctx, request, new_ability_id=None):
    px_undo = int(ctx["event"].get_config("px_undo", 0))
    config_name = "added_px"
    member = request.user.member
    val = member.get_config(config_name, "{}")
    added_map = ast.literal_eval(val)
    current_time = int(time.time())
    # clean from abilities out of the undo time windows
    for key in list(added_map.keys()):
        if added_map[key] < current_time - px_undo * 3600:
            del added_map[key]
    # add newly acquired ability and save it
    if px_undo and new_ability_id:
        added_map[str(new_ability_id)] = current_time
        save_single_config(member, config_name, json.dumps(added_map))

    # return map of abilities recently added, with int key
    return [int(k) for k in added_map.keys()]


@login_required
def character_relationships(request, s, n, num):
    ctx = get_event_run(request, s, n, status=True, signup=True)
    get_char_check(request, ctx, num, True)
    get_event_cache_all(ctx)

    ctx["rel"] = []
    que = PlayerRelationship.objects.filter(reg__member_id=ctx["char"]["player_id"], reg__run=ctx["run"])
    for tg_num, text in que.values_list("target__number", "text"):
        if "chars" in ctx and tg_num in ctx["chars"]:
            show = ctx["chars"][tg_num]
        else:
            try:
                ch = Character.objects.get(event=ctx["event"], number=tg_num)
                show = ch.show(ctx["run"])
            except ObjectDoesNotExist:
                continue

        show["text"] = text
        show["font_size"] = int(100 - ((len(text) / 50) * 4))
        ctx["rel"].append(show)

    return render(request, "larpmanager/event/character/relationships.html", ctx)


@login_required
def character_relationships_edit(request, s, n, num, oth):
    ctx = get_event_run(request, s, n, status=True, signup=True)
    get_char_check(request, ctx, num, True)

    ctx["relationship"] = None
    if oth != 0:
        get_player_relationship(ctx, oth)

    if user_edit(request, ctx, PlayerRelationshipForm, "relationship", oth):
        return redirect("character_relationships", s=ctx["event"].slug, n=ctx["run"].number, num=ctx["char"]["number"])
    return render(request, "larpmanager/orga/edit.html", ctx)


@require_POST
def show_char(request, s, n):
    ctx = get_event_run(request, s, n)
    get_event_cache_all(ctx)
    search = request.POST.get("text", "").strip()
    if not search.startswith(("#", "@", "^")):
        raise Http404(f"malformed request {search}")
    search = int(search[1:])
    if not search:
        raise Http404(f"not valid search {search}")
    if search not in ctx["chars"]:
        raise Http404(f"not present char number {search}")
    ch = ctx["chars"][search]
    tooltip = get_tooltip(ctx, ch)
    return JsonResponse({"content": f"<div class='show_char'>{tooltip}</div>"})
