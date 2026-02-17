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

import logging
from typing import Any

from django.contrib.auth.models import User
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
from larpmanager.cache.config import reset_element_configs
from larpmanager.cache.event_text import reset_event_text, update_event_text_cache_on_save
from larpmanager.cache.feature import (
    clear_event_features_cache,
    get_event_features,
    on_association_post_save_reset_features_cache,
)
from larpmanager.cache.fields import clear_event_fields_cache
from larpmanager.cache.larpmanager import clear_blog_cache, clear_larpmanager_home_cache, clear_larpmanager_texts_cache
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
from larpmanager.cache.px import (
    on_ability_characters_m2m_changed,
    on_ability_prerequisites_m2m_changed,
    on_ability_requirements_m2m_changed,
    on_delivery_characters_m2m_changed,
    on_modifier_prerequisites_m2m_changed,
    on_modifier_requirements_m2m_changed,
)
from larpmanager.cache.px import (
    on_modifier_abilities_m2m_changed as on_modifier_abilities_m2m_changed_cache,
)
from larpmanager.cache.px import (
    on_rule_abilities_m2m_changed as on_rule_abilities_m2m_changed_cache,
)
from larpmanager.cache.question import clear_registration_questions_cache, clear_writing_questions_cache
from larpmanager.cache.registration import (
    clear_registration_counts_cache,
    clear_registration_tickets_cache,
    on_character_update_registration_cache,
)
from larpmanager.cache.rels import (
    clear_event_relationships_cache,
    on_faction_characters_m2m_changed,
    on_plot_characters_m2m_changed,
    on_prologue_characters_m2m_changed,
    on_speedlarp_characters_m2m_changed,
    refresh_character_related_caches,
    refresh_character_relationships,
    refresh_character_relationships_background,
    refresh_event_faction_relationships_background,
    refresh_event_plot_relationships_background,
    refresh_event_prologue_relationships_background,
    refresh_event_quest_relationships_background,
    refresh_event_questtype_relationships_background,
    refresh_event_speedlarp_relationships_background,
    remove_item_from_cache_section,
)
from larpmanager.cache.role import remove_association_role_cache, remove_event_role_cache
from larpmanager.cache.run import (
    on_event_post_save_reset_config_cache,
    on_event_pre_save_invalidate_cache,
    on_run_post_save_reset_config_cache,
    on_run_pre_save_invalidate_cache,
    reset_cache_config_run,
    update_visible_factions,
)
from larpmanager.cache.skin import clear_skin_cache
from larpmanager.cache.text_fields import update_text_fields_cache
from larpmanager.cache.warehouse import on_warehouse_item_tags_m2m_changed
from larpmanager.cache.widget import reset_widgets
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
    AccountingItem,
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
from larpmanager.models.base import (
    Feature,
    FeatureModule,
    auto_assign_sequential_numbers,
    auto_set_uuid,
    debug_set_uuid,
    update_model_search_field,
)
from larpmanager.models.casting import AssignmentTrait, Casting, Quest, QuestType, Trait, refresh_all_instance_traits
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
    RegistrationQuestion,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.inventory import Inventory, PoolBalanceCI, PoolTypeCI
from larpmanager.models.larpmanager import (
    LarpManagerBlog,
    LarpManagerFaq,
    LarpManagerGuide,
    LarpManagerHighlight,
    LarpManagerShowcase,
    LarpManagerText,
    LarpManagerTicket,
    LarpManagerTutorial,
)
from larpmanager.models.member import Badge, Member, MemberConfig, Membership
from larpmanager.models.miscellanea import ChatMessage, HelpQuestion, Log, PlayerRelationship, WarehouseItem
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationInstallment,
    RegistrationQuota,
    RegistrationSection,
    RegistrationTicket,
)
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
from larpmanager.utils.auth.permission import auto_assign_event_permission_number
from larpmanager.utils.io.pdf import (
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
from larpmanager.utils.larpmanager.tutorial import auto_assign_faq_sequential_number, generate_tutorial_url_slug
from larpmanager.utils.services.association import (
    apply_skin_features_to_association,
    auto_assign_association_permission_number,
    generate_association_encryption_key,
    prepare_association_skin_features,
)
from larpmanager.utils.services.event import (
    assign_previous_campaign_character,
    copy_parent_event_to_campaign,
    create_default_event_setup,
    on_event_features_m2m_changed,
    prepare_campaign_event_data,
    update_run_plan_on_event_change,
)
from larpmanager.utils.services.experience import (
    _recalcuate_characters_experience_points,
    calculate_character_experience_points,
    on_experience_characters_m2m_changed,
    on_modifier_abilities_m2m_changed,
    on_rule_abilities_m2m_changed,
)
from larpmanager.utils.services.inventory import generate_base_inventories
from larpmanager.utils.services.miscellanea import auto_rotate_vertical_photos
from larpmanager.utils.services.writing import replace_character_names_before_save
from larpmanager.utils.users.member import create_member_profile_for_user, process_membership_status_updates
from larpmanager.utils.users.registration import (
    process_character_ticket_options,
    process_registration_event_change,
    reset_registration_ticket,
)

log = logging.getLogger(__name__)

# ruff: noqa: FBT001 (Do not check "Boolean-typed positional argument in function definition", as with created there are too many)
# ruff: noqa: ARG001 Unused function argument


# Generic signal handlers (no specific sender)
@receiver(pre_save)
def pre_save_callback(sender: type, instance: object, *args: Any, **kwargs: Any) -> None:
    """Handle pre-save operations for all models."""
    # Auto-assign sequential numbers for models with number/order fields
    auto_assign_sequential_numbers(instance)

    # Update search fields for models that implement search functionality
    update_model_search_field(instance)

    # Assign uuid for models that has it
    auto_set_uuid(instance)


@receiver(post_save)
def post_save_callback(sender: type, instance: object, created: bool, **kwargs: Any) -> None:
    """Handle post-save operations for all models."""
    # Update text fields cache after model instance is saved
    update_text_fields_cache(instance)

    # Set simplified uuid for debug
    debug_set_uuid(instance, created=created)

    # Update cache for accounting items
    reset_accountingitem_cache(instance)


@receiver(post_delete)
def post_delete_text_fields_callback(sender: type, instance: object, **kwargs: Any) -> None:
    """Handle post-delete operations for all models."""
    # Update text fields cache after model instance deletion
    update_text_fields_cache(instance)

    # Update cache for accounting items
    reset_accountingitem_cache(instance)


def reset_accountingitem_cache(instance: Any) -> None:
    """Handle reset cache after accounting item saved."""
    if not isinstance(instance, AccountingItem):
        return

    reset_widgets(instance)

    if hasattr(instance, "run") and instance.run and instance.member_id:
        refresh_member_accounting_cache(instance.run, instance.member_id)


# AbilityPx signals
@receiver(post_save, sender=AbilityPx)
def post_save_ability_px(sender: type, instance: AbilityPx, *args: Any, **kwargs: Any) -> None:
    """Update character experience when ability changes."""
    _recalcuate_characters_experience_points(instance)
    reset_widgets(instance)


@receiver(post_delete, sender=AbilityPx)
def post_delete_ability_px(sender: type, instance: AbilityPx, *args: Any, **kwargs: Any) -> None:
    """Update character experience when ability is deleted."""
    _recalcuate_characters_experience_points(instance)
    reset_widgets(instance)


# AccountingItemCollection signals
@receiver(pre_save, sender=AccountingItemCollection)
def pre_save_collection_gift(sender: type, instance: AccountingItemCollection, **kwargs: Any) -> None:
    """Send gift collection notification email before saving."""
    send_gift_collection_notification_email(instance)


@receiver(post_save, sender=AccountingItemCollection)
def post_save_accounting_item_collection(
    sender: type,
    instance: AccountingItemCollection,
    created: bool,
    **kwargs: Any,
) -> None:
    """Handle post-save signal for accounting item collection."""
    handle_accounting_item_collection_post_save(instance)


# AccountingItemDiscount signals
@receiver(post_save, sender=AccountingItemDiscount)
def post_save_discount_accounting_cache(
    sender: type, instance: AccountingItemDiscount, created: bool, **kwargs: Any
) -> None:
    """Update accounting caches when a discount is saved."""
    # Process discount changes in accounting system
    process_accounting_discount_post_save(instance)

    # Refresh member's accounting cache if discount is associated with a run and member
    if instance.run and instance.member_id:
        refresh_member_accounting_cache(instance.run, instance.member_id)


# AccountingItemDonation signals
@receiver(pre_save, sender=AccountingItemDonation)
def pre_save_accounting_item_donation(
    sender: type, instance: AccountingItemDonation, *args: Any, **kwargs: Any
) -> None:
    """Send confirmation email to donor."""
    send_donation_confirmation_email(instance)


# AccountingItemExpense signals
@receiver(pre_save, sender=AccountingItemExpense)
def pre_save_accounting_item_expense(sender: type, instance: AccountingItemExpense, **kwargs: Any) -> None:
    """Send approval email when expense is saved."""
    send_expense_approval_email(instance)


@receiver(post_save, sender=AccountingItemExpense)
def post_save_accounting_item_expense(
    sender: type,
    instance: AccountingItemExpense,
    created: bool,
    **kwargs: Any,
) -> None:
    """Send expense notification and update credit balance."""
    if created:
        send_expense_notification_email(instance)
    update_credit_on_expense_save(instance)


# AccountingItemMembership signals
@receiver(pre_save, sender=AccountingItemMembership)
def pre_save_accounting_item_membership(sender: type, instance: AccountingItem, *args: Any, **kwargs: Any) -> None:
    """Send payment notification email when membership accounting item is saved."""
    send_membership_payment_notification_email(instance)


# AccountingItemOther signals
@receiver(pre_save, sender=AccountingItemOther)
def pre_save_accounting_item_other(sender: type, instance: AccountingItemOther, **kwargs: Any) -> None:
    """Send token credit notification email when accounting item is saved."""
    send_token_credit_notification_email(instance)


@receiver(post_save, sender=AccountingItemOther)
def post_save_other_accounting_cache(
    sender: type,
    instance: AccountingItemOther,
    created: bool,
    **kwargs: Any,
) -> None:
    """Update token credit and member accounting cache after OtherAccounting save."""
    # Update token credit based on the OtherAccounting instance
    update_token_credit_on_other_save(instance)


# AccountingItemPayment signals
@receiver(pre_save, sender=AccountingItemPayment)
def pre_save_accounting_item_payment(sender: type, instance: AccountingItemPayment, **kwargs: Any) -> None:
    """Send payment confirmation and handle pre-save operations."""
    handle_accounting_item_payment_pre_save(instance)


@receiver(post_save, sender=AccountingItemPayment)
def post_save_payment_accounting_cache(
    sender: type, instance: AccountingItemPayment, created: bool, **kwargs: Any
) -> None:
    """Update accounting caches and process payment-related calculations after payment save."""
    # Send confirmation payment
    send_payment_confirmation_email(instance)

    # Update registration and member accounting cache if payment has associated registration
    if instance.registration and instance.registration.run:
        instance.registration.save()
        refresh_member_accounting_cache(instance.registration.run, instance.member_id)

    # Update token credits based on payment changes
    update_token_credit_on_payment_save(instance, created=created)

    # Calculate and update VAT information for the payment
    calculate_payment_vat(instance)


@receiver(post_delete, sender=AccountingItemPayment)
def post_delete_payment_accounting_cache(
    sender: type,
    instance: AccountingItemPayment,
    **kwargs: Any,
) -> None:
    """Update accounting caches after payment deletion."""
    update_token_credit_on_payment_delete(instance)

    # Refresh member accounting cache if payment is linked to a registration
    if instance.registration and instance.registration.run:
        refresh_member_accounting_cache(instance.registration.run, instance.member_id)


# AssignmentTrait signals
@receiver(pre_delete, sender=AssignmentTrait)
def pre_delete_assignment_trait(sender: type, instance: AssignmentTrait, **kwargs: Any) -> None:
    """Signal handler to deactivate castings and remove PDFs when an assignment trait is deleted."""
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
    if created and instance.member:
        send_trait_assignment_email(instance)
        # Remove outdated PDF files if necessary
        cleanup_pdfs_on_trait_assignment(instance)


@receiver(post_delete, sender=AssignmentTrait)
def post_delete_assignment_trait_reset(sender: type, instance: AssignmentTrait, **kwargs: Any) -> None:
    """Clear cache and media after assignment deletion."""
    clear_run_cache_and_media(instance.run)


# AssociationPermission signals
@receiver(pre_save, sender=AssociationPermission)
def pre_save_association_permission(sender: type, instance: object, **kwargs: Any) -> None:
    """Auto-assign number to association permission before save."""
    auto_assign_association_permission_number(instance)


@receiver(post_save, sender=AssociationPermission)
def post_save_association_permission_index_permission(
    sender: type,
    instance: AssociationPermission,
    **kwargs: Any,
) -> None:
    """Clear caches when association permission is saved."""
    clear_index_permission_cache("association")
    clear_association_permission_cache(instance)


@receiver(post_delete, sender=AssociationPermission)
def post_delete_association_permission_index_permission(
    sender: type,
    instance: AssociationPermission,
    **kwargs: Any,
) -> None:
    """Clear association permission caches after deletion."""
    clear_index_permission_cache("association")
    clear_association_permission_cache(instance)


# AssociationRole signals
@receiver(pre_delete, sender=AssociationRole)
def pre_delete_association_role_reset(sender: type, instance: AssociationRole, **kwargs: dict) -> None:
    """Clean up cache and event links when an association role is deleted."""
    # Clear cached role data
    remove_association_role_cache(instance.pk)

    # Reset event links for all members with this role
    for member in instance.members.all():
        reset_event_links(member.id, instance.association_id)


@receiver(post_save, sender=AssociationRole)
def post_save_association_role_reset(sender: type, instance: AssociationRole, **kwargs: Any) -> None:
    """Reset caches when an association role is saved."""
    # Clear association role cache
    remove_association_role_cache(instance.pk)

    # Reset event links for all members with this role
    for member in instance.members.all():
        reset_event_links(member.id, instance.association_id)


# AssocText signals
@receiver(pre_delete, sender=AssociationText)
def pre_delete_association_text(sender: type, instance: object, **kwargs: Any) -> None:
    """Clear association text cache before deletion."""
    clear_association_text_cache_on_delete(instance)


@receiver(post_save, sender=AssociationText)
def post_save_association_text(sender: type, instance: object, created: bool, **kwargs: Any) -> None:
    """Update association text cache after save."""
    update_association_text_cache_on_save(instance)


# AssociationTranslation signals
@receiver(post_save, sender=AssociationTranslation)
def post_save_association_translation(sender: type, instance: object, created: bool, **kwargs: Any) -> None:
    """Clear cache when association translation is saved."""
    clear_association_translation_cache(instance.association_id, instance.language)


@receiver(pre_delete, sender=AssociationTranslation)
def pre_delete_association_translation(sender: type, instance: object, **kwargs: Any) -> None:
    """Clear cache when association translation is deleted."""
    clear_association_translation_cache(instance.association_id, instance.language)


# Association signals
@receiver(pre_save, sender=Association)
def pre_save_association_set_skin_features(sender: type, instance: Association, **kwargs: Any) -> None:
    """Prepare association skin features and encryption key before saving."""
    prepare_association_skin_features(instance)
    generate_association_encryption_key(instance)


@receiver(post_save, sender=Association)
def post_save_association_reset_lm_home(sender: type, instance: object, **kwargs: Any) -> None:
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
def post_save_reset_association_config(sender: type, instance: object, **kwargs: Any) -> None:
    """Clear association config cache after save."""
    reset_element_configs(instance.association)


@receiver(post_delete, sender=AssociationConfig)
def post_delete_reset_association_config(sender: type, instance: object, **kwargs: Any) -> None:
    """Clear association config cache after deletion."""
    reset_element_configs(instance.association)


# AssociationSkin signals
@receiver(post_save, sender=AssociationSkin)
def post_save_association_skin_reset_cache(sender: type, instance: Association, **kwargs: Any) -> None:
    """Clear skin cache when association is saved."""
    clear_skin_cache(instance.domain)


# Character signals
@receiver(pre_save, sender=Character)
def pre_save_character_update_status(sender: type, instance: Character, **kwargs: Any) -> None:
    """Update character status and cache before saving."""
    # Send email notification for character status changes
    send_character_status_update_email(instance)

    # Replace character name placeholders in related fields
    replace_character_names_before_save(instance)

    # Update cached character data
    on_character_pre_save_update_cache(instance)


@receiver(post_save, sender=Character, dispatch_uid="post_character_update_px_v1")
def post_character_update_px(sender: type, instance: Character, *args: Any, **kwargs: Any) -> None:
    """Calculate experience points for character after update."""
    calculate_character_experience_points(instance)


@receiver(post_save, sender=Character)
def post_save_character(sender: type, instance: Character, created: bool, **kwargs: Any) -> None:
    """Handle post-save operations for Character model instances.

    This signal handler performs several maintenance tasks after a Character
    instance is saved, including PDF cleanup, cache updates, and relationship
    refreshes to maintain data consistency across the application.
    """
    # Clean up any outdated PDF files associated with this character
    cleanup_character_pdfs_on_save(instance)

    # Update registration-related cache entries for this character
    on_character_update_registration_cache(instance)

    # Refresh the character's own relationship cache
    refresh_character_relationships_background(instance.id)

    # Update relationship caches for all characters that have this character as a target
    for rel in Relationship.objects.filter(target=instance):
        refresh_character_relationships_background(rel.source_id)

    # Update all other character-related caches (experience, skills, etc.)
    refresh_character_related_caches(instance)

    # Update visible factions
    update_visible_factions(instance.event)

    # Create a personal inventory for newly created characters
    generate_base_inventories(instance)

    # Clear actions cache
    reset_widgets(instance)


@receiver(pre_delete, sender=Character)
def pre_delete_character_reset(sender: type, instance: Character, **kwargs: Any) -> None:
    """Clear event cache and cleanup PDFs before character deletion."""
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
        refresh_character_relationships_background(rel.source_id)

    # Update visible factions
    update_visible_factions(instance.event)

    # Clear actions cache
    reset_widgets(instance)


# Casting signals
@receiver(post_save, sender=Casting)
def post_save_casting_cache(sender: type, instance: Casting, **kwargs: Any) -> None:
    """Clear deadline widget cache when casting preferences are saved."""
    # Clear deadline widget cache for this run (casting deadline)
    reset_widgets(instance)


@receiver(post_delete, sender=Casting)
def post_delete_casting_cache(sender: type, instance: Casting, **kwargs: Any) -> None:
    """Clear deadline widget cache when casting preferences are deleted."""
    # Clear deadline widget cache for this run (casting deadline)
    reset_widgets(instance)


# Log signals
@receiver(post_save, sender=Log)
def post_save_log_cache(sender: type, instance: Log, **kwargs: Any) -> None:
    """Clear log widget cache when log entries are saved."""
    reset_widgets(instance)


# CharacterConfig signals
@receiver(post_save, sender=CharacterConfig)
def post_save_reset_character_config(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reset character configuration cache after save."""
    reset_element_configs(instance.character)


@receiver(post_delete, sender=CharacterConfig)
def post_delete_reset_character_config(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reset character configuration cache after model deletion."""
    reset_element_configs(instance.character)


# ChatMessage signals
@receiver(pre_save, sender=ChatMessage)
def pre_save_notify_chat_message(sender: type[ChatMessage], instance: ChatMessage, **kwargs: Any) -> None:
    """Notify users via email when a new chat message is created."""
    send_chat_message_notification_email(instance)


# Collection signals
@receiver(pre_save, sender=Collection)
def pre_save_collection(sender: type, instance: Any, **kwargs: Any) -> None:
    """Pre-save signal handler for collection instances."""
    handle_collection_pre_save(instance)
    process_collection_status_change(instance)


@receiver(post_save, sender=Collection)
def post_save_collection_activation_email(
    sender: type,
    instance: Collection,
    created: bool,
    **kwargs: Any,
) -> None:
    """Send collection activation email after save signal."""
    if created:
        send_collection_activation_email(instance)


# DeliveryPx signals
@receiver(post_save, sender=DeliveryPx)
def post_save_delivery_px(
    sender: type,
    instance: DeliveryPx,
    *args: Any,
    **kwargs: Any,
) -> None:
    """Refresh delivery characters after save signal."""
    _recalcuate_characters_experience_points(instance)
    reset_widgets(instance)


@receiver(post_delete, sender=DeliveryPx)
def post_delete_delivery_px(sender: type, instance: object, *args: Any, **kwargs: Any) -> None:
    """Signal handler that refreshes delivery characters after a delivery is deleted."""
    _recalcuate_characters_experience_points(instance)
    reset_widgets(instance)


@receiver(post_save, sender=Inventory)
def create_pools_for_inventory(sender: type, instance: Inventory, created: bool, **kwargs: Any) -> None:
    """Create pool balances for newly created character inventories based on event pool types."""
    if created:
        for pool_type in PoolTypeCI.objects.filter(event=instance.event):
            PoolBalanceCI.objects.create(
                inventory=instance, event=instance.event, number=1, name=pool_type.name, pool_type=pool_type, amount=0
            )


# Event signals
@receiver(pre_save, sender=Event)
def pre_save_event(sender: type, instance: Event, **kwargs: Any) -> None:
    """Invalidate cache and prepare campaign data before saving an Event."""
    on_event_pre_save_invalidate_cache(instance)
    prepare_campaign_event_data(instance)


@receiver(post_save, sender=Event)
def post_save_event_update(sender: type, instance: Event, **kwargs: Any) -> None:
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
    if not getattr(instance, "_skip_campaign_setup", False):  # Internal flag to prevent recursion
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
def post_delete_event_links(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear cache for event links after deletion."""
    clear_run_event_links_cache(instance)


# EventButton signals
@receiver(post_save, sender=EventButton)
def post_save_event_button(sender: type, instance: object, created: bool, **kwargs: Any) -> None:
    """Clear event button cache after save."""
    clear_event_button_cache(instance.event_id)


@receiver(pre_delete, sender=EventButton)
def pre_delete_event_button(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear cache when event button is deleted."""
    clear_event_button_cache(instance.event_id)


# EventConfig signals
@receiver(post_save, sender=EventConfig)
def post_save_reset_event_config(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reset event configuration cache after model save."""
    reset_element_configs(instance.event)
    for run in instance.event.runs.all():
        reset_cache_config_run(run)


@receiver(post_delete, sender=EventConfig)
def post_delete_reset_event_config(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear event configuration cache after deletion."""
    reset_element_configs(instance.event)
    for run in instance.event.runs.all():
        reset_cache_config_run(run)


# EventPermission signals
@receiver(pre_save, sender=EventPermission)
def pre_save_event_permission(sender: type, instance: EventPermission, **kwargs: Any) -> None:
    """Auto-assign permission number before saving EventPermission."""
    auto_assign_event_permission_number(instance)


@receiver(post_save, sender=EventPermission)
def post_save_event_permission_reset(sender: type, instance: EventPermission, **kwargs: Any) -> None:
    """Reset caches when EventPermission is saved."""
    clear_event_permission_cache(instance)
    clear_index_permission_cache("event")


@receiver(post_delete, sender=EventPermission)
def post_delete_event_permission_reset(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reset event permission caches after EventPermission deletion."""
    clear_event_permission_cache(instance)
    clear_index_permission_cache("event")


# EventRole signals
@receiver(pre_delete, sender=EventRole)
def pre_delete_event_role_reset(sender: type, instance: EventRole, **kwargs: Any) -> None:
    """Reset caches and event links when an EventRole is deleted."""
    # Clear the event role cache for this instance
    remove_event_role_cache(instance.pk)

    # Reset event links for all members associated with this role
    for member in instance.members.all():
        reset_event_links(member.id, instance.event.association_id)


@receiver(post_save, sender=EventRole)
def post_save_event_role_reset(sender: type, instance: EventRole, **kwargs: Any) -> None:
    """Reset caches when an EventRole is saved."""
    # Clear the event role cache for this specific instance
    remove_event_role_cache(instance.pk)

    # Reset event links cache for all members assigned to this role
    for member in instance.members.all():
        reset_event_links(member.id, instance.event.association_id)


# EventText signals
@receiver(pre_delete, sender=EventText)
def pre_delete_event_text(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear event text cache before deletion."""
    reset_event_text(instance)


@receiver(post_save, sender=EventText)
def post_save_event_text(sender: type, instance: EventText, created: bool, **kwargs: Any) -> None:
    """Update cache when EventText is saved."""
    update_event_text_cache_on_save(instance)


# Faction signals
@receiver(pre_save, sender=Faction)
def pre_save_faction(sender: type, instance: Faction, *args: Any, **kwargs: Any) -> None:
    """Signal handler that updates faction before saving."""
    replace_character_names(instance)
    on_faction_pre_save_update_cache(instance)


@receiver(post_save, sender=Faction)
def post_save_faction_reset_rels(sender: type, instance: Faction, **kwargs: Any) -> None:
    """Reset faction relationships and update character caches after faction save.

    Args:
        sender: The model class that sent the signal
        instance: The faction instance that was saved
        **kwargs: Additional keyword arguments from the signal

    """
    # Update faction cache for event relationships
    refresh_event_faction_relationships_background(instance.id)

    # Update cache for all characters belonging to this faction
    for char in instance.characters.all():
        refresh_character_relationships_background(char.id)

    # Clean up faction PDFs after save operation
    cleanup_faction_pdfs_on_save(instance)

    # Update visible factions config
    update_visible_factions(instance.event)


@receiver(pre_delete, sender=Faction)
def pre_delete_faction(sender: type, instance: Faction, **kwargs: dict) -> None:
    """Clean up faction PDFs and clear event cache before faction deletion."""
    cleanup_faction_pdfs_before_delete(instance)
    clear_event_cache_all_runs(instance.event)


@receiver(post_delete, sender=Faction)
def post_delete_faction_reset_rels(sender: type, instance: object, **kwargs: Any) -> None:
    """Reset character relationships when a faction is deleted."""
    # Update cache for all characters that were in this faction
    for char in instance.characters.all():
        refresh_character_relationships_background(char.id)

    # Remove faction from cache
    remove_item_from_cache_section(instance.event_id, "factions", instance.id)

    # Update visible factions config
    update_visible_factions(instance.event)


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
def pre_delete_handout(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clean up handout PDFs before deletion."""
    cleanup_handout_pdfs_before_delete(instance)


@receiver(post_save, sender=Handout)
def post_save_handout(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clean up handout PDFs after save."""
    cleanup_handout_pdfs_after_save(instance)


# HandoutTemplate signals
@receiver(pre_delete, sender=HandoutTemplate)
def pre_delete_handout_template(sender: type, instance: Any, **kwargs: Any) -> None:
    """Delete associated PDF files before deleting handout template."""
    cleanup_handout_template_pdfs_before_delete(instance)


@receiver(post_save, sender=HandoutTemplate)
def post_save_handout_template(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clean up handout template PDFs after save."""
    cleanup_handout_template_pdfs_after_save(instance)


# HelpQuestion signals
@receiver(pre_save, sender=HelpQuestion)
def pre_save_notify_help_question(sender: type, instance: Any, **kwargs: Any) -> None:
    """Notify about help question before saving."""
    send_help_question_notification_email(instance)


# LarpManagerFaq signals
@receiver(pre_save, sender=LarpManagerFaq)
def pre_save_larp_manager_faq(sender: type, instance: LarpManagerFaq, *args: Any, **kwargs: Any) -> None:
    """Signal handler that auto-assigns sequential FAQ numbers before saving."""
    auto_assign_faq_sequential_number(instance)


# LarpManagerGuide signals
@receiver(post_save, sender=LarpManagerGuide)
def post_save_reset_guides_cache(sender: type, instance: object, **kwargs: dict) -> None:
    """Signal handler to reset guides cache when guide content changes."""
    reset_guides_cache()


@receiver(post_delete, sender=LarpManagerGuide)
def post_delete_reset_guides_cache(sender: type, instance: object, **kwargs: dict) -> None:
    """Reset guides cache after model deletion."""
    reset_guides_cache()


# LarpManagerBlog signals
@receiver(post_save, sender=LarpManagerBlog)
def post_save_clear_blog_cache(sender: type, instance: LarpManagerBlog, **kwargs: dict) -> None:
    """Clear blog content cache when blog is updated."""
    clear_blog_cache(instance.id)


# LarpManagerTicket signals
@receiver(post_save, sender=LarpManagerTicket)
def save_larpmanager_ticket(sender: type, instance: LarpManagerTicket, created: bool, **kwargs: Any) -> None:
    """Send email notification when a support ticket is saved."""
    send_support_ticket_email(instance)


# LarpManagerTutorial signals
@receiver(pre_save, sender=LarpManagerTutorial)
def pre_save_larp_manager_tutorial(sender: type, instance: object, *args: Any, **kwargs: Any) -> None:
    """Generate URL slug for tutorial instance before saving."""
    generate_tutorial_url_slug(instance)


@receiver(post_save, sender=LarpManagerTutorial)
def post_save_reset_tutorials_cache(sender: type, instance: Any, **kwargs: Any) -> None:
    """Django signal handler that clears the tutorials cache when a related model is saved."""
    reset_tutorials_cache()


@receiver(post_delete, sender=LarpManagerTutorial)
def post_delete_reset_tutorials_cache(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reset tutorials cache after instance deletion."""
    reset_tutorials_cache()


@receiver(post_save, sender=LarpManagerShowcase)
def post_save_reset_lm_home_cache_showcase(sender: type, instance: object, **kwargs: dict) -> None:
    """Signal handler to reset home cache when showcase content changes."""
    clear_larpmanager_home_cache()


@receiver(post_delete, sender=LarpManagerShowcase)
def post_delete_reset_lm_home_cache_showcase(sender: type, instance: object, **kwargs: dict) -> None:
    """Reset home cache after showcase deletion."""
    clear_larpmanager_home_cache()


@receiver(post_save, sender=LarpManagerHighlight)
def post_save_reset_lm_home_cache_highlight(sender: type, instance: object, **kwargs: dict) -> None:
    """Signal handler to reset home cache when highlight content changes."""
    clear_larpmanager_home_cache()


@receiver(post_delete, sender=LarpManagerHighlight)
def post_delete_reset_lm_home_cache_highlight(sender: type, instance: object, **kwargs: dict) -> None:
    """Reset home cache after highlight deletion."""
    clear_larpmanager_home_cache()


@receiver(post_save, sender=LarpManagerText)
def post_save_reset_lm_texts_cache(sender: type, instance: LarpManagerText, **kwargs: dict) -> None:
    """Signal handler to reset texts cache when text content changes."""
    clear_larpmanager_texts_cache()


@receiver(post_delete, sender=LarpManagerText)
def post_delete_reset_lm_texts_cache(sender: type, instance: LarpManagerText, **kwargs: dict) -> None:
    """Reset texts cache after text deletion."""
    clear_larpmanager_texts_cache()


# Member signals
@receiver(post_save, sender=Member)
def post_save_member_reset(sender: type, instance: Member, **kwargs: dict) -> None:
    """Update cached event character data when member changes."""
    update_member_event_character_cache(instance)


# MemberConfig signals
@receiver(post_save, sender=MemberConfig)
def post_save_reset_member_config(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reset member configuration cache after save."""
    reset_element_configs(instance.member)


@receiver(post_delete, sender=MemberConfig)
def post_delete_reset_member_config(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear member config cache after deletion."""
    reset_element_configs(instance.member)


# Membership signals
@receiver(pre_save, sender=Membership)
def pre_save_membership(sender: type, instance: Membership, **kwargs: Any) -> None:
    """Process membership status updates before save."""
    process_membership_status_updates(instance)


@receiver(post_save, sender=Membership)
def post_save_membership_cache(sender: type, instance: Membership, **kwargs: Any) -> None:
    """Clear deadline widget cache when membership status changes."""
    reset_widgets(instance)


@receiver(post_delete, sender=Membership)
def post_delete_membership_cache(sender: type, instance: Membership, **kwargs: Any) -> None:
    """Clear deadline widget cache when membership status changes."""
    reset_widgets(instance)


# ModifierPx signals
@receiver(post_save, sender=ModifierPx)
def post_save_modifier_px(sender: type, instance: object, *args: Any, **kwargs: Any) -> None:
    """Update character experience when a modifier is saved."""
    _recalcuate_characters_experience_points(instance)


@receiver(post_delete, sender=ModifierPx)
def post_delete_modifier_px(sender: type, instance: object, *args: Any, **kwargs: Any) -> None:
    """Update character experience after modifier deletion."""
    _recalcuate_characters_experience_points(instance)


# PaymentInvoice signals
@receiver(pre_save, sender=PaymentInvoice)
def pre_save_payment_invoice(sender: type[PaymentInvoice], instance: PaymentInvoice, **kwargs: Any) -> None:
    """Process payment invoice status changes before saving."""
    process_payment_invoice_status_change(instance)


# PlayerRelationship signals
@receiver(pre_delete, sender=PlayerRelationship)
def pre_delete_player_relationship(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clean up relationship PDFs before deleting instance."""
    cleanup_relationship_pdfs_before_delete(instance)


@receiver(post_save, sender=PlayerRelationship)
def post_save_player_relationship(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clean up relationship PDFs after save."""
    cleanup_relationship_pdfs_after_save(instance)


# Plot signals
@receiver(pre_save, sender=Plot)
def pre_save_plot(sender: type, instance: object, *args: Any, **kwargs: Any) -> None:
    """Replace character names in plot instance before saving."""
    replace_character_names(instance)


@receiver(post_save, sender=Plot)
def post_save_plot_reset_rels(sender: type, instance: Plot, **kwargs: Any) -> None:
    """Update plot and character relationship caches after plot save."""
    # Update plot cache
    refresh_event_plot_relationships_background(instance.id)

    # Update cache for all characters in this plot
    for char_rel in instance.get_plot_characters():
        refresh_character_relationships_background(char_rel.character_id)


@receiver(post_delete, sender=Plot)
def post_delete_plot_reset_rels(sender: type, instance: Plot, **kwargs: Any) -> None:
    """Reset character relationships and cache when a plot is deleted."""
    # Update cache for all characters that were in this plot
    for char_rel in instance.get_plot_characters():
        refresh_character_relationships_background(char_rel.character_id)

    # Remove plot from cache
    remove_item_from_cache_section(instance.event_id, "plots", instance.id)


# PreRegistration signals
@receiver(pre_save, sender=PreRegistration)
def pre_save_pre_registration(sender: type, instance: Any, **kwargs: Any) -> None:
    """Send confirmation email for the pre-registration."""
    send_pre_registration_confirmation_email(instance)


# Prologue signals
@receiver(pre_save, sender=Prologue)
def pre_save_prologue(sender: type, instance: object, *args: Any, **kwargs: Any) -> None:
    """Replace character names in prologue before saving."""
    replace_character_names(instance)


@receiver(post_save, sender=Prologue)
def post_save_prologue_reset_rels(sender: type, instance: Prologue, **kwargs: Any) -> None:
    """Reset relationship cache for prologue and associated characters."""
    # Update prologue cache
    refresh_event_prologue_relationships_background(instance.id)

    # Update cache for all characters in this prologue
    for char in instance.characters.all():
        refresh_character_relationships_background(char.id)


@receiver(post_delete, sender=Prologue)
def post_delete_prologue_reset_rels(sender: type, instance: object, **kwargs: Any) -> None:
    """Reset character relationships and cache when prologue is deleted."""
    # Update cache for all characters that were in this prologue
    for char in instance.characters.all():
        refresh_character_relationships_background(char.id)

    # Remove prologue from cache
    remove_item_from_cache_section(instance.event_id, "prologues", instance.id)


# Quest signals
@receiver(pre_save, sender=Quest)
def pre_save_quest_reset(sender: type, instance: Any, **kwargs: Any) -> None:
    """Update cache before saving quest instance."""
    on_quest_pre_save_update_cache(instance)


@receiver(post_save, sender=Quest)
def post_save_quest_reset_rels(sender: type, instance: Quest, **kwargs: Any) -> None:
    """Update quest and questtype cache relationships after quest save."""
    # Update quest cache
    refresh_event_quest_relationships_background(instance.id)

    # Update questtype cache if quest has a type
    if instance.typ:
        refresh_event_questtype_relationships_background(instance.typ_id)

    reset_widgets(instance)


@receiver(pre_delete, sender=Quest)
def pre_delete_quest_reset(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear event cache when quest is deleted."""
    clear_event_cache_all_runs(instance.event)


@receiver(post_delete, sender=Quest)
def post_delete_quest_reset_rels(sender: type, instance: object, **kwargs: Any) -> None:
    """Reset quest relationships after quest deletion."""
    # Update questtype cache if quest had a type
    if instance.typ:
        refresh_event_questtype_relationships_background(instance.typ_id)

    # Remove quest from cache
    remove_item_from_cache_section(instance.event_id, "quests", instance.id)

    reset_widgets(instance)


# QuestType signals
@receiver(pre_save, sender=QuestType)
def pre_save_questtype_reset(sender: type, instance: QuestType, **kwargs: dict) -> None:
    """Signal handler that updates cache when a quest type is modified."""
    on_quest_type_pre_save_update_cache(instance)


@receiver(post_save, sender=QuestType)
def post_save_questtype_reset_rels(
    sender: type,
    instance: QuestType,
    **kwargs: Any,
) -> None:
    """Reset quest type and related quest caches after save."""
    # Update questtype cache
    refresh_event_questtype_relationships_background(instance.id)

    # Update cache for all quests of this type
    for quest in instance.quests.all():
        refresh_event_quest_relationships_background(quest.id)

    reset_widgets(instance)


@receiver(pre_delete, sender=QuestType)
def pre_delete_quest_type_reset(sender: type, instance: QuestType, **kwargs: dict) -> None:
    """Clear cache when a quest type is deleted."""
    clear_event_cache_all_runs(instance.event)


@receiver(post_delete, sender=QuestType)
def post_delete_questtype_reset_rels(sender: type, instance: QuestType, **kwargs: Any) -> None:
    """Reset quest relationships when a quest type is deleted."""
    # Update cache for all quests that were of this type
    for quest in instance.quests.all():
        refresh_event_quest_relationships_background(quest.id)

    # Remove questtype from cache
    remove_item_from_cache_section(instance.event_id, "questtypes", instance.id)

    reset_widgets(instance)


# RefundRequest signals
@receiver(pre_save, sender=RefundRequest)
def pre_save_refund_request(sender: type, instance: Any, **kwargs: Any) -> None:
    """Process refund request status changes before saving."""
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
def post_save_registration_cache(sender: type, instance: Registration, created: bool, **kwargs: Any) -> None:
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

    # Clear deadline widget cache for this run
    reset_widgets(instance)


@receiver(pre_delete, sender=Registration)
def pre_delete_registration(sender: type, instance: Registration, *args: Any, **kwargs: Any) -> None:
    """Send email notification before registration is deleted."""
    send_registration_deletion_email(instance)


@receiver(post_delete, sender=Registration)
def post_delete_registration_accounting_cache(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear accounting cache for the associated run after registration deletion."""
    clear_registration_accounting_cache(instance.run_id)
    reset_widgets(instance)


# RegistrationCharacterRel signals
@receiver(post_save, sender=RegistrationCharacterRel)
def post_save_registration_character_rel_savereg(
    sender: type,
    instance: RegistrationCharacterRel,
    created: bool,
    **kwargs: Any,
) -> None:
    """Reset character cache and send assignment email notification."""
    reset_character_registration_cache(instance)

    # Clear deadline widget cache (casting requirements)
    reset_widgets(instance.registration)

    # Auto-assign player if player editor is active and character has no player
    features = get_event_features(instance.character.event_id)
    if "user_character" in features and not instance.character.player:
        instance.character.player = instance.registration.member
        instance.character.save()

    if created:
        send_character_assignment_email(instance)


@receiver(post_delete, sender=RegistrationCharacterRel)
def post_delete_registration_character_rel_savereg(
    sender: type, instance: RegistrationCharacterRel, **kwargs: Any
) -> None:
    """Reset character registration cache after relationship deletion."""
    reset_character_registration_cache(instance)

    # Clear deadline widget cache (casting requirements)
    reset_widgets(instance.registration)


@receiver(post_save, sender=RegistrationSection)
def post_save_registration_section(sender: type, instance: RegistrationSection, **kwargs: dict) -> None:
    """Process registration section post-save signal."""
    clear_registration_questions_cache(instance.event_id)


@receiver(post_delete, sender=RegistrationSection)
def post_delete_registration_section(sender: type, instance: RegistrationSection, **kwargs: Any) -> None:
    """Process registration section post-delete signal."""
    clear_registration_questions_cache(instance.event_id)


@receiver(post_save, sender=RegistrationQuestion)
def post_save_registration_question(sender: type, instance: RegistrationQuestion, **kwargs: dict) -> None:
    """Process registration question post-save signal."""
    clear_registration_questions_cache(instance.event_id)
    reset_widgets(instance)


@receiver(post_delete, sender=RegistrationQuestion)
def post_delete_registration_question(sender: type, instance: RegistrationTicket, **kwargs: Any) -> None:
    """Process registration question post-delete signal."""
    clear_registration_questions_cache(instance.event_id)
    reset_widgets(instance)


# RegistrationOption signals
@receiver(post_save, sender=RegistrationOption)
def post_save_registration_option(sender: type, instance: RegistrationOption, **kwargs: dict) -> None:
    """Process registration option post-save signal."""
    process_registration_option_post_save(instance)
    clear_registration_questions_cache(instance.question.event_id)


@receiver(post_delete, sender=RegistrationOption)
def post_delete_registration_option(sender: type, instance: RegistrationOption, **kwargs: Any) -> None:
    """Process registration option post-delete signal."""
    clear_registration_questions_cache(instance.question.event_id)


# RegistrationTicket signals
@receiver(post_save, sender=RegistrationTicket)
def post_save_ticket_accounting_cache(
    sender: type,
    instance: RegistrationTicket,
    created: bool,
    **kwargs: Any,
) -> None:
    """Clear cache for all runs when a ticket is saved."""
    log_registration_ticket_saved(instance)
    reset_registration_ticket(instance)
    clear_registration_tickets_cache(instance.event_id)
    reset_widgets(instance)


@receiver(post_delete, sender=RegistrationTicket)
def post_delete_ticket_accounting_cache(sender: type, instance: RegistrationTicket, **kwargs: Any) -> None:
    """Clear cache for all runs when a ticket is deleted."""
    reset_registration_ticket(instance)
    reset_widgets(instance)


# RegistrationInstallment signals
@receiver(post_save, sender=RegistrationInstallment)
def post_save_registration_installment(sender: type, instance: RegistrationInstallment, **kwargs: Any) -> None:
    """Clear actions cache when installment is saved."""
    reset_widgets(instance)


@receiver(post_delete, sender=RegistrationInstallment)
def post_delete_registration_installment(sender: type, instance: RegistrationInstallment, **kwargs: Any) -> None:
    """Clear actions cache when installment is deleted."""
    reset_widgets(instance)


# RegistrationQuota signals
@receiver(post_save, sender=RegistrationQuota)
def post_save_registration_quota(sender: type, instance: RegistrationQuota, **kwargs: Any) -> None:
    """Clear actions cache when quota is saved."""
    reset_widgets(instance)


@receiver(post_delete, sender=RegistrationQuota)
def post_delete_registration_quota(sender: type, instance: RegistrationQuota, **kwargs: Any) -> None:
    """Clear actions cache when quota is deleted."""
    reset_widgets(instance)
    clear_registration_tickets_cache(instance.event_id)
    reset_widgets(instance)


# Relationship signals
@receiver(pre_delete, sender=Relationship)
def pre_delete_relationship(sender: type, instance: Any, **kwargs: Any) -> None:
    """Delete character PDF files before relationship deletion."""
    delete_character_pdf_files(instance.source)


@receiver(post_save, sender=Relationship)
def post_save_relationship_reset_rels(sender: type, instance: Any, **kwargs: Any) -> None:
    """Update cached relationships and delete PDF files after saving a relationship."""
    refresh_character_relationships(instance.source)
    delete_character_pdf_files(instance.source)


@receiver(post_delete, sender=Relationship)
def post_delete_relationship_reset_rels(sender: type, instance: Any, **kwargs: Any) -> None:
    """Update cache for source character after relationship deletion."""
    refresh_character_relationships(instance.source)


# RulePx signals
@receiver(post_save, sender=RulePx)
def post_save_rule_px(sender: type, instance: object, *args: Any, **kwargs: Any) -> None:
    """Update characters experience when rule changes."""
    _recalcuate_characters_experience_points(instance)


@receiver(post_delete, sender=RulePx)
def post_delete_rule_px(sender: type, instance: object, *args: Any, **kwargs: Any) -> None:
    """Update character experience when a rule is deleted."""
    _recalcuate_characters_experience_points(instance)


# Run signals
@receiver(pre_save, sender=Run)
def pre_save_run(sender: type, instance: Any, **kwargs: Any) -> None:
    """Invalidate cache on run pre-save signal."""
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

    # Clear association cache to update onboarding status
    clear_association_cache(instance.event.association.slug)


@receiver(pre_delete, sender=Run)
def pre_delete_run_reset(sender: type, instance: Run, **kwargs: Any) -> None:
    """Reset run cache and media files before deletion."""
    clear_run_cache_and_media(instance)


@receiver(post_delete, sender=Run)
def post_delete_run_links(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear event links cache when a run link is deleted."""
    clear_run_event_links_cache(instance.event)

    # Clear association cache to update onboarding status
    clear_association_cache(instance.event.association.slug)


# RunConfig signals
@receiver(post_save, sender=RunConfig)
def post_save_reset_run_config(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reset run config cache when related instance is saved."""
    reset_element_configs(instance.run)


@receiver(post_delete, sender=RunConfig)
def post_delete_reset_run_config(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear configuration cache after Run deletion."""
    reset_element_configs(instance.run)


# SpeedLarp signals
@receiver(pre_save, sender=SpeedLarp)
def pre_save_speed_larp(sender: type, instance: object, *args: Any, **kwargs: Any) -> None:
    """Pre-save signal handler that replaces character names in the instance."""
    replace_character_names(instance)


@receiver(post_save, sender=SpeedLarp)
def post_save_speedlarp_reset_rels(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reset speedlarp and character relationship caches after speedlarp save."""
    # Update speedlarp cache
    refresh_event_speedlarp_relationships_background(instance.id)

    # Update cache for all characters in this speedlarp
    for char in instance.characters.all():
        refresh_character_relationships_background(char.id)


@receiver(post_delete, sender=SpeedLarp)
def post_delete_speedlarp_reset_rels(sender: type, instance: SpeedLarp, **kwargs: Any) -> None:
    """Reset character relationships and cache when speedlarp is deleted."""
    # Update cache for all characters that were in this speedlarp
    for char in instance.characters.all():
        refresh_character_relationships_background(char.id)

    # Remove speedlarp from cache
    remove_item_from_cache_section(instance.event_id, "speedlarps", instance.id)


# Trait signals
@receiver(pre_save, sender=Trait)
def pre_save_trait_reset(sender: type, instance: Trait, **kwargs: dict) -> None:
    """Update cache before saving trait."""
    on_trait_pre_save_update_cache(instance)


@receiver(post_save, sender=Trait)
def post_save_trait_reset_rels(sender: type, instance: Trait, **kwargs: Any) -> None:
    """Update quest relationships and trait cache when a trait is saved."""
    # Update quest cache if trait has a quest
    if instance.quest:
        refresh_event_quest_relationships_background(instance.quest_id)

    # Refresh all trait relationships for this instance
    refresh_all_instance_traits(instance)

    # Clear actions cache
    reset_widgets(instance)


@receiver(pre_delete, sender=Trait)
def pre_delete_trait_reset(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear event cache when trait is deleted."""
    clear_event_cache_all_runs(instance.event)


@receiver(post_delete, sender=Trait)
def post_delete_trait_reset_rels(sender: type, instance: Any, **kwargs: Any) -> None:
    """Reset quest relationships after trait deletion."""
    # Update quest cache if trait had a quest
    if instance.quest:
        refresh_event_quest_relationships_background(instance.quest_id)

    reset_widgets(instance)


# User signals
@receiver(post_save, sender=User)
def post_save_user_profile(sender: type, instance: User, created: bool, **kwargs: Any) -> None:
    """Create member profile when user is created."""
    create_member_profile_for_user(instance, is_newly_created=created)


# WarehouseItem signals
@receiver(pre_save, sender=WarehouseItem, dispatch_uid="warehouseitem_rotate_vertical_photo")
def pre_save_warehouse_item(sender: type[WarehouseItem], instance: WarehouseItem, **kwargs: Any) -> None:
    """Rotate vertical photos before saving warehouse item."""
    auto_rotate_vertical_photos(instance, sender)


# WritingOption signals
@receiver(post_save, sender=WritingOption)
def post_save_writing_option_reset(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear caches when WritingOption is saved."""
    clear_event_fields_cache(instance.question.event_id)
    clear_event_cache_all_runs(instance.question.event)
    clear_writing_questions_cache(instance.event_id)


@receiver(pre_delete, sender=WritingOption)
def pre_delete_character_option_reset(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear character-related caches when a character option is deleted."""
    clear_event_cache_all_runs(instance.question.event)
    clear_event_fields_cache(instance.question.event_id)
    clear_writing_questions_cache(instance.event_id)


# WritingQuestion signals
@receiver(pre_delete, sender=WritingQuestion)
def pre_delete_writing_question_reset(sender: type, instance: WritingQuestion, **kwargs: Any) -> None:
    """Clear caches when a writing question is deleted."""
    clear_event_fields_cache(instance.event_id)
    clear_event_cache_all_runs(instance.event)
    clear_writing_questions_cache(instance.event_id)
    reset_widgets(instance)


@receiver(post_save, sender=WritingQuestion)
def post_save_writing_question_reset(sender: type, instance: Any, **kwargs: Any) -> None:
    """Clear cache for event fields and all runs when writing question changes."""
    clear_event_fields_cache(instance.event_id)
    clear_event_cache_all_runs(instance.event)
    clear_writing_questions_cache(instance.event_id)
    reset_widgets(instance)


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

m2m_changed.connect(on_warehouse_item_tags_m2m_changed, sender=WarehouseItem.tags.through)

# PX caching signals - cache relationship data in Redis
m2m_changed.connect(on_ability_characters_m2m_changed, sender=AbilityPx.characters.through)
m2m_changed.connect(on_ability_prerequisites_m2m_changed, sender=AbilityPx.prerequisites.through)
m2m_changed.connect(on_ability_requirements_m2m_changed, sender=AbilityPx.requirements.through)
m2m_changed.connect(on_delivery_characters_m2m_changed, sender=DeliveryPx.characters.through)
m2m_changed.connect(on_modifier_abilities_m2m_changed_cache, sender=ModifierPx.abilities.through)
m2m_changed.connect(on_modifier_prerequisites_m2m_changed, sender=ModifierPx.prerequisites.through)
m2m_changed.connect(on_modifier_requirements_m2m_changed, sender=ModifierPx.requirements.through)
m2m_changed.connect(on_rule_abilities_m2m_changed_cache, sender=RulePx.abilities.through)

m2m_changed.connect(on_event_features_m2m_changed, sender=Event.features.through)


@receiver(valid_ipn_received)
def paypal_webhook(sender: type, **kwargs: Any) -> Any:
    """Handle valid PayPal IPN notifications."""
    return handle_valid_paypal_ipn(sender)


@receiver(invalid_ipn_received)
def paypal_ko_webhook(sender: type, **kwargs: Any) -> None:
    """Handle invalid PayPal IPN notifications."""
    handle_invalid_paypal_ipn(sender)
