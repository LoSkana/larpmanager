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

from calmjs.parse.asttypes import Object
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
from larpmanager.models.member import Member, get_user_membership
from larpmanager.models.registration import Registration


def info_accounting(request: HttpRequest, ctx: dict[str, Any]) -> None:
    """Gather comprehensive accounting information for a member.

    Collects registration history, payment status, membership fees, donations,
    collections, refunds, and token/credit balances for display in member dashboard.

    Args:
        request: Django HTTP request object containing user session and metadata
        ctx: Context dictionary containing member object and association ID (a_id).
             Modified in-place to include accounting data.

    Returns:
        None: Function modifies ctx dictionary in-place

    Side Effects:
        Populates ctx with the following keys:
        - reg_list: List of registration records
        - payments_todo: Outstanding payments requiring action
        - payments_pending: Payments awaiting processing
        - refunds: Active refund requests
        - reg_years: Registration data grouped by year
        - Various balance and membership information
    """
    member = ctx["member"]
    # Initialize user membership data for the given association
    get_user_membership(member, ctx["a_id"])
    ctx["reg_list"] = []

    # Gather membership fee information and status
    _info_membership(ctx, member, request)

    # Collect donation history and outstanding donations
    _info_donations(ctx, member, request)

    # Process collection records and payment collections
    _info_collections(ctx, member, request)

    # Initialize registration years tracking dictionary
    ctx["reg_years"] = {}

    # Set up pending payments tracking for the member
    pending = _init_pending(member)

    # Initialize payment choices and options
    choices = _init_choices(member)

    # Initialize payment status lists for todo and pending items
    for s in ["payments_todo", "payments_pending"]:
        ctx[s] = []

    # Query all registrations for this member in the current association
    # Exclude cancelled events from the development status
    reg_que = Registration.objects.filter(member=member, run__event__assoc_id=ctx["a_id"])
    reg_que = reg_que.exclude(run__development__in=[DevelopStatus.CANC])

    # Process each registration to populate payment and status information
    for reg in reg_que.select_related("run", "run__event", "ticket"):
        _init_regs(choices, ctx, pending, reg)

    # Retrieve open refund requests for this member and association
    ctx["refunds"] = ctx["member"].refund_requests.filter(status=RefundStatus.REQUEST, assoc_id=ctx["a_id"])

    # Calculate and add token/credit balance information
    _info_token_credit(ctx, member)


def _init_regs(choices: dict[int, dict], ctx: dict, pending: dict[int, bool], reg: Registration) -> None:
    """Initialize registration options and payment status tracking.

    This function processes a registration instance by setting up its options,
    tracking payment status, and updating the context with relevant payment
    information for the registration workflow.

    Args:
        choices: Dictionary mapping registration IDs to their selected options.
            Keys are registration IDs (int), values are option dictionaries.
        ctx: Context dictionary to update with payment status information.
            Must contain 'reg_list', 'payments_pending', 'payments_todo',
            and 'reg_years' keys.
        pending: Dictionary of pending payment invoices. Keys are registration
            IDs (int), values indicate pending status (bool).
        reg: Registration instance to process. Must have id, quota, and run
            attributes.

    Returns:
        None

    Side Effects:
        - Updates ctx['reg_list'] with the registration instance
        - Updates ctx['payments_pending'] if payment is pending
        - Updates ctx['payments_todo'] if payment is required
        - Updates ctx['reg_years'] with the registration year
        - Sets reg.opts attribute with selected options
        - Sets reg.pending attribute if payment is pending
    """
    # Initialize registration options if not already present
    if reg.id not in choices:
        choices[reg.id] = {}
    reg.opts = choices[reg.id]
    ctx["reg_list"].append(reg)

    # Process payment status and categorize registration accordingly
    if reg.id in pending:
        # Mark registration as having pending payment
        reg.pending = True
        ctx["payments_pending"].append(reg)
    elif reg.quota > 0:
        # Add to todo list if payment is required (quota > 0)
        ctx["payments_todo"].append(reg)

    # Track registration years for events that have started
    if reg.run.start:
        # Skip processing if event has already started
        if reg.run.start < datetime.now().date():
            return
        # Record the year for grouping purposes
        ctx["reg_years"][reg.run.start.year] = 1


def _init_pending(member: Member) -> dict[int, list[PaymentInvoice]]:
    """Initialize pending payment tracking for a member.

    This function queries the database for submitted registration payment invoices
    associated with the given member and organizes them by registration ID.

    Args:
        member: Member instance to check for pending payments

    Returns:
        dict: Mapping of registration IDs to lists of pending payment invoices.
              Keys are registration IDs (int), values are lists of PaymentInvoice objects.
    """
    # Initialize empty dictionary to store pending payments by registration ID
    pending = {}

    # Query for submitted registration payment invoices for this member
    pending_que = PaymentInvoice.objects.filter(
        member_id=member.id,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.REGISTRATION,
    )

    # Group payment invoices by registration ID (idx field)
    for el in pending_que:
        if el.idx not in pending:
            pending[el.idx] = []
        pending[el.idx].append(el)

    return pending


def _init_choices(member: Member) -> dict[int, dict[int, dict[str, any]]]:
    """Initialize registration choice tracking for a member.

    Creates a nested dictionary structure mapping registration IDs to question IDs
    to their selected options and question objects.

    Args:
        member (Member): Member instance to get registration choices for

    Returns:
        dict[int, dict[int, dict[str, any]]]: Nested mapping structure where:
            - First level keys are registration IDs (int)
            - Second level keys are question IDs (int)
            - Third level contains:
                - 'q': Question object
                - 'l': List of selected Option objects

    Example:
        {
            123: {  # registration_id
                456: {  # question_id
                    'q': Question(...),
                    'l': [Option(...), Option(...)]
                }
            }
        }
    """
    choices = {}

    # Get all registration choices for this member with related objects
    choice_que = RegistrationChoice.objects.filter(reg__member_id=member.id)
    choice_que = choice_que.select_related("option", "question")

    # Build nested dictionary structure from query results
    for el in choice_que:
        # Initialize registration level if not exists
        if el.reg_id not in choices:
            choices[el.reg_id] = {}

        # Initialize question level if not exists
        if el.question_id not in choices[el.reg_id]:
            choices[el.reg_id][el.question_id] = {"q": el.question, "l": []}

        # Add option to the list for this question
        choices[el.reg_id][el.question_id]["l"].append(el.option)

    return choices


def _info_token_credit(ctx: dict, member: Member) -> None:
    """Get token and credit balance information for a member.

    Retrieves the count of tokens and credits associated with a member
    for a specific association and updates the context dictionary with
    the results.

    Args:
        ctx: Context dictionary containing association ID ('a_id') that
             will be updated with token and credit counts
        member: Member instance to check balances for

    Returns:
        None: Function modifies ctx in-place

    Side Effects:
        Updates ctx with:
        - acc_tokens: Count of token items for the member
        - acc_credits: Combined count of approved expenses and credit items
    """
    # Query for token items associated with the member
    que = AccountingItemOther.objects.filter(
        member=member,
        oth=OtherChoices.TOKEN,
        assoc_id=ctx["a_id"],
    )
    # Store token count in context
    ctx["acc_tokens"] = que.count()

    # Query for approved expense items for credit calculation
    que_exp = AccountingItemExpense.objects.filter(member=member, is_approved=True, assoc_id=ctx["a_id"])

    # Query for credit items associated with the member
    que_cre = AccountingItemOther.objects.filter(
        member=member,
        oth=OtherChoices.CREDIT,
        assoc_id=ctx["a_id"],
    )
    # Calculate total credits from both expenses and credit items
    ctx["acc_credits"] = que_exp.count() + que_cre.count()


def _info_collections(ctx: dict, member: Member, request: HttpRequest) -> None:
    """Get collection information if collections feature is enabled.

    Retrieves collection data for a member and updates the context dictionary
    with collections and collection gifts if the collections feature is enabled
    for the association.

    Args:
        ctx: Context dictionary containing association ID, will be updated
             with collection data if feature is enabled
        member: Member instance to retrieve collections for
        request: Django request object containing association features

    Returns:
        None: Function modifies ctx dictionary in-place

    Side Effects:
        Updates ctx with 'collections' and 'collection_gifts' keys if
        collections feature is enabled for the association
    """
    # Check if collections feature is enabled for this association
    if "collection" not in request.assoc["features"]:
        return

    # Get all collections organized by this member for the current association
    ctx["collections"] = Collection.objects.filter(organizer=member, assoc_id=ctx["a_id"])

    # Get all collection gifts received by this member in the current association
    ctx["collection_gifts"] = AccountingItemCollection.objects.filter(member=member, collection__assoc_id=ctx["a_id"])


def _info_donations(ctx: dict, member: Member, request: HttpRequest) -> None:
    """Get donation history if donations feature is enabled.

    Args:
        ctx: Context dictionary with association ID to update with donations list
        member: Member instance to get donations for
        request: Django request object containing association features

    Returns:
        None: Function modifies ctx dictionary in place

    Side Effects:
        Updates ctx with 'donations' key containing ordered donation queryset
        if donations feature is enabled for the association
    """
    # Check if donations feature is enabled for this association
    if "donate" not in request.assoc["features"]:
        return

    # Query donation items for the specific member and association
    que = AccountingItemDonation.objects.filter(member=member, assoc_id=ctx["a_id"])

    # Add ordered donations to context (newest first)
    ctx["donations"] = que.order_by("-created")


def _info_membership(ctx: dict, member: Member, request: HttpRequest) -> None:
    """Get membership fee information if membership feature is enabled.

    Retrieves membership fee history, current year status, pending payments,
    and grace period information for a member if the membership feature is
    enabled for the association.

    Args:
        ctx: Context dictionary containing association ID that will be updated
             with membership information
        member: Member instance to retrieve membership information for
        request: Django request object containing association features

    Returns:
        None: Function modifies ctx dictionary in place

    Side Effects:
        Updates ctx with the following keys if membership feature is enabled:
        - membership_fee: List of years with membership fees paid
        - year_membership_fee: Boolean indicating if current year fee is paid
        - year_membership_pending: Boolean indicating if payment is pending
        - year: Current year
        - grazing: Boolean indicating if within grace period
    """
    # Early return if membership feature is not enabled
    if "membership" not in request.assoc["features"]:
        return

    # Get current year for membership calculations
    year = datetime.now().year

    # Retrieve all membership fee years for this member and association
    ctx["membership_fee"] = []
    for el in AccountingItemMembership.objects.filter(member=member, assoc_id=ctx["a_id"]).order_by("year"):
        ctx["membership_fee"].append(el.year)

    # Check if current year membership fee has been paid
    ctx["year_membership_fee"] = year in ctx["membership_fee"]

    # Check for pending membership payments
    pending_que = PaymentInvoice.objects.filter(
        member=member,
        status=PaymentStatus.SUBMITTED,
        typ=PaymentType.MEMBERSHIP,
    )
    if pending_que.count() > 0:
        ctx["year_membership_pending"] = True

    # Set current year in context
    ctx["year"] = year

    # Initialize config holder for association settings
    config_holder = Object()

    # Get membership day and calculate grace period
    m_day = get_assoc_config(ctx["a_id"], "membership_day", "01-01", config_holder)
    if m_day:
        # Get grace period in months and build full date string
        m_grazing = int(get_assoc_config(ctx["a_id"], "membership_grazing", "0", config_holder))
        m_day += f"-{year}"

        # Parse membership date and add grace period
        dt = datetime.strptime(m_day, "%d-%m-%Y")
        dt += relativedelta(months=m_grazing)

        # Check if we're still within the grace period
        ctx["grazing"] = datetime.now() < dt
