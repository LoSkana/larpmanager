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

from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from larpmanager.models.accounting import (
    AccountingItemOther,
    AccountingItemPayment,
    OtherChoices,
    PaymentInvoice,
)
from larpmanager.models.event import Run
from larpmanager.models.form import (
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    RegistrationQuestionType,
)
from larpmanager.models.registration import (
    Registration,
    RegistrationCharacterRel,
    RegistrationTicket,
)


def transfer_registration_between_runs(
    registration: Registration,
    target_run: Run,
    ticket_mapping: Optional[dict[int, int]] = None,
    preserve_choices: bool = True,
    preserve_answers: bool = True,
    preserve_accounting: bool = True,
    move_registration: bool = True,
) -> Registration:
    """
    Transfer a registration from one run to another, attempting to match tickets, questions and options.

    Args:
        registration: The registration to transfer
        target_run: The destination run
        ticket_mapping: Manual mapping between ticket IDs (source_ticket_id -> target_ticket_id)
        preserve_choices: Whether to preserve multiple choice selections
        preserve_answers: Whether to preserve text answers
        preserve_accounting: Whether to preserve accounting items (payments and other items)
        move_registration: If True, deletes the original registration and related data (default: True).
                          If False, creates a copy leaving the original intact.

    Returns:
        The new registration created in the target run

    Raises:
        ValidationError: If the transfer is not possible
    """

    # Check that the registration is not already in the target run
    if registration.run == target_run:
        raise ValidationError("Registration is already in the target run")

    # Check that the member doesn't already have a registration in the target run
    existing_reg = Registration.objects.filter(
        run=target_run, member=registration.member, cancellation_date__isnull=True
    ).first()

    if existing_reg:
        raise ValidationError(f"Member {registration.member} already has a registration in run {target_run}")

    with transaction.atomic():
        # 1. Find matching ticket in the new run
        target_ticket = _find_matching_ticket(registration.ticket, target_run, ticket_mapping)

        # 2. Create the new registration
        new_registration = Registration.objects.create(
            run=target_run,
            member=registration.member,
            quotas=registration.quotas,
            ticket=target_ticket,
            additionals=registration.additionals,
            pay_what=0,  # Reset payment info
            num_payments=1,
            tot_payed=0,
            tot_iscr=target_ticket.price if target_ticket else 0,
            quota=0,
            alert=False,
            deadline=0,
            surcharge=0,
            refunded=False,
            modified=0,
        )

        # 3. Transfer choices and answers if requested
        if preserve_choices:
            _transfer_choices(registration, new_registration)

        if preserve_answers:
            _transfer_answers(registration, new_registration)

        # 4. Transfer associated characters
        _transfer_character_relations(registration, new_registration)

        # 5. Transfer accounting items if requested
        if preserve_accounting:
            _transfer_accounting_items(registration, new_registration)

        # 6. Delete original registration and related data if moving
        if move_registration:
            _delete_original_registration_data(registration)

        return new_registration


def _find_matching_ticket(
    source_ticket: RegistrationTicket, target_run: Run, ticket_mapping: Optional[dict[int, int]] = None
) -> Optional[RegistrationTicket]:
    """
    Find the corresponding ticket in the destination run.

    Matching logic:
    1. If manual mapping exists, use it
    2. Search by tier and exact name
    3. Search by tier only
    4. Return None if no match found
    """
    if not source_ticket:
        return None

    target_event = target_run.event

    # Manual mapping
    if ticket_mapping and source_ticket.id in ticket_mapping:
        target_ticket_id = ticket_mapping[source_ticket.id]
        return RegistrationTicket.objects.filter(id=target_ticket_id, event=target_event).first()

    # Match by tier and name
    exact_match = RegistrationTicket.objects.filter(
        event=target_event, tier=source_ticket.tier, name=source_ticket.name
    ).first()

    if exact_match:
        return exact_match

    # Match by tier only
    tier_match = RegistrationTicket.objects.filter(event=target_event, tier=source_ticket.tier).first()

    return tier_match


def _transfer_choices(source_reg: Registration, target_reg: Registration) -> list[RegistrationChoice]:
    """
    Transfer multiple choice selections from source registration to destination.
    """
    source_choices = RegistrationChoice.objects.filter(reg=source_reg)
    transferred_choices = []

    for choice in source_choices:
        # Find corresponding question in destination event
        target_question = _find_matching_question(choice.question, target_reg.run.event)
        if not target_question:
            continue

        # Find corresponding option
        target_option = _find_matching_option(choice.option, target_question)
        if not target_option:
            continue

        # Create the new choice
        new_choice = RegistrationChoice.objects.create(question=target_question, option=target_option, reg=target_reg)
        transferred_choices.append(new_choice)

    return transferred_choices


def _transfer_answers(source_reg: Registration, target_reg: Registration) -> list[RegistrationAnswer]:
    """
    Transfer text answers from source registration to destination.
    """
    source_answers = RegistrationAnswer.objects.filter(reg=source_reg)
    transferred_answers = []

    for answer in source_answers:
        # Find corresponding question in destination event
        target_question = _find_matching_question(answer.question, target_reg.run.event)
        if not target_question:
            continue

        # Create the new answer
        new_answer = RegistrationAnswer.objects.create(question=target_question, text=answer.text, reg=target_reg)
        transferred_answers.append(new_answer)

    return transferred_answers


def _find_matching_question(source_question: RegistrationQuestion, target_event) -> Optional[RegistrationQuestion]:
    """
    Find the corresponding question in the destination event.

    Matching logic:
    1. Match by type and exact name
    2. Match by type only (if it's a special type like TICKET, QUOTA, etc.)
    3. Match by name only
    """
    # Exact match by type and name
    exact_match = RegistrationQuestion.objects.filter(
        event=target_event, typ=source_question.typ, name=source_question.name
    ).first()

    if exact_match:
        return exact_match

    # For special types, match by type only
    special_types = [
        RegistrationQuestionType.TICKET,
        RegistrationQuestionType.ADDITIONAL,
        RegistrationQuestionType.PWYW,
        RegistrationQuestionType.QUOTA,
        RegistrationQuestionType.SURCHARGE,
    ]

    if source_question.typ in special_types:
        type_match = RegistrationQuestion.objects.filter(event=target_event, typ=source_question.typ).first()

        if type_match:
            return type_match

    # Match by name
    name_match = RegistrationQuestion.objects.filter(event=target_event, name=source_question.name).first()

    return name_match


def _find_matching_option(
    source_option: RegistrationOption, target_question: RegistrationQuestion
) -> Optional[RegistrationOption]:
    """
    Find the corresponding option in the destination question.
    """
    # Match by exact name
    exact_match = RegistrationOption.objects.filter(question=target_question, name=source_option.name).first()

    if exact_match:
        return exact_match

    # Match by description if name doesn't match
    desc_match = RegistrationOption.objects.filter(
        question=target_question, description=source_option.description
    ).first()

    return desc_match


def _transfer_character_relations(source_reg: Registration, target_reg: Registration):
    """
    Transfer character relationships from source registration to destination.
    """
    source_relations = RegistrationCharacterRel.objects.filter(reg=source_reg)

    for relation in source_relations:
        # Check that the character is available in the destination event
        # (considering campaigns that share characters)
        character_event = target_reg.run.event.get_class_parent("character")

        if relation.character.event == character_event:
            RegistrationCharacterRel.objects.create(
                reg=target_reg,
                character=relation.character,
                custom_name=relation.custom_name,
                custom_pronoun=relation.custom_pronoun,
                custom_song=relation.custom_song,
                custom_public=relation.custom_public,
                custom_private=relation.custom_private,
                custom_profile=relation.custom_profile,
            )


def _transfer_accounting_items(source_reg: Registration, target_reg: Registration):
    """
    Transfer accounting items (payments, invoices and other items) from source registration to destination.

    Note: This function transfers the accounting structure but resets payment amounts to 0
    to avoid double-counting payments. The actual financial reconciliation should be handled separately.
    """
    # Transfer PaymentInvoice records linked to the registration
    payment_invoices = PaymentInvoice.objects.filter(reg=source_reg)

    for invoice in payment_invoices:
        # Create new invoice record but reset financial amounts
        PaymentInvoice.objects.create(
            member=invoice.member,
            typ=invoice.typ,
            invoice=invoice.invoice,  # Keep reference to original invoice file
            text=f"Transferred from {source_reg.run}: {invoice.text or ''}".strip(),
            status=invoice.status,
            method=invoice.method,
            mc_gross=0,  # Reset payment amount
            mc_fee=0,  # Reset fee amount
            idx=invoice.idx,
            txn_id=None,  # Reset transaction ID to avoid conflicts
            causal=f"Transfer: {invoice.causal}",
            assoc=target_reg.run.event.assoc,
            reg=target_reg,
            verified=False,  # Reset verification status
            hide=invoice.hide,
            key=None,  # Reset key to avoid conflicts
        )

    # Transfer AccountingItemPayment records
    payment_items = AccountingItemPayment.objects.filter(reg=source_reg)

    for payment_item in payment_items:
        AccountingItemPayment.objects.create(
            member=payment_item.member,
            value=0,  # Reset payment amount - actual payments should be handled separately
            assoc=target_reg.run.event.assoc,
            pay=payment_item.pay,
            reg=target_reg,
            info=f"Transferred from {source_reg.run}: {payment_item.info or ''}".strip(),
            vat=payment_item.vat,
            hide=payment_item.hide,
        )

    # Transfer AccountingItemOther records linked to the run
    other_items = AccountingItemOther.objects.filter(member=source_reg.member, run=source_reg.run)

    for other_item in other_items:
        # Only transfer non-cancellation items or credits/tokens that make sense in the new context
        if not other_item.cancellation or other_item.oth in [OtherChoices.CREDIT, OtherChoices.TOKEN]:
            AccountingItemOther.objects.create(
                member=other_item.member,
                value=other_item.value,
                assoc=target_reg.run.event.assoc,
                oth=other_item.oth,
                run=target_reg.run,
                descr=f"Transferred from {source_reg.run}: {other_item.descr}",
                cancellation=False,  # Reset cancellation flag
                ref_addit=other_item.ref_addit,
                hide=other_item.hide,
            )


def _delete_original_registration_data(registration: Registration):
    """
    Delete the original registration and all its related data.

    This function removes:
    - Payment invoices linked to the registration (PaymentInvoice)
    - Registration choices (RegistrationChoice)
    - Registration answers (RegistrationAnswer)
    - Registration character relations (RegistrationCharacterRel)
    - Accounting items linked to the registration (AccountingItemPayment)
    - Accounting items linked to the member and run (AccountingItemOther)
    - The registration itself

    Note: This is called within a transaction so it will be rolled back if any part fails.
    """
    # Delete payment invoices linked to this registration
    PaymentInvoice.objects.filter(reg=registration).delete()

    # Delete registration choices
    RegistrationChoice.objects.filter(reg=registration).delete()

    # Delete registration answers
    RegistrationAnswer.objects.filter(reg=registration).delete()

    # Delete character relations
    RegistrationCharacterRel.objects.filter(reg=registration).delete()

    # Delete accounting items linked to this registration
    AccountingItemPayment.objects.filter(reg=registration).delete()

    # Delete accounting items linked to this member and run
    AccountingItemOther.objects.filter(member=registration.member, run=registration.run).delete()

    # Finally, delete the registration itself
    registration.delete()


def get_suggested_ticket_mapping(source_run: Run, target_run: Run) -> dict[int, int]:
    """
    Generate a suggested mapping between tickets of two runs.

    Args:
        source_run: The source run
        target_run: The target run

    Returns:
        Dictionary mapping source ticket IDs to target ticket IDs
    """
    source_tickets = RegistrationTicket.objects.filter(event=source_run.event)
    target_tickets = RegistrationTicket.objects.filter(event=target_run.event)

    mapping = {}

    for source_ticket in source_tickets:
        # Look for exact match
        exact_match = target_tickets.filter(tier=source_ticket.tier, name=source_ticket.name).first()

        if exact_match:
            mapping[source_ticket.id] = exact_match.id
            continue

        # Look for tier match
        tier_match = target_tickets.filter(tier=source_ticket.tier).first()
        if tier_match:
            mapping[source_ticket.id] = tier_match.id

    return mapping


def validate_transfer_feasibility(registration: Registration, target_run: Run) -> dict[str, list[str]]:
    """
    Validate if a registration transfer is feasible and return potential issues.

    Args:
        registration: The registration to transfer
        target_run: The target run

    Returns:
        Dictionary with validation results:
        {
            'errors': [...],      # Blocking errors
            'warnings': [...],    # Non-blocking issues
            'info': [...]         # Informational messages
        }
    """
    result = {"errors": [], "warnings": [], "info": []}

    # Check if member already has registration in target run
    existing_reg = Registration.objects.filter(
        run=target_run, member=registration.member, cancellation_date__isnull=True
    ).first()

    if existing_reg:
        result["errors"].append(f"Member already has an active registration in {target_run}")

    _validate_ticket(registration, result, target_run)

    # Check question matching
    source_questions = RegistrationQuestion.objects.filter(event=registration.run.event).count()

    target_questions = RegistrationQuestion.objects.filter(event=target_run.event).count()

    if source_questions != target_questions:
        result["info"].append(f"Number of questions differs: {source_questions} → {target_questions}")

    _validate_character(registration, result, target_run)

    # Check accounting items
    payment_invoices_count = PaymentInvoice.objects.filter(reg=registration).count()
    payment_items_count = AccountingItemPayment.objects.filter(reg=registration).count()
    other_items_count = AccountingItemOther.objects.filter(member=registration.member, run=registration.run).count()

    if payment_invoices_count > 0:
        result["info"].append(f"Found {payment_invoices_count} payment invoices - financial amounts will be reset")

    if payment_items_count > 0:
        result["info"].append(f"Found {payment_items_count} payment records - amounts will be reset to 0")

    if other_items_count > 0:
        transferable_other = (
            AccountingItemOther.objects.filter(member=registration.member, run=registration.run)
            .exclude(
                cancellation=True,
                oth__in=[OtherChoices.REFUND],  # Don't transfer refunds
            )
            .count()
        )

        if transferable_other < other_items_count:
            result["info"].append(
                f"Found {other_items_count} other accounting items - {transferable_other} will be transferred"
            )
        else:
            result["info"].append(f"Found {other_items_count} other accounting items to transfer")

    # Check for outstanding payments
    if registration.tot_iscr > registration.tot_payed:
        outstanding = registration.tot_iscr - registration.tot_payed
        result["warnings"].append(
            f"Registration has outstanding balance of {outstanding} - consider resolving before transfer"
        )

    return result


def _validate_character(registration, result, target_run):
    # Check character compatibility
    source_characters = registration.characters.all()
    if source_characters:
        character_event = target_run.event.get_class_parent("character")
        incompatible_chars = []

        for char in source_characters:
            if char.event != character_event:
                incompatible_chars.append(char.name)

        if incompatible_chars:
            result["warnings"].append(f"Characters not available in target event: {', '.join(incompatible_chars)}")


def _validate_ticket(registration, result, target_run):
    # Check ticket matching
    target_ticket = _find_matching_ticket(registration.ticket, target_run)
    if not target_ticket and registration.ticket:
        result["warnings"].append(
            f"No matching ticket found for '{registration.ticket.name}' ({registration.ticket.get_tier_display()})"
        )
    elif target_ticket and registration.ticket:
        if target_ticket.tier != registration.ticket.tier:
            result["info"].append(
                f"Ticket tier will change from {registration.ticket.get_tier_display()} to {target_ticket.get_tier_display()}"
            )
        if target_ticket.price != registration.ticket.price:
            result["info"].append(f"Ticket price will change from {registration.ticket.price} to {target_ticket.price}")


def copy_registration_between_runs(
    registration: Registration,
    target_run: Run,
    ticket_mapping: Optional[dict[int, int]] = None,
    preserve_choices: bool = True,
    preserve_answers: bool = True,
    preserve_accounting: bool = True,
) -> Registration:
    """
    Copy a registration from one run to another without deleting the original.

    This is a convenience wrapper around transfer_registration_between_runs with move_registration=False.

    Args:
        registration: The registration to copy
        target_run: The destination run
        ticket_mapping: Manual mapping between ticket IDs (source_ticket_id -> target_ticket_id)
        preserve_choices: Whether to preserve multiple choice selections
        preserve_answers: Whether to preserve text answers
        preserve_accounting: Whether to preserve accounting items (payments and other items)

    Returns:
        The new registration created in the target run

    Raises:
        ValidationError: If the copy is not possible
    """
    return transfer_registration_between_runs(
        registration=registration,
        target_run=target_run,
        ticket_mapping=ticket_mapping,
        preserve_choices=preserve_choices,
        preserve_answers=preserve_answers,
        preserve_accounting=preserve_accounting,
        move_registration=False,
    )


def move_registration_between_runs(
    registration: Registration,
    target_run: Run,
    ticket_mapping: Optional[dict[int, int]] = None,
    preserve_choices: bool = True,
    preserve_answers: bool = True,
    preserve_accounting: bool = True,
) -> Registration:
    """
    Move a registration from one run to another, deleting the original.

    This is a convenience wrapper around transfer_registration_between_runs with move_registration=True.

    Args:
        registration: The registration to move
        target_run: The destination run
        ticket_mapping: Manual mapping between ticket IDs (source_ticket_id -> target_ticket_id)
        preserve_choices: Whether to preserve multiple choice selections
        preserve_answers: Whether to preserve text answers
        preserve_accounting: Whether to preserve accounting items (payments and other items)

    Returns:
        The new registration created in the target run

    Raises:
        ValidationError: If the move is not possible
    """
    return transfer_registration_between_runs(
        registration=registration,
        target_run=target_run,
        ticket_mapping=ticket_mapping,
        preserve_choices=preserve_choices,
        preserve_answers=preserve_answers,
        preserve_accounting=preserve_accounting,
        move_registration=True,
    )
