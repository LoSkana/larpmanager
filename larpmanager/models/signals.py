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

from django.contrib.auth.models import User
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from larpmanager.accounting.base import (
    handle_accounting_item_collection_post_save,
    handle_accounting_item_payment_pre_save,
    handle_collection_pre_save,
)
from larpmanager.accounting.payment import (
    process_collection_status_change,
    process_payment_invoice_status_change,
    process_refund_request_status_change,
)
from larpmanager.accounting.registration import (
    handle_registration_accounting_updates,
    process_accounting_discount_post_save,
    process_registration_option_post_save,
    process_registration_pre_save,
    process_registration_ticket_post_save,
)
from larpmanager.accounting.token_credit import (
    handle_accounting_item_expense_save,
    handle_accounting_item_other_save,
    handle_accounting_item_payment_post_delete,
    handle_accounting_item_payment_post_save,
)
from larpmanager.accounting.vat import compute_vat
from larpmanager.cache.accounting import reset_registration_accounting_cache, update_member_accounting_cache
from larpmanager.cache.association import reset_cache_assoc
from larpmanager.cache.character import (
    character_factions_changed,
    handle_character_pre_save,
    handle_faction_pre_save,
    handle_quest_presave,
    handle_quest_type_presave,
    handle_registration_character_rel_save,
    handle_trait_presave,
    handle_update_event_characters,
    reset_event_cache_all_runs,
    reset_run,
)
from larpmanager.cache.config import reset_configs
from larpmanager.cache.feature import handle_association_features_post_save, reset_event_features
from larpmanager.cache.fields import reset_event_fields_cache
from larpmanager.cache.larpmanager import reset_cache_lm_home
from larpmanager.cache.links import handle_registration_event_links_post_save, reset_run_event_links
from larpmanager.cache.permission import reset_assoc_permission, reset_event_permission, reset_index_permission
from larpmanager.cache.registration import handle_update_registration_character_rel, reset_cache_reg_counts
from larpmanager.cache.rels import (
    handle_faction_characters_changed,
    handle_plot_characters_changed,
    handle_prologue_characters_changed,
    handle_speedlarp_characters_changed,
    remove_from_cache_section,
    reset_event_rels_cache,
    update_character_related_caches,
    update_event_char_rels,
    update_event_faction_rels,
    update_event_plot_rels,
    update_event_prologue_rels,
    update_event_quest_rels,
    update_event_questtype_rels,
    update_event_speedlarp_rels,
)
from larpmanager.cache.role import delete_cache_assoc_role, delete_cache_event_role
from larpmanager.cache.run import (
    handle_event_post_save_cache_reset,
    handle_event_pre_save,
    handle_run_post_save_cache_reset,
    handle_run_pre_save,
)
from larpmanager.cache.skin import reset_cache_skin
from larpmanager.cache.text_fields import update_acc_callback
from larpmanager.mail.accounting import (
    handle_accounting_item_other_pre_save,
    handle_collection_gift_pre_save,
    handle_collection_post_save,
    handle_donation_item_pre_save,
    handle_expense_item_approval_notification,
    handle_expense_item_post_save,
    handle_payment_item_pre_save,
)
from larpmanager.mail.base import (
    assoc_roles_changed,
    event_roles_changed,
    handle_character_status_update_notification,
    handle_trait_assignment_notification,
    mail_larpmanager_ticket,
)
from larpmanager.mail.member import (
    badges_changed,
    handle_chat_message_notification,
    handle_help_question_notification,
    handle_membership_payment_notification,
)
from larpmanager.mail.registration import (
    handle_pre_registration_pre_save,
    handle_registration_character_rel_post_save,
    handle_registration_pre_delete,
    handle_registration_pre_save,
)
from larpmanager.models.access import AssocPermission, AssocRole, EventPermission, EventRole
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemDiscount,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemPayment,
    Collection,
    PaymentInvoice,
    RefundRequest,
)
from larpmanager.models.association import Association, AssociationConfig, AssociationSkin, AssocText
from larpmanager.models.base import Feature, FeatureModule, auto_populate_number_order_fields, update_search_field
from larpmanager.models.casting import AssignmentTrait, Quest, QuestType, Trait, update_traits_all
from larpmanager.models.event import (
    Event,
    EventButton,
    EventConfig,
    EventText,
    PreRegistration,
    Run,
    RunConfig,
)
from larpmanager.models.experience import AbilityPx, DeliveryPx, ModifierPx, RulePx
from larpmanager.models.form import (
    RegistrationOption,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.larpmanager import LarpManagerFaq, LarpManagerGuide, LarpManagerTicket, LarpManagerTutorial
from larpmanager.models.member import Badge, Member, MemberConfig, Membership
from larpmanager.models.miscellanea import ChatMessage, HelpQuestion, PlayerRelationship, WarehouseItem
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket
from larpmanager.models.writing import (
    Character,
    CharacterConfig,
    Faction,
    Handout,
    HandoutTemplate,
    Plot,
    Prologue,
    Relationship,
    SpeedLarp,
    replace_chars_all,
)
from larpmanager.utils.association import (
    assign_assoc_permission_number,
    handle_association_fernet_key_generation,
    handle_association_skin_features_post_save,
    handle_association_skin_features_pre_save,
)
from larpmanager.utils.auth import assign_event_permission_number
from larpmanager.utils.event import (
    auto_assign_campaign_character,
    handle_event_pre_save_prepare_campaign,
    handle_run_post_save,
    reset_event_button,
    setup_campaign_event,
    setup_event_after_save,
)
from larpmanager.utils.experience import (
    handle_ability_save,
    handle_delivery_save,
    handle_modifier_save,
    handle_rule_save,
    modifier_abilities_changed,
    px_characters_changed,
    rule_abilities_changed,
    update_px,
)
from larpmanager.utils.larpmanager import assign_faq_number, handle_tutorial_slug_generation
from larpmanager.utils.member import handle_membership_status_changes, handle_user_profile_creation
from larpmanager.utils.miscellanea import rotate_vertical_photo
from larpmanager.utils.pdf import (
    handle_assignment_trait_post_save,
    handle_character_post_save,
    handle_character_pre_delete,
    handle_faction_post_save,
    handle_faction_pre_delete,
    handle_handout_post_save,
    handle_handout_pre_delete,
    handle_handout_template_post_save,
    handle_handout_template_pre_delete,
    handle_player_relationship_post_save,
    handle_player_relationship_pre_delete,
    remove_char_pdf,
    remove_pdf_assignment_trait,
)
from larpmanager.utils.registration import handle_registration_event_switch, save_registration_character_form
from larpmanager.utils.text import (
    handle_assoc_text_del,
    handle_assoc_text_save,
    handle_event_text_del,
    handle_event_text_save,
)
from larpmanager.utils.tutorial_query import delete_index_guide, delete_index_tutorial, index_guide, index_tutorial
from larpmanager.utils.writing import handle_replace_char_names

log = logging.getLogger(__name__)


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


@receiver(pre_save, sender=Association)
def pre_save_association_generate_fernet(sender, instance, **kwargs):
    handle_association_fernet_key_generation(instance)


@receiver(pre_save, sender=AssocPermission)
def pre_save_assoc_permission(sender, instance, **kwargs):
    assign_assoc_permission_number(instance)


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


@receiver(post_save, sender=Run)
def post_save_run_plan(sender, instance, **kwargs):
    handle_run_post_save(instance)


@receiver(post_save, sender=Trait)
def post_save_trait(sender, instance, **kwargs):
    update_traits_all(instance)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_accounting_item_payment_updatereg(sender, instance, created, **kwargs):
    instance.reg.save()


@receiver(pre_save, sender=AccountingItemPayment)
def pre_save_accounting_item_payment_member(sender, instance, **kwargs):
    handle_accounting_item_payment_pre_save(instance)


@receiver(pre_save, sender=Collection)
def pre_save_collection(sender, instance, **kwargs):
    handle_collection_pre_save(instance)


@receiver(post_save, sender=AccountingItemCollection)
def post_save_accounting_item_collection(sender, instance, created, **kwargs):
    handle_accounting_item_collection_post_save(instance)


@receiver(pre_save, sender=SpeedLarp)
def pre_save_speed_larp(sender, instance, *args, **kwargs):
    replace_chars_all(instance)


@receiver(pre_save, sender=LarpManagerTutorial)
def pre_save_larp_manager_tutorial(sender, instance, *args, **kwargs):
    handle_tutorial_slug_generation(instance)


@receiver(pre_save, sender=LarpManagerFaq)
def pre_save_larp_manager_faq(sender, instance, *args, **kwargs):
    assign_faq_number(instance)


@receiver(post_save, sender=User)
def post_save_user_profile(sender, instance, created, **kwargs):
    handle_user_profile_creation(instance, created)


@receiver(pre_save, sender=Membership)
def pre_save_membership(sender, instance, **kwargs):
    handle_membership_status_changes(instance)


@receiver(post_save, sender=EventButton)
def post_save_event_button(sender, instance, created, **kwargs):
    reset_event_button(instance)


@receiver(pre_delete, sender=EventButton)
def pre_delete_event_button(sender, instance, **kwargs):
    reset_event_button(instance)


@receiver(pre_save, sender=Event)
def pre_save_event_prepare_campaign(sender, instance, **kwargs):
    handle_event_pre_save_prepare_campaign(instance)


@receiver(post_save, sender=Event)
def post_save_event_campaign(sender, instance, **kwargs):
    if not getattr(instance, "_skip_campaign_setup", False):
        setup_campaign_event(instance)


@receiver(post_save, sender=Event)
def post_save_event_update(sender, instance, **kwargs):
    setup_event_after_save(instance)


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


@receiver(pre_save, sender=Association)
def pre_save_association_set_skin_features(sender, instance, **kwargs):
    handle_association_skin_features_pre_save(instance)


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


@receiver(pre_save, sender=WarehouseItem, dispatch_uid="warehouseitem_rotate_vertical_photo")
def pre_save_warehouse_item(sender, instance: WarehouseItem, **kwargs):
    rotate_vertical_photo(instance, sender)


@receiver(post_save, sender=Registration)
def post_save_registration_character_form(sender, instance, **kwargs):
    save_registration_character_form(instance)


@receiver(post_save, sender=Character, dispatch_uid="post_character_update_px_v1")
def post_character_update_px(sender, instance, *args, **kwargs):
    update_px(instance)


@receiver(post_save, sender=AbilityPx)
def post_save_ability_px(sender, instance, *args, **kwargs):
    handle_ability_save(instance)


@receiver(post_delete, sender=AbilityPx)
def post_delete_ability_px(sender, instance, *args, **kwargs):
    handle_ability_save(instance)


@receiver(post_save, sender=DeliveryPx)
def post_save_delivery_px(sender, instance, *args, **kwargs):
    handle_delivery_save(instance)


@receiver(post_delete, sender=DeliveryPx)
def post_delete_delivery_px(sender, instance, *args, **kwargs):
    handle_delivery_save(instance)


@receiver(post_save, sender=RulePx)
def post_save_rule_px(sender, instance, *args, **kwargs):
    handle_rule_save(instance)


@receiver(post_delete, sender=RulePx)
def post_delete_rule_px(sender, instance, *args, **kwargs):
    handle_rule_save(instance)


@receiver(post_save, sender=ModifierPx)
def post_save_modifier_px(sender, instance, *args, **kwargs):
    handle_modifier_save(instance)


@receiver(post_delete, sender=ModifierPx)
def post_delete_modifier_px(sender, instance, *args, **kwargs):
    handle_modifier_save(instance)


m2m_changed.connect(px_characters_changed, sender=DeliveryPx.characters.through)
m2m_changed.connect(px_characters_changed, sender=AbilityPx.characters.through)

m2m_changed.connect(modifier_abilities_changed, sender=ModifierPx.abilities.through)
m2m_changed.connect(rule_abilities_changed, sender=RulePx.abilities.through)


@receiver(post_save, sender=LarpManagerTicket)
def save_larpmanager_ticket(sender, instance, created, **kwargs):
    mail_larpmanager_ticket(instance)


@receiver(post_save, sender=Registration)
def post_save_registration_accounting(sender, instance, **kwargs):
    handle_registration_accounting_updates(instance)


@receiver(post_save, sender=AccountingItemDiscount)
def post_save_accounting_item_discount_accounting(sender, instance, **kwargs):
    process_accounting_discount_post_save(instance)


@receiver(post_save, sender=RegistrationTicket)
def post_save_registration_ticket(sender, instance, created, **kwargs):
    process_registration_ticket_post_save(instance)


@receiver(post_save, sender=RegistrationOption)
def post_save_registration_option(sender, instance, created, **kwargs):
    process_registration_option_post_save(instance)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_accounting_item_payment(sender, instance, created, **kwargs):
    handle_accounting_item_payment_post_save(instance, created)


@receiver(post_delete, sender=AccountingItemPayment)
def post_delete_accounting_item_payment(sender, instance, **kwargs):
    handle_accounting_item_payment_post_delete(instance)


@receiver(post_save, sender=AccountingItemOther)
def post_save_accounting_item_other_accounting(sender, instance, **kwargs):
    handle_accounting_item_other_save(instance)


@receiver(post_save, sender=AccountingItemExpense)
def post_save_accounting_item_expense_accounting(sender, instance, **kwargs):
    handle_accounting_item_expense_save(instance)


@receiver(post_save, sender=Registration)
def post_save_registration_accounting_cache(sender, instance, created, **kwargs):
    """Reset accounting cache when a registration is saved."""
    reset_registration_accounting_cache(instance.run)


@receiver(post_delete, sender=Registration)
def post_delete_registration_accounting_cache(sender, instance, **kwargs):
    """Reset accounting cache when a registration is deleted."""
    reset_registration_accounting_cache(instance.run)


@receiver(post_save, sender=RegistrationTicket)
def post_save_ticket_accounting_cache(sender, instance, created, **kwargs):
    """Reset accounting cache when a ticket is saved."""
    for run in instance.event.runs.all():
        reset_registration_accounting_cache(run)


@receiver(post_delete, sender=RegistrationTicket)
def post_delete_ticket_accounting_cache(sender, instance, **kwargs):
    """Reset accounting cache when a ticket is deleted."""
    for run in instance.event.runs.all():
        reset_registration_accounting_cache(run)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_payment_accounting_cache(sender, instance, created, **kwargs):
    """Update accounting cache when a payment is saved."""
    if instance.reg and instance.reg.run:
        update_member_accounting_cache(instance.reg.run, instance.member_id)


@receiver(post_delete, sender=AccountingItemPayment)
def post_delete_payment_accounting_cache(sender, instance, **kwargs):
    """Update accounting cache when a payment is deleted."""
    if instance.reg and instance.reg.run:
        update_member_accounting_cache(instance.reg.run, instance.member_id)


@receiver(post_save, sender=AccountingItemDiscount)
def post_save_discount_accounting_cache(sender, instance, created, **kwargs):
    """Update accounting cache when a discount is saved."""
    if instance.run and instance.member_id:
        update_member_accounting_cache(instance.run, instance.member_id)


@receiver(post_delete, sender=AccountingItemDiscount)
def post_delete_discount_accounting_cache(sender, instance, **kwargs):
    """Update accounting cache when a discount is deleted."""
    if instance.run and instance.member_id:
        update_member_accounting_cache(instance.run, instance.member_id)


@receiver(post_save, sender=AccountingItemOther)
def post_save_other_accounting_cache(sender, instance, created, **kwargs):
    """Update accounting cache when an other accounting item is saved."""
    if instance.run and instance.member_id:
        update_member_accounting_cache(instance.run, instance.member_id)


@receiver(post_delete, sender=AccountingItemOther)
def post_delete_other_accounting_cache(sender, instance, **kwargs):
    """Update accounting cache when an other accounting item is deleted."""
    if instance.run and instance.member_id:
        update_member_accounting_cache(instance.run, instance.member_id)


@receiver(post_save, sender=Association)
def update_association_reset_cache(sender, instance, **kwargs):
    reset_cache_assoc(instance.slug)


@receiver(post_save, sender=Member)
def post_save_member_reset(sender, instance, **kwargs):
    handle_update_event_characters(instance)


@receiver(pre_save, sender=Character)
def pre_save_character_reset(sender, instance, **kwargs):
    handle_character_pre_save(instance)


@receiver(post_save, sender=RegistrationCharacterRel)
def post_save_registration_character_rel_savereg(sender, instance, created, **kwargs):
    handle_registration_character_rel_save(instance)


@receiver(post_delete, sender=RegistrationCharacterRel)
def post_delete_registration_character_rel_savereg(sender, instance, **kwargs):
    handle_registration_character_rel_save(instance)


@receiver(post_save, sender=AssignmentTrait)
def post_save_assignment_trait_reset(sender, instance, **kwargs):
    reset_run(instance.run)


@receiver(post_delete, sender=AssignmentTrait)
def post_delete_assignment_trait_reset(sender, instance, **kwargs):
    reset_run(instance.run)


@receiver(post_save, sender=Event)
def post_save_event_reset(sender, instance, **kwargs):
    reset_event_cache_all_runs(instance)


@receiver(post_save, sender=Run)
def post_save_run_reset(sender, instance, **kwargs):
    reset_run(instance)


@receiver(post_save, sender=WritingQuestion)
def post_save_character_question_reset(sender, instance, **kwargs):
    reset_event_cache_all_runs(instance.event)


@receiver(post_save, sender=WritingOption)
def post_save_character_option_reset(sender, instance, **kwargs):
    reset_event_cache_all_runs(instance.question.event)


@receiver(post_save, sender=Association)
def post_save_association_reset_features(sender, instance, **kwargs):
    handle_association_features_post_save(instance)


@receiver(post_save, sender=Event)
def post_save_event_reset_features(sender, instance, **kwargs):
    reset_event_features(instance.id)


@receiver(pre_delete, sender=WritingQuestion)
def pre_delete_writing_question_reset(sender, instance, **kwargs):
    reset_event_fields_cache(instance.event_id)


@receiver(post_save, sender=WritingQuestion)
def post_save_writing_question_reset(sender, instance, **kwargs):
    reset_event_fields_cache(instance.event_id)


@receiver(pre_delete, sender=WritingOption)
def pre_delete_writing_option_reset(sender, instance, **kwargs):
    reset_event_fields_cache(instance.question.event_id)


@receiver(post_save, sender=WritingOption)
def post_save_writing_option_reset(sender, instance, **kwargs):
    reset_event_fields_cache(instance.question.event_id)


@receiver(post_save, sender=Association)
def post_save_association_reset_lm_home(sender, instance, **kwargs):
    reset_cache_lm_home()


@receiver(post_save, sender=Registration)
def post_save_registration_event_links(sender, instance, **kwargs):
    handle_registration_event_links_post_save(instance)


@receiver(post_save, sender=Event)
def post_save_event_links(sender, instance, **kwargs):
    reset_run_event_links(instance)


@receiver(post_delete, sender=Event)
def post_delete_event_links(sender, instance, **kwargs):
    reset_run_event_links(instance)


@receiver(post_save, sender=Run)
def post_save_run_links(sender, instance, **kwargs):
    reset_run_event_links(instance.event)


@receiver(post_delete, sender=Run)
def post_delete_run_links(sender, instance, **kwargs):
    reset_run_event_links(instance.event)


@receiver(post_save, sender=AssocPermission)
def post_save_assoc_permission_reset(sender, instance, **kwargs):
    reset_assoc_permission(instance)


@receiver(post_delete, sender=AssocPermission)
def post_delete_assoc_permission_reset(sender, instance, **kwargs):
    reset_assoc_permission(instance)


@receiver(post_save, sender=EventPermission)
def post_save_event_permission_reset(sender, instance, **kwargs):
    reset_event_permission(instance)


@receiver(post_delete, sender=EventPermission)
def post_delete_event_permission_reset(sender, instance, **kwargs):
    reset_event_permission(instance)


@receiver(post_save, sender=AssocPermission)
def post_save_assoc_permission_index_permission(sender, instance, **kwargs):
    reset_index_permission("assoc")


@receiver(post_delete, sender=AssocPermission)
def post_delete_assoc_permission_index_permission(sender, instance, **kwargs):
    reset_index_permission("assoc")


@receiver(post_save, sender=EventPermission)
def post_save_event_permission_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")


@receiver(post_delete, sender=EventPermission)
def post_delete_event_permission_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")


@receiver(post_save, sender=Feature)
def post_save_feature_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")
    reset_index_permission("assoc")


@receiver(post_delete, sender=Feature)
def post_delete_feature_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")
    reset_index_permission("assoc")


@receiver(post_save, sender=FeatureModule)
def post_save_feature_module_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")
    reset_index_permission("assoc")


@receiver(post_delete, sender=FeatureModule)
def post_delete_feature_module_index_permission(sender, instance, **kwargs):
    reset_index_permission("event")
    reset_index_permission("assoc")


@receiver(post_save, sender=Registration)
def post_save_registration_cache(sender, instance, created, **kwargs):
    reset_cache_reg_counts(instance.run)


@receiver(post_save, sender=Character)
def post_save_character_cache(sender, instance, created, **kwargs):
    handle_update_registration_character_rel(instance)


@receiver(post_save, sender=Run)
def post_save_run_cache(sender, instance, created, **kwargs):
    reset_cache_reg_counts(instance)


@receiver(post_save, sender=Event)
def post_save_event_cache(sender, instance, created, **kwargs):
    for r in instance.runs.all():
        reset_cache_reg_counts(r)


@receiver(post_save, sender=Character)
def post_save_character_reset_rels(sender, instance, **kwargs):
    """Handle character save to update cache.

    Args:
        sender: The model class that sent the signal
        instance: The Character instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    update_event_char_rels(instance)
    for rel in Relationship.objects.filter(target=instance):
        update_event_char_rels(rel.source)

    # Update all related caches
    update_character_related_caches(instance)


@receiver(post_delete, sender=Character)
def post_delete_character_reset_rels(sender, instance, **kwargs):
    """Handle character deletion to reset cache.

    Resets the entire event cache when a character is deleted to ensure
    all references to the deleted character are removed.

    Args:
        sender: The model class that sent the signal
        instance: The Character instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update all related caches
    update_character_related_caches(instance)

    reset_event_rels_cache(instance.event_id)
    for rel in Relationship.objects.filter(target=instance):
        update_event_char_rels(rel.source)


@receiver(post_save, sender=Faction)
def post_save_faction_reset_rels(sender, instance, **kwargs):
    """Handle faction save to update related caches.

    Updates both faction cache and related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The Faction instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update faction cache
    update_event_faction_rels(instance)

    # Update cache for all characters in this faction
    for char in instance.characters.all():
        update_event_char_rels(char)


@receiver(post_delete, sender=Faction)
def post_delete_faction_reset_rels(sender, instance, **kwargs):
    """Handle faction deletion to update related caches.

    Removes faction from cache and updates related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The Faction instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for all characters that were in this faction
    for char in instance.characters.all():
        update_event_char_rels(char)

    # Remove faction from cache
    remove_from_cache_section(instance.event_id, "factions", instance.id)


@receiver(post_save, sender=Plot)
def post_save_plot_reset_rels(sender, instance, **kwargs):
    """Handle plot save to update related caches.

    Updates both plot cache and related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The Plot instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update plot cache
    update_event_plot_rels(instance)

    # Update cache for all characters in this plot
    for char_rel in instance.get_plot_characters():
        update_event_char_rels(char_rel.character)


@receiver(post_delete, sender=Plot)
def post_delete_plot_reset_rels(sender, instance, **kwargs):
    """Handle plot deletion to update related caches.

    Removes plot from cache and updates related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The Plot instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for all characters that were in this plot
    for char_rel in instance.get_plot_characters():
        update_event_char_rels(char_rel.character)

    # Remove plot from cache
    remove_from_cache_section(instance.event_id, "plots", instance.id)


@receiver(post_save, sender=SpeedLarp)
def post_save_speedlarp_reset_rels(sender, instance, **kwargs):
    """Handle speedlarp save to update related caches.

    Updates both speedlarp cache and related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The SpeedLarp instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update speedlarp cache
    update_event_speedlarp_rels(instance)

    # Update cache for all characters in this speedlarp
    for char in instance.characters.all():
        update_event_char_rels(char)


@receiver(post_delete, sender=SpeedLarp)
def post_delete_speedlarp_reset_rels(sender, instance, **kwargs):
    """Handle speedlarp deletion to update related caches.

    Removes speedlarp from cache and updates related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The SpeedLarp instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for all characters that were in this speedlarp
    for char in instance.characters.all():
        update_event_char_rels(char)

    # Remove speedlarp from cache
    remove_from_cache_section(instance.event_id, "speedlarps", instance.id)


@receiver(post_save, sender=Prologue)
def post_save_prologue_reset_rels(sender, instance, **kwargs):
    """Handle prologue save to update related caches.

    Updates both prologue cache and related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The Prologue instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update prologue cache
    update_event_prologue_rels(instance)

    # Update cache for all characters in this prologue
    for char in instance.characters.all():
        update_event_char_rels(char)


@receiver(post_delete, sender=Prologue)
def post_delete_prologue_reset_rels(sender, instance, **kwargs):
    """Handle prologue deletion to update related caches.

    Removes prologue from cache and updates related character caches.

    Args:
        sender: The model class that sent the signal
        instance: The Prologue instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for all characters that were in this prologue
    for char in instance.characters.all():
        update_event_char_rels(char)

    # Remove prologue from cache
    remove_from_cache_section(instance.event_id, "prologues", instance.id)


@receiver(post_save, sender=Relationship)
def post_save_relationship_reset_rels(sender, instance, **kwargs):
    """Handle relationship save to update character caches.

    Updates cache for both source and target characters when relationship changes.

    Args:
        sender: The model class that sent the signal
        instance: The Relationship instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for source character
    update_event_char_rels(instance.source)


@receiver(post_delete, sender=Relationship)
def post_delete_relationship_reset_rels(sender, instance, **kwargs):
    """Handle relationship deletion to update character caches.

    Updates cache for both source and target characters when relationship is deleted.

    Args:
        sender: The model class that sent the signal
        instance: The Relationship instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for source character
    update_event_char_rels(instance.source)


@receiver(post_save, sender=Quest)
def post_save_quest_reset_rels(sender, instance, **kwargs):
    """Handle quest save to update related caches.

    Updates both quest cache and related questtype cache.

    Args:
        sender: The model class that sent the signal
        instance: The Quest instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update quest cache
    update_event_quest_rels(instance)

    # Update questtype cache if quest has a type
    if instance.typ:
        update_event_questtype_rels(instance.typ)


@receiver(post_delete, sender=Quest)
def post_delete_quest_reset_rels(sender, instance, **kwargs):
    """Handle quest deletion to update related caches.

    Removes quest from cache and updates related questtype cache.

    Args:
        sender: The model class that sent the signal
        instance: The Quest instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update questtype cache if quest had a type
    if instance.typ:
        update_event_questtype_rels(instance.typ)

    # Remove quest from cache
    remove_from_cache_section(instance.event_id, "quests", instance.id)


@receiver(post_save, sender=QuestType)
def post_save_questtype_reset_rels(sender, instance, **kwargs):
    """Handle questtype save to update related caches.

    Updates both questtype cache and related quest caches.

    Args:
        sender: The model class that sent the signal
        instance: The QuestType instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update questtype cache
    update_event_questtype_rels(instance)

    # Update cache for all quests of this type
    for quest in instance.quests.all():
        update_event_quest_rels(quest)


@receiver(post_delete, sender=QuestType)
def post_delete_questtype_reset_rels(sender, instance, **kwargs):
    """Handle questtype deletion to update related caches.

    Removes questtype from cache and updates related quest caches.

    Args:
        sender: The model class that sent the signal
        instance: The QuestType instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update cache for all quests that were of this type
    for quest in instance.quests.all():
        update_event_quest_rels(quest)

    # Remove questtype from cache
    remove_from_cache_section(instance.event_id, "questtypes", instance.id)


@receiver(post_save, sender=Trait)
def post_save_trait_reset_rels(sender, instance, **kwargs):
    """Handle trait save to update quest cache.

    Updates the quest cache when a trait changes.

    Args:
        sender: The model class that sent the signal
        instance: The Trait instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update quest cache if trait has a quest
    if instance.quest:
        update_event_quest_rels(instance.quest)


@receiver(post_delete, sender=Trait)
def post_delete_trait_reset_rels(sender, instance, **kwargs):
    """Handle trait deletion to update quest cache.

    Updates the quest cache when a trait is deleted.

    Args:
        sender: The model class that sent the signal
        instance: The Trait instance that was deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update quest cache if trait had a quest
    if instance.quest:
        update_event_quest_rels(instance.quest)


@receiver(post_save, sender=AssocRole)
def post_save_assoc_role_reset(sender, instance, **kwargs):
    delete_cache_assoc_role(instance.pk)


@receiver(pre_delete, sender=AssocRole)
def pre_delete_assoc_role_reset(sender, instance, **kwargs):
    delete_cache_assoc_role(instance.pk)


@receiver(post_save, sender=EventRole)
def post_save_event_role_reset(sender, instance, **kwargs):
    delete_cache_event_role(instance.pk)


@receiver(pre_delete, sender=EventRole)
def pre_delete_event_role_reset(sender, instance, **kwargs):
    delete_cache_event_role(instance.pk)


@receiver(pre_save, sender=Run)
def pre_save_run(sender, instance, **kwargs):
    handle_run_pre_save(instance)


@receiver(pre_save, sender=Event)
def pre_save_event(sender, instance, **kwargs):
    handle_event_pre_save(instance)


@receiver(post_save, sender=Run)
def post_save_run_reset_cache_config_run(sender, instance, **kwargs):
    handle_run_post_save_cache_reset(instance)


@receiver(post_save, sender=Event)
def post_save_event_reset_cache_config_run(sender, instance, **kwargs):
    handle_event_post_save_cache_reset(instance)


@receiver(post_save, sender=AssociationSkin)
def post_save_association_skin_reset_cache(sender, instance, **kwargs):
    reset_cache_skin(instance.domain)


@receiver(post_save)
def post_save_text_fields_callback(sender, instance, *args, **kwargs):
    update_acc_callback(instance)


@receiver(post_delete)
def post_delete_text_fields_callback(sender, instance, **kwargs):
    update_acc_callback(instance)


@receiver(post_save, sender=AccountingItemExpense)
def post_save_accounting_item_expense(sender, instance, created, **kwargs):
    handle_expense_item_post_save(instance, created)


@receiver(pre_save, sender=AccountingItemExpense)
def pre_save_accounting_item_expense(sender, instance, **kwargs):
    handle_expense_item_approval_notification(instance)


@receiver(pre_save, sender=AccountingItemPayment)
def pre_save_accounting_item_payment(sender, instance, **kwargs):
    handle_payment_item_pre_save(instance)


@receiver(pre_save, sender=AccountingItemOther)
def pre_save_accounting_item_other(sender, instance, **kwargs):
    handle_accounting_item_other_pre_save(instance)


@receiver(pre_save, sender=AccountingItemDonation)
def pre_save_accounting_item_donation(sender, instance, *args, **kwargs):
    handle_donation_item_pre_save(instance)


@receiver(post_save, sender=Collection)
def post_save_collection_activation_email(sender, instance, created, **kwargs):
    handle_collection_post_save(instance, created)


@receiver(pre_save, sender=AccountingItemCollection)
def pre_save_collection_gift(sender, instance, **kwargs):
    handle_collection_gift_pre_save(instance)


@receiver(post_save, sender=AssignmentTrait)
def post_save_notify_trait_assigned(sender, instance, created, **kwargs):
    handle_trait_assignment_notification(instance, created)


@receiver(pre_save, sender=Character)
def pre_save_character_update_status(sender, instance, **kwargs):
    handle_character_status_update_notification(instance)


@receiver(post_save, sender=RegistrationCharacterRel)
def post_save_registration_character_rel(sender, instance, created, **kwargs):
    handle_registration_character_rel_post_save(instance, created)


@receiver(pre_save, sender=Registration)
def pre_save_registration(sender, instance, **kwargs):
    handle_registration_pre_save(instance)


@receiver(pre_delete, sender=Registration)
def pre_delete_registration(sender, instance, *args, **kwargs):
    handle_registration_pre_delete(instance)


@receiver(pre_save, sender=PreRegistration)
def pre_save_pre_registration(sender, instance, **kwargs):
    handle_pre_registration_pre_save(instance)


@receiver(pre_delete, sender=Handout)
def pre_delete_handout(sender, instance, **kwargs):
    handle_handout_pre_delete(instance)


@receiver(post_save, sender=Handout)
def post_save_handout(sender, instance, **kwargs):
    handle_handout_post_save(instance)


@receiver(pre_delete, sender=HandoutTemplate)
def pre_delete_handout_template(sender, instance, **kwargs):
    handle_handout_template_pre_delete(instance)


@receiver(post_save, sender=HandoutTemplate)
def post_save_handout_template(sender, instance, **kwargs):
    handle_handout_template_post_save(instance)


@receiver(pre_delete, sender=Character)
def pre_delete_character(sender, instance, **kwargs):
    handle_character_pre_delete(instance)


@receiver(post_save, sender=Character)
def post_save_character(sender, instance, **kwargs):
    handle_character_post_save(instance)


@receiver(pre_delete, sender=PlayerRelationship)
def pre_delete_player_relationship(sender, instance, **kwargs):
    handle_player_relationship_pre_delete(instance)


@receiver(post_save, sender=PlayerRelationship)
def post_save_player_relationship(sender, instance, **kwargs):
    handle_player_relationship_post_save(instance)


@receiver(pre_delete, sender=Relationship)
def pre_delete_relationship(sender, instance, **kwargs):
    remove_char_pdf(instance.source)


@receiver(post_save, sender=Relationship)
def post_save_relationship(sender, instance, **kwargs):
    remove_char_pdf(instance.source)


@receiver(pre_delete, sender=Faction)
def pre_delete_faction(sender, instance, **kwargs):
    handle_faction_pre_delete(instance)


@receiver(post_save, sender=Faction)
def post_save_faction(sender, instance, **kwargs):
    handle_faction_post_save(instance)


@receiver(pre_delete, sender=AssignmentTrait)
def pre_delete_assignment_trait(sender, instance, **kwargs):
    remove_pdf_assignment_trait(instance)


@receiver(post_save, sender=AssignmentTrait)
def post_save_assignment_trait(sender, instance, created, **kwargs):
    handle_assignment_trait_post_save(instance, created)


@receiver(post_save, sender=AssocText)
def post_save_assoc_text(sender, instance, created, **kwargs):
    handle_assoc_text_save(instance)


@receiver(pre_delete, sender=AssocText)
def pre_delete_assoc_text(sender, instance, **kwargs):
    handle_assoc_text_del(instance)


@receiver(post_save, sender=EventText)
def post_save_event_text(sender, instance, created, **kwargs):
    handle_event_text_save(instance)


@receiver(pre_delete, sender=EventText)
def pre_delete_event_text(sender, instance, **kwargs):
    handle_event_text_del(instance)


@receiver(pre_delete, sender=Character)
def pre_delete_character_reset(sender, instance, **kwargs):
    reset_event_cache_all_runs(instance.event)


@receiver(pre_save, sender=Faction)
def pre_save_faction_reset(sender, instance, **kwargs):
    handle_faction_pre_save(instance)


@receiver(pre_delete, sender=Faction)
def pre_delete_faction_reset(sender, instance, **kwargs):
    reset_event_cache_all_runs(instance.event)


@receiver(pre_save, sender=QuestType)
def pre_save_questtype_reset(sender, instance, **kwargs):
    handle_quest_type_presave(instance)


@receiver(pre_delete, sender=QuestType)
def pre_delete_quest_type_reset(sender, instance, **kwargs):
    reset_event_cache_all_runs(instance.event)


@receiver(pre_save, sender=Quest)
def pre_save_quest_reset(sender, instance, **kwargs):
    handle_quest_presave(instance)


@receiver(pre_delete, sender=Quest)
def pre_delete_quest_reset(sender, instance, **kwargs):
    reset_event_cache_all_runs(instance.event)


@receiver(pre_save, sender=Trait)
def pre_save_trait_reset(sender, instance, **kwargs):
    handle_trait_presave(instance)


@receiver(pre_delete, sender=Trait)
def pre_delete_trait_reset(sender, instance, **kwargs):
    reset_event_cache_all_runs(instance.event)


@receiver(pre_delete, sender=WritingQuestion)
def pre_delete_character_question_reset(sender, instance, **kwargs):
    reset_event_cache_all_runs(instance.event)


@receiver(pre_delete, sender=WritingOption)
def pre_delete_character_option_reset(sender, instance, **kwargs):
    reset_event_cache_all_runs(instance.question.event)


@receiver(pre_delete, sender=Run)
def pre_delete_run_reset(sender, instance, **kwargs):
    reset_run(instance)


@receiver(pre_save, sender=PaymentInvoice)
def pre_save_payment_invoice(sender, instance, **kwargs):
    process_payment_invoice_status_change(instance)


@receiver(pre_save, sender=RefundRequest)
def pre_save_refund_request(sender, instance, **kwargs):
    process_refund_request_status_change(instance)


@receiver(pre_save, sender=Collection)
def pre_save_collection_status(sender, instance, **kwargs):
    process_collection_status_change(instance)


@receiver(pre_save, sender=Registration)
def pre_save_registration_surcharge(sender, instance, *args, **kwargs):
    process_registration_pre_save(instance)


@receiver(pre_save, sender=AccountingItemMembership)
def pre_save_accounting_item_membership(sender, instance, *args, **kwargs):
    handle_membership_payment_notification(instance)


@receiver(pre_save, sender=HelpQuestion)
def pre_save_notify_help_question(sender, instance, **kwargs):
    handle_help_question_notification(instance)


@receiver(pre_save, sender=ChatMessage)
def pre_save_notify_chat_message(sender, instance, **kwargs):
    handle_chat_message_notification(instance)


@receiver(pre_save, sender=Registration)
def pre_save_registration_switch_event(sender, instance, **kwargs):
    handle_registration_event_switch(instance)


@receiver(pre_save, sender=Character)
def pre_save_character_char_names(sender, instance, *args, **kwargs):
    handle_replace_char_names(instance)


m2m_changed.connect(character_factions_changed, sender=Faction.characters.through)

m2m_changed.connect(handle_faction_characters_changed, sender=Faction.characters.through)
m2m_changed.connect(handle_plot_characters_changed, sender=Plot.characters.through)
m2m_changed.connect(handle_speedlarp_characters_changed, sender=SpeedLarp.characters.through)
m2m_changed.connect(handle_prologue_characters_changed, sender=Prologue.characters.through)

m2m_changed.connect(assoc_roles_changed, sender=AssocRole.members.through)

m2m_changed.connect(event_roles_changed, sender=EventRole.members.through)

m2m_changed.connect(badges_changed, sender=Badge.members.through)
