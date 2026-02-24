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

from typing import Any

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Max
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.association import clear_association_cache
from larpmanager.cache.association_text import clear_association_text_cache_on_delete
from larpmanager.cache.association_translation import clear_association_translation_cache
from larpmanager.cache.config import get_association_config, get_event_config, reset_element_configs
from larpmanager.cache.feature import reset_association_features
from larpmanager.cache.links import reset_event_links
from larpmanager.cache.permission import clear_index_permission_cache
from larpmanager.cache.role import remove_association_role_cache
from larpmanager.cache.wwyltd import reset_features_cache, reset_guides_cache, reset_tutorials_cache
from larpmanager.models.access import AssociationPermission, AssociationRole
from larpmanager.models.association import Association, AssociationText
from larpmanager.models.event import Event, Run
from larpmanager.models.member import Membership
from larpmanager.models.registration import Registration, RegistrationCharacterRel
from larpmanager.utils.services.event import reset_all_run


def generate_association_encryption_key(association: Any) -> None:
    """Generate Fernet encryption key for new associations."""
    if not association.key:
        association.key = Fernet.generate_key()


def auto_assign_association_permission_number(association_permission: Any) -> None:
    """Assign number to association permission if not set.

    Args:
        association_permission: AssociationPermission instance to assign number to

    """
    if not association_permission.number:
        max_number = AssociationPermission.objects.filter(
            feature__module=association_permission.feature.module,
        ).aggregate(Max("number"))["number__max"]
        if not max_number:
            max_number = 1
        association_permission.number = max_number + 10


def prepare_association_skin_features(instance: Association) -> None:
    """Prepare association skin features by applying default values from the skin.

    Updates the association instance with default values from its associated skin
    if this is a new association or if the skin has changed. Only applies defaults
    for fields that are currently empty/None.

    Args:
        instance: Association instance to update with skin defaults

    Returns:
        None

    """
    # Early return if no skin is associated
    if not instance.skin_id:
        return

    # Check if this is a new association or if the skin has changed
    # Only proceed if skin is new or different from previous value
    if instance.pk:
        try:
            previous_association = Association.objects.get(pk=instance.pk)
        except ObjectDoesNotExist:
            return
        # Skip if skin hasn't changed
        if instance.skin_id == previous_association.skin_id:
            return

    # Retrieve the skin object, return early if not found
    try:
        skin = instance.skin
    except ObjectDoesNotExist:
        return

    # Mark instance for skin feature updates
    instance._update_skin_features = True  # noqa: SLF001  # Internal flag for skin feature updates

    # Apply skin defaults only to empty/unset fields
    # Set default nationality if not already specified
    if not instance.nationality:
        instance.nationality = skin.default_nation

    # Set default optional fields configuration if not set
    if not instance.optional_fields:
        instance.optional_fields = skin.default_optional_fields

    # Set default mandatory fields configuration if not set
    if not instance.mandatory_fields:
        instance.mandatory_fields = skin.default_mandatory_fields


def apply_skin_features_to_association(association: Association) -> None:
    """Handle association skin feature setup after saving.

    This function updates an association's features to match its skin's default
    features when the association has been modified to use a new skin.

    Args:
        association: Association instance that was saved. Must have a skin attribute
                 with default_features and a features manager.

    Note:
        The function only executes if the instance has the _update_skin_features
        attribute set, which indicates that skin features should be updated.
        The actual feature update is deferred until after the current database
        transaction commits to ensure data consistency.

    """
    # Check if the association is marked for skin feature updates
    if not hasattr(association, "_update_skin_features"):
        return

    # Define the feature update operation to run after transaction commit
    def update_features() -> None:
        """Replace all features with the skin's default features."""
        association.features.set(association.skin.default_features.all())

    # Schedule the feature update to run after the current transaction commits
    transaction.on_commit(update_features)


def _reset_all_association(association_id: int, association_slug: str) -> None:
    """Reset all cache of one association."""
    # Clear association overall cache
    clear_association_cache(association_slug)

    # Clear association features cache
    reset_association_features(association_id)

    # Clear association translation caches for all languages
    for language_code, _language_name in settings.LANGUAGES:
        clear_association_translation_cache(association_id, language_code)

    # Clear association config cache
    association_obj = Association.objects.get(id=association_id)
    reset_element_configs(association_obj)

    # Clear permission index caches (for both association and event)
    clear_index_permission_cache("association")
    clear_index_permission_cache("event")

    # Clear global WWYLTD caches (guides, tutorials, features)
    reset_guides_cache()
    reset_tutorials_cache()
    reset_features_cache()

    # Clear association text caches for all AssociationText instances
    for assoc_text in AssociationText.objects.filter(association_id=association_id):
        clear_association_text_cache_on_delete(assoc_text)

    # Clear association role caches
    for assoc_role_id in AssociationRole.objects.filter(association_id=association_id).values_list("id", flat=True):
        remove_association_role_cache(assoc_role_id)

    # Clear event links for all members of this association
    for member_id in Membership.objects.filter(association__id=association_id).values_list("member_id", flat=True):
        reset_event_links(member_id, association_id)

    # Clear all events' caches for this association
    for run in Run.objects.filter(event__association_id=association_id):
        reset_all_run(run.event, run)


def _get_registrations_url(association_id: int) -> str:
    """Return URL to the registrations page of the first event that has registrations, or exe_events as fallback."""
    reg = Registration.objects.filter(run__event__association_id=association_id).select_related("run__event").first()
    if reg:
        return reverse("orga_registrations", kwargs={"event_slug": reg.run.event.slug})
    return reverse("exe_events")


def get_activation_checklist(association_id: int) -> tuple[list[dict], int]:
    """Build the activation checklist and compute progress for a demo association.

    Each item represents a required setup step. Progress is expressed as an
    integer percentage (0-100) based on how many steps are complete.

    Args:
        association_id: Primary key of the association to evaluate.

    Returns:
        A tuple of (checklist, progress) where:
            - checklist: list of dicts with keys slug, name, descr, done, url
            - progress: integer percentage of completed steps (0-100)

    """
    association = Association.objects.only("skin_id").get(pk=association_id)

    event_ids = list(Event.objects.filter(association_id=association_id).values_list("id", flat=True))

    def _done(slug: str) -> bool:
        config_key = f"{slug}_suggestion"
        if slug.startswith("exe"):
            return bool(get_association_config(association_id, config_key, default_value=False))
        return any(get_event_config(eid, config_key, default_value=False) for eid in event_ids)

    checklist = [
        {
            "slug": "exe_events",
            "name": _("Event creation"),
            "descr": _("Create your first event"),
            "done": Event.objects.filter(association_id=association_id).exists(),
            "url": reverse("exe_events"),
        },
        {
            "slug": "exe_methods",
            "name": _("Payment methods"),
            "descr": _("Configure at least one payment method for participants"),
            "done": _done("exe_methods"),
            "url": reverse("exe_methods"),
        },
        {
            "slug": "orga_roles",
            "name": _("Event roles"),
            "descr": _("Define at least one additional role for event management"),
            "done": _done("orga_roles"),
            "url": reverse("redr", kwargs={"path": "event/manage/roles/"}),
        },
        {
            "slug": "orga_registration_tickets",
            "name": _("Registration tickets"),
            "descr": _("Create at least one ticket type for event registrations"),
            "done": _done("orga_registration_tickets"),
            "url": reverse("redr", kwargs={"path": "event/manage/tickets/"}),
        },
        {
            "slug": "orga_registration_form",
            "name": _("Registration form"),
            "descr": _("Define at least one question in the registration form"),
            "done": _done("orga_registration_form"),
            "url": reverse("redr", kwargs={"path": "event/manage/form/"}),
        },
        {
            "slug": "orga_registrations",
            "name": _("First registration"),
            "descr": _("Have at least one participant registered for an event"),
            "done": Registration.objects.filter(run__event__association_id=association_id).exists(),
            "url": _get_registrations_url(association_id),
        },
    ]

    if association.skin_id == 1:
        checklist += [
            {
                "slug": "orga_characters",
                "name": _("First character"),
                "descr": _("Create at least one character for one of your events"),
                "done": _done("orga_characters"),
                "url": reverse("redr", kwargs={"path": "event/manage/characters/"}),
            },
            {
                "slug": "orga_casting",
                "name": _("First assignment"),
                "descr": _("Assign a character to a registered participant"),
                "done": RegistrationCharacterRel.objects.filter(
                    registration__run__event__association_id=association_id
                ).exists(),
                "url": reverse("redr", kwargs={"path": "event/manage/registrations/"}),
            },
        ]

    done_count = sum(1 for item in checklist if item["done"])
    progress = round(done_count * 100 / len(checklist))

    return checklist, progress
