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

from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.http import Http404
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import is_registration_provisional
from larpmanager.mail.base import bring_friend_instructions
from larpmanager.mail.registration import update_registration_status_bkg
from larpmanager.models.accounting import AccountingItemDiscount, AccountingItemOther, OtherChoices
from larpmanager.models.event import Event, Run
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.models.utils import my_uuid
from larpmanager.utils.core.common import get_object_uuid
from larpmanager.utils.registrations.characters import check_assign_character

logger = logging.getLogger(__name__)

_NON_PLAYER_TIERS = TicketTier.non_player_tiers()


def _enforce_capacity_under_lock(run: Run, registration: Registration) -> None:
    """Re-check event and per-ticket capacity under the held run lock.

    Must be called inside the transaction that locked the run row. Raises
    PermissionDenied if adding this registration would exceed the event's
    max_pg or the chosen ticket's max_available (closes oversell TOCTOU races
    left open by the pre-lock, form-level validation).
    """
    # Event-wide player cap
    if run.event.max_pg > 0 and registration.ticket and registration.ticket.tier not in _NON_PLAYER_TIERS:
        player_count = (
            Registration.objects.filter(run=run, cancellation_date__isnull=True)
            .exclude(ticket__tier__in=_NON_PLAYER_TIERS)
            .exclude(pk=registration.pk)
            .count()
        )
        if player_count >= run.event.max_pg:
            raise PermissionDenied

    # Per-ticket availability cap
    if registration.ticket and registration.ticket.max_available > 0:
        other_seats = (
            Registration.objects.filter(
                run=run,
                ticket=registration.ticket,
                cancellation_date__isnull=True,
            )
            .exclude(pk=registration.pk)
            .aggregate(total=models.Sum(1 + models.F("additionals")))["total"]
            or 0
        )
        if other_seats >= registration.ticket.max_available:
            raise PermissionDenied


def save_registration(
    context: dict,
    form: object,  # Registration form instance
    run: Run,
    event: Event,
    registration: Registration | None,
    *,
    gifted: bool = False,
) -> Registration:
    """Save registration data and handle payment processing.

    This function creates or updates a registration record within a database transaction,
    handling standard registration data, questions, discounts, and special features.

    Args:
        context: Context dictionary with form data, event info, and feature flags
        form: Registration form instance with cleaned data
        run: Run instance being registered for
        event: Event instance associated with the run
        registration: Existing registration instance to update, or None to create new
        gifted: Whether this is a gifted registration requiring redeem code

    Returns:
        Registration: The saved registration instance

    Note:
        This function handles special features like user_character assignment
        and bring_friend functionality based on context feature flags.

    """
    is_new = not registration

    # Create or update registration within atomic transaction
    with transaction.atomic():
        # Lock the run row to serialise concurrent new registrations
        if is_new:
            Run.objects.select_for_update().get(pk=run.pk)

        # Initialize new registration if none provided
        if is_new:
            registration = Registration()
            registration.run = run
            registration.member = context["member"]
            # Generate redeem code for gifted registrations
            if gifted:
                registration.redeem_code = my_uuid(16)
            registration.save()

        # Determine if registration should be provisional
        provisional = is_registration_provisional(registration)

        # Save standard registration fields and data
        save_registration_standard(context, event, form, registration, gifted=gifted, provisional=provisional)

        # Enforce max_pg and per-ticket availability atomically under the run lock
        if is_new:
            _enforce_capacity_under_lock(run, registration)

        # Process and save registration-specific questions
        form.save_registration_questions(registration, is_organizer=False)

        # Confirm and finalize any pending discounts for this member/run
        que = AccountingItemDiscount.objects.filter(member=context["member"], run=registration.run)
        for el in que:
            # Remove expiration date to confirm discount usage
            if el.expires is not None:
                el.expires = None
                el.save()

        # Save the updated registration instance
        registration.save()

        # Handle special feature processing based on context flags
        if "user_character" in context["features"]:
            check_assign_character(context)
        if "bring_friend" in context["features"]:
            save_registration_bring_friend(context, form, registration)

    # Send background notification email for registration update
    update_registration_status_bkg(registration.id)

    return registration


def save_registration_standard(
    context: dict,
    event: Event,
    form: object,  # RegistrationForm instance
    registration: Registration,
    *,
    gifted: bool,
    provisional: bool,
) -> None:
    """Save standard registration with ticket and payment processing.

    Processes a standard registration by updating modification counter,
    handling additional participants, quotas, ticket selection, and
    custom payment amounts based on form data.

    Args:
        context: Context dictionary containing event and form data, including 'tot_payed'
        event: Event instance for validation and processing
        form: Registration form instance with cleaned_data
        gifted: Whether this is a gifted registration (skips modification counter)
        provisional: Whether registration is provisional (skips modification counter)
        registration: Registration instance to update with form data

    Raises:
        Http404: When ticket doesn't exist, belongs to wrong event, or has lower price
                than current ticket for paid registrations

    Side Effects:
        Modifies the registration instance with form data including:
        - Increments modification counter for non-gifted, non-provisional registrations
        - Updates additionals count, quotas, ticket selection, and payment amount

    """
    # Increment modification counter for standard registrations
    if not gifted and not provisional:
        registration.modified = registration.modified + 1

    # Process additional participants count
    if "additionals" in form.cleaned_data:
        additionals_value = form.cleaned_data["additionals"]
        registration.additionals = int(additionals_value) if additionals_value else 0

    # Handle quota assignments if present
    if form.cleaned_data.get("quotas"):
        quotas_value = form.cleaned_data["quotas"]
        registration.quotas = int(quotas_value) if quotas_value else 0

    # Process ticket selection and validation
    if "ticket" in form.cleaned_data:
        sel = form.cleaned_data["ticket"]

        # Validate ticket exists and belongs to correct event
        if not sel:
            msg = "RegistrationTicket does not exist"
            raise Http404(msg)

        if sel.event_id != event.id:
            msg = "RegistrationTicket wrong event"
            raise Http404(msg)

        # Prevent downgrading ticket price for paid registrations
        if (
            context["tot_payed"]
            and registration.ticket
            and registration.ticket.price > 0
            and sel.price < registration.ticket.price
        ):
            msg = "lower price"
            raise Http404(msg)
        registration.ticket = sel

    # Set custom payment amount if specified
    if form.cleaned_data.get("pay_what"):
        registration.pay_what = int(form.cleaned_data["pay_what"])


def save_registration_bring_friend(context: dict, form: object, registration: Registration) -> None:
    """Process bring-a-friend discount codes for registration.

    This function handles the bring-a-friend functionality by:
    1. Sending instructions email to the registrant
    2. Validating the provided friend code
    3. Creating accounting entries for both parties
    4. Applying discounts to both the registrant and their friend

    Args:
        context: Context dictionary containing bring friend configuration including:
            - bring_friend_discount_from: Discount amount for code user
            - bring_friend_discount_to: Discount amount for code owner
            - run: Event run instance
            - a_id: Association ID
        form: Registration form with bring_friend field containing the friend code
        registration: Registration instance for the current registrant

    Raises:
        Http404: When the provided friend code is not found in the database

    """
    # Send bring-a-friend instructions email to the new registrant
    bring_friend_instructions(registration, context)

    # Early return if no bring_friend field in form data
    if "bring_friend" not in form.cleaned_data:
        return
    logger.debug("Bring friend form data: %s", form.cleaned_data)

    # Extract and validate the friend code from form
    cod = form.cleaned_data["bring_friend"]
    logger.debug("Processing bring friend code: %s", cod)
    if not cod:
        return

    # Look up the registration associated with the friend code
    friend = get_object_uuid(Registration, cod)

    # Create accounting entries atomically for both parties
    with transaction.atomic():
        # Create discount token for the person using the friend code
        AccountingItemOther.objects.create(
            member=context["member"],
            value=int(context["bring_friend_discount_from"]),
            run=context["run"],
            oth=OtherChoices.TOKEN,
            descr=_("You have used a friend code.") + f" - {friend.member.display_member()} - {cod}",
            association_id=context["association_id"],
            ref_addit=registration.id,
        )

        # Create discount token for the friend whose code was used
        AccountingItemOther.objects.create(
            member=friend.member,
            value=int(context["bring_friend_discount_to"]),
            run=context["run"],
            oth=OtherChoices.TOKEN,
            descr=_("Your friend code has been used") + f" - {context['member'].display_member()} - {cod}",
            association_id=context["association_id"],
            ref_addit=friend.id,
        )

        # Trigger accounting update for the friend's registration
        friend.save()
