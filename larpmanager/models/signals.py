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
from typing import Any

from django.contrib.auth.models import User
from django.core.signals import got_request_exception
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from paypal.standard.ipn.signals import invalid_ipn_received, valid_ipn_received

from larpmanager.accounting.base import (
    handle_accounting_item_collection_post_save,
    handle_accounting_item_payment_pre_save,
    handle_collection_pre_save,
)
from larpmanager.accounting.gateway import handle_invalid_paypal_ipn, handle_valid_paypal_ipn
from larpmanager.accounting.payment import (
    process_collection_status_change,
    process_payment_invoice_status_change,
    process_refund_request_status_change,
)
from larpmanager.accounting.registration import (
    handle_registration_accounting_updates,
    log_registration_ticket_saved,
    process_accounting_discount_post_save,
    process_registration_option_post_save,
    process_registration_pre_save,
)
from larpmanager.accounting.token_credit import (
    update_credit_on_expense_save,
    update_token_credit_on_other_save,
    update_token_credit_on_payment_delete,
    update_token_credit_on_payment_save,
)
from larpmanager.accounting.vat import calculate_payment_vat
from larpmanager.cache.accounting import clear_registration_accounting_cache, refresh_member_accounting_cache
from larpmanager.cache.association import clear_association_cache
from larpmanager.cache.association_text import (
    clear_association_text_cache_on_delete,
    update_association_text_cache_on_save,
)
from larpmanager.cache.association_translation import clear_association_translation_cache
from larpmanager.cache.button import clear_event_button_cache
from larpmanager.cache.character import (
    clear_event_cache_all_runs,
    clear_run_cache_and_media,
    on_character_pre_save_update_cache,
    on_faction_pre_save_update_cache,
    on_quest_pre_save_update_cache,
    on_quest_type_pre_save_update_cache,
    on_trait_pre_save_update_cache,
    reset_character_registration_cache,
    update_member_event_character_cache,
)
from larpmanager.cache.config import clear_config_cache
from larpmanager.cache.event_text import clear_event_text_cache_on_delete, update_event_text_cache_on_save
from larpmanager.cache.feature import clear_event_features_cache, on_association_post_save_reset_features_cache
from larpmanager.cache.fields import clear_event_fields_cache
from larpmanager.cache.larpmanager import clear_larpmanager_home_cache
from larpmanager.cache.links import (
    clear_run_event_links_cache,
    on_registration_post_save_reset_event_links,
    reset_event_links,
)
from larpmanager.cache.permission import (
    clear_association_permission_cache,
    clear_event_permission_cache,
    clear_index_permission_cache,
)
from larpmanager.cache.registration import clear_registration_counts_cache, on_character_update_registration_cache
from larpmanager.cache.rels import (
    clear_event_relationships_cache,
    on_faction_characters_m2m_changed,
    on_plot_characters_m2m_changed,
    on_prologue_characters_m2m_changed,
    on_speedlarp_characters_m2m_changed,
    refresh_character_related_caches,
    refresh_character_relationships,
    refresh_event_faction_relationships,
    refresh_event_plot_relationships,
    refresh_event_prologue_relationships,
    refresh_event_quest_relationships,
    refresh_event_questtype_relationships,
    refresh_event_speedlarp_relationships,
    remove_item_from_cache_section,
)
from larpmanager.cache.role import remove_association_role_cache, remove_event_role_cache
from larpmanager.cache.run import (
    on_event_post_save_reset_config_cache,
    on_event_pre_save_invalidate_cache,
    on_run_post_save_reset_config_cache,
    on_run_pre_save_invalidate_cache,
)
from larpmanager.cache.skin import clear_skin_cache
from larpmanager.cache.text_fields import update_text_fields_cache
from larpmanager.cache.wwyltd import reset_features_cache, reset_guides_cache, reset_tutorials_cache
from larpmanager.mail.accounting import (
    send_collection_activation_email,
    send_donation_confirmation_email,
    send_expense_approval_email,
    send_expense_notification_email,
    send_gift_collection_notification_email,
    send_payment_confirmation_email,
    send_token_credit_notification_email,
)
from larpmanager.mail.base import (
    on_association_roles_m2m_changed,
    on_event_roles_m2m_changed,
    send_character_status_update_email,
    send_support_ticket_email,
    send_trait_assignment_email,
)
from larpmanager.mail.member import (
    on_member_badges_m2m_changed,
    send_chat_message_notification_email,
    send_help_question_notification_email,
    send_membership_payment_notification_email,
)
from larpmanager.mail.registration import (
    send_character_assignment_email,
    send_pre_registration_confirmation_email,
    send_registration_cancellation_email,
    send_registration_deletion_email,
)
from larpmanager.models.access import AssociationPermission, AssociationRole, EventPermission, EventRole
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
from larpmanager.models.association import (
    Association,
    AssociationConfig,
    AssociationSkin,
    AssociationText,
    AssociationTranslation,
)
from larpmanager.models.base import Feature, FeatureModule, auto_assign_sequential_numbers, update_model_search_field
from larpmanager.models.casting import AssignmentTrait, Quest, QuestType, Trait, refresh_all_instance_traits
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
    replace_character_names,
)
from larpmanager.utils.association import (
    apply_skin_features_to_association,
    auto_assign_association_permission_number,
    generate_association_encryption_key,
    prepare_association_skin_features,
)
from larpmanager.utils.auth import auto_assign_event_permission_number
from larpmanager.utils.event import (
    assign_previous_campaign_character,
    copy_parent_event_to_campaign,
    create_default_event_setup,
    prepare_campaign_event_data,
    update_run_plan_on_event_change,
)
from larpmanager.utils.experience import (
    calculate_character_experience_points,
    on_experience_characters_m2m_changed,
    on_modifier_abilities_m2m_changed,
    on_rule_abilities_m2m_changed,
    refresh_delivery_characters,
    update_characters_experience_on_ability_change,
    update_characters_experience_on_modifier_change,
    update_characters_experience_on_rule_change,
)
from larpmanager.utils.larpmanager import auto_assign_faq_sequential_number, generate_tutorial_url_slug
from larpmanager.utils.member import create_member_profile_for_user, process_membership_status_updates
from larpmanager.utils.miscellanea import auto_rotate_vertical_photos
from larpmanager.utils.pdf import (
    cleanup_character_pdfs_before_delete,
    cleanup_character_pdfs_on_save,
    cleanup_faction_pdfs_before_delete,
    cleanup_faction_pdfs_on_save,
    cleanup_handout_pdfs_after_save,
    cleanup_handout_pdfs_before_delete,
    cleanup_handout_template_pdfs_after_save,
    cleanup_handout_template_pdfs_before_delete,
    cleanup_pdfs_on_trait_assignment,
    cleanup_relationship_pdfs_after_save,
    cleanup_relationship_pdfs_before_delete,
    deactivate_castings_and_remove_pdfs,
    delete_character_pdf_files,
)
from larpmanager.utils.registration import process_character_ticket_options, process_registration_event_change
from larpmanager.utils.ticket import create_error_ticket
from larpmanager.utils.writing import replace_character_names_before_save

log = logging.getLogger(__name__)


# Generic signal handlers (no specific sender)
@receiver(pre_save)
def pre_save_callback(sender: type, instance: object, *args: any, **kwargs: any) -> None:
    """Generic pre-save handler for automatic field population.

    Automatically sets number/order fields and updates search fields
    for models that have them. This function is designed to be used
    as a Django model signal handler.

    Parameters
    ----------
    sender : type
        Model class sending the signal
    instance : object
        Model instance being saved
    *args : any
        Additional positional arguments passed by Django signal
    **kwargs : any
        Additional keyword arguments passed by Django signal

    Returns
    -------
    None
        This function performs side effects on the instance
    """
    # Auto-assign sequential numbers for models with number/order fields
    auto_assign_sequential_numbers(instance)

    # Update search fields for models that implement search functionality
    update_model_search_field(instance)


@receiver(post_save)
def post_save_text_fields_callback(sender, instance, *args, **kwargs):
    update_text_fields_cache(instance)


@receiver(post_delete)
def post_delete_text_fields_callback(sender, instance, **kwargs):
    update_text_fields_cache(instance)


# AbilityPx signals
@receiver(post_save, sender=AbilityPx)
def post_save_ability_px(sender, instance, *args, **kwargs):
    update_characters_experience_on_ability_change(instance)


@receiver(post_delete, sender=AbilityPx)
def post_delete_ability_px(sender, instance, *args, **kwargs):
    update_characters_experience_on_ability_change(instance)


# AccountingItemCollection signals
@receiver(pre_save, sender=AccountingItemCollection)
def pre_save_collection_gift(sender, instance, **kwargs):
    send_gift_collection_notification_email(instance)


@receiver(post_save, sender=AccountingItemCollection)
def post_save_accounting_item_collection(sender, instance, created, **kwargs):
    handle_accounting_item_collection_post_save(instance)


# AccountingItemDiscount signals
@receiver(post_save, sender=AccountingItemDiscount)
def post_save_discount_accounting_cache(sender, instance, created, **kwargs):
    process_accounting_discount_post_save(instance)
    if instance.run and instance.member_id:
        refresh_member_accounting_cache(instance.run, instance.member_id)


@receiver(post_delete, sender=AccountingItemDiscount)
def post_delete_discount_accounting_cache(sender, instance, **kwargs):
    if instance.run and instance.member_id:
        refresh_member_accounting_cache(instance.run, instance.member_id)


# AccountingItemDonation signals
@receiver(pre_save, sender=AccountingItemDonation)
def pre_save_accounting_item_donation(sender, instance, *args, **kwargs):
    send_donation_confirmation_email(instance)


# AccountingItemExpense signals
@receiver(pre_save, sender=AccountingItemExpense)
def pre_save_accounting_item_expense(sender, instance, **kwargs):
    send_expense_approval_email(instance)


@receiver(post_save, sender=AccountingItemExpense)
def post_save_accounting_item_expense(sender, instance, created, **kwargs):
    send_expense_notification_email(instance, created)
    update_credit_on_expense_save(instance)


# AccountingItemMembership signals
@receiver(pre_save, sender=AccountingItemMembership)
def pre_save_accounting_item_membership(sender, instance, *args, **kwargs):
    send_membership_payment_notification_email(instance)


# AccountingItemOther signals
@receiver(pre_save, sender=AccountingItemOther)
def pre_save_accounting_item_other(sender, instance, **kwargs):
    send_token_credit_notification_email(instance)


@receiver(post_save, sender=AccountingItemOther)
def post_save_other_accounting_cache(sender, instance, created, **kwargs):
    update_token_credit_on_other_save(instance)
    if instance.run and instance.member_id:
        refresh_member_accounting_cache(instance.run, instance.member_id)


@receiver(post_delete, sender=AccountingItemOther)
def post_delete_other_accounting_cache(sender, instance, **kwargs):
    if instance.run and instance.member_id:
        refresh_member_accounting_cache(instance.run, instance.member_id)


# AccountingItemPayment signals
@receiver(pre_save, sender=AccountingItemPayment)
def pre_save_accounting_item_payment(sender, instance, **kwargs):
    send_payment_confirmation_email(instance)
    handle_accounting_item_payment_pre_save(instance)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_payment_accounting_cache(sender, instance: PaymentInvoice, created: bool, **kwargs) -> None:
    """Updates accounting caches and processes payment-related calculations after payment save."""

    # Update registration and member accounting cache if payment has associated registration
    if instance.reg and instance.reg.run:
        instance.reg.save()
        refresh_member_accounting_cache(instance.reg.run, instance.member_id)

    # Update token credits based on payment changes
    update_token_credit_on_payment_save(instance, created)

    # Calculate and update VAT information for the payment
    calculate_payment_vat(instance)


@receiver(post_delete, sender=AccountingItemPayment)
def post_delete_payment_accounting_cache(
    sender: type,
    instance: Any,
    **kwargs: Any,
) -> None:
    """Update accounting caches after payment deletion."""
    update_token_credit_on_payment_delete(instance)

    # Refresh member accounting cache if payment is linked to a registration
    if instance.reg and instance.reg.run:
        refresh_member_accounting_cache(instance.reg.run, instance.member_id)


# AssignmentTrait signals
@receiver(pre_delete, sender=AssignmentTrait)
def pre_delete_assignment_trait(sender, instance, **kwargs):
    deactivate_castings_and_remove_pdfs(instance)


@receiver(post_save, sender=AssignmentTrait)
def post_save_assignment_trait(
    sender: type,
    instance: AssignmentTrait,
    created: bool,
    **kwargs: dict,
) -> None:
    """Handle post-save actions for AssignmentTrait instances.

    Clears caches, sends notification emails, and manages PDF cleanup.
    """
    # Clear cached data and generated media for the run
    clear_run_cache_and_media(instance.run)

    # Notify relevant users about trait assignment
    send_trait_assignment_email(instance, created)

    # Remove outdated PDF files if necessary
    cleanup_pdfs_on_trait_assignment(instance, created)


@receiver(post_delete, sender=AssignmentTrait)
def post_delete_assignment_trait_reset(sender, instance, **kwargs):
    clear_run_cache_and_media(instance.run)


# AssociationPermission signals
@receiver(pre_save, sender=AssociationPermission)
def pre_save_association_permission(sender, instance, **kwargs):
    auto_assign_association_permission_number(instance)


@receiver(post_save, sender=AssociationPermission)
def post_save_association_permission_index_permission(sender, instance, **kwargs):
    clear_index_permission_cache("association")
    clear_association_permission_cache(instance)


@receiver(post_delete, sender=AssociationPermission)
def post_delete_association_permission_index_permission(sender, instance, **kwargs):
    clear_index_permission_cache("association")
    clear_association_permission_cache(instance)


# AssociationRole signals
@receiver(pre_delete, sender=AssociationRole)
def pre_delete_association_role_reset(sender, instance, **kwargs):
    remove_association_role_cache(instance.pk)
    for member in instance.members.all():
        reset_event_links(member.user.id, instance.association_id)


@receiver(post_save, sender=AssociationRole)
def post_save_association_role_reset(sender, instance, **kwargs):
    remove_association_role_cache(instance.pk)
    for member in instance.members.all():
        reset_event_links(member.user.id, instance.association_id)


# AssocText signals
@receiver(pre_delete, sender=AssociationText)
def pre_delete_association_text(sender, instance, **kwargs):
    clear_association_text_cache_on_delete(instance)


@receiver(post_save, sender=AssociationText)
def post_save_association_text(sender, instance, created, **kwargs):
    update_association_text_cache_on_save(instance)


# AssociationTranslation signals
@receiver(post_save, sender=AssociationTranslation)
def post_save_association_translation(sender, instance, created, **kwargs):
    """Clear cache when association translation is saved."""
    clear_association_translation_cache(instance.association_id, instance.language)


@receiver(pre_delete, sender=AssociationTranslation)
def pre_delete_association_translation(sender, instance, **kwargs):
    """Clear cache when association translation is deleted."""
    clear_association_translation_cache(instance.association_id, instance.language)


# Association signals
@receiver(pre_save, sender=Association)
def pre_save_association_set_skin_features(sender, instance, **kwargs):
    prepare_association_skin_features(instance)
    generate_association_encryption_key(instance)


@receiver(post_save, sender=Association)
def post_save_association_reset_lm_home(sender, instance, **kwargs) -> None:
    """Reset caches and apply features when an association is saved."""
    # Clear global home cache
    clear_larpmanager_home_cache()

    # Apply skin features to the association
    apply_skin_features_to_association(instance)

    # Clear association-specific cache
    clear_association_cache(instance.slug)

    # Reset features cache for this association
    on_association_post_save_reset_features_cache(instance)


# AssociationConfig signals
@receiver(post_save, sender=AssociationConfig)
def post_save_reset_association_config(sender, instance, **kwargs):
    clear_config_cache(instance.association)


@receiver(post_delete, sender=AssociationConfig)
def post_delete_reset_association_config(sender, instance, **kwargs):
    clear_config_cache(instance.association)


# AssociationSkin signals
@receiver(post_save, sender=AssociationSkin)
def post_save_association_skin_reset_cache(sender, instance, **kwargs):
    clear_skin_cache(instance.domain)


# Character signals
@receiver(pre_save, sender=Character)
def pre_save_character_update_status(sender: type, instance: Character, **kwargs: Any) -> None:
    """Update character status and cache before saving.

    Args:
        sender: Model class sending the signal.
        instance: Character instance being saved.
        **kwargs: Additional signal arguments.
    """
    # Send email notification for character status changes
    send_character_status_update_email(instance)

    # Replace character name placeholders in related fields
    replace_character_names_before_save(instance)

    # Update cached character data
    on_character_pre_save_update_cache(instance)


@receiver(post_save, sender=Character, dispatch_uid="post_character_update_px_v1")
def post_character_update_px(sender, instance, *args, **kwargs):
    calculate_character_experience_points(instance)


@receiver(post_save, sender=Character)
def post_save_character(sender: type, instance: Character, **kwargs) -> None:
    """Handle post-save operations for Character model instances.

    This signal handler performs several maintenance tasks after a Character
    instance is saved, including PDF cleanup, cache updates, and relationship
    refreshes to maintain data consistency across the application.

    Args:
        sender: The model class that sent the signal (Character).
        instance: The Character instance that was saved.
        **kwargs: Additional keyword arguments from the signal.

    Returns:
        None
    """
    # Clean up any outdated PDF files associated with this character
    cleanup_character_pdfs_on_save(instance)

    # Update registration-related cache entries for this character
    on_character_update_registration_cache(instance)

    # Refresh the character's own relationship cache
    refresh_character_relationships(instance)

    # Update relationship caches for all characters that have this character as a target
    for rel in Relationship.objects.filter(target=instance):
        refresh_character_relationships(rel.source)

    # Update all other character-related caches (experience, skills, etc.)
    refresh_character_related_caches(instance)


@receiver(pre_delete, sender=Character)
def pre_delete_character_reset(sender, instance, **kwargs):
    clear_event_cache_all_runs(instance.event)
    cleanup_character_pdfs_before_delete(instance)


@receiver(post_delete, sender=Character)
def post_delete_character_reset_rels(sender: type, instance: Character, **kwargs: Any) -> None:
    """Clear caches for deleted character and update related relationships."""
    # Update all related caches
    refresh_character_related_caches(instance)

    # Clear event-level relationship cache
    clear_event_relationships_cache(instance.event_id)

    # Refresh cache for characters that had this character as target
    for rel in Relationship.objects.filter(target=instance):
        refresh_character_relationships(rel.source)


# CharacterConfig signals
@receiver(post_save, sender=CharacterConfig)
def post_save_reset_character_config(sender, instance, **kwargs):
    clear_config_cache(instance.character)


@receiver(post_delete, sender=CharacterConfig)
def post_delete_reset_character_config(sender, instance, **kwargs):
    clear_config_cache(instance.character)


# ChatMessage signals
@receiver(pre_save, sender=ChatMessage)
def pre_save_notify_chat_message(sender, instance, **kwargs):
    send_chat_message_notification_email(instance)


# Collection signals
@receiver(pre_save, sender=Collection)
def pre_save_collection(sender, instance, **kwargs):
    handle_collection_pre_save(instance)
    process_collection_status_change(instance)


@receiver(post_save, sender=Collection)
def post_save_collection_activation_email(sender, instance, created, **kwargs):
    send_collection_activation_email(instance, created)


# DeliveryPx signals
@receiver(post_save, sender=DeliveryPx)
def post_save_delivery_px(sender, instance, *args, **kwargs):
    refresh_delivery_characters(instance)


@receiver(post_delete, sender=DeliveryPx)
def post_delete_delivery_px(sender, instance, *args, **kwargs):
    refresh_delivery_characters(instance)


# Event signals
@receiver(pre_save, sender=Event)
def pre_save_event(sender, instance, **kwargs):
    on_event_pre_save_invalidate_cache(instance)
    prepare_campaign_event_data(instance)


@receiver(post_save, sender=Event)
def post_save_event_update(sender: type, instance: Event, **kwargs) -> None:
    """Handle post-save operations for Event model instances.

    This function is triggered after an Event instance is saved and performs
    various cache invalidation and setup operations to maintain data consistency.

    Args:
        sender: The model class that sent the signal
        instance: The Event instance that was saved
        **kwargs: Additional keyword arguments from the signal

    Returns:
        None
    """
    # Clear event-related caches to ensure fresh data
    clear_event_cache_all_runs(instance)
    clear_event_features_cache(instance.id)

    # Setup campaign inheritance if not explicitly skipped
    if not getattr(instance, "_skip_campaign_setup", False):
        copy_parent_event_to_campaign(instance)

    # Clear run and registration related caches
    clear_run_event_links_cache(instance)

    # Clear registration counts for all associated runs
    for run_id in instance.runs.values_list("id", flat=True):
        clear_registration_counts_cache(run_id)

    # Reset configuration cache and create default setup
    on_event_post_save_reset_config_cache(instance)
    create_default_event_setup(instance)


@receiver(post_delete, sender=Event)
def post_delete_event_links(sender, instance, **kwargs):
    clear_run_event_links_cache(instance)


# EventButton signals
@receiver(post_save, sender=EventButton)
def post_save_event_button(sender, instance, created, **kwargs):
    clear_event_button_cache(instance.event_id)


@receiver(pre_delete, sender=EventButton)
def pre_delete_event_button(sender, instance, **kwargs):
    clear_event_button_cache(instance.event_id)


# EventConfig signals
@receiver(post_save, sender=EventConfig)
def post_save_reset_event_config(sender, instance, **kwargs):
    clear_config_cache(instance.event)


@receiver(post_delete, sender=EventConfig)
def post_delete_reset_event_config(sender, instance, **kwargs):
    clear_config_cache(instance.event)


# EventPermission signals
@receiver(pre_save, sender=EventPermission)
def pre_save_event_permission(sender, instance, **kwargs):
    auto_assign_event_permission_number(instance)


@receiver(post_save, sender=EventPermission)
def post_save_event_permission_reset(sender, instance, **kwargs):
    clear_event_permission_cache(instance)
    clear_index_permission_cache("event")


@receiver(post_delete, sender=EventPermission)
def post_delete_event_permission_reset(sender, instance, **kwargs):
    clear_event_permission_cache(instance)
    clear_index_permission_cache("event")


# EventRole signals
@receiver(pre_delete, sender=EventRole)
def pre_delete_event_role_reset(sender, instance, **kwargs):
    remove_event_role_cache(instance.pk)
    for member in instance.members.all():
        reset_event_links(member.user.id, instance.event.association_id)


@receiver(post_save, sender=EventRole)
def post_save_event_role_reset(sender, instance, **kwargs):
    remove_event_role_cache(instance.pk)
    for member in instance.members.all():
        reset_event_links(member.user.id, instance.event.association_id)


# EventText signals
@receiver(pre_delete, sender=EventText)
def pre_delete_event_text(sender, instance, **kwargs):
    clear_event_text_cache_on_delete(instance)


@receiver(post_save, sender=EventText)
def post_save_event_text(sender, instance, created, **kwargs):
    update_event_text_cache_on_save(instance)


# Faction signals
@receiver(pre_save, sender=Faction)
def pre_save_faction(sender, instance, *args, **kwargs):
    replace_character_names(instance)
    on_faction_pre_save_update_cache(instance)


@receiver(post_save, sender=Faction)
def post_save_faction_reset_rels(sender, instance: Faction, **kwargs) -> None:
    """Reset faction relationships and update character caches after faction save.

    Args:
        sender: The model class that sent the signal
        instance: The faction instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Update faction cache for event relationships
    refresh_event_faction_relationships(instance)

    # Update cache for all characters belonging to this faction
    for char in instance.characters.all():
        refresh_character_relationships(char)

    # Clean up faction PDFs after save operation
    cleanup_faction_pdfs_on_save(instance)


@receiver(pre_delete, sender=Faction)
def pre_delete_faction(sender, instance, **kwargs):
    cleanup_faction_pdfs_before_delete(instance)
    clear_event_cache_all_runs(instance.event)


@receiver(post_delete, sender=Faction)
def post_delete_faction_reset_rels(sender, instance, **kwargs) -> None:
    """Reset character relationships when a faction is deleted."""
    # Update cache for all characters that were in this faction
    for char in instance.characters.all():
        refresh_character_relationships(char)

    # Remove faction from cache
    remove_item_from_cache_section(instance.event_id, "factions", instance.id)


# Feature signals
@receiver(post_save, sender=Feature)
def post_save_feature_index_permission(sender: type, instance: object, **kwargs: dict) -> None:
    """Clear permission and feature caches after feature/permission save."""
    clear_index_permission_cache("event")
    clear_index_permission_cache("association")
    reset_features_cache()


@receiver(post_delete, sender=Feature)
def post_delete_feature_index_permission(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear permission and feature caches after deleting feature index permission."""
    # Clear both event and association permission caches
    clear_index_permission_cache("event")
    clear_index_permission_cache("association")

    # Reset global features cache
    reset_features_cache()


# FeatureModule signals
@receiver(post_save, sender=FeatureModule)
def post_save_feature_module_index_permission(sender: type, instance: object, **kwargs: object) -> None:
    """Clear cached permissions and features after feature/module/permission changes."""
    # Clear cached index permissions for event and organization contexts
    clear_index_permission_cache("event")
    clear_index_permission_cache("association")

    # Invalidate the global features cache
    reset_features_cache()


@receiver(post_delete, sender=FeatureModule)
def post_delete_feature_module_index_permission(
    sender: type,
    instance: object,
    **kwargs: object,
) -> None:
    """Clear permission and feature caches after deletion."""
    clear_index_permission_cache("event")
    clear_index_permission_cache("association")
    reset_features_cache()


# Handout signals
@receiver(pre_delete, sender=Handout)
def pre_delete_handout(sender, instance, **kwargs):
    cleanup_handout_pdfs_before_delete(instance)


@receiver(post_save, sender=Handout)
def post_save_handout(sender, instance, **kwargs):
    cleanup_handout_pdfs_after_save(instance)


# HandoutTemplate signals
@receiver(pre_delete, sender=HandoutTemplate)
def pre_delete_handout_template(sender, instance, **kwargs):
    cleanup_handout_template_pdfs_before_delete(instance)


@receiver(post_save, sender=HandoutTemplate)
def post_save_handout_template(sender, instance, **kwargs):
    cleanup_handout_template_pdfs_after_save(instance)


# HelpQuestion signals
@receiver(pre_save, sender=HelpQuestion)
def pre_save_notify_help_question(sender, instance, **kwargs):
    send_help_question_notification_email(instance)


# LarpManagerFaq signals
@receiver(pre_save, sender=LarpManagerFaq)
def pre_save_larp_manager_faq(sender, instance, *args, **kwargs):
    auto_assign_faq_sequential_number(instance)


# LarpManagerGuide signals
@receiver(post_save, sender=LarpManagerGuide)
def post_save_reset_guides_cache(sender, instance, **kwargs):
    reset_guides_cache()


@receiver(post_delete, sender=LarpManagerGuide)
def post_delete_reset_guides_cache(sender, instance, **kwargs):
    reset_guides_cache()


# LarpManagerTicket signals
@receiver(post_save, sender=LarpManagerTicket)
def save_larpmanager_ticket(sender, instance, created, **kwargs):
    send_support_ticket_email(instance)


# LarpManagerTutorial signals
@receiver(pre_save, sender=LarpManagerTutorial)
def pre_save_larp_manager_tutorial(sender, instance, *args, **kwargs):
    generate_tutorial_url_slug(instance)


@receiver(post_save, sender=LarpManagerTutorial)
def post_save_reset_tutorials_cache(sender, instance, **kwargs):
    reset_tutorials_cache()


@receiver(post_delete, sender=LarpManagerTutorial)
def post_delete_reset_tutorials_cache(sender, instance, **kwargs):
    reset_tutorials_cache()


# Member signals
@receiver(post_save, sender=Member)
def post_save_member_reset(sender, instance, **kwargs):
    update_member_event_character_cache(instance)


# MemberConfig signals
@receiver(post_save, sender=MemberConfig)
def post_save_reset_member_config(sender, instance, **kwargs):
    clear_config_cache(instance.member)


@receiver(post_delete, sender=MemberConfig)
def post_delete_reset_member_config(sender, instance, **kwargs):
    clear_config_cache(instance.member)


# Membership signals
@receiver(pre_save, sender=Membership)
def pre_save_membership(sender, instance, **kwargs):
    process_membership_status_updates(instance)


# ModifierPx signals
@receiver(post_save, sender=ModifierPx)
def post_save_modifier_px(sender, instance, *args, **kwargs):
    update_characters_experience_on_modifier_change(instance)


@receiver(post_delete, sender=ModifierPx)
def post_delete_modifier_px(sender, instance, *args, **kwargs):
    update_characters_experience_on_modifier_change(instance)


# PaymentInvoice signals
@receiver(pre_save, sender=PaymentInvoice)
def pre_save_payment_invoice(sender, instance, **kwargs):
    process_payment_invoice_status_change(instance)


# PlayerRelationship signals
@receiver(pre_delete, sender=PlayerRelationship)
def pre_delete_player_relationship(sender, instance, **kwargs):
    cleanup_relationship_pdfs_before_delete(instance)


@receiver(post_save, sender=PlayerRelationship)
def post_save_player_relationship(sender, instance, **kwargs):
    cleanup_relationship_pdfs_after_save(instance)


# Plot signals
@receiver(pre_save, sender=Plot)
def pre_save_plot(sender, instance, *args, **kwargs):
    replace_character_names(instance)


@receiver(post_save, sender=Plot)
def post_save_plot_reset_rels(sender: type, instance: Plot, **kwargs: Any) -> None:
    """Update plot and character relationship caches after plot save."""
    # Update plot cache
    refresh_event_plot_relationships(instance)

    # Update cache for all characters in this plot
    for char_rel in instance.get_plot_characters():
        refresh_character_relationships(char_rel.character)


@receiver(post_delete, sender=Plot)
def post_delete_plot_reset_rels(sender, instance: Plot, **kwargs: Any) -> None:
    """Reset character relationships and cache when a plot is deleted."""
    # Update cache for all characters that were in this plot
    for char_rel in instance.get_plot_characters():
        refresh_character_relationships(char_rel.character)

    # Remove plot from cache
    remove_item_from_cache_section(instance.event_id, "plots", instance.id)


# PreRegistration signals
@receiver(pre_save, sender=PreRegistration)
def pre_save_pre_registration(sender, instance, **kwargs):
    send_pre_registration_confirmation_email(instance)


# Prologue signals
@receiver(pre_save, sender=Prologue)
def pre_save_prologue(sender, instance, *args, **kwargs):
    replace_character_names(instance)


@receiver(post_save, sender=Prologue)
def post_save_prologue_reset_rels(sender, instance: Prologue, **kwargs: Any) -> None:
    """Reset relationship cache for prologue and associated characters."""
    # Update prologue cache
    refresh_event_prologue_relationships(instance)

    # Update cache for all characters in this prologue
    for char in instance.characters.all():
        refresh_character_relationships(char)


@receiver(post_delete, sender=Prologue)
def post_delete_prologue_reset_rels(sender, instance, **kwargs) -> None:
    """Reset character relationships and cache when prologue is deleted."""
    # Update cache for all characters that were in this prologue
    for char in instance.characters.all():
        refresh_character_relationships(char)

    # Remove prologue from cache
    remove_item_from_cache_section(instance.event_id, "prologues", instance.id)


# Quest signals
@receiver(pre_save, sender=Quest)
def pre_save_quest_reset(sender, instance, **kwargs):
    on_quest_pre_save_update_cache(instance)


@receiver(post_save, sender=Quest)
def post_save_quest_reset_rels(sender, instance: Quest, **kwargs: Any) -> None:
    """Update quest and questtype cache relationships after quest save."""
    # Update quest cache
    refresh_event_quest_relationships(instance)

    # Update questtype cache if quest has a type
    if instance.typ:
        refresh_event_questtype_relationships(instance.typ)


@receiver(pre_delete, sender=Quest)
def pre_delete_quest_reset(sender, instance, **kwargs):
    clear_event_cache_all_runs(instance.event)


@receiver(post_delete, sender=Quest)
def post_delete_quest_reset_rels(sender, instance, **kwargs) -> None:
    """Reset quest relationships after quest deletion.

    Args:
        sender: The model class that sent the signal
        instance: The quest instance being deleted
        **kwargs: Additional keyword arguments from the signal
    """
    # Update questtype cache if quest had a type
    if instance.typ:
        refresh_event_questtype_relationships(instance.typ)

    # Remove quest from cache
    remove_item_from_cache_section(instance.event_id, "quests", instance.id)


# QuestType signals
@receiver(pre_save, sender=QuestType)
def pre_save_questtype_reset(sender, instance, **kwargs):
    on_quest_type_pre_save_update_cache(instance)


@receiver(post_save, sender=QuestType)
def post_save_questtype_reset_rels(
    sender: type,
    instance: QuestType,
    **kwargs: Any,
) -> None:
    """Reset quest type and related quest caches after save.

    Args:
        sender: The model class that sent the signal.
        instance: The QuestType instance being saved.
        **kwargs: Additional keyword arguments from the signal.
    """
    # Update questtype cache
    refresh_event_questtype_relationships(instance)

    # Update cache for all quests of this type
    for quest in instance.quests.all():
        refresh_event_quest_relationships(quest)


@receiver(pre_delete, sender=QuestType)
def pre_delete_quest_type_reset(sender, instance, **kwargs):
    clear_event_cache_all_runs(instance.event)


@receiver(post_delete, sender=QuestType)
def post_delete_questtype_reset_rels(sender, instance: QuestType, **kwargs) -> None:
    """Reset quest relationships when a quest type is deleted."""
    # Update cache for all quests that were of this type
    for quest in instance.quests.all():
        refresh_event_quest_relationships(quest)

    # Remove questtype from cache
    remove_item_from_cache_section(instance.event_id, "questtypes", instance.id)


# RefundRequest signals
@receiver(pre_save, sender=RefundRequest)
def pre_save_refund_request(sender, instance, **kwargs):
    process_refund_request_status_change(instance)


# Registration signals
@receiver(pre_save, sender=Registration)
def pre_save_registration_switch_event(sender: type, instance: Registration, **kwargs: Any) -> None:
    """Handle registration updates when switching events."""
    # Process event change logic
    process_registration_event_change(instance)

    # Send cancellation notification if needed
    send_registration_cancellation_email(instance)

    # Execute pre-save registration processing
    process_registration_pre_save(instance)


@receiver(post_save, sender=Registration)
def post_save_registration_cache(sender: type, instance: Registration, created: bool, **kwargs) -> None:
    """Handle post-save operations for Registration instances.

    This signal handler performs various cache updates and business logic
    operations after a Registration instance is saved to the database.

    Args:
        sender: The model class that sent the signal
        instance: The Registration instance that was saved
        created: True if this is a new instance, False if updated
        **kwargs: Additional keyword arguments from the signal

    Returns:
        None
    """
    # Assign character from previous campaign if applicable
    assign_previous_campaign_character(instance)

    # Process ticket options and character-related data
    process_character_ticket_options(instance)

    # Update accounting records and balances
    handle_registration_accounting_updates(instance)

    # Clear cached accounting data for this run
    clear_registration_accounting_cache(instance.run_id)

    # Reset event navigation links cache
    on_registration_post_save_reset_event_links(instance)

    # Update registration count caches for this run
    clear_registration_counts_cache(instance.run_id)


@receiver(pre_delete, sender=Registration)
def pre_delete_registration(sender, instance, *args, **kwargs):
    send_registration_deletion_email(instance)


@receiver(post_delete, sender=Registration)
def post_delete_registration_accounting_cache(sender, instance, **kwargs):
    clear_registration_accounting_cache(instance.run_id)


# RegistrationCharacterRel signals
@receiver(post_save, sender=RegistrationCharacterRel)
def post_save_registration_character_rel_savereg(sender, instance, created, **kwargs):
    reset_character_registration_cache(instance)
    send_character_assignment_email(instance, created)


@receiver(post_delete, sender=RegistrationCharacterRel)
def post_delete_registration_character_rel_savereg(sender, instance, **kwargs):
    reset_character_registration_cache(instance)


# RegistrationOption signals
@receiver(post_save, sender=RegistrationOption)
def post_save_registration_option(sender, instance, created, **kwargs):
    process_registration_option_post_save(instance)


# RegistrationTicket signals
@receiver(post_save, sender=RegistrationTicket)
def post_save_ticket_accounting_cache(
    sender: type,
    instance: Any,
    created: bool,
    **kwargs: Any,
) -> None:
    """Clears accounting cache for all runs when a ticket is saved."""
    log_registration_ticket_saved(instance)

    # Clear accounting cache for all runs in the ticket's event
    for run in instance.event.runs.all():
        clear_registration_accounting_cache(run.id)


@receiver(post_delete, sender=RegistrationTicket)
def post_delete_ticket_accounting_cache(sender, instance, **kwargs):
    for run in instance.event.runs.all():
        clear_registration_accounting_cache(run.id)


# Relationship signals
@receiver(pre_delete, sender=Relationship)
def pre_delete_relationship(sender, instance, **kwargs):
    delete_character_pdf_files(instance.source)


@receiver(post_save, sender=Relationship)
def post_save_relationship_reset_rels(sender: type, instance: Any, **kwargs: Any) -> None:
    # Update cached relationships and delete PDF files after saving a relationship
    refresh_character_relationships(instance.source)
    delete_character_pdf_files(instance.source)


@receiver(post_delete, sender=Relationship)
def post_delete_relationship_reset_rels(sender, instance, **kwargs):
    # Update cache for source character
    refresh_character_relationships(instance.source)


# RulePx signals
@receiver(post_save, sender=RulePx)
def post_save_rule_px(sender, instance, *args, **kwargs):
    update_characters_experience_on_rule_change(instance)


@receiver(post_delete, sender=RulePx)
def post_delete_rule_px(sender, instance, *args, **kwargs):
    update_characters_experience_on_rule_change(instance)


# Run signals
@receiver(pre_save, sender=Run)
def pre_save_run(sender, instance, **kwargs):
    on_run_pre_save_invalidate_cache(instance)


@receiver(post_save, sender=Run)
def post_save_run_links(sender: type, instance: Run, **kwargs: Any) -> None:
    """Handle post-save actions for Run model instances.

    This signal handler performs cache clearing and configuration updates
    when a Run instance is saved. It handles both new runs and updates
    to existing runs, with special handling for development status changes.

    Args:
        sender: The model class that sent the signal
        instance: The Run instance that was saved
        **kwargs: Additional keyword arguments from the signal
    """
    # Clear registration-related caches for this run
    clear_registration_counts_cache(instance.id)

    # Reset configuration cache when run changes
    on_run_post_save_reset_config_cache(instance)

    # Update run plan based on event changes
    update_run_plan_on_event_change(instance)

    # Clear run-specific cache and media files
    clear_run_cache_and_media(instance)

    clear_run_event_links_cache(instance.event)


@receiver(pre_delete, sender=Run)
def pre_delete_run_reset(sender, instance, **kwargs):
    clear_run_cache_and_media(instance)


@receiver(post_delete, sender=Run)
def post_delete_run_links(sender, instance, **kwargs):
    clear_run_event_links_cache(instance.event)


# RunConfig signals
@receiver(post_save, sender=RunConfig)
def post_save_reset_run_config(sender, instance, **kwargs):
    clear_config_cache(instance.run)


@receiver(post_delete, sender=RunConfig)
def post_delete_reset_run_config(sender, instance, **kwargs):
    clear_config_cache(instance.run)


# SpeedLarp signals
@receiver(pre_save, sender=SpeedLarp)
def pre_save_speed_larp(sender, instance, *args, **kwargs):
    replace_character_names(instance)


@receiver(post_save, sender=SpeedLarp)
def post_save_speedlarp_reset_rels(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reset speedlarp and character relationship caches after speedlarp save."""
    # Update speedlarp cache
    refresh_event_speedlarp_relationships(instance)

    # Update cache for all characters in this speedlarp
    for char in instance.characters.all():
        refresh_character_relationships(char)


@receiver(post_delete, sender=SpeedLarp)
def post_delete_speedlarp_reset_rels(sender, instance: SpeedLarp, **kwargs: Any) -> None:
    """Reset character relationships and cache when speedlarp is deleted."""
    # Update cache for all characters that were in this speedlarp
    for char in instance.characters.all():
        refresh_character_relationships(char)

    # Remove speedlarp from cache
    remove_item_from_cache_section(instance.event_id, "speedlarps", instance.id)


# Trait signals
@receiver(pre_save, sender=Trait)
def pre_save_trait_reset(sender, instance, **kwargs):
    on_trait_pre_save_update_cache(instance)


@receiver(post_save, sender=Trait)
def post_save_trait_reset_rels(sender: type, instance: Trait, **kwargs: Any) -> None:
    """Update quest relationships and trait cache when a trait is saved."""
    # Update quest cache if trait has a quest
    if instance.quest:
        refresh_event_quest_relationships(instance.quest)

    # Refresh all trait relationships for this instance
    refresh_all_instance_traits(instance)


@receiver(pre_delete, sender=Trait)
def pre_delete_trait_reset(sender, instance, **kwargs):
    clear_event_cache_all_runs(instance.event)


@receiver(post_delete, sender=Trait)
def post_delete_trait_reset_rels(sender, instance, **kwargs):
    # Update quest cache if trait had a quest
    if instance.quest:
        refresh_event_quest_relationships(instance.quest)


# User signals
@receiver(post_save, sender=User)
def post_save_user_profile(sender, instance, created, **kwargs):
    create_member_profile_for_user(instance, created)


# WarehouseItem signals
@receiver(pre_save, sender=WarehouseItem, dispatch_uid="warehouseitem_rotate_vertical_photo")
def pre_save_warehouse_item(sender, instance: WarehouseItem, **kwargs):
    auto_rotate_vertical_photos(instance, sender)


# WritingOption signals
@receiver(post_save, sender=WritingOption)
def post_save_writing_option_reset(sender, instance, **kwargs):
    clear_event_fields_cache(instance.question.event_id)
    clear_event_cache_all_runs(instance.question.event)


@receiver(pre_delete, sender=WritingOption)
def pre_delete_character_option_reset(sender, instance, **kwargs):
    clear_event_cache_all_runs(instance.question.event)
    clear_event_fields_cache(instance.question.event_id)


# WritingQuestion signals
@receiver(pre_delete, sender=WritingQuestion)
def pre_delete_writing_question_reset(sender, instance, **kwargs):
    clear_event_fields_cache(instance.event_id)
    clear_event_cache_all_runs(instance.event)


@receiver(post_save, sender=WritingQuestion)
def post_save_writing_question_reset(sender, instance, **kwargs):
    clear_event_fields_cache(instance.event_id)
    clear_event_cache_all_runs(instance.event)


# m2m_changed signals
m2m_changed.connect(on_experience_characters_m2m_changed, sender=DeliveryPx.characters.through)
m2m_changed.connect(on_experience_characters_m2m_changed, sender=AbilityPx.characters.through)
m2m_changed.connect(on_modifier_abilities_m2m_changed, sender=ModifierPx.abilities.through)
m2m_changed.connect(on_rule_abilities_m2m_changed, sender=RulePx.abilities.through)

m2m_changed.connect(on_faction_characters_m2m_changed, sender=Faction.characters.through)
m2m_changed.connect(on_plot_characters_m2m_changed, sender=Plot.characters.through)
m2m_changed.connect(on_speedlarp_characters_m2m_changed, sender=SpeedLarp.characters.through)
m2m_changed.connect(on_prologue_characters_m2m_changed, sender=Prologue.characters.through)

m2m_changed.connect(on_association_roles_m2m_changed, sender=AssociationRole.members.through)
m2m_changed.connect(on_event_roles_m2m_changed, sender=EventRole.members.through)

m2m_changed.connect(on_member_badges_m2m_changed, sender=Badge.members.through)


@receiver(valid_ipn_received)
def paypal_webhook(sender, **kwargs):
    """Handle valid PayPal IPN notifications.

    Args:
        sender: IPN object from PayPal
        **kwargs: Additional keyword arguments

    Returns:
        Result from invoice_received_money or None
    """
    return handle_valid_paypal_ipn(sender)


@receiver(invalid_ipn_received)
def paypal_ko_webhook(sender, **kwargs):
    """Handle invalid PayPal IPN notifications.

    Args:
        sender: Invalid IPN object from PayPal
        **kwargs: Additional keyword arguments
    """
    handle_invalid_paypal_ipn(sender)


@receiver(got_request_exception)
def handle_request_exception(sender, request, **kwargs):
    """Handle request exceptions and create error tickets automatically.

    This signal handler is triggered when an exception occurs during request processing.
    It creates an error ticket with the exception details.

    Args:
        sender: The sender of the signal
        request: The HttpRequest object
        **kwargs: Additional keyword arguments (may contain 'exception')
    """
    try:
        create_error_ticket(request)
    except Exception:
        # Don't let ticket creation failure break the error handling
        pass
