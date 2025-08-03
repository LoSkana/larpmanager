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
import zipfile
from datetime import datetime
from decimal import Decimal
import pandas as pd

from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import ForeignKey
from django.db.models.functions import Lower

from larpmanager.cache.character import get_event_cache_fields
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
from larpmanager.models.member import Member, Membership, MembershipStatus
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
from larpmanager.utils.download import _get_column_names
from larpmanager.utils.edit import save_log


def go_upload(request, ctx, files):
    if request.POST.get("upload") == "cover":
        # check extension
        if zipfile.is_zipfile(files[0]):
            with zipfile.ZipFile(files[0]) as z_obj:
                cover_load(ctx, z_obj)
            z_obj.close()
            return ""

    if not request.FILES:
        return "ERR - No files upload"
    for f in request.FILES.values():
        if f.content_type in ['text/csv']:
            return f"ERR - detected non csv file: {f.name.}"

    if ctx["typ"] == "registration_form":
        return registration_question_loads(request, ctx, files)
    elif ctx["typ"] == "character_form":
        return character_question_loads(request, ctx, files)
    elif ctx["typ"] == "registration":
        return registrations_load(request, ctx, files)
    else:
        return writing_load(request, ctx, files)


def read_uploaded_csv(files):
    if not files:
        return None

    encodings = [
        'utf-8',
        'utf-8-sig',
        'latin1',
        'windows-1252',
        'utf-16',
        'utf-32',
        'ascii',
        'mac-roman',
        'cp437',
        'cp850',
    ]

    uploaded_file = next(iter(files.values()))

    for enc in encodings:
        try:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, encoding=enc, engine='python')
        except Exception:
            continue

    return None


def registrations_load(request, ctx, files):
    _get_column_names(ctx)
    allowed = list(ctx["columns"][0].keys())
    allowed.extend(ctx["fields"].keys())
    allowed = [a.lower() for a in allowed]

    input_df = read_uploaded_csv(files)
    if not input_df:
        return "ERR - Could not read input csv"

    for col in input_df.columns:
        if col.lower() not in allowed:
            return f"ERR - column not recognized: {col}"

    logs = []
    for row in input_df.to_dict(orient='records'):
        logs.append(reg_load(request, ctx, row))
    return logs


def reg_load(request, ctx, row):
    if "player" not in row:
        return "ERR - There is no player column"

    try:
        user = User.objects.get(email=row["player"])
    except ObjectDoesNotExist:
        return "ERR - Email not found"

    member = user.member

    try:
        membership = Membership.objects.get(member=member, assoc_id=ctx["event"].assoc_id)
    except ObjectDoesNotExist:
        return "ERR - Sharing data not found"

    if membership.status == MembershipStatus.EMPTY:
        return "ERR - User has not approved sharing of data"

    (reg, cr) = Registration.objects.get_or_create(run=ctx["run"], member=member, cancellation_date__isnull=True)

    logs = []

    for field, value in row.keys():
        _reg_field_load(ctx, reg, field, value, logs)

    reg.save()
    save_log(request.user.member, Registration, reg)

    if logs:
        return "KO - " + ",".join(logs)

    if cr:
        return "OK - Created"
    else:
        return "OK - Updated"


def _reg_field_load(ctx, reg, field, value, logs):
    if field == "player":
        return

    if not value:
        return

    if field == "ticket":
        assign_elem(ctx, reg, field, value, RegistrationTicket, logs)
    elif field == "character":
        _reg_assign_character(ctx, reg, value, logs)
    elif field == "pwyw":
        reg.pay_what = Decimal(value)
    else:
        # assign writing answer / choice
        # TODO

def assign_elem(ctx, obj, field, value, typ, logs):
    try:
        if value.isdigit():
            el = typ.objects.get(event=ctx["event"], number=int(value))
        else:
            el = typ.objects.get(event=ctx["event"], name__iexact=value)
    except ObjectDoesNotExist:
        logs.append(f"ERR - element {k} not found")
        return

    obj.__setattr__(field, el)

def _reg_assign_character(ctx, reg, value, logs):
    try:
        char = Character.objects.get(event=ctx["event"], name__iexact=value)
    except ObjectDoesNotExist:
        logs.append("ERR - Character not found")
        return

    # check if we have a registration with the same character
    que = RegistrationCharacterRel.objects.filter(
        reg__run=ctx["run"],
        reg__cancellation_date__isnull=True,
        character=char,
    )
    if que.exclude(reg_id=reg.id).count() > 0:
        logs.append("ERR - character already assigned")
        return

    RegistrationCharacterRel.objects.get_or_create(reg=reg, character=char)


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


def assign_faction(ch, v, run, log):
    for fac_name in v.split(","):
        try:
            fac = Faction.objects.get(name__iexact=fac_name.strip(), event=run.event)
            ch.save()  # to be sure
            fac.characters.add(ch)
            fac.save()
        except ObjectDoesNotExist:
            log.append(f"Faction not found: {fac_name}")


def elements_load(request, ctx, csv_upload):
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


def assign_choice_answer(ctx, character, value, key, log):
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
                log.append(f"Problem with question {key}: couldn't find option {input_opt}")
                continue
            WritingChoice.objects.create(element_id=character.id, question_id=question_id, option_id=option_id)



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

    if len(row) < fields[k]:
        return ""

    v = row[fields[k]].strip()
    v = "<br />".join(v.strip().split("\n"))
    if not v:
        return ""

    log = []

    if chars and k in ["presentation", "text"]:
        v = replace_char_names(v, chars)
    if k == "mirror":
        get_mirror_instance(v, event)
    elif k in rels:
        assign_elem(ch, v, k, rels[k], event, log)
    elif "questions_inverted" in ctx and k in ctx["questions_inverted"]:
        assign_choice_answer(ctx, ch, v, k, log)
    elif k == "factions":
        assign_faction(ch, v, ctx["run"], log)
    elif k == "presentation":
        ch.teaser = v
    else:
        ch.__setattr__(k, v)
    return ",".join(log)


def get_mirror_instance(v, e):
    try:
        return e.get_elements(Character).get(number=v)
    except ObjectDoesNotExist:
        return None
