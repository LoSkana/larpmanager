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
"""Template association showcasing player self-service character creation.

Player-written characters with a multi-type form (single/multiple/text/paragraph/editor
questions, with options depending on previously chosen values), an organizer approval
queue, and player-authored relationships.
"""

from __future__ import annotations

import datetime
from datetime import UTC
from typing import Any

from django.contrib.auth.models import User

from larpmanager.models.association import Association
from larpmanager.models.base import Feature
from larpmanager.models.event import Event, EventConfig
from larpmanager.models.form import WritingAnswer, WritingChoice, WritingOption, WritingQuestion, WritingQuestionType
from larpmanager.models.larpmanager import LarpManagerDemoHint, LarpManagerDemoType
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.miscellanea import PlayerRelationship
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import Character, CharacterStatus

ASSOCIATION_SLUG = "demo-player-characters"
EVENT_SLUG = "ashfall"
DEMO_TYPE_SLUG = "player-characters"


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


def _build_character_form(event: Event) -> dict[str, Any]:
    origin_question = WritingQuestion.objects.create(event=event, name="Origin", typ=WritingQuestionType.SINGLE)
    mutation_question = WritingQuestion.objects.create(
        event=event, name="Mutation Path", typ=WritingQuestionType.SINGLE
    )
    skills_question = WritingQuestion.objects.create(event=event, name="Skills", typ=WritingQuestionType.MULTIPLE)
    gear_question = WritingQuestion.objects.create(event=event, name="Gear Loadout", typ=WritingQuestionType.MULTIPLE)
    callsign_question = WritingQuestion.objects.create(
        event=event, name="Callsign", typ=WritingQuestionType.TEXT, max_length=50
    )
    appearance_question = WritingQuestion.objects.create(
        event=event, name="Appearance", typ=WritingQuestionType.PARAGRAPH, max_length=800
    )
    backstory_question = WritingQuestion.objects.create(
        event=event, name="Backstory", typ=WritingQuestionType.EDITOR, max_length=5000
    )

    def option(question: WritingQuestion, name: str, requirements: list[WritingOption] = ()) -> WritingOption:
        created_option = WritingOption.objects.create(event=event, question=question, name=name)
        if requirements:
            created_option.requirements.set(requirements)
        return created_option

    # Origin: the root choice everything else branches from.
    origin_bunker = option(origin_question, "Bunker-Dweller")
    origin_wasteland = option(origin_question, "Wastelander")
    origin_raider = option(origin_question, "Raider Clan")

    # Mutation Path: depends on Origin.
    mutation_none = option(mutation_question, "None")
    mutation_feral = option(mutation_question, "Feral Strain", requirements=[origin_wasteland])
    mutation_psionic = option(mutation_question, "Psionic Strain", requirements=[origin_bunker])

    # Skills: depend on Origin, or (Psionic Static) two hops back through Mutation Path.
    skill_lockpicking = option(skills_question, "Lockpicking", requirements=[origin_bunker])
    skill_scavenging = option(skills_question, "Scavenging", requirements=[origin_wasteland])
    skill_melee = option(skills_question, "Melee Combat", requirements=[origin_raider])
    skill_psionic_static = option(skills_question, "Psionic Static", requirements=[mutation_psionic])

    # Gear Loadout: depends on Skills or Mutation Path, chaining back to Origin.
    gear_machete = option(gear_question, "Rusty Machete", requirements=[skill_melee])
    gear_toolkit = option(gear_question, "Salvaged Toolkit", requirements=[skill_scavenging])
    gear_lockpick_rig = option(gear_question, "Auto-Lockpick Rig", requirements=[skill_lockpicking])
    gear_injector = option(gear_question, "Serum Injector", requirements=[mutation_psionic])

    return {
        "origin_question": origin_question,
        "origin_bunker": origin_bunker,
        "origin_wasteland": origin_wasteland,
        "origin_raider": origin_raider,
        "mutation_question": mutation_question,
        "mutation_none": mutation_none,
        "mutation_feral": mutation_feral,
        "mutation_psionic": mutation_psionic,
        "skills_question": skills_question,
        "skill_lockpicking": skill_lockpicking,
        "skill_scavenging": skill_scavenging,
        "skill_melee": skill_melee,
        "skill_psionic_static": skill_psionic_static,
        "gear_question": gear_question,
        "gear_machete": gear_machete,
        "gear_toolkit": gear_toolkit,
        "gear_lockpick_rig": gear_lockpick_rig,
        "gear_injector": gear_injector,
        "callsign_question": callsign_question,
        "appearance_question": appearance_question,
        "backstory_question": backstory_question,
    }


def _build_players_and_characters(
    event: Event, association: Association, opt: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Character]]:
    def make_character(spec: dict[str, Any]) -> tuple[Any, Character]:
        member = _make_member(spec["username"], spec["first_name"], spec["surname"], association)
        char = Character.objects.create(
            event=event,
            name=spec["char_name"],
            player=member,
            status=spec["status"],
            teaser=f"<p>{spec['appearance']}</p>",
            text=f"<p>{spec['backstory']}</p>",
        )
        WritingChoice.objects.create(element_id=char.id, question=opt["origin_question"], option=spec["origin"])
        WritingChoice.objects.create(element_id=char.id, question=opt["mutation_question"], option=spec["mutation"])
        for skill in spec["skills"]:
            WritingChoice.objects.create(element_id=char.id, question=opt["skills_question"], option=skill)
        for item in spec["gear"]:
            WritingChoice.objects.create(element_id=char.id, question=opt["gear_question"], option=item)
        WritingAnswer.objects.create(element_id=char.id, question=opt["callsign_question"], text=spec["callsign"])
        WritingAnswer.objects.create(element_id=char.id, question=opt["appearance_question"], text=spec["appearance"])
        WritingAnswer.objects.create(element_id=char.id, question=opt["backstory_question"], text=spec["backstory"])
        return member, char

    specs = [
        (
            "rhys",
            {
                "username": "demo-pc-player1",
                "first_name": "Alice",
                "surname": "Stone",
                "char_name": "Rhys Talon",
                "status": CharacterStatus.CREATION,
                "origin": opt["origin_bunker"],
                "mutation": opt["mutation_psionic"],
                "skills": [opt["skill_lockpicking"], opt["skill_psionic_static"]],
                "gear": [opt["gear_lockpick_rig"], opt["gear_injector"]],
                "callsign": "Whisper",
                "appearance": "Still filling this in.",
                "backstory": "Draft: grew up in Sub-Level 4, got out when the seals failed. Rest TBD.",
            },
        ),
        (
            "sable",
            {
                "username": "demo-pc-player2",
                "first_name": "Ben",
                "surname": "Voss",
                "char_name": "Sable Vance",
                "status": CharacterStatus.PROPOSED,
                "origin": opt["origin_wasteland"],
                "mutation": opt["mutation_feral"],
                "skills": [opt["skill_scavenging"]],
                "gear": [opt["gear_toolkit"]],
                "callsign": "Jackal",
                "appearance": "Lean, sun-scarred, a strip of scavenged fur across one shoulder.",
                "backstory": (
                    "Born on the open flats, Sable learned to read a ruin for salvage before she "
                    "could read words. The Feral Strain sharpened her senses further, at a cost "
                    "she is still learning to hide."
                ),
            },
        ),
        (
            "korr",
            {
                "username": "demo-pc-player3",
                "first_name": "Clara",
                "surname": "Wynn",
                "char_name": "Korr Dune",
                "status": CharacterStatus.REVIEW,
                "origin": opt["origin_raider"],
                "mutation": opt["mutation_none"],
                "skills": [opt["skill_melee"]],
                "gear": [opt["gear_machete"]],
                "callsign": "Ironjaw",
                "appearance": "Broad-shouldered, a jaw of scavenged plating welded shut over an old wound.",
                "backstory": (
                    "Raised in the Raider Clan's warbands, Korr never trusted anyone who did not "
                    "carry a scar earned in the open wastes."
                ),
            },
        ),
        (
            "nyx",
            {
                "username": "demo-pc-player4",
                "first_name": "Dario",
                "surname": "Kell",
                "char_name": "Nyx Ashworth",
                "status": CharacterStatus.APPROVED,
                "origin": opt["origin_bunker"],
                "mutation": opt["mutation_psionic"],
                "skills": [opt["skill_lockpicking"], opt["skill_psionic_static"]],
                "gear": [opt["gear_lockpick_rig"], opt["gear_injector"]],
                "callsign": "Static",
                "appearance": "Pale from decades underground, eyes that catch the light wrong.",
                "backstory": (
                    "Nyx was one of the first bunker-born to survive the Psionic Strain trials. "
                    "She has spent the years since trying to atone for what that program cost others."
                ),
            },
        ),
        (
            "brann",
            {
                "username": "demo-pc-player5",
                "first_name": "Eva",
                "surname": "Marsh",
                "char_name": "Brann Coyle",
                "status": CharacterStatus.APPROVED,
                "origin": opt["origin_wasteland"],
                "mutation": opt["mutation_feral"],
                "skills": [opt["skill_scavenging"]],
                "gear": [opt["gear_toolkit"]],
                "callsign": "Dustwalker",
                "appearance": "Weathered, quiet, carries more scavenged tools than weapons.",
                "backstory": (
                    "Brann has crossed the wastes alone for longer than most survive. He keeps "
                    "moving because the Feral Strain makes it hard to stay anywhere too long."
                ),
            },
        ),
    ]

    members: dict[str, Any] = {}
    chars: dict[str, Character] = {}
    for key, spec in specs:
        members[key], chars[key] = make_character(spec)
    return members, chars


def _build_registrations(event: Event, members: dict[str, Any], chars: dict[str, Character]) -> dict[str, Registration]:
    run = event.runs.first()
    ticket = event.tickets.get(tier=TicketTier.STANDARD)
    registrations: dict[str, Registration] = {}
    for key, member in members.items():
        registration = Registration.objects.create(run=run, member=member, ticket=ticket)
        RegistrationCharacterRel.objects.create(registration=registration, character=chars[key])
        registrations[key] = registration
    return registrations


def _build_relationships(chars: dict[str, Character], registrations: dict[str, Registration]) -> None:
    edges = [
        ("rhys", "sable", "She doesn't know I've been listening to Raider chatter about her stash."),
        ("sable", "korr", "He thinks I'm harmless. Good."),
        ("korr", "nyx", "The bunker-born make my skin crawl, but she's saved my crew twice."),
        ("nyx", "brann", "He carries wasteland scars I recognize from my own nightmares."),
        ("brann", "rhys", "Kid's got bunker manners but wasteland nerves. I like him."),
    ]
    for source_key, target_key, text in edges:
        PlayerRelationship.objects.create(
            registration=registrations[source_key],
            target=chars[target_key],
            text=f"<p>{text}</p>",
        )


def _build_demo_type_and_hints(association: Association) -> LarpManagerDemoType:
    demo_type = LarpManagerDemoType.objects.create(
        name="Player Character Creation",
        slug=DEMO_TYPE_SLUG,
        descr=(
            "Sandbox/boffer style: players write their own characters through a multi-type "
            "form with conditional options, then submit them for organizer approval."
        ),
        template_association=association,
        allowed_sidebar="orga_characters,orga_character_form",
    )

    hints = [
        ("player-characters-demo-event", "event", "Welcome to Ashfall", "<p>Start by exploring the event page.</p>"),
        ("player-characters-demo-register", "register", "Sign up", "<p>Register for the event to get started.</p>"),
        (
            "player-characters-demo-create",
            "character_create",
            "Write your own character",
            (
                "<p>Fill in Origin, Mutation Path, Skills and Gear: some options only unlock "
                "once you have picked the ones they depend on. Add a Callsign, Appearance and Backstory.</p>"
            ),
        ),
        (
            "player-characters-demo-relationships",
            "character_relationships",
            "Add a relationship",
            "<p>Write how your character feels about another one in the cast.</p>",
        ),
        (
            "player-characters-demo-manage",
            "orga_characters",
            "Review the approval queue",
            "<p>As organizer, this is where submitted characters wait for review and approval.</p>",
        ),
    ]
    for key, view_name, title, content in hints:
        LarpManagerDemoHint.objects.get_or_create(
            key=key,
            defaults={"demo_type": demo_type, "view_name": view_name, "title": title, "content": content},
        )

    return demo_type


def build_player_characters_demo() -> LarpManagerDemoType:
    """Create (or fetch) the template association/event for the Player Character Creation demo."""
    existing = LarpManagerDemoType.objects.filter(slug=DEMO_TYPE_SLUG).first()
    if existing:
        return existing

    association = Association.objects.create(slug=ASSOCIATION_SLUG, name="Player Character Creation Demo")
    event = Event.objects.create(
        association=association,
        name="Ashfall",
        slug=EVENT_SLUG,
        tagline="Bring your own survivor. The wasteland doesn't hand out backstories.",
        description=(
            "<p>A post-apocalyptic sandbox where every character is player-written from scratch. "
            "Pick an Origin, a Mutation Path branching off it, Skills and Gear that chain off "
            "both, then write your own Callsign, Appearance and Backstory. Submitted characters "
            "queue for organizer review before they hit the wasteland.</p>"
        ),
    )
    run = event.runs.first()
    run.start = datetime.datetime.now(tz=UTC).date() + datetime.timedelta(days=60)
    run.end = run.start + datetime.timedelta(days=2)
    run.save()
    _enable_features(event, ["character", "user_character", "player_relationships"])

    EventConfig.objects.create(event=event, name="user_character_approval", value="True")

    opt = _build_character_form(event)
    members, chars = _build_players_and_characters(event, association, opt)
    registrations = _build_registrations(event, members, chars)
    _build_relationships(chars, registrations)

    return _build_demo_type_and_hints(association)
