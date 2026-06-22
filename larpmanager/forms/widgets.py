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

from typing import Any

from django import forms
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _


def _inject_description(option: dict, label: Any, desc: str) -> None:
    """Inject description HTML into option label; no-op when desc is empty."""
    if not desc:
        return
    option["label"] = format_html(
        '<span class="opt-name">{}</span><small class="opt-desc">{}</small>',
        label,
        desc,
    )


def _inject_card(option: dict, label: Any, desc: str, meta: dict) -> None:
    """Render option as a card with structured name, price, availability, and description."""
    name = meta.get("name") or label
    price = meta.get("price")
    available = meta.get("available")

    price_html = format_html('<span class="opt-card-price">{}</span>', price) if price else mark_safe("")
    desc_html = format_html('<div class="opt-card-desc">{}</div>', desc) if desc else mark_safe("")
    avail_html = (
        format_html('<div class="opt-card-avail">{} {}</div>', available, _("available"))
        if available is not None
        else mark_safe("")
    )

    option["label"] = format_html(
        '<div class="opt-card-body">'
        '<div class="opt-card-header"><span class="opt-card-name">{}</span>{}</div>'
        "{}{}"
        "</div>",
        name,
        price_html,
        desc_html,
        avail_html,
    )


class _DescriptionOptionsMixin:
    """Mixin that injects per-option description and card layout into each option label."""

    def __init__(
        self,
        *args: Any,
        descriptions: dict | None = None,
        metadata: dict | None = None,
        **kwargs: Any,
    ) -> None:
        """Prepare widget metadata."""
        super().__init__(*args, **kwargs)
        self.descriptions = descriptions or {}
        self.metadata = metadata or {}

    def create_option(
        self,
        name: str,
        value: Any,
        label: Any,
        selected: bool,  # noqa: FBT001
        index: int,
        **kwargs: Any,
    ) -> dict:
        option = super().create_option(name, value, label, selected, index, **kwargs)
        meta = self.metadata.get(str(value))
        desc = self.descriptions.get(str(value), "")
        if meta:
            _inject_card(option, label, desc, meta)
        else:
            _inject_description(option, label, desc)
        return option


class DescriptionRadioSelect(_DescriptionOptionsMixin, forms.RadioSelect):
    """RadioSelect that shows option description below each option label."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Prepare RadioSelect metadata."""
        super().__init__(*args, **kwargs)
        self.attrs.setdefault("class", "")
        self.attrs["class"] = (self.attrs["class"] + " reg-radio-class").strip()


class DescriptionCheckboxSelectMultiple(_DescriptionOptionsMixin, forms.CheckboxSelectMultiple):
    """CheckboxSelectMultiple that shows option description below each option label."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Prepare CheckboxSelectMultiple metadata."""
        super().__init__(*args, **kwargs)
        self.attrs.setdefault("class", "")
        self.attrs["class"] = (self.attrs["class"] + " reg-checkbox-class").strip()
