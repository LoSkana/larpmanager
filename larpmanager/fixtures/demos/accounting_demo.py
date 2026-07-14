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
"""Template association showcasing ticketing flexibility and the full money lifecycle.

Tiered tickets (patron/standard/waiting/new player), a sectioned registration
form with priced options, a discount code, pay-what-you-want donations,
installment schedules, and organizer-side expenses/outflows/inflows so the
event accounting overview is fully populated.
"""

from __future__ import annotations

import datetime
from datetime import UTC
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone

from larpmanager.models.accounting import (
    AccountingItemDiscount,
    AccountingItemExpense,
    AccountingItemInflow,
    AccountingItemOutflow,
    AccountingItemPayment,
    BalanceChoices,
    Discount,
    DiscountType,
    ExpenseChoices,
    PaymentChoices,
)
from larpmanager.models.association import Association
from larpmanager.models.base import Feature
from larpmanager.models.event import Event, EventConfig
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionStatus,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    RegistrationSection,
)
from larpmanager.models.larpmanager import LarpManagerDemoHint, LarpManagerDemoType
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import Registration, RegistrationInstallment, RegistrationTicket, TicketTier

ASSOCIATION_SLUG = "demo-accounting"
EVENT_SLUG = "midwinter-fair"
DEMO_TYPE_SLUG = "accounting"


def _days_ago(days: int) -> datetime.datetime:
    return timezone.now() - datetime.timedelta(days=days)


def _enable_event_features(event: Event, slugs: list[str]) -> None:
    for slug in slugs:
        event.features.add(Feature.objects.get(slug=slug))


def _enable_assoc_features(association: Association, slugs: list[str]) -> None:
    for slug in slugs:
        association.features.add(Feature.objects.get(slug=slug))


def _make_member(username: str, name: str, surname: str, association: Association) -> Any:
    user, _created = User.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@demo.it"},
    )
    member = user.member
    member.name = name
    member.surname = surname
    member.save()
    Membership.objects.get_or_create(
        member=member,
        association=association,
        defaults={"status": MembershipStatus.JOINED},
    )
    return member


def _build_tickets(event: Event) -> dict[str, RegistrationTicket]:
    # Event creation already auto-created a default Standard ticket; reuse and configure it.
    standard = event.tickets.get(tier=TicketTier.STANDARD)
    standard.name = "Standard"
    standard.price = 60
    standard.max_available = 6
    standard.save()

    return {
        "patron": RegistrationTicket.objects.create(
            event=event, number=2, tier=TicketTier.PATRON, name="Patron", price=120, max_available=0
        ),
        "standard": standard,
        "new_player": RegistrationTicket.objects.create(
            event=event, number=3, tier=TicketTier.NEW_PLAYER, name="New player", price=40, max_available=3
        ),
        "waiting": RegistrationTicket.objects.create(
            event=event, number=4, tier=TicketTier.WAITING, name="Waiting list", price=00, max_available=0
        ),
    }


def _build_form(event: Event, tickets: dict[str, RegistrationTicket]) -> dict[str, Any]:
    logistics = RegistrationSection.objects.create(event=event, name="Logistics", order=1)
    food = RegistrationSection.objects.create(event=event, name="Food", order=2)
    gameplay = RegistrationSection.objects.create(event=event, name="Gameplay", order=3)

    transport = RegistrationQuestion.objects.create(
        event=event,
        section=logistics,
        name="Arrival transport",
        typ=BaseQuestionType.SINGLE,
        status=QuestionStatus.MANDATORY,
    )
    transport_car = RegistrationOption.objects.create(event=event, question=transport, name="Own car", price=0)
    transport_shuttle = RegistrationOption.objects.create(event=event, question=transport, name="Shuttle bus", price=10)

    sleeping = RegistrationQuestion.objects.create(
        event=event,
        section=logistics,
        name="Sleeping arrangement",
        typ=BaseQuestionType.SINGLE,
        status=QuestionStatus.MANDATORY,
    )
    sleeping_own_tent = RegistrationOption.objects.create(event=event, question=sleeping, name="Own tent", price=0)
    sleeping_rental_tent = RegistrationOption.objects.create(
        event=event, question=sleeping, name="Rental tent", price=15
    )
    sleeping_cabin = RegistrationOption.objects.create(event=event, question=sleeping, name="Cabin bed", price=25)

    diet = RegistrationQuestion.objects.create(
        event=event,
        section=food,
        name="Dietary requirements",
        typ=BaseQuestionType.MULTIPLE,
        status=QuestionStatus.OPTIONAL,
    )
    diet_veggie = RegistrationOption.objects.create(event=event, question=diet, name="Vegetarian", price=0)
    diet_gluten_free = RegistrationOption.objects.create(event=event, question=diet, name="Gluten free", price=0)
    diet_snack_pack = RegistrationOption.objects.create(event=event, question=diet, name="Extra snack pack", price=8)

    RegistrationQuestion.objects.create(
        event=event,
        section=food,
        name="Allergies notes",
        typ=BaseQuestionType.PARAGRAPH,
        status=QuestionStatus.OPTIONAL,
    )

    weapon_kit = RegistrationQuestion.objects.create(
        event=event,
        section=gameplay,
        name="Weapon kit",
        typ=BaseQuestionType.SINGLE,
        status=QuestionStatus.OPTIONAL,
    )
    weapon_own = RegistrationOption.objects.create(event=event, question=weapon_kit, name="Bring own", price=0)
    weapon_basic = RegistrationOption.objects.create(event=event, question=weapon_kit, name="Rent basic kit", price=12)
    weapon_deluxe = RegistrationOption.objects.create(
        event=event, question=weapon_kit, name="Rent deluxe kit", price=20
    )

    experience = RegistrationQuestion.objects.create(
        event=event,
        section=gameplay,
        name="Experience level",
        typ=BaseQuestionType.SINGLE,
        status=QuestionStatus.MANDATORY,
    )
    experience_first = RegistrationOption.objects.create(event=event, question=experience, name="First timer")
    experience_veteran = RegistrationOption.objects.create(event=event, question=experience, name="Veteran")
    experience_expert = RegistrationOption.objects.create(event=event, question=experience, name="Very experienced")

    # Ticket-gated questions: only shown to participants holding the matching ticket.
    vip_dinner = RegistrationQuestion.objects.create(
        event=event,
        section=gameplay,
        name="VIP dinner with the cast",
        typ=BaseQuestionType.SINGLE,
        status=QuestionStatus.OPTIONAL,
    )
    vip_dinner.tickets.set([tickets["patron"]])
    vip_dinner_attend = RegistrationOption.objects.create(event=event, question=vip_dinner, name="Attend", price=25)
    vip_dinner_skip = RegistrationOption.objects.create(event=event, question=vip_dinner, name="Skip", price=0)

    orientation = RegistrationQuestion.objects.create(
        event=event,
        section=logistics,
        name="First-timer orientation",
        typ=BaseQuestionType.SINGLE,
        status=QuestionStatus.OPTIONAL,
    )
    orientation.tickets.set([tickets["new_player"]])
    orientation_join = RegistrationOption.objects.create(
        event=event, question=orientation, name="Join session", price=0
    )
    orientation_skip = RegistrationOption.objects.create(
        event=event, question=orientation, name="Already know the ropes", price=0
    )

    return {
        "transport": transport,
        "transport_car": transport_car,
        "transport_shuttle": transport_shuttle,
        "sleeping": sleeping,
        "sleeping_own_tent": sleeping_own_tent,
        "sleeping_rental_tent": sleeping_rental_tent,
        "sleeping_cabin": sleeping_cabin,
        "diet": diet,
        "diet_veggie": diet_veggie,
        "diet_gluten_free": diet_gluten_free,
        "diet_snack_pack": diet_snack_pack,
        "weapon_kit": weapon_kit,
        "weapon_own": weapon_own,
        "weapon_basic": weapon_basic,
        "weapon_deluxe": weapon_deluxe,
        "experience": experience,
        "experience_first": experience_first,
        "experience_veteran": experience_veteran,
        "experience_expert": experience_expert,
        "vip_dinner": vip_dinner,
        "vip_dinner_attend": vip_dinner_attend,
        "vip_dinner_skip": vip_dinner_skip,
        "orientation": orientation,
        "orientation_join": orientation_join,
        "orientation_skip": orientation_skip,
    }


def _create_discount(event: Event, run: Any) -> Discount:
    discount = Discount.objects.create(
        event=event,
        number=1,
        name="Early bird friend code",
        typ=DiscountType.STANDARD,
        value=15,
        max_redeem=5,
        visible=True,
    )
    discount.runs.set([run])
    return discount


def _build_installments(event: Event, tickets: dict[str, RegistrationTicket]) -> None:
    applicable = [tickets["standard"], tickets["new_player"], tickets["waiting"]]
    today = datetime.datetime.now(tz=UTC).date()

    deposit = RegistrationInstallment.objects.create(
        event=event, number=1, amount=30, date_deadline=today - datetime.timedelta(days=25)
    )
    deposit.tickets.set(applicable)

    balance = RegistrationInstallment.objects.create(
        event=event, number=2, amount=0, date_deadline=today - datetime.timedelta(days=5)
    )
    balance.tickets.set(applicable)


def _make_registration(
    run: Any,
    ticket: RegistrationTicket,
    member: Any,
    choices: list[Any],
    *,
    pay_what: int = 0,
    paid: int = 0,
    reg_days_ago: int = 0,
    paid_days_ago: int | None = None,
) -> Registration:
    registration = Registration.objects.create(run=run, member=member, ticket=ticket, pay_what=pay_what)
    for option in choices:
        RegistrationChoice.objects.create(registration=registration, question=option.question, option=option)
    # Persist now so tot_iscr is recomputed including the choices above (post_save signal).
    registration.save()
    if paid:
        payment = AccountingItemPayment.objects.create(
            member=member,
            association=run.event.association,
            registration=registration,
            value=paid,
            pay=PaymentChoices.MONEY,
        )
        # The payment's post_save signal re-saves the registration, recomputing tot_payed/quota/deadline.
        if paid_days_ago is None:
            paid_days_ago = reg_days_ago
        # Backdate via queryset update: bypasses save() so no further signal-triggered recompute fires.
        AccountingItemPayment.objects.filter(pk=payment.pk).update(created=_days_ago(paid_days_ago))
    else:
        registration.save()
    if reg_days_ago:
        Registration.objects.filter(pk=registration.pk).update(created=_days_ago(reg_days_ago))
    registration.refresh_from_db()
    return registration


def _build_registrations(event: Event, association: Association, form: dict[str, Any], discount: Discount) -> None:
    run = event.runs.first()
    standard = event.tickets.get(tier=TicketTier.STANDARD)
    patron = event.tickets.get(tier=TicketTier.PATRON)
    new_player = event.tickets.get(tier=TicketTier.NEW_PLAYER)
    waiting = event.tickets.get(tier=TicketTier.WAITING)

    alice = _make_member("demo-acct-alice", "Alice", "Stone", association)
    _make_registration(
        run,
        patron,
        alice,
        [
            form["transport_car"],
            form["sleeping_cabin"],
            form["diet_veggie"],
            form["weapon_deluxe"],
            form["experience_veteran"],
            form["vip_dinner_attend"],
        ],
        paid=190,
        reg_days_ago=55,
    )

    ben = _make_member("demo-acct-ben", "Ben", "Voss", association)
    AccountingItemDiscount.objects.create(
        member=ben, association=association, run=run, disc=discount, value=discount.value
    )
    _make_registration(
        run,
        standard,
        ben,
        [form["transport_car"], form["sleeping_own_tent"], form["weapon_own"], form["experience_first"]],
        paid=45,
        reg_days_ago=40,
        paid_days_ago=26,
    )

    clara = _make_member("demo-acct-clara", "Clara", "Wynn", association)
    AccountingItemDiscount.objects.create(
        member=clara, association=association, run=run, disc=discount, value=discount.value
    )
    _make_registration(
        run,
        standard,
        clara,
        [
            form["transport_shuttle"],
            form["sleeping_rental_tent"],
            form["diet_gluten_free"],
            form["weapon_basic"],
            form["experience_veteran"],
        ],
        paid=82,
        reg_days_ago=30,
    )

    dario = _make_member("demo-acct-dario", "Dario", "Kell", association)
    _make_registration(
        run,
        standard,
        dario,
        [form["transport_car"], form["sleeping_own_tent"], form["weapon_own"], form["experience_first"]],
        paid=30,
        reg_days_ago=20,
    )

    eva = _make_member("demo-acct-eva", "Eva", "Marsh", association)
    _make_registration(
        run,
        standard,
        eva,
        [
            form["transport_car"],
            form["sleeping_own_tent"],
            form["diet_snack_pack"],
            form["weapon_own"],
            form["experience_veteran"],
        ],
        paid=0,
        reg_days_ago=3,
    )

    finn = _make_member("demo-acct-finn", "Finn", "Osei", association)
    _make_registration(
        run,
        standard,
        finn,
        [
            form["transport_shuttle"],
            form["sleeping_cabin"],
            form["diet_snack_pack"],
            form["weapon_deluxe"],
            form["experience_expert"],
        ],
        paid=123,
        reg_days_ago=45,
        paid_days_ago=35,
    )

    grace = _make_member("demo-acct-grace", "Grace", "Lund", association)
    _make_registration(
        run,
        standard,
        grace,
        [
            form["transport_car"],
            form["sleeping_rental_tent"],
            form["diet_veggie"],
            form["weapon_own"],
            form["experience_first"],
        ],
        pay_what=20,
        paid=95,
        reg_days_ago=35,
        paid_days_ago=6,
    )

    # Standard tier is now sold out (6 of 6): the next signup lands on the waiting list.
    henry = _make_member("demo-acct-henry", "Henry", "Cole", association)
    _make_registration(
        run,
        waiting,
        henry,
        [form["transport_car"], form["sleeping_own_tent"], form["weapon_own"], form["experience_first"]],
        pay_what=10,
        paid=0,
        reg_days_ago=2,
    )

    isla = _make_member("demo-acct-isla", "Isla", "Novak", association)
    AccountingItemDiscount.objects.create(
        member=isla, association=association, run=run, disc=discount, value=discount.value
    )
    _make_registration(
        run,
        new_player,
        isla,
        [
            form["transport_car"],
            form["sleeping_own_tent"],
            form["diet_veggie"],
            form["weapon_own"],
            form["experience_first"],
            form["orientation_join"],
        ],
        paid=25,
        reg_days_ago=15,
    )

    jules = _make_member("demo-acct-jules", "Jules", "Farrow", association)
    _make_registration(
        run,
        new_player,
        jules,
        [
            form["transport_shuttle"],
            form["sleeping_rental_tent"],
            form["weapon_basic"],
            form["experience_first"],
            form["orientation_skip"],
        ],
        paid=30,
        reg_days_ago=10,
    )


def _build_staff_accounting(event: Event, association: Association) -> None:
    run = event.runs.first()

    quinn = _make_member("demo-acct-quinn", "Quinn", "Ashby", association)
    rosa = _make_member("demo-acct-rosa", "Rosa", "Pell", association)

    AccountingItemExpense.objects.create(
        member=quinn,
        association=association,
        run=run,
        descr="Kitchen supplies",
        value=85,
        exp=ExpenseChoices.KITCH,
        balance=BalanceChoices.MATER,
        is_approved=False,
    )
    AccountingItemExpense.objects.create(
        member=rosa,
        association=association,
        run=run,
        descr="Prop rental late fee",
        value=40,
        exp=ExpenseChoices.PROP,
        balance=BalanceChoices.SERV,
        is_approved=False,
    )
    AccountingItemExpense.objects.create(
        member=quinn,
        association=association,
        run=run,
        descr="Transportation fuel",
        value=55,
        exp=ExpenseChoices.TRANS,
        balance=BalanceChoices.DIVER,
        is_approved=True,
    )

    today = datetime.datetime.now(tz=UTC).date()
    AccountingItemOutflow.objects.create(
        association=association,
        run=run,
        descr="Venue deposit",
        value=300,
        exp=ExpenseChoices.LOCAT,
        balance=BalanceChoices.SERV,
        payment_date=today,
    )
    AccountingItemOutflow.objects.create(
        association=association,
        run=run,
        descr="Event insurance",
        value=60,
        exp=ExpenseChoices.OTHER,
        balance=BalanceChoices.DIVER,
        payment_date=today,
    )

    AccountingItemInflow.objects.create(
        association=association,
        run=run,
        descr="Local council sponsorship",
        value=200,
        payment_date=today,
    )
    AccountingItemInflow.objects.create(
        association=association,
        run=run,
        descr="Merchandise table revenue",
        value=45,
        payment_date=today,
    )


def _build_demo_type_and_hints(association: Association) -> LarpManagerDemoType:
    demo_type = LarpManagerDemoType.objects.create(
        name="Ticketing & Accounting",
        slug=DEMO_TYPE_SLUG,
        descr=(
            "Tiered ticketing, a sectioned registration form with priced options, discounts, "
            "pay-what-you-want, installments, and the full organizer money lifecycle."
        ),
        template_association=association,
        allowed_sidebar=(
            "orga_registrations,orga_registration_tickets,orga_registration_form,"
            "orga_discounts,orga_accounting,orga_expenses"
        ),
    )

    hints = [
        (
            "accounting-demo-event",
            "event",
            "Welcome to the Midwinter Fair",
            "<p>Start by exploring the event page and its ticket tiers.</p>",
        ),
        (
            "accounting-demo-register",
            "register",
            "Register and fill in the form",
            (
                "<p>Pick a ticket - notice the Standard tier is nearly sold out, so a late signup "
                "lands on the waiting list. Then fill the sectioned form: Logistics, Food and "
                "Gameplay each have questions, and some choices add extra cost to your total. "
                "A few questions only appear for certain ticket tiers, like the VIP dinner for "
                "Patrons or the orientation session for new players.</p>"
            ),
        ),
        (
            "accounting-demo-orga-registrations",
            "orga_registrations",
            "See every registration",
            (
                "<p>As organizer, this list shows all signups side by side: some fully paid, "
                "some mid-installment, some overdue.</p>"
            ),
        ),
        (
            "accounting-demo-orga-tickets",
            "orga_registration_tickets",
            "Check ticket availability",
            "<p>See how close each tier is to its cap, and how the waiting list kicks in.</p>",
        ),
        (
            "accounting-demo-orga-discounts",
            "orga_discounts",
            "Discount codes",
            "<p>One discount code is active here, already redeemed by a few participants.</p>",
        ),
        (
            "accounting-demo-orga-accounting",
            "orga_accounting",
            "Event accounting overview",
            (
                "<p>Installment deadlines, outstanding balances, staff expenses, outflows and "
                "inflows all come together here.</p>"
            ),
        ),
        (
            "accounting-demo-orga-expenses",
            "orga_expenses",
            "Approve staff expenses",
            "<p>Some expenses submitted by staff are still waiting for your approval.</p>",
        ),
    ]
    for key, view_name, title, content in hints:
        LarpManagerDemoHint.objects.get_or_create(
            key=key,
            defaults={"demo_type": demo_type, "view_name": view_name, "title": title, "content": content},
        )

    return demo_type


def build_accounting_demo() -> LarpManagerDemoType:
    """Create (or fetch) the template association/event for the ticketing & accounting demo."""
    existing = LarpManagerDemoType.objects.filter(slug=DEMO_TYPE_SLUG).first()
    if existing:
        return existing

    association = Association.objects.create(slug=ASSOCIATION_SLUG, name="Accounting Demo")
    event = Event.objects.create(association=association, name="Midwinter Fair", slug=EVENT_SLUG)
    run = event.runs.first()
    run.start = datetime.datetime.now(tz=UTC).date() + datetime.timedelta(days=60)
    run.end = run.start + datetime.timedelta(days=2)
    run.save()

    _enable_event_features(
        event, ["waiting", "new_player", "reg_que_sections", "discount", "pay_what_you_want", "reg_installments"]
    )
    _enable_assoc_features(association, ["payment", "expense", "outflow", "inflow"])

    EventConfig.objects.create(event=event, name="payment_alert", value="30")

    tickets = _build_tickets(event)
    form = _build_form(event, tickets)
    discount = _create_discount(event, run)
    _build_installments(event, tickets)
    _build_registrations(event, association, form, discount)
    _build_staff_accounting(event, association)

    return _build_demo_type_and_hints(association)
