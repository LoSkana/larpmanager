from __future__ import annotations

from abc import abstractmethod
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from django import forms
from django.forms import Textarea
from django.utils.html import escape, format_html_join

from larpmanager.cache.config import reset_element_configs, save_all_element_configs
from larpmanager.forms.base import BaseModelForm
from larpmanager.forms.utils import AssociationMemberS2WidgetMulti, CSRFTinyMCE, get_members_queryset

if TYPE_CHECKING:
    from larpmanager.models.base import BaseModel


class ConfigType(IntEnum):
    """Represents ConfigType model."""

    CHAR = 1
    BOOL = 2
    HTML = 3
    INT = 4
    TEXTAREA = 5
    MEMBERS = 6
    MULTI_BOOL = 7
    CHOICE = 8


class MultiCheckboxWidget(forms.CheckboxSelectMultiple):
    """Represents MultiCheckboxWidget model."""

    def render(self, name: str, value: list | None, attrs: dict | None = None, renderer: Any = None) -> str:  # noqa: ARG002
        """Render the checkbox widget as HTML.

        Args:
            name: The name attribute for the input elements
            value: List of selected values, defaults to empty list if None
            attrs: HTML attributes dictionary for the widget
            renderer: Optional renderer (unused in this implementation)

        Returns:
            Safe HTML string containing the rendered checkbox elements

        """
        value = value or []

        # Build list of checkbox elements as tuples for format_html_join
        checkbox_elements = []
        for i, (option_value, option_label) in enumerate(self.choices):
            # Generate unique ID for each checkbox using the base name and index
            checkbox_id = f"{escape(attrs.get('id', name))}_{i}"

            # Check if current option value is in the selected values list
            checked = "checked" if str(option_value) in value else ""

            # Build the complete HTML for this checkbox
            checkbox_elements.append(
                (
                    name,
                    option_value,
                    checkbox_id,
                    checked,
                    checkbox_id,
                    option_label,
                ),
            )

        # Use format_html_join to safely generate the HTML
        return format_html_join(
            "\n",
            '<div class="feature_checkbox"><input type="checkbox" name="{}" value="{}" id="{}" {}> <label for="{}">{}</label></div>',
            checkbox_elements,
        )


class ConfigForm(BaseModelForm):
    """Form for Config."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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

        # If in frame mode with a specific section, remove fields from other sections
        if self.params.get("frame") and self.jump_section:
            self._filter_fields_by_section()

    @abstractmethod
    def set_configs(self) -> None:
        """No-op method placeholder."""

    def _filter_fields_by_section(self) -> None:
        """Remove all fields that don't belong to jump_section when in frame mode.

        This method filters out configuration fields from other sections when
        the form is being displayed in a modal frame focused on a specific section.

        Side effects:
            - Removes fields from self.fields that don't belong to jump_section
            - Updates self.sections to only contain fields from jump_section
            - Updates self.config_fields to only contain configs from jump_section
            - Sets show_sections to True to auto-open the section

        """
        # Filter config_fields to keep only those in the target section
        self.config_fields = [cf for cf in self.config_fields if cf["section"] == self.jump_section]

        # Get keys of fields to keep
        fields_to_keep = {cf["key"] for cf in self.config_fields}

        # Remove fields not in the target section
        fields_to_remove = [key for key in self.fields if key not in fields_to_keep]
        for key in fields_to_remove:
            del self.fields[key]

        # Update sections dict to only contain fields from target section
        if hasattr(self, "sections"):
            self.sections = {k: v for k, v in self.sections.items() if v == self.jump_section}

        # Auto-open the section in frame mode
        self.show_sections = True

        # Flag to hide section headers in frame mode
        self.hide_section_headers = True

    def set_section(self, section_slug: str, section_name: str) -> None:
        """Set the current section for grouping configuration fields."""
        self._section = section_name
        if self.params.get("jump_section", "") == section_slug:
            self.jump_section = section_name

    def add_configs(
        self,
        configuration_key: str,
        config_type: ConfigType,
        field_label: str,
        field_help_text: str,
        extra_data: Any = None,
    ) -> None:
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
            },
        )

    def save(self, commit: bool = True) -> BaseModel:  # noqa: FBT001, FBT002
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

    def _get_custom_field(self, field_definition: dict, result_dict: dict) -> None:
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
    def _get_form_field(field_type: ConfigType, label: str, help_text: str, extra: Any = None) -> forms.Field | None:
        """Create appropriate Django form field based on configuration type.

        Args:
            field_type:  Type of configuration field that determines which Django form field to create
            label: Human-readable label text displayed for the form field
            help_text: Descriptive text shown to help users understand the field purpose
            extra:Additional configuration data specific to certain field types (e.g., choices for MULTI_BOOL)

        Returns:
            forms.Field or None: Django form field instance matching the specified type, or None if field_type is unknown

        Notes:
            Supported field types include CHAR, BOOL, HTML, INT, TEXTAREA, MEMBERS, and MULTI_BOOL.
            The MEMBERS type requires extra parameter to contain association data for queryset filtering.

        """
        # Map each configuration type to its corresponding Django form field factory
        field_type_to_form_field = {
            # Basic text input field for short strings, with optional validators from extra
            ConfigType.CHAR: lambda: forms.CharField(
                label=label, help_text=help_text, required=False, validators=extra if extra else []
            ),
            # Checkbox field with custom styling for boolean values
            ConfigType.BOOL: lambda: forms.BooleanField(
                label=label,
                help_text=help_text,
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "checkbox_single"}),
            ),
            # Rich text editor field for HTML content
            ConfigType.HTML: lambda: forms.CharField(
                label=label,
                widget=CSRFTinyMCE(),
                help_text=help_text,
                required=False,
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
            # Dropdown select field for single choice from a list
            ConfigType.CHOICE: lambda: forms.ChoiceField(
                label=label,
                choices=extra,
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
        extra_config = (
            config["extra"]
            if field_type in [ConfigType.MEMBERS, ConfigType.MULTI_BOOL, ConfigType.CHAR, ConfigType.CHOICE]
            else None
        )

        # Create and add the form field
        self.fields[field_key] = self._get_form_field(field_type, config["label"], config["help_text"], extra_config)

        # Configure widget for MEMBERS field type
        if field_type == ConfigType.MEMBERS:
            self.configure_field_association(field_key, config["extra"])
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

    def _get_all_element_configs(self) -> dict[str, str]:
        """Get all existing configuration values for the instance."""
        config_mapping = {}
        if self.instance.pk:
            for config in self.instance.configs.all():
                config_mapping[config.name] = config.value
        return config_mapping
