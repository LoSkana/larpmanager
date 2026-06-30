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

from typing import TYPE_CHECKING, Any

from django.core.cache import cache
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from larpmanager.models.registration import Registration

if TYPE_CHECKING:
    from django.http import HttpRequest

_USER_NAV_CACHE_TIMEOUT = 3600 * 24


def _user_nav_cache_key(member_id: int) -> str:
    return f"user_nav_entries_{member_id}"


def _user_nav_profile_flags_cache_key(member_id: int) -> str:
    return f"user_nav_profile_flags_{member_id}"


def invalidate_user_nav_entries(member_id: int) -> None:
    """Invalidate list of registrations for the user."""
    cache.delete(_user_nav_cache_key(member_id))
    cache.delete(_user_nav_profile_flags_cache_key(member_id))


def _item(
    url: str,
    icon: str,
    label: Any,
    tooltip: Any,
    *,
    active: bool = False,
    target: str | None = None,
    download: bool = False,
    home: bool = False,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "url": url,
        "icon": icon,
        "label": label,
        "tooltip": tooltip,
        "active": active,
        "home": home,
    }
    if target:
        entry["target"] = target
    if download:
        entry["download"] = True
    return entry


def _add_registration_items(
    items: list[dict[str, Any]],
    slug: str,
    active: str,
    features: set[str],
    registration: Any,
    context: dict[str, Any],
) -> None:
    if registration:
        items.append(
            _item(
                reverse("register", args=[slug]),
                "fa-solid fa-pen-to-square",
                _("Registration"),
                str(_("Update here the registration options")) + "!",
                active=active == "register",
            )
        )
        if registration.tot_iscr:
            items.append(
                _item(
                    reverse("event_payments", args=[slug]),
                    "fa-solid fa-receipt",
                    _("Payments"),
                    str(_("View your payment details for this event")) + "!",
                    active=active == "event_payments",
                )
            )
        if getattr(registration, "character", None):
            items.append(
                _item(
                    reverse("character_your", args=[slug]),
                    "fa-solid fa-person",
                    _("Your character"),
                    str(_("Access your character")) + "!",
                    active=active == "char",
                )
            )
        if (
            "casting" in features
            and context.get("show_character")
            and registration.ticket
            and registration.ticket.tier != "w"
        ):
            items.append(
                _item(
                    reverse("casting", args=[slug]),
                    "fa-solid fa-masks-theater",
                    _("Casting"),
                    str(_("Select your preferences on the characters to play")) + "!",
                    active=active == "casting",
                )
            )
    else:
        items.append(
            _item(
                reverse("register", args=[slug]),
                "fa-solid fa-user-plus",
                _("Register"),
                str(_("Register to the event")),
                active=active == "register",
            )
        )


def _add_character_items(
    items: list[dict[str, Any]],
    slug: str,
    active: str,
    features: set[str],
) -> None:
    items.append(
        _item(
            reverse("gallery", args=[slug]),
            "fa-solid fa-images",
            _("Gallery"),
            str(_("View the list of characters and participants")) + "!",
            active=active == "gallery",
        )
    )
    items.append(
        _item(
            reverse("search", args=[slug]),
            "fa-solid fa-magnifying-glass",
            _("Search"),
            str(_("Filter or search the characters")) + "!",
            active=active == "search",
        )
    )
    if "ensemble" in features:
        items.append(
            _item(
                reverse("ensemble", args=[slug]),
                "fa-solid fa-people-group",
                _("Ensemble"),
                str(_("Learn all characters before the event")) + "!",
                active=active == "ensemble",
            )
        )


def _add_writing_items(
    items: list[dict[str, Any]],
    slug: str,
    active: str,
    features: set[str],
    context: dict[str, Any],
) -> None:
    show_addit = context.get("show_addit", {})
    if "workshop" in features and show_addit.get("workshop"):
        items.append(
            _item(
                reverse("workshops", args=[slug]),
                "fa-solid fa-hammer",
                _("Workshop"),
                str(_("Fill out the event prep questions")) + "!",
                active=active == "workshops",
            )
        )
    if "character" in features:
        _add_character_items(items, slug, active, features)
    if "faction" in features and context.get("show_faction") and context.get("has_visible_factions"):
        items.append(
            _item(
                reverse("factions", args=[slug]),
                "fa-solid fa-flag",
                _("Factions"),
                str(_("Discover the game factions")) + "!",
                active=active == "factions",
            )
        )
    if "questbuilder" in features and context.get("show_quest"):
        items.append(
            _item(
                reverse("quests", args=[slug]),
                "fa-solid fa-scroll",
                _("Quest"),
                str(_("Find out what quests are available")) + "!",
                active=active == "quests",
            )
        )


def _add_extra_items(
    items: list[dict[str, Any]],
    slug: str,
    features: set[str],
    context: dict[str, Any],
    registration: Any,
    run: Any,
) -> None:
    if "album" in features and run.albums.exists():
        items.append(
            _item(
                reverse("album", args=[slug]),
                "fa-solid fa-camera",
                _("Album"),
                str(_("View photos from the event")) + "!",
            )
        )
    if "gift" in features:
        items.append(
            _item(
                reverse("gift", args=[slug]),
                "fa-solid fa-gift",
                _("Gift"),
                str(_("Give a card to your friend")),
            )
        )
    for el in context.get("buttons", []):
        entry: dict[str, Any] = {"url": el[2], "label": el[0], "tooltip": el[1], "active": False}
        if el[3]:
            entry["icon"] = el[3]
        items.append(entry)
    if registration and "print_pdf" in features and context.get("show_character"):
        pdf_tooltip = str(_("Download the list of characters with their interpreters' profile images")) + "!"
        items.append(
            _item(
                reverse("portraits", args=[slug]),
                "fa-solid fa-id-badge",
                _("Portraits (PDF)"),
                pdf_tooltip,
                download=True,
            )
        )
        items.append(
            _item(
                reverse("profiles", args=[slug]),
                "fa-solid fa-address-card",
                _("Profiles (PDF)"),
                pdf_tooltip,
                download=True,
            )
        )


def _build_reg_nav_entries(member_id: int) -> list[dict[str, Any]]:
    regs = (
        Registration.objects.filter(
            member_id=member_id,
            cancellation_date__isnull=True,
            deleted__isnull=True,
        )
        .select_related("run__event__association")
        .order_by("-run__start")
    )

    entries = []
    for reg in regs:
        run = reg.run
        event = run.event
        slug = run.get_slug()
        entries.append(
            {
                "label": event.get_name(),
                "url": reverse("register", args=[slug]),
                "slug": slug,
                "assoc_name": event.association.name if event.association else "",
            }
        )
    return entries


def build_main_nav_items(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the main event navigation item list from view context."""
    run = context.get("run")
    if not run:
        return []

    items: list[dict[str, Any]] = []
    slug = run.get_slug()
    active = context.get("request_func_name", "")
    features = context.get("features", set())
    registration = context.get("registration")
    event = context.get("event")

    items.append(
        _item(
            reverse("event", args=[slug]),
            "fa-solid fa-calendar-days",
            _("Event"),
            str(_("Discover what this event is about")) + "!",
            active=active == "event",
        )
    )

    if event and event.website:
        items.append(
            _item(
                event.website,
                "fa-solid fa-globe",
                _("Website"),
                str(_("Browse the presentation website")) + "!",
                target="_blank",
            )
        )

    _add_registration_items(items, slug, active, features, registration, context)
    _add_writing_items(items, slug, active, features, context)
    _add_extra_items(items, slug, features, context, registration, run)

    return items


def build_profile_nav_items(request: HttpRequest) -> list[dict[str, Any]]:
    """Build profile navigation item list from request."""
    if not hasattr(request, "association"):
        return []

    features = request.association.get("features", set())
    active = request.resolver_match.url_name if request.resolver_match else ""

    items: list[dict[str, Any]] = [
        _item(reverse("profile"), "fa-solid fa-user", _("Profile"), "", active=active == "profile", home=False),
        _item(
            reverse("privacy"),
            "fa-solid fa-shield-halved",
            _("Privacy"),
            "",
            active=active == "privacy",
            home=False,
        ),
    ]

    if "membership" in features:
        items.append(
            _item(
                reverse("membership"),
                "fa-solid fa-id-card",
                _("Membership"),
                "",
                active=active == "membership",
                home=False,
            )
        )

    if "delegated_members" in features:
        items.append(
            _item(
                reverse("delegated"),
                "fa-solid fa-user-shield",
                _("Delegated users"),
                "",
                active=active == "delegated",
                home=False,
            )
        )

    items.append(
        _item(reverse("language"), "fa-solid fa-language", _("Language"), "", active=active == "language", home=False)
    )
    items.append(
        _item(reverse("security"), "fa-solid fa-lock", _("Security"), "", active=active == "security", home=False)
    )

    return items


def build_profile_home_nav_items(request: HttpRequest) -> list[dict[str, Any]]:
    """Build home shortcut navigation item list from request."""
    if not hasattr(request, "association"):
        return []

    features = request.association.get("features", set())
    active = request.resolver_match.url_name if request.resolver_match else ""

    member = getattr(getattr(request, "user", None), "member", None)
    has_registrations = False
    has_paid_registrations = False
    if member:
        flags_cache_key = _user_nav_profile_flags_cache_key(member.id)
        flags = cache.get(flags_cache_key)
        if flags is None:
            qs = Registration.objects.filter(member=member)
            flags = {
                "has_registrations": qs.exists(),
                "has_paid_registrations": qs.filter(tot_iscr__gt=0).exists(),
            }
            cache.set(flags_cache_key, flags, _USER_NAV_CACHE_TIMEOUT)
        has_registrations = flags["has_registrations"]
        has_paid_registrations = flags["has_paid_registrations"]

    items: list[dict[str, Any]] = []

    if request.association.get("user_characters_shortcut", False):
        items.append(
            _item(
                reverse("characters"),
                "fa-solid fa-users",
                _("Characters"),
                "",
                active=active == "characters",
                home=True,
            )
        )

    if has_registrations and request.association.get("user_registrations_shortcut", False):
        items.append(
            _item(
                reverse("registrations"),
                "fa-solid fa-list-check",
                _("Registrations"),
                "",
                active=active == "registrations",
                home=True,
            )
        )

    if has_registrations and "past_events" in features and request.association.get("calendar_past_events", False):
        items.append(
            _item(
                reverse("calendar_past"),
                "fa-solid fa-clock-rotate-left",
                _("Past events"),
                "",
                active=active == "calendar_past",
                home=True,
            )
        )

    if has_paid_registrations:
        items.append(
            _item(
                reverse("accounting"),
                "fa-solid fa-money-bill",
                _("Accounting"),
                "",
                active=active == "accounting",
                home=True,
            )
        )

    if "badge" in features:
        items.append(
            _item(reverse("badges"), "fa-solid fa-trophy", _("Badges"), "", active=active == "badges", home=True)
        )

    if "chat" in features:
        items.append(
            _item(reverse("messages"), "fa-solid fa-message", _("Messages"), "", active=active == "messages", home=True)
        )

    return items
