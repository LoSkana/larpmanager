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
"""Template association showcasing the Experience feature.

Races, classes, abilities, prerequisites, modifiers, criteria and computed rules (Hit Points / Mana).
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User

from larpmanager.models.association import Association
from larpmanager.models.base import Feature
from larpmanager.models.event import Event, EventConfig
from larpmanager.models.experience import (
    AbilityExp,
    AbilityTypeExp,
    CriterionExp,
    DeliveryExp,
    ModifierExp,
    Operation,
    RuleExp,
    SystemExp,
)
from larpmanager.models.form import WritingChoice, WritingOption, WritingQuestion, WritingQuestionType
from larpmanager.models.larpmanager import LarpManagerDemoHint, LarpManagerDemoType
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import Character, Faction

ASSOCIATION_SLUG = "demo-experience"
EVENT_SLUG = "ebonreach"
DEMO_TYPE_SLUG = "experience"


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


def _build_character_options(event: Event) -> dict[str, Any]:
    race_question = WritingQuestion.objects.create(event=event, name="Race", typ=WritingQuestionType.SINGLE)
    class_question = WritingQuestion.objects.create(event=event, name="Class", typ=WritingQuestionType.SINGLE)
    return {
        "race_question": race_question,
        "race_human": WritingOption.objects.create(event=event, question=race_question, name="Human"),
        "race_dwarf": WritingOption.objects.create(event=event, question=race_question, name="Dwarf"),
        "race_elf": WritingOption.objects.create(event=event, question=race_question, name="Elf"),
        "class_question": class_question,
        "class_fighter": WritingOption.objects.create(event=event, question=class_question, name="Fighter"),
        "class_mage": WritingOption.objects.create(event=event, question=class_question, name="Mage"),
        "class_rogue": WritingOption.objects.create(event=event, question=class_question, name="Rogue"),
        "hp_question": WritingQuestion.objects.create(event=event, name="Hit Points", typ=WritingQuestionType.COMPUTED),
        "mana_question": WritingQuestion.objects.create(event=event, name="Mana", typ=WritingQuestionType.COMPUTED),
    }


def _build_abilities(event: Event, system: SystemExp, opt: dict[str, Any]) -> dict[str, AbilityExp]:
    combat_type = AbilityTypeExp.objects.create(event=event, name="Combat")
    magic_type = AbilityTypeExp.objects.create(event=event, name="Magic")
    skill_type = AbilityTypeExp.objects.create(event=event, name="Skill")
    general_type = AbilityTypeExp.objects.create(event=event, name="General")

    def ability(
        name: str,
        typ: AbilityTypeExp,
        cost: int,
        descr: str,
        requirements: list[WritingOption] = (),
        prerequisites: list[AbilityExp] = (),
    ) -> AbilityExp:
        created_ability = AbilityExp.objects.create(
            event=event, system=system, typ=typ, name=name, cost=cost, descr=descr
        )
        if requirements:
            created_ability.requirements.set(requirements)
        if prerequisites:
            created_ability.prerequisites.set(prerequisites)
        return created_ability

    # Combat: ability-to-ability prerequisite chain, gated to the Fighter class
    weapon_training = ability(
        "Weapon Training", combat_type, 5, "Basic mastery of melee weapons.", requirements=[opt["class_fighter"]]
    )
    shield_wall = ability(
        "Shield Wall",
        combat_type,
        10,
        "Form a defensive line, reducing incoming damage.",
        requirements=[opt["class_fighter"]],
        prerequisites=[weapon_training],
    )
    berserker_rage = ability(
        "Berserker Rage",
        combat_type,
        15,
        "Fight in a battle fury, ignoring pain.",
        requirements=[opt["class_fighter"]],
        prerequisites=[shield_wall],
    )

    # Magic: ability-to-ability chain, gated to the Mage class, with a race+class combined requirement
    arcane_bolt = ability(
        "Arcane Bolt", magic_type, 5, "A basic bolt of arcane energy.", requirements=[opt["class_mage"]]
    )
    mana_shield = ability(
        "Mana Shield",
        magic_type,
        10,
        "Convert mana into a protective barrier.",
        requirements=[opt["class_mage"]],
        prerequisites=[arcane_bolt],
    )
    greater_ritual = ability(
        "Greater Ritual",
        magic_type,
        20,
        "An elven rite of power, reserved to the most gifted mages.",
        requirements=[opt["race_elf"], opt["class_mage"]],
        prerequisites=[mana_shield],
    )

    # Skill: ability-to-ability chain, gated to the Rogue class
    stealth = ability("Stealth", skill_type, 5, "Move unseen and unheard.", requirements=[opt["class_rogue"]])
    backstab = ability(
        "Backstab",
        skill_type,
        10,
        "Strike an unaware foe for extra damage.",
        requirements=[opt["class_rogue"]],
        prerequisites=[stealth],
    )

    # General
    physical_training = ability(
        "Physical Training",
        general_type,
        10,
        "Harden your body.",
    )
    mental_training = ability(
        "Mental Training",
        general_type,
        10,
        "Sharpen your mind.",
    )

    return {
        "weapon_training": weapon_training,
        "shield_wall": shield_wall,
        "berserker_rage": berserker_rage,
        "arcane_bolt": arcane_bolt,
        "mana_shield": mana_shield,
        "greater_ritual": greater_ritual,
        "stealth": stealth,
        "backstab": backstab,
        "physical_training": physical_training,
        "mental_training": mental_training,
    }


def _build_modifiers_and_criterion(event: Event, system: SystemExp, opt: dict[str, Any], ab: dict) -> None:
    # Modifiers: same ability, free cost for a specific race
    physical_free_for_dwarves = ModifierExp.objects.create(event=event, name="Dwarven Physique", cost=0)
    physical_free_for_dwarves.abilities.set([ab["physical_training"]])
    physical_free_for_dwarves.requirements.set([opt["race_dwarf"]])

    physical_blocked_for_elves = ModifierExp.objects.create(event=event, name="Elf Physique", cost=999)
    physical_blocked_for_elves.abilities.set([ab["physical_training"]])
    physical_blocked_for_elves.requirements.set([opt["race_elf"]])

    physical_half_for_human = ModifierExp.objects.create(event=event, name="Human Physique", cost=5)
    physical_half_for_human.abilities.set([ab["physical_training"]])
    physical_half_for_human.requirements.set([opt["race_human"]])

    mental_free_for_elves = ModifierExp.objects.create(event=event, name="Elven Mind", cost=0)
    mental_free_for_elves.abilities.set([ab["mental_training"]])
    mental_free_for_elves.requirements.set([opt["race_elf"]])

    mental_free_for_dwarves = ModifierExp.objects.create(event=event, name="Dwarven mind", cost=999)
    mental_free_for_dwarves.abilities.set([ab["mental_training"]])
    mental_free_for_dwarves.requirements.set([opt["race_dwarf"]])

    mental_half_for_human = ModifierExp.objects.create(event=event, name="Human mind", cost=5)
    mental_half_for_human.abilities.set([ab["mental_training"]])
    mental_half_for_human.requirements.set([opt["race_human"]])

    # Criterion: elves start with extra experience points
    elven_heritage = CriterionExp.objects.create(
        event=event, system=system, name="Elven Heritage", operation=Operation.ADDITION, amount=5
    )
    elven_heritage.requirements.set([opt["race_elf"]])


def _build_rules(event: Event, opt: dict[str, Any], ab: dict) -> None:
    def rule(name: str, field: WritingQuestion, amount: int, abilities: list[AbilityExp] = ()) -> RuleExp:
        created_rule = RuleExp.objects.create(
            event=event, name=name, field=field, operation=Operation.ADDITION, amount=amount
        )
        if abilities:
            created_rule.abilities.set(abilities)
        return created_rule

    hp_question, mana_question = opt["hp_question"], opt["mana_question"]
    rule("Base Hit Points", hp_question, 10)
    rule("Shield Wall Toughness", hp_question, 15, abilities=[ab["shield_wall"]])
    rule("Berserker Fortitude", hp_question, 20, abilities=[ab["berserker_rage"]])
    rule("Physical Conditioning", hp_question, 15, abilities=[ab["physical_training"]])

    rule("Arcane Bolt Focus", mana_question, 10, abilities=[ab["arcane_bolt"]])
    rule("Mana Shield Reserve", mana_question, 15, abilities=[ab["mana_shield"]])
    rule("Greater Ritual Power", mana_question, 25, abilities=[ab["greater_ritual"]])
    rule("Mental Conditioning", mana_question, 15, abilities=[ab["mental_training"]])


def _build_characters(event: Event, opt: dict[str, Any]) -> dict[str, Character]:
    def make_character(name: str, race_opt: WritingOption, class_opt: WritingOption) -> Character:
        char = Character.objects.create(event=event, name=name)
        WritingChoice.objects.create(element_id=char.id, question=opt["race_question"], option=race_opt)
        WritingChoice.objects.create(element_id=char.id, question=opt["class_question"], option=class_opt)
        return char

    bram = make_character("Bram Ironfist", opt["race_dwarf"], opt["class_fighter"])
    sera = make_character("Sera Nightblade", opt["race_human"], opt["class_rogue"])
    elowen = make_character("Elowen Starweaver", opt["race_elf"], opt["class_mage"])
    grom = make_character("Grom Stonehide", opt["race_dwarf"], opt["class_fighter"])
    finn = make_character("Finn Quickstep", opt["race_human"], opt["class_rogue"])

    ashen_company = Faction.objects.create(event=event, name="The Ashen Company")
    ashen_company.characters.set([bram, sera, elowen])

    hollow_road = Faction.objects.create(event=event, name="Hollow Road")
    hollow_road.characters.set([grom, finn])

    return {"bram": bram, "sera": sera, "elowen": elowen, "grom": grom, "finn": finn}


def _build_registrations(event: Event, association: Association, chars: dict[str, Character]) -> None:
    run = event.runs.first()
    ticket = event.tickets.get(tier=TicketTier.STANDARD)
    players = [
        ("demo-player1", "Alice", "Stone", chars["bram"]),
        ("demo-player2", "Ben", "Voss", chars["sera"]),
        ("demo-player3", "Clara", "Wynn", chars["elowen"]),
        ("demo-player4", "Dario", "Kell", chars["grom"]),
        ("demo-player5", "Eva", "Marsh", chars["finn"]),
    ]
    for username, name, surname, char in players:
        member = _make_member(username, name, surname, association)
        registration = Registration.objects.create(run=run, member=member, ticket=ticket)
        RegistrationCharacterRel.objects.create(registration=registration, character=char)


def _build_deliveries(event: Event, system: SystemExp, chars: dict[str, Character]) -> None:
    founding_bonus = DeliveryExp.objects.create(event=event, system=system, name="Founding Bonus", amount=15)
    founding_bonus.characters.set([chars["bram"], chars["elowen"], chars["grom"]])

    quest_reward = DeliveryExp.objects.create(event=event, system=system, name="Quest Reward", amount=10)
    quest_reward.characters.set([chars["sera"], chars["grom"], chars["finn"], chars["bram"]])


def _build_demo_type_and_hints(association: Association) -> LarpManagerDemoType:
    demo_type = LarpManagerDemoType.objects.create(
        name="Experience Points",
        slug=DEMO_TYPE_SLUG,
        descr="Races, classes, abilities, prerequisites, modifiers, criteria and computed rules.",
        template_association=association,
        allowed_sidebar="orga_characters,orga_character_form,orga_exp_abilities",
    )

    hints = [
        ("experience-demo-event", "event", "Welcome to Ebonreach", "<p>Start by exploring the event page.</p>"),
        ("experience-demo-register", "register", "Sign up", "<p>Register for the event to get a character.</p>"),
        (
            "experience-demo-character-create",
            "character_create",
            "Create your character",
            "<p>Pick a Race and a Class: they unlock different abilities.</p>",
        ),
        (
            "experience-demo-abilities",
            "character_abilities",
            "Spend your experience points",
            "<p>Buy abilities, following the prerequisites, and watch your Hit Points and Mana grow.</p>",
        ),
        (
            "experience-demo-manage",
            "orga_exp_abilities",
            "Manage experience",
            "<p>As organizer, this is where abilities, modifiers, criteria and rules are configured.</p>",
        ),
    ]
    for key, view_name, title, content in hints:
        LarpManagerDemoHint.objects.get_or_create(
            key=key,
            defaults={"demo_type": demo_type, "view_name": view_name, "title": title, "content": content},
        )

    return demo_type


def build_experience_demo() -> LarpManagerDemoType:
    """Create (or fetch) the template association/event for the Experience feature demo."""
    existing = LarpManagerDemoType.objects.filter(slug=DEMO_TYPE_SLUG).first()
    if existing:
        return existing

    association = Association.objects.create(slug=ASSOCIATION_SLUG, name="Experience Demo")
    event = Event.objects.create(association=association, name="Trial of Ebonreach", slug=EVENT_SLUG)
    _enable_features(event, ["character", "user_character", "experience"])

    EventConfig.objects.create(event=event, name="exp_modifiers", value="True")
    EventConfig.objects.create(event=event, name="exp_criterions", value="True")

    system = SystemExp.objects.create(event=event, name="XP")
    opt = _build_character_options(event)
    ab = _build_abilities(event, system, opt)
    _build_modifiers_and_criterion(event, system, opt, ab)
    _build_rules(event, opt, ab)

    chars = _build_characters(event, opt)
    _build_registrations(event, association, chars)
    _build_deliveries(event, system, chars)

    return _build_demo_type_and_hints(association)
