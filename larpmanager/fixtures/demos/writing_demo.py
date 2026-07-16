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
"""Template association showcasing the Story Writing features.

Characters, plots with per-character text, factions (incl. a secret one),
relationships, handouts, editorial progress and PDF sheet generation.
"""

from __future__ import annotations

import datetime
from datetime import UTC
from typing import Any

from django.contrib.auth.models import User

from larpmanager.models.association import Association
from larpmanager.models.base import Feature
from larpmanager.models.event import Event, ProgressStep
from larpmanager.models.larpmanager import LarpManagerDemoHint, LarpManagerDemoType
from larpmanager.models.member import Membership, MembershipStatus
from larpmanager.models.registration import Registration, RegistrationCharacterRel, TicketTier
from larpmanager.models.writing import Character, Faction, FactionType, Handout, Plot, PlotCharacterRel, Relationship

ASSOCIATION_SLUG = "demo-writing"
EVENT_SLUG = "neongala"
DEMO_TYPE_SLUG = "writing"


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


def _build_progress_steps(event: Event) -> dict[str, ProgressStep]:
    draft = ProgressStep.objects.create(event=event, number=1, name="Draft")
    ready = ProgressStep.objects.create(event=event, number=2, name="Ready for review")
    approved = ProgressStep.objects.create(event=event, number=3, name="Approved")
    return {"draft": draft, "ready": ready, "approved": approved}


def _build_characters(event: Event, progress: dict[str, ProgressStep]) -> dict[str, Character]:
    # Pass 1: create characters in order so their `number` is deterministic (1..8),
    # which lets pass 2 reference them by #<number> to showcase auto-linking.
    roster = [
        ("kade", "Kade Osei", progress["approved"]),
        ("rin", "Rin Kessler", progress["approved"]),
        ("vex", "Vex Marrow", progress["ready"]),
        ("juno", "Juno Alvarez", progress["ready"]),
        ("dice", "Dice Okafor", progress["draft"]),
        ("moth", "Moth Ferreira", progress["draft"]),
        ("silas", "Silas Cho", progress["ready"]),
        ("priya", "Priya Nandakumar", progress["approved"]),
    ]
    chars: dict[str, Character] = {}
    for key, name, step in roster:
        chars[key] = Character.objects.create(event=event, name=name, progress=step)

    n = {key: char.number for key, char in chars.items()}

    # Pass 2: fill teaser (public) and text (private) referencing other characters
    # by #<number> — LarpManager auto-links these tokens to the target sheet.
    updates = {
        "kade": (
            f"<p>Rising executive at Zenith Dynamics, torn between duty and the black-market debt he owes #{n['dice']}.</p>",
            f"<p>You clawed your way into the executive tier three years ago. #{n['rin']} is your most trusted "
            f"head of security, but you have never told her about the fixer you turned to when the launch "
            f"almost failed: #{n['dice']}. You suspect #{n['priya']} knows more about the Ghost Chorus signal "
            "than she admits.</p>",
        ),
        "rin": (
            f"<p>Head of security at Zenith Dynamics, secretly feeding intel to the Undercroft through #{n['silas']}.</p>",
            f"<p>Your loyalty to #{n['kade']} is genuine, but the Undercroft pays in chrome and clean idents "
            f"for what you overhear. #{n['silas']} is your handler. If #{n['kade']} ever finds out, it "
            "ends both your careers.</p>",
        ),
        "vex": (
            "<p>A Zenith netrunner obsessed with the deep archive layers nobody else dares to walk.</p>",
            f"<p>You are the ghost behind #{n['priya']}'s public face inside the Ghost Chorus. "
            f"You and #{n['kade']} grew up jacked into the same arcade net, and you dread what he "
            "will think if he ever learns what the Chorus wants from Zenith's core.</p>",
        ),
        "juno": (
            "<p>Boss of the Undercroft, blunt, practical, allergic to corporate badges.</p>",
            f"<p>You despise Zenith Dynamics' grip on the city's data lanes. #{n['dice']} runs grey-market "
            f"chips for you, and #{n['moth']} is the only Zenith contact you half-trust.</p>",
        ),
        "dice": (
            "<p>An Undercroft fixer with a foot in every faction's business.</p>",
            f"<p>You lent #{n['kade']} the clean capital that saved his launch, at a price he does not yet "
            f"know the full cost of. #{n['juno']} thinks you work only for the Undercroft; #{n['moth']} suspects otherwise.</p>",
        ),
        "moth": (
            "<p>A young Zenith runner, eager to prove her worth on the net.</p>",
            f"<p>You work for Zenith Dynamics but grew up in the Undercroft, and #{n['juno']} still treats "
            f"you like family. You do not yet know #{n['rin']}'s secret, but you are close to finding out.</p>",
        ),
        "silas": (
            "<p>An Undercroft fixer who trades in secrets as much as in black-clinic chrome.</p>",
            f"<p>You run #{n['rin']} as an asset inside Zenith Dynamics. You also quietly watch "
            f"#{n['priya']}, whose Ghost Chorus dealings could be worth even more than corporate secrets.</p>",
        ),
        "priya": (
            "<p>A Zenith liaison with a reputation for going dark at odd hours.</p>",
            f"<p>In public you are #{n['kade']}'s liaison. Inside the Ghost Chorus, you speak for it, "
            f"with #{n['vex']} as your unseen ghost. #{n['silas']} is starting to ask too many questions.</p>",
        ),
    }
    for key, (teaser, text) in updates.items():
        char = chars[key]
        char.teaser = teaser
        char.text = text
        char.save()

    return chars


def _build_factions(event: Event, chars: dict[str, Character]) -> dict[str, Faction]:
    zenith_dynamics = Faction.objects.create(
        event=event,
        name="Zenith Dynamics",
        typ=FactionType.PRIM,
        color="#0ea5b8",
        teaser="<p>The megacorp holding the city's data lanes, and its secrets, together.</p>",
    )
    zenith_dynamics.characters.set([chars["kade"], chars["rin"], chars["vex"], chars["moth"], chars["priya"]])

    undercroft = Faction.objects.create(
        event=event,
        name="The Undercroft",
        typ=FactionType.PRIM,
        color="#c2410c",
        teaser="<p>Fixers and runners who answer to no corp.</p>",
    )
    undercroft.characters.set([chars["juno"], chars["dice"], chars["silas"]])

    ghost_chorus = Faction.objects.create(
        event=event,
        name="The Ghost Chorus",
        typ=FactionType.SECRET,
        color="#1a0b2e",
        teaser="<p>A hidden emergent-AI cult with members inside Zenith Dynamics itself.</p>",
    )
    ghost_chorus.characters.set([chars["vex"], chars["priya"]])

    return {"zenith_dynamics": zenith_dynamics, "undercroft": undercroft, "ghost_chorus": ghost_chorus}


def _build_plots(event: Event, chars: dict[str, Character], progress: dict[str, ProgressStep]) -> dict[str, Plot]:
    debt_plot = Plot.objects.create(
        event=event,
        name="The Zenith Backdoor",
        teaser="<p>A debt owed by a Zenith executive to an Undercroft fixer threatens to come due.</p>",
        progress=progress["approved"],
    )
    debt_texts = {
        "kade": (
            f"<p>Three years ago you borrowed from #{chars['dice'].number} to save the launch. "
            "He has come to collect, and the price is a favor you cannot openly grant.</p>"
        ),
        "dice": (
            f"<p>You hold Exec #{chars['kade'].number}'s debt. Calling it in now, during the gala, "
            "would humiliate Zenith Dynamics in front of the whole corp.</p>"
        ),
        "juno": (
            f"<p>You do not know about the debt yet, but #{chars['dice'].number} has been oddly generous "
            "lately, and you want to know why.</p>"
        ),
    }
    for key, text in debt_texts.items():
        PlotCharacterRel.objects.create(plot=debt_plot, character=chars[key], text=text)

    circle_plot = Plot.objects.create(
        event=event,
        name="Signal from the Ghost Chorus",
        teaser="<p>A hidden emergent-AI cult is using Zenith Dynamics' name for its own ends.</p>",
        progress=progress["ready"],
    )
    circle_texts = {
        "vex": (
            f"<p>You speak for the Ghost Chorus from the deep net, mirrored in public by #{chars['priya'].number}. "
            "The Chorus wants a foothold in Zenith's core, and you must decide how far to let it in.</p>"
        ),
        "priya": (
            f"<p>You are the Chorus's public face, while #{chars['vex'].number} does the real work unseen. "
            f"#{chars['silas'].number} has started asking questions you cannot safely answer.</p>"
        ),
        "silas": (
            f"<p>You have noticed #{chars['priya'].number}'s odd absences and mean to find out what "
            "the Ghost Chorus wants from Zenith Dynamics, and what it would be worth to the Undercroft.</p>"
        ),
    }
    for key, text in circle_texts.items():
        PlotCharacterRel.objects.create(plot=circle_plot, character=chars[key], text=text)

    loyalty_plot = Plot.objects.create(
        event=event,
        name="Divided Loyalties",
        teaser="<p>An informant inside Zenith Dynamics feeds secrets to the Undercroft.</p>",
        progress=progress["draft"],
    )
    loyalty_texts = {
        "rin": (
            f"<p>You report to #{chars['silas'].number} in exchange for chrome the Undercroft pays too well to refuse. "
            f"If #{chars['kade'].number} ever learns of it, your place at his side is over.</p>"
        ),
        "silas": (
            f"<p>#{chars['rin'].number} is your best-placed asset inside Zenith Dynamics. Protecting her "
            "identity is now as important as the secrets she brings.</p>"
        ),
        "moth": (
            f"<p>You have started to notice #{chars['rin'].number} slipping away at odd hours, and you "
            "are not sure whether to speak up.</p>"
        ),
    }
    for key, text in loyalty_texts.items():
        PlotCharacterRel.objects.create(plot=loyalty_plot, character=chars[key], text=text)

    return {"debt_plot": debt_plot, "circle_plot": circle_plot, "loyalty_plot": loyalty_plot}


def _build_handouts(event: Event, plots: dict[str, Plot], progress: dict[str, ProgressStep]) -> None:
    Handout.objects.create(
        event=event,
        name="Zenith Ledger Fragment",
        text=(
            f"<p>A recovered ledger fragment recording a loan from Dice Okafor to Zenith Dynamics, "
            f"tied to the '{plots['debt_plot'].name}' plot. The final entry is corrupted, "
            "but the sum is unmistakable.</p>"
        ),
        progress=progress["approved"],
    )
    Handout.objects.create(
        event=event,
        name="Ghost Chorus Cipher Key",
        text=(
            f"<p>A hand-etched cipher key, evidence for the '{plots['circle_plot'].name}' plot. "
            "Anyone who decodes it will know the Ghost Chorus has been here.</p>"
        ),
        progress=progress["ready"],
    )
    Handout.objects.create(
        event=event,
        name="Intercepted Comm Log",
        text=(
            f"<p>An unsigned comm log passing along Zenith Dynamics gossip, relevant to the "
            f"'{plots['loyalty_plot'].name}' plot. The voiceprint looks familiar.</p>"
        ),
        progress=progress["draft"],
    )


def _build_relationships(event: Event, chars: dict[str, Character]) -> None:  # noqa: ARG001
    edges = [
        ("kade", "rin", "Your most trusted head of security, though lately she seems distracted."),
        ("kade", "dice", "The fixer who saved your launch, and now holds your debt."),
        ("kade", "priya", "Your liaison. You have always sensed she hides something."),
        ("rin", "kade", "Your boss, and the man you are betraying one report at a time."),
        ("rin", "silas", "Your handler in the Undercroft. He pays well and asks little."),
        ("vex", "priya", "Your public ghost in the Chorus. She carries the risk you cannot."),
        ("vex", "kade", "A childhood friend who must never learn what you have become."),
        ("juno", "dice", "Your best runner, and lately your most secretive one."),
        ("juno", "moth", "A Zenith contact who still feels like family to you."),
        ("dice", "kade", "A debt is owed, and debts are meant to be collected."),
        ("dice", "moth", "She is starting to notice too much of your business."),
        ("moth", "rin", "Something about her is off, and you mean to find out what."),
        ("silas", "priya", "Her absences are too regular to be innocent."),
        ("priya", "vex", "The one who does the real work of the Chorus, unseen."),
    ]
    for source_key, target_key, text in edges:
        relationship, created = Relationship.objects.get_or_create(
            source=chars[source_key],
            target=chars[target_key],
            defaults={"text": f"<p>{text}</p>"},
        )
        if not created:
            relationship.auto = False
            relationship.text = f"<p>{text}</p>"
            relationship.save()


def _build_registrations(event: Event, association: Association, chars: dict[str, Character]) -> None:
    run = event.runs.first()
    ticket = event.tickets.get(tier=TicketTier.STANDARD)
    players = [
        ("demo-writing-player1", "Alice", "Stone", chars["kade"]),
        ("demo-writing-player2", "Ben", "Voss", chars["rin"]),
        ("demo-writing-player3", "Clara", "Wynn", chars["vex"]),
        ("demo-writing-player4", "Dario", "Kell", chars["juno"]),
        ("demo-writing-player5", "Eva", "Marsh", chars["dice"]),
        ("demo-writing-player6", "Finn", "Osei", chars["moth"]),
        ("demo-writing-player7", "Grace", "Lund", chars["silas"]),
        ("demo-writing-player8", "Hugo", "Reyes", chars["priya"]),
    ]
    for username, name, surname, char in players:
        member = _make_member(username, name, surname, association)
        registration = Registration.objects.create(run=run, member=member, ticket=ticket)
        RegistrationCharacterRel.objects.create(registration=registration, character=char)


def _build_demo_type_and_hints(association: Association) -> LarpManagerDemoType:
    demo_type = LarpManagerDemoType.objects.create(
        name="Story Writing",
        slug=DEMO_TYPE_SLUG,
        descr=(
            "Characters, plots with per-character text, factions, relationships, handouts, "
            "editorial progress and PDF sheets."
        ),
        template_association=association,
        allowed_sidebar="orga_characters,orga_plots,orga_factions,orga_handouts,orga_progress_steps,"
        "faction,print_pdf,user_character",
    )

    hints = [
        ("writing-demo-event", "event", "Welcome to Neon Gala", "<p>Start by exploring the event page.</p>"),
        ("writing-demo-register", "register", "Sign up", "<p>Register for the event to get a character.</p>"),
        (
            "writing-demo-gallery",
            "gallery",
            "Browse the cast",
            "<p>This is the full cast of characters, organized by faction.</p>",
        ),
        (
            "writing-demo-character",
            "character",
            "Open a character sheet",
            (
                "<p>Every sheet has a public presentation and a private text. Notice the #number "
                "references: LarpManager turns them into links to the referenced character automatically.</p>"
            ),
        ),
        (
            "writing-demo-plot",
            "orga_plots_view",
            "One plot, many voices",
            (
                "<p>A plot ties several characters together, but each one gets their own private text: "
                "the same story, seen from different angles.</p>"
            ),
        ),
        (
            "writing-demo-factions",
            "orga_factions",
            "The faction grid",
            "<p>Factions can be public, transversal, or secret, like the Ghost Chorus hidden here.</p>",
        ),
        (
            "writing-demo-relationships",
            "character_relationships",
            "The relationship map",
            "<p>Each character carries a web of relationships to the others, visible from their sheet.</p>",
        ),
        (
            "writing-demo-pdf",
            "character_pdf_sheet",
            "Generate a character PDF",
            "<p>Every character sheet, plot text and relationship included, can be exported to a print-ready PDF.</p>",
        ),
    ]
    for key, view_name, title, content in hints:
        LarpManagerDemoHint.objects.get_or_create(
            key=key,
            defaults={"demo_type": demo_type, "view_name": view_name, "title": title, "content": content},
        )

    return demo_type


def build_writing_demo() -> LarpManagerDemoType:
    """Create (or fetch) the template association/event for the Story Writing demo."""
    existing = LarpManagerDemoType.objects.filter(slug=DEMO_TYPE_SLUG).first()
    if existing:
        return existing

    association = Association.objects.create(slug=ASSOCIATION_SLUG, name="Story Writing Demo")
    event = Event.objects.create(
        association=association,
        name="The Neon Gala",
        slug=EVENT_SLUG,
        tagline="One night, one gala, and secrets enough to burn the city down.",
        description=(
            "<p>Zenith Dynamics is throwing its annual gala, and every faction in the city has "
            "a reason to be there. An executive with a debt he cannot repay, a security chief "
            "feeding secrets to the Undercroft, and a hidden cult wearing Zenith's own colors: "
            "eight characters, three interlocking plots, and a faction map with more going on "
            "under the surface than above it.</p>"
        ),
    )
    run = event.runs.first()
    run.start = datetime.datetime.now(tz=UTC).date() + datetime.timedelta(days=60)
    run.end = run.start + datetime.timedelta(days=2)
    run.save()
    _enable_features(
        event,
        ["character", "user_character", "plot", "faction", "relationships", "handout", "progress", "print_pdf"],
    )

    progress = _build_progress_steps(event)
    chars = _build_characters(event, progress)
    _build_factions(event, chars)
    plots = _build_plots(event, chars, progress)
    _build_handouts(event, plots, progress)
    _build_relationships(event, chars)
    _build_registrations(event, association, chars)

    return _build_demo_type_and_hints(association)
