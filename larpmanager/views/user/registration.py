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
import traceback
from datetime import datetime, timedelta
from typing import Any, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.timezone import now as timezone_now
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.accounting.base import is_reg_provisional
from larpmanager.accounting.member import info_accounting
from larpmanager.accounting.registration import cancel_reg
from larpmanager.cache.config import get_assoc_config, get_event_config
from larpmanager.cache.feature import get_assoc_features
from larpmanager.forms.registration import (
    PreRegistrationForm,
    RegistrationForm,
    RegistrationGiftForm,
)
from larpmanager.mail.base import bring_friend_instructions
from larpmanager.mail.registration import update_registration_status_bkg
from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemMembership,
    AccountingItemOther,
    Discount,
    OtherChoices,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.association import AssocTextType
from larpmanager.models.event import (
    Event,
    EventTextType,
    PreRegistration,
    Run,
)
from larpmanager.models.member import Member, MembershipStatus, get_user_membership
from larpmanager.models.registration import (
    Registration,
    RegistrationTicket,
    TicketTier,
)
from larpmanager.models.utils import my_uuid
from larpmanager.utils.base import def_user_ctx
from larpmanager.utils.event import get_event, get_event_run
from larpmanager.utils.exceptions import (
    RedirectError,
    RewokedMembershipError,
    check_event_feature,
)
from larpmanager.utils.registration import check_assign_character, get_reduced_available_count
from larpmanager.utils.text import get_assoc_text, get_event_text

logger = logging.getLogger(__name__)


@login_required
def pre_register(request: HttpRequest, s: str = "") -> HttpResponse:
    """Handle pre-registration for events before full registration opens.

    Allows users to express interest in events and set preference order,
    optionally with additional information. Manages list of existing
    pre-registrations and creates new ones.

    Args:
        request: HTTP request object with authenticated user
        s: Optional event slug to pre-register for specific event, empty shows all

    Returns:
        HttpResponse: Pre-registration form page or redirect after successful save

    Side effects:
        - Creates PreRegistration records linking member to events
        - Saves preference order and additional info
    """
    # Handle specific event pre-registration vs all events listing
    if s:
        # Get context for specific event and verify pre-register feature is active
        ctx = get_event(request, s)
        ctx["sel"] = ctx["event"].id
        check_event_feature(request, ctx, "pre_register")
    else:
        # Show all available events for pre-registration
        ctx = def_user_ctx(request)
        ctx.update({"features": get_assoc_features(request.assoc["id"])})

    # Initialize event lists for template
    ctx["choices"] = []  # Events available for new pre-registration
    ctx["already"] = []  # Events user has already pre-registered for
    ctx["member"] = request.user.member

    # Check if preference ordering is enabled
    ctx["preferences"] = get_assoc_config(request.assoc["id"], "pre_reg_preferences", False)

    # Build set of already pre-registered event IDs
    ch = {}
    que = PreRegistration.objects.filter(member=request.user.member, event__assoc_id=request.assoc["id"])
    for el in que.order_by("pref"):
        ch[el.event_id] = True
        ctx["already"].append(el)

    # Find events available for pre-registration
    for r in Event.objects.filter(assoc_id=request.assoc["id"], template=False):
        # Skip if pre-registration not active for this event
        if not get_event_config(r.id, "pre_register_active", False):
            continue

        # Skip if user already pre-registered
        if r.id in ch:
            continue

        ctx["choices"].append(r)

    # Handle form submission for new pre-registration
    if request.method == "POST":
        form = PreRegistrationForm(request.POST, ctx=ctx)
        if form.is_valid():
            nr = form.cleaned_data["new_event"]
            # Only save if an event was actually selected
            if nr != "":
                with transaction.atomic():
                    PreRegistration(
                        member=request.user.member,
                        event_id=nr,
                        pref=form.cleaned_data["new_pref"],
                        info=form.cleaned_data["new_info"],
                    ).save()

            messages.success(request, _("Pre-registrations saved") + "!")
            return redirect("pre_register")
    else:
        form = PreRegistrationForm(ctx=ctx)
    ctx["form"] = form

    return render(request, "larpmanager/general/pre_register.html", ctx)


@login_required
def pre_register_remove(request, s):
    """Remove user's pre-registration for an event.

    Args:
        request: Django HTTP request object (must be authenticated)
        s: Event slug to remove pre-registration from

    Returns:
        HttpResponse: Redirect to pre-registration list
    """
    ctx = get_event(request, s)
    element = PreRegistration.objects.get(member=request.user.member, event=ctx["event"])
    element.delete()
    messages.success(request, _("Pre-registration cancelled!"))
    return redirect("pre_register")


@login_required
def register_exclusive(request, s, sc="", dis=""):
    """Handle exclusive event registration (delegates to main register function).

    Args:
        request: Django HTTP request object
        s: Event slug
        sc: Secret code (optional)
        dis: Discount code (optional)

    Returns:
        HttpResponse: Result from register function
    """
    return register(request, s, sc, dis)


def save_registration(
    request: HttpRequest,
    ctx: dict[str, Any],
    form: Any,  # Registration form instance
    run: Run,
    event: Event,
    reg: Optional[Registration],
    gifted: bool = False,
) -> "Registration":
    """Save registration data and handle payment processing.

    This function creates or updates a registration record within a database transaction,
    handling standard registration data, questions, discounts, and special features.

    Args:
        request: Django HTTP request object containing user information
        ctx: Context dictionary with form data, event info, and feature flags
        form: Registration form instance with cleaned data
        run: Run instance being registered for
        event: Event instance associated with the run
        reg: Existing registration instance to update, or None to create new
        gifted: Whether this is a gifted registration requiring redeem code

    Returns:
        Registration: The saved registration instance

    Note:
        This function handles special features like user_character assignment
        and bring_friend functionality based on context feature flags.
    """
    # pprint(form.cleaned_data)  # Debug output for form data

    # Create or update registration within atomic transaction
    with transaction.atomic():
        # Initialize new registration if none provided
        if not reg:
            reg = Registration()
            reg.run = run
            reg.member = request.user.member
            # Generate redeem code for gifted registrations
            if gifted:
                reg.redeem_code = my_uuid(16)
            reg.save()

        # Determine if registration should be provisional
        provisional = is_reg_provisional(reg)

        # Save standard registration fields and data
        save_registration_standard(ctx, event, form, gifted, provisional, reg)

        # Process and save registration-specific questions
        form.save_reg_questions(reg, False)

        # Confirm and finalize any pending discounts for this member/run
        que = AccountingItemDiscount.objects.filter(member=request.user.member, run=reg.run)
        for el in que:
            # Remove expiration date to confirm discount usage
            if el.expires is not None:
                el.expires = None
                el.save()

        # Save the updated registration instance
        reg.save()

        # Handle special feature processing based on context flags
        if "user_character" in ctx["features"]:
            check_assign_character(request, ctx)
        if "bring_friend" in ctx["features"]:
            save_registration_bring_friend(ctx, form, reg, request)

    # Send background notification email for registration update
    update_registration_status_bkg(reg.id)

    return reg


def save_registration_standard(
    ctx: dict, event: Event, form: RegistrationForm, gifted: bool, provisional: bool, reg: Registration
) -> None:
    """Save standard registration with ticket and payment processing.

    Processes a standard registration by updating modification counter,
    handling additional participants, quotas, ticket selection, and
    custom payment amounts based on form data.

    Args:
        ctx: Context dictionary containing event and form data, including 'tot_payed'
        event: Event instance for validation and processing
        form: Registration form instance with cleaned_data
        gifted: Whether this is a gifted registration (skips modification counter)
        provisional: Whether registration is provisional (skips modification counter)
        reg: Registration instance to update with form data

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
        reg.modified = reg.modified + 1

    # Process additional participants count
    if "additionals" in form.cleaned_data:
        reg.additionals = int(form.cleaned_data["additionals"])

    # Handle quota assignments if present
    if "quotas" in form.cleaned_data and form.cleaned_data["quotas"]:
        reg.quotas = int(form.cleaned_data["quotas"])

    # Process ticket selection and validation
    if "ticket" in form.cleaned_data:
        try:
            sel = RegistrationTicket.objects.filter(pk=form.cleaned_data["ticket"]).select_related("event").first()
        except Exception as err:
            raise Http404("RegistrationTicket does not exists") from err

        # Validate ticket exists and belongs to correct event
        if sel and sel.event != event:
            raise Http404("RegistrationTicket wrong event")

        # Prevent downgrading ticket price for paid registrations
        if ctx["tot_payed"] and reg.ticket and reg.ticket.price > 0 and sel.price < reg.ticket.price:
            raise Http404("lower price")
        reg.ticket = sel

    # Set custom payment amount if specified
    if "pay_what" in form.cleaned_data and form.cleaned_data["pay_what"]:
        reg.pay_what = int(form.cleaned_data["pay_what"])


def registration_redirect(request: HttpRequest, reg: Registration, new_reg: bool, run: Run) -> HttpResponse:
    """Handle post-registration redirect logic.

    Determines the appropriate redirect destination after a user completes
    or updates their event registration. Checks membership requirements,
    payment status, and redirects accordingly.

    Args:
        request: Django HTTP request object containing user and association data
        reg: Registration instance for the current user's registration
        new_reg: Whether this is a new registration (True) or an update (False)
        run: Run instance representing the event run being registered for

    Returns:
        HttpResponse: Redirect response to the appropriate next step:
            - Profile page if membership compilation needed
            - Membership application if membership status requires it
            - Payment page if payment is outstanding
            - Event gallery if registration is complete

    Note:
        This function handles the post-registration workflow by checking
        feature flags and user status to determine the next required action.
    """
    # Check if membership feature is enabled and user needs to complete profile
    if "membership" in request.assoc["features"]:
        # Redirect to profile if membership data not compiled
        if not request.user.member.membership.compiled:
            mes = _("To confirm your registration, please fill in your personal profile") + "."
            messages.success(request, mes)
            return redirect("profile")

        # Check membership status for non-waiting registrations
        memb_status = request.user.member.membership.status
        if memb_status in [MembershipStatus.EMPTY, MembershipStatus.JOINED] and reg.ticket.tier != TicketTier.WAITING:
            mes = _("To confirm your registration, apply to become a member of the Association") + "."
            messages.success(request, mes)
            return redirect("membership")

    # Check if payment feature is enabled and payment is required
    if "payment" in request.assoc["features"]:
        # Redirect to payment page if registration has outstanding payment alert
        if reg.alert:
            mes = _("To confirm your registration, please pay the amount indicated") + "."
            messages.success(request, mes)
            return redirect("acc_reg", reg_id=reg.id)

    # All requirements satisfied - show success message and redirect to event gallery
    context = {"event": run}
    if new_reg:
        # Success message for new registration
        mes = _("Registration confirmed at %(event)s!") % context
    else:
        # Success message for registration update
        mes = _("Registration updated to %(event)s!") % context

    messages.success(request, mes)
    return redirect("gallery", s=reg.run.get_slug())


def save_registration_bring_friend(ctx: dict, form, reg: Registration, request) -> None:
    """Process bring-a-friend discount codes for registration.

    This function handles the bring-a-friend functionality by:
    1. Sending instructions email to the registrant
    2. Validating the provided friend code
    3. Creating accounting entries for both parties
    4. Applying discounts to both the registrant and their friend

    Args:
        ctx: Context dictionary containing bring friend configuration including:
            - bring_friend_discount_from: Discount amount for code user
            - bring_friend_discount_to: Discount amount for code owner
            - run: Event run instance
            - a_id: Association ID
        form: Registration form with bring_friend field containing the friend code
        reg: Registration instance for the current registrant
        request: Django HTTP request object containing user information

    Raises:
        Http404: When the provided friend code is not found in the database
    """
    # Send bring-a-friend instructions email to the new registrant
    bring_friend_instructions(reg, ctx)

    # Early return if no bring_friend field in form data
    if "bring_friend" not in form.cleaned_data:
        return
    logger.debug(f"Bring friend form data: {form.cleaned_data}")

    # Extract and validate the friend code from form
    cod = form.cleaned_data["bring_friend"]
    logger.debug(f"Processing bring friend code: {cod}")
    if not cod:
        return

    # Look up the registration associated with the friend code
    try:
        friend = Registration.objects.get(special_cod=cod)
    except Exception as err:
        raise Http404("I'm sorry, this friend code was not found") from err

    # Create accounting entries atomically for both parties
    with transaction.atomic():
        # Create discount token for the person using the friend code
        AccountingItemOther.objects.create(
            member=request.user.member,
            value=int(ctx["bring_friend_discount_from"]),
            run=ctx["run"],
            oth=OtherChoices.TOKEN,
            descr=_("You have use a friend code") + f" - {friend.member.display_member()} - {cod}",
            assoc_id=ctx["a_id"],
            ref_addit=reg.id,
        )

        # Create discount token for the friend whose code was used
        AccountingItemOther.objects.create(
            member=friend.member,
            value=int(ctx["bring_friend_discount_to"]),
            run=ctx["run"],
            oth=OtherChoices.TOKEN,
            descr=_("Your friend code has been used") + f" - {request.user.member.display_member()} - {cod}",
            assoc_id=ctx["a_id"],
            ref_addit=friend.id,
        )

        # Trigger accounting update for the friend's registration
        friend.save()


def register_info(request, ctx, form, reg, dis):
    """Display registration information and status.

    Args:
        request: HTTP request object
        ctx: Context dictionary to populate with registration data
        form: Registration form instance
        reg: Registration object if exists
        dis: Discount information

    Side effects:
        Updates ctx with form data, terms, conditions, and membership status
    """
    ctx["form"] = form
    ctx["lang"] = request.user.member.language
    ctx["discount_apply"] = dis
    ctx["custom_text"] = get_event_text(ctx["event"].id, EventTextType.REGISTER)
    ctx["event_terms_conditions"] = get_event_text(ctx["event"].id, EventTextType.TOC)
    ctx["assoc_terms_conditions"] = get_assoc_text(ctx["a_id"], AssocTextType.TOC)
    ctx["hide_unavailable"] = get_event_config(ctx["event"].id, "registration_hide_unavailable", False, ctx)
    ctx["no_provisional"] = get_event_config(ctx["event"].id, "payment_no_provisional", False, ctx)

    init_form_submitted(ctx, form, request, reg)

    if reg:
        reg.provisional = is_reg_provisional(reg)

    if ctx["run"].start and "membership" in ctx["features"]:
        que = AccountingItemMembership.objects.filter(year=ctx["run"].start.year, member=request.user.member)
        if que.count() > 0:
            ctx["membership_fee"] = "done"
        elif datetime.today().year != ctx["run"].start.year:
            ctx["membership_fee"] = "future"
        else:
            ctx["membership_fee"] = "todo"

        ctx["membership_amount"] = get_assoc_config(request.assoc["id"], "membership_fee", 0)


def init_form_submitted(ctx, form, request, reg=None):
    """Initialize form submission data in context.

    Args:
        ctx: Context dictionary to update
        form: Form object containing questions
        request: HTTP request object with POST data
        reg: Registration object (optional)
    """
    ctx["submitted"] = request.POST.dict()
    if hasattr(form, "questions"):
        for question in form.questions:
            if question.id in form.singles:
                ctx["submitted"]["q" + str(question.id)] = form.singles[question.id].option_id

    if reg:
        if reg.ticket_id:
            ctx["submitted"]["ticket"] = reg.ticket_id
        if reg.quotas:
            ctx["submitted"]["quotas"] = reg.quotas
        if reg.additionals:
            ctx["submitted"]["additionals"] = reg.additionals

    if "ticket" in ctx:
        ctx["submitted"]["ticket"] = ctx["ticket"]


@login_required
def register(request: HttpRequest, s: str, sc: str = "", dis: str = "", tk: int = 0) -> HttpResponse:
    """Handle event registration form display and submission.

    Manages the complete registration process including ticket selection,
    form validation, payment processing, and membership verification.

    Args:
        request: Django HTTP request object
        s: Event slug identifier
        sc: Optional scenario code for registration context
        dis: Optional discount code to apply
        tk: Ticket ID to pre-select (default: 0)

    Returns:
        HttpResponse: Rendered registration page or redirect response

    Raises:
        RewokedMembershipError: When user membership has been revoked
    """
    # Get event and run context with status validation
    ctx = get_event_run(request, s, include_status=True)
    run = ctx["run"]
    event = ctx["event"]

    # Set up registration context for the current run
    if hasattr(run, "reg"):
        ctx["run_reg"] = run.reg
    else:
        ctx["run_reg"] = None

    # Apply ticket selection if provided
    _apply_ticket(ctx, tk)

    # Check if payment features are enabled for this association
    ctx["payment_feature"] = "payment" in get_assoc_features(ctx["a_id"])

    # Prepare new registration or load existing one
    new_reg = _register_prepare(ctx, ctx["run_reg"])

    # Handle registration redirects for new registrations
    if new_reg:
        res = _check_redirect_registration(request, ctx, event, sc)
        if res:
            return res

    # Add any available bring-a-friend discounts
    _add_bring_friend_discounts(ctx)

    # Verify user membership status and permissions
    mb = get_user_membership(request.user.member, request.assoc["id"])
    if mb.status in [MembershipStatus.REWOKED]:
        raise RewokedMembershipError()
    ctx["member"] = request.user.member

    # Process form submission or display registration form
    if request.method == "POST":
        form = RegistrationForm(request.POST, ctx=ctx, instance=ctx["run_reg"])
        form.sel_ticket_map(request.POST.get("ticket", ""))
        # Validate form and save registration if valid
        if form.is_valid():
            reg = save_registration(request, ctx, form, run, event, ctx["run_reg"])
            return registration_redirect(request, reg, new_reg, run)
    else:
        # Display empty form for GET requests
        form = RegistrationForm(ctx=ctx, instance=ctx["run_reg"])

    # Prepare additional registration information and render page
    register_info(request, ctx, form, ctx["run_reg"], dis)
    return render(request, "larpmanager/event/register.html", ctx)


def _apply_ticket(ctx: dict, tk: int | None) -> None:
    """Apply ticket information to context if ticket exists.

    Args:
        ctx: Context dictionary to update with ticket data
        tk: Ticket ID to retrieve, or None
    """
    if not tk:
        return

    try:
        # Retrieve ticket and set tier in context
        tick = RegistrationTicket.objects.get(pk=tk)
        ctx["tier"] = tick.tier

        # Remove closed status for staff/NPC tickets
        if tick.tier in [TicketTier.STAFF, TicketTier.NPC] and "closed" in ctx["run"].status:
            del ctx["run"].status["closed"]

        # Store ticket ID in context
        ctx["ticket"] = tk
    except ObjectDoesNotExist:
        pass


def _check_redirect_registration(request, ctx: dict, event, secret_code: str | None) -> HttpResponse | None:
    """Check if registration should be redirected based on event status and settings.

    This function performs various checks to determine if a user's registration
    attempt should be redirected or blocked based on event configuration,
    timing, and access controls.

    Parameters
    ----------
    request : HttpRequest
        Django HTTP request object containing user and session data
    ctx : dict
        Context dictionary containing event, run data, features, and tier info
    event : Event
        Event model instance being registered for
    secret_code : str or None
        Optional secret code for registration access, None if not provided

    Returns
    -------
    HttpResponse or None
        HttpResponse object for redirect/error pages if registration should be
        blocked or redirected, None if registration can proceed normally

    Raises
    ------
    Http404
        If an invalid registration secret code is provided when secret
        registration is enabled
    """
    # Check if event registration is closed
    if "closed" in ctx["run"].status:
        return render(request, "larpmanager/event/closed.html", ctx)

    # Validate secret code if secret registration is enabled
    if "registration_secret" in ctx["features"] and secret_code:
        if ctx["run"].registration_secret != secret_code:
            raise Http404("wrong registration code")
        return None

    # Redirect to external registration link if configured
    # Skip redirect for staff and NPC tiers who register internally
    if "register_link" in ctx["features"] and event.register_link:
        if "tier" not in ctx or ctx["tier"] not in [TicketTier.STAFF, TicketTier.NPC]:
            return redirect(event.register_link)

    # Check registration timing and pre-registration options
    if "registration_open" in ctx["features"]:
        if not ctx["run"].registration_open or ctx["run"].registration_open > timezone_now():
            # Redirect to pre-registration if available and active
            if "pre_register" in ctx["features"] and get_event_config(event.id, "pre_register_active", False):
                return redirect("pre_register", s=ctx["event"].slug)
            else:
                return render(request, "larpmanager/event/not_open.html", ctx)

    return None


def _add_bring_friend_discounts(ctx: dict) -> None:
    """Add bring-a-friend discount configuration to context if feature is enabled."""
    if "bring_friend" not in ctx["features"]:
        return

    # Retrieve discount configuration for both directions (to/from)
    for config_name in ["bring_friend_discount_to", "bring_friend_discount_from"]:
        ctx[config_name] = get_event_config(ctx["event"].id, config_name, 0, ctx)


def _register_prepare(ctx, reg):
    """Prepare registration context with payment information and locks.

    Args:
        ctx: Context dictionary to update
        reg: Existing registration instance or None for new registration

    Returns:
        bool: True if this is a new registration, False if updating existing
    """
    new_reg = True
    ctx["tot_payed"] = 0
    if reg:
        ctx["tot_payed"] = reg.tot_payed
        new_reg = False

        # we lock changing values with lower prices if there is already a payment (done or submitted)
        pending = (
            PaymentInvoice.objects.filter(
                idx=reg.id,
                member_id=reg.member_id,
                status=PaymentStatus.SUBMITTED,
                typ=PaymentType.REGISTRATION,
            ).count()
            > 0
        )
        ctx["payment_lock"] = pending or reg.tot_payed > 0

    return new_reg


def register_reduced(request: HttpRequest, s: str) -> JsonResponse:
    """Return count of available reduced-price tickets for an event run."""
    ctx = get_event_run(request, s)
    # Count reduced tickets still available for this run
    ct = get_reduced_available_count(ctx["run"])
    return JsonResponse({"res": ct})


@login_required
def register_conditions(request: HttpRequest, s: str = None) -> HttpResponse:
    """Render registration conditions page with event and association terms.

    Args:
        request: HTTP request object
        s: Optional event slug for event-specific conditions

    Returns:
        Rendered HTML response with terms and conditions
    """
    # Initialize base user context
    ctx = def_user_ctx(request)

    # Add event-specific context if event slug provided
    if s:
        ctx["event"] = get_event(request, s)["event"]
        ctx["event_text"] = get_event_text(ctx["event"].id, EventTextType.TOC)

    # Add association terms and conditions
    ctx["assoc_text"] = get_assoc_text(request.assoc["id"], AssocTextType.TOC)

    return render(request, "larpmanager/event/register_conditions.html", ctx)


# ~ def discount_bring_friend(request, ctx, cod):
# ~ # check if there is a registration with that cod
# ~ try:
# ~ friend = Registration.objects.get(special_cod=cod)
# ~ except Exception as e:
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discount code not valid")})
# ~ if friend.member == request.user.member:
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('Nice Try! But no, I'm sorry.')})
# ~ # check same event
# ~ if friend.run.event != ctx['event']:
# ~ Return Jsonresonse ({'res': 'ko', 'msg': _ ('Code applicable only to run of the same event!')})
# ~ # check future run
# ~ if friend.run.end < datetime.now().date():
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('Code not valid for runs passed!')})
# ~ # get discount friend
# ~ disc = Discount.objects.get(typ=Discount.FRIEND, runs__in=[ctx['run']])
# ~ if disc.max_redeem > 0:
# ~ if AccountingItemDiscount.objects.filter(disc=disc, run=ctx['run']).count() > disc.max_redeem:
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('We are sorry, the maximum number of concessions has been reached a friend')})
# ~ # check if not already registered
# ~ try:
# ~ reg = Registration.objects.get(member=request.user.member, run=ctx['run'])
# ~ if disc.only_reg:
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discounts only applicable with new registrations")})
# ~ except Exception as e:
# ~ pass
# ~ # check there are no discount stores a friend
# ~ if AccountingItemDiscount.objects.filter(member=request.user.member, run=ctx['run'], disc__typ=Discount.STANDARD).count() > 0:
# ~ Return jsonrespone ({'really': 'ko', 'msg': _ ("Discount not combinable with other benefits") + "."})
# ~ # check the user TO don't already have the discount
# ~ try:
# ~ ac = AccountingItemDiscount.objects.get(disc=disc, member=request.user.member, run=ctx['run'])
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('You have already used a personal code')})
# ~ except Exception as e:
# ~ pass
# ~ if AccountingItemDiscount.objects.filter(member=request.user.member, run=ctx['run'], disc__typ=Discount.PLAYAGAIN).count() > 0:
# ~ Return Jsonresonse ({'res': 'Ko', 'msg': _ ('Discount not comulary with Play Again')})
# ~ # all green! proceed
# ~ now = datetime.now()
# ~ AccountingItemDiscount.objects.create(disc=disc, value=disc.value, member=request.user.member, expires=now + timedelta(minutes = 15), run=ctx['run'], detail=friend.id, assoc_id=ctx['a_id'])
# ~ Return Jsonresonse ({'res': 'ok', 'msg': _ ('The facility has been added! It was reserved for you for 15 minutes, after which it will be removed')})


@login_required
@require_POST
def discount(request: HttpRequest, s: str) -> JsonResponse:
    """Handle discount code application for user registration.

    This function validates and applies discount codes for event registrations,
    creating temporary discount reservations that expire after 15 minutes.

    Args:
        request: Django HTTP request object containing POST data with discount code
        s: Event slug identifier used to retrieve the event context

    Returns:
        JsonResponse: JSON response containing either success message with
                     reservation details or error message with validation failure

    Raises:
        ObjectDoesNotExist: When discount code is not found for the event run
    """

    def error(msg):
        return JsonResponse({"res": "ko", "msg": msg})

    # Get event context and validate discount feature availability
    ctx = get_event_run(request, s)

    if "discount" not in ctx["features"]:
        return error(_("Not available, kiddo"))

    # Extract and validate discount code from request
    cod = request.POST.get("cod")
    try:
        disc = Discount.objects.get(runs__in=[ctx["run"]], cod=cod)
    except ObjectDoesNotExist:
        logger.warning(f"Discount code not found: {cod}")
        logger.debug(traceback.format_exc())
        return error(_("Discount code not valid"))

    # Clean up expired discount reservations
    now = timezone_now()
    AccountingItemDiscount.objects.filter(expires__lte=now).delete()

    # Extract context variables for discount validation
    member = request.user.member
    run = ctx["run"]
    event = ctx["event"]

    # Validate discount eligibility and constraints
    check = _check_discount(disc, member, run, event)
    if check:
        return error(check)

    # Create temporary discount reservation with 15-minute expiration
    AccountingItemDiscount.objects.create(
        value=disc.value,
        member=member,
        expires=now + timedelta(minutes=15),
        disc=disc,
        run=run,
        assoc_id=ctx["a_id"],
    )

    # Return success response with reservation confirmation
    return JsonResponse(
        {
            "res": "ok",
            "msg": _(
                "The discount has been added! It has been reserved for you for 15 minutes, after which it will be removed"
            ),
        }
    )


def _check_discount(disc, member, run, event):
    """Validate if a discount can be applied to a member's registration.

    Args:
        disc: Discount object to validate
        member: Member attempting to use discount
        run: Event run instance
        event: Event instance

    Returns:
        str or None: Error message if invalid, None if valid
    """
    if _is_discount_invalid_for_registration(disc, member, run):
        return _("Discounts only applicable with new registrations")

    if _is_discount_already_used(disc, member, run):
        return _("Code already used")

    if _is_type_already_used(disc.typ, member, run):
        return _("Non-cumulative code")

    if disc.max_redeem > 0 and _is_discount_maxed(disc, run):
        return _("Sorry, this facilitation code has already been used the maximum number allowed")

    if not _validate_exclusive_logic(disc, member, run, event):
        return _("Discount not combinable with other benefits") + "."

    return None


def _is_discount_invalid_for_registration(disc: Discount, member: Member, run: Run) -> bool:
    """Check if discount is invalid due to existing registration.

    Returns True if discount is registration-only and member already registered.
    """
    # Discount not limited to registration-only
    if not disc.only_reg:
        return False

    # Check if member has active registration for this run
    return Registration.objects.filter(member=member, run=run, cancellation_date__isnull=True).exists()


def _is_discount_already_used(disc, member, run):
    return AccountingItemDiscount.objects.filter(disc=disc, member=member, run=run).exists()


def _is_type_already_used(disc_type, member, run):
    return AccountingItemDiscount.objects.filter(disc__typ=disc_type, member=member, run=run).exists()


def _is_discount_maxed(disc, run):
    count = AccountingItemDiscount.objects.filter(disc=disc, run=run).count()
    return count > disc.max_redeem


def _validate_exclusive_logic(disc: Discount, member: Member, run: Run, event: Event) -> bool:
    """
    Validate exclusive discount logic for member registrations.

    Ensures that PLAYAGAIN discounts are mutually exclusive with other discounts
    and validates eligibility requirements.

    Args:
        disc: The discount to validate
        member: The member applying for the discount
        run: The specific run for this registration
        event: The event containing multiple runs

    Returns:
        True if the discount can be applied, False otherwise
    """
    # For PLAYAGAIN discount: no other discounts and has another registration
    if disc.typ == Discount.PLAYAGAIN:
        # Check if member already has any discount for this run
        if AccountingItemDiscount.objects.filter(member=member, run=run).exists():
            return False

        # Verify member has registration in another run of the same event
        if not Registration.objects.filter(member=member, run__event=event).exclude(run=run).exists():
            return False

    # If PLAYAGAIN discount was already applied, no other allowed
    elif AccountingItemDiscount.objects.filter(member=member, run=run, disc__typ=Discount.PLAYAGAIN).exists():
        return False

    return True


@login_required
def discount_list(request: HttpRequest, s: str) -> JsonResponse:
    """Get list of valid discount items for the current user and event run.

    This function retrieves all non-expired discount items for the authenticated user
    within the specified event run context. Expired items are automatically cleaned up.

    Args:
        request: The HTTP request object containing user authentication
        s: String identifier for the event run

    Returns:
        JsonResponse containing a list of discount items with name, value, and expiration
    """
    # Get the event run context from the request and identifier
    ctx = get_event_run(request, s)
    now = timezone_now()

    # Bulk delete expired discount items for this user and run
    AccountingItemDiscount.objects.filter(member=request.user.member, run=ctx["run"], expires__lte=now).delete()

    # Get remaining valid discount items with optimized query
    # Filter for current user/run and non-expired items
    discount_items = (
        AccountingItemDiscount.objects.filter(member=request.user.member, run=ctx["run"])
        .select_related("disc")
        .filter(models.Q(expires__isnull=True) | models.Q(expires__gt=now))
    )

    # Build response list efficiently
    # Convert discount items to JSON-serializable format
    lst = []
    for aid in discount_items:
        j = {"name": aid.disc.name, "value": aid.value}
        # Format expiration time or set empty string for permanent discounts
        if aid.expires:
            j["expires"] = aid.expires.strftime("%H:%M")
        else:
            j["expires"] = ""
        lst.append(j)

    return JsonResponse({"lst": lst})


@login_required
def unregister(request, s):
    """Handle user self-unregistration from an event.

    Args:
        request: HTTP request object from authenticated user
        s: Event slug string

    Returns:
        HttpResponse: Confirmation form or redirect to accounting page after cancellation
    """
    ctx = get_event_run(request, s, signup=True, include_status=True)

    # check if user is actually registered
    try:
        reg = Registration.objects.get(run=ctx["run"], member=request.user.member, cancellation_date__isnull=True)
    except ObjectDoesNotExist as err:
        raise Http404("Registration does not exist") from err

    if request.method == "POST":
        cancel_reg(reg)
        mes = _("You have correctly cancelled the registration to the %(event)s event") % {"event": ctx["event"]}
        messages.success(request, mes)
        return redirect("accounting")

    ctx["reg"] = reg
    ctx["event_terms_conditions"] = get_event_text(ctx["event"].id, EventTextType.TOC)
    ctx["assoc_terms_conditions"] = get_assoc_text(ctx["a_id"], AssocTextType.TOC)
    return render(request, "larpmanager/event/unregister.html", ctx)


@login_required
def gift(request: HttpRequest, s: str) -> HttpResponse:
    """Display gift registrations and their payment status for the current user.

    This view shows all gift registrations (registrations with redeem codes) for the
    current user in a specific event run, along with their payment status and accounting
    information.

    Args:
        request: The HTTP request object containing user and session data
        s: The event slug string used to identify the specific event

    Returns:
        HttpResponse: Rendered gift.html template containing the registration list
        and payment information context

    Raises:
        Http404: If the event or run is not found
        PermissionDenied: If registration is not open or user lacks permissions
    """
    # Get event context and verify registration access
    ctx = get_event_run(request, s, signup=False, feature_slug="gift", include_status=True)
    check_registration_open(ctx, request)

    # Filter registrations for current user with redeem codes (gift registrations)
    ctx["list"] = Registration.objects.filter(
        run=ctx["run"], member=request.user.member, redeem_code__isnull=False, cancellation_date__isnull=True
    )

    # Load accounting information (payments, pending transactions, etc.)
    info_accounting(request, ctx)

    # Attach payment and accounting info to each registration
    for reg in ctx["list"]:
        # Check for pending payments
        for el in ctx["payments_todo"]:
            if reg.id == el.id:
                reg.payment = el

        # Check for pending transactions
        for el in ctx["payments_pending"]:
            if reg.id == el.id:
                reg.pending = el

        # Attach additional registration info
        for el in ctx["reg_list"]:
            if reg.id == el.id:
                reg.info = el

    return render(request, "larpmanager/event/gift.html", ctx)


def check_registration_open(ctx, request):
    if not ctx["run"].status["open"]:
        messages.warning(request, _("Registrations not open!"))
        raise RedirectError("home")


@login_required
def gift_edit(request: HttpRequest, s: str, r: int) -> HttpResponse:
    """Handle gift registration modifications.

    This function manages the editing of gift registrations, allowing users to
    modify gift card details or cancel them entirely. It validates permissions,
    handles form processing, and manages the gift registration lifecycle.

    Args:
        request: The HTTP request object containing user data and form submission
        s: The event slug identifier used to locate the specific event
        r: The registration ID for the gift card being edited

    Returns:
        HttpResponse: Either renders the gift edit form template or redirects
        to the gift list page after successful save/cancel operations

    Raises:
        Http404: If the event, run, or registration cannot be found
        PermissionDenied: If user lacks permission to edit gift registrations
    """
    # Get event context and verify user has gift management permissions
    ctx = get_event_run(request, s, signup=False, feature_slug="gift", include_status=True)
    check_registration_open(ctx, request)

    # Retrieve the specific gift registration and prepare form context
    reg = get_registration_gift(ctx, r, request)
    _register_prepare(ctx, reg)

    # Handle POST requests for form submission (save or delete operations)
    if request.method == "POST":
        form = RegistrationGiftForm(request.POST, ctx=ctx, instance=reg)

        # Validate form data before processing
        if form.is_valid():
            # Check if this is a deletion request
            if "delete" in request.POST and request.POST["delete"] == "1":
                cancel_reg(reg)
                messages.success(request, _("Gift card cancelled!"))
            else:
                # Save the updated registration data
                save_registration(request, ctx, form, ctx["run"], ctx["event"], reg, gifted=True)
                messages.success(request, _("Operation completed") + "!")

            # Redirect back to gift list after successful operation
            return redirect("gift", s=s)
    else:
        # Handle GET requests by creating a new form with existing data
        form = RegistrationGiftForm(ctx=ctx, instance=reg)

    # Prepare context for template rendering
    ctx["form"] = form
    ctx["gift"] = True

    # Initialize form submission state and validation
    init_form_submitted(ctx, form, request, reg)

    return render(request, "larpmanager/event/gift_edit.html", ctx)


def get_registration_gift(ctx: dict, r: int | None, request) -> Registration | None:
    """Get a registration with gift redeem code for the current user.

    Args:
        ctx: Context dictionary containing run information
        r: Registration primary key to lookup
        request: HTTP request object with authenticated user

    Returns:
        Registration object if found and valid, None otherwise

    Raises:
        Http404: If registration lookup fails or invalid parameters provided
    """
    reg = None

    # Early return if no registration ID provided
    if r:
        try:
            # Query for valid gift registration matching all criteria
            reg = Registration.objects.get(
                pk=r,
                run=ctx["run"],
                member=request.user.member,
                redeem_code__isnull=False,  # Must have a redeem code (gift)
                cancellation_date__isnull=True,  # Must not be cancelled
            )
        except Exception as err:
            # Convert any lookup error to 404 for security
            raise Http404("what are you trying to do?") from err

    return reg


@login_required
def gift_redeem(request: HttpRequest, s: str, code: str) -> HttpResponse:
    """
    Handle gift code redemption for event registrations.

    Processes the redemption of a gift code for event registrations. If the user
    is already registered for the event, they are redirected with a success message.
    Otherwise, the function handles both GET (display form) and POST (process redemption)
    requests for gift code redemption.

    Args:
        request (HttpRequest): The HTTP request object containing user and method info
        s (str): Event slug identifier for the specific event
        code (str): Gift redemption code to be validated and processed

    Returns:
        HttpResponse: Either renders the redemption form template for GET requests
                     or redirects to the gallery page after successful redemption

    Raises:
        Http404: When no valid registration is found matching the provided code
                and association constraints
    """
    # Get event context and validate user permissions for gift redemption
    ctx = get_event_run(request, s, signup=False, feature_slug="gift", include_status=True)

    # Check if user is already registered for this event
    if ctx["run"].reg:
        messages.success(request, _("You cannot redeem a membership, you are already a member!"))
        return redirect("gallery", s=ctx["run"].get_slug())

    # Attempt to find valid registration with the provided redemption code
    try:
        reg = Registration.objects.get(
            redeem_code=code,
            cancellation_date__isnull=True,
            run__event__assoc_id=ctx["a_id"],
        )
    except Exception as err:
        raise Http404("registration not found") from err

    # Process POST request - complete the gift redemption
    if request.method == "POST":
        # Use atomic transaction to ensure data consistency during redemption
        with transaction.atomic():
            reg.member = request.user.member
            reg.redeem_code = None
            reg.save()

        # Notify user of successful redemption and redirect to event gallery
        messages.success(request, _("Your gifted registration has been redeemed!"))
        return redirect("gallery", s=ctx["run"].get_slug())

    # Add registration object to context for template rendering
    ctx["reg"] = reg

    return render(request, "larpmanager/event/gift_redeem.html", ctx)
