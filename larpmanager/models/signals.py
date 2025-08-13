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

from datetime import date

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Max, Q
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _
from slugify import slugify

from larpmanager.accounting.vat import compute_vat
from larpmanager.cache.button import event_button_key
from larpmanager.cache.config import reset_configs
from larpmanager.cache.feature import get_assoc_features, get_event_features, reset_event_features
from larpmanager.cache.fields import reset_event_fields_cache
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
from larpmanager.models.form import (
    QuestionApplicable,
    QuestionStatus,
    QuestionType,
    QuestionVisibility,
    WritingQuestion,
)
from larpmanager.models.larpmanager import LarpManagerFaq, LarpManagerTutorial
from larpmanager.models.member import Member, MemberConfig, Membership, MembershipStatus
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Faction, Plot, Prologue, SpeedLarp, replace_chars_all
from larpmanager.utils.common import copy_class
from larpmanager.utils.tutorial_query import delete_index, index_tutorial


@receiver(pre_save)
def pre_save_callback(sender, instance, *args, **kwargs):
    for field in ["number", "order"]:
        if hasattr(instance, field) and not getattr(instance, field):
            que = None
            if hasattr(instance, "event") and instance.event:
                que = instance.__class__.objects.filter(event=instance.event)
            if hasattr(instance, "assoc") and instance.assoc:
                que = instance.__class__.objects.filter(assoc=instance.assoc)
            if que is not None:
                n = que.aggregate(Max(field))[f"{field}__max"]
                if not n:
                    setattr(instance, field, 1)
                else:
                    setattr(instance, field, n + 1)

    if hasattr(instance, "search"):
        instance.search = None
        instance.search = str(instance)


@receiver(pre_save, sender=Association)
def pre_save_association_generate_fernet(sender, instance, **kwargs):
    if not instance.key:
        instance.key = Fernet.generate_key()


@receiver(pre_save, sender=AssocPermission)
def pre_save_assoc_permission(sender, instance, **kwargs):
    if not instance.number:
        n = AssocPermission.objects.filter(feature__module=instance.feature.module).aggregate(Max("number"))[
            "number__max"
        ]
        if not n:
            n = 1
        instance.number = n + 10


@receiver(pre_save, sender=EventPermission)
def pre_save_event_permission(sender, instance, **kwargs):
    if not instance.number:
        n = EventPermission.objects.filter(feature__module=instance.feature.module).aggregate(Max("number"))[
            "number__max"
        ]
        if not n:
            n = 1
        instance.number = n + 10


@receiver(pre_save, sender=Plot)
def pre_save_plot(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(pre_save, sender=Faction)
def pre_save_faction(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(pre_save, sender=Prologue)
def pre_save_prologue(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(post_save, sender=Run)
def save_run_plan(sender, instance, **kwargs):
    if not instance.plan and instance.event:
        updates = {"plan": instance.event.assoc.plan}
        Run.objects.filter(pk=instance.pk).update(**updates)


@receiver(post_save, sender=Trait)
def update_trait(sender, instance, **kwargs):
    update_traits_all(instance)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_accounting_item_payment_updatereg(sender, instance, created, **kwargs):
    instance.reg.save()


@receiver(pre_save, sender=AccountingItemPayment)
def update_accounting_item_payment_member(sender, instance, **kwargs):
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


@receiver(pre_save, sender=Collection)
def pre_save_collection(sender, instance, **kwargs):
    if not instance.pk:
        instance.unique_contribute_code()
        instance.unique_redeem_code()
        return
    instance.total = 0
    for el in instance.collection_gifts.all():
        instance.total += el.value


@receiver(post_save, sender=AccountingItemCollection)
def post_save_accounting_item_collection(sender, instance, created, **kwargs):
    if instance.collection:
        instance.collection.save()


@receiver(pre_save, sender=SpeedLarp)
def pre_save_speed_larp(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(pre_save, sender=LarpManagerTutorial)
def pre_save_larp_manager_tutorial(sender, instance, *args, **kwargs):
    if not instance.slug:
        instance.slug = slugify(instance.name)


@receiver(pre_save, sender=LarpManagerFaq)
def pre_save_larp_manager_faq(sender, instance, *args, **kwargs):
    if instance.number:
        return
    n = LarpManagerFaq.objects.filter(typ=instance.typ).aggregate(Max("number"))["number__max"]
    if not n:
        n = 1
    else:
        n = ((n / 10) + 1) * 10
    instance.number = n


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Member.objects.create(user=instance)
    instance.member.email = instance.email
    instance.member.save()


@receiver(pre_save, sender=Membership)
def pre_save_membership(sender, instance, **kwargs):
    if instance.status == MembershipStatus.ACCEPTED:
        if not instance.card_number:
            n = Membership.objects.filter(assoc=instance.assoc).aggregate(Max("card_number"))["card_number__max"]
            if not n:
                n = 0
            instance.card_number = n + 1
        if not instance.date:
            instance.date = date.today()

    if instance.status == MembershipStatus.EMPTY:
        if instance.card_number:
            instance.card_number = None
        if instance.date:
            instance.date = None


@receiver(post_save, sender=EventButton)
def save_event_button(sender, instance, created, **kwargs):
    cache.delete(event_button_key(instance.event_id))


@receiver(pre_delete, sender=EventButton)
def delete_event_button(sender, instance, **kwargs):
    cache.delete(event_button_key(instance.event_id))


@receiver(pre_save, sender=Event)
def pre_save_event_prepare_campaign(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Event.objects.get(pk=instance.pk)
            instance._old_parent_id = old_instance.parent_id
        except ObjectDoesNotExist:
            instance._old_parent_id = None
    else:
        instance._old_parent_id = None


@receiver(post_save, sender=Event)
def post_save_event_campaign(sender, instance, **kwargs):
    if instance.parent_id:
        # noinspection PyProtectedMember
        if instance._old_parent_id != instance.parent_id:
            # copy config, texts, roles, features
            copy_class(instance.pk, instance.parent_id, EventConfig)
            copy_class(instance.pk, instance.parent_id, EventText)
            copy_class(instance.pk, instance.parent_id, EventRole)
            for fn in instance.parent.features.all():
                instance.features.add(fn)

            # Temporarily disconnect signal
            post_save.disconnect(post_save_event_campaign, sender=Event)
            instance.save()
            post_save.connect(post_save_event_campaign, sender=Event)


@receiver(post_save, sender=Event)
def save_event_update(sender, instance, **kwargs):
    if instance.template:
        return

    if instance.runs.count() == 0:
        Run.objects.create(event=instance, number=1)

    features = get_event_features(instance.id)

    save_event_tickets(features, instance)

    save_event_character_form(features, instance)

    reset_event_features(instance.id)

    reset_event_fields_cache(instance.id)


def save_event_tickets(features, instance):
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
    # create fields if not exists / delete if feature not active
    if "character" not in features:
        return

    # if has parent, use those
    if instance.parent:
        return

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

    def_tps = {
        QuestionType.NAME: ("Name", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 100),
        QuestionType.TEASER: ("Presentation", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 3000),
        QuestionType.SHEET: ("Text", QuestionStatus.MANDATORY, QuestionVisibility.PRIVATE, 5000),
    }

    custom_tps = QuestionType.get_basic_types()

    _init_character_form_questions(custom_tps, def_tps, features, instance)
    _init_faction_form_questions(def_tps, instance, features)
    _init_questbuilder_form_questions(def_tps, instance, features)
    _init_plot_form_questions(def_tps, instance, features)


def _init_questbuilder_form_questions(def_tps, instance, features):
    if "questbuilder" not in features:
        return

    for applicable in [QuestionApplicable.QUEST, QuestionApplicable.TRAIT]:
        que = instance.get_elements(WritingQuestion)
        que = que.filter(applicable=applicable)
        types = set(que.values_list("typ", flat=True).distinct())

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
                    applicable=applicable,
                )


def _init_faction_form_questions(def_tps, instance, features):
    if "faction" not in features:
        return

    que = instance.get_elements(WritingQuestion)
    que = que.filter(applicable=QuestionApplicable.FACTION)
    types = set(que.values_list("typ", flat=True).distinct())

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
                applicable=QuestionApplicable.FACTION,
            )


def _init_plot_form_questions(def_tps, instance, features):
    if "plot" not in features:
        return

    que = instance.get_elements(WritingQuestion)
    que = que.filter(applicable=QuestionApplicable.PLOT)
    types = set(que.values_list("typ", flat=True).distinct())

    plot_tps = def_tps.copy()
    plot_tps[QuestionType.TEASER] = ("Concept", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 3000)

    # add default types if none are present
    if not types:
        for el, add in plot_tps.items():
            WritingQuestion.objects.create(
                event=instance,
                typ=el,
                name=_(add[0]),
                status=add[1],
                visibility=add[2],
                max_length=add[3],
                applicable=QuestionApplicable.PLOT,
            )


def _init_character_form_questions(custom_tps, def_tps, features, instance):
    que = instance.get_elements(WritingQuestion).filter(applicable=QuestionApplicable.CHARACTER)
    types = set(que.values_list("typ", flat=True).distinct())

    # evaluate each question type field
    choices = dict(QuestionType.choices)
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
    all_types -= set(def_tps.keys())
    for el in all_types:
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


@receiver(post_save, sender=Registration)
def post_save_registration_campaign(sender, instance, **kwargs):
    if not instance.member:
        return

    if instance.cancellation_date:
        return

    # auto assign last character if campaign
    if "campaign" not in get_event_features(instance.run.event_id):
        return
    if not instance.run.event.parent:
        return

    # if already has a character, do not proceed
    if RegistrationCharacterRel.objects.filter(reg__run=instance.run).count() > 0:
        return

    # get last run of campaign
    last = (
        Run.objects.filter(Q(event__parent=instance.run.event.parent) | Q(event_id=instance.run.event.parent_id))
        .exclude(event_id=instance.run.event_id)
        .order_by("-end")
        .first()
    )
    if not last:
        return

    try:
        old_rcr = RegistrationCharacterRel.objects.get(reg__member=instance.member, reg__run=last)
        rcr = RegistrationCharacterRel.objects.create(reg=instance, character=old_rcr.character)
        for s in ["name", "pronoun", "song", "public", "private"]:
            if hasattr(old_rcr, "custom_" + s):
                value = getattr(old_rcr, "custom_" + s)
                setattr(rcr, "custom_" + s, value)
        rcr.save()
    except ObjectDoesNotExist:
        pass


@receiver(post_save, sender=AccountingItemPayment)
def post_save_accounting_item_payment_vat(sender, instance, created, **kwargs):
    if "vat" not in get_assoc_features(instance.assoc_id):
        return

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


@receiver(pre_save, sender=Association)
def pre_save_association_set_skin_features(sender, instance, **kwargs):
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


@receiver(post_save, sender=Association)
def post_save_association_set_skin_features(sender, instance, created, **kwargs):
    if not hasattr(instance, "_update_skin_features"):
        return

    def update_features():
        instance.features.set(instance.skin.default_features.all())

    transaction.on_commit(update_features)


@receiver(post_save, sender=LarpManagerTutorial)
def post_save_index_tutorial(sender, instance, **kwargs):
    index_tutorial(instance.id)


@receiver(post_delete, sender=LarpManagerTutorial)
def delete_tutorial_from_index(sender, instance, **kwargs):
    delete_index(instance.id)


@receiver(post_save, sender=WritingQuestion)
def save_event_field(sender, instance, created, **kwargs):
    reset_event_fields_cache(instance.event_id)


@receiver(pre_delete, sender=WritingQuestion)
def delete_event_field(sender, instance, **kwargs):
    reset_event_fields_cache(instance.event_id)
