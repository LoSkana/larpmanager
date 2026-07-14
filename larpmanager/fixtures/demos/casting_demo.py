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
"""Template association showcasing the Casting feature.

Pre-written characters, factions, seeded preference lists with deliberate
conflicts, and organizer-side casting assignment.
"""

from __future__ import annotations

import datetime
from datetime import UTC
from typing import Any

from django.contrib.auth.models import User

from larpmanager.models.association import Association
from larpmanager.models.base import Feature
from larpmanager.models.casting import Casting, CastingAvoid
from larpmanager.models.event import Event, EventConfig
from larpmanager.models.larpmanager import LarpManagerDemoHint, LarpManagerDemoType
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import Registration, TicketTier
from larpmanager.models.writing import Character, Faction

ASSOCIATION_SLUG = "demo-casting"
EVENT_SLUG = "regency-ball"
DEMO_TYPE_SLUG = "casting"


def _enable_features(event: Event, slugs: list[str]) -> None:
    for slug in slugs:
        event.features.add(Feature.objects.get(slug=slug))


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


def _build_characters(event: Event) -> dict[str, Character]:
    roster = [
        (
            "duke",
            "The Duke of Ashworth",
            "<p>Wealthiest bachelor of the season, guarding a scandal of his own.</p>",
            "<p>Your late father gambled away half the estate before he died. You have "
            "quietly rebuilt the fortune through shipping investments, but if the ton "
            "learns the Ashworth name was ever in debt, no family will let you near "
            "their daughters.</p>",
        ),
        (
            "dowager",
            "The Dowager Countess",
            "<p>Matriarch who decides whose reputation lives or dies this season.</p>",
            "<p>You know Lord Bramwell owes the Duke a debt of honor, and you intend "
            "to use that knowledge to force a match between his family and yours "
            "before the season ends.</p>",
        ),
        (
            "heiress",
            "Miss Eleanor Faircliffe",
            "<p>An heiress determined to marry for love, not fortune.</p>",
            "<p>You have fallen for Captain Osei despite your guardians pushing you "
            "toward the Duke. You are prepared to elope if no one will bless the "
            "match.</p>",
        ),
        (
            "rake",
            "Lord Bramwell",
            "<p>A notorious rake with a secret debt to the Duke.</p>",
            "<p>You owe the Duke of Ashworth a sum you cannot repay. You have been "
            "courting Miss Whitmore's favor not from affection but because her "
            "dowry would clear the debt.</p>",
        ),
        (
            "chaperone",
            "Mrs. Hartley",
            "<p>A chaperone who trades secrets as freely as she trades gossip.</p>",
            "<p>You sell what you overhear belowstairs and in the ballroom alike. "
            "Mr. Reed is your best source, and you pay him in coin he thinks is "
            "generous and you know is a pittance.</p>",
        ),
        (
            "captain",
            "Captain Osei",
            "<p>A war hero of new money, eager to be accepted by the old families.</p>",
            "<p>Your fortune was earned, not inherited, and the old families never "
            "let you forget it. You love Miss Faircliffe and mean to prove yourself "
            "worthy of her regardless of what the Ashworth Set thinks.</p>",
        ),
        (
            "debutante",
            "Miss Clara Whitmore",
            "<p>A debutante hiding a talent for forgery behind her fan.</p>",
            "<p>You have been forging letters of introduction for a fee, and Lord "
            "Bramwell has guessed as much. If he exposes you, your season is over "
            "before it begins.</p>",
        ),
        (
            "vicar",
            "The Reverend Mr. Pryce",
            "<p>A vicar who hears every confession this season and keeps none private.</p>",
            "<p>You have heard the Dowager Countess confess her scheme against Lord "
            "Bramwell's family, and you are deciding whether silence or disclosure "
            "serves you better.</p>",
        ),
        (
            "widow",
            "Lady Seraphina Vance",
            "<p>A young widow whose late husband's fortune is being contested.</p>",
            "<p>Your husband's will is being challenged by his brother. Mr. Reed, "
            "who served the household for years, holds evidence that could settle "
            "the matter in your favor, if he chooses to give it.</p>",
        ),
        (
            "valet",
            "Mr. Thomas Reed",
            "<p>A gentleman's valet who knows every secret belowstairs.</p>",
            "<p>You hold papers that would resolve Lady Vance's inheritance dispute "
            "in her favor. You have not decided whether loyalty or profit will "
            "guide you when Mrs. Hartley comes asking.</p>",
        ),
    ]
    chars: dict[str, Character] = {}
    for key, name, teaser, text in roster:
        chars[key] = Character.objects.create(event=event, name=name, teaser=teaser, text=text)
    return chars


def _build_factions(event: Event, chars: dict[str, Character]) -> None:
    old_money = Faction.objects.create(
        event=event,
        name="The Ashworth Set",
        teaser="<p>Old titles, old money, and old secrets.</p>",
    )
    old_money.characters.set([chars["duke"], chars["dowager"], chars["rake"], chars["chaperone"], chars["vicar"]])

    new_money = Faction.objects.create(
        event=event,
        name="New Fortunes",
        teaser="<p>Fresh wealth, still fighting for a place at the table.</p>",
    )
    new_money.characters.set([chars["captain"], chars["heiress"], chars["debutante"]])

    downstairs = Faction.objects.create(
        event=event,
        name="Belowstairs",
        teaser="<p>They serve the ballroom, and they know what really happens in it.</p>",
    )
    downstairs.characters.set([chars["valet"], chars["widow"]])


def _build_casting_config(event: Event) -> None:
    EventConfig.objects.create(event=event, name="casting_min", value="3")
    EventConfig.objects.create(event=event, name="casting_max", value="5")
    EventConfig.objects.create(event=event, name="casting_add", value="2")
    EventConfig.objects.create(event=event, name="casting_characters", value="1")
    EventConfig.objects.create(event=event, name="casting_avoid", value="True")


def _build_registrations(event: Event, association: Association) -> list[Registration]:
    run = event.runs.first()
    ticket = event.tickets.get(tier=TicketTier.STANDARD)
    players = [
        ("demo-casting-player1", "Alice", "Stone"),
        ("demo-casting-player2", "Ben", "Voss"),
        ("demo-casting-player3", "Clara", "Wynn"),
        ("demo-casting-player4", "Dario", "Kell"),
        ("demo-casting-player5", "Eva", "Marsh"),
        ("demo-casting-player6", "Finn", "Osei"),
        ("demo-casting-player7", "Grace", "Lund"),
    ]
    registrations = []
    for username, name, surname in players:
        member = _make_member(username, name, surname, association)
        registrations.append(Registration.objects.create(run=run, member=member, ticket=ticket))
    return registrations


def _build_casting_preferences(event: Event, registrations: list[Registration], chars: dict[str, Character]) -> None:
    run = event.runs.first()

    # Deliberately conflicting preference lists: the Duke and the Heiress are
    # both fought over by several players, while the Valet is picked by no one,
    # so the casting algorithm has real work to do.
    preferences = {
        0: ["duke", "rake", "captain", "dowager", "widow"],
        1: ["duke", "captain", "rake", "heiress", "chaperone"],
        2: ["heiress", "debutante", "widow", "dowager", "duke"],
        3: ["heiress", "widow", "debutante", "captain", "rake"],
        4: ["captain", "duke", "heiress", "vicar", "dowager"],
        5: ["dowager", "chaperone", "vicar", "duke", "captain"],
        6: ["rake", "duke", "dowager", "heiress", "widow"],
    }
    for index, registration in enumerate(registrations):
        for rank, char_key in enumerate(preferences[index], start=1):
            Casting.objects.create(
                run=run,
                member=registration.member,
                element=str(chars[char_key].uuid),
                pref=rank,
                typ=0,
            )

    # One player explicitly refuses to play the Vicar.
    CastingAvoid.objects.create(
        run=run,
        member=registrations[2].member,
        typ=0,
        text="I would rather not play the Reverend, thank you.",
    )


def _build_demo_type_and_hints(association: Association) -> LarpManagerDemoType:
    demo_type = LarpManagerDemoType.objects.create(
        name="Casting",
        slug=DEMO_TYPE_SLUG,
        descr=(
            "Pre-written characters, factions, player preference lists and organizer-run "
            "casting assignment, resolving deliberately conflicting picks."
        ),
        template_association=association,
        allowed_sidebar="orga_characters,orga_factions,orga_casting_preferences,orga_casting",
    )

    hints = [
        ("casting-demo-event", "event", "Welcome to the Regency Ball", "<p>Start by exploring the event page.</p>"),
        (
            "casting-demo-register",
            "register",
            "Sign up and cast your own picks",
            (
                "<p>Register for the event, then submit your own preference list: you will be matched "
                "against seven other players who already submitted theirs, some competing for the same "
                "characters you want.</p>"
            ),
        ),
        (
            "casting-demo-gallery",
            "gallery",
            "Browse the cast",
            "<p>Ten pre-written characters, organized by faction, each with a public teaser.</p>",
        ),
        (
            "casting-demo-preferences",
            "casting_preferences",
            "Rank your preferences",
            (
                "<p>Pick your favorite characters in order, and optionally mark one you would rather avoid. "
                "Some of the most popular characters here are wanted by several other players already.</p>"
            ),
        ),
        (
            "casting-demo-orga-preferences",
            "orga_casting_preferences",
            "See everyone's picks",
            (
                "<p>As organizer, this view shows every submitted preference list side by side: "
                "notice how the Duke and the Heiress are fought over, while the Valet is unwanted.</p>"
            ),
        ),
        (
            "casting-demo-orga-casting",
            "orga_casting",
            "Run the casting algorithm",
            (
                "<p>Let LarpManager compute the optimal assignment from all the preference lists, "
                "then confirm it to assign characters to players.</p>"
            ),
        ),
        (
            "casting-demo-customize",
            "character_customize",
            "Customize your character",
            "<p>Once assigned, players can personalize their character's name and pronouns.</p>",
        ),
    ]
    for key, view_name, title, content in hints:
        LarpManagerDemoHint.objects.get_or_create(
            key=key,
            defaults={"demo_type": demo_type, "view_name": view_name, "title": title, "content": content},
        )

    return demo_type


def build_casting_demo() -> LarpManagerDemoType:
    """Create (or fetch) the template association/event for the Casting feature demo."""
    existing = LarpManagerDemoType.objects.filter(slug=DEMO_TYPE_SLUG).first()
    if existing:
        return existing

    association = Association.objects.create(slug=ASSOCIATION_SLUG, name="Casting Demo")
    event = Event.objects.create(
        association=association,
        name="The Regency Ball",
        slug=EVENT_SLUG,
        tagline="Ten guests, three factions, and a season's worth of scandal in one ballroom.",
        description=(
            "<p>A season of debts, elopements, forgery and blackmail collides in one ballroom. "
            "Ten pre-written characters split across old money, new fortunes and the servants "
            "belowstairs who know everyone's business. Submit your ranked preferences, then "
            "watch the organizer's casting algorithm untangle who gets the Duke and who gets "
            "left with the Vicar nobody wanted.</p>"
        ),
    )
    run = event.runs.first()
    run.start = datetime.datetime.now(tz=UTC).date() + datetime.timedelta(days=60)
    run.end = run.start + datetime.timedelta(days=2)
    run.save()
    _enable_features(event, ["character", "user_character", "casting", "custom_character", "faction"])

    _build_casting_config(event)
    chars = _build_characters(event)
    _build_factions(event, chars)
    registrations = _build_registrations(event, association)
    _build_casting_preferences(event, registrations, chars)

    return _build_demo_type_and_hints(association)
