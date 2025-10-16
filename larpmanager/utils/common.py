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
import logging
import random
import re
import string
import unicodedata
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

import pytz
from background_task.models import Task
from diff_match_patch import diff_match_patch
from django.conf import settings as conf_settings
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max, Subquery
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_event_features
from larpmanager.models.accounting import Collection, Discount
from larpmanager.models.association import Association
from larpmanager.models.base import Feature, FeatureModule
from larpmanager.models.casting import Quest, QuestType, Trait
from larpmanager.models.event import Event
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
from larpmanager.models.registration import Registration
from larpmanager.models.utils import my_uuid_short, strip_tags
from larpmanager.models.writing import (
    Character,
    Handout,
    HandoutTemplate,
    Plot,
    Prologue,
    PrologueType,
    Relationship,
    SpeedLarp,
)
from larpmanager.utils.exceptions import NotFoundError

logger = logging.getLogger(__name__)

format_date = "%d/%m/%y"

format_datetime = "%d/%m/%y %H:%M"

utc = pytz.UTC


# ## PROFILING CHECK
def check_already(nm, params):
    """Check if a background task is already queued.

    Args:
        nm (str): Task name
        params: Task parameters

    Returns:
        bool: True if task already exists in queue
    """
    q = Task.objects.filter(task_name=nm, task_params=params)
    return q.exists()


def get_channel(a, b):
    """Generate unique channel ID for two entities.

    Args:
        a (int): First entity ID
        b (int): Second entity ID

    Returns:
        int: Unique channel ID using Cantor pairing
    """
    a = int(a)
    b = int(b)
    if a > b:
        return int(cantor(a, b))
    else:
        return int(cantor(b, a))


def cantor(k1, k2):
    """Cantor pairing function to map two integers to a unique integer.

    Args:
        k1 (int): First integer
        k2 (int): Second integer

    Returns:
        float: Unique pairing result
    """
    return ((k1 + k2) * (k1 + k2 + 1) / 2) + k2


def compute_diff(self, other):
    """Compute differences between this instance and another.

    Args:
        self: Current instance
        other: Other instance to compare against
    """
    check_diff(self, other.text, self.text)


def check_diff(self, tx1, tx2):
    """Generate HTML diff between two text strings.

    Args:
        self: Instance to store diff result
        tx1: First text string
        tx2: Second text string
    """
    if tx1 == tx2:
        self.diff = None
        return
    dmp = diff_match_patch()
    self.diff = dmp.diff_main(tx1, tx2)
    dmp.diff_cleanupEfficiency(self.diff)
    self.diff = dmp.diff_prettyHtml(self.diff)


def get_assoc(request):
    """Get association from request context.

    Args:
        request: Django HTTP request object

    Returns:
        Association: Association instance from request context
    """
    return get_object_or_404(Association, pk=request.assoc["id"])


def get_member(n):
    """Get member by ID with proper error handling.

    Args:
        n: Member ID

    Returns:
        dict: Dictionary containing member instance

    Raises:
        Http404: If member does not exist
    """
    try:
        return {"member": Member.objects.get(pk=n)}
    except ObjectDoesNotExist as err:
        raise Http404("Member does not exist") from err


def get_contact(mid, yid):
    """Get contact relationship between two members.

    Args:
        mid: ID of first member
        yid: ID of second member

    Returns:
        Contact: Contact instance or None if not found
    """
    try:
        return Contact.objects.get(me_id=mid, you_id=yid)
    except ObjectDoesNotExist:
        return None


def get_event_template(ctx, n):
    """Get event template by ID and add to context.

    Args:
        ctx: Template context dictionary
        n: Event template ID
    """
    try:
        ctx["event"] = Event.objects.get(pk=n, template=True, assoc_id=ctx["a_id"])
    except ObjectDoesNotExist as err:
        raise NotFoundError() from err


def get_char(ctx, n, by_number=False):
    """Get character by ID or number and add to context.

    Args:
        ctx: Template context dictionary
        n: Character ID or number
        by_number: Whether to search by number instead of ID
    """
    get_element(ctx, n, "character", Character, by_number)


def get_registration(ctx, n):
    """Get registration by ID and add to context.

    Args:
        ctx: Template context dictionary
        n: Registration ID

    Raises:
        Http404: If registration does not exist
    """
    try:
        ctx["registration"] = Registration.objects.get(run=ctx["run"], pk=n)
        ctx["name"] = str(ctx["registration"])
    except ObjectDoesNotExist as err:
        raise Http404("Registration does not exist") from err


def get_discount(ctx, n):
    """Get discount by ID and add to context.

    Args:
        ctx: Template context dictionary
        n: Discount ID

    Raises:
        Http404: If discount does not exist
    """
    try:
        ctx["discount"] = Discount.objects.get(pk=n)
        ctx["name"] = str(ctx["discount"])
    except ObjectDoesNotExist as err:
        raise Http404("Discount does not exist") from err


def get_album(ctx, n):
    """Get album by ID and add to context.

    Args:
        ctx: Template context dictionary
        n: Album ID

    Raises:
        Http404: If album does not exist
    """
    try:
        ctx["album"] = Album.objects.get(pk=n)
    except ObjectDoesNotExist as err:
        raise Http404("Album does not exist") from err


def get_album_cod(ctx, s):
    try:
        ctx["album"] = Album.objects.get(cod=s)
    except ObjectDoesNotExist as err:
        raise Http404("Album does not exist") from err


def get_feature(ctx, slug):
    try:
        ctx["feature"] = Feature.objects.get(slug=slug)
    except ObjectDoesNotExist as err:
        raise Http404("Feature does not exist") from err


def get_feature_module(ctx, num):
    try:
        ctx["feature_module"] = FeatureModule.objects.get(pk=num)
    except ObjectDoesNotExist as err:
        raise Http404("FeatureModule does not exist") from err


def get_plot(ctx, n):
    try:
        ctx["plot"] = (
            Plot.objects.select_related("event", "progress", "assigned")
            .prefetch_related("characters", "plotcharacterrel_set__character")
            .get(event=ctx["event"], pk=n)
        )
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
    threshold = 1000
    # round by 10
    if abs(number) < threshold:
        rounded = d.quantize(Decimal("1E1"), rounding=ROUND_DOWN)
    # round by 100
    else:
        rounded = d.quantize(Decimal("1E2"), rounding=ROUND_DOWN)
    return int(rounded)


def exchange_order(ctx: dict, cls: type, num: int, order: bool, elements=None) -> None:
    """
    Exchange ordering positions between two elements in a sequence.

    This function moves an element up or down in the ordering sequence by swapping
    its order value with an adjacent element. If no adjacent element exists,
    it simply increments or decrements the order value.

    Args:
        ctx: Context dictionary to store the current element after operation.
        cls: Model class of elements to reorder.
        num: Primary key of the element to move.
        order: Direction to move - True for up (increase order), False for down (decrease order).
        elements: Optional queryset of elements. Defaults to event elements if None.

    Returns:
        None: Function modifies elements in-place and updates ctx['current'].

    Note:
        The function handles edge cases where elements have the same order value
        by adjusting one of them to maintain proper ordering.
    """
    # Get elements queryset, defaulting to event elements if not provided
    elements = elements or ctx["event"].get_elements(cls)
    current = elements.get(pk=num)

    # Determine direction: order=True means move up (increase order), False means down
    qs = elements.filter(order__gt=current.order) if order else elements.filter(order__lt=current.order)
    qs = qs.order_by("order" if order else "-order")

    # Apply additional filters based on current element's attributes
    # This ensures we only swap within the same logical group
    for attr in ("question", "section", "applicable"):
        if hasattr(current, attr):
            qs = qs.filter(**{attr: getattr(current, attr)})

    # Get the next element in the desired direction
    other = qs.first()

    # If no adjacent element found, just increment/decrement order
    if not other:
        current.order += 1 if order else -1
        current.save()
        ctx["current"] = current
        return

    # Exchange ordering values between current and adjacent element
    current.order, other.order = other.order, current.order

    # Handle edge case where both elements have same order (data inconsistency)
    if current.order == other.order:
        other.order += -1 if order else 1

    # Save both elements and update context
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
    """
    Copy all objects of a given class from source event to target event.

    Args:
        target_id: Target event ID to copy objects to
        source_id: Source event ID to copy objects from
        cls: Django model class to copy instances of
    """
    cls.objects.filter(event_id=target_id).delete()

    for obj in cls.objects.filter(event_id=source_id):
        try:
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
        except Exception as err:
            logging.warning(f"found exp: {err}")


def get_payment_methods_ids(ctx):
    """
    Get set of payment method IDs for an association.

    Args:
        ctx: Context dictionary containing association ID

    Returns:
        set: Set of payment method primary keys
    """
    return set(Association.objects.get(pk=ctx["a_id"]).payment_methods.values_list("pk", flat=True))


def detect_delimiter(content):
    """
    Detect CSV delimiter from content header line.

    Args:
        content: CSV content string

    Returns:
        str: Detected delimiter character

    Raises:
        Exception: If no delimiter is found
    """
    header = content.split("\n")[0]
    for d in ["\t", ";", ","]:
        if d in header:
            return d
    raise Exception("no delimiter")


def clean(s):
    """
    Clean and normalize string by removing symbols, spaces, and accents.

    Args:
        s: String to clean

    Returns:
        str: Cleaned string with normalized characters
    """
    s = s.lower()
    s = re.sub(r"[^\w]", " ", s)  # remove symbols
    s = re.sub(r"\s", " ", s)  # replace whitespaces with spaces
    s = re.sub(r" +", "", s)  # remove spaces
    s = s.replace("ò", "o").replace("ù", "u").replace("à", "a").replace("è", "e").replace("é", "e").replace("ì", "i")
    return s


def _search_char_reg(ctx, char, js):
    """
    Populate character search result with registration and player data.

    Args:
        ctx: Context dictionary with run information
        char: Character instance with registration data
        js: JSON object to populate with search results
    """
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
    """Retrieve and categorize help questions for the current association/run.

    Args:
        ctx: Context dictionary containing association/run information
        request: HTTP request object

    Returns:
        tuple: (closed_questions, open_questions) lists
    """
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


def format_email_body(email):
    body_with_spaces = email.body.replace("<br />", " ").replace("<br>", " ")
    stripped = strip_tags(body_with_spaces)
    cleaned = stripped.split("============")[0]
    cutoff = 200
    return cleaned[:cutoff] + "..." if len(cleaned) > cutoff else cleaned
