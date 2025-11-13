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
from __future__ import annotations

import html
import logging
import random
import re
import string
import unicodedata
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytz
from background_task.models import Task
from diff_match_patch import diff_match_patch
from django.conf import settings as conf_settings
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max, Subquery
from django.http import Http404, HttpRequest
from django.utils import timezone
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

if TYPE_CHECKING:
    from django.contrib.auth.models import User


class DelimiterNotFoundError(ValueError):
    """Raised when CSV delimiter cannot be detected."""


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


def get_channel(first_entity_id, second_entity_id):
    """Generate unique channel ID for two entities.

    Args:
        first_entity_id (int): First entity ID
        second_entity_id (int): Second entity ID

    Returns:
        int: Unique channel ID using Cantor pairing

    """
    first_entity_id = int(first_entity_id)
    second_entity_id = int(second_entity_id)
    if first_entity_id > second_entity_id:
        return int(cantor(first_entity_id, second_entity_id))
    return int(cantor(second_entity_id, first_entity_id))


def cantor(first_integer, second_integer):
    """Cantor pairing function to map two integers to a unique integer.

    Args:
        first_integer (int): First integer
        second_integer (int): Second integer

    Returns:
        float: Unique pairing result

    """
    return ((first_integer + second_integer) * (first_integer + second_integer + 1) / 2) + second_integer


def compute_diff(self, other) -> None:
    """Compute differences between this instance and another.

    Args:
        self: Current instance
        other: Other instance to compare against

    """
    check_diff(self, other.text, self.text)


def check_diff(self, old_text, new_text) -> None:
    """Generate HTML diff between two text strings.

    Args:
        self: Instance to store diff result
        old_text: First text string
        new_text: Second text string

    """
    if old_text == new_text:
        self.diff = None
        return
    diff_engine = diff_match_patch()
    self.diff = diff_engine.diff_main(old_text, new_text)
    diff_engine.diff_cleanupEfficiency(self.diff)
    self.diff = diff_engine.diff_prettyHtml(self.diff)


def get_member(member_id: int) -> Member:
    """Get member by ID with proper error handling.

    Args:
        member_id: Member ID

    Returns:
        dict: Dictionary containing member instance

    Raises:
        Http404: If member does not exist

    """
    try:
        return Member.objects.get(pk=member_id)
    except ObjectDoesNotExist as err:
        msg = "Member does not exist"
        raise Http404(msg) from err


def get_contact(member_id, other_member_id):
    """Get contact relationship between two members.

    Args:
        member_id: ID of first member
        other_member_id: ID of second member

    Returns:
        Contact: Contact instance or None if not found

    """
    try:
        return Contact.objects.get(me_id=member_id, you_id=other_member_id)
    except ObjectDoesNotExist:
        return None


def get_event_template(context, template_id) -> None:
    """Get event template by ID and add to context.

    Args:
        context: Template context dictionary
        template_id: Event template ID

    """
    try:
        context["event"] = Event.objects.get(pk=template_id, template=True, association_id=context["association_id"])
    except ObjectDoesNotExist as err:
        raise NotFoundError from err


def get_char(context, character_identifier, *, by_number=False) -> None:
    """Get character by ID or number and add to context.

    Args:
        context: Template context dictionary
        character_identifier: Character ID or number
        by_number: Whether to search by number instead of ID

    """
    get_element(context, character_identifier, "character", Character, by_number=by_number)


def get_registration(context, registration_id) -> None:
    """Get registration by ID and add to context.

    Args:
        context: Template context dictionary
        registration_id: Registration ID

    Raises:
        Http404: If registration does not exist

    """
    try:
        context["registration"] = Registration.objects.get(run=context["run"], pk=registration_id)
        context["name"] = str(context["registration"])
    except ObjectDoesNotExist as err:
        msg = "Registration does not exist"
        raise Http404(msg) from err


def get_discount(context, discount_id) -> None:
    """Get discount by ID and add to context.

    Args:
        context: Template context dictionary
        discount_id: Discount ID

    Raises:
        Http404: If discount does not exist

    """
    try:
        context["discount"] = Discount.objects.get(pk=discount_id)
        context["name"] = str(context["discount"])
    except ObjectDoesNotExist as err:
        msg = "Discount does not exist"
        raise Http404(msg) from err


def get_album(context, album_id) -> None:
    """Get album by ID and add to context.

    Args:
        context: Template context dictionary
        album_id: Album ID

    Raises:
        Http404: If album does not exist

    """
    try:
        context["album"] = Album.objects.get(pk=album_id)
    except ObjectDoesNotExist as err:
        msg = "Album does not exist"
        raise Http404(msg) from err


def get_album_cod(context: dict, album_code: str) -> None:
    """Get album by code and add it to context, raising 404 if not found."""
    try:
        context["album"] = Album.objects.get(cod=album_code)
    except ObjectDoesNotExist as err:
        msg = "Album does not exist"
        raise Http404(msg) from err


def get_feature(context: dict, feature_slug: str) -> None:
    """Add feature to context or raise 404 if not found."""
    try:
        context["feature"] = Feature.objects.get(slug=feature_slug)
    except ObjectDoesNotExist as err:
        msg = "Feature does not exist"
        raise Http404(msg) from err


def get_feature_module(context: dict, num: int) -> None:
    """Retrieve FeatureModule by ID and add it to context, or raise 404 if not found."""
    try:
        context["feature_module"] = FeatureModule.objects.get(pk=num)
    except ObjectDoesNotExist as err:
        msg = "FeatureModule does not exist"
        raise Http404(msg) from err


def get_plot(context: dict, plot_id: int) -> None:
    """Fetch and add plot to context with related data.

    Args:
        context: View context dictionary to update
        plot_id: Primary key of the plot to retrieve

    Raises:
        Http404: If plot does not exist for the event

    """
    try:
        # Fetch plot with optimized queries for related objects and characters
        context["plot"] = (
            Plot.objects.select_related("event", "progress", "assigned")
            .prefetch_related("characters", "plotcharacterrel_set__character")
            .get(event=context["event"], pk=plot_id)
        )
        # Set plot name in context for template display
        context["name"] = context["plot"].name
    except ObjectDoesNotExist as err:
        msg = "Plot does not exist"
        raise Http404(msg) from err


def get_quest_type(context: dict, quest_number: int) -> None:
    """Get quest type from context by number."""
    get_element(context, quest_number, "quest_type", QuestType)


def get_quest(context: dict, quest_number: int) -> None:
    """Get a quest element and add it to the context."""
    get_element(context, quest_number, "quest", Quest)


def get_trait(character_context: dict, trait_name: str) -> None:
    """Get trait from character context by name."""
    get_element(character_context, trait_name, "trait", Trait)


def get_handout(context: dict, handout_id: int) -> None:
    """Fetch handout from database and populate context with its data.

    Args:
        context: View context dictionary to populate with handout data
        handout_id: Primary key of the handout to retrieve

    Raises:
        Http404: If handout does not exist for the given event

    """
    try:
        # Retrieve handout for current event
        context["handout"] = Handout.objects.get(event=context["event"], pk=handout_id)
        context["name"] = context["handout"].name

        # Populate handout data for display
        context["handout"].data = context["handout"].show()
    except ObjectDoesNotExist as err:
        msg = "handout does not exist"
        raise Http404(msg) from err


def get_handout_template(context: dict, handout_template_id: int) -> dict:
    """Add handout template to context dict.

    Args:
        context: View context dictionary
        handout_template_id: Primary key of the handout template

    Returns:
        Updated context dictionary

    Raises:
        Http404: If handout template does not exist

    """
    try:
        # Fetch the handout template and add to context
        context["handout_template"] = HandoutTemplate.objects.get(event=context["event"], pk=handout_template_id)
        context["name"] = context["handout_template"].name
    except ObjectDoesNotExist as err:
        msg = "handout_template does not exist"
        raise Http404(msg) from err

    return context


def get_prologue(context: dict, prologue_number: int) -> None:
    """Retrieve prologue element and add it to the context."""
    get_element(context, prologue_number, "prologue", Prologue)


def get_prologue_type(context: dict, prologue_type_id: int) -> dict:
    """Fetch prologue type and add it to context with its name."""
    try:
        # Retrieve prologue type for the event
        context["prologue_type"] = PrologueType.objects.get(event=context["event"], pk=prologue_type_id)
        context["name"] = str(context["prologue_type"])
    except ObjectDoesNotExist as error:
        msg = "prologue_type does not exist"
        raise Http404(msg) from error

    return context


def get_speedlarp(context: dict, speedlarp_id: int) -> None:
    """Get speedlarp object and add it to context with its name.

    Args:
        context: View context dictionary containing event
        speedlarp_id: Primary key of the SpeedLarp object

    Raises:
        Http404: If speedlarp doesn't exist for the event

    """
    try:
        # Retrieve speedlarp for current event
        context["speedlarp"] = SpeedLarp.objects.get(event=context["event"], pk=speedlarp_id)
        context["name"] = str(context["speedlarp"])
    except ObjectDoesNotExist as err:
        msg = "speedlarp does not exist"
        raise Http404(msg) from err

    # ~ def get_ord_faction(char):
    # ~ for g in char.factions_list.all():
    # ~ if g.typ == FactionType.PRIM:
    # ~ return (g.get_name(), g)
    # ~ return ("UNASSIGNED", None)


def get_badge(badge_id: int, context: dict) -> Badge:
    """Get a badge by ID for a specific association."""
    try:
        return Badge.objects.get(pk=badge_id, association_id=context["association_id"])
    except ObjectDoesNotExist as err:
        msg = "Badge does not exist"
        raise Http404(msg) from err


def get_collection_partecipate(context: dict[str, Any], contribution_code: str) -> Collection:
    """Retrieve collection by contribution code for the current association.

    Args:
        context: View context containing association_id
        contribution_code: Unique contribution code for the collection

    Returns:
        Collection object matching the criteria

    Raises:
        Http404: If collection does not exist

    """
    try:
        return Collection.objects.get(contribute_code=contribution_code, association_id=context["association_id"])
    except ObjectDoesNotExist as err:
        msg = "Collection does not exist"
        raise Http404(msg) from err


def get_collection_redeem(context: dict, redeem_code: str) -> Collection:
    """Get Collection by redeem code and association from context.

    Args:
        context: View context containing association_id
        redeem_code: Unique redemption code for the collection

    Returns:
        Collection: The matching Collection instance

    Raises:
        Http404: If collection not found for given code and association

    """
    try:
        return Collection.objects.get(redeem_code=redeem_code, association_id=context["association_id"])
    except ObjectDoesNotExist as error:
        msg = "Collection does not exist"
        raise Http404(msg) from error


def get_workshop(context: dict, workshop_id: int) -> None:
    """Get workshop module and add it to context, raise 404 if not found."""
    try:
        context["workshop"] = WorkshopModule.objects.get(event=context["event"], pk=workshop_id)
    except ObjectDoesNotExist as error:
        msg = "WorkshopModule does not exist"
        raise Http404(msg) from error


def get_workshop_question(context: dict, n: int, mod: int) -> dict:
    """Get workshop question and add it to context.

    Args:
        context: Template context dictionary containing event
        n: Workshop question primary key
        mod: Module primary key

    Returns:
        Updated context dictionary with workshop_question

    Raises:
        Http404: If WorkshopQuestion doesn't exist

    """
    try:
        # Retrieve workshop question filtered by event and module
        context["workshop_question"] = WorkshopQuestion.objects.get(
            module__event=context["event"],
            pk=n,
            module__pk=mod,
        )
    except ObjectDoesNotExist as err:
        msg = "WorkshopQuestion does not exist"
        raise Http404(msg) from err

    return context


def get_workshop_option(context: dict, m: int) -> None:
    """Get workshop option by ID and validate it belongs to the current event.

    Args:
        context: Context dictionary to store the workshop option
        m: Workshop option primary key

    Raises:
        Http404: If workshop option doesn't exist or belongs to wrong event

    """
    try:
        # Retrieve workshop option by primary key
        context["workshop_option"] = WorkshopOption.objects.get(pk=m)
    except ObjectDoesNotExist as err:
        msg = "WorkshopOption does not exist"
        raise Http404(msg) from err

    # Validate workshop option belongs to current event
    if context["workshop_option"].question.module.event != context["event"]:
        msg = "wrong event"
        raise Http404(msg)


def get_element(
    context: dict[str, Any],
    primary_key: int | str,
    context_key_name: str,
    model_class: type[BaseModel],
    *,
    by_number: bool = False,
) -> None:
    """Retrieve a model instance and add it to the context dictionary.

    Fetches a model instance related to a parent event and stores it in the provided
    context dictionary. The lookup can be performed either by primary key or by a
    'number' field.

    Args:
        context: Context dictionary that must contain an 'event' key with a model
            instance that has a `get_class_parent()` method. The retrieved object
            will be added to this dictionary under the key specified by `context_key_name`.
        primary_key: The identifier used to look up the model instance. Either a primary
            key (int/str) or a number field value depending on `by_number` parameter.
        context_key_name: The key name under which the retrieved object will be stored
            in the context dictionary. Also used in error messages.
        model_class: The Django model class to query. Must have a foreign key relationship
            to an 'event' and optionally a 'number' field if `by_number=True`.
        by_number: If True, lookup by 'number' field instead of primary key.

    Raises:
        Http404: If the requested object does not exist in the database.

    Example:
        >>> context = {"event": some_event_instance}
        >>> get_element(context, 42, "ticket", Ticket, by_number=True)
        >>> # context now contains: {"event": ..., "ticket": <Ticket>, "class_name": "ticket"}

    """
    try:
        # Get the parent event associated with the current event in context
        parent_event = context["event"].get_class_parent(model_class)

        # Perform database lookup based on specified field
        if by_number:
            # Lookup by 'number' field (e.g., ticket number, order number)
            context[context_key_name] = model_class.objects.get(event=parent_event, number=primary_key)
        else:
            # Lookup by primary key (default behavior)
            context[context_key_name] = model_class.objects.get(event=parent_event, pk=primary_key)

        # Store the context key name for potential later reference
        context["class_name"] = context_key_name

    except ObjectDoesNotExist as err:
        # Raise a user-friendly 404 error if the object doesn't exist
        msg = f"{context_key_name} does not exist"
        raise Http404(msg) from err


def get_relationship(context: dict, num: int) -> None:
    """Retrieve a relationship by ID and validate it belongs to the event."""
    try:
        context["relationship"] = Relationship.objects.get(pk=num)
    except ObjectDoesNotExist as err:
        msg = "relationship does not exist"
        raise Http404(msg) from err

    # Validate relationship belongs to the current event
    if context["relationship"].source.event_id != context["event"].id:
        msg = "wrong event"
        raise Http404(msg)


def get_player_relationship(context: dict, other_player_number: int) -> None:
    """Retrieve and add player relationship to context."""
    try:
        # Get relationship for the run's registration targeting the specified player
        context["relationship"] = PlayerRelationship.objects.get(
            reg=context["run"].reg,
            target__number=other_player_number,
        )
    except ObjectDoesNotExist as err:
        msg = "relationship does not exist"
        raise Http404(msg) from err


def get_time_diff(start_datetime: date, end_datetime: date) -> int:
    """Calculate the difference in days between two datetimes."""
    return (start_datetime - end_datetime).days


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

    return get_time_diff(target_date, timezone.now().date())


def generate_number(length: int) -> str:
    """Generate a random string of digits with the specified length."""
    return "".join(random.choice(string.digits) for _ in range(length))  # noqa: S311


def html_clean(text: str | None) -> str:
    """Clean HTML tags and unescape HTML entities from text.

    Args:
        text: Input text that may contain HTML tags and entities.

    Returns:
        Cleaned text with HTML tags removed and entities unescaped.

    """
    if not text:
        return ""
    # Remove all HTML tags from the text
    text = strip_tags(text)
    # Unescape HTML entities (e.g., &amp; -> &, &lt; -> <)
    return html.unescape(text)


def dump(obj: object) -> str:
    """Return a string representation of all object attributes and their values."""
    output_string = ""
    for attribute_name in dir(obj):
        output_string += f"obj.{attribute_name} = {getattr(obj, attribute_name)!r}\n"
    return output_string


def rmdir(directory: Path) -> None:
    """Recursively remove a directory and all its contents."""
    directory = Path(directory)

    # Iterate through all items in the directory
    for filesystem_entry in directory.iterdir():
        if filesystem_entry.is_dir():
            # Recursively remove subdirectories
            rmdir(filesystem_entry)
        else:
            # Remove files
            filesystem_entry.unlink()

    # Remove the empty directory
    directory.rmdir()


def average(lst: list[float]) -> float:
    """Calculate the arithmetic mean of a list of numbers."""
    return sum(lst) / len(lst)


def pretty_request(request: HttpRequest) -> str:
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


def remove_choice(choices: list[tuple], term_to_remove: str) -> list[tuple]:
    """Remove choice from list where first element matches term."""
    filtered_choices = []
    # Iterate through each element in the list
    for choice in choices:
        if choice[0] == term_to_remove:
            continue
        filtered_choices.append(choice)
    return filtered_choices


def check_field(model_class: type, field_name: str) -> bool:
    """Check if a field exists in the Django model class.

    Args:
        model_class: The Django model class to check
        field_name: The name of the field to look for

    Returns:
        True if field exists, False otherwise

    """
    # Iterate through all fields including hidden ones
    return any(field.name == field_name for field in model_class._meta.get_fields(include_hidden=True))  # noqa: SLF001  # Django model metadata


def round_to_two_significant_digits(number: float) -> int:
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
    decimal_number = Decimal(number)
    small_number_threshold = 1000

    # Round by 10 for smaller numbers
    if abs(number) < small_number_threshold:
        rounded_decimal = decimal_number.quantize(Decimal("1E1"), rounding=ROUND_DOWN)
    # Round by 100 for larger numbers
    else:
        rounded_decimal = decimal_number.quantize(Decimal("1E2"), rounding=ROUND_DOWN)

    # Convert back to integer and return
    return int(rounded_decimal)


def exchange_order(context: dict, model_class: type, element_id: int, move_up: int, elements=None) -> None:
    """Exchange ordering positions between two elements in a sequence.

    This function moves an element up or down in the ordering sequence by swapping
    its order value with an adjacent element. If no adjacent element exists,
    it simply increments or decrements the order value.

    Args:
        context: Context dictionary to store the current element after operation.
        model_class: Model class of elements to reorder.
        element_id: Primary key of the element to move.
        move_up: Direction to move - 1 for up (increase order), 0 for down (decrease order).
        elements: Optional queryset of elements. Defaults to event elements if None.

    Returns:
        None: Function modifies elements in-place and updates context['current'].

    Note:
        The function handles edge cases where elements have the same order value
        by adjusting one of them to maintain proper ordering.

    """
    # Get elements queryset, defaulting to event elements if not provided
    elements = elements or context["event"].get_elements(model_class)
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
        context["current"] = current_element
        return

    # Exchange ordering values between current and adjacent element
    current_element.order, adjacent_element.order = adjacent_element.order, current_element.order

    # Handle edge case where both elements have same order (data inconsistency)
    if current_element.order == adjacent_element.order:
        adjacent_element.order += -1 if move_up else 1

    # Save both elements and update context
    current_element.save()
    adjacent_element.save()
    context["current"] = current_element


def normalize_string(input_string: str) -> str:
    """Normalize a string by converting to lowercase, removing spaces and accents.

    Args:
        input_string: Input string to normalize.

    Returns:
        Normalized string with lowercase, no spaces, and no accented characters.

    """
    # Convert to lowercase
    normalized_string = input_string.lower()

    # Remove spaces
    normalized_string = normalized_string.replace(" ", "")

    # Remove accented characters using Unicode normalization
    return "".join(
        char for char in unicodedata.normalize("NFD", normalized_string) if unicodedata.category(char) != "Mn"
    )


def copy_class(target_event_id, source_event_id, model_class) -> None:
    """Copy all objects of a given class from source event to target event.

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
            for field in source_object._meta.many_to_many:  # noqa: SLF001  # Django model metadata
                many_to_many_data[field.name] = list(getattr(source_object, field.name).all())

            source_object.pk = None
            source_object.event_id = target_event_id
            # noinspection PyProtectedMember
            source_object._state.adding = True  # noqa: SLF001  # Django model state
            for field_name, generation_function in {"access_token": my_uuid_short}.items():
                if not hasattr(source_object, field_name):
                    continue
                setattr(source_object, field_name, generation_function())
            source_object.save()

            # copy m2m relations
            for field_name, related_values in many_to_many_data.items():
                getattr(source_object, field_name).set(related_values)
        except Exception as error:  # noqa: BLE001 - Complex object cloning may fail in many ways, log and continue
            logger.warning("found exp: %s", error)


def get_payment_methods_ids(context):
    """Get set of payment method IDs for an association.

    Args:
        context: Context dictionary containing association ID

    Returns:
        set: Set of payment method primary keys

    """
    return set(Association.objects.get(pk=context["association_id"]).payment_methods.values_list("pk", flat=True))


def detect_delimiter(content):
    """Detect CSV delimiter from content header line.

    Args:
        content: CSV content string

    Returns:
        str: Detected delimiter character

    Raises:
        DelimiterNotFoundError: If no delimiter is found

    """
    header_line = content.split("\n")[0]
    for delimiter in ["\t", ";", ","]:
        if delimiter in header_line:
            return delimiter
    msg = "no delimiter"
    raise DelimiterNotFoundError(msg)


def clean(s):
    """Clean and normalize string by removing symbols, spaces, and accents.

    Args:
        s: String to clean

    Returns:
        str: Cleaned string with normalized characters

    """
    s = s.lower()
    s = re.sub(r"[^\w]", " ", s)  # remove symbols
    s = re.sub(r"\s", " ", s)  # replace whitespaces with spaces
    s = re.sub(r" +", "", s)  # remove spaces
    return s.replace("ò", "o").replace("ù", "u").replace("à", "a").replace("è", "e").replace("é", "e").replace("ì", "i")


def _search_char_reg(context: dict, character, search_result: dict) -> None:
    """Populate character search result with registration and player data.

    This function extracts character and player information from registration data
    and populates a JSON object for search results display.

    Args:
        context : dict
            Context dictionary containing run information and event data
        character : Character
            Character instance with associated registration data
        search_result : dict
            JSON object to populate with search results data

    Returns: None -Modifies the search_result dictionary in place

    """
    # Set character name, prioritizing custom name if available
    search_result["name"] = character.name
    if character.rcr and character.rcr.custom_name:
        search_result["name"] = character.rcr.custom_name

    # Extract player information from registration
    search_result["player"] = character.reg.display_member()
    search_result["player_full"] = str(character.reg.member)
    search_result["player_id"] = character.reg.member_id
    search_result["first_aid"] = character.reg.member.first_aid

    # Set profile image with fallback hierarchy: character custom -> member -> None
    if character.rcr.profile_thumb:
        search_result["player_prof"] = character.rcr.profile_thumb.url
        search_result["profile"] = character.rcr.profile_thumb.url
    elif character.reg.member.profile_thumb:
        search_result["player_prof"] = character.reg.member.profile_thumb.url
    else:
        search_result["player_prof"] = None

    # Extract custom character attributes (pronoun, song, public, private notes)
    for attribute_suffix in ["pronoun", "song", "public", "private"]:
        if hasattr(character.rcr, "custom_" + attribute_suffix):
            search_result[attribute_suffix] = getattr(character.rcr, "custom_" + attribute_suffix)

    # Override profile with character cover if event supports both cover and user characters
    if {"cover", "user_character"}.issubset(get_event_features(context["run"].event_id)) and character.cover:
        search_result["player_prof"] = character.thumb.url


def clear_messages(request: HttpRequest) -> None:
    """Clear all queued messages from the request."""
    if hasattr(request, "_messages"):
        request._messages._queued_messages.clear()  # noqa: SLF001  # Django messages internal


def _get_help_questions(context: dict, request: HttpRequest) -> tuple[list, list]:
    """Retrieve and categorize help questions for the current association/run.

    Fetches help questions filtered by association and optionally by run, then
    categorizes them into open and closed questions based on their status and origin.

    Args:
        context: Context dictionary containing association/run information.
             Must include 'association_id' key, optionally includes 'run' key.
        request: HTTP request object used to determine filtering behavior.

    Returns:
        A tuple containing two lists:
        - closed_questions: List of closed or staff-originated questions
        - open_questions: List of open user-originated questions

    """
    # Filter questions by association ID
    base_queryset = HelpQuestion.objects.filter(association_id=context["association_id"])

    # Add run filter if run context exists
    if "run" in context:
        base_queryset = base_queryset.filter(run=context["run"])

    # For non-POST requests, limit to questions from last 90 days
    if request.method != "POST":
        base_queryset = base_queryset.filter(created__gte=timezone.now() - timedelta(days=90))

    # Find the latest creation timestamp for each member
    latest_created_per_member = (
        base_queryset.values("member_id").annotate(latest_created=Max("created")).values("latest_created")
    )

    # Get the most recent question for each member with related data
    questions = base_queryset.filter(created__in=Subquery(latest_created_per_member)).select_related(
        "member",
        "run",
        "run__event",
    )

    # Categorize questions into open and closed lists
    open_questions = []
    closed_questions = []
    for current_question in questions:
        # Open questions are user-originated and not closed
        if current_question.is_user and not current_question.closed:
            open_questions.append(current_question)
        else:
            closed_questions.append(current_question)

    return closed_questions, open_questions


def get_recaptcha_secrets(request: HttpRequest) -> tuple[str | None, str | None]:
    """Get reCAPTCHA public and private keys for the current request.

    Handles both single-site and multi-site configurations. In multi-site mode,
    keys are stored as comma-separated pairs in format "skin_id:key".

    Args:
        request: Django request object with association data containing skin_id

    Returns:
        Tuple of (public_key, private_key) or (None, None) if not found

    """
    # Get base configuration values
    public_key = conf_settings.RECAPTCHA_PUBLIC_KEY
    private_key = conf_settings.RECAPTCHA_PRIVATE_KEY

    # Handle multi-site configuration with comma-separated values
    if "," in public_key:
        # Extract skin_id from request association data
        current_skin_id = request.association["skin_id"]

        # Parse public key pairs and find matching skin_id
        public_key_pairs = dict(entry.split(":") for entry in public_key.split(",") if ":" in entry)
        public_key = public_key_pairs.get(str(current_skin_id))

        # Parse private key pairs and find matching skin_id
        private_key_pairs = dict(entry.split(":") for entry in private_key.split(",") if ":" in entry)
        private_key = private_key_pairs.get(str(current_skin_id))

    return public_key, private_key


def welcome_user(request: HttpRequest, user: User) -> None:
    """Display welcome message for user."""
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


def get_now():
    """Get current time - if executed in debug/test, without timezone, add it."""
    now = timezone.now()
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        # If timezone.now() returns naive, make it aware
        now = now.replace(tzinfo=dt_timezone.utc)
    return now
