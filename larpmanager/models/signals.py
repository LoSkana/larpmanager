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
import os
from datetime import date
from io import BytesIO

import PIL.Image as PILImage
from cryptography.fernet import Fernet
from django.conf import settings as conf_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import Max, Q
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _
from PIL import ImageOps
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
    BaseQuestionType,
    QuestionApplicable,
    QuestionStatus,
    QuestionVisibility,
    RegistrationQuestion,
    RegistrationQuestionType,
    WritingChoice,
    WritingQuestion,
    WritingQuestionType,
)
from larpmanager.models.larpmanager import LarpManagerFaq, LarpManagerGuide, LarpManagerTicket, LarpManagerTutorial
from larpmanager.models.member import Member, MemberConfig, Membership, MembershipStatus
from larpmanager.models.miscellanea import WarehouseItem
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, CharacterConfig, Faction, Plot, Prologue, SpeedLarp, replace_chars_all
from larpmanager.utils.common import copy_class
from larpmanager.utils.tasks import my_send_mail
from larpmanager.utils.tutorial_query import delete_index_guide, delete_index_tutorial, index_guide, index_tutorial


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

    if hasattr(instance, "search"):
        instance.search = None
        instance.search = str(instance)


@receiver(pre_save, sender=Association)
def pre_save_association_generate_fernet(sender, instance, **kwargs):
    """Generate Fernet encryption key for new associations.

    Args:
        sender: Association model class
        instance: Association instance being saved
        **kwargs: Additional keyword arguments
    """
    if not instance.key:
        instance.key = Fernet.generate_key()


@receiver(pre_save, sender=AssocPermission)
def pre_save_assoc_permission(sender, instance, **kwargs):
    """Handle association permission changes and cache updates.

    Args:
        sender: AssocPermission model class
        instance: AssocPermission instance being saved
        **kwargs: Additional keyword arguments
    """
    if not instance.number:
        n = AssocPermission.objects.filter(feature__module=instance.feature.module).aggregate(Max("number"))[
            "number__max"
        ]
        if not n:
            n = 1
        instance.number = n + 10


@receiver(pre_save, sender=EventPermission)
def pre_save_event_permission(sender, instance, **kwargs):
    """Handle event permission changes and numbering.

    Args:
        sender: EventPermission model class
        instance: EventPermission instance being saved
        **kwargs: Additional keyword arguments
    """
    if not instance.number:
        n = EventPermission.objects.filter(feature__module=instance.feature.module).aggregate(Max("number"))[
            "number__max"
        ]
        if not n:
            n = 1
        instance.number = n + 10


@receiver(pre_save, sender=Plot)
def pre_save_plot(sender, instance, *args, **kwargs):
    """Replace character references in plot text before saving.

    Args:
        sender: Plot model class
        instance: Plot instance being saved
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments
    """
    replace_chars_all(instance)


@receiver(pre_save, sender=Faction)
def pre_save_faction(sender, instance, *args, **kwargs):
    """Replace character references in faction text before saving.

    Args:
        sender: Faction model class
        instance: Faction instance being saved
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments
    """
    replace_chars_all(instance)


@receiver(pre_save, sender=Prologue)
def pre_save_prologue(sender, instance, *args, **kwargs):
    """Replace character references in prologue text before saving.

    Args:
        sender: Prologue model class
        instance: Prologue instance being saved
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments
    """
    replace_chars_all(instance)


@receiver(post_save, sender=Run)
def save_run_plan(sender, instance, **kwargs):
    """Set run plan from association default if not already set.

    Args:
        sender: Run model class
        instance: Run instance that was saved
        **kwargs: Additional keyword arguments
    """
    if not instance.plan and instance.event:
        updates = {"plan": instance.event.assoc.plan}
        Run.objects.filter(pk=instance.pk).update(**updates)


@receiver(post_save, sender=Trait)
def update_trait(sender, instance, **kwargs):
    """Update trait relationships after trait is saved.

    Args:
        sender: Trait model class
        instance: Trait instance that was saved
        **kwargs: Additional keyword arguments
    """
    update_traits_all(instance)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_accounting_item_payment_updatereg(sender, instance, created, **kwargs):
    """Update registration totals when payment items are saved.

    Args:
        sender: AccountingItemPayment model class
        instance: AccountingItemPayment instance that was saved
        created (bool): Whether this is a new instance
        **kwargs: Additional keyword arguments
    """
    instance.reg.save()


@receiver(pre_save, sender=AccountingItemPayment)
def update_accounting_item_payment_member(sender, instance, **kwargs):
    """Update payment member and handle registration changes.

    Args:
        sender: AccountingItemPayment model class
        instance: AccountingItemPayment instance being saved
        **kwargs: Additional keyword arguments
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


@receiver(pre_save, sender=Collection)
def pre_save_collection(sender, instance, **kwargs):
    """Generate unique codes and calculate collection totals.

    Args:
        sender: Collection model class
        instance: Collection instance being saved
        **kwargs: Additional keyword arguments
    """
    if not instance.pk:
        instance.unique_contribute_code()
        instance.unique_redeem_code()
        return
    instance.total = 0
    for el in instance.collection_gifts.all():
        instance.total += el.value


@receiver(post_save, sender=AccountingItemCollection)
def post_save_accounting_item_collection(sender, instance, created, **kwargs):
    """Update collection total when items are added.

    Args:
        sender: AccountingItemCollection model class
        instance: AccountingItemCollection instance that was saved
        created (bool): Whether this is a new instance
        **kwargs: Additional keyword arguments
    """
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
    """Create member profile and sync email when user is saved.

    Args:
        sender: User model class
        instance: User instance that was saved
        created (bool): Whether this is a new user
        **kwargs: Additional keyword arguments
    """
    if created:
        Member.objects.create(user=instance)
    instance.member.email = instance.email
    instance.member.save()


@receiver(pre_save, sender=Membership)
def pre_save_membership(sender, instance, **kwargs):
    """Handle membership status changes and card numbering.

    Args:
        sender: Membership model class
        instance: Membership instance being saved
        **kwargs: Additional keyword arguments
    """
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

    save_event_registration_form(features, instance)

    save_event_character_form(features, instance)

    reset_event_features(instance.id)

    reset_event_fields_cache(instance.id)


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


@receiver(post_save, sender=Registration)
def post_save_registration_campaign(sender, instance, **kwargs):
    """Auto-assign last character for campaign registrations.

    Args:
        sender: Registration model class
        instance: Registration instance that was saved
        **kwargs: Additional keyword arguments
    """
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
    if RegistrationCharacterRel.objects.filter(reg__member=instance.member, reg__run=instance.run).count() > 0:
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
    """Calculate VAT for payment items when VAT feature is enabled.

    Args:
        sender: AccountingItemPayment model class
        instance: AccountingItemPayment instance that was saved
        created (bool): Whether this is a new instance
        **kwargs: Additional keyword arguments
    """
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


@receiver(post_save, sender=CharacterConfig)
def post_save_reset_character_config(sender, instance, **kwargs):
    reset_configs(instance.character)


@receiver(post_delete, sender=CharacterConfig)
def post_delete_reset_character_config(sender, instance, **kwargs):
    reset_configs(instance.character)


@receiver(pre_save, sender=Association)
def pre_save_association_set_skin_features(sender, instance, **kwargs):
    if not instance.skin_id:
        return

    # execute if new association, or if changed skin
    if instance.pk:
        try:
            prev = Association.objects.get(pk=instance.pk)
        except ObjectDoesNotExist:
            return
        if instance.skin_id == prev.skin_id:
            return

    try:
        skin = instance.skin
    except ObjectDoesNotExist:
        return

    instance._update_skin_features = True
    if not instance.nationality:
        instance.nationality = skin.default_nation

    if not instance.optional_fields:
        instance.optional_fields = skin.default_optional_fields

    if not instance.mandatory_fields:
        instance.mandatory_fields = skin.default_mandatory_fields


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


@receiver(post_save, sender=LarpManagerTicket)
def save_larpmanager_ticket(sender, instance, created, **kwargs):
    for _name, email in conf_settings.ADMINS:
        subj = f"LarpManager ticket - {instance.assoc.name}"
        if instance.reason:
            subj += f" [{instance.reason}]"
        body = f"Email: {instance.email} <br /><br />"
        if instance.member:
            body += f"User: {instance.member} ({instance.member.email}) <br /><br />"
        body += instance.content
        if instance.screenshot:
            body += f"<br /><br /><img src='http://larpmanager.com/{instance.screenshot_reduced.url}' />"
        my_send_mail(subj, body, email)


@receiver(pre_save, sender=WarehouseItem, dispatch_uid="warehouseitem_rotate_vertical_photo")
def rotate_vertical_photo(sender, instance: WarehouseItem, **kwargs):
    """Automatically rotate vertical photos in warehouse items before saving.

    Args:
        sender: The model class that sent the signal
        instance: The WarehouseItem instance being saved
        **kwargs: Additional keyword arguments
    """
    try:
        # noinspection PyProtectedMember, PyUnresolvedReferences
        field = instance._meta.get_field("photo")
        if not isinstance(field, models.ImageField):
            return
    except Exception:
        return

    f = getattr(instance, "photo", None)
    if not f:
        return

    if _check_new(f, instance, sender):
        return

    fileobj = getattr(f, "file", None) or f
    try:
        fileobj.seek(0)
        img = PILImage.open(fileobj)
    except Exception:
        return

    img = ImageOps.exif_transpose(img)
    w, h = img.size
    if h <= w:
        return

    img = img.rotate(90, expand=True)

    fmt = _get_extension(f, img)

    if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    out = BytesIO()
    save_kwargs = {"optimize": True}
    if fmt == "JPEG":
        save_kwargs["quality"] = 88
    img.save(out, format=fmt, **save_kwargs)
    out.seek(0)

    basename = os.path.basename(f.name) or f.name
    instance.photo = ContentFile(out.read(), name=basename)


def _get_extension(f, img):
    ext = os.path.splitext(f.name)[1].lower()
    fmt = (img.format or "").upper()
    if not fmt:
        if ext in (".jpg", ".jpeg"):
            fmt = "JPEG"
        elif ext == ".png":
            fmt = "PNG"
        elif ext == ".webp":
            fmt = "WEBP"
        else:
            fmt = "JPEG"
    return fmt


def _check_new(f, instance, sender):
    if instance.pk:
        try:
            old = sender.objects.filter(pk=instance.pk).only("photo").first()
            if old:
                old_name = old.photo.name if old.photo else ""
                if f.name == old_name and not getattr(f, "file", None):
                    return True
        except Exception:
            pass

    return False


def check_character_ticket_options(reg, char):
    """Remove character options not available for registration ticket.

    Args:
        reg: Registration instance
        char: Character instance to check options for
    """
    ticket_id = reg.ticket.id

    to_delete = []

    # get options
    for choice in WritingChoice.objects.filter(element_id=char.id):
        tickets_map = choice.option.tickets.values_list("pk", flat=True)
        if tickets_map and ticket_id not in tickets_map:
            to_delete.append(choice.id)

    WritingChoice.objects.filter(pk__in=to_delete).delete()


@receiver(post_save, sender=Registration)
def post_save_registration_character_form(sender, instance, **kwargs):
    """Clean up character form options based on ticket restrictions.

    Args:
        sender: Registration model class
        instance: Registration instance that was saved
        **kwargs: Additional keyword arguments
    """
    if not instance.member:
        return

    if not instance.ticket:
        return

    event = instance.run.event

    for char in instance.characters.all():
        check_character_ticket_options(instance, char)

    for char in event.get_elements(Character).filter(player=instance.member):
        check_character_ticket_options(instance, char)
