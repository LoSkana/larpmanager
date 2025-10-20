from abc import abstractmethod
from enum import IntEnum

from django import forms
from django.forms import Textarea
from django.utils.html import escape
from django.utils.safestring import mark_safe
from tinymce.widgets import TinyMCE

from larpmanager.cache.config import reset_element_configs, save_all_element_configs
from larpmanager.forms.base import MyForm
from larpmanager.forms.utils import AssocMemberS2WidgetMulti, get_members_queryset
from larpmanager.models.base import BaseModel


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
        """Render a custom checkbox widget with feature styling.

        Args:
            name: The HTML name attribute for the input elements
            value: List of selected option values, or None if no selections
            attrs: Dictionary of HTML attributes to apply to the widget
            renderer: Django template renderer (unused in this implementation)

        Returns:
            HTML string containing the rendered checkbox elements
        """
        output = []
        value = value or []

        # Iterate through each choice option to create individual checkboxes
        for i, (option_value, option_label) in enumerate(self.choices):
            # Generate unique ID for each checkbox using the base name and index
            checkbox_id = f"{escape(attrs.get('id', name))}_{i}"

            # Check if this option should be pre-selected
            checked = "checked" if str(option_value) in value else ""

            # Create the checkbox input element with proper escaping
            checkbox_html = f'<input type="checkbox" name="{escape(name)}" value="{escape(option_value)}" id="{checkbox_id}" {checked}>'

            # Create the associated label for accessibility
            link_html = f'<label for="{checkbox_id}">{escape(option_label)}</label>'

            # Wrap checkbox and label in a styled container div
            output.append(f'<div class="feature_checkbox">{checkbox_html} {link_html}</div>')

        return mark_safe("\n".join(output))


class ConfigForm(MyForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config_fields = []
        self._section = None
        self.jump_section = None

        self.set_configs()

        res = self._get_all_element_configs()
        for el in self.config_fields:
            self._add_custom_field(el, res)

    @abstractmethod
    def set_configs(self):
        pass

    def set_section(self, slug: str, name: str) -> None:
        """Set the current section for grouping configuration fields.

        This method updates the internal section state and conditionally sets
        the jump_section attribute when the provided slug matches the
        jump_section parameter.

        Args:
            slug: Section slug identifier used for navigation and matching.
            name: Human-readable display name for the section.

        Side Effects:
            - Updates the internal _section attribute with the display name
            - Sets jump_section attribute if slug matches params['jump_section']
        """
        # Set the current section display name
        self._section = name

        # Check if this section should be marked as the jump target
        if self.params.get("jump_section", "") == slug:
            self.jump_section = name

    def add_configs(
        self, key: str, config_type: "ConfigType", label: str, help_text: str, extra: dict | None = None
    ) -> None:
        """Add a configuration field to be rendered in the form.

        This method appends a field definition dictionary to the config_fields list,
        which will later be used to render form fields in the UI.

        Args:
            key: Configuration key name used to identify the field
            config_type: Type of configuration field from ConfigType enum
            label: Human-readable display label for the field
            help_text: Descriptive help text shown with the field
            extra: Optional additional data for specific field types (e.g., choices, validators)

        Returns:
            None

        Side Effects:
            Modifies the config_fields list by appending a new field definition
        """
        # Build the field definition dictionary with required properties
        field_definition = {
            "key": key,
            "type": config_type,
            "section": self._section,  # Current section context
            "label": label,
            "help_text": help_text,
            "extra": extra,  # Optional field-specific configuration
        }

        # Append the field definition to the config fields list
        self.config_fields.append(field_definition)

    def save(self, commit: bool = True) -> BaseModel:
        """Save the form instance with custom configuration fields.

        This method saves the form instance and processes any custom configuration
        fields defined in self.config_fields. Configuration values are extracted
        from form data, saved to the instance's configuration, and the configuration
        cache is reset.

        Args:
            commit: Whether to save the instance to the database immediately.
                   Defaults to True.

        Returns:
            The saved model instance.
        """
        # Save the parent form instance using the standard save method
        instance = super().save(commit=commit)

        # Extract configuration values from custom fields
        config_values = {}
        for el in self.config_fields:
            self._get_custom_field(el, config_values)

        # Save all configuration values to the instance
        save_all_element_configs(instance, config_values)

        # Reset the configuration cache for this instance
        reset_element_configs(instance)

        # Save the instance again to persist any changes
        instance.save()

        return instance

    def _get_custom_field(self, el: dict, res: dict) -> None:
        """Extract and format configuration field value from form data.

        This method processes a configuration field definition and extracts the
        corresponding value from the form's cleaned data. The value is then
        formatted according to the field type and stored in the result dictionary.

        Args:
            el: Configuration field definition containing 'key' and 'type' fields
            res: Dictionary to store extracted values, modified in-place

        Returns:
            None: This method modifies the res dictionary in-place

        Side Effects:
            Updates the res dictionary with the formatted field value under the
            key specified in el['key']
        """
        # Extract the field key from the configuration element
        k = el["key"]

        # Get the cleaned value from form data
        val = self.cleaned_data[k]
        if val is None:
            return

        # Format value based on configuration field type
        if el["type"] == ConfigType.MEMBERS:
            # Convert member objects to comma-separated ID string
            val = ",".join([str(el.id) for el in val])
        else:
            # Convert to string and normalize double slashes
            val = str(val)
            val = val.replace(r"//", r"/")

        # Store the formatted value in the result dictionary
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

        Parameters
        ----------
        config : dict
            Configuration field definition containing 'key', 'type', 'label',
            'help_text', 'section', and optionally 'extra'
        res : dict
            Dictionary of existing configuration values

        Side Effects
        ------------
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

        # Get field type and optional extra configuration
        field_type = config["type"]
        extra = config["extra"] if field_type in [ConfigType.MEMBERS, ConfigType.MULTI_BOOL] else None

        # Create and add the form field
        self.fields[key] = self._get_form_field(field_type, config["label"], config["help_text"], extra)

        # Special handling for MEMBERS field type
        if field_type == ConfigType.MEMBERS:
            self.fields[key].widget.set_assoc(config["extra"])
            if init:
                init = [s.strip() for s in init.split(",")]

        # Initialize sections mapping if it doesn't exist and add field section
        if not hasattr(self, "sections"):
            self.sections = {}
        self.sections["id_" + key] = config["section"]

        # Set initial value with type conversion for boolean fields
        if init:
            if field_type == ConfigType.BOOL:
                init = init == "True"
            self.initial[key] = init

    def _get_all_element_configs(self) -> dict[str, str]:
        """Get all existing configuration values for the instance.

        Retrieves all configuration objects associated with the current instance
        and returns them as a dictionary mapping configuration names to their values.

        Returns:
            dict[str, str]: Mapping of configuration names to their current values.
                Returns empty dict if instance has no primary key or no configurations.
        """
        res = {}

        # Only fetch configs if instance exists in database
        if self.instance.pk:
            # Iterate through all related configuration objects
            for config in self.instance.configs.all():
                # Map configuration name to its value
                res[config.name] = config.value

        return res
