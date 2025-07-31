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

import html
import os
import random
import re
import string
import unicodedata
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

import magic
import pytz
from background_task.models import Task
from diff_match_patch import diff_match_patch
from django.conf import settings as conf_settings
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Max, Subquery
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_event_features
from larpmanager.models.accounting import Collection, Discount
from larpmanager.models.association import Association
from larpmanager.models.base import Feature, FeatureModule
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event
from larpmanager.models.experience import update_px
from larpmanager.models.member import Badge, Member
from larpmanager.models.miscellanea import (
    Album,
    Contact,
    HelpQuestion,
    PlayerRelationship,
    WorkshopModule,
    WorkshopOption,
    WorkshopQuestion,
)
from larpmanager.models.registration import (
    Registration,
)
from larpmanager.models.utils import my_uuid_short, strip_tags
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    Handout,
    HandoutTemplate,
    Plot,
    Prologue,
    PrologueType,
    Relationship,
    SpeedLarp,
)
from larpmanager.utils.exceptions import (
    NotFoundError,
)

format_date = "%d/%m/%y"

format_datetime = "%d/%m/%y %H:%M"

utc = pytz.UTC


# ## PROFILING CHECK
def check_already(nm, params):
    q = Task.objects.filter(task_name=nm, task_params=params)
    return q.count() > 0


def get_channel(a, b):
    a = int(a)
    b = int(b)
    if a > b:
        return int(cantor(a, b))
    else:
        return int(cantor(b, a))


def cantor(k1, k2):
    return ((k1 + k2) * (k1 + k2 + 1) / 2) + k2


def compute_diff(self, other):
    check_diff(self, other.text, self.text)


def check_diff(self, tx1, tx2):
    if tx1 == tx2:
        self.diff = None
        return
    dmp = diff_match_patch()
    self.diff = dmp.diff_main(tx1, tx2)
    dmp.diff_cleanupEfficiency(self.diff)
    self.diff = dmp.diff_prettyHtml(self.diff)


def get_assoc(request):
    return get_object_or_404(Association, pk=request.assoc["id"])


def get_member(n):
    try:
        return {"member": Member.objects.get(pk=n)}
    except ObjectDoesNotExist as err:
        raise Http404("Member does not exist") from err


def get_contact(mid, yid):
    try:
        return Contact.objects.get(me_id=mid, you_id=yid)
    except ObjectDoesNotExist:
        return None


def get_event_template(ctx, n):
    try:
        ctx["event"] = Event.objects.get(pk=n, template=True, assoc_id=ctx["a_id"])
    except ObjectDoesNotExist as err:
        raise NotFoundError() from err


def get_char(ctx, n, by_number=False):
    get_element(ctx, n, "character", Character, by_number)


def get_registration(ctx, n):
    try:
        ctx["registration"] = Registration.objects.get(run=ctx["run"], pk=n)
        ctx["name"] = str(ctx["registration"])
    except ObjectDoesNotExist as err:
        raise Http404("Registration does not exist") from err


def get_discount(ctx, n):
    try:
        ctx["discount"] = Discount.objects.get(pk=n)
        ctx["name"] = str(ctx["discount"])
    except ObjectDoesNotExist as err:
        raise Http404("Discount does not exist") from err


def get_album(ctx, n):
    try:
        ctx["album"] = Album.objects.get(pk=n)
    except ObjectDoesNotExist as err:
        raise Http404("Album does not exist") from err


def get_album_cod(ctx, s):
    try:
        ctx["album"] = Album.objects.get(cod=s)
    except ObjectDoesNotExist as err:
        raise Http404("Album does not exist") from err


def get_feature(ctx, num):
    try:
        ctx["feature"] = Feature.objects.get(pk=num)
    except ObjectDoesNotExist as err:
        raise Http404("Feature does not exist") from err


def get_feature_module(ctx, num):
    try:
        ctx["feature_module"] = FeatureModule.objects.get(pk=num)
    except ObjectDoesNotExist as err:
        raise Http404("FeatureModule does not exist") from err


def get_plot(ctx, n):
    try:
        ctx["plot"] = Plot.objects.get(event=ctx["event"], pk=n)
        ctx["name"] = ctx["plot"].name
    except ObjectDoesNotExist as err:
        raise Http404("Plot does not exist") from err


def get_quest_type(ctx, n):
    get_element(ctx, n, "quest_type", QuestType)


def get_quest(ctx, n):
    get_element(ctx, n, "quest", Quest)


def get_trait(ctx, n):
    get_element(ctx, n, "trait", Trait)


def get_handout(ctx, n):
    try:
        ctx["handout"] = Handout.objects.get(event=ctx["event"], pk=n)
        ctx["name"] = ctx["handout"].name
        ctx["handout"].data = ctx["handout"].show()
    except ObjectDoesNotExist as err:
        raise Http404("handout does not exist") from err


def get_handout_template(ctx, n):
    try:
        ctx["handout_template"] = HandoutTemplate.objects.get(event=ctx["event"], pk=n)
        ctx["name"] = ctx["handout_template"].name
    except ObjectDoesNotExist as err:
        raise Http404("handout_template does not exist") from err


def get_prologue(ctx, n):
    get_element(ctx, n, "prologue", Prologue)


def get_prologue_type(ctx, n):
    try:
        ctx["prologue_type"] = PrologueType.objects.get(event=ctx["event"], pk=n)
        ctx["name"] = str(ctx["prologue_type"])
    except ObjectDoesNotExist as err:
        raise Http404("prologue_type does not exist") from err


def get_speedlarp(ctx, n):
    try:
        ctx["speedlarp"] = SpeedLarp.objects.get(event=ctx["event"], pk=n)
        ctx["name"] = str(ctx["speedlarp"])
    except ObjectDoesNotExist as err:
        raise Http404("speedlarp does not exist") from err

    # ~ def get_ord_faction(char):
    # ~ for g in char.factions_list.all():
    # ~ if g.typ == FactionType.PRIM:
    # ~ return (g.get_name(), g)
    # ~ return ("UNASSIGNED", None)


def get_badge(n, request):
    try:
        return Badge.objects.get(pk=n, assoc_id=request.assoc["id"])
    except ObjectDoesNotExist as err:
        raise Http404("Badge does not exist") from err


def get_collection_partecipate(request, cod):
    try:
        return Collection.objects.get(contribute_code=cod, assoc_id=request.assoc["id"])
    except ObjectDoesNotExist as err:
        raise Http404("Collection does not exist") from err


def get_collection_redeem(request, cod):
    try:
        return Collection.objects.get(redeem_code=cod, assoc_id=request.assoc["id"])
    except ObjectDoesNotExist as err:
        raise Http404("Collection does not exist") from err


def get_workshop(ctx, n):
    try:
        ctx["workshop"] = WorkshopModule.objects.get(event=ctx["event"], pk=n)
    except ObjectDoesNotExist as err:
        raise Http404("WorkshopModule does not exist") from err


def get_workshop_question(ctx, n, mod):
    try:
        ctx["workshop_question"] = WorkshopQuestion.objects.get(module__event=ctx["event"], pk=n, module__pk=mod)
    except ObjectDoesNotExist as err:
        raise Http404("WorkshopQuestion does not exist") from err


def get_workshop_option(ctx, m):
    try:
        ctx["workshop_option"] = WorkshopOption.objects.get(pk=m)
    except ObjectDoesNotExist as err:
        raise Http404("WorkshopOption does not exist") from err

    if ctx["workshop_option"].question.module.event != ctx["event"]:
        raise Http404("wrong event")


def get_element(ctx, n, name, typ, by_number=False):
    try:
        ev = ctx["event"].get_class_parent(typ)
        if by_number:
            ctx[name] = typ.objects.get(event=ev, number=n)
        else:
            ctx[name] = typ.objects.get(event=ev, pk=n)
        ctx["class_name"] = name
    except ObjectDoesNotExist as err:
        raise Http404(name + " does not exist") from err


def get_relationship(ctx, num):
    try:
        ctx["relationship"] = Relationship.objects.get(pk=num)
    except ObjectDoesNotExist as err:
        raise Http404("relationship does not exist") from err
    if ctx["relationship"].source.event_id != ctx["event"].id:
        raise Http404("wrong event")


def get_player_relationship(ctx, oth):
    try:
        ctx["relationship"] = PlayerRelationship.objects.get(reg=ctx["run"].reg, target__number=oth)
    except ObjectDoesNotExist as err:
        raise Http404("relationship does not exist") from err


def get_time_diff(dt1, dt2):
    return (dt1 - dt2).days


def get_time_diff_today(dt1):
    if not dt1:
        return -1
    if isinstance(dt1, datetime):
        dt1 = dt1.date()
    return get_time_diff(dt1, datetime.today().date())


def generate_number(length):
    return "".join(random.choice(string.digits) for idx in range(length))


def html_clean(tx):
    if not tx:
        return ""
    tx = strip_tags(tx)
    tx = html.unescape(tx)
    return tx


def dump(obj):
    s = ""
    for attr in dir(obj):
        s += f"obj.{attr} = {repr(getattr(obj, attr))}\n"


def rmdir(directory):
    directory = Path(directory)
    for item in directory.iterdir():
        if item.is_dir():
            rmdir(item)
        else:
            item.unlink()
    directory.rmdir()


# max bytes to read for file type detection
READ_SIZE = 5 * (1024 * 1024)  # 5MB


@deconstructible
class FileTypeValidator:
    """
    File type validator for validating mimetypes and extensions

    Args:
        allowed_types (list): list of acceptable mimetypes e.g; ['image/jpeg', 'application/pdf']
                    see https://www.iana.org/assignments/media-types/media-types.xhtml
        allowed_extensions (list, optional): list of allowed file extensions e.g; ['.jpeg', '.pdf', '.docx']
    """

    type_message = _("File type '%(detected_type)s' is not allowed.Allowed types are: '%(allowed_types)s'.")

    extension_message = _(
        "File extension '%(extension)s' is not allowed. Allowed extensions are: '%(allowed_extensions)s'."
    )

    invalid_message = _(
        "Allowed type '%(allowed_type)s' is not a valid type.See "
        "https://www.iana.org/assignments/media-types/media-types.xhtml"
    )

    def __init__(self, allowed_types, allowed_extensions=()):
        self.input_allowed_types = allowed_types
        self.allowed_mimes = self._normalize(allowed_types)
        self.allowed_exts = allowed_extensions

    def __call__(self, fileobj):
        detected_type = magic.from_buffer(fileobj.read(READ_SIZE), mime=True)
        root, extension = os.path.splitext(fileobj.name.lower())

        # seek back to start so a valid file could be read
        # later without resetting the position
        fileobj.seek(0)

        # some versions of libmagic do not report proper mimes for Office subtypes
        # use detection details to transform it to proper mime
        if detected_type in ("application/octet-stream", "application/vnd.ms-office"):
            detected_type = self._check_word_or_excel(fileobj, detected_type, extension)

        if detected_type not in self.allowed_mimes and detected_type.split("/")[0] not in self.allowed_mimes:
            raise ValidationError(
                message=self.type_message,
                params={
                    "detected_type": detected_type,
                    "allowed_types": ", ".join(self.input_allowed_types),
                },
                code="invalid_type",
            )

        if self.allowed_exts and (extension not in self.allowed_exts):
            raise ValidationError(
                message=self.extension_message,
                params={
                    "extension": extension,
                    "allowed_extensions": ", ".join(self.allowed_exts),
                },
                code="invalid_extension",
            )

    def _normalize(self, allowed_types):
        """
        Validate and transforms given allowed types
        e.g; wildcard character specification will be normalized as text/* -> text
        """
        allowed_mimes = []
        for allowed_type_orig in allowed_types:
            allowed_type = allowed_type_orig.decode() if type(allowed_type_orig) is bytes else allowed_type_orig
            parts = allowed_type.split("/")
            max_parts = 2
            if len(parts) == max_parts:
                if parts[1] == "*":
                    allowed_mimes.append(parts[0])
                else:
                    allowed_mimes.append(allowed_type)
            else:
                raise ValidationError(
                    message=self.invalid_message,
                    params={"allowed_type": allowed_type},
                    code="invalid_input",
                )

        return allowed_mimes

    @staticmethod
    def _check_word_or_excel(fileobj, detected_type, extension):
        """
        Returns proper mimetype in case of word or excel files
        """
        word_strings = [
            "Microsoft Word",
            "Microsoft Office Word",
            "Microsoft Macintosh Word",
        ]
        excel_strings = [
            "Microsoft Excel",
            "Microsoft Office Excel",
            "Microsoft Macintosh Excel",
        ]
        office_strings = ["Microsoft OOXML"]

        file_type_details = magic.from_buffer(fileobj.read(READ_SIZE))

        fileobj.seek(0)

        if any(string in file_type_details for string in word_strings):
            detected_type = "application/msword"
        elif any(string in file_type_details for string in excel_strings):
            detected_type = "application/vnd.ms-excel"
        elif any(string in file_type_details for string in office_strings) or (
            detected_type == "application/vnd.ms-office"
        ):
            if extension in (".doc", ".docx"):
                detected_type = "application/msword"
            if extension in (".xls", ".xlsx"):
                detected_type = "application/vnd.ms-excel"

        return detected_type


def average(lst):
    return sum(lst) / len(lst)


def pretty_request(request):
    headers = ""
    for header, value in request.META.items():
        if not header.startswith("HTTP"):
            continue
        header_value = "-".join([h.capitalize() for h in header[5:].lower().split("_")])
        headers += f"{header_value}: {value}\n"

    return f"{request.method} HTTP/1.1\nMeta: {request.META}\n{headers}\n\n{request.body}"


def add_char_addit(char):
    char.addit = {}
    configs = CharacterConfig.objects.filter(character__id=char.id)
    if not configs.count():
        update_px(char)
        configs = CharacterConfig.objects.filter(character__id=char.id)

    for config in configs:
        char.addit[config.name] = config.value


def remove_choice(lst, trm):
    new = []
    for el in lst:
        if el[0] == trm:
            continue
        new.append(el)
    return new


def check_field(cls, check):
    for field in cls._meta.get_fields(include_hidden=True):
        if field.name == check:
            return True
    return False


def round_to_two_significant_digits(number):
    d = Decimal(number)
    # Scales the number so that the first significant figure is in the unit
    shift = d.adjusted()
    rounded = d.scaleb(-shift).quantize(Decimal("1.0"), rounding=ROUND_DOWN)
    # Reply to the original position
    rounded = rounded.scaleb(shift)
    return float(rounded)


def exchange_order(ctx, cls, num, order):
    elements = ctx["event"].get_elements(cls)
    # get elements
    current = elements.get(pk=num)

    # order indicates if we have to increase, or reduce, the current_order
    if order:
        other = elements.filter(order__gt=current.order).order_by("order")
    else:
        other = elements.filter(order__lt=current.order).order_by("-order")

    if hasattr(current, "question"):
        other = other.filter(question=current.question)
    if hasattr(current, "section"):
        other = other.filter(section=current.section)
    if hasattr(current, "applicable"):
        other = other.filter(applicable=current.applicable)

    # if not element is found, simply increase / reduce the order
    if len(other) == 0:
        if order:
            current.order += 1
        else:
            current.order -= 1
        current.save()
    else:
        other = other.first()
        # exchange ordering
        current.order = other.order
        other.order = current.order
        if current.order == other.order:
            if order:
                other.order -= 1
            else:
                other.order += 1
        current.save()
        other.save()
    ctx["current"] = current


def normalize_string(value):
    # Convert to lowercase
    value = value.lower()
    # Remove spaces
    value = value.replace(" ", "")
    # Remove accented characters
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    return value


def copy_class(target_id, source_id, cls):
    cls.objects.filter(event_id=target_id).delete()

    for obj in cls.objects.filter(event_id=source_id):
        # save a copy of m2m relations
        m2m_data = {}

        # noinspection PyProtectedMember
        for field in obj._meta.many_to_many:
            m2m_data[field.name] = list(getattr(obj, field.name).all())

        obj.pk = None
        obj.event_id = target_id
        # noinspection PyProtectedMember
        obj._state.adding = True
        for field_name, func in {"access_token": my_uuid_short}.items():
            if not hasattr(obj, field_name):
                continue
            setattr(obj, field_name, func())
        obj.save()

        # copy m2m relations
        for field_name, values in m2m_data.items():
            getattr(obj, field_name).set(values)


def get_payment_methods_ids(ctx):
    return set(Association.objects.get(pk=ctx["a_id"]).payment_methods.values_list("pk", flat=True))


def detect_delimiter(content):
    header = content.split("\n")[0]
    for d in ["\t", ";", ","]:
        if d in header:
            return d
    raise Exception("no delimiter")


def clean(s):
    s = s.lower()
    s = re.sub(r"[^\w]", " ", s)  # remove symbols
    s = re.sub(r"\s", " ", s)  # replace whitespaces with spaces
    s = re.sub(r" +", "", s)  # remove spaces
    s = s.replace("ò", "o").replace("ù", "u").replace("à", "a").replace("è", "e").replace("é", "e").replace("ì", "i")
    return s


def _search_char_reg(ctx, char, js):
    js["name"] = char.name
    if char.rcr and char.rcr.custom_name:
        js["name"] = char.rcr.custom_name

    js["player"] = char.reg.display_member()
    js["player_full"] = str(char.reg.member)
    js["player_id"] = char.reg.member.id
    js["first_aid"] = char.reg.member.first_aid

    if char.rcr.profile_thumb:
        js["player_prof"] = char.rcr.profile_thumb.url
        js["profile"] = char.rcr.profile_thumb.url
    elif char.reg.member.profile_thumb:
        js["player_prof"] = char.reg.member.profile_thumb.url
    else:
        js["player_prof"] = None

    for s in ["pronoun", "song", "public", "private"]:
        if hasattr(char.rcr, "custom_" + s):
            js[s] = getattr(char.rcr, "custom_" + s)

    # if the event has both cover and character created by user, use that as player profile
    if {"cover", "user_character"}.issubset(get_event_features(ctx["run"].event_id)):
        if char.cover:
            js["player_prof"] = char.thumb.url


def clear_messages(request):
    if hasattr(request, "_messages"):
        request._messages._queued_messages.clear()


def _get_help_questions(ctx, request):
    base_qs = HelpQuestion.objects.filter(assoc_id=ctx["a_id"])
    if "run" in ctx:
        base_qs = base_qs.filter(run=ctx["run"])

    if request.method != "POST":
        base_qs = base_qs.filter(created__gte=datetime.now() - timedelta(days=90))

    # last created question for each member_id
    latest = base_qs.values("member_id").annotate(latest_created=Max("created")).values("latest_created")

    # last message for each member_id
    que = base_qs.filter(created__in=Subquery(latest)).select_related("member", "run", "run__event")

    open_q = []
    closed_q = []
    for cq in que:
        if cq.is_user and not cq.closed:
            open_q.append(cq)
        else:
            closed_q.append(cq)

    return closed_q, open_q


def get_recaptcha_secrets(request):
    public = conf_settings.RECAPTCHA_PUBLIC_KEY
    private = conf_settings.RECAPTCHA_PRIVATE_KEY

    # if multi-site settings
    if "," in public:
        skin_id = request.assoc["skin_id"]
        pairs = dict(item.split(":") for item in public.split(",") if ":" in item)
        public = pairs.get(str(skin_id))
        pairs = dict(item.split(":") for item in private.split(",") if ":" in item)
        private = pairs.get(str(skin_id))

    return public, private


def welcome_user(request, user):
    messages.success(request, _("Welcome") + ", " + user.get_username() + "!")
