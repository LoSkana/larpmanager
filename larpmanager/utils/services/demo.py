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
"""Deep-copy engine that clones a template association into a demo instance."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from background_task import background
from dateutil.relativedelta import relativedelta
from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Min, Q
from django.utils import timezone

from larpmanager.cache.association import clear_association_cache
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemOther,
    AccountingItemPayment,
    AccountingItemTransaction,
    Discount,
    PaymentInvoice,
)
from larpmanager.models.association import Association, AssociationConfig, AssociationText
from larpmanager.models.event import Event, EventButton, EventConfig, EventText, ProgressStep, Run
from larpmanager.models.experience import (
    AbilityExp,
    AbilityTypeExp,
    CriterionExp,
    DeliveryExp,
    ModifierExp,
    RuleExp,
    SystemExp,
)
from larpmanager.models.form import (
    QuestionApplicable,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingAnswer,
    WritingChoice,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.larpmanager import LarpManagerDemoHint, LarpManagerDemoHintDismissal
from larpmanager.models.member import Member, Membership
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSection,
    RegistrationSurcharge,
    RegistrationTicket,
)
from larpmanager.models.utils import my_uuid, my_uuid_short
from larpmanager.models.writing import (
    Character,
    Faction,
    Plot,
    PlotCharacterRel,
    Prologue,
    PrologueType,
    Relationship,
    SpeedLarp,
)
from larpmanager.utils.core.clone_guard import clone_signals_suppressed

logger = logging.getLogger(__name__)

# M2M fields never copied onto the clone (they point at staff or template-management data)
SKIPPED_M2M_FIELDS = frozenset({"maintainers", "allowed"})

DEMO_LIFETIME_SECONDS = 30 * 24 * 3600


class CloneContext:
    """Holds the state shared by all steps of a single association clone."""

    def __init__(self, template: Association, delta: timedelta) -> None:
        """Initialize the clone context for a template association."""
        self.template = template
        self.delta = delta
        # Maps (model class, source pk) to the pk of the cloned row
        self.id_map: dict[tuple[type, int], int] = {}
        # M2M assignments deferred until every row has been cloned
        self.deferred_m2m: list[tuple[Any, str, type, list[int]]] = []

    def mapped(self, model_class: type, source_pk: int | None) -> int | None:
        """Return the cloned pk for a source pk, or None when not cloned."""
        if source_pk is None:
            return None
        return self.id_map.get((model_class, source_pk))


def clone_association(demo_type: Any, new_slug: str, skin_id: int) -> Association:
    """Clone the whole data graph of a demo type's template association.

    Copies association, members, events, runs, registration setup, writing
    elements, registrations and accounting into a brand new association,
    shifting run dates so the first run starts one month from today and
    applying the same delta to registration and accounting timestamps.

    Args:
        demo_type: LarpManagerDemoType whose template association is cloned
        new_slug: Slug for the new demo association
        skin_id: Skin to assign to the new association

    Returns:
        The newly created demo Association.

    """
    template = demo_type.template_association
    clone_context = CloneContext(template, _compute_date_delta(template))

    with transaction.atomic(), clone_signals_suppressed():
        new_association = _clone_association_row(clone_context, demo_type, new_slug, skin_id)
        _clone_members(clone_context, new_association, new_slug)
        _clone_events(clone_context)
        _clone_registrations(clone_context)
        _clone_accounting(clone_context)
        _fix_deferred_self_references(clone_context)
        _apply_deferred_m2m(clone_context)

    clear_association_cache(new_slug)
    return new_association


def _compute_date_delta(template: Association) -> timedelta:
    """Compute the shift that puts the template's first run one month from today."""
    first_start = Run.objects.filter(event__association=template, start__isnull=False).aggregate(Min("start"))[
        "start__min"
    ]
    if not first_start:
        return timedelta(0)
    target_start = timezone.now().date() + relativedelta(months=1)
    return target_start - first_start


def _copy_row(clone_context: CloneContext, source_object: Any, overrides: dict | None = None) -> Any:
    """Clone a single model row, remapping FKs through the id map.

    Snapshots auto-created M2M relations for deferred assignment, resets
    unique generated fields (uuid, media_token, access_token), remaps every
    FK whose target has already been cloned, applies overrides and saves.
    """
    model_class = type(source_object)
    source_pk = source_object.pk

    _snapshot_m2m(clone_context, source_object)

    source_object.pk = None
    source_object.id = None
    source_object._state.adding = True  # noqa: SLF001

    _reset_generated_fields(source_object)

    # Remap FKs pointing to rows already cloned; unmapped FKs keep their value
    for field in source_object._meta.concrete_fields:  # noqa: SLF001
        if not field.is_relation:
            continue
        new_target_pk = clone_context.mapped(field.related_model, getattr(source_object, field.attname))
        if new_target_pk is not None:
            setattr(source_object, field.attname, new_target_pk)

    for field_name, field_value in (overrides or {}).items():
        setattr(source_object, field_name, field_value)

    source_object.save()
    clone_context.id_map[(model_class, source_pk)] = source_object.pk
    return source_object


def _snapshot_m2m(clone_context: CloneContext, source_object: Any) -> None:
    """Snapshot auto-created M2M relations of a source row for deferred assignment."""
    for m2m_field in source_object._meta.many_to_many:  # noqa: SLF001
        if not m2m_field.remote_field.through._meta.auto_created:  # noqa: SLF001
            continue
        if m2m_field.name in SKIPPED_M2M_FIELDS:
            continue
        target_ids = list(getattr(source_object, m2m_field.name).values_list("pk", flat=True))
        if target_ids:
            clone_context.deferred_m2m.append((source_object, m2m_field.name, m2m_field.related_model, target_ids))


def _reset_generated_fields(source_object: Any) -> None:
    """Reset generated unique fields so pre-save hooks regenerate them."""
    if hasattr(source_object, "uuid"):
        source_object.uuid = None
    if hasattr(source_object, "media_token"):
        source_object.media_token = ""
    if hasattr(source_object, "access_token"):
        source_object.access_token = my_uuid_short()


def _copy_all(
    clone_context: CloneContext, model_class: type, source_filter: dict, overrides_fn: Any = None
) -> list[Any]:
    """Clone every row of a model matching the given filter."""
    cloned_rows = []
    for source_object in model_class.objects.filter(**source_filter):
        overrides = overrides_fn(source_object) if overrides_fn else None
        cloned_rows.append(_copy_row(clone_context, source_object, overrides))
    return cloned_rows


def _clone_association_row(clone_context: CloneContext, demo_type: Any, new_slug: str, skin_id: int) -> Association:
    """Clone the association itself plus its configs, texts and M2M relations."""
    template = clone_context.template
    new_association = _copy_row(
        clone_context,
        Association.objects.get(pk=template.pk),
        overrides={
            "slug": new_slug,
            "skin_id": skin_id,
            "lite_mode": False,
            "demo_type": demo_type,
            "key": None,
            "css_code": "",
        },
    )

    # Association.save() auto-creates the "version" config, so upsert instead of blind copy
    for config_row in AssociationConfig.objects.filter(association=template):
        AssociationConfig.objects.update_or_create(
            association=new_association,
            name=config_row.name,
            defaults={"value": config_row.value},
        )

    _copy_all(clone_context, AssociationText, {"association": template})
    return new_association


def _clone_members(clone_context: CloneContext, new_association: Association, new_slug: str) -> None:
    """Duplicate every member of the template association with a fresh demo user."""
    memberships = Membership.objects.filter(association=clone_context.template).select_related("member")
    for member_index, membership_row in enumerate(memberships):
        template_member = membership_row.member
        demo_user = User.objects.create(
            username=f"{new_slug}-m{member_index}",
            email=f"{new_slug}-m{member_index}@demo.it",
            password=conf_settings.DEMO_PASSWORD,
        )
        # The User post-save hook auto-creates the Member profile
        cloned_member = demo_user.member
        for profile_field in ["name", "surname", "nickname", "pronoun", "gender", "language", "presentation", "diet"]:
            setattr(cloned_member, profile_field, getattr(template_member, profile_field))
        cloned_member.save()
        clone_context.id_map[(Member, template_member.pk)] = cloned_member.pk

        _copy_row(clone_context, membership_row, overrides={"association_id": new_association.pk})


def _clone_events(clone_context: CloneContext) -> None:
    """Clone events with their runs, registration setup and writing elements."""
    template_events = list(Event.objects.filter(association=clone_context.template).order_by("pk"))
    for template_event in template_events:
        event_pk = template_event.pk
        # Defer the campaign parent FK: the parent event may not be cloned yet
        _copy_row(clone_context, template_event, overrides={"parent_id": None, "css_code": ""})
        _clone_event_children(clone_context, event_pk)


def _clone_event_children(clone_context: CloneContext, event_pk: int) -> None:
    """Clone all event-scoped children of a single template event."""
    delta = clone_context.delta
    event_filter = {"event_id": event_pk}

    _copy_all(clone_context, ProgressStep, event_filter)
    _copy_all(clone_context, EventConfig, event_filter)
    _copy_all(clone_context, EventText, event_filter)
    _copy_all(clone_context, EventButton, event_filter)

    def run_overrides(source_run: Run) -> dict:
        overrides: dict[str, Any] = {"registration_secret": my_uuid_short()}
        if source_run.start:
            overrides["start"] = source_run.start + delta
        if source_run.end:
            overrides["end"] = source_run.end + delta
        return overrides

    _copy_all(clone_context, Run, event_filter, run_overrides)

    # Registration setup
    _copy_all(clone_context, RegistrationTicket, event_filter)
    _copy_all(clone_context, RegistrationSection, event_filter)
    _copy_all(clone_context, RegistrationQuestion, event_filter)
    _copy_all(clone_context, RegistrationOption, event_filter)
    _copy_all(clone_context, Discount, event_filter)
    _copy_all(clone_context, RegistrationQuota, event_filter)
    _copy_all(clone_context, RegistrationInstallment, event_filter)
    _copy_all(clone_context, RegistrationSurcharge, event_filter)

    # Writing setup and elements; character mirror FK is fixed in a later pass
    _copy_all(clone_context, WritingQuestion, event_filter)
    _copy_all(clone_context, WritingOption, event_filter)
    _copy_all(clone_context, PrologueType, event_filter)

    def character_overrides(source_character: Character) -> dict:  # noqa: ARG001
        return {"mirror_id": None}

    _copy_all(clone_context, Character, event_filter, character_overrides)
    _copy_all(clone_context, Faction, event_filter)
    _copy_all(clone_context, Plot, event_filter)
    _copy_all(clone_context, Prologue, event_filter)
    _copy_all(clone_context, SpeedLarp, event_filter)

    # Through models between writing elements
    for plot_rel in PlotCharacterRel.objects.filter(plot__event_id=event_pk):
        _copy_row(clone_context, plot_rel)
    for relationship_row in Relationship.objects.filter(source__event_id=event_pk):
        _copy_row(clone_context, relationship_row)

    _clone_writing_choices(clone_context, event_pk)
    _clone_experience(clone_context, event_pk)


def _clone_writing_choices(clone_context: CloneContext, event_pk: int) -> None:
    """Clone character/faction/plot/prologue option choices and free-text answers.

    ``element_id`` is a plain int, not a real FK, so it is remapped by hand via the
    model class its question applies to; rows whose target element was not cloned
    (e.g. quest/trait, not part of this clone graph) are skipped.
    """

    def remapped_element_id(source_row: Any) -> int | None:
        model_class = QuestionApplicable.get_applicable_inverse(source_row.question.applicable)
        return clone_context.mapped(model_class, source_row.element_id)

    for choice in WritingChoice.objects.filter(question__event_id=event_pk).select_related("question"):
        new_element_id = remapped_element_id(choice)
        if new_element_id is not None:
            _copy_row(clone_context, choice, overrides={"element_id": new_element_id})

    for answer in WritingAnswer.objects.filter(question__event_id=event_pk).select_related("question"):
        new_element_id = remapped_element_id(answer)
        if new_element_id is not None:
            _copy_row(clone_context, answer, overrides={"element_id": new_element_id})


def _clone_experience(clone_context: CloneContext, event_pk: int) -> None:
    """Clone the Experience feature graph: systems, ability types, abilities and their rules."""
    event_filter = {"event_id": event_pk}
    _copy_all(clone_context, SystemExp, event_filter)
    _copy_all(clone_context, AbilityTypeExp, event_filter)
    _copy_all(clone_context, AbilityExp, event_filter)
    _copy_all(clone_context, ModifierExp, event_filter)
    _copy_all(clone_context, CriterionExp, event_filter)
    _copy_all(clone_context, RuleExp, event_filter)
    _copy_all(clone_context, DeliveryExp, event_filter)


def _clone_registrations(clone_context: CloneContext) -> None:
    """Clone registrations with their choices, answers and character assignments."""
    delta = clone_context.delta
    registration_filter = {"run__event__association": clone_context.template}

    def registration_overrides(source_registration: Registration) -> dict:
        return {"created": source_registration.created + delta}

    _copy_all(clone_context, Registration, registration_filter, registration_overrides)
    _copy_all(clone_context, RegistrationChoice, {"registration__run__event__association": clone_context.template})
    _copy_all(clone_context, RegistrationAnswer, {"registration__run__event__association": clone_context.template})
    _copy_all(
        clone_context, RegistrationCharacterRel, {"registration__run__event__association": clone_context.template}
    )


def _clone_accounting(clone_context: CloneContext) -> None:
    """Clone payment invoices and accounting items, shifting their timestamps."""
    delta = clone_context.delta
    template = clone_context.template

    def invoice_overrides(source_invoice: PaymentInvoice) -> dict:
        return {"cod": my_uuid(), "created": source_invoice.created + delta}

    _copy_all(clone_context, PaymentInvoice, {"association": template}, invoice_overrides)

    def item_overrides(source_item: Any) -> dict:
        return {"created": source_item.created + delta}

    for accounting_class in [
        AccountingItemPayment,
        AccountingItemTransaction,
        AccountingItemOther,
        AccountingItemDiscount,
    ]:
        _copy_all(clone_context, accounting_class, {"association": template}, item_overrides)


def _fix_deferred_self_references(clone_context: CloneContext) -> None:
    """Second pass fixing self-referential FKs (event parent, character mirror)."""
    for template_event in Event.objects.filter(association=clone_context.template, parent__isnull=False):
        new_event_pk = clone_context.mapped(Event, template_event.pk)
        new_parent_pk = clone_context.mapped(Event, template_event.parent_id)
        if new_event_pk and new_parent_pk:
            Event.objects.filter(pk=new_event_pk).update(parent_id=new_parent_pk)

    for template_character in Character.objects.filter(event__association=clone_context.template, mirror__isnull=False):
        new_character_pk = clone_context.mapped(Character, template_character.pk)
        new_mirror_pk = clone_context.mapped(Character, template_character.mirror_id)
        if new_character_pk and new_mirror_pk:
            Character.objects.filter(pk=new_character_pk).update(mirror_id=new_mirror_pk)


def _apply_deferred_m2m(clone_context: CloneContext) -> None:
    """Apply the snapshotted M2M relations, remapping cloned targets."""
    for cloned_object, field_name, target_model, source_target_ids in clone_context.deferred_m2m:
        new_target_ids = []
        for source_target_id in source_target_ids:
            mapped_pk = clone_context.mapped(target_model, source_target_id)
            new_target_ids.append(mapped_pk if mapped_pk is not None else source_target_id)
        getattr(cloned_object, field_name).set(new_target_ids)


def add_demo_hint_context(request: Any, context: dict) -> None:
    """Add the contextual demo hint for the current view to the context.

    The hint is looked up by view name and demo type (hints without a demo
    type apply to every demo). Dismissals and the session guided flag only
    control whether the panel starts open; the toggle button stays available
    whenever a hint exists for the view.
    """
    hint = (
        LarpManagerDemoHint.objects.filter(active=True, view_name=context.get("request_func_name"))
        .filter(Q(demo_type_id=context.get("demo_type")) | Q(demo_type__isnull=True))
        .order_by("order", "pk")
        .first()
    )
    context["demo_hint"] = hint
    if not hint:
        return

    dismissed = False
    if context.get("member"):
        dismissed = LarpManagerDemoHintDismissal.objects.filter(member=context["member"], hint=hint).exists()
    guided = request.session.get("demo_guided", True)
    context["demo_hint_open"] = guided and not dismissed


@background(queue="demo")
def deferred_delete_demo(association_id: int) -> None:
    """Delete a demo association once its lifetime has expired."""
    try:
        demo_association = Association.objects.get(pk=association_id)
    except Association.DoesNotExist:
        return
    if demo_association.demo_type_id is None:
        return
    demo_association.delete()
    clear_association_cache(demo_association.slug)


def schedule_demo_cleanup(association: Association) -> None:
    """Schedule the deferred deletion of a freshly created demo association."""
    deferred_delete_demo(association.pk, schedule=DEMO_LIFETIME_SECONDS)
