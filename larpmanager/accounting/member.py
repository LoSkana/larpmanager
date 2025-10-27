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

from datetime import datetime
from typing import Any

from dateutil.relativedelta import relativedelta
from django.http import HttpRequest

from larpmanager.cache.config import get_assoc_config
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemMembership,
    AccountingItemOther,
    Collection,
    OtherChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
    RefundStatus,
)
from larpmanager.models.event import DevelopStatus
from larpmanager.models.form import RegistrationChoice
from larpmanager.models.member import get_user_membership
from larpmanager.models.registration import Registration


def info_accounting(request: HttpRequest, context: dict[str, Any]) -> None:
    """Gather comprehensive accounting information for a member.

    Collects registration history, payment status, membership fees, donations,
    collections, refunds, and token/credit balances for display in member dashboard.

    Args:
        request: Django HTTP request object containing user session and metadata
        context: Context dictionary containing member object and association ID (association_id).
             Modified in-place to include accounting data.

    Returns:
        None: Function modifies context dictionary in-place

    Side Effects:
        Populates context with the following keys:
        - registration_list: List of registration records
        - payments_todo: Outstanding payments requiring action
        - payments_pending: Payments awaiting processing
        - refunds: Active refund requests
        - registration_years: Registration data grouped by year
        - Various balance and membership information
    """
    member = context["member"]
    # Initialize user membership data for the given association
    get_user_membership(member, context["association_id"])
    context["registration_list"] = []

    # Gather membership fee information and status
    _info_membership(context, member, request)

    # Collect donation history and outstanding donations
    _info_donations(context, member, request)

    # Process collection records and payment collections
    _info_collections(context, member, request)

    # Initialize registration years tracking dictionary
    context["registration_years"] = {}

    # Set up pending payments tracking for the member
    pending_payments = _init_pending(member)

    # Initialize payment choices and options
    payment_choices = _init_choices(member)

    # Initialize payment status lists for todo and pending items
    for status in ["payments_todo", "payments_pending"]:
        context[status] = []

    # Query all registrations for this member in the current association
    # Exclude cancelled events from the development status
    registration_query = Registration.objects.filter(member=member, run__event__assoc_id=context["association_id"])
    registration_query = registration_query.exclude(run__development__in=[DevelopStatus.CANC])

    # Process each registration to populate payment and status information
    for registration in registration_query.select_related("run", "run__event", "ticket"):
        _init_regs(payment_choices, context, pending_payments, registration)

    # Retrieve open refund requests for this member and association
    context["refunds"] = context["member"].refund_requests.filter(
        status=RefundStatus.REQUEST, assoc_id=context["association_id"]
    )

    # Calculate and add token/credit balance information
    _info_token_credit(context, member)


def _init_regs(registration_choices, context, pending_invoices, registration):
    """Initialize registration options and payment status tracking.

    Args:
        registration_choices: Dictionary mapping registration IDs to their selected options
        context: Context dictionary to update with payment status
        pending_invoices: Dictionary of pending payment invoices
        registration: Registration instance to process

    Side effects:
        Updates context with payments_pending and payments_todo lists
        Sets registration.opts and registration.pending attributes
    """
    if registration.id not in registration_choices:
        registration_choices[registration.id] = {}
    registration.opts = registration_choices[registration.id]
    context["registration_list"].append(registration)

    # check if there is a pending payment
    if registration.id in pending_invoices:
        registration.pending = True
        context["payments_pending"].append(registration)
    elif registration.quota > 0:
        context["payments_todo"].append(registration)
    if registration.run.start:
        if registration.run.start < datetime.now().date():
            return
        context["registration_years"][registration.run.start.year] = 1


def _init_pending(member):
    """Initialize pending payment tracking for a member.

    Args:
        member: Member instance to check for pending payments

    Returns:
        dict: Mapping of registration IDs to lists of pending payment invoices
    """
    pending_payments_by_registration = {}
    pending_payment_invoices = PaymentInvoice.objects.filter(
        member_id=member.id,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.REGISTRATION,
    )
    for payment_invoice in pending_payment_invoices:
        if payment_invoice.idx not in pending_payments_by_registration:
            pending_payments_by_registration[payment_invoice.idx] = []
        pending_payments_by_registration[payment_invoice.idx].append(payment_invoice)
    return pending_payments_by_registration


def _init_choices(member):
    """Initialize registration choice tracking for a member.

    Args:
        member: Member instance to get registration choices for

    Returns:
        dict: Nested mapping of registration and question IDs to selected options
    """
    choices = {}
    choice_queryset = RegistrationChoice.objects.filter(reg__member_id=member.id)
    choice_queryset = choice_queryset.select_related("option", "question").order_by("question__order")
    for registration_choice in choice_queryset:
        if registration_choice.reg_id not in choices:
            choices[registration_choice.reg_id] = {}
        if registration_choice.question_id not in choices[registration_choice.reg_id]:
            choices[registration_choice.reg_id][registration_choice.question_id] = {
                "question": registration_choice.question,
                "selected_options": [],
            }
        choices[registration_choice.reg_id][registration_choice.question_id]["selected_options"].append(
            registration_choice.option
        )
    return choices


def _info_token_credit(context, member):
    """Get token and credit balance information for a member.

    Args:
        context: Context dictionary with association ID to update
        member: Member instance to check balances for

    Side effects:
        Updates context with acc_tokens and acc_credits counts
    """
    # check if it had any token
    token_queryset = AccountingItemOther.objects.filter(
        member=member,
        oth=OtherChoices.TOKEN,
        assoc_id=context["association_id"],
    )
    context["acc_tokens"] = token_queryset.count()

    # check if it had any credits
    expense_queryset = AccountingItemExpense.objects.filter(
        member=member, is_approved=True, assoc_id=context["association_id"]
    )
    credit_queryset = AccountingItemOther.objects.filter(
        member=member,
        oth=OtherChoices.CREDIT,
        assoc_id=context["association_id"],
    )
    context["acc_credits"] = expense_queryset.count() + credit_queryset.count()


def _info_collections(context, member, request):
    """Get collection information if collections feature is enabled.

    Args:
        context: Context dictionary with association ID to update
        member: Member instance to get collections for
        request: Django request with association features

    Side effects:
        Updates context with collections and collection_gifts if feature enabled
    """
    if "collection" not in context["features"]:
        return

    context["collections"] = Collection.objects.filter(organizer=member, assoc_id=context["association_id"])
    context["collection_gifts"] = AccountingItemCollection.objects.filter(
        member=member, collection__assoc_id=context["association_id"]
    )


def _info_donations(context, member, request):
    """Get donation history if donations feature is enabled.

    Args:
        context: Context dictionary with association ID to update
        member: Member instance to get donations for
        request: Django request with association features

    Side effects:
        Updates context with donations list if feature enabled
    """
    if "donate" not in context["features"]:
        return

    donation_queryset = AccountingItemDonation.objects.filter(member=member, assoc_id=context["association_id"])
    context["donations"] = donation_queryset.order_by("-created")


def _info_membership(context: dict, member, request) -> None:
    """Get membership fee information if membership feature is enabled.

    Retrieves and adds membership-related information to the context dictionary,
    including fee history, current year status, pending payments, and grace period
    calculations. Only processes if the membership feature is enabled for the association.

    Args:
        context: Context dictionary containing association ID, will be updated with
             membership information including fee history and status flags
        member: Member instance to retrieve membership information for
        request: Django request object containing association features configuration

    Returns:
        None: Function modifies context dictionary in-place

    Side Effects:
        Updates context with the following keys if membership feature is enabled:
        - membership_fee: List of years with membership fees
        - year_membership_fee: Boolean indicating if current year fee exists
        - year_membership_pending: Boolean indicating pending membership payments
        - year: Current year
        - grazing: Boolean indicating if within grace period
    """
    # Early return if membership feature is not enabled
    if "membership" not in context["features"]:
        return

    # Get current year for membership calculations
    current_year = datetime.now().year

    # Retrieve all membership fee years for this member and association
    context["membership_fee"] = []
    for membership_item in AccountingItemMembership.objects.filter(
        member=member, assoc_id=context["association_id"]
    ).order_by("year"):
        context["membership_fee"].append(membership_item.year)

    # Check if current year membership fee exists
    context["year_membership_fee"] = current_year in context["membership_fee"]

    # Check for pending membership payment invoices
    pending_invoices_query = PaymentInvoice.objects.filter(
        member=member,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.MEMBERSHIP,
    )
    if pending_invoices_query.count() > 0:
        context["year_membership_pending"] = True

    # Store current year in context
    context["year"] = current_year

    # Get membership day configuration (default: January 1st)
    membership_day = get_assoc_config(context["association_id"], "membership_day", "01-01", context)
    if membership_day:
        # Get grace period in months (default: 0 months)
        membership_grace_period_months = int(
            get_assoc_config(context["association_id"], "membership_grazing", "0", context)
        )

        # Build full date string with current year
        membership_day += f"-{current_year}"
        membership_deadline_date = datetime.strptime(membership_day, "%d-%m-%Y")

        # Add grace period months to membership date
        membership_deadline_date += relativedelta(months=membership_grace_period_months)

        # Check if we're still within the grace period
        context["grazing"] = datetime.now() < membership_deadline_date
