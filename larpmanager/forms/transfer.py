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

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.utils import CampaignS2Widget
from larpmanager.models.event import Event, Run
from larpmanager.models.registration import Registration


class RegistrationTransferForm(forms.Form):
    """Form for selecting registration and target for transfer."""

    registration_id = forms.ModelChoiceField(
        queryset=Registration.objects.none(),
        label=_("Registration to transfer"),
        required=True,
        help_text=_("Select the registration you want to transfer"),
    )

    target_run_id = forms.ModelChoiceField(
        queryset=Run.objects.none(),
        label=_("Target session (same event)"),
        required=False,
        help_text=_("Select a session from the same event"),
    )

    target_event_id = forms.ModelChoiceField(
        queryset=Event.objects.none(),
        label=_("Target event (different event)"),
        required=False,
        widget=CampaignS2Widget(),
        help_text=_("Or select a different event"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with context data.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments including:
                - run: Current run instance
                - event: Current event instance
                - association_id: Association ID for filtering

        """
        run = kwargs.pop("run", None)
        event = kwargs.pop("event", None)
        association_id = kwargs.pop("association_id", None)

        super().__init__(*args, **kwargs)

        # Set up registration queryset
        if run:
            self.fields["registration_id"].queryset = (
                Registration.objects.filter(run=run, cancellation_date__isnull=True)
                .select_related("member", "ticket")
                .order_by("member__name", "member__surname")
            )

        # Set up target run queryset (same event, different runs)
        if event:
            self.fields["target_run_id"].queryset = (
                Run.objects.filter(event=event).exclude(id=run.id).order_by("number")
            )

        # Set up target event queryset (different events in same association)
        if association_id:
            self.fields["target_event_id"].queryset = (
                Event.objects.filter(assoc_id=association_id).exclude(id=event.id).order_by("-start")
            )
            # Configure the CampaignS2Widget
            self.fields["target_event_id"].widget.set_association_id(association_id)
            self.fields["target_event_id"].widget.set_exclude(event.id)

    def clean(self) -> dict[str, Any]:
        """Validate that either target_run or target_event is selected.

        Returns:
            dict: Cleaned form data

        Raises:
            ValidationError: If neither or both targets are selected

        """
        cleaned_data = super().clean()
        target_run = cleaned_data.get("target_run_id")
        target_event = cleaned_data.get("target_event_id")

        if not target_run and not target_event:
            raise forms.ValidationError(_("Please select either a target session or a target event"))

        if target_run and target_event:
            raise forms.ValidationError(_("Please select only one target (either session or event, not both)"))

        return cleaned_data
