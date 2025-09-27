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
from larpmanager.models.experience import AbilityPx, AbilityTypePx
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    QuestionVisibility,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationTicket,
    TicketTier,
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
    """Route uploaded files to appropriate processing functions.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary with upload type and settings
        form: Uploaded file form data

    Returns:
        list: Result messages from processing function
    """
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
    elif ctx["typ"] == "px_abilitie":
        return abilities_load(request, ctx, form)
    elif ctx["typ"] == "registration_ticket":
        return tickets_load(request, ctx, form)
    else:
        return writing_load(request, ctx, form)


def _read_uploaded_csv(uploaded_file):
    """Read CSV file with multiple encoding fallbacks.

    Args:
        uploaded_file: Django uploaded file object

    Returns:
        pandas.DataFrame or None: Parsed CSV data or None if failed
    """
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
    """Get file path and save uploaded file to media directory.

    Args:
        ctx: Context dictionary with event information
        file: Uploaded file object
        column_id: Optional column identifier for file naming

    Returns:
        tuple: (DataFrame, error_list) or (None, error_list) if failed
    """
    """Get file path and save uploaded file to media directory.

    Args:
        ctx: Context dictionary with event information
        file: Uploaded file object
        column_id: Optional column identifier for file naming

    Returns:
        str: Saved file path relative to media root
    """
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
    """Load registration data from uploaded CSV file.

    Args:
        request: Django HTTP request object
        ctx: Context dictionary with event and form settings
        form: Form data containing uploaded CSV file

    Returns:
        str: HTML formatted result message with processing statistics
    """
    (input_df, logs) = _get_file(ctx, form.cleaned_data["first"], 0)

    que = ctx["event"].get_elements(RegistrationQuestion).prefetch_related("options")
    questions = _get_questions(que)

    if input_df is not None:
        for row in input_df.to_dict(orient="records"):
            logs.append(_reg_load(request, ctx, row, questions))
    return logs


def _reg_load(request, ctx, row, questions):
    """Load registration data from CSV row for bulk import.

    Creates or updates registrations with field validation, membership checks,
    and question processing for event registration imports.
    """
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
    """Load individual registration field from CSV data.

    Args:
        ctx: Context dictionary with event data
        reg: Registration instance to update
        field: Field name from CSV
        value: Field value from CSV
        questions: Dictionary of registration questions
        logs: List to append error messages to
    """
    if field == "player":
        return

    if not value or pd.isna(value):
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
    """Assign a character to a registration during upload processing.

    Args:
        ctx: Context dictionary containing event and run data
        reg: Registration object to assign character to
        value: Character name string to look up
        logs: List to append error messages to
    """
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
    """Load writing data from uploaded files and process relationships.

    Args:
        request: HTTP request object
        ctx: Context dictionary with event and writing type data
        form: Form object containing uploaded files

    Returns:
        List of log messages from the loading process
    """
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
    """Assign choice answers to form elements during bulk import.

    Processes choice field assignments with validation, option matching,
    and proper relationship creation for registration or character forms.
    """
    field = field.lower()
    if field not in questions:
        logs.append(f"ERR - question not found {field}")
        return

    question = questions[field]

    # check if answer
    if question["typ"] in [BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR]:
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
    """Load generic element data from CSV row for bulk import.

    Processes element creation or updates with field validation,
    question processing, and proper logging for various element types.
    """
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
    """
    Load writing field data during upload processing.

    Args:
        ctx: Context dictionary with event and field information
        element: Writing element to update
        field: Field name to process
        value: Field value from upload
        questions: Dictionary of available questions
        logs: List to append error messages to
    """
    if pd.isna(value):
        return

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

    if field_type in [WritingQuestionType.NAME, "skip"]:
        return

    value = "<br />".join(str(value).strip().split("\n"))
    if not value:
        return

    _writing_question_load(ctx, element, field, field_type, logs, questions, value)


def _writing_question_load(ctx, element, field, field_type, logs, questions, value):
    """Process and load writing question values into element fields.

    Args:
        ctx: Context dictionary
        element: Target writing element to update
        field: Field identifier
        field_type: WritingQuestionType enum value
        logs: List to collect processing logs
        questions: Dictionary of questions
        value: Value to assign to the field
    """
    if field_type == WritingQuestionType.MIRROR:
        _get_mirror_instance(ctx, element, value, logs)
    elif field_type == WritingQuestionType.HIDE:
        element.hide = value.lower() == "true"
    elif field_type == WritingQuestionType.FACTIONS:
        _assign_faction(ctx, element, value, logs)
    elif field_type == WritingQuestionType.TEASER:
        element.teaser = value
    elif field_type == WritingQuestionType.SHEET:
        element.text = value
    elif field_type == WritingQuestionType.TITLE:
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
    """Load form questions and options from uploaded files.

    Args:
        request: HTTP request object
        ctx: Context dictionary with event data
        form: Upload form with file data
        is_registration: Whether loading registration or writing questions

    Returns:
        list: Log messages from the upload processing operations
    """
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
    return {v.lower().strip(): k for k, v in d.items()}


def _questions_load(ctx, row, is_registration):
    """Load and validate question data from upload files.

    Processes question configurations for registration or character forms,
    creating or updating RegistrationQuestion or WritingQuestion instances
    based on the row data and validation mappings.

    Args:
        ctx (dict): Context dictionary containing event and processing information
        row (dict): Data row from upload file containing question configuration
        is_registration (bool): True for registration questions, False for writing questions

    Returns:
        str: Status message indicating success or error details
    """
    name = row.get("name")
    if not name:
        return "ERR - name not found"

    mappings = _get_mappings(is_registration)

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


def _get_mappings(is_registration):
    mappings = {
        "typ": invert_dict(BaseQuestionType.get_mapping()),
        "status": invert_dict(QuestionStatus.get_mapping()),
        "applicable": invert_dict(QuestionApplicable.get_mapping()),
        "visibility": invert_dict(QuestionVisibility.get_mapping()),
    }
    if is_registration:
        # update typ with new types
        typ_mapping = mappings["typ"]
        for key, _ in WritingQuestionType.choices:
            if key not in typ_mapping:
                typ_mapping[key] = key
    return mappings


def _options_load(ctx, row, questions, is_registration):
    """Load question options from CSV row for bulk import.

    Creates or updates question options with proper validation,
    ordering, and association with the correct question type.
    """
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

    created, instance = _get_option(ctx, is_registration, name, question_id)

    for field, value in row.items():
        if not value or pd.isna(value):
            continue
        new_value = value
        if field in ["question", "name"]:
            continue
        if field in ["max_available", "price"]:
            new_value = int(new_value)
        if field == "requirements":
            _assign_requirements(ctx, instance, [], value)
            continue
        setattr(instance, field, new_value)

    instance.save()

    if created:
        return f"OK - Created {name}"
    else:
        return f"OK - Updated {name}"


def _get_option(ctx, is_registration, name, question_id):
    """Get or create a question option for registration or writing forms.

    Args:
        ctx: Context dictionary containing event data
        is_registration: Boolean indicating if this is for registration (True) or writing (False)
        name: Name of the option
        question_id: ID of the parent question

    Returns:
        tuple: (created, instance) where created is bool and instance is the option object
    """
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
    return created, instance


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
    """Handle cover image upload and processing from ZIP archive.

    Args:
        ctx: Context dictionary containing run and event information
        z_obj: ZIP file object containing character cover images

    Side effects:
        Extracts ZIP contents, processes images, updates character cover fields,
        and moves files to proper media directory structure
    """
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


def tickets_load(request, ctx, form):
    (input_df, logs) = _get_file(ctx, form.cleaned_data["first"], 0)

    if input_df is not None:
        for row in input_df.to_dict(orient="records"):
            logs.append(_ticket_load(request, ctx, row))
    return logs


def _ticket_load(request, ctx, row):
    """Load ticket data from CSV row for bulk import.

    Creates or updates ticket objects with tier validation, price handling,
    and proper relationship setup for event registration.
    """
    if "name" not in row:
        return "ERR - There is no name column"

    (ticket, cr) = RegistrationTicket.objects.get_or_create(event=ctx["event"], name=row["name"])

    mappings = {
        "tier": invert_dict(TicketTier.get_mapping()),
    }

    for field, value in row.items():
        if not value or pd.isna(value) or field in ["name"]:
            continue
        new_value = value
        if field in mappings:
            new_value = new_value.lower().strip()
            if new_value not in mappings[field]:
                return f"ERR - unknow value {value} for field {field}"
            new_value = mappings[field][new_value]
        if field == "max_available":
            new_value = int(value)
        if field == "price":
            new_value = float(value)
        setattr(ticket, field, new_value)

    ticket.save()
    save_log(request.user.member, RegistrationTicket, ticket)

    if cr:
        msg = f"OK - Created {ticket}"
    else:
        msg = f"OK - Updated {ticket}"

    return msg


def abilities_load(request, ctx, form):
    (input_df, logs) = _get_file(ctx, form.cleaned_data["first"], 0)

    if input_df is not None:
        for row in input_df.to_dict(orient="records"):
            logs.append(_ability_load(request, ctx, row))
    return logs


def _ability_load(request, ctx, row):
    """Load ability data from CSV row for bulk import.

    Creates or updates ability objects with field validation, type assignment,
    prerequisite parsing, and requirement processing.
    """
    if "name" not in row:
        return "ERR - There is no name column"

    (element, cr) = AbilityPx.objects.get_or_create(event=ctx["event"].get_class_parent(AbilityPx), name=row["name"])

    logs = []

    for field, value in row.items():
        if not value or pd.isna(value) or field in ["name"]:
            continue
        new_value = value
        if field == "typ":
            _assign_type(ctx, element, logs, value)
            continue
        if field == "cost":
            new_value = int(value)
        if field == "prerequisites":
            _assign_prereq(ctx, element, logs, value)
            continue
        if field == "requirements":
            _assign_requirements(ctx, element, logs, value)
            continue
        if field == "visible":
            new_value = value.lower().strip() == "true"
        setattr(element, field, new_value)

    element.save()

    save_log(request.user.member, AbilityPx, element)

    if cr:
        msg = f"OK - Created {element}"
    else:
        msg = f"OK - Updated {element}"

    return msg


def _assign_type(ctx, element, logs, value):
    try:
        element.typ = ctx["event"].get_elements(AbilityTypePx).get(name__iexact=value)
    except ObjectDoesNotExist:
        logs.append(f"ERR - quest type not found: {value}")


def _assign_prereq(ctx, element, logs, value):
    for name in value.split(","):
        try:
            prereq = ctx["event"].get_elements(AbilityPx).get(name__iexact=name.strip())
            element.save()  # to be sure
            element.prerequisites.add(prereq)
        except ObjectDoesNotExist:
            logs.append(f"Prerequisite not found: {name}")


def _assign_requirements(ctx, element, logs, value):
    for name in value.split(","):
        try:
            option = ctx["event"].get_elements(WritingOption).get(name__iexact=name.strip())
            element.save()  # to be sure
            element.requirements.add(option)
        except ObjectDoesNotExist:
            logs.append(f"requirements not found: {name}")
