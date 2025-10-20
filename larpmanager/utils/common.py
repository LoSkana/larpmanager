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
from django.http import Http404, HttpRequest
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
def check_already(nm: str, params: str) -> bool:
    """Check if a background task is already queued.

    This function queries the database to determine if a task with the given
    name and parameters is already present in the task queue, preventing
    duplicate task creation.

    Args:
        nm: The name of the task to check for in the queue.
        params: The serialized parameters of the task to match against.

    Returns:
        True if a task with matching name and parameters exists in the queue,
        False otherwise.

    Example:
        >>> check_already('send_email', '{"recipient": "user@example.com"}')
        True
    """
    # Query for existing tasks matching both name and parameters
    q = Task.objects.filter(task_name=nm, task_params=params)

    # Return whether any matching tasks exist
    return q.exists()


def get_channel(a: int, b: int) -> int:
    """Generate unique channel ID for two entities using Cantor pairing function.

    Creates a deterministic, unique channel identifier for any pair of entity IDs
    by applying the Cantor pairing function to the ordered pair (larger, smaller).
    This ensures that get_channel(a, b) == get_channel(b, a) for any valid inputs.

    Args:
        a: First entity ID (must be convertible to int)
        b: Second entity ID (must be convertible to int)

    Returns:
        Unique channel ID as integer using Cantor pairing

    Example:
        >>> get_channel(5, 3)
        64
        >>> get_channel(3, 5)  # Same result due to ordering
        64
    """
    # Convert inputs to integers to ensure type safety
    a = int(a)
    b = int(b)

    # Order parameters consistently to ensure symmetry: get_channel(a,b) == get_channel(b,a)
    if a > b:
        return int(cantor(a, b))
    else:
        return int(cantor(b, a))


def cantor(k1: int, k2: int) -> int:
    """Cantor pairing function to map two integers to a unique integer.

    The Cantor pairing function is a primitive recursive pairing function
    that encodes two natural numbers into a single natural number.

    Args:
        k1: First integer to be paired.
        k2: Second integer to be paired.

    Returns:
        Unique integer result of the Cantor pairing.

    Example:
        >>> cantor(3, 4)
        32
        >>> cantor(0, 0)
        0
    """
    # Calculate the sum of both integers
    sum_k = k1 + k2

    # Apply Cantor pairing formula: ((k1 + k2) * (k1 + k2 + 1) / 2) + k2
    return int((sum_k * (sum_k + 1) // 2) + k2)


def compute_diff(self, other):
    """Compute differences between this instance and another.

    Args:
        self: Current instance
        other: Other instance to compare against
    """
    check_diff(self, other.text, self.text)


def check_diff(self, tx1: str, tx2: str) -> None:
    """Generate HTML diff between two text strings.

    Args:
        tx1: First text string to compare
        tx2: Second text string to compare

    Returns:
        None: Sets self.diff attribute with HTML diff or None if strings are identical

    Note:
        Uses diff_match_patch library to generate semantic diffs with HTML formatting.
        The diff is cleaned up for efficiency before HTML conversion.
    """
    # Early return if strings are identical - no diff needed
    if tx1 == tx2:
        self.diff = None
        return

    # Initialize diff_match_patch instance for text comparison
    dmp = diff_match_patch()

    # Generate semantic diff between the two text strings
    self.diff = dmp.diff_main(tx1, tx2)

    # Clean up diff for better efficiency and readability
    dmp.diff_cleanupEfficiency(self.diff)

    # Convert diff to HTML format for display
    self.diff = dmp.diff_prettyHtml(self.diff)


def get_assoc(request: HttpRequest) -> Association:
    """Get association from request context.

    Retrieves the Association instance associated with the current request
    by looking up the association ID stored in the request context.

    Args:
        request (HttpRequest): Django HTTP request object containing
            association context data in request.assoc dictionary.

    Returns:
        Association: The Association instance matching the ID found in
            the request context.

    Raises:
        Http404: If no Association exists with the given ID.

    Example:
        >>> association = get_assoc(request)
        >>> print(association.name)
    """
    # Extract association ID from request context
    assoc_id = request.assoc["id"]

    # Retrieve and return the Association instance or raise 404
    return get_object_or_404(Association, pk=assoc_id)


def get_member(n: int) -> dict[str, Member]:
    """Get member by ID with proper error handling.

    Args:
        n: The primary key ID of the member to retrieve.

    Returns:
        A dictionary containing the member instance under the 'member' key.

    Raises:
        Http404: If the member with the specified ID does not exist.

    Example:
        >>> result = get_member(123)
        >>> member = result['member']
    """
    try:
        # Attempt to retrieve the member by primary key
        return {"member": Member.objects.get(pk=n)}
    except ObjectDoesNotExist as err:
        # Re-raise as Http404 with descriptive message for web context
        raise Http404("Member does not exist") from err


def get_contact(mid: int, yid: int) -> Contact | None:
    """Get contact relationship between two members.

    Retrieves the contact relationship record that exists between two members
    in the system, where one member (mid) has a contact relationship with
    another member (yid).

    Args:
        mid (int): ID of the first member (the "me" in the relationship)
        yid (int): ID of the second member (the "you" in the relationship)

    Returns:
        Contact | None: Contact instance if relationship exists, None if not found

    Example:
        >>> contact = get_contact(123, 456)
        >>> if contact:
        ...     print(f"Contact found: {contact}")
    """
    try:
        # Query the Contact model for the specific relationship
        return Contact.objects.get(me_id=mid, you_id=yid)
    except ObjectDoesNotExist:
        # Return None when no contact relationship exists
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


def get_registration(ctx: dict, n: int) -> None:
    """Get registration by ID and add to context.

    Retrieves a registration object by its primary key within the context of a specific run,
    then adds both the registration object and its string representation to the template context.

    Args:
        ctx: Template context dictionary that must contain a 'run' key
        n: Registration primary key identifier

    Raises:
        Http404: If registration does not exist for the given run and ID

    Note:
        This function modifies the ctx dictionary in-place by adding 'registration' and 'name' keys.
    """
    try:
        # Retrieve registration object filtered by run context and primary key
        ctx["registration"] = Registration.objects.get(run=ctx["run"], pk=n)

        # Add string representation of registration to context for display purposes
        ctx["name"] = str(ctx["registration"])
    except ObjectDoesNotExist as err:
        # Convert Django's ObjectDoesNotExist to HTTP 404 response
        raise Http404("Registration does not exist") from err


def get_discount(ctx: dict, n: int) -> None:
    """Get discount by ID and add to context.

    Retrieves a discount object from the database using the provided ID and adds it
    to the template context along with its string representation.

    Args:
        ctx: Template context dictionary to be updated with discount data
        n: Primary key of the discount to retrieve

    Raises:
        Http404: If discount with the specified ID does not exist

    Returns:
        None: Function modifies the context dictionary in-place
    """
    try:
        # Fetch discount object by primary key
        ctx["discount"] = Discount.objects.get(pk=n)

        # Add string representation of discount to context
        ctx["name"] = str(ctx["discount"])
    except ObjectDoesNotExist as err:
        # Raise 404 error if discount not found
        raise Http404("Discount does not exist") from err


def get_album(ctx: dict, n: int) -> None:
    """Get album by ID and add to context.

    Retrieves an Album object from the database using the provided ID
    and adds it to the template context dictionary.

    Args:
        ctx: Template context dictionary to store the album
        n: Primary key/ID of the album to retrieve

    Raises:
        Http404: If album with the specified ID does not exist

    Returns:
        None: Function modifies the context dictionary in-place
    """
    try:
        # Query database for album with the given primary key
        ctx["album"] = Album.objects.get(pk=n)
    except ObjectDoesNotExist as err:
        # Raise HTTP 404 error if album is not found
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


def round_to_two_significant_digits(number: float) -> int:
    """Round a number to two significant digits using specific thresholds.

    Args:
        number: The numeric value to round.

    Returns:
        The rounded number as an integer.

    Note:
        Numbers with absolute value < 1000 are rounded to the nearest 10.
        Numbers with absolute value >= 1000 are rounded to the nearest 100.
        Uses ROUND_DOWN rounding mode for consistent behavior.
    """
    # Convert input to Decimal for precise arithmetic
    d = Decimal(number)
    threshold = 1000

    # Round by 10 for smaller numbers (< 1000)
    if abs(number) < threshold:
        rounded = d.quantize(Decimal("1E1"), rounding=ROUND_DOWN)
    # Round by 100 for larger numbers (>= 1000)
    else:
        rounded = d.quantize(Decimal("1E2"), rounding=ROUND_DOWN)

    # Return as integer
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


def copy_class(target_id: int, source_id: int, cls) -> None:
    """Copy all objects of a given class from source event to target event.

    This function deletes all existing objects of the specified class in the target event,
    then copies all objects from the source event, including their many-to-many relationships.
    Special handling is provided for access_token fields which are regenerated.

    Args:
        target_id: Target event ID to copy objects to
        source_id: Source event ID to copy objects from
        cls: Django model class to copy instances of

    Returns:
        None

    Raises:
        Exception: Logs warnings for any errors during object copying
    """
    # Remove all existing objects of this class from target event
    cls.objects.filter(event_id=target_id).delete()

    # Iterate through all objects in source event
    for obj in cls.objects.filter(event_id=source_id):
        try:
            # Store many-to-many relationships before cloning
            m2m_data = {}

            # noinspection PyProtectedMember
            for field in obj._meta.many_to_many:
                m2m_data[field.name] = list(getattr(obj, field.name).all())

            # Clone object by resetting primary key and updating event reference
            obj.pk = None
            obj.event_id = target_id
            # noinspection PyProtectedMember
            obj._state.adding = True

            # Regenerate special fields that need unique values
            for field_name, func in {"access_token": my_uuid_short}.items():
                if not hasattr(obj, field_name):
                    continue
                setattr(obj, field_name, func())

            # Save the cloned object
            obj.save()

            # Restore many-to-many relationships on the new object
            for field_name, values in m2m_data.items():
                getattr(obj, field_name).set(values)
        except Exception as err:
            logging.warning(f"found exp: {err}")


def get_payment_methods_ids(ctx: dict) -> set[int]:
    """
    Get set of payment method IDs for an association.

    Args:
        ctx: Context dictionary containing association ID under 'a_id' key.

    Returns:
        Set of payment method primary keys as integers.

    Raises:
        KeyError: If 'a_id' key is not found in context dictionary.
        Association.DoesNotExist: If association with given ID does not exist.
    """
    # Extract association ID from context dictionary
    association_id = ctx["a_id"]

    # Retrieve association instance and get payment method IDs
    association = Association.objects.get(pk=association_id)
    payment_method_ids = association.payment_methods.values_list("pk", flat=True)

    # Convert queryset to set and return
    return set(payment_method_ids)


def detect_delimiter(content: str) -> str:
    """
    Detect CSV delimiter from content header line.

    This function analyzes the first line of CSV content to identify the most
    likely delimiter character used to separate fields.

    Args:
        content (str): CSV content string containing headers and data rows

    Returns:
        str: Detected delimiter character (tab, semicolon, or comma)

    Raises:
        Exception: If no standard delimiter is found in the header line

    Example:
        >>> detect_delimiter("name,age,city\\nJohn,25,NYC")
        ','
        >>> detect_delimiter("name;age;city\\nJohn;25;NYC")
        ';'
    """
    # Extract the first line which should contain column headers
    header = content.split("\n")[0]

    # Check for common delimiters in order of preference
    # Tab, semicolon, comma are the most standard CSV delimiters
    for d in ["\t", ";", ","]:
        if d in header:
            return d

    # No standard delimiter found in header line
    raise Exception("no delimiter")


def clean(s: str) -> str:
    """Clean and normalize string by removing symbols, spaces, and accents.

    Removes all non-word characters, normalizes whitespace, and replaces
    common Italian accented characters with their unaccented equivalents.

    Args:
        s: The input string to clean and normalize.

    Returns:
        A cleaned string with symbols removed, whitespace normalized,
        and accented characters replaced with ASCII equivalents.

    Example:
        >>> clean("Ciao! Come stà?")
        "ciaocomestaì"
    """
    # Convert to lowercase for consistent processing
    s = s.lower()

    # Remove all symbols and non-word characters, replace with spaces
    s = re.sub(r"[^\w]", " ", s)

    # Normalize all whitespace characters to regular spaces
    s = re.sub(r"\s", " ", s)

    # Remove all spaces to create continuous string
    s = re.sub(r" +", "", s)

    # Replace common Italian accented characters with ASCII equivalents
    s = s.replace("ò", "o").replace("ù", "u").replace("à", "a").replace("è", "e").replace("é", "e").replace("ì", "i")

    return s


def _search_char_reg(ctx: dict, char, js: dict) -> None:
    """
    Populate character search result with registration and player data.

    Parameters
    ----------
    ctx : dict
        Context dictionary containing run information and event data
    char : Character
        Character instance with associated registration and player data
    js : dict
        JSON object to populate with search results and character information

    Returns
    -------
    None
        Modifies the js dictionary in-place with character and player data
    """
    # Set character name, preferring custom name if available
    js["name"] = char.name
    if char.rcr and char.rcr.custom_name:
        js["name"] = char.rcr.custom_name

    # Populate player information from registration
    js["player"] = char.reg.display_member()
    js["player_full"] = str(char.reg.member)
    js["player_id"] = char.reg.member.id
    js["first_aid"] = char.reg.member.first_aid

    # Set profile image, prioritizing character's custom profile
    if char.rcr.profile_thumb:
        js["player_prof"] = char.rcr.profile_thumb.url
        js["profile"] = char.rcr.profile_thumb.url
    elif char.reg.member.profile_thumb:
        js["player_prof"] = char.reg.member.profile_thumb.url
    else:
        js["player_prof"] = None

    # Copy custom character attributes if they exist
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

    Fetches help questions from the database, filters them based on context and request method,
    then categorizes them into open and closed questions based on their status.

    Args:
        ctx: Context dictionary containing association/run information with keys:
            - 'a_id': Association ID for filtering questions
            - 'run': Optional run object for additional filtering
        request: HTTP request object used to determine filtering behavior

    Returns:
        A tuple containing two lists:
            - closed_questions: List of closed or staff-created HelpQuestion objects
            - open_questions: List of open user-created HelpQuestion objects
    """
    # Filter questions by association ID
    base_qs = HelpQuestion.objects.filter(assoc_id=ctx["a_id"])

    # Apply run-specific filtering if run context exists
    if "run" in ctx:
        base_qs = base_qs.filter(run=ctx["run"])

    # For non-POST requests, limit to questions from last 90 days
    if request.method != "POST":
        base_qs = base_qs.filter(created__gte=datetime.now() - timedelta(days=90))

    # Get the latest creation timestamp for each member
    latest = base_qs.values("member_id").annotate(latest_created=Max("created")).values("latest_created")

    # Fetch the most recent question for each member with related data
    que = base_qs.filter(created__in=Subquery(latest)).select_related("member", "run", "run__event")

    # Categorize questions based on user type and closure status
    open_q = []
    closed_q = []
    for cq in que:
        # Open questions: user-created and not closed
        if cq.is_user and not cq.closed:
            open_q.append(cq)
        else:
            # Closed questions: staff-created or closed user questions
            closed_q.append(cq)

    return closed_q, open_q


def get_recaptcha_secrets(request: HttpRequest) -> tuple[str | None, str | None]:
    """Get reCAPTCHA public and private keys for the current request.

    Handles both single-site and multi-site configurations. For multi-site setups,
    keys are stored as comma-separated pairs in format "skin_id:key".

    Args:
        request: Django request object containing association data with skin_id.

    Returns:
        Tuple of (public_key, private_key). Both may be None if not found.
    """
    # Get base configuration keys
    public = conf_settings.RECAPTCHA_PUBLIC_KEY
    private = conf_settings.RECAPTCHA_PRIVATE_KEY

    # Handle multi-site configuration with comma-separated key pairs
    if "," in public:
        # Extract skin ID from request association data
        skin_id = request.assoc["skin_id"]

        # Parse public key pairs and find matching skin ID
        pairs = dict(item.split(":") for item in public.split(",") if ":" in item)
        public = pairs.get(str(skin_id))

        # Parse private key pairs and find matching skin ID
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
