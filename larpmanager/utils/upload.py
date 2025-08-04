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

import io
import os
import shutil
from datetime import datetime
from decimal import Decimal

import pandas as pd
from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.functions import Lower

from larpmanager.models.form import (
    QuestionApplicable,
    QuestionType,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationTicket,
)
from larpmanager.models.utils import UploadToPathAndRename
from larpmanager.models.writing import (
    Character,
    Faction,
    Plot,
    PlotCharacterRel,
    Relationship,
)
from larpmanager.utils.download import _get_column_names
from larpmanager.utils.edit import save_log


def go_upload(request, ctx, form):
    # FIX
    # if request.POST.get("upload") == "cover":
    #     # check extension
    #     if zipfile.is_zipfile(form[0]):
    #         with zipfile.ZipFile(form[0]) as z_obj:
    #             cover_load(ctx, z_obj)
    #         z_obj.close()
    #         return ""

    if ctx["typ"] == "registration_form":
        return registration_question_loads(request, ctx, form)
    elif ctx["typ"] == "character_form":
        return character_question_loads(request, ctx, form)
    elif ctx["typ"] == "registration":
        return registrations_load(request, ctx, form)
    else:
        return writing_load(request, ctx, form)


def _read_uploaded_csv(uploaded_file):
    if not uploaded_file:
        return None

    encodings = [
        "utf-8",
        "utf-8-sig",
        "latin1",
        "windows-1252",
        "utf-16",
        "utf-32",
        "ascii",
        "mac-roman",
        "cp437",
        "cp850",
    ]

    for encoding in encodings:
        try:
            uploaded_file.seek(0)
            decoded = uploaded_file.read().decode(encoding)
            text_io = io.StringIO(decoded)
            return pd.read_csv(text_io, encoding=encoding, sep=None, engine="python")
        except Exception as err:
            print(err)
            continue

    return None


def _get_file(ctx, file, column_id=None):
    _get_column_names(ctx)
    allowed = []
    if column_id is not None:
        allowed.extend(list(ctx["columns"][0].keys()))
    if "fields" in ctx:
        allowed.extend(ctx["fields"].keys())
    allowed = [a.lower() for a in allowed]

    input_df = _read_uploaded_csv(file)
    if input_df is None:
        return None, ["ERR - Could not read input csv"]

    input_df.columns = [c.lower() for c in input_df.columns]

    for col in input_df.columns:
        if col.lower() not in allowed:
            return None, [f"ERR - column not recognized: {col}"]

    return input_df, []


def registrations_load(request, ctx, form):
    (input_df, logs) = _get_file(ctx, form.cleaned_data["first"], 0)

    que = ctx["event"].get_elements(RegistrationQuestion).prefetch_related("options")
    questions = _get_questions(que)

    if input_df is not None:
        for row in input_df.to_dict(orient="records"):
            logs.append(_reg_load(request, ctx, row, questions))
    return logs


def _reg_load(request, ctx, row, questions):
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

    for field, value in row.items():
        _reg_field_load(ctx, reg, field, value, questions, logs)

    reg.save()
    save_log(request.user.member, Registration, reg)

    if logs:
        msg = "KO - " + ",".join(logs)
    elif cr:
        msg = f"OK - Created {member}"
    else:
        msg = f"OK - Updated {member}"

    return msg


def _reg_field_load(ctx, reg, field, value, questions, logs):
    if field == "player":
        return

    if not value:
        return

    if field == "ticket":
        _assign_elem(ctx, reg, field, value, RegistrationTicket, logs)
    elif field == "character":
        _reg_assign_character(ctx, reg, value, logs)
    elif field == "pwyw":
        reg.pay_what = Decimal(value)
    else:
        _assign_choice_answer(reg, field, value, questions, logs, is_registration=True)


def _assign_elem(ctx, obj, field, value, typ, logs):
    try:
        if value.isdigit():
            el = typ.objects.get(event=ctx["event"], number=int(value))
        else:
            el = typ.objects.get(event=ctx["event"], name__iexact=value)
    except ObjectDoesNotExist:
        logs.append(f"ERR - element {field} not found")
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


def writing_load(request, ctx, form):
    logs = []
    uploaded_file = form.cleaned_data.get("first", None)
    if uploaded_file:
        (input_df, logs) = _get_file(ctx, uploaded_file)

        que = (
            ctx["event"].get_elements(WritingQuestion).filter(applicable=ctx["writing_typ"]).prefetch_related("options")
        )
        questions = _get_questions(que)

        if input_df is not None:
            for row in input_df.to_dict(orient="records"):
                logs.append(element_load(request, ctx, row, questions))

    # upload relationships
    if ctx["typ"] == "character":
        uploaded_file = form.cleaned_data.get("second", None)
        if uploaded_file:
            (input_df, new_logs) = _get_file(ctx, uploaded_file, 0)
            chars = {el["name"].lower(): el["id"] for el in ctx["event"].get_elements(Character).values("id", "name")}
            if input_df is not None:
                for row in input_df.to_dict(orient="records"):
                    new_logs.append(_relationships_load(row, chars))
            logs.extend(new_logs)

    # upload rels
    if ctx["typ"] == "plot":
        uploaded_file = form.cleaned_data.get("second", None)
        if uploaded_file:
            (input_df, new_logs) = _get_file(ctx, uploaded_file, 0)
            chars = {el["name"].lower(): el["id"] for el in ctx["event"].get_elements(Character).values("id", "name")}
            plots = {el["name"].lower(): el["id"] for el in ctx["event"].get_elements(Plot).values("id", "name")}
            if input_df is not None:
                for row in input_df.to_dict(orient="records"):
                    new_logs.append(_plot_rels_load(row, chars, plots))
            logs.extend(new_logs)

    return logs


def _plot_rels_load(row, chars, plots):
    char = row.get("character", "").lower()
    if char not in chars:
        return f"ERR - source not found {char}"
    char_id = chars[char]

    plot = row.get("plot", "").lower()
    if plot not in plots:
        return f"ERR - target not found {plot}"
    plot_id = plots[plot]

    rel, _ = PlotCharacterRel.objects.get_or_create(character_id=char_id, plot_id=plot_id)
    rel.text = row.get("text")
    rel.save()
    return f"OK - Plot role {char} {plot}"


def _relationships_load(row, chars):
    source_char = row.get("source", "").lower()
    if source_char not in chars:
        return f"ERR - source not found {source_char}"
    source_id = chars[source_char]

    target_char = row.get("target", "").lower()
    if target_char not in chars:
        return f"ERR - target not found {target_char}"
    target_id = chars[target_char]

    relation, _ = Relationship.objects.get_or_create(source_id=source_id, target_id=target_id)
    relation.text = row.get("text")
    relation.save()
    return f"OK - Relationship {source_char} {target_char}"


def _get_questions(que):
    questions = {}
    for question in que:
        options = {option.name.lower(): option.id for option in question.options.all()}
        questions[question.name.lower()] = {"id": question.id, "typ": question.typ, "options": options}
    return questions


def _assign_choice_answer(element, field, value, questions, logs, is_registration=False):
    field = field.lower()
    if field not in questions:
        logs.append(f"ERR - question not found {field}")
        return

    question = questions[field]

    # check if answer
    if question["typ"] in [QuestionType.TEXT, QuestionType.PARAGRAPH, QuestionType.EDITOR]:
        if is_registration:
            answer, _ = RegistrationAnswer.objects.get_or_create(reg_id=element.id, question_id=question["id"])
        else:
            answer, _ = WritingAnswer.objects.get_or_create(element_id=element.id, question_id=question["id"])
        answer.text = value
        answer.save()

    # check if choice
    else:
        if is_registration:
            RegistrationChoice.objects.filter(reg_id=element.id, question_id=question["id"]).delete()
        else:
            WritingChoice.objects.filter(element_id=element.id, question_id=question["id"]).delete()

        for input_opt_orig in value.split(","):
            input_opt = input_opt_orig.lower().strip()
            option_id = question["options"].get(input_opt)
            if not option_id:
                logs.append(f"Problem with question {field}: couldn't find option {input_opt}")
                continue

            if is_registration:
                RegistrationChoice.objects.create(reg_id=element.id, question_id=question["id"], option_id=option_id)
            else:
                WritingChoice.objects.create(element_id=element.id, question_id=question["id"], option_id=option_id)


def element_load(request, ctx, row, questions):
    field_name = ctx["field_name"].lower()
    if field_name not in row:
        return "ERR - There is no name in fields"

    name = row[field_name]
    typ = QuestionApplicable.get_applicable(ctx["typ"])
    writing_cls = QuestionApplicable.get_applicable_inverse(typ)

    created = False
    try:
        element = writing_cls.objects.get(event=ctx["event"], name__iexact=name)
    except ObjectDoesNotExist:
        element = writing_cls.objects.create(event=ctx["event"], name=name)
        created = True

    logs = []

    ctx["fields"] = {key.lower(): content for key, content in ctx["fields"].items()}

    for field, value in row.items():
        _writing_load_field(ctx, element, field, value, questions, logs)

    element.save()
    save_log(request.user.member, writing_cls, element)

    if logs:
        return "KO - " + ",".join(logs)

    if created:
        return f"OK - Created {name}"
    else:
        return f"OK - Updated {name}"


def _writing_load_field(ctx, element, field, value, questions, logs):
    field_type = ctx["fields"][field]

    if field_type == QuestionType.NAME:
        return

    value = "<br />".join(str(value).strip().split("\n"))
    if not value:
        return

    if field_type == QuestionType.MIRROR:
        _get_mirror_instance(ctx, element, value, logs)
    elif field_type == QuestionType.HIDE:
        element.hide = value.lower() == "true"
    elif field_type == QuestionType.FACTIONS:
        _assign_faction(ctx, element, value, logs)
    elif field_type == QuestionType.TEASER:
        element.teaser = value
    elif field_type == QuestionType.SHEET:
        element.text = value
    elif field_type == QuestionType.TITLE:
        element.title = value
    # TODO implement
    # elif field_type == QuestionType.COVER:
    #     element.cover = value
    # elif field_type == QuestionType.PROGRESS:
    #     element.cover = value
    # elif field_type == QuestionType.ASSIGNED:
    #     element.cover = value
    else:
        _assign_choice_answer(element, field, value, questions, logs)


def _get_mirror_instance(ctx, element, value, logs):
    try:
        element.mirror = ctx["event"].get_elements(Character).get(name__iexact=value)
    except ObjectDoesNotExist:
        logs.append(f"ERR - mirror not found: {value}")


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


def _assign_faction(ctx, element, value, logs):
    for fac_name in value.split(","):
        try:
            fac = Faction.objects.get(name__iexact=fac_name.strip(), event=ctx["event"])
            element.save()  # to be sure
            fac.characters.add(element)
            fac.save()
        except ObjectDoesNotExist:
            logs.append(f"Faction not found: {fac_name}")


def registration_question_loads(request, ctx, files):
    pass


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


def character_question_loads(request, ctx, files):
    pass


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
