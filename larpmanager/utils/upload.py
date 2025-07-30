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
import os
import shutil
import traceback
import zipfile
from datetime import datetime
from decimal import Decimal

from django.conf import settings as conf_settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import ForeignKey
from django.db.models.functions import Lower
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_fields
from larpmanager.forms.writing import UploadElementsForm
from larpmanager.models.form import (
    QuestionType,
    RegistrationOption,
    RegistrationQuestion,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    get_ordered_registration_questions,
)
from larpmanager.models.member import Member
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationTicket,
)
from larpmanager.models.utils import UploadToPathAndRename
from larpmanager.models.writing import (
    Character,
    Faction,
    replace_char_names,
)
from larpmanager.utils.edit import save_log


def upload_elements(request, ctx, typ, nm, red):
    form = UploadElementsForm(request.POST, request.FILES)
    redr = reverse(red, args=[ctx["event"].slug, ctx["run"].number])
    if form.is_valid():
        try:
            # print(request.FILES)
            ctx["logs"] = element_load(request, ctx, request.FILES["elem"], typ, nm)
            ctx["redr"] = redr
            messages.success(request, _("Elements uploaded") + "!")
            return render(request, "larpmanager/orga/uploads.html", ctx)

        except Exception as exp:
            print(traceback.format_exc())
            messages.error(request, _("Unknow error on upload") + f": {exp}")
    else:
        messages.error(request, _("invalid form") + f": {form.errors}")
    return HttpResponseRedirect(redr)


def element_load(request, ctx, fil, typ, nm):
    if request.POST.get("upload") == "cover":
        # check extension
        if zipfile.is_zipfile(fil):
            with zipfile.ZipFile(fil) as z_obj:
                cover_load(ctx, z_obj)
            z_obj.close()
            return ""

    if nm == "registration_question":
        return registration_question_loads(request, ctx, fil)
    elif nm == "character_question":
        return character_question_loads(request, ctx, fil)

    return elements_load(request, ctx, fil, typ, nm)


def get_csv_upload_tmp(csv_upload, run):
    tmp_file = os.path.join(conf_settings.MEDIA_ROOT, "tmp")
    tmp_file = os.path.join(tmp_file, run.event.slug)
    if not os.path.exists(tmp_file):
        os.makedirs(tmp_file)
    tmp_file = os.path.join(tmp_file, datetime.now().strftime("%Y-%m-%d-%H:%M:%S"))
    with open(tmp_file, "wb") as destination:
        for chunk in csv_upload.chunks():
            destination.write(chunk)
    return tmp_file


def cover_load(ctx, z_obj):
    # extract images
    fpath = os.path.join(conf_settings.MEDIA_ROOT, "cover_load")
    fpath = os.path.join(fpath, ctx["run"].event.slug)
    fpath = os.path.join(fpath, str(ctx["run"].number))
    if os.path.exists(fpath):
        shutil.rmtree(fpath)
    z_obj.extractall(path=fpath)
    covers = {}
    # get images
    for root, _dirnames, filenames in os.walk(fpath):
        for el in filenames:
            num = os.path.splitext(el)[0]
            covers[num] = os.path.join(root, el)
    print(covers)
    upload_to = UploadToPathAndRename("character/cover/")
    # cicle characters
    for c in ctx["run"].event.get_elements(Character):
        num = str(c.number)
        if num not in covers:
            continue
        fn = upload_to.__call__(c, covers[num])
        c.cover = fn
        c.save()
        os.rename(covers[num], os.path.join(conf_settings.MEDIA_ROOT, fn))


def assign_faction(ch, v, run):
    logs = ""
    for fac_name in v.split(","):
        try:
            fac = Faction.objects.get(name__iexact=fac_name.strip(), event=run.event)
            ch.save()  # to be sure
            fac.characters.add(ch)
            fac.save()
        except ObjectDoesNotExist:
            logs += f" - Faction not found: {fac_name}"
    return logs


def elements_load(request, ctx, csv_upload, typ, nm):
    # prepare custom fields for character
    if nm == "character" and "character" in ctx["features"]:
        res = {"chars": {}}
        get_event_cache_fields(ctx, res, only_visible=False)
        inv = {value["name"].lower(): key for key, value in ctx["questions"].items()}
        ctx["questions_inverted"] = inv

    # get all characters name for replacement
    chars = {}
    event = ctx["run"].event.get_class_parent(typ)
    if ctx["run"].event.get_config("writing_substitute", True):
        for c in event.get_elements(Character):
            chars[c.name] = c.number

    # Get relations models
    rels = {}
    # noinspection PyProtectedMember
    for el in typ._meta.get_fields():
        if not isinstance(el, ForeignKey):
            continue
        rels[el.name] = el.related_model

    tmp_file = get_csv_upload_tmp(csv_upload, ctx["run"])
    with open(tmp_file, newline="") as csvfile:
        dialect = csv.Sniffer().sniff(csvfile.readline(), delimiters=";,\t")
        csvfile.seek(0)
        csv_data = csv.reader(csvfile, dialect)

        # Read fields
        fields = {}
        header = next(csv_data)
        aux = {}
        for i in range(0, len(header)):
            v = header[i].lower().replace("\ufeff", "").strip()
            fields[v] = i
            aux[i] = v

        # Read rows
        logs = []
        cnt = 0
        for row in csv_data:
            rpr = ", ".join([f"{aux[i]}: {row[i]}" for i in range(0, min(len(aux), len(row)))])
            log = f"# ROW{cnt} [ {rpr} ] "
            try:
                if nm == "registration":
                    log += registration_load(request, ctx, row, fields, event)
                else:
                    log += writing_load(request, ctx, row, fields, typ, rels, event, chars)
            except Exception as err:
                log += "EXP - " + str(err)

            logs.append(log)
            cnt += 1

    return logs


def registration_load(request, ctx, row, fields, event):
    if "player" not in fields:
        return "ERR - There is no player in fields"

    if len(row) < fields["player"]:
        return "ERR - Can't find player column for this row"

    v = row[fields["player"]]

    if "@" in v:
        (user, cr) = User.objects.get_or_create(email=v, username=v)
        member = user.member
    else:
        aux = v.rsplit(" ", 1)
        member = Member.objects.get(name__iexact=aux[0], surname__iexact=aux[1])

    (el, cr) = Registration.objects.get_or_create(run=ctx["run"], member=member, cancellation_date__isnull=True)

    log = ""

    for k in fields:
        log += _registration_load_field(ctx, el, event, fields, k, row)

    el.save()
    save_log(request.user.member, Registration, el)

    if cr:
        return "OK - Created" + log
    else:
        return "OK - Updated" + log


def _registration_load_field(ctx, el, event, fields, k, row):
    if k == "player":
        return

    v = row[fields[k]]
    if not v:
        return

    log = ""

    if k == "ticket":
        assign_elem(el, v, k, RegistrationTicket, event)
    elif k == "character":
        char = Character.objects.get(event=event, number=v)

        # check if we have a registration with the same character
        que = RegistrationCharacterRel.objects.filter(
            reg__run=ctx["run"],
            reg__cancellation_date__isnull=True,
            character=char,
        )
        if que.exclude(reg_id=el.id).count() > 0:
            log = "ERR - character already assigned"
        RegistrationCharacterRel.objects.get_or_create(reg=el, character=char)

    elif k == "pwyw":
        el.pay_what = Decimal(v)
    else:
        el.__setattr__(k, v)

    return log


def registration_question_loads(request, ctx, csv_upload):
    questions = get_ordered_registration_questions(ctx)

    tmp_file = get_csv_upload_tmp(csv_upload, ctx["run"])
    with open(tmp_file, newline="") as csvfile:
        dialect = csv.Sniffer().sniff(csvfile.readline(), delimiters=";,\t")
        csvfile.seek(0)
        csv_data = csv.reader(csvfile, dialect)
        _ = next(csv_data)

        # Read rows
        logs = []
        cnt = 0
        for row in csv_data:
            log = f"# ROW{cnt} :"
            try:
                question = None
                if cnt < len(questions):
                    question = questions[cnt]
                log += registration_question_load(request, ctx, row, question)
            except Exception as err:
                log += "EXP - " + str(err)

            logs.append(log)
            cnt += 1

    return logs


def registration_question_load(request, ctx, row, question):
    cr = False
    if not question:
        question = RegistrationQuestion(event=ctx["event"])
        cr = True

    question.typ = row[0]
    question.name = row[1]
    question.description = row[2]
    question.status = row[3]
    question.save()
    save_log(request.user.member, RegistrationQuestion, question)

    num_options = int(row[4])
    options = question.options.all()
    for cnt in range(0, num_options):
        if cnt < len(options):
            option = options[cnt]
        else:
            option = RegistrationOption(event=ctx["event"], question=question)

        ff = 5 + cnt * 4
        option.name = row[ff]
        option.description = row[ff + 1]
        option.price = float(row[ff + 2])
        option.max_available = int(row[ff + 3])
        option.save()
        save_log(request.user.member, RegistrationOption, option)

    if num_options > len(options):
        for cnt in range(num_options + 1, len(options)):
            option = options[cnt]
            option.delete()
            save_log(request.user.member, WritingOption, option, dl=True)

    if cr:
        return "OK - Created"
    else:
        return "OK - Updated"


def character_question_loads(request, ctx, csv_upload):
    questions = ctx["event"].get_elements(WritingQuestion).order_by("order").prefetch_related("options")

    tmp_file = get_csv_upload_tmp(csv_upload, ctx["run"])
    with open(tmp_file, newline="") as csvfile:
        dialect = csv.Sniffer().sniff(csvfile.readline(), delimiters=";,\t")
        csvfile.seek(0)
        csv_data = csv.reader(csvfile, dialect)
        _ = next(csv_data)

        # Read rows
        logs = []
        cnt = 0
        for row in csv_data:
            log = f"# ROW{cnt} :"
            try:
                question = None
                if cnt < len(questions):
                    question = questions[cnt]
                log += character_question_load(request, ctx, row, question)
            except Exception as err:
                log += "EXP - " + str(err)

            logs.append(log)
            cnt += 1

    return logs


def character_question_load(request, ctx, row, question):
    cr = False
    if not question:
        question = WritingQuestion(event=ctx["event"])
        cr = True

    question.typ = row[0]
    question.name = row[1]
    question.description = row[2]
    question.status = row[3]
    question.visibility = row[4]
    question.save()
    save_log(request.user.member, WritingQuestion, question)

    num_options = int(row[5])
    options = question.options.order_by("order")
    for cnt in range(0, num_options):
        if cnt < len(options):
            option = options[cnt]
        else:
            option = WritingOption(event=ctx["event"], question=question)

        ff = 6 + cnt * 5
        option.name = row[ff]
        option.description = row[ff + 1]
        option.max_available = int(row[ff + 2])
        if option.pk:
            option.dependents.clear()
            option.tickets.clear()
        dependent_text = row[ff + 3].strip()
        if dependent_text:
            display_list = [d.strip().lower() for d in dependent_text.split(",")]
            option.save()
            dependent_options = WritingOption.objects.annotate(lower_name=Lower("name")).filter(
                lower_display__in=display_list, event=ctx["event"]
            )
            option.dependents.set(dependent_options)
        tickets_text = row[ff + 4].strip()
        if tickets_text:
            name_list = [d.strip().lower() for d in tickets_text.split(",")]
            option.save()
            tickets_options = RegistrationTicket.objects.annotate(lower_name=Lower("name")).filter(
                lower_name__in=name_list, event=ctx["event"]
            )
            option.dependents.set(tickets_options)
        option.save()
        save_log(request.user.member, WritingOption, option)

    if num_options > len(options):
        for cnt in range(num_options + 1, len(options)):
            option = options[cnt]
            option.delete()
            save_log(request.user.member, WritingOption, option, dl=True)

    if cr:
        return "OK - Created"
    else:
        return "OK - Updated"


def assign_choice_answer(ctx, character, value, key):
    question_id = ctx["questions_inverted"][key]

    # check if answer
    if ctx["questions"][question_id]["typ"] in [QuestionType.TEXT, QuestionType.PARAGRAPH, QuestionType.EDITOR]:
        (car, cr) = WritingAnswer.objects.get_or_create(element_id=character.id, question_id=question_id)
        car.text = value
        car.save()

    # check if choice
    else:
        WritingChoice.objects.filter(element_id=character.id, question_id=question_id).delete()
        for input_opt_orig in value.split(","):
            input_opt = input_opt_orig.lower().strip()
            option_id = None
            for ido, opt in ctx["options"].items():
                if opt["name"].lower().strip() == input_opt and opt["question_id"] == question_id:
                    option_id = ido
            if not option_id:
                return f" - Problem with question {key}: couldn't find option {input_opt}"
            WritingChoice.objects.create(element_id=character.id, question_id=question_id, option_id=option_id)

    return ""


def writing_load(request, ctx, row, fields, typ, rels, event, chars):
    if "number" not in fields:
        return "ERR - There is no number in fields"

    if len(row) < fields["number"]:
        return "ERR - Can't find number column for this row"

    # print(fields["number"])
    # print(row[fields["number"]])

    num = int(row[fields["number"]])

    try:
        ch = typ.objects.get(event=event, number=num)
        created = False
    except ObjectDoesNotExist:
        ch = typ()
        ch.event = event
        ch.number = num
        ch.save()
        created = True

    log = ""

    for k in fields:
        log += _writing_load_field(ch, chars, ctx, event, fields, k, rels, row)

    # update_chars_all(ch)
    # print(row)

    ch.save()
    save_log(request.user.member, typ, ch)

    if created:
        return "OK - Created" + log
    else:
        return "OK - Updated" + log


def _writing_load_field(ch, chars, ctx, event, fields, k, rels, row):
    if k == "number":
        return ""

    # meta_field_type = typ._meta.get_field(k).get_internal_type()
    # print(meta_field_type)
    if len(row) < fields[k]:
        return ""

    v = row[fields[k]]
    v = "<br />".join(v.strip().split("\n"))
    if not v:
        return ""

    log = ""

    if chars and k in ["presentation", "text"]:
        v = replace_char_names(v, chars)
    if k == "mirror":
        get_mirror_instance(v, event)
    elif k == "player":
        log = assign_player(ctx, ch, v)
    elif k in rels:
        assign_elem(ch, v, k, rels[k], event)
    elif "questions_inverted" in ctx and k in ctx["questions_inverted"]:
        log = assign_choice_answer(ctx, ch, v, k)
    elif k == "factions":
        log = assign_faction(ch, v, ctx["run"])
    elif k == "presentation":
        ch.teaser = v
    else:
        ch.__setattr__(k, v)
    return log


def assign_player(ctx, ch, v):
    if "@" in v:
        try:
            user = User.objects.get(email=v)
        except ObjectDoesNotExist:
            return f" - Problem with player '{v}': couldn't find"
        member = user.member
    else:
        aux = v.rsplit(" ", 1)
        try:
            member = Member.objects.get(name__iexact=aux[0], surname__iexact=aux[1])
        except ObjectDoesNotExist:
            return f" - Problem with player '{v}': couldn't find"

    ch.player = member

    regs = Registration.objects.filter(member=member, run=ctx["run"], cancellation_date__isnull=True)
    if not regs:
        return " - Registration not found, character not assigned!"

    RegistrationCharacterRel.objects.get_or_create(character=ch, reg=regs.first())
    return ""


def assign_elem(ch, v, k, rel, e):
    if v.isdigit():
        el = rel.objects.get(event=e, number=int(v))
    else:
        el = rel.objects.get(event=e, name=v)
    ch.__setattr__(k, el)


def get_mirror_instance(v, e):
    try:
        return e.get_elements(Character).get(number=v)
    except ObjectDoesNotExist:
        return None
