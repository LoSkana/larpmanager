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
import logging
from datetime import date

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Max, Q
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _
from slugify import slugify

from larpmanager.accounting.vat import compute_vat
from larpmanager.cache.button import event_button_key
from larpmanager.cache.config import reset_configs
from larpmanager.cache.feature import get_event_features, reset_event_features
from larpmanager.cache.fields import reset_event_fields_cache
from larpmanager.mail.base import mail_larpmanager_ticket
from larpmanager.models.access import AssocPermission, EventPermission, EventRole, get_event_organizers
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemPayment,
    AccountingItemTransaction,
    Collection,
)
from larpmanager.models.association import Association, AssociationConfig
from larpmanager.models.casting import Trait, update_traits_all
from larpmanager.models.event import Event, EventButton, EventConfig, EventText, Run, RunConfig
from larpmanager.models.experience import AbilityPx, DeliveryPx, ModifierPx, RulePx
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    QuestionVisibility,
    RegistrationQuestion,
    RegistrationQuestionType,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.larpmanager import LarpManagerFaq, LarpManagerGuide, LarpManagerTicket, LarpManagerTutorial
from larpmanager.models.member import Member, MemberConfig, Membership, MembershipStatus
from larpmanager.models.miscellanea import WarehouseItem
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, CharacterConfig, Faction, Plot, Prologue, SpeedLarp, replace_chars_all
from larpmanager.utils.common import copy_class
from larpmanager.utils.experience import (
    modifier_abilities_changed,
    px_characters_changed,
    rule_abilities_changed,
    update_px,
)
from larpmanager.utils.miscellanea import rotate_vertical_photo
from larpmanager.utils.registration import save_registration_character_form
from larpmanager.utils.tutorial_query import delete_index_guide, delete_index_tutorial, index_guide, index_tutorial

log = logging.getLogger(__name__)


def auto_populate_number_order_fields(instance):
    """Auto-populate number and order fields for model instances.

    Args:
        instance: Model instance to populate fields for
    """
    for field in ["number", "order"]:
        if hasattr(instance, field) and not getattr(instance, field):
            que = None
            if hasattr(instance, "event") and instance.event:
                que = instance.__class__.objects.filter(event=instance.event)
            if hasattr(instance, "assoc") and instance.assoc:
                que = instance.__class__.objects.filter(assoc=instance.assoc)
            if hasattr(instance, "character") and instance.character:
                que = instance.__class__.objects.filter(character=instance.character)
            if que is not None:
                n = que.aggregate(Max(field))[f"{field}__max"]
                if not n:
                    setattr(instance, field, 1)
                else:
                    setattr(instance, field, n + 1)


def update_search_field(instance):
    """Update search field for model instances that have one.

    Args:
        instance: Model instance to update search field for
    """
    if hasattr(instance, "search"):
        instance.search = None
        instance.search = str(instance)


@receiver(pre_save)
def pre_save_callback(sender, instance, *args, **kwargs):
    """Generic pre-save handler for automatic field population.

    Automatically sets number/order fields and updates search fields
    for models that have them.

    Args:
        sender: Model class sending the signal
        instance: Model instance being saved
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments
    """
    auto_populate_number_order_fields(instance)
    update_search_field(instance)


def handle_association_fernet_key_generation(instance):
    """Generate Fernet encryption key for new associations.

    Args:
        instance: Association instance being saved
    """
    if not instance.key:
        instance.key = Fernet.generate_key()


@receiver(pre_save, sender=Association)
def pre_save_association_generate_fernet(sender, instance, **kwargs):
    handle_association_fernet_key_generation(instance)


def assign_assoc_permission_number(assoc_permission):
    """Assign number to association permission if not set.

    Args:
        assoc_permission: AssocPermission instance to assign number to
    """
    if not assoc_permission.number:
        n = AssocPermission.objects.filter(feature__module=assoc_permission.feature.module).aggregate(Max("number"))[
            "number__max"
        ]
        if not n:
            n = 1
        assoc_permission.number = n + 10


@receiver(pre_save, sender=AssocPermission)
def pre_save_assoc_permission(sender, instance, **kwargs):
    assign_assoc_permission_number(instance)


def assign_event_permission_number(event_permission):
    """Assign number to event permission if not set.

    Args:
        event_permission: EventPermission instance to assign number to
    """
    if not event_permission.number:
        n = EventPermission.objects.filter(feature__module=event_permission.feature.module).aggregate(Max("number"))[
            "number__max"
        ]
        if not n:
            n = 1
        event_permission.number = n + 10


@receiver(pre_save, sender=EventPermission)
def pre_save_event_permission(sender, instance, **kwargs):
    assign_event_permission_number(instance)


@receiver(pre_save, sender=Plot)
def pre_save_plot(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(pre_save, sender=Faction)
def pre_save_faction(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(pre_save, sender=Prologue)
def pre_save_prologue(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


def handle_run_post_save(instance):
    """Set run plan from association default if not already set.

    Args:
        instance: Run instance that was saved
    """
    if not instance.plan and instance.event:
        updates = {"plan": instance.event.assoc.plan}
        Run.objects.filter(pk=instance.pk).update(**updates)


@receiver(post_save, sender=Run)
def save_run_plan(sender, instance, **kwargs):
    handle_run_post_save(instance)


@receiver(post_save, sender=Trait)
def update_trait(sender, instance, **kwargs):
    update_traits_all(instance)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_accounting_item_payment_updatereg(sender, instance, created, **kwargs):
    instance.reg.save()


def handle_accounting_item_payment_pre_save(instance):
    """Update payment member and handle registration changes.

    Args:
        instance: AccountingItemPayment instance being saved
    """
    if not instance.member:
        instance.member = instance.reg.member

    if not instance.pk:
        return

    prev = AccountingItemPayment.objects.get(pk=instance.pk)
    instance._update_reg = prev.value != instance.value

    if prev.reg != instance.reg:
        for trans in AccountingItemTransaction.objects.filter(inv_id=instance.inv_id):
            trans.reg = instance.reg
            trans.save()


@receiver(pre_save, sender=AccountingItemPayment)
def update_accounting_item_payment_member(sender, instance, **kwargs):
    handle_accounting_item_payment_pre_save(instance)


def handle_collection_pre_save(instance):
    """Generate unique codes and calculate collection totals.

    Args:
        instance: Collection instance being saved
    """
    if not instance.pk:
        instance.unique_contribute_code()
        instance.unique_redeem_code()
        return
    instance.total = 0
    for el in instance.collection_gifts.all():
        instance.total += el.value


@receiver(pre_save, sender=Collection)
def pre_save_collection(sender, instance, **kwargs):
    handle_collection_pre_save(instance)


def handle_accounting_item_collection_post_save(instance):
    """Update collection total when items are added.

    Args:
        instance: AccountingItemCollection instance that was saved
    """
    if instance.collection:
        instance.collection.save()


@receiver(post_save, sender=AccountingItemCollection)
def post_save_accounting_item_collection(sender, instance, created, **kwargs):
    handle_accounting_item_collection_post_save(instance)


@receiver(pre_save, sender=SpeedLarp)
def pre_save_speed_larp(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


def handle_tutorial_slug_generation(instance):
    """Generate slug for tutorial if not already set.

    Args:
        instance: LarpManagerTutorial instance being saved
    """
    if not instance.slug:
        instance.slug = slugify(instance.name)


@receiver(pre_save, sender=LarpManagerTutorial)
def pre_save_larp_manager_tutorial(sender, instance, *args, **kwargs):
    handle_tutorial_slug_generation(instance)


def assign_faq_number(faq):
    """Assign number to FAQ if not already set.

    Args:
        faq: LarpManagerFaq instance to assign number to
    """
    if faq.number:
        return
    n = LarpManagerFaq.objects.filter(typ=faq.typ).aggregate(Max("number"))["number__max"]
    if not n:
        n = 1
    else:
        n = ((n / 10) + 1) * 10
    faq.number = n


@receiver(pre_save, sender=LarpManagerFaq)
def pre_save_larp_manager_faq(sender, instance, *args, **kwargs):
    assign_faq_number(instance)


def handle_user_profile_creation(user, created):
    """Create member profile and sync email when user is saved.

    Args:
        user: User instance that was saved
        created: Whether this is a new user
    """
    if created:
        Member.objects.create(user=user)
    user.member.email = user.email
    user.member.save()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    handle_user_profile_creation(instance, created)


def handle_membership_status_changes(membership):
    """Handle membership status changes and card numbering.

    Args:
        membership: Membership instance being saved
    """
    if membership.status == MembershipStatus.ACCEPTED:
        if not membership.card_number:
            n = Membership.objects.filter(assoc=membership.assoc).aggregate(Max("card_number"))["card_number__max"]
            if not n:
                n = 0
            membership.card_number = n + 1
        if not membership.date:
            membership.date = date.today()

    if membership.status == MembershipStatus.EMPTY:
        if membership.card_number:
            membership.card_number = None
        if membership.date:
            membership.date = None


@receiver(pre_save, sender=Membership)
def pre_save_membership(sender, instance, **kwargs):
    handle_membership_status_changes(instance)


@receiver(post_save, sender=EventButton)
def save_event_button(sender, instance, created, **kwargs):
    reset_event_button(instance)


@receiver(pre_delete, sender=EventButton)
def delete_event_button(sender, instance, **kwargs):
    reset_event_button(instance)


def reset_event_button(instance):
    cache.delete(event_button_key(instance.event_id))


def handle_event_pre_save_prepare_campaign(instance):
    """Prepare campaign event data before saving.

    Args:
        instance: Event instance being saved
    """
    if instance.pk:
        try:
            old_instance = Event.objects.get(pk=instance.pk)
            instance._old_parent_id = old_instance.parent_id
        except ObjectDoesNotExist:
            instance._old_parent_id = None
    else:
        instance._old_parent_id = None


@receiver(pre_save, sender=Event)
def pre_save_event_prepare_campaign(sender, instance, **kwargs):
    handle_event_pre_save_prepare_campaign(instance)


def setup_campaign_event(event):
    """Setup campaign event by copying from parent.

    Args:
        event: Event instance that was saved
    """
    if event.parent_id:
        # noinspection PyProtectedMember
        if event._old_parent_id != event.parent_id:
            # copy config, texts, roles, features
            copy_class(event.pk, event.parent_id, EventConfig)
            copy_class(event.pk, event.parent_id, EventText)
            copy_class(event.pk, event.parent_id, EventRole)
            for fn in event.parent.features.all():
                event.features.add(fn)

            # Temporarily disconnect signal
            post_save.disconnect(post_save_event_campaign, sender=Event)
            event.save()
            post_save.connect(post_save_event_campaign, sender=Event)


@receiver(post_save, sender=Event)
def post_save_event_campaign(sender, instance, **kwargs):
    setup_campaign_event(instance)


def setup_event_after_save(event):
    """Setup event with runs, tickets, and forms after save.

    Args:
        event: Event instance that was saved
    """
    if event.template:
        return

    if event.runs.count() == 0:
        Run.objects.create(event=event, number=1)

    features = get_event_features(event.id)

    save_event_tickets(features, event)

    save_event_registration_form(features, event)

    save_event_character_form(features, event)

    reset_event_features(event.id)

    reset_event_fields_cache(event.id)


@receiver(post_save, sender=Event)
def save_event_update(sender, instance, **kwargs):
    setup_event_after_save(instance)


def save_event_tickets(features, instance):
    """Create default registration tickets for event.

    Args:
        features (dict): Enabled features for the event
        instance: Event instance to create tickets for
    """
    # create tickets if not exists
    tickets = [
        ("", TicketTier.STANDARD, "Standard"),
        ("waiting", TicketTier.WAITING, "Waiting"),
        ("filler", TicketTier.FILLER, "Filler"),
    ]
    for ticket in tickets:
        if ticket[0] and ticket[0] not in features:
            continue
        if RegistrationTicket.objects.filter(event=instance, tier=ticket[1]).count() == 0:
            RegistrationTicket.objects.create(event=instance, tier=ticket[1], name=ticket[2])


def save_event_character_form(features, instance):
    """Create character form questions based on enabled features.

    Args:
        features (dict): Enabled features for the event
        instance: Event instance to create form for
    """
    # create fields if not exists / delete if feature not active
    if "character" not in features:
        return

    # if has parent, use those
    if instance.parent:
        return

    _activate_orga_lang(instance)

    def_tps = {
        WritingQuestionType.NAME: ("Name", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 100),
        WritingQuestionType.TEASER: ("Presentation", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 3000),
        WritingQuestionType.SHEET: ("Text", QuestionStatus.MANDATORY, QuestionVisibility.PRIVATE, 5000),
    }

    custom_tps = BaseQuestionType.get_basic_types()

    _init_character_form_questions(custom_tps, def_tps, features, instance)

    if "questbuilder" in features:
        _init_writing_element(instance, def_tps, [QuestionApplicable.QUEST, QuestionApplicable.TRAIT])

    if "prologue" in features:
        _init_writing_element(instance, def_tps, [QuestionApplicable.PROLOGUE])

    if "faction" in features:
        _init_writing_element(instance, def_tps, [QuestionApplicable.FACTION])

    if "plot" in features:
        plot_tps = dict(def_tps)
        plot_tps[WritingQuestionType.TEASER] = (
            "Concept",
            QuestionStatus.MANDATORY,
            QuestionVisibility.PUBLIC,
            3000,
        )
        _init_writing_element(instance, plot_tps, [QuestionApplicable.PLOT])


def _init_writing_element(instance, def_tps, applicables):
    """Initialize writing questions for specific applicables in an event instance.

    Args:
        instance: Event instance to initialize writing elements for
        def_tps: Dictionary of default question types and their configurations
        applicables: List of QuestionApplicable types to create questions for
    """
    for applicable in applicables:
        # if there are already questions for this applicable, skip
        if instance.get_elements(WritingQuestion).filter(applicable=applicable).exists():
            continue

        objs = [
            WritingQuestion(
                event=instance,
                typ=typ,
                name=_(cfg[0]),
                status=cfg[1],
                visibility=cfg[2],
                max_length=cfg[3],
                applicable=applicable,
            )
            for typ, cfg in def_tps.items()
        ]
        WritingQuestion.objects.bulk_create(objs)


def _init_character_form_questions(custom_tps, def_tps, features, instance):
    """Initialize character form questions during model setup.

    Sets up default and custom question types for character creation forms,
    managing question creation and deletion based on enabled features and
    existing question configurations.
    """
    que = instance.get_elements(WritingQuestion).filter(applicable=QuestionApplicable.CHARACTER)
    types = set(que.values_list("typ", flat=True).distinct())

    # evaluate each question type field
    choices = dict(WritingQuestionType.choices)
    all_types = choices.keys()
    all_types -= custom_tps

    # add default types if none are present
    if not types:
        for el, add in def_tps.items():
            WritingQuestion.objects.create(
                event=instance,
                typ=el,
                name=_(add[0]),
                status=add[1],
                visibility=add[2],
                max_length=add[3],
                applicable=QuestionApplicable.CHARACTER,
            )

    # add types from feature if the feature is active but the field is missing
    not_to_remove = set(def_tps.keys())
    if "px" in features:
        not_to_remove.add(WritingQuestionType.COMPUTED)
    all_types -= not_to_remove
    for el in sorted(list(all_types)):
        if el in features and el not in types:
            WritingQuestion.objects.create(
                event=instance,
                typ=el,
                name=_(el.capitalize()),
                status=QuestionStatus.HIDDEN,
                visibility=QuestionVisibility.HIDDEN,
                max_length=1000,
                applicable=QuestionApplicable.CHARACTER,
            )
        if el not in features and el in types:
            WritingQuestion.objects.filter(event=instance, typ=el).delete()


def save_event_registration_form(features, instance):
    """Create registration form questions based on enabled features.

    Args:
        features (dict): Enabled features for the event
        instance: Event instance to create form for
    """
    _activate_orga_lang(instance)

    def_tps = {RegistrationQuestionType.TICKET}

    help_texts = {
        RegistrationQuestionType.TICKET: _("Your registration ticket"),
    }

    basic_tps = BaseQuestionType.get_basic_types()

    que = instance.get_elements(RegistrationQuestion)
    types = set(que.values_list("typ", flat=True).distinct())

    # evaluate each question type field
    choices = dict(RegistrationQuestionType.choices)
    all_types = choices.keys()
    all_types -= basic_tps

    # add default types if none are present
    for el in def_tps:
        if el not in types:
            RegistrationQuestion.objects.create(
                event=instance,
                typ=el,
                name=choices[el],
                description=help_texts.get(el, ""),
                status=QuestionStatus.MANDATORY,
            )

    # add types from feature if the feature is active but the field is missing
    not_to_remove = set(def_tps)
    all_types -= not_to_remove

    help_texts = {
        "additional_tickets": _("Reserve additional tickets beyond your own"),
        "pay_what_you_want": _("Freely indicate the amount of your donation"),
        "reg_surcharges": _("Registration surcharge"),
        "reg_quotas": _(
            "Number of installments to split the fee: payments and deadlines will be equally divided from the registration date"
        ),
    }

    for el in sorted(list(all_types)):
        if el in features and el not in types:
            RegistrationQuestion.objects.create(
                event=instance,
                typ=el,
                name=_(choices[el].capitalize()),
                description=help_texts.get(el, ""),
                status=QuestionStatus.OPTIONAL,
            )
        if el not in features and el in types:
            RegistrationQuestion.objects.filter(event=instance, typ=el).delete()


def _activate_orga_lang(instance):
    # get most common language between organizers
    langs = {}
    for orga in get_event_organizers(instance):
        lang = orga.language
        if lang not in langs:
            langs[lang] = 1
        else:
            langs[lang] += 1
    if langs:
        max_lang = max(langs, key=langs.get)
    else:
        max_lang = "en"
    activate(max_lang)


def auto_assign_campaign_character(registration):
    """Auto-assign last character for campaign registrations.

    Args:
        registration: Registration instance to assign character to
    """
    if not registration.member:
        return

    if registration.cancellation_date:
        return

    # auto assign last character if campaign
    if "campaign" not in get_event_features(registration.run.event_id):
        return
    if not registration.run.event.parent:
        return

    # if already has a character, do not proceed
    if RegistrationCharacterRel.objects.filter(reg__run=registration.run).count() > 0:
        return

    # get last run of campaign
    last = (
        Run.objects.filter(
            Q(event__parent=registration.run.event.parent) | Q(event_id=registration.run.event.parent_id)
        )
        .exclude(event_id=registration.run.event_id)
        .order_by("-end")
        .first()
    )
    if not last:
        return

    try:
        old_rcr = RegistrationCharacterRel.objects.get(reg__member=registration.member, reg__run=last)
        rcr = RegistrationCharacterRel.objects.create(reg=registration, character=old_rcr.character)
        for s in ["name", "pronoun", "song", "public", "private"]:
            if hasattr(old_rcr, "custom_" + s):
                value = getattr(old_rcr, "custom_" + s)
                setattr(rcr, "custom_" + s, value)
        rcr.save()
    except ObjectDoesNotExist:
        pass


@receiver(post_save, sender=Registration)
def post_save_registration_campaign(sender, instance, **kwargs):
    auto_assign_campaign_character(instance)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_accounting_item_payment_vat(sender, instance, created, **kwargs):
    compute_vat(instance)


@receiver(post_save, sender=EventConfig)
def post_save_reset_event_config(sender, instance, **kwargs):
    reset_configs(instance.event)


@receiver(post_delete, sender=EventConfig)
def post_delete_reset_event_config(sender, instance, **kwargs):
    reset_configs(instance.event)


@receiver(post_save, sender=AssociationConfig)
def post_save_reset_assoc_config(sender, instance, **kwargs):
    reset_configs(instance.assoc)


@receiver(post_delete, sender=AssociationConfig)
def post_delete_reset_assoc_config(sender, instance, **kwargs):
    reset_configs(instance.assoc)


@receiver(post_save, sender=RunConfig)
def post_save_reset_run_config(sender, instance, **kwargs):
    reset_configs(instance.run)


@receiver(post_delete, sender=RunConfig)
def post_delete_reset_run_config(sender, instance, **kwargs):
    reset_configs(instance.run)


@receiver(post_save, sender=MemberConfig)
def post_save_reset_member_config(sender, instance, **kwargs):
    reset_configs(instance.member)


@receiver(post_delete, sender=MemberConfig)
def post_delete_reset_member_config(sender, instance, **kwargs):
    reset_configs(instance.member)


@receiver(post_save, sender=CharacterConfig)
def post_save_reset_character_config(sender, instance, **kwargs):
    reset_configs(instance.character)


@receiver(post_delete, sender=CharacterConfig)
def post_delete_reset_character_config(sender, instance, **kwargs):
    reset_configs(instance.character)


def handle_association_skin_features_pre_save(instance):
    """Handle association skin feature setup before saving.

    Args:
        instance: Association instance being saved
    """
    if not instance.skin:
        return

    # execute if new association, or if changed skin
    if instance.pk:
        try:
            prev = Association.objects.get(pk=instance.pk)
        except ObjectDoesNotExist:
            return
        if instance.skin == prev.skin:
            return

    instance._update_skin_features = True
    if not instance.nationality:
        instance.nationality = instance.skin.default_nation

    if not instance.optional_fields:
        instance.optional_fields = instance.skin.default_optional_fields

    if not instance.mandatory_fields:
        instance.mandatory_fields = instance.skin.default_mandatory_fields


@receiver(pre_save, sender=Association)
def pre_save_association_set_skin_features(sender, instance, **kwargs):
    handle_association_skin_features_pre_save(instance)


def handle_association_skin_features_post_save(instance):
    """Handle association skin feature setup after saving.

    Args:
        instance: Association instance that was saved
    """
    if not hasattr(instance, "_update_skin_features"):
        return

    def update_features():
        instance.features.set(instance.skin.default_features.all())

    transaction.on_commit(update_features)


@receiver(post_save, sender=Association)
def post_save_association_set_skin_features(sender, instance, created, **kwargs):
    handle_association_skin_features_post_save(instance)


@receiver(post_save, sender=LarpManagerTutorial)
def post_save_index_tutorial(sender, instance, **kwargs):
    index_tutorial(instance.id)


@receiver(post_delete, sender=LarpManagerTutorial)
def delete_tutorial_from_index(sender, instance, **kwargs):
    delete_index_tutorial(instance.id)


@receiver(post_save, sender=LarpManagerGuide)
def post_save_index_guide(sender, instance, **kwargs):
    index_guide(instance.id)


@receiver(post_delete, sender=LarpManagerGuide)
def delete_guide_from_index(sender, instance, **kwargs):
    delete_index_guide(instance.id)


@receiver(post_save, sender=WritingQuestion)
def save_event_field(sender, instance, created, **kwargs):
    reset_event_fields_cache(instance.event_id)


@receiver(pre_delete, sender=WritingQuestion)
def delete_event_field(sender, instance, **kwargs):
    reset_event_fields_cache(instance.event_id)


# Miscellanea


@receiver(pre_save, sender=WarehouseItem, dispatch_uid="warehouseitem_rotate_vertical_photo")
def pre_save_warehouse_item(sender, instance: WarehouseItem, **kwargs):
    rotate_vertical_photo(instance, sender)


@receiver(post_save, sender=Registration)
def post_save_registration_character_form(sender, instance, **kwargs):
    save_registration_character_form(instance)


# Experience


@receiver(post_save, sender=Character, dispatch_uid="post_character_update_px_v1")
def post_character_update_px(sender, instance, *args, **kwargs):
    update_px(instance)


@receiver(post_save, sender=AbilityPx)
def post_save_ability_px(sender, instance, *args, **kwargs):
    handle_ability_save(instance)


def handle_ability_save(instance):
    for char in instance.characters.all():
        update_px(char)


@receiver(post_save, sender=DeliveryPx)
def post_save_delivery_px(sender, instance, *args, **kwargs):
    handle_delivery_save(instance)


def handle_delivery_save(instance):
    for char in instance.characters.all():
        char.save()


@receiver(post_save, sender=RulePx)
def post_save_rule_px(sender, instance, *args, **kwargs):
    handle_rule_save(instance)


def handle_rule_save(instance):
    event = instance.event.get_class_parent(RulePx)
    for char in event.get_elements(Character).all():
        update_px(char)


@receiver(post_save, sender=ModifierPx)
def post_save_modifier_px(sender, instance, *args, **kwargs):
    handle_modifier_save(instance)


def handle_modifier_save(instance):
    event = instance.event.get_class_parent(ModifierPx)
    for char in event.get_elements(Character).all():
        update_px(char)


m2m_changed.connect(px_characters_changed, sender=DeliveryPx.characters.through)
m2m_changed.connect(px_characters_changed, sender=AbilityPx.characters.through)

m2m_changed.connect(modifier_abilities_changed, sender=ModifierPx.abilities.through)
m2m_changed.connect(rule_abilities_changed, sender=RulePx.abilities.through)

# LarpManager


@receiver(post_save, sender=LarpManagerTicket)
def save_larpmanager_ticket(sender, instance, created, **kwargs):
    mail_larpmanager_ticket(instance)
