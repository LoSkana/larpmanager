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
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Union

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
from larpmanager.models.base import BaseModel, Feature, FeatureModule
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


def get_workshop_option(ctx: dict, m: int) -> None:
    """Get workshop option by ID and validate it belongs to the current event.

    Args:
        ctx: Context dictionary to store the workshop option
        m: Workshop option primary key

    Raises:
        Http404: If workshop option doesn't exist or belongs to wrong event
    """
    try:
        # Retrieve workshop option by primary key
        ctx["workshop_option"] = WorkshopOption.objects.get(pk=m)
    except ObjectDoesNotExist as err:
        raise Http404("WorkshopOption does not exist") from err

    # Validate workshop option belongs to current event
    if ctx["workshop_option"].question.module.event != ctx["event"]:
        raise Http404("wrong event")


def get_element(
    ctx: dict[str, Any],
    primary_key: Union[int, str],
    context_key_name: str,
    model_class: type[BaseModel],
    by_number: bool = False,
) -> None:
    """
    Retrieve a model instance and add it to the context dictionary.

    This function fetches a model instance related to a parent event and stores it
    in the provided context dictionary. The lookup can be performed either by the
    model's primary key or by a 'number' field.

    Args:
        ctx: Context dictionary that must contain an 'event' key with a model instance
            that has a `get_class_parent()` method. The retrieved object will be added
            to this dictionary under the key specified by `context_key_name`.
        primary_key: The identifier used to look up the model instance. Either a primary
            key (int/str) or a number field value depending on `by_number` parameter.
        context_key_name: The key name under which the retrieved object will be stored
            in the context dictionary. Also used in error messages.
        model_class: The Django model class to query. Must have a foreign key relationship
            to an 'event' and optionally a 'number' field if `by_number=True`.
        by_number: If True, lookup by 'number' field instead of primary key. Defaults to False.

    Returns:
        None. Modifies the `ctx` dictionary in place by adding:
            - ctx[context_key_name]: The retrieved model instance
            - ctx["class_name"]: Set to the value of `context_key_name`

    Raises:
        Http404: If the requested object does not exist in the database.

    Example:
        >>> ctx = {"event": some_event_instance}
        >>> get_element(ctx, 42, "ticket", Ticket, by_number=True)
        >>> # ctx now contains: {"event": ..., "ticket": <Ticket>, "class_name": "ticket"}
    """
    try:
        # Get the parent event associated with the current event in context
        parent_event = ctx["event"].get_class_parent(model_class)

        if by_number:
            # Lookup by 'number' field (e.g., ticket number, order number)
            ctx[context_key_name] = model_class.objects.get(event=parent_event, number=primary_key)
        else:
            # Lookup by primary key (default behavior)
            ctx[context_key_name] = model_class.objects.get(event=parent_event, pk=primary_key)

        # Store the context key name for potential later reference
        ctx["class_name"] = context_key_name

    except ObjectDoesNotExist as err:
        # Raise a user-friendly 404 error if the object doesn't exist
        raise Http404(f"{context_key_name} does not exist") from err


def get_relationship(ctx: dict, num: int) -> None:
    """Retrieves a relationship by ID and validates it belongs to the event."""
    try:
        ctx["relationship"] = Relationship.objects.get(pk=num)
    except ObjectDoesNotExist as err:
        raise Http404("relationship does not exist") from err

    # Validate relationship belongs to the current event
    if ctx["relationship"].source.event_id != ctx["event"].id:
        raise Http404("wrong event")


def get_player_relationship(ctx, oth):
    try:
        ctx["relationship"] = PlayerRelationship.objects.get(reg=ctx["run"].reg, target__number=oth)
    except ObjectDoesNotExist as err:
        raise Http404("relationship does not exist") from err


def get_time_diff(dt1, dt2):
    return (dt1 - dt2).days


def get_time_diff_today(target_date: datetime | date | None) -> int:
    """Calculate time difference between given date and today.

    Args:
        target_date: Date to compare with today

    Returns:
        Time difference in days, or -1 if target_date is None
    """
    if not target_date:
        return -1

    # Convert datetime to date if necessary
    if isinstance(target_date, datetime):
        target_date = target_date.date()

    return get_time_diff(target_date, datetime.today().date())


def generate_number(length):
    return "".join(random.choice(string.digits) for idx in range(length))


def html_clean(tx: str | None) -> str:
    """Clean HTML tags and unescape HTML entities from text.

    Args:
        tx: Input text that may contain HTML tags and entities.

    Returns:
        Cleaned text with HTML tags removed and entities unescaped.
    """
    if not tx:
        return ""
    # Remove all HTML tags from the text
    tx = strip_tags(tx)
    # Unescape HTML entities (e.g., &amp; -> &, &lt; -> <)
    tx = html.unescape(tx)
    return tx


def dump(obj: object) -> str:
    """Return a string representation of all object attributes and their values."""
    s = ""
    for attr in dir(obj):
        s += f"obj.{attr} = {repr(getattr(obj, attr))}\n"
    return s


def rmdir(directory: Path) -> None:
    """Recursively remove a directory and all its contents."""
    directory = Path(directory)

    # Iterate through all items in the directory
    for item in directory.iterdir():
        if item.is_dir():
            # Recursively remove subdirectories
            rmdir(item)
        else:
            # Remove files
            item.unlink()

    # Remove the empty directory
    directory.rmdir()


def average(lst):
    return sum(lst) / len(lst)


def pretty_request(request) -> str:
    """Format HTTP request details into a readable string representation.

    Args:
        request: Django HttpRequest object to format

    Returns:
        Formatted string containing request method, headers, and body
    """
    headers = ""

    # Extract and format HTTP headers from request META
    for header, value in request.META.items():
        if not header.startswith("HTTP"):
            continue
        # Convert HTTP_HEADER_NAME to Header-Name format
        header_value = "-".join([h.capitalize() for h in header[5:].lower().split("_")])
        headers += f"{header_value}: {value}\n"

    # Combine method, meta info, headers and body into formatted output
    return f"{request.method} HTTP/1.1\nMeta: {request.META}\n{headers}\n\n{request.body}"


def remove_choice(lst: list[tuple], trm: str) -> list[tuple]:
    """Remove choice from list where first element matches term."""
    new = []
    # Iterate through each element in the list
    for el in lst:
        if el[0] == trm:
            continue
        new.append(el)
    return new


def check_field(cls: type, check: str) -> bool:
    """Check if a field exists in the Django model class.

    Args:
        cls: The Django model class to check
        check: The name of the field to look for

    Returns:
        True if field exists, False otherwise
    """
    # Iterate through all fields including hidden ones
    for field in cls._meta.get_fields(include_hidden=True):
        if field.name == check:
            return True
    return False


def round_to_two_significant_digits(number: float | int) -> int:
    """Round a number to two significant digits using specific thresholds.

    Args:
        number: The number to round. Can be float or int.

    Returns:
        The rounded number as an integer.

    Notes:
        - Numbers with absolute value < 1000 are rounded to nearest 10 (down)
        - Numbers with absolute value >= 1000 are rounded to nearest 100 (down)
    """
    # Convert input to Decimal for precise arithmetic
    d = Decimal(number)
    threshold = 1000

    # Round by 10 for smaller numbers
    if abs(number) < threshold:
        rounded = d.quantize(Decimal("1E1"), rounding=ROUND_DOWN)
    # Round by 100 for larger numbers
    else:
        rounded = d.quantize(Decimal("1E2"), rounding=ROUND_DOWN)

    # Convert back to integer and return
    return int(rounded)


def exchange_order(ctx: dict, model_class: type, element_id: int, move_up: bool, elements=None) -> None:
    """
    Exchange ordering positions between two elements in a sequence.

    This function moves an element up or down in the ordering sequence by swapping
    its order value with an adjacent element. If no adjacent element exists,
    it simply increments or decrements the order value.

    Args:
        ctx: Context dictionary to store the current element after operation.
        model_class: Model class of elements to reorder.
        element_id: Primary key of the element to move.
        move_up: Direction to move - True for up (increase order), False for down (decrease order).
        elements: Optional queryset of elements. Defaults to event elements if None.

    Returns:
        None: Function modifies elements in-place and updates ctx['current'].

    Note:
        The function handles edge cases where elements have the same order value
        by adjusting one of them to maintain proper ordering.
    """
    # Get elements queryset, defaulting to event elements if not provided
    elements = elements or ctx["event"].get_elements(model_class)
    current_element = elements.get(pk=element_id)

    # Determine direction: move_up=True means move up (increase order), False means down
    queryset = (
        elements.filter(order__gt=current_element.order)
        if move_up
        else elements.filter(order__lt=current_element.order)
    )
    queryset = queryset.order_by("order" if move_up else "-order")

    # Apply additional filters based on current element's attributes
    # This ensures we only swap within the same logical group
    for attribute_name in ("question", "section", "applicable"):
        if hasattr(current_element, attribute_name):
            queryset = queryset.filter(**{attribute_name: getattr(current_element, attribute_name)})

    # Get the next element in the desired direction
    adjacent_element = queryset.first()

    # If no adjacent element found, just increment/decrement order
    if not adjacent_element:
        current_element.order += 1 if move_up else -1
        current_element.save()
        ctx["current"] = current_element
        return

    # Exchange ordering values between current and adjacent element
    current_element.order, adjacent_element.order = adjacent_element.order, current_element.order

    # Handle edge case where both elements have same order (data inconsistency)
    if current_element.order == adjacent_element.order:
        adjacent_element.order += -1 if move_up else 1

    # Save both elements and update context
    current_element.save()
    adjacent_element.save()
    ctx["current"] = current_element


def normalize_string(value: str) -> str:
    """Normalize a string by converting to lowercase, removing spaces and accents.

    Args:
        value: Input string to normalize.

    Returns:
        Normalized string with lowercase, no spaces, and no accented characters.
    """
    # Convert to lowercase
    value = value.lower()

    # Remove spaces
    value = value.replace(" ", "")

    # Remove accented characters using Unicode normalization
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")

    return value


def copy_class(target_event_id, source_event_id, model_class):
    """
    Copy all objects of a given class from source event to target event.

    Args:
        target_event_id: Target event ID to copy objects to
        source_event_id: Source event ID to copy objects from
        model_class: Django model class to copy instances of
    """
    model_class.objects.filter(event_id=target_event_id).delete()

    for source_object in model_class.objects.filter(event_id=source_event_id):
        try:
            # save a copy of m2m relations
            many_to_many_data = {}

            # noinspection PyProtectedMember
            for field in source_object._meta.many_to_many:
                many_to_many_data[field.name] = list(getattr(source_object, field.name).all())

            source_object.pk = None
            source_object.event_id = target_event_id
            # noinspection PyProtectedMember
            source_object._state.adding = True
            for field_name, generation_function in {"access_token": my_uuid_short}.items():
                if not hasattr(source_object, field_name):
                    continue
                setattr(source_object, field_name, generation_function())
            source_object.save()

            # copy m2m relations
            for field_name, related_values in many_to_many_data.items():
                getattr(source_object, field_name).set(related_values)
        except Exception as error:
            logging.warning(f"found exp: {error}")


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


def _search_char_reg(ctx: dict, char, js: dict) -> None:
    """
    Populate character search result with registration and player data.

    This function extracts character and player information from registration data
    and populates a JSON object for search results display.

    Args:
        ctx : dict
            Context dictionary containing run information and event data
        char : Character
            Character instance with associated registration data
        js : dict
            JSON object to populate with search results data

    Returns: None -Modifies the js dictionary in place
    """
    # Set character name, prioritizing custom name if available
    js["name"] = char.name
    if char.rcr and char.rcr.custom_name:
        js["name"] = char.rcr.custom_name

    # Extract player information from registration
    js["player"] = char.reg.display_member()
    js["player_full"] = str(char.reg.member)
    js["player_id"] = char.reg.member_id
    js["first_aid"] = char.reg.member.first_aid

    # Set profile image with fallback hierarchy: character custom -> member -> None
    if char.rcr.profile_thumb:
        js["player_prof"] = char.rcr.profile_thumb.url
        js["profile"] = char.rcr.profile_thumb.url
    elif char.reg.member.profile_thumb:
        js["player_prof"] = char.reg.member.profile_thumb.url
    else:
        js["player_prof"] = None

    # Extract custom character attributes (pronoun, song, public, private notes)
    for s in ["pronoun", "song", "public", "private"]:
        if hasattr(char.rcr, "custom_" + s):
            js[s] = getattr(char.rcr, "custom_" + s)

    # Override profile with character cover if event supports both cover and user characters
    if {"cover", "user_character"}.issubset(get_event_features(ctx["run"].event_id)):
        if char.cover:
            js["player_prof"] = char.thumb.url


def clear_messages(request):
    if hasattr(request, "_messages"):
        request._messages._queued_messages.clear()


def _get_help_questions(ctx: dict, request) -> tuple[list, list]:
    """Retrieve and categorize help questions for the current association/run.

    Fetches help questions filtered by association and optionally by run, then
    categorizes them into open and closed questions based on their status and origin.

    Args:
        ctx: Context dictionary containing association/run information.
             Must include 'a_id' key, optionally includes 'run' key.
        request: HTTP request object used to determine filtering behavior.

    Returns:
        A tuple containing two lists:
        - closed_questions: List of closed or staff-originated questions
        - open_questions: List of open user-originated questions
    """
    # Filter questions by association ID
    base_qs = HelpQuestion.objects.filter(assoc_id=ctx["a_id"])

    # Add run filter if run context exists
    if "run" in ctx:
        base_qs = base_qs.filter(run=ctx["run"])

    # For non-POST requests, limit to questions from last 90 days
    if request.method != "POST":
        base_qs = base_qs.filter(created__gte=datetime.now() - timedelta(days=90))

    # Find the latest creation timestamp for each member
    latest = base_qs.values("member_id").annotate(latest_created=Max("created")).values("latest_created")

    # Get the most recent question for each member with related data
    que = base_qs.filter(created__in=Subquery(latest)).select_related("member", "run", "run__event")

    # Categorize questions into open and closed lists
    open_q = []
    closed_q = []
    for cq in que:
        # Open questions are user-originated and not closed
        if cq.is_user and not cq.closed:
            open_q.append(cq)
        else:
            closed_q.append(cq)

    return closed_q, open_q


def get_recaptcha_secrets(request) -> tuple[str | None, str | None]:
    """Get reCAPTCHA public and private keys for the current request.

    Handles both single-site and multi-site configurations. In multi-site mode,
    keys are stored as comma-separated pairs in format "skin_id:key".

    Args:
        request: Django request object with assoc data containing skin_id

    Returns:
        Tuple of (public_key, private_key) or (None, None) if not found
    """
    # Get base configuration values
    public = conf_settings.RECAPTCHA_PUBLIC_KEY
    private = conf_settings.RECAPTCHA_PRIVATE_KEY

    # Handle multi-site configuration with comma-separated values
    if "," in public:
        # Extract skin_id from request association data
        skin_id = request.assoc["skin_id"]

        # Parse public key pairs and find matching skin_id
        pairs = dict(item.split(":") for item in public.split(",") if ":" in item)
        public = pairs.get(str(skin_id))

        # Parse private key pairs and find matching skin_id
        pairs = dict(item.split(":") for item in private.split(",") if ":" in item)
        private = pairs.get(str(skin_id))

    return public, private


def welcome_user(request, user):
    messages.success(request, _("Welcome") + ", " + user.get_username() + "!")


def format_email_body(email) -> str:
    """Format email body for display by cleaning HTML and truncating text.

    Args:
        email: Email object with body attribute containing HTML content.

    Returns:
        Cleaned and truncated email body text.
    """
    # Replace HTML line breaks with spaces
    body_with_spaces = email.body.replace("<br />", " ").replace("<br>", " ")

    # Strip all HTML tags
    stripped = strip_tags(body_with_spaces)

    # Remove content after separator line
    cleaned = stripped.split("============")[0]

    # Truncate text if longer than cutoff
    cutoff = 200
    return cleaned[:cutoff] + "..." if len(cleaned) > cutoff else cleaned
