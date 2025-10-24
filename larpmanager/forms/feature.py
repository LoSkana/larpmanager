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
from django.db.models import Q
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import save_single_config
from larpmanager.forms.base import MyForm
from larpmanager.models.association import Association
from larpmanager.models.base import Feature, FeatureModule


class FeatureCheckboxWidget(forms.CheckboxSelectMultiple):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with optional feature help text."""
        # Extract and store feature help text from kwargs
        self.feature_help = kwargs.pop("help_text", {})
        super().__init__(*args, **kwargs)

    def render(self, name: str, value: list[str] | None, attrs: dict[str, str] | None = None, renderer=None) -> str:
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
        output = []
        value = value or []

        # Get localized text for help tooltip
        know_more = _("click on the icon to open the tutorial")

        # Generate HTML for each feature option
        for i, (option_value, option_label) in enumerate(self.choices):
            # Create unique checkbox ID and determine checked state
            checkbox_id = f"{attrs.get('id', name)}_{i}"
            checked = "checked" if str(option_value) in value else ""

            # Build individual HTML components
            checkbox_html = f'<input type="checkbox" name="{name}" value="{option_value}" id="{checkbox_id}" {checked}>'
            label_html = f'<label for="{checkbox_id}">{option_label}</label>'
            link_html = f'<a href="#" feat="{option_value}"><i class="fas fa-question-circle"></i></a>'

            # Get help text for this feature and build tooltip
            help_text = self.feature_help.get(option_value, "")
            output.append(f"""
                <div class="feature_checkbox lm_tooltip">
                    <span class="hide lm_tooltiptext">{help_text} ({know_more})</span>
                    {checkbox_html} {label_html} {link_html}
                </div>
            """)

        return mark_safe("\n".join(output))


class FeatureForm(MyForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Initialize parent class and set cancellation prevention flag
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def _init_features(self, overall):
        """Initialize feature selection fields organized by modules.

        Args:
            overall: If True, initialize association-level features;
                    if False, initialize event-level features

        Side effects:
            Adds feature selection fields to the form organized by modules
            Sets initial values based on current feature assignments
        """
        init_features = None
        if self.instance.pk:
            init_features = [str(v) for v in self.instance.features.values_list("pk", flat=True)]

        modules = FeatureModule.objects.exclude(order=0).order_by("order")
        if overall:
            modules = modules.filter(Q(nationality__isnull=True) | Q(nationality=self.instance.nationality))
        for module in modules:
            features = module.features.filter(overall=overall, placeholder=False, hidden=False).order_by("order")
            choices = [(str(f.id), _(f.name)) for f in features]
            help_text = {str(f.id): _(f.descr) for f in features}
            if not choices:
                continue
            label = _(module.name)
            if module.icon:
                label = f"<i class='fa-solid fa-{module.icon}'></i> {label}"
            self.fields[f"mod_{module.id}"] = forms.MultipleChoiceField(
                choices=choices,
                widget=FeatureCheckboxWidget(help_text=help_text),
                label=label,
                required=False,
            )
            if init_features:
                self.initial[f"mod_{module.id}"] = init_features

    def _save_features(self, instance):
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
        # Initialize parent class and prevent cancellation
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def init_fields(self, features):
        """Initialize form fields for quick setup configuration.

        Args:
            features: List of currently enabled feature slugs

        Side effects:
            Creates boolean fields for each setup option
            Sets initial values based on current configuration
        """
        # for each value in self.setup, init a field
        for key, element in self.setup.items():
            (is_feature, label, help_text) = element
            self.fields[key] = forms.BooleanField(required=False, label=label, help_text=help_text + "?")
            if is_feature:
                init = key in features
            else:
                init = self.instance.get_config(key, False)
            self.initial[key] = init

    def save(self, commit: bool = True) -> Association:
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
