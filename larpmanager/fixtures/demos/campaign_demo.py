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
"""Template association showcasing the Campaign feature.

A chronicle of three events sharing one character pool: two played chapters
whose characters carry their experience forward, and one upcoming chapter
whose registration setup was duplicated from the previous one via Copy.
"""

from __future__ import annotations

import datetime
from datetime import UTC
from typing import Any

from django.contrib.auth.models import User

from larpmanager.models.association import Association
from larpmanager.models.base import Feature
from larpmanager.models.event import Event, EventConfig, RegistrationStatus
from larpmanager.models.experience import AbilityExp, AbilityTypeExp, DeliveryExp, SystemExp
from larpmanager.models.larpmanager import LarpManagerDemoHint, LarpManagerDemoType
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import Registration, RegistrationCharacterRel, RegistrationTicket, TicketTier
from larpmanager.models.writing import Character, Faction
from larpmanager.utils.core.common import copy_class

ASSOCIATION_SLUG = "demo-campaign"
DEMO_TYPE_SLUG = "campaign"

CHAPTER_1_SLUG = "sundering"
CHAPTER_2_SLUG = "ashen-court"
CHAPTER_3_SLUG = "last-vigil"


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


def _build_events(association: Association) -> dict[str, Event]:
    today = datetime.datetime.now(tz=UTC).date()

    chapter_1 = Event.objects.create(
        association=association,
        name="Vaelmoor: The Sundering",
        slug=CHAPTER_1_SLUG,
        tagline="The Ashblood Court chooses its heir, or breaks trying.",
        description=(
            "<p>For three centuries Lucian Thorne has held the Ashblood Court by will alone. "
            "Tonight the succession comes to a head: a knight hungry for the throne, a seer who "
            "has already glimpsed the coup, and a voice from the rival Silver Veil offering a "
            "peace no one asked for.</p><p>The first chapter of the Vaelmoor Chronicle, a "
            "vampire-court campaign played across three linked chapters with one persistent "
            "cast of characters.</p>"
        ),
    )
    run_1 = chapter_1.runs.first()
    run_1.start = today - datetime.timedelta(days=180)
    run_1.end = run_1.start + datetime.timedelta(days=2)
    run_1.development = "9"  # Concluded
    run_1.registration_status = RegistrationStatus.CLOSED
    run_1.save()

    chapter_2 = Event.objects.create(
        association=association,
        name="Vaelmoor: The Ashen Court",
        slug=CHAPTER_2_SLUG,
        parent=chapter_1,
        tagline="The Sundering left scars. The court still has to rule.",
        description=(
            "<p>Second chapter of the Vaelmoor Chronicle. The same cast returns, carrying the "
            "consequences of the Sundering with them, as a newly Embraced player joins the "
            "table and the balance between the Ashblood Court and the Silver Veil is tested "
            "again.</p>"
        ),
    )
    run_2 = chapter_2.runs.first()
    run_2.start = today - datetime.timedelta(days=60)
    run_2.end = run_2.start + datetime.timedelta(days=2)
    run_2.development = "9"  # Concluded
    run_2.registration_status = RegistrationStatus.CLOSED
    run_2.save()

    chapter_3 = Event.objects.create(
        association=association,
        name="Vaelmoor: The Last Vigil",
        slug=CHAPTER_3_SLUG,
        parent=chapter_1,
        tagline="One more night for the Ashblood Court to decide what it is.",
        description=(
            "<p>The upcoming third chapter of the Vaelmoor Chronicle. Registration is open now; "
            "its ticket and form setup was duplicated from Chapter 2 with the Copy feature "
            "rather than rebuilt from scratch.</p>"
        ),
    )
    run_3 = chapter_3.runs.first()
    run_3.start = today + datetime.timedelta(days=45)
    run_3.end = run_3.start + datetime.timedelta(days=2)
    run_3.development = "1"  # Visible
    run_3.registration_status = RegistrationStatus.OPEN
    run_3.save()

    return {"chapter_1": chapter_1, "chapter_2": chapter_2, "chapter_3": chapter_3}


def _build_characters(chapter_1: Event) -> dict[str, Character]:
    lucian = Character.objects.create(
        event=chapter_1,
        name="Lucian Thorne",
        teaser="<p>Elder of the Ashblood Court, holding the throne by will alone.</p>",
        text=(
            "<p>You have ruled the Ashblood Court for three centuries. Aurelio "
            "believes it is time you stepped aside, and you are not certain he "
            "is wrong.</p>"
        ),
    )
    mireille = Character.objects.create(
        event=chapter_1,
        name="Mireille Duskwood",
        teaser="<p>Voice of the Silver Veil, who trades in secrets rather than blood.</p>",
        text=(
            "<p>You know Lucian's grip on the Ashblood Court is weakening, and you "
            "intend to broker a peace before Aurelio's ambition drags both courts "
            "into open war.</p>"
        ),
    )
    aurelio = Character.objects.create(
        event=chapter_1,
        name="Aurelio Vance",
        teaser="<p>Ambitious knight of the Ashblood Court, hungry for the throne.</p>",
        text=(
            "<p>You have spent a decade proving your loyalty to Lucian, all while "
            "quietly gathering the support you will need the night you finally "
            "challenge him.</p>"
        ),
    )
    ysolde = Character.objects.create(
        event=chapter_1,
        name="Ysolde Marrow",
        teaser="<p>A Silver Veil seer whose visions unsettle even the elders.</p>",
        text=(
            "<p>Your visions have shown you Aurelio's coup before it happens. You "
            "have not decided whether warning Lucian would prevent it or simply "
            "hasten it.</p>"
        ),
    )
    corvin = Character.objects.create(
        event=chapter_1,
        name="Corvin Ashe",
        teaser="<p>A mortal on the verge of the Embrace, caught between two courts.</p>",
        text=(
            "<p>Aurelio promised to Embrace you if you helped him against Lucian. "
            "You are only now learning what that promise will actually cost you.</p>"
        ),
    )

    ashblood_court = Faction.objects.create(event=chapter_1, name="The Ashblood Court")
    ashblood_court.characters.set([lucian, aurelio, corvin])

    silver_veil = Faction.objects.create(event=chapter_1, name="The Silver Veil")
    silver_veil.characters.set([mireille, ysolde])

    return {
        "lucian": lucian,
        "mireille": mireille,
        "aurelio": aurelio,
        "ysolde": ysolde,
        "corvin": corvin,
    }


def _build_experience(chapter_1: Event, chars: dict[str, Character]) -> None:
    system = SystemExp.objects.create(event=chapter_1, name="Vitae")
    discipline = AbilityTypeExp.objects.create(event=chapter_1, name="Discipline")

    beasts_grip = AbilityExp.objects.create(
        event=chapter_1,
        system=system,
        typ=discipline,
        name="Beast's Grip",
        cost=5,
        descr="Suppress the frenzy for one more moment.",
    )
    blood_sense = AbilityExp.objects.create(
        event=chapter_1,
        system=system,
        typ=discipline,
        name="Blood Sense",
        cost=10,
        descr="Taste the truth of another's vitae.",
    )
    blood_sense.prerequisites.set([beasts_grip])
    dominate = AbilityExp.objects.create(
        event=chapter_1,
        system=system,
        typ=discipline,
        name="Dominate",
        cost=15,
        descr="Bend a mortal's will to your own.",
    )
    dominate.prerequisites.set([blood_sense])

    # XP deliveries per chapter: everyone who survived Chapter 1 carries the reward forward,
    # and Chapter 2's veterans (plus the newly embraced Corvin) earn the next batch.
    chapter_1_reward = DeliveryExp.objects.create(
        event=chapter_1, system=system, name="Chapter 1: The Sundering - Session Reward", amount=10
    )
    chapter_1_reward.characters.set([chars["lucian"], chars["mireille"], chars["aurelio"], chars["ysolde"]])

    chapter_2_reward = DeliveryExp.objects.create(
        event=chapter_1, system=system, name="Chapter 2: The Ashen Court - Session Reward", amount=15
    )
    chapter_2_reward.characters.set(list(chars.values()))


def _build_registrations(chapters: dict[str, Event], chars: dict[str, Character]) -> None:
    association = chapters["chapter_1"].association
    ticket_1 = chapters["chapter_1"].tickets.get(tier=TicketTier.STANDARD)

    run_1 = chapters["chapter_1"].runs.first()
    veterans = [
        ("demo-camp-player1", "Alice", "Stone", chars["lucian"]),
        ("demo-camp-player2", "Ben", "Voss", chars["mireille"]),
        ("demo-camp-player3", "Clara", "Wynn", chars["aurelio"]),
        ("demo-camp-player4", "Dario", "Kell", chars["ysolde"]),
    ]
    for username, name, surname, char in veterans:
        member = _make_member(username, name, surname, association)
        registration = Registration.objects.create(run=run_1, member=member, ticket=ticket_1)
        RegistrationCharacterRel.objects.create(registration=registration, character=char)

    # Chapter 2 has its own ticket setup (a "Returning Character" tier), reused by the
    # same four players plus one newly embraced character.
    ticket_2 = chapters["chapter_2"].tickets.get(tier=TicketTier.STANDARD)
    ticket_2.name = "Returning Character"
    ticket_2.price = 20
    ticket_2.save()
    run_2 = chapters["chapter_2"].runs.first()
    for username, _name, _surname, char in veterans:
        member = User.objects.get(username=username).member
        registration = Registration.objects.create(run=run_2, member=member, ticket=ticket_2)
        RegistrationCharacterRel.objects.create(registration=registration, character=char)

    member_5 = _make_member("demo-camp-player5", "Eva", "Marsh", association)
    registration_5 = Registration.objects.create(run=run_2, member=member_5, ticket=ticket_2)
    RegistrationCharacterRel.objects.create(registration=registration_5, character=chars["corvin"])


def _copy_chapter_setup(chapters: dict[str, Event]) -> None:
    """Set up the upcoming Chapter 3 by copying Chapter 2's registration setup (as Copy would)."""
    target_id, source_id = chapters["chapter_3"].id, chapters["chapter_2"].id
    copy_class(target_id, source_id, RegistrationTicket)
    copy_class(target_id, source_id, EventConfig)


def _build_demo_type_and_hints(association: Association) -> LarpManagerDemoType:
    demo_type = LarpManagerDemoType.objects.create(
        name="Campaign",
        slug=DEMO_TYPE_SLUG,
        descr=(
            "A chronicle of recurring events sharing one persistent cast of characters, "
            "with experience carried forward chapter after chapter."
        ),
        template_association=association,
        allowed_sidebar="orga_characters,orga_character_form,orga_exp_abilities,orga_copy",
        is_campaign=True,
    )

    hints = [
        (
            "campaign-demo-event",
            "event",
            "Welcome to the Vaelmoor Chronicle",
            "<p>This association runs a campaign: three chapters, one shared cast of characters.</p>",
        ),
        (
            "campaign-demo-register",
            "register",
            "Join the next chapter",
            "<p>Sign up for the upcoming chapter and pick up where the story left off.</p>",
        ),
        (
            "campaign-demo-abilities",
            "character_abilities",
            "Experience carried across chapters",
            "<p>These points were earned over two previous chapters, not just this one.</p>",
        ),
        (
            "campaign-demo-manage-characters",
            "orga_characters",
            "One roster, every chapter",
            "<p>Characters live on the campaign's founding event: every chapter reads the same roster.</p>",
        ),
        (
            "campaign-demo-manage-copy",
            "orga_copy",
            "Reuse a previous chapter's setup",
            (
                "<p>The upcoming chapter's tickets and settings were duplicated from the last one with "
                "Copy, instead of being rebuilt from scratch.</p>"
            ),
        ),
    ]
    for key, view_name, title, content in hints:
        LarpManagerDemoHint.objects.get_or_create(
            key=key,
            defaults={"demo_type": demo_type, "view_name": view_name, "title": title, "content": content},
        )

    return demo_type


def build_campaign_demo() -> LarpManagerDemoType:
    """Create (or fetch) the template association/events for the Campaign feature demo."""
    existing = LarpManagerDemoType.objects.filter(slug=DEMO_TYPE_SLUG).first()
    if existing:
        return existing

    association = Association.objects.create(slug=ASSOCIATION_SLUG, name="Campaign Demo")
    _enable_assoc_features(association, ["campaign"])

    chapters = _build_events(association)
    chapter_1 = chapters["chapter_1"]
    _enable_event_features(chapter_1, ["character", "user_character", "experience", "campaign", "copy"])

    chars = _build_characters(chapter_1)
    _build_experience(chapter_1, chars)
    _build_registrations(chapters, chars)
    _copy_chapter_setup(chapters)

    return _build_demo_type_and_hints(association)
