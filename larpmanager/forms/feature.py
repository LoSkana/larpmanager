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

from django import forms
from django.db.models import Q
from django.utils.html import format_html_join
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import save_single_config
from larpmanager.forms.base import MyForm
from larpmanager.models.base import Feature, FeatureModule

if TYPE_CHECKING:
    from larpmanager.models.association import Association
    from larpmanager.models.event import Event


class FeatureCheckboxWidget(forms.CheckboxSelectMultiple):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with optional feature help text."""
        # Extract and store feature help text from kwargs
        self.feature_help = kwargs.pop("help_text", {})
        super().__init__(*args, **kwargs)

    def render(
        self, name: str, value: list[str] | None, attrs: dict[str, str] | None = None, renderer: Any = None
    ) -> str:  # noqa: ARG002
        """Render feature checkboxes with tooltips and help links.

        Generates HTML for a set of feature checkboxes, each with an associated tooltip
        containing help text and a clickable icon that opens a tutorial.

        Args:
            name : str
                Field name for the HTML input elements
            value : list[str] | None
                List of selected feature values, None if no selection
            attrs : dict[str, str] | None, optional
                HTML attributes dictionary for the input elements
            renderer : optional
                Form renderer, currently unused

        Returns:
            str
                HTML string containing feature checkboxes with tooltips and help icons

        """
        value = value or []

        # Get localized text for help tooltip
        know_more = _("click on the icon to open the tutorial")

        # Build list of checkbox elements as tuples for format_html_join
        checkbox_elements = []
        for i, (option_value, option_label) in enumerate(self.choices):
            # Create unique checkbox ID and determine checked state
            checkbox_id = f"{attrs.get('id', name)}_{i}"
            checked = "checked" if str(option_value) in value else ""

            # Get help text for this feature
            help_text = self.feature_help.get(option_value, "")

            # Add tuple with all the data needed for this checkbox
            checkbox_elements.append(
                (
                    help_text,
                    know_more,
                    name,
                    option_value,
                    checkbox_id,
                    checked,
                    checkbox_id,
                    option_label,
                    option_value,
                ),
            )

        # Use format_html_join to safely generate the HTML
        return format_html_join(
            "\n",
            '<div class="feature_checkbox lm_tooltip"><span class="hide lm_tooltiptext">{} ({})</span><input type="checkbox" name="{}" value="{}" id="{}" {}> <label for="{}">{}</label> <a href="#" feat="{}"><i class="fas fa-question-circle"></i></a></div>',
            checkbox_elements,
        )


class FeatureForm(MyForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and set cancellation prevention flag."""
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def _init_features(self, *, is_association: bool) -> None:
        """Initialize feature selection fields organized by modules.

        Args:
            is_association: If True, initialize association-level features;
                                 if False, initialize event-level features

        Side effects:
            Adds feature selection fields to the form organized by modules
            Sets initial values based on current feature assignments

        """
        selected_feature_ids = None
        if self.instance.pk:
            selected_feature_ids = [str(v) for v in self.instance.features.values_list("pk", flat=True)]

        feature_modules = FeatureModule.objects.exclude(order=0).order_by("order")
        if is_association:
            feature_modules = feature_modules.filter(
                Q(nationality__isnull=True) | Q(nationality=self.instance.nationality),
            )
        for feature_module in feature_modules:
            module_features = feature_module.features.filter(
                overall=is_association,
                placeholder=False,
                hidden=False,
            ).order_by("order")
            feature_choices = [(str(feature.id), _(feature.name)) for feature in module_features]
            feature_help_texts = {str(feature.id): _(feature.descr) for feature in module_features}
            if not feature_choices:
                continue
            field_label = _(feature_module.name)
            if feature_module.icon:
                field_label = f"<i class='fa-solid fa-{feature_module.icon}'></i> {field_label}"
            self.fields[f"mod_{feature_module.id}"] = forms.MultipleChoiceField(
                choices=feature_choices,
                widget=FeatureCheckboxWidget(help_text=feature_help_texts),
                label=field_label,
                required=False,
            )
            if selected_feature_ids:
                self.initial[f"mod_{feature_module.id}"] = selected_feature_ids

    def _save_features(self, instance: Association | Event) -> None:
        """Save selected features to the instance.

        Args:
            instance: Model instance to save features to

        Side effects:
            Clears existing features and sets new ones based on form data
            Sets self.added_features with newly added feature IDs

        """
        old_features = set(instance.features.values_list("id", flat=True))
        instance.features.clear()

        features_id = []
        for module_id in FeatureModule.objects.values_list("pk", flat=True):
            key = f"mod_{module_id}"
            if key not in self.cleaned_data:
                continue
            features_id.extend([int(v) for v in self.cleaned_data[key]])

        instance.features.set(features_id)
        instance.save()

        new_features = set(features_id)
        self.added_features = new_features - old_features


class QuickSetupForm(MyForm):
    setup = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the form and prevent cancellation."""
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def init_fields(self, features: list[str]) -> None:
        """Initialize form fields for quick setup configuration.

        Args:
            features: List of currently enabled feature slugs

        Side effects:
            Creates boolean fields for each setup option
            Sets initial values based on current configuration

        """
        # for each value in self.setup, init a field
        for config_key, setup_element in self.setup.items():
            (is_feature_flag, field_label, field_help_text) = setup_element
            self.fields[config_key] = forms.BooleanField(
                required=False,
                label=field_label,
                help_text=field_help_text + "?",
            )
            initial_value = (
                config_key in features if is_feature_flag else self.instance.get_config(config_key, default_value=False)
            )
            self.initial[config_key] = initial_value

    def save(self, commit: bool = True) -> Association:  # noqa: FBT001, FBT002
        """Save form data and update feature assignments and configurations.

        Processes form data to handle both feature flags and configuration settings.
        Features are managed through many-to-many relationships, while configurations
        are stored as individual config entries.

        Args:
            commit: Whether to save the instance to the database. Defaults to True.

        Returns:
            The saved Association instance with updated features and configurations.

        Note:
            This method performs database operations even when commit=False for
            feature assignments and configuration updates.

        """
        # Save the base instance first
        instance = super().save(commit=commit)

        # Process form fields to separate features from configurations
        features = {}
        for key, element in self.setup.items():
            (is_feature, _label, _help_text) = element
            checked = self.cleaned_data[key]

            # Route to appropriate handler based on field type
            if is_feature:
                features[key] = checked
            else:
                # Save configuration value immediately
                save_single_config(self.instance, key, checked)

        # Bulk fetch feature IDs to minimize database queries
        features_ids_map = dict(Feature.objects.filter(slug__in=features.keys()).values_list("slug", "id"))

        # Update feature assignments based on form data
        for slug, checked in features.items():
            feature_id = features_ids_map[slug]
            if checked:
                # Add feature to association
                self.instance.features.add(feature_id)
            else:
                # Remove feature from association
                self.instance.features.remove(feature_id)

        # Final save to persist any remaining changes
        instance.save()

        return instance
