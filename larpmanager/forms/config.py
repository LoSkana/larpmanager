from abc import abstractmethod
from enum import IntEnum
from typing import Any

from django import forms
from django.forms import Textarea
from django.utils.html import escape
from django.utils.safestring import mark_safe
from tinymce.widgets import TinyMCE

from larpmanager.cache.config import reset_element_configs, save_all_element_configs
from larpmanager.forms.base import MyForm
from larpmanager.forms.utils import AssociationMemberS2WidgetMulti, get_members_queryset


class ConfigType(IntEnum):
    CHAR = 1
    BOOL = 2
    HTML = 3
    INT = 4
    TEXTAREA = 5
    MEMBERS = 6
    MULTI_BOOL = 7


class MultiCheckboxWidget(forms.CheckboxSelectMultiple):
    def render(self, name: str, value: list | None, attrs: dict | None = None, renderer=None) -> str:
        """Render the checkbox widget as HTML.

        Args:
            name: The name attribute for the input elements
            value: List of selected values, defaults to empty list if None
            attrs: HTML attributes dictionary for the widget
            renderer: Optional renderer (unused in this implementation)

        Returns:
            Safe HTML string containing the rendered checkbox elements

        """
        output = []
        value = value or []

        # Iterate through each choice option to create checkbox elements
        for i, (option_value, option_label) in enumerate(self.choices):
            # Generate unique ID for each checkbox using the base name and index
            checkbox_id = f"{escape(attrs.get('id', name))}_{i}"

            # Check if current option value is in the selected values list
            checked = "checked" if str(option_value) in value else ""

            # Create the checkbox input element with proper escaping
            checkbox_html = f'<input type="checkbox" name="{escape(name)}" value="{escape(option_value)}" id="{checkbox_id}" {checked}>'

            # Create the associated label element
            link_html = f'<label for="{checkbox_id}">{escape(option_label)}</label>'

            # Wrap checkbox and label in a container div
            output.append(f'<div class="feature_checkbox">{checkbox_html} {link_html}</div>')

        return mark_safe("\n".join(output))


class ConfigForm(MyForm):
    def __init__(self, *args, **kwargs) -> None:
        """Initialize the form with configuration fields and custom elements.

        Args:
            *args: Variable length argument list passed to parent class.
            **kwargs: Arbitrary keyword arguments passed to parent class.

        """
        super().__init__(*args, **kwargs)

        # Initialize configuration attributes
        self.config_fields = []
        self._section = None
        self.jump_section = None

        # Set up initial configurations
        self.set_configs()

        # Get all element configurations and add custom fields
        res = self._get_all_element_configs()
        for el in self.config_fields:
            self._add_custom_field(el, res)

    @abstractmethod
    def set_configs(self) -> None:
        """No-op method placeholder."""
        pass

    def set_section(self, section_slug, section_name):
        """Set the current section for grouping configuration fields.

        Args:
            section_slug: Section slug identifier
            section_name: Display name for the section

        Side effects:
            Sets internal section state and jump_section if matches params

        """
        self._section = section_name
        if self.params.get("jump_section", "") == section_slug:
            self.jump_section = section_name

    def add_configs(self, configuration_key, config_type, field_label, field_help_text, extra_data=None):
        """Add a configuration field to be rendered in the form.

        Args:
            configuration_key: Configuration key name
            config_type: Type of configuration field (ConfigType enum)
            field_label: Display label for the field
            field_help_text: Help text to show with the field
            extra_data: Additional data for specific field types

        Side effects:
            Appends field definition to config_fields list

        """
        self.config_fields.append(
            {
                "key": configuration_key,
                "type": config_type,
                "section": self._section,
                "label": field_label,
                "help_text": field_help_text,
                "extra": extra_data,
            }
        )

    def save(self, commit: bool = True) -> Any:
        """Save the form instance with configuration values.

        Args:
            commit: Whether to save the instance to the database immediately.
                   Defaults to True.

        Returns:
            The saved model instance.

        """
        # Save the parent form instance
        instance = super().save(commit=commit)

        # Collect configuration values from custom fields
        config_values = {}
        for el in self.config_fields:
            self._get_custom_field(el, config_values)

        # Save all collected configuration values to the instance
        save_all_element_configs(instance, config_values)

        # Reset configuration cache for this instance
        reset_element_configs(instance)

        # Final save to persist all changes
        instance.save()

        return instance

    def _get_custom_field(self, field_definition, result_dict):
        """Extract and format configuration field value from form data.

        Args:
            field_definition: Configuration field definition
            result_dict: Dictionary to store extracted values

        Side effects:
            Updates result_dict dictionary with formatted field value

        """
        field_key = field_definition["key"]

        field_value = self.cleaned_data[field_key]
        if field_value is None:
            return

        if field_definition["type"] == ConfigType.MEMBERS:
            field_value = ",".join([str(member.id) for member in field_value])
        else:
            field_value = str(field_value)
            field_value = field_value.replace(r"//", r"/")

        result_dict[field_key] = field_value

    @staticmethod
    def _get_form_field(field_type: ConfigType, label: str, help_text: str, extra=None) -> forms.Field | None:
        """Create appropriate Django form field based on configuration type.

        Parameters
        ----------
        field_type : ConfigType
            Type of configuration field that determines which Django form field to create
        label : str
            Human-readable label text displayed for the form field
        help_text : str
            Descriptive text shown to help users understand the field purpose
        extra : Any, optional
            Additional configuration data specific to certain field types (e.g., choices for MULTI_BOOL)

        Returns
        -------
        forms.Field or None
            Django form field instance matching the specified type, or None if field_type is unknown

        Notes
        -----
        Supported field types include CHAR, BOOL, HTML, INT, TEXTAREA, MEMBERS, and MULTI_BOOL.
        The MEMBERS type requires extra parameter to contain association data for queryset filtering.

        """
        # Map each configuration type to its corresponding Django form field factory
        field_type_to_form_field = {
            # Basic text input field for short strings
            ConfigType.CHAR: lambda: forms.CharField(label=label, help_text=help_text, required=False),
            # Checkbox field with custom styling for boolean values
            ConfigType.BOOL: lambda: forms.BooleanField(
                label=label,
                help_text=help_text,
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "checkbox_single"}),
            ),
            # Rich text editor field for HTML content
            ConfigType.HTML: lambda: forms.CharField(
                label=label, widget=TinyMCE(), help_text=help_text, required=False
            ),
            # Numeric input field with integer validation
            ConfigType.INT: lambda: forms.IntegerField(label=label, help_text=help_text, required=False),
            # Multi-line text area for longer text content
            ConfigType.TEXTAREA: lambda: forms.CharField(
                label=label,
                widget=Textarea(attrs={"rows": 5}),
                help_text=help_text,
                required=False,
            ),
            # Multi-select field for choosing association members
            ConfigType.MEMBERS: lambda: forms.ModelMultipleChoiceField(
                label=label,
                queryset=get_members_queryset(extra),
                widget=AssociationMemberS2WidgetMulti,
                required=False,
                help_text=help_text,
            ),
            # Multiple checkbox field for selecting multiple boolean options
            ConfigType.MULTI_BOOL: lambda: forms.MultipleChoiceField(
                label=label,
                choices=extra,
                widget=MultiCheckboxWidget,
                required=False,
                help_text=help_text,
            ),
        }

        # Get the factory function for the specified field type
        field_factory_function = field_type_to_form_field.get(ConfigType(field_type))
        # Create and return the form field instance, or None if type is unsupported
        return field_factory_function() if field_factory_function else None

    def _add_custom_field(self, config: dict, configuration_values: dict) -> None:
        """Add a custom configuration field to the form.

        Args:
            config : dict
                Configuration field definition containing 'key', 'type', 'label',
                'help_text', 'section', and optionally 'extra'
            configuration_values : dict
                Dictionary of existing configuration values

        This method has side effects:
            - Adds field to form.fields and sets initial values
            - Updates sections mapping for UI organization
            - Initializes custom_field list if not present

        """
        # Extract key and initial value from configuration
        field_key = config["key"]
        initial_value = str(configuration_values[field_key]) if field_key in configuration_values else None

        # Initialize custom_field list if it doesn't exist
        if not hasattr(self, "custom_field"):
            self.custom_field = []
        self.custom_field.append(field_key)

        # Get field type and extra configuration for specific field types
        field_type = config["type"]
        extra_config = config["extra"] if field_type in [ConfigType.MEMBERS, ConfigType.MULTI_BOOL] else None

        # Create and add the form field
        self.fields[field_key] = self._get_form_field(field_type, config["label"], config["help_text"], extra_config)

        # Configure widget for MEMBERS field type
        if field_type == ConfigType.MEMBERS:
            self.fields[field_key].widget.set_association_id(config["extra"])
            if initial_value:
                initial_value = [s.strip() for s in initial_value.split(",")]

        # Initialize sections dictionary and set field section
        if not hasattr(self, "sections"):
            self.sections = {}
        self.sections["id_" + field_key] = config["section"]

        # Set initial value with type conversion for boolean fields
        if initial_value:
            if field_type == ConfigType.BOOL:
                initial_value = initial_value == "True"
            self.initial[field_key] = initial_value

    def _get_all_element_configs(self):
        """Get all existing configuration values for the instance.

        Returns:
            dict: Mapping of configuration names to their current values

        """
        config_mapping = {}
        if self.instance.pk:
            for config in self.instance.configs.all():
                config_mapping[config.name] = config.value
        return config_mapping
