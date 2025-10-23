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
from larpmanager.forms.utils import AssocMemberS2WidgetMulti, get_members_queryset


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
    def set_configs(self):
        pass

    def set_section(self, slug, name):
        """Set the current section for grouping configuration fields.

        Args:
            slug: Section slug identifier
            name: Display name for the section

        Side effects:
            Sets internal section state and jump_section if matches params
        """
        self._section = name
        if self.params.get("jump_section", "") == slug:
            self.jump_section = name

    def add_configs(self, key, config_type, label, help_text, extra=None):
        """Add a configuration field to be rendered in the form.

        Args:
            key: Configuration key name
            config_type: Type of configuration field (ConfigType enum)
            label: Display label for the field
            help_text: Help text to show with the field
            extra: Additional data for specific field types

        Side effects:
            Appends field definition to config_fields list
        """
        self.config_fields.append(
            {
                "key": key,
                "type": config_type,
                "section": self._section,
                "label": label,
                "help_text": help_text,
                "extra": extra,
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

    def _get_custom_field(self, el, res):
        """Extract and format configuration field value from form data.

        Args:
            el: Configuration field definition
            res: Dictionary to store extracted values

        Side effects:
            Updates res dictionary with formatted field value
        """
        k = el["key"]

        val = self.cleaned_data[k]
        if val is None:
            return

        if el["type"] == ConfigType.MEMBERS:
            val = ",".join([str(el.id) for el in val])
        else:
            val = str(val)
            val = val.replace(r"//", r"/")

        res[k] = val

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
        field_map = {
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
                widget=AssocMemberS2WidgetMulti,
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
        factory = field_map.get(ConfigType(field_type))
        # Create and return the form field instance, or None if type is unsupported
        return factory() if factory else None

    def _add_custom_field(self, config: dict, res: dict) -> None:
        """Add a custom configuration field to the form.

        Args:
            config : dict
                Configuration field definition containing 'key', 'type', 'label',
                'help_text', 'section', and optionally 'extra'
            res : dict
                Dictionary of existing configuration values

        This method has side effects:
            - Adds field to form.fields and sets initial values
            - Updates sections mapping for UI organization
            - Initializes custom_field list if not present
        """
        # Extract key and initial value from configuration
        key = config["key"]
        init = str(res[key]) if key in res else None

        # Initialize custom_field list if it doesn't exist
        if not hasattr(self, "custom_field"):
            self.custom_field = []
        self.custom_field.append(key)

        # Get field type and extra configuration for specific field types
        field_type = config["type"]
        extra = config["extra"] if field_type in [ConfigType.MEMBERS, ConfigType.MULTI_BOOL] else None

        # Create and add the form field
        self.fields[key] = self._get_form_field(field_type, config["label"], config["help_text"], extra)

        # Configure widget for MEMBERS field type
        if field_type == ConfigType.MEMBERS:
            self.fields[key].widget.set_assoc(config["extra"])
            if init:
                init = [s.strip() for s in init.split(",")]

        # Initialize sections dictionary and set field section
        if not hasattr(self, "sections"):
            self.sections = {}
        self.sections["id_" + key] = config["section"]

        # Set initial value with type conversion for boolean fields
        if init:
            if field_type == ConfigType.BOOL:
                init = init == "True"
            self.initial[key] = init

    def _get_all_element_configs(self):
        """Get all existing configuration values for the instance.

        Returns:
            dict: Mapping of configuration names to their current values
        """
        res = {}
        if self.instance.pk:
            for config in self.instance.configs.all():
                res[config.name] = config.value
        return res
