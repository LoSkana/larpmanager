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
from django.db.models import Max, Q
from django.db.models.signals import pre_save, post_save, pre_delete
from django.dispatch import receiver
from django.utils.translation import activate, gettext_lazy as _
from slugify import slugify

from larpmanager.cache.feature import get_event_features, reset_event_features
from larpmanager.models.accounting import (
    AccountingItemTransaction,
    AccountingItemPayment,
    Collection,
    AccountingItemCollection,
)
from larpmanager.models.association import Association
from larpmanager.models.access import AssocPermission, EventPermission, get_event_organizers, EventRole
from larpmanager.models.event import Run, EventButton, Event, EventText, EventConfig
from larpmanager.models.form import CharacterQuestion, QuestionType, QuestionStatus, QuestionVisibility
from larpmanager.models.larpmanager import LarpManagerTutorial, LarpManagerFaq
from larpmanager.models.member import Member, Membership
from larpmanager.models.registration import RegistrationTicket, Registration, RegistrationCharacterRel
from larpmanager.models.writing import Plot, Faction, Prologue, SpeedLarp, replace_chars_all
from larpmanager.models.casting import Trait, update_traits_all
from larpmanager.cache.button import event_button_key
from larpmanager.utils.common import copy_class


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
def pre_save_Association(sender, instance, **kwargs):
    if not instance.key:
        instance.key = Fernet.generate_key()


@receiver(pre_save, sender=AssocPermission)
def pre_save_AssocPermission(sender, instance, **kwargs):
    if not instance.number:
        n = AssocPermission.objects.filter(feature__module=instance.feature.module).aggregate(Max("number"))[
            "number__max"
        ]
        if not n:
            n = 1
        instance.number = n + 10


@receiver(pre_save, sender=EventPermission)
def pre_save_EventPermission(sender, instance, **kwargs):
    if not instance.number:
        n = EventPermission.objects.filter(feature__module=instance.feature.module).aggregate(Max("number"))[
            "number__max"
        ]
        if not n:
            n = 1
        instance.number = n + 10


@receiver(pre_save, sender=Plot)
def pre_save_Plot(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(pre_save, sender=Faction)
def pre_save_Faction(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(pre_save, sender=Prologue)
def pre_save_Prologue(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(post_save, sender=Run)
def save_Run_plan(sender, instance, **kwargs):
    if not instance.plan and instance.event:
        updates = {"plan": instance.event.assoc.plan}
        Run.objects.filter(pk=instance.pk).update(**updates)


@receiver(post_save, sender=Trait)
def update_trait(sender, instance, **kwargs):
    update_traits_all(instance)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_AccountingItemPayment_updatereg(sender, instance, created, **kwargs):
    instance.reg.save()


@receiver(pre_save, sender=AccountingItemPayment)
def update_AccountingItemPayment_member(sender, instance, **kwargs):
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
def post_save_AccountingItemCollection(sender, instance, created, **kwargs):
    if instance.collection:
        instance.collection.save()


@receiver(pre_save, sender=SpeedLarp)
def pre_save_SpeedLarp(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(pre_save, sender=LarpManagerTutorial)
def pre_save_LarpManagerTutorial(sender, instance, *args, **kwargs):
    if not instance.slug:
        instance.slug = slugify(instance.name)


@receiver(pre_save, sender=LarpManagerFaq)
def pre_save_LarpManagerFaq(sender, instance, *args, **kwargs):
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
def pre_save_Membership(sender, instance, **kwargs):
    if instance.status == Membership.ACCEPTED:
        if not instance.card_number:
            n = Membership.objects.filter(assoc=instance.assoc).aggregate(Max("card_number"))["card_number__max"]
            if not n:
                n = 0
            instance.card_number = n + 1
        if not instance.date:
            instance.date = date.today()

    if instance.status == Membership.EMPTY:
        if instance.card_number:
            instance.card_number = None
        if instance.date:
            instance.date = None


@receiver(post_save, sender=EventButton)
def save_EventButton(sender, instance, created, **kwargs):
    cache.delete(event_button_key(instance.event_id))


@receiver(pre_delete, sender=EventButton)
def delete_EventButton(sender, instance, **kwargs):
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
        if instance._old_parent_id != instance.parent_id:
            # copy config, texts, roles
            copy_class(instance.pk, instance.parent_id, EventConfig)
            copy_class(instance.pk, instance.parent_id, EventText)
            copy_class(instance.pk, instance.parent_id, EventRole)
            # copy features
            for fn in instance.parent.features.all():
                instance.features.add(fn)


@receiver(post_save, sender=Event)
def save_event_update(sender, instance, **kwargs):
    if instance.template:
        return

    if instance.runs.count() == 0:
        Run.objects.create(event=instance, number=1)

    features = get_event_features(instance.id)

    # create tickets if not exists
    tickets = [
        ("", RegistrationTicket.STANDARD, "Standard"),
        ("waiting", RegistrationTicket.WAITING, "Waiting"),
        ("filler", RegistrationTicket.FILLER, "Filler"),
    ]
    for ticket in tickets:
        if ticket[0] and ticket[0] not in features:
            continue
        if RegistrationTicket.objects.filter(event=instance, tier=ticket[1]).count() == 0:
            RegistrationTicket.objects.create(event=instance, tier=ticket[1], name=ticket[2])

    # create fields if not exists / delete if feature not active
    if "character_form" in features:
        types = set(CharacterQuestion.objects.filter(event=instance).values_list("typ", flat=True).distinct())

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

        # evaluate each question type field
        choices = dict(QuestionType.choices)
        all_types = choices.keys()

        custom_tps = {QuestionType.SINGLE, QuestionType.MULTIPLE, QuestionType.TEXT, QuestionType.PARAGRAPH}
        all_types -= custom_tps

        def_tps = {
            QuestionType.NAME: ("Name", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 100),
            QuestionType.TEASER: ("Presentation", QuestionStatus.MANDATORY, QuestionVisibility.PUBLIC, 3000),
            QuestionType.SHEET: ("Text", QuestionStatus.MANDATORY, QuestionVisibility.PRIVATE, 5000),
        }
        if not types:
            for el, add in def_tps.items():
                CharacterQuestion.objects.create(
                    event=instance, typ=el, display=_(add[0]), status=add[1], visibility=add[2], max_length=add[3]
                )
        all_types -= set(def_tps.keys())

        for el in all_types:
            if el in features and el not in types:
                CharacterQuestion.objects.create(
                    event=instance,
                    typ=el,
                    display=_(el.capitalize()),
                    status=QuestionStatus.HIDDEN,
                    visibility=QuestionVisibility.PRIVATE,
                    max_length=1000,
                )
            if el not in features and el in types:
                CharacterQuestion.objects.filter(event=instance, typ=el).delete()

    reset_event_features(instance.id)


@receiver(post_save, sender=Registration)
def post_save_Registration_campaign(sender, instance, **kwargs):
    if not instance.member:
        return

    # auto assign last character if campaign
    if "campaign" not in get_event_features(instance.run.event_id):
        return
    if not instance.run.event.parent:
        return

    # if already has a character, do not proceed
    if RegistrationCharacterRel.objects.filter(reg=instance).count() > 0:
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
