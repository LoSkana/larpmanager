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

from larpmanager.models.casting import Quest, QuestType
from larpmanager.models.form import (
    QuestionApplicable,
    QuestionStatus,
    QuestionType,
    QuestionVisibility,
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
        return form_load(request, ctx, form, is_registration=True)
    elif ctx["typ"] == "character_form":
        return form_load(request, ctx, form, is_registration=False)
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
            return pd.read_csv(text_io, encoding=encoding, sep=None, engine="python", dtype=str)
        except Exception as err:
            print(err)
            continue

    return None


def _get_file(ctx, file, column_id=None):
    _get_column_names(ctx)
    allowed = []
    if column_id is not None:
        allowed.extend(list(ctx["columns"][column_id].keys()))
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
        (input_df, logs) = _get_file(ctx, uploaded_file, 0)

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
            (input_df, new_logs) = _get_file(ctx, uploaded_file, 1)
            chars = {el["name"].lower(): el["id"] for el in ctx["event"].get_elements(Character).values("id", "name")}
            if input_df is not None:
                for row in input_df.to_dict(orient="records"):
                    new_logs.append(_relationships_load(row, chars))
            logs.extend(new_logs)

    # upload rels
    if ctx["typ"] == "plot":
        uploaded_file = form.cleaned_data.get("second", None)
        if uploaded_file:
            (input_df, new_logs) = _get_file(ctx, uploaded_file, 1)
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
    if field == "typ":
        try:
            element.typ = ctx["event"].get_elements(QuestType).get(name__iexact=value)
        except ObjectDoesNotExist:
            logs.append(f"ERR - quest type not found: {value}")
        return
    if field == "quest":
        try:
            element.quest = ctx["event"].get_elements(Quest).get(name__iexact=value)
        except ObjectDoesNotExist:
            logs.append(f"ERR - quest not found: {value}")
        return

    field_type = ctx["fields"][field]

    if field_type == QuestionType.NAME:
        return

    value = "<br />".join(str(value).strip().split("\n"))
    if not value:
        return

    _writing_question_load(ctx, element, field, field_type, logs, questions, value)


def _writing_question_load(ctx, element, field, field_type, logs, questions, value):
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


def _assign_faction(ctx, element, value, logs):
    for fac_name in value.split(","):
        try:
            fac = Faction.objects.get(name__iexact=fac_name.strip(), event=ctx["event"])
            element.save()  # to be sure
            fac.characters.add(element)
            fac.save()
        except ObjectDoesNotExist:
            logs.append(f"Faction not found: {fac_name}")


def form_load(request, ctx, form, is_registration=True):
    logs = []

    # upload questions
    uploaded_file = form.cleaned_data.get("first", None)
    if uploaded_file:
        (input_df, logs) = _get_file(ctx, uploaded_file, 0)
        if input_df is not None:
            for row in input_df.to_dict(orient="records"):
                logs.append(_questions_load(ctx, row, is_registration))

    # upload options
    uploaded_file = form.cleaned_data.get("second", None)
    if uploaded_file:
        (input_df, new_logs) = _get_file(ctx, uploaded_file, 1)
        if input_df is not None:
            question_cls = WritingQuestion
            if is_registration:
                question_cls = RegistrationQuestion
            questions = {
                el["name"].lower(): el["id"] for el in ctx["event"].get_elements(question_cls).values("id", "name")
            }
            for row in input_df.to_dict(orient="records"):
                new_logs.append(_options_load(ctx, row, questions, is_registration))
        logs.extend(new_logs)

    return logs


def invert_dict(d):
    return {v: k for k, v in d.items()}


def _questions_load(ctx, row, is_registration):
    name = row.get("name")
    if not name:
        return "ERR - name not found"

    mappings = {
        "typ": invert_dict(QuestionType.get_mapping()),
        "status": invert_dict(QuestionStatus.get_mapping()),
        "applicable": invert_dict(QuestionApplicable.get_mapping()),
        "visibility": invert_dict(QuestionVisibility.get_mapping()),
    }

    if is_registration:
        instance, created = RegistrationQuestion.objects.get_or_create(
            event=ctx["event"],
            name__iexact=name,
            defaults={"name": name},
        )
    else:
        if "applicable" not in row:
            return "ERR - missing applicable column"
        applicable = row["applicable"]
        if applicable not in mappings["applicable"]:
            return "ERR - unknown applicable"

        instance, created = WritingQuestion.objects.get_or_create(
            event=ctx["event"],
            name__iexact=name,
            applicable=mappings["applicable"][applicable],
            defaults={"name": name},
        )

    for field, value in row.items():
        if not value or pd.isna(value) or field in ["applicable", "name"]:
            continue
        new_value = value
        if field in mappings:
            new_value = new_value.lower().strip()
            if new_value not in mappings[field]:
                return f"ERR - unknow value {value} for field {field}"
            new_value = mappings[field][new_value]
        if field == "max_length":
            new_value = int(value)
        setattr(instance, field, new_value)

    instance.save()

    if created:
        msg = f"OK - Created {name}"
    else:
        msg = f"OK - Updated {name}"
    return msg


def _options_load(ctx, row, questions, is_registration):
    for field in ["name", "question"]:
        if field not in row:
            return f"ERR - column {field} missing"

    name = row["name"]
    if not name:
        return "ERR - empty name"

    question = row["question"].lower()
    if question not in questions:
        return "ERR - question not found"
    question_id = questions[question]

    if is_registration:
        instance, created = RegistrationOption.objects.get_or_create(
            event=ctx["event"],
            question_id=question_id,
            name__iexact=name,
            defaults={"name": name},
        )
    else:
        instance, created = WritingOption.objects.get_or_create(
            event=ctx["event"],
            name__iexact=name,
            question_id=question_id,
            defaults={"name": name},
        )

    for field, value in row.items():
        if not value or pd.isna(value):
            continue
        new_value = value
        if field in ["question", "name"]:
            continue
        if field in ["max_available", "price"]:
            new_value = int(new_value)
        setattr(instance, field, new_value)

    instance.save()

    if created:
        return f"OK - Created {name}"
    else:
        return f"OK - Updated {name}"


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
