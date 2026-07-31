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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.config import get_event_config
from larpmanager.cache.writing import get_writing_element_fields
from larpmanager.forms.utils import GuildInviteS2Widget
from larpmanager.forms.writing import GuildForm
from larpmanager.mail.base import my_send_mail
from larpmanager.models.association import hdr
from larpmanager.models.form import QuestionApplicable
from larpmanager.models.writing import Character, Guild, GuildMembership, GuildMembershipStatus, GuildRole
from larpmanager.utils.core.base import get_event_context
from larpmanager.utils.users.registration import get_player_characters


def _get_my_character_ids(context: dict) -> list[int]:
    """Return the ids of the current player's characters in this event."""
    return list(get_player_characters(context["member"], context["event"]).values_list("id", flat=True))


def _get_my_membership(
    context: dict, guild: Guild, my_character_ids: list[int] | None = None
) -> GuildMembership | None:
    """Return the current player's membership on this guild, for any of their characters.

    Prefers an ACCEPTED membership over a pending INVITED one when both exist.
    """
    if my_character_ids is None:
        my_character_ids = _get_my_character_ids(context)
    if not my_character_ids:
        return None
    base = GuildMembership.objects.filter(guild=guild, character_id__in=my_character_ids).select_related("character")
    return base.filter(status=GuildMembershipStatus.ACCEPTED).first() or base.first()


def _get_my_admin_membership(
    context: dict, guild: Guild, my_character_ids: list[int] | None = None
) -> GuildMembership | None:
    """Return the current player's ACCEPTED, ADMIN membership on this guild, if any."""
    if my_character_ids is None:
        my_character_ids = _get_my_character_ids(context)
    if not my_character_ids:
        return None
    return GuildMembership.objects.filter(
        guild=guild,
        character_id__in=my_character_ids,
        role=GuildRole.ADMIN,
        status=GuildMembershipStatus.ACCEPTED,
    ).first()


def _check_admin(context: dict, guild: Guild) -> None:
    """Raise Http404 if the current player is not an accepted admin of the guild."""
    if not _get_my_admin_membership(context, guild):
        msg = "Not a guild admin"
        raise Http404(msg)


def _guild_max_number(context: dict) -> int:
    return get_event_config(context["event"].id, "guild_max_number", default_value=0, context=context)


def _guild_max_members(context: dict) -> int:
    return get_event_config(context["event"].id, "guild_max_members", default_value=0, context=context)


@login_required
def guilds(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Render the guild list page for an event run."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    guild_list = list(
        Guild.objects.filter(event=context["event"]).prefetch_related("memberships__character").order_by("number"),
    )
    for guild_obj in guild_list:
        guild_obj.accepted_members = [
            m.character for m in guild_obj.memberships.all() if m.status == GuildMembershipStatus.ACCEPTED
        ]
    context["list"] = guild_list

    max_number = _guild_max_number(context)
    context["can_create_guild"] = bool(get_player_characters(context["member"], context["event"]).exists()) and (
        max_number <= 0 or len(guild_list) < max_number
    )

    return render(request, "larpmanager/event/guilds.html", context)


@login_required
def guild(request: HttpRequest, event_slug: str, guild_uuid: str) -> HttpResponse:
    """Display detail page for a specific guild, including membership management for admins."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    guild_obj = get_object_or_404(Guild, event=context["event"], uuid=guild_uuid)
    context["guild"] = guild_obj

    get_event_cache_all(context)

    context["memberships"] = (
        GuildMembership.objects.filter(guild=guild_obj, status=GuildMembershipStatus.ACCEPTED)
        .select_related("character")
        .order_by("character__number")
    )
    for membership in context["memberships"]:
        membership.char = context["chars"].get(membership.character.number, {})

    my_character_ids = _get_my_character_ids(context)
    context["my_membership"] = _get_my_membership(context, guild_obj, my_character_ids)
    context["my_admin_membership"] = _get_my_admin_membership(context, guild_obj, my_character_ids)

    context["fields"] = get_writing_element_fields(
        context,
        "guild",
        QuestionApplicable.GUILD,
        guild_obj.id,
        only_visible=True,
    )

    if context["my_admin_membership"]:
        widget = GuildInviteS2Widget(attrs={"id": "guild-invite-select"})
        widget.set_event(context["event"])
        widget.set_guild(guild_obj)
        context["guild_invite_widget"] = widget.render(name="character_uuid", value="")
        context["guild_invite_media"] = widget.media

    return render(request, "larpmanager/event/guild.html", context)


@login_required
def guild_invites(request: HttpRequest, event_slug: str) -> HttpResponse:
    """List pending guild invites for any of the current player's characters."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    my_character_ids = list(get_player_characters(context["member"], context["event"]).values_list("id", flat=True))
    context["invites"] = (
        GuildMembership.objects.filter(
            character_id__in=my_character_ids,
            status=GuildMembershipStatus.INVITED,
        )
        .select_related("guild", "character")
        .order_by("guild__number")
    )

    return render(request, "larpmanager/event/guild_invites.html", context)


@login_required
def guild_create(request: HttpRequest, event_slug: str) -> HttpResponse:
    """Create a new guild; the creating character becomes its first admin."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    my_characters = get_player_characters(context["member"], context["event"])
    if not my_characters.exists():
        messages.error(request, _("You need a character to create a guild"))
        return redirect("guilds", event_slug=event_slug)

    max_number = _guild_max_number(context)
    if max_number > 0 and Guild.objects.filter(event=context["event"]).count() >= max_number:
        messages.error(request, _("The maximum number of guilds for this event has been reached"))
        return redirect("guilds", event_slug=event_slug)

    context["my_characters"] = my_characters

    if request.method == "POST":
        form = GuildForm(request.POST, request.FILES, instance=None, context=context)
        founder_uuid = request.POST.get("founder_character")
        founder = my_characters.filter(uuid=founder_uuid).first()
        if not founder:
            form.add_error(None, _("Select a valid character"))
        elif form.is_valid():
            new_guild = form.save()
            GuildMembership.objects.create(
                guild=new_guild,
                character=founder,
                role=GuildRole.ADMIN,
                status=GuildMembershipStatus.ACCEPTED,
            )
            messages.success(request, _("Guild created!"))
            return redirect("guild", event_slug=event_slug, guild_uuid=new_guild.uuid)
    else:
        form = GuildForm(instance=None, context=context)

    context["form"] = form
    return render(request, "larpmanager/event/guild_edit.html", context)


@login_required
def guild_edit(request: HttpRequest, event_slug: str, guild_uuid: str) -> HttpResponse:
    """Edit a guild's own text/cover/custom fields, restricted to guild admins."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    guild_obj = get_object_or_404(Guild, event=context["event"], uuid=guild_uuid)
    _check_admin(context, guild_obj)

    if request.method == "POST":
        form = GuildForm(request.POST, request.FILES, instance=guild_obj, context=context)
        if form.is_valid():
            form.save()
            messages.success(request, _("Guild updated!"))
            return redirect("guild", event_slug=event_slug, guild_uuid=guild_obj.uuid)
    else:
        form = GuildForm(instance=guild_obj, context=context)

    context["guild"] = guild_obj
    context["form"] = form
    return render(request, "larpmanager/event/guild_edit.html", context)


@login_required
@require_POST
def guild_invite(request: HttpRequest, event_slug: str, guild_uuid: str) -> HttpResponse:
    """Invite a character to the guild, restricted to guild admins."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    guild_obj = get_object_or_404(Guild, event=context["event"], uuid=guild_uuid)
    _check_admin(context, guild_obj)

    target_uuid = request.POST.get("character_uuid")
    target = Character.objects.filter(event=context["event"], uuid=target_uuid).first()

    if not target:
        messages.error(request, _("Character not found"))
    elif GuildMembership.objects.filter(guild=guild_obj, character=target).exists():
        messages.error(request, _("This character is already a member or has a pending invite"))
    else:
        GuildMembership.objects.create(
            guild=guild_obj,
            character=target,
            role=GuildRole.MEMBER,
            status=GuildMembershipStatus.INVITED,
        )
        if target.player:
            subject = f"{hdr(context['event'])} {_('Guild invite')} - {guild_obj.name}"
            body = _("You have been invited to join the guild %(guild)s with your character %(character)s") % {
                "guild": guild_obj.name,
                "character": target.name,
            }
            body += "<br/><br/>" + reverse("guild_invites", args=[context["event"].slug])
            my_send_mail(subject, body, target.player, context["event"])
        messages.success(request, _("Invite sent!"))

    return redirect("guild", event_slug=event_slug, guild_uuid=guild_obj.uuid)


@login_required
@require_POST
def guild_invite_accept(request: HttpRequest, event_slug: str, guild_uuid: str, character_uuid: str) -> HttpResponse:
    """Accept a pending guild invite for one of the player's own characters."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    guild_obj = get_object_or_404(Guild, event=context["event"], uuid=guild_uuid)
    character = get_object_or_404(Character, event=context["event"], uuid=character_uuid, player=context["member"])

    membership = get_object_or_404(
        GuildMembership,
        guild=guild_obj,
        character=character,
        status=GuildMembershipStatus.INVITED,
    )

    max_members = _guild_max_members(context)
    accepted_count = GuildMembership.objects.filter(guild=guild_obj, status=GuildMembershipStatus.ACCEPTED).count()
    if max_members > 0 and accepted_count >= max_members:
        messages.error(request, _("This guild has reached its maximum number of members"))
    else:
        membership.status = GuildMembershipStatus.ACCEPTED
        membership.save()
        messages.success(request, _("You joined the guild!"))

    return redirect("guild_invites", event_slug=event_slug)


@login_required
@require_POST
def guild_invite_decline(request: HttpRequest, event_slug: str, guild_uuid: str, character_uuid: str) -> HttpResponse:
    """Decline a pending guild invite for one of the player's own characters."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    guild_obj = get_object_or_404(Guild, event=context["event"], uuid=guild_uuid)
    character = get_object_or_404(Character, event=context["event"], uuid=character_uuid, player=context["member"])

    GuildMembership.objects.filter(
        guild=guild_obj,
        character=character,
        status=GuildMembershipStatus.INVITED,
    ).delete()

    messages.success(request, _("Invite declined"))
    return redirect("guild_invites", event_slug=event_slug)


@login_required
@require_POST
def guild_kick(request: HttpRequest, event_slug: str, guild_uuid: str, character_uuid: str) -> HttpResponse:
    """Kick a member out of the guild, restricted to guild admins."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    guild_obj = get_object_or_404(Guild, event=context["event"], uuid=guild_uuid)
    _check_admin(context, guild_obj)

    membership = get_object_or_404(
        GuildMembership,
        guild=guild_obj,
        character__uuid=character_uuid,
        status=GuildMembershipStatus.ACCEPTED,
    )

    if membership.role == GuildRole.ADMIN:
        other_admins = GuildMembership.objects.filter(
            guild=guild_obj,
            role=GuildRole.ADMIN,
            status=GuildMembershipStatus.ACCEPTED,
        ).exclude(pk=membership.pk)
        if not other_admins.exists():
            messages.error(request, _("Cannot kick the last admin of the guild"))
            return redirect("guild", event_slug=event_slug, guild_uuid=guild_obj.uuid)

    character = membership.character
    membership.delete()

    if character.player:
        subject = f"{hdr(context['event'])} {_('Removed from guild')} - {guild_obj.name}"
        body = _("Your character %(character)s has been removed from the guild %(guild)s") % {
            "character": character.name,
            "guild": guild_obj.name,
        }
        my_send_mail(subject, body, character.player, context["event"])

    messages.success(request, _("Member removed!"))
    return redirect("guild", event_slug=event_slug, guild_uuid=guild_obj.uuid)


@login_required
@require_POST
def guild_leave(request: HttpRequest, event_slug: str, guild_uuid: str) -> HttpResponse:
    """Leave a guild with one of the player's own characters."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    guild_obj = get_object_or_404(Guild, event=context["event"], uuid=guild_uuid)
    character_uuid = request.POST.get("character_uuid")
    character = get_object_or_404(Character, event=context["event"], uuid=character_uuid, player=context["member"])

    membership = get_object_or_404(
        GuildMembership,
        guild=guild_obj,
        character=character,
        status=GuildMembershipStatus.ACCEPTED,
    )

    if membership.role == GuildRole.ADMIN:
        other_admins = GuildMembership.objects.filter(
            guild=guild_obj,
            role=GuildRole.ADMIN,
            status=GuildMembershipStatus.ACCEPTED,
        ).exclude(pk=membership.pk)
        if not other_admins.exists():
            messages.error(request, _("You are the last admin: promote another member before leaving"))
            return redirect("guild", event_slug=event_slug, guild_uuid=guild_obj.uuid)

    membership.delete()
    messages.success(request, _("You left the guild"))
    return redirect("guilds", event_slug=event_slug)


@login_required
@require_POST
def guild_promote(request: HttpRequest, event_slug: str, guild_uuid: str, character_uuid: str) -> HttpResponse:
    """Promote a member to admin, restricted to guild admins."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    guild_obj = get_object_or_404(Guild, event=context["event"], uuid=guild_uuid)
    _check_admin(context, guild_obj)

    membership = get_object_or_404(
        GuildMembership,
        guild=guild_obj,
        character__uuid=character_uuid,
        status=GuildMembershipStatus.ACCEPTED,
    )
    membership.role = GuildRole.ADMIN
    membership.save()
    messages.success(request, _("Member promoted to admin!"))
    return redirect("guild", event_slug=event_slug, guild_uuid=guild_obj.uuid)


@login_required
@require_POST
def guild_demote(request: HttpRequest, event_slug: str, guild_uuid: str, character_uuid: str) -> HttpResponse:
    """Demote an admin to regular member, restricted to guild admins. Blocked if it would leave the guild admin-less."""
    context = get_event_context(request, event_slug, feature_slug="guild", include_status=True)

    guild_obj = get_object_or_404(Guild, event=context["event"], uuid=guild_uuid)
    _check_admin(context, guild_obj)

    membership = get_object_or_404(
        GuildMembership,
        guild=guild_obj,
        character__uuid=character_uuid,
        role=GuildRole.ADMIN,
        status=GuildMembershipStatus.ACCEPTED,
    )

    other_admins = GuildMembership.objects.filter(
        guild=guild_obj,
        role=GuildRole.ADMIN,
        status=GuildMembershipStatus.ACCEPTED,
    ).exclude(pk=membership.pk)
    if not other_admins.exists():
        messages.error(request, _("Cannot demote the last admin of the guild"))
    else:
        membership.role = GuildRole.MEMBER
        membership.save()
        messages.success(request, _("Member demoted!"))

    return redirect("guild", event_slug=event_slug, guild_uuid=guild_obj.uuid)
