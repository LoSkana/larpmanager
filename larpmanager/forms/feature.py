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
from larpmanager.models.base import Feature, FeatureModule


class FeatureCheckboxWidget(forms.CheckboxSelectMultiple):
    def __init__(self, *args, **kwargs):
        self.feature_help = kwargs.pop("help_text", {})
        super().__init__(*args, **kwargs)

    def render(self, name: str, value: list[str] | None, attrs: dict[str, str] | None = None, renderer=None) -> str:
        """Render feature checkboxes with tooltips and help links.

        Generates HTML checkboxes for each feature choice with associated tooltips
        and help links. Each checkbox is wrapped in a tooltip container with
        feature-specific help text.

        Args:
            name: Field name for the HTML input elements
            value: List of selected feature values, can be None for no selection
            attrs: HTML attributes dictionary for customizing input attributes
            renderer: Form renderer instance (currently unused)

        Returns:
            Safe HTML string containing feature checkboxes with tooltips and help icons
        """
        output = []
        value = value or []

        # Get localized text for tooltip help message
        know_more = _("click on the icon to open the tutorial")

        # Iterate through each feature choice to create checkbox elements
        for i, (option_value, option_label) in enumerate(self.choices):
            # Generate unique checkbox ID using field name and index
            checkbox_id = f"{attrs.get('id', name)}_{i}"

            # Determine if checkbox should be checked based on current value
            checked = "checked" if str(option_value) in value else ""

            # Create HTML elements for checkbox, label, and help link
            checkbox_html = f'<input type="checkbox" name="{name}" value="{option_value}" id="{checkbox_id}" {checked}>'
            label_html = f'<label for="{checkbox_id}">{option_label}</label>'
            link_html = f'<a href="#" feat="{option_value}"><i class="fas fa-question-circle"></i></a>'

            # Get feature-specific help text from the help dictionary
            help_text = self.feature_help.get(option_value, "")

            # Combine all elements into a tooltip-enabled feature checkbox container
            output.append(f"""
                <div class="feature_checkbox lm_tooltip">
                    <span class="hide lm_tooltiptext">{help_text} ({know_more})</span>
                    {checkbox_html} {label_html} {link_html}
                </div>
            """)

        return mark_safe("\n".join(output))


class FeatureForm(MyForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def _init_features(self, overall: bool) -> None:
        """Initialize feature selection fields organized by modules.

        Creates form fields for feature selection, grouped by feature modules.
        Each module becomes a MultipleChoiceField with checkboxes for its features.
        Only shows modules and features appropriate for the given context (overall vs event-level).

        Args:
            overall: If True, initialize association-level features;
                    if False, initialize event-level features

        Side Effects:
            - Adds feature selection fields to the form organized by modules
            - Sets initial values based on current feature assignments
            - Modifies self.fields and self.initial dictionaries
        """
        # Get currently assigned features for initial form state
        init_features = None
        if self.instance.pk:
            init_features = [str(v) for v in self.instance.features.values_list("pk", flat=True)]

        # Fetch modules excluding order=0 (disabled/system modules)
        modules = FeatureModule.objects.exclude(order=0).order_by("order")

        # Filter modules by nationality for association-level features
        if overall:
            modules = modules.filter(Q(nationality__isnull=True) | Q(nationality=self.instance.nationality))

        # Process each module to create form fields
        for module in modules:
            # Get visible, non-placeholder features for this module
            features = module.features.filter(overall=overall, placeholder=False, hidden=False).order_by("order")

            # Build choices and help text for feature checkboxes
            choices = [(str(f.id), _(f.name)) for f in features]
            help_text = {str(f.id): _(f.descr) for f in features}

            # Skip modules with no available features
            if not choices:
                continue

            # Create module label with optional icon
            label = _(module.name)
            if module.icon:
                label = f"<i class='fa-solid fa-{module.icon}'></i> {label}"

            # Add the multiple choice field for this module
            self.fields[f"mod_{module.id}"] = forms.MultipleChoiceField(
                choices=choices,
                widget=FeatureCheckboxWidget(help_text=help_text),
                label=label,
                required=False,
            )

            # Set initial selected features if instance exists
            if init_features:
                self.initial[f"mod_{module.id}"] = init_features

    def _save_features(self, instance: Any) -> None:
        """Save selected features to the instance.

        Args:
            instance: Model instance to save features to. Must have a 'features'
                     many-to-many relationship.

        Side Effects:
            - Clears existing features from the instance
            - Sets new features based on form's cleaned_data
            - Updates self.added_features with newly added feature IDs

        Note:
            Expects form data with keys in format 'mod_{module_id}' containing
            lists of feature IDs to assign to the instance.
        """
        # Store current features for comparison
        old_features = set(instance.features.values_list("id", flat=True))

        # Clear existing feature associations
        instance.features.clear()

        # Collect feature IDs from all module form fields
        features_id = []
        for module_id in FeatureModule.objects.values_list("pk", flat=True):
            key = f"mod_{module_id}"

            # Skip if this module's data is not present in form
            if key not in self.cleaned_data:
                continue

            # Add all feature IDs from this module to the list
            features_id.extend([int(v) for v in self.cleaned_data[key]])

        # Set the new feature associations and save
        instance.features.set(features_id)
        instance.save()

        # Track which features were newly added for later use
        new_features = set(features_id)
        self.added_features = new_features - old_features


class QuickSetupForm(MyForm):
    setup = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def init_fields(self, features: list[str]) -> None:
        """Initialize form fields for quick setup configuration.

        Creates boolean fields for each setup option and sets initial values
        based on current configuration or feature availability.

        Args:
            features: List of currently enabled feature slugs.

        Side Effects:
            - Creates boolean fields for each setup option in self.setup
            - Sets initial values based on feature availability or instance config
            - Modifies self.fields and self.initial dictionaries
        """
        # Iterate through each setup configuration item
        for key, element in self.setup.items():
            # Unpack the setup element tuple
            (is_feature, label, help_text) = element

            # Create a boolean field for this setup option
            self.fields[key] = forms.BooleanField(required=False, label=label, help_text=help_text + "?")

            # Determine initial value based on whether it's a feature or config
            if is_feature:
                # For features, check if the key exists in enabled features
                init = key in features
            else:
                # For non-features, get value from instance configuration
                init = self.instance.get_config(key, False)

            # Set the initial value for the field
            self.initial[key] = init

    def save(self, commit: bool = True) -> Any:
        """Save form data and update feature assignments and configurations.

        This method processes form data to update both feature assignments and
        configuration values for the instance. Features are handled through
        many-to-many relationships while configurations are saved individually.

        Args:
            commit: Whether to save the instance to the database. Defaults to True.

        Returns:
            The saved instance with updated features and configurations applied.

        Note:
            The method processes two types of setup elements: features (boolean flags)
            and configurations (individual settings). Features are bulk-updated while
            configurations are saved one by one.
        """
        # Save the base instance first
        instance = super().save(commit=commit)

        # Separate features from configurations based on setup metadata
        features = {}
        for key, element in self.setup.items():
            (is_feature, _label, _help_text) = element
            checked = self.cleaned_data[key]

            # Route to appropriate handler based on element type
            if is_feature:
                features[key] = checked
            else:
                save_single_config(self.instance, key, checked)

        # Bulk retrieve feature IDs to minimize database queries
        features_ids_map = dict(Feature.objects.filter(slug__in=features.keys()).values_list("slug", "id"))

        # Update feature assignments through many-to-many relationship
        for slug, checked in features.items():
            feature_id = features_ids_map[slug]
            if checked:
                self.instance.features.add(feature_id)
            else:
                self.instance.features.remove(feature_id)

        # Final save to persist all changes
        instance.save()

        return instance
