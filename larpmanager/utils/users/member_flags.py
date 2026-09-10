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

from django.db import transaction
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import get_association_config, reset_member_configs, save_single_config
from larpmanager.models.member import Member, MemberConfig, MemberFlagDef, Membership


def member_flags_active(association_id: int, context: dict | None = None) -> bool:
    """Return whether the member status flags pseudo-feature is active for the association."""
    return bool(get_association_config(association_id, "member_flags_active", context=context))


def get_association_flag_defs(association_id: int):  # noqa: ANN201
    """Return active flag definitions for an association, in display order."""
    return MemberFlagDef.objects.filter(association_id=association_id, deleted=None).order_by("order")


def get_member_flags_html(member: Member, association_id: int) -> str:
    """Build a read-only HTML snippet listing each active flag def and whether it's set for the member.

    Used by the popups shown in orga_registrations, orga_payments and exe_payments.
    """
    flag_defs = list(get_association_flag_defs(association_id))
    if not flag_defs:
        return ""

    values = get_member_flag_values(member, flag_defs)
    rows = []
    for flag_def in flag_defs:
        icon = '<i class="fa-solid fa-check"></i>' if values[flag_def.id] else ""
        rows.append(f"<tr><td>{escape(flag_def.name)}</td><td>{icon}</td></tr>")

    return f"<p><b>{_('Flags')}</b></p><table>{''.join(rows)}</table>"


def get_member_flag_values(member: Member, flag_defs: list[MemberFlagDef]) -> dict[int, bool]:
    """Return {flag_def_id: bool} for a single member, in one query."""
    config_names = {flag_def.config_name(): flag_def.id for flag_def in flag_defs}
    set_names = MemberConfig.objects.filter(
        member_id=member.id,
        name__in=config_names,
        deleted=None,
    ).values_list("name", flat=True)
    set_ids = {config_names[name] for name in set_names}
    return {flag_def.id: flag_def.id in set_ids for flag_def in flag_defs}


def set_member_flag(member: Member, flag_def: MemberFlagDef, *, active: bool) -> None:
    """Set or clear a single member status flag, stored as a MemberConfig row."""
    config_name = flag_def.config_name()
    with transaction.atomic():
        Member.objects.select_for_update().get(pk=member.pk)
        if active:
            save_single_config(member, config_name, "True")
        else:
            MemberConfig.objects.filter(member=member, name=config_name, deleted=None).delete()
            reset_member_configs(member.id)


def set_member_flags(member: Member, flag_defs: list[MemberFlagDef], active_by_flag_id: dict[int, bool]) -> None:
    """Set or clear a member's whole flag set in a single atomic operation."""
    with transaction.atomic():
        for flag_def in flag_defs:
            set_member_flag(member, flag_def, active=active_by_flag_id.get(flag_def.id, False))


def get_member_in_association(association_id: int, member_uuid: str) -> Member:
    """Return the member with the given uuid, only if they have a membership in this association.

    Raises Member.DoesNotExist otherwise, to prevent cross-association access to members via uuid.
    """
    try:
        return (
            Membership.objects.select_related("member")
            .get(
                association_id=association_id,
                member__uuid=member_uuid,
            )
            .member
        )
    except Membership.DoesNotExist as exc:
        raise Member.DoesNotExist from exc


def get_member_flags_eye_html(member_uuid: str, turl: str) -> str:
    """Build the read-only eye-icon link markup that opens the member status flags popup."""
    return (
        f" <a href='#' class='member_flags_eye' mid='{escape(member_uuid)}' turl='{escape(turl)}'>"
        "<i class='fas fa-eye'></i></a>"
    )
