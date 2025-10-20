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
from typing import Any, Optional

from django import forms
from django.conf import settings as conf_settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms

from larpmanager.cache.config import get_assoc_config
from larpmanager.forms.utils import WritingTinyMCE, css_delimeter
from larpmanager.models.association import Association
from larpmanager.models.base import BaseModel
from larpmanager.models.event import Event, Run
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionStatus,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingQuestion,
    WritingQuestionType,
    get_writing_max_length,
)
from larpmanager.models.utils import generate_id, get_attr, strip_tags
from larpmanager.templatetags.show_tags import hex_to_rgb


class MyForm(forms.ModelForm):
    """Base form class with context parameter handling.

    Extends Django's ModelForm to support additional context parameters
    that can be passed during form initialization.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with optional context parameters.

        This method sets up the form with context data, removes unnecessary fields,
        configures widgets, and initializes tracking dictionaries for form state.

        Args:
            *args: Positional arguments passed to parent ModelForm.
            **kwargs: Keyword arguments that may include:
                - ctx: Context data dictionary
                - run: Run instance for form context
                - request: HTTP request object

        Note:
            Automatically removes 'deleted' and 'temp' fields if present.
            Sets up character widget with event context when available.
            Configures automatic fields as hidden or removes them based on instance state.
        """
        # Initialize parent class and extract context parameters
        super().__init__()
        if "ctx" in kwargs:
            self.params = kwargs.pop("ctx")
        else:
            self.params = {}

        # Extract run and request parameters if provided
        for k in ["run", "request"]:
            if k in kwargs:
                self.params[k] = kwargs.pop(k)

        # Call parent ModelForm initialization with remaining arguments
        super(forms.ModelForm, self).__init__(*args, **kwargs)

        # Remove system fields that shouldn't be user-editable
        for m in ["deleted", "temp"]:
            if m in self.fields:
                del self.fields[m]

        # Configure characters field widget with event context
        if "characters" in self.fields:
            self.fields["characters"].widget.set_event(self.params["event"])

        # Handle automatic fields based on instance state
        for s in self.get_automatic_field():
            if s in self.fields:
                if self.instance.pk:
                    # Remove automatic fields for existing instances
                    del self.fields[s]
                else:
                    # Hide automatic fields for new instances
                    self.fields[s].widget = forms.HiddenInput()
                    self.fields[s].required = False

        # Initialize tracking dictionaries for form state management
        self.mandatory = []
        self.answers = {}
        self.singles = {}
        self.multiples = {}
        self.unavail = {}
        self.max_lengths = {}

    def get_automatic_field(self):
        """Get list of fields that should be automatically populated.

        Returns:
            list: Field names that are automatically set and hidden from user
        """
        s = ["event", "assoc"]
        if hasattr(self, "auto_run"):
            s.extend(["run"])
        return s

    def allow_run_choice(self) -> None:
        """Configure run selection field based on available runs.

        Sets up the run choice field, considering campaign switches and
        hiding the field if only one run is available. When campaign_switch
        is enabled, includes runs from parent/child events in the same campaign.

        Notes:
            - Hides run field if only one run is available
            - For existing instances, deletes the field entirely
            - For new instances, uses HiddenInput widget
            - Orders runs by end date
        """
        # Get base runs for the current event
        runs = Run.objects.filter(event=self.params["event"])

        # If campaign switch is active, expand to include related events
        if get_assoc_config(self.params["event"].assoc_id, "campaign_switch", False):
            # Start with current event ID
            event_ids = {self.params["event"].id}

            # Add child events
            child = Event.objects.filter(parent_id=self.params["event"].id).values_list("pk", flat=True)
            event_ids.update(child)

            # Add parent and sibling events if current event has a parent
            if self.params["event"].parent_id:
                event_ids.add(self.params["event"].parent_id)
                siblings = Event.objects.filter(parent_id=self.params["event"].parent_id).values_list("pk", flat=True)
                event_ids.update(siblings)

            # Filter runs by all related event IDs
            runs = Run.objects.filter(event_id__in=event_ids)

        # Optimize query and order by end date
        runs = runs.select_related("event").order_by("end")

        # Set initial value to current run
        self.initial["run"] = self.params["run"].id

        # Handle field visibility based on number of available runs
        if len(runs) <= 1:
            if self.instance.pk:
                # For existing instances, remove field entirely
                self.delete_field("run")
            else:
                # For new instances, hide the field
                self.fields["run"].widget = forms.HiddenInput()
        else:
            # Multiple runs available, populate choices
            self.fields["run"].choices = [(r.id, str(r)) for r in runs]
            # noinspection PyUnresolvedReferences
            del self.auto_run

    def clean_run(self):
        if hasattr(self, "auto_run"):
            return self.params["run"]
        return self.cleaned_data["run"]

    def clean_event(self):
        if hasattr(self, "choose_event"):
            return self.cleaned_data["event"]
        typ = self.params["elementTyp"]
        return self.params["event"].get_class_parent(typ)

    def clean_assoc(self):
        return Association.objects.get(pk=self.params["a_id"])

    def clean_name(self):
        return self._validate_unique_event("name")

    def clean_display(self):
        return self._validate_unique_event("display")

    def _validate_unique_event(self, field_name: str) -> any:
        """
        Validate field uniqueness within event scope.

        This method ensures that a field value is unique within the context of a specific
        event or association. It handles different model types and applies various filters
        based on the form's configuration.

        Args:
            field_name (str): Name of the field to validate for uniqueness

        Returns:
            any: The validated field value if unique

        Raises:
            ValidationError: If value is not unique within the event scope
        """
        # Get the field value and required parameters
        value = self.cleaned_data.get(field_name)
        event = self.params.get("event")
        typ = self.params.get("elementTyp")

        # Only validate if we have both event and type parameters
        if event and typ:
            # Get the appropriate event ID based on the element type
            event_id = event.get_class_parent(typ).id

            # Build the base queryset based on the model type
            model = self._meta.model
            if model == Event:
                # For Event model, filter by association ID
                qs = model.objects.filter(**{field_name: value}, assoc_id=event.assoc_id)
            else:
                # For other models, filter by event ID
                qs = model.objects.filter(**{field_name: value}, event_id=event_id)

            # Apply additional filters if question is specified
            question = self.cleaned_data.get("question")
            if question:
                qs = qs.filter(question_id=question.id)

            # Apply applicable filter if the form supports it
            if hasattr(self, "check_applicable"):
                qs = qs.filter(applicable=self.check_applicable)

            # Exclude current instance for updates (not for new instances)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            # Check if any duplicates exist and raise error if found
            if qs.exists():
                raise ValidationError(field_name.capitalize() + " " + _("already used"))

        return value

    def save(self, commit: bool = True) -> BaseModel:
        """Save the form instance with custom field handling.

        Args:
            commit: Whether to save the instance to the database immediately.
                   Defaults to True.

        Returns:
            The saved model instance.
        """
        # Call parent save method to get the instance
        instance = super(forms.ModelForm, self).save(commit=commit)

        # Validate all fields before processing
        self.full_clean()

        # Process each field in the form
        for s in self.fields:
            # Skip custom fields if they exist
            if hasattr(self, "custom_field"):
                if s in self.custom_field:
                    continue

            # Handle multi-select widgets specially
            if isinstance(self.fields[s].widget, s2forms.ModelSelect2MultipleWidget):
                self._save_multi(s, instance)

        return instance

    def _save_multi(self, s: str, instance) -> None:
        """Save many-to-many field relationships for a model instance.

        Compares the initial values with cleaned form data to determine
        which relationships to add or remove, then updates the instance
        accordingly.

        Args:
            s: The field name for the many-to-many relationship
            instance: The model instance to update
        """
        # Get the initial set of related object primary keys
        if s in self.initial:
            old = set()
            for el in self.initial[s]:
                if hasattr(el, "pk"):
                    old.add(el.pk)
                else:
                    old.add(int(el))
        else:
            old = set()

        # Get the new set of primary keys from cleaned form data
        new = set(self.cleaned_data[s].values_list("pk", flat=True))

        # Get the attribute manager for the many-to-many field
        attr = get_attr(instance, s)

        # Remove relationships that are no longer selected
        for ch in old - new:
            attr.remove(ch)

        # Add new relationships that were selected
        for ch in new - old:
            attr.add(ch)

    def delete_field(self, key):
        if key in self.fields:
            del self.fields[key]


class MyFormRun(MyForm):
    """Form class for run-specific operations.

    Extends MyForm with automatic run handling functionality.
    Sets auto_run to True by default for run-related forms.
    """

    def __init__(self, *args, **kwargs):
        self.auto_run = True
        super().__init__(*args, **kwargs)


def max_selections_validator(max_choices: int) -> callable:
    """Create a validator that limits the number of selectable options.

    This function returns a validator that can be used with Django form fields
    to ensure that users don't select more than the specified maximum number
    of options in multi-choice fields.

    Args:
        max_choices: Maximum number of options that can be selected.
            Must be a positive integer.

    Returns:
        A validator function that takes a value and raises ValidationError
        if the number of selected options exceeds max_choices.

    Raises:
        ValidationError: When the validator is called and the number of
            selected options exceeds the maximum allowed.

    Example:
        >>> validator = max_selections_validator(3)
        >>> validator(['option1', 'option2'])  # OK
        >>> validator(['option1', 'option2', 'option3', 'option4'])  # Raises ValidationError
    """

    def validator(value):
        # Check if the number of selected values exceeds the maximum allowed
        if len(value) > max_choices:
            # Raise validation error with localized message
            raise ValidationError(_("You have exceeded the maximum number of selectable options"))

    return validator


def max_length_validator(max_length: int) -> callable:
    """Create a validator that limits text length after stripping HTML tags.

    This validator removes HTML tags from the input text before checking length,
    ensuring that HTML markup doesn't count toward the character limit.

    Args:
        max_length: Maximum allowed text length after HTML stripping.

    Returns:
        A validator function that raises ValidationError if text exceeds max_length.

    Raises:
        ValidationError: When stripped text length exceeds the maximum allowed.
    """

    def validator(value: str) -> None:
        # Strip HTML tags from the input value to get plain text
        plain_text = strip_tags(value)

        # Check if the plain text exceeds the maximum allowed length
        if len(plain_text) > max_length:
            raise ValidationError(_("You have exceeded the maximum text length"))

    return validator


class BaseRegistrationForm(MyFormRun):
    """Base form class for registration-related forms.

    Provides common functionality for handling registration questions,
    answers, and form validation. Supports both gift registrations
    and regular registrations with dynamic form field generation.
    """

    gift = False
    answer_class = RegistrationAnswer
    choice_class = RegistrationChoice
    option_class = RegistrationOption
    question_class = RegistrationQuestion
    instance_key = "reg_id"

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_link = []
        self.sections = {}

    def _init_reg_question(self, instance: Optional[Any], event: Any) -> None:
        """Initialize registration questions and answers from existing instance.

        Loads existing answers and choices from the database for a given registration
        instance, then initializes the available choice options for the event's
        registration questions.

        Args:
            instance: Registration instance to load data from. Can be None for new registrations.
            event: Event object providing context for question filtering and options.

        Returns:
            None: This method modifies instance attributes in place.
        """
        # Load existing answers if instance exists and has been saved
        if instance and instance.pk:
            # Populate answers dictionary with existing text/numeric answers
            for el in self.answer_class.objects.filter(**{self.instance_key: instance.id}):
                self.answers[el.question_id] = el

            # Populate choice dictionaries with existing single/multiple choice answers
            for el in self.choice_class.objects.filter(**{self.instance_key: instance.id}).select_related("question"):
                # Handle single choice questions - store the selected choice
                if el.question.typ == BaseQuestionType.SINGLE:
                    self.singles[el.question_id] = el
                # Handle multiple choice questions - store as a set of selected choices
                elif el.question.typ == BaseQuestionType.MULTIPLE:
                    if el.question_id not in self.multiples:
                        self.multiples[el.question_id] = set()
                    self.multiples[el.question_id].add(el)

        # Initialize choices dictionary for all available options
        self.choices = {}

        # Load all available choice options for this event's questions
        for r in self.get_options_query(event):
            # Group options by question ID for easy lookup during form rendering
            if r.question_id not in self.choices:
                self.choices[r.question_id] = []
            self.choices[r.question_id].append(r)

        # Finalize question initialization with event context
        self._init_questions(event)

    def _init_questions(self, event):
        self.questions = self.question_class.get_instance_questions(event, self.params["features"])

    def get_options_query(self, event):
        return self.option_class.objects.filter(question__event=event).order_by("order")

    def get_choice_options(self, all_options: dict, question, chosen=None, reg_count=None) -> tuple[list[tuple], str]:
        """
        Build form choice options for a question with availability and ticket validation.

        Processes available options for a registration question, applying availability
        constraints and ticket validation rules to generate valid form choices.

        Parameters
        ----------
        all_options : dict
            Dictionary mapping question IDs to their available option lists
        question : Question
            Question instance to retrieve and process options for
        chosen : optional
            Previously selected options for validation checks
        reg_count : optional
            Registration count data used for availability verification

        Returns
        -------
        tuple[list[tuple], str]
            A tuple containing:
            - List of (option_id, display_name) tuples for form choices
            - Combined help text string with question description and option details
        """
        choices = []
        help_text = question.description
        run = self.params["run"]

        # Early return if no options available for this question
        if question.id not in all_options:
            return choices, help_text

        options = all_options[question.id]

        # Process each available option for the question
        for option in options:
            # Generate display text with pricing information
            name = option.get_form_text(run, cs=self.params["currency_symbol"])

            # Check availability constraints if registration counts provided
            if reg_count and option.max_available > 0:
                name, valid = self.check_option(chosen, name, option, reg_count, run)
                if not valid:
                    continue

            # Validate ticket compatibility if ticket mapping exists
            if reg_count and hasattr(option, "tickets_map"):
                tickets_id = [i for i in option.tickets_map if i is not None]
                if tickets_id and run.reg.ticket_id not in tickets_id:
                    continue

            # Add valid option to choices and append description to help text
            choices.append((option.id, name))
            if option.description:
                help_text += f'<p id="hp_{option.id}"><b>{option.name}</b> {option.description}</p>'

        return choices, help_text

    def check_option(self, chosen: list, name: str, option, reg_count: dict, run) -> tuple[str, bool]:
        """
        Check option availability and update display name with availability info.

        This function determines if an option is available for selection by checking
        if it was previously chosen and if there are remaining available spots.
        It updates the display name to show availability information.

        Args:
            chosen: List of previously chosen options for this registration
            name: Display name for the option that will be updated
            option: Option instance to check availability for
            reg_count: Dictionary containing registration count data by option key
            run: Run instance for the current event

        Returns:
            tuple[str, bool]: A tuple containing:
                - updated_name: Display name with availability info appended
                - is_valid: Boolean indicating if the option is valid/available
        """
        # Check if this option was previously chosen by the user
        found = False
        valid = True

        if chosen:
            for choice in chosen:
                if choice.option_id == option.id:
                    found = True

        # If option wasn't previously chosen, check availability
        if not found:
            # Get the count key and calculate remaining availability
            key = self.get_option_key_count(option)
            avail = option.max_available

            # Subtract current registrations from max available
            if key in reg_count:
                avail -= reg_count[key]

            # Handle unavailable options or update name with availability
            if avail <= 0:
                # Track unavailable options for this question
                if option.question_id not in self.unavail:
                    self.unavail[option.question_id] = []
                self.unavail[option.question_id].append(option.id)
            else:
                # Append availability count to display name
                name += " - (" + _("Available") + f" {avail})"

        return name, valid

    def clean(self) -> dict:
        """Validate form data and check registration constraints.

        Validates that selected options in multiple choice and single choice
        questions are still available and not in the unavailable list.

        Returns:
            dict: The cleaned form data dictionary containing validated field values.

        Raises:
            ValidationError: If any selected option is no longer available or
                           validation rules are violated.
        """
        form_data = super().clean()

        # Skip validation if no questions are defined on the form
        if hasattr(self, "questions"):
            # Iterate through all questions to validate selected options
            for q in self.questions:
                k = "q" + str(q.id)

                # Skip if this question's data is not in the form submission
                if k not in form_data:
                    continue

                # Handle multiple choice questions
                if q.typ == BaseQuestionType.MULTIPLE:
                    for sel in form_data[k]:
                        # Skip empty selections
                        if not sel:
                            continue

                        # Check if selected option is unavailable
                        if q.id in self.unavail and int(sel) in self.unavail[q.id]:
                            self.add_error(k, _("Option no longer available"))

                # Handle single choice questions
                elif q.typ == BaseQuestionType.SINGLE:
                    # Skip empty selections
                    if not form_data[k]:
                        continue

                    # Check if selected option is unavailable
                    if q.id in self.unavail and int(form_data[k]) in self.unavail[q.id]:
                        self.add_error(k, _("Option no longer available"))

        return form_data

    def get_option_key_count(self, option: BaseModel) -> str:
        """
        Generate counting key for option availability tracking.

        This method creates a unique identifier string used to track the usage
        count of a specific option in the system's availability monitoring.

        Parameters
        ----------
        option : Option
            The option instance for which to generate the tracking key.

        Returns
        -------
        str
            A formatted key string in the format "option_{id}" used for
            tracking option usage counts.

        Examples
        --------
        >>> option = Option(id=123)
        >>> key = self.get_option_key_count(option)
        >>> print(key)
        'option_123'
        """
        # Generate unique key using option ID for tracking purposes
        key = f"option_{option.id}"

        return key

    def init_orga_fields(self, reg_section: str = None) -> list[str]:
        """
        Initialize form fields for organizer view with registration questions.

        This method processes registration questions for the event associated with the
        current run, filtering and initializing fields based on feature availability
        and organizer permissions.

        Args:
            reg_section: Optional registration section name override. If provided,
                        overrides the section name from question.section.

        Returns:
            List of initialized field keys that were successfully processed and added
            to the form.
        """
        # Get the event from the current run and initialize registration questions
        event = self.params["run"].event
        self._init_reg_question(self.instance, event)

        # Initialize list to track successfully processed field keys
        keys = []

        # Process each registration question for organizer view
        for question in self.questions:
            # Skip questions that don't apply to current context/features
            if question.skip(self.instance, self.params["features"], self.params, True):
                continue

            # Initialize the field for this question in organizer mode
            k = self._init_field(question, reg_counts=None, orga=True)
            if not k:
                continue

            # Add successfully initialized field key to results
            keys.append(k)

            # Determine section name - use override or question's section
            sec_name = reg_section
            if hasattr(question, "section") and question.section:
                sec_name = question.section.name

            # Associate field with its section for UI organization
            if sec_name:
                self.sections["id_" + k] = sec_name

        return keys

    def check_editable(self, question):
        return True

    def _init_field(
        self, question: WritingQuestion, reg_counts: Optional[dict[str, Any]] = None, orga: bool = True
    ) -> Optional[str]:
        """Initialize form field for a writing question.

        Creates and configures a form field based on the writing question type and settings.
        Handles different question statuses, validation requirements, and organizer vs user contexts.

        Args:
            question: WritingQuestion instance to create field for
            reg_counts: Registration count data for field initialization, defaults to None
            orga: Whether this is an organizer form, defaults to True

        Returns:
            Form field key string if field was created, None if question was skipped
            (computed questions or non-editable questions for users)
        """
        # Skip computed questions entirely - they don't need form fields
        if question.typ == WritingQuestionType.COMPUTED:
            return None

        # Generate unique field key based on question ID
        key = "q" + str(question.id)

        # Set default field states for organizer context
        active = True
        required = False

        # Apply user-specific field logic when not in organizer mode
        if not orga:
            # Check if question is editable for current user context
            if not self.check_editable(question):
                return None

            # Hide questions marked as hidden from users
            if question.status == QuestionStatus.HIDDEN:
                return None

            # Disable fields for disabled questions or creation-only questions
            if question.status == QuestionStatus.DISABLED:
                active = False
            else:
                # Set field as required based on question status
                required = question.status == QuestionStatus.MANDATORY

        # Initialize field type and apply type-specific configuration
        key = self.init_type(key, orga, question, reg_counts, required)
        if not key:
            return key

        # Apply user-specific field state (disabled/enabled)
        if not orga:
            self.fields[key].disabled = not active

        # Configure max length validation for applicable question types
        if question.max_length:
            if question.typ in get_writing_max_length():
                self.max_lengths[f"id_{key}"] = (question.max_length, question.typ)

        # Mark mandatory fields with visual indicator and track for validation
        if question.status == QuestionStatus.MANDATORY:
            self.fields[key].label += " (*)"
            self.has_mandatory = True
            self.mandatory.append("id_" + key)

        # Set basic type flag for template rendering logic
        question.basic_typ = question.typ in BaseQuestionType.get_basic_types()

        return key

    def init_type(self, key: str, orga: bool, question: object, reg_counts: dict, required: bool) -> str:
        """Initialize form field based on question type.

        Creates and configures form fields according to the question type, handling
        multiple choice, single choice, text input, paragraph, editor, and special
        question types with appropriate field initialization.

        Args:
            key: Field key identifier for form field mapping
            orga: Organization context flag indicating organizational scope
            question: Question object containing type and configuration data
            reg_counts: Registration count data for field population
            required: Whether the field is mandatory for form submission

        Returns:
            str: The field key identifier, potentially modified by special handlers

        Note:
            Sets the 'key' attribute on the created field for later reference.
        """
        # Handle multiple choice questions with checkboxes or select widgets
        if question.typ == BaseQuestionType.MULTIPLE:
            self.init_multiple(key, orga, question, reg_counts, required)

        # Handle single choice questions with radio buttons or dropdowns
        elif question.typ == BaseQuestionType.SINGLE:
            self.init_single(key, orga, question, reg_counts, required)

        # Handle simple text input fields
        elif question.typ == BaseQuestionType.TEXT:
            self.init_text(key, question, required)

        # Handle multi-line paragraph text areas
        elif question.typ == BaseQuestionType.PARAGRAPH:
            self.init_paragraph(key, question, required)

        # Handle rich text editor fields with formatting options
        elif question.typ == BaseQuestionType.EDITOR:
            self.init_editor(key, question, required)

        # Handle special question types that may modify the key
        else:
            key = self.init_special(question, required)

        # Set the key attribute on the field for form processing
        if key:
            self.fields[key].key = key

        return key

    def init_special(self, question: BaseModel, required: bool) -> str | None:
        """Initialize special form field configurations.

        This method configures special form fields based on question type,
        applying labels, help text, validation, and field ordering.

        Args:
            question: Question object containing type, name, description, and validation data
            required: Whether the field should be marked as required

        Returns:
            The field key if successfully initialized, None if field doesn't exist

        Note:
            Only applies max_length validation to text-based fields (name, teaser, text).
        """
        # Map question types to their corresponding field keys
        key = question.typ
        mapping = {
            "faction": "factions_list",
            "additional_tickets": "additionals",
            "pay_what_you_want": "pay_what",
            "reg_quotas": "quotas",
            "reg_surcharges": "surcharge",
        }

        # Use mapped key if available, otherwise use original type
        if key in mapping:
            key = mapping[key]

        # Exit early if field doesn't exist in form
        if key not in self.fields:
            return None

        # Configure field properties from question data
        self.fields[key].label = question.name
        self.fields[key].help_text = question.description
        self.reorder_field(key)
        self.fields[key].required = required

        # Apply length validation only to text-based fields
        if key in ["name", "teaser", "text"]:
            self.fields[key].validators = [max_length_validator(question.max_length)] if question.max_length else []

        return key

    def init_editor(self, key: str, question: BaseModel, required: bool) -> None:
        """Initialize a TinyMCE editor field for a form question.

        Args:
            key: The field key/name to use in the form
            question: Question object containing field configuration
            required: Whether the field is required
        """
        # Set up validators based on question configuration
        validators = [max_length_validator(question.max_length)] if question.max_length else []

        # Create the CharField with TinyMCE widget
        self.fields[key] = forms.CharField(
            required=required,
            widget=WritingTinyMCE(),
            label=question.name,
            help_text=question.description,
            validators=validators,
        )

        # Set initial value if answer exists
        if question.id in self.answers:
            self.initial[key] = self.answers[question.id].text

        # Add field to show_link list for frontend handling
        self.show_link.append(f"id_{key}")

    def init_paragraph(self, key, question, required):
        validators = [max_length_validator(question.max_length)] if question.max_length else []
        self.fields[key] = forms.CharField(
            required=required,
            widget=forms.Textarea(attrs={"rows": 4}),
            label=question.name,
            help_text=question.description,
            validators=validators,
        )
        if question.id in self.answers:
            self.initial[key] = self.answers[question.id].text

    def init_text(self, key, question, required):
        validators = [max_length_validator(question.max_length)] if question.max_length else []
        self.fields[key] = forms.CharField(
            required=required, label=question.name, help_text=question.description, validators=validators
        )
        if question.id in self.answers:
            self.initial[key] = self.answers[question.id].text

    def init_single(self, key: str, orga: bool, question: Any, reg_counts: dict, required: bool) -> None:
        """Initialize single choice form field.

        Args:
            key: Form field key for the choice field
            orga: Whether this is an organizational form context
            question: Question object containing choices configuration and metadata
            reg_counts: Registration counts dictionary for quota tracking
            required: Whether the field is required for form validation

        Side Effects:
            - Creates and adds a single choice field to self.fields
            - Sets initial value in self.initial if a previous selection exists
        """
        if orga:
            # Get choice options for organizational context
            (choices, help_text) = self.get_choice_options(self.choices, question)

            # Add default "Not selected" option if no previous selection exists
            if question.id not in self.singles:
                choices.insert(0, (0, "--- " + _("Not selected")))
        else:
            # Prepare list of previously chosen options for user context
            chosen = []
            if question.id in self.singles:
                chosen.append(self.singles[question.id])

            # Get choice options with quota tracking for user registration
            (choices, help_text) = self.get_choice_options(self.choices, question, chosen, reg_counts)

        # Create the choice field with determined options and configuration
        self.fields[key] = forms.ChoiceField(
            required=required,
            choices=choices,
            label=question.name,
            help_text=help_text,
        )

        # Set initial value from previous selection if it exists
        if question.id in self.singles:
            self.initial[key] = self.singles[question.id].option_id

    def init_multiple(self, key: str, orga: bool, question: Any, reg_counts: dict, required: bool) -> None:
        """Set up multiple choice form field handling.

        Creates a multiple choice field with checkboxes for form questions that allow
        multiple selections. Handles both organizational and regular forms with
        different choice option processing.

        Args:
            key: Form field identifier used as the field name
            orga: True if this is an organizational form, False for regular forms
            question: Question object containing choices configuration and metadata
            reg_counts: Dictionary mapping registration types to their current counts
                       for quota tracking purposes
            required: True if the field must be filled, False if optional

        Side Effects:
            - Creates a MultipleChoiceField in self.fields[key]
            - Sets initial values in self.initial[key] if previous selections exist
            - Applies max_selections_validator if question has max_length limit
        """
        # Process choice options differently for organizational vs regular forms
        if orga:
            (choices, help_text) = self.get_choice_options(self.choices, question)
        else:
            chosen = []
            # Retrieve previously selected choices if they exist
            if question.id in self.multiples:
                chosen = self.multiples[question.id]
            (choices, help_text) = self.get_choice_options(self.choices, question, chosen, reg_counts)

        # Add validator for maximum selection limit if specified
        validators = [max_selections_validator(question.max_length)] if question.max_length else []

        # Create the multiple choice field with checkbox widget
        self.fields[key] = forms.MultipleChoiceField(
            required=required,
            choices=choices,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"}),
            label=question.name,
            help_text=help_text,
            validators=validators,
        )

        # Set initial values from previously selected options
        if question.id in self.multiples:
            init = list([el.option_id for el in self.multiples[question.id]])
            self.initial[key] = init

    def reorder_field(self, key):
        # reorder the field, adding it now in the ordering
        field = self.fields.pop(key)
        self.fields[key] = field

    def save_reg_questions(self, instance, orga=True):
        """Save registration question answers to database.

        Args:
            instance: Registration instance to save answers for
            orga (bool): Whether to save organizational questions
        """
        for q in self.questions:
            if q.skip(instance, self.params["features"], self.params, orga):
                continue

            k = "q" + str(q.id)
            if k not in self.cleaned_data:
                continue
            oid = self.cleaned_data[k]

            if q.typ == BaseQuestionType.MULTIPLE:
                self.save_reg_multiple(instance, oid, q)
            elif q.typ == BaseQuestionType.SINGLE:
                self.save_reg_single(instance, oid, q)
            elif q.typ in [BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR]:
                self.save_reg_text(instance, oid, q)

    def save_reg_text(self, instance, oid, q):
        if q.id in self.answers:
            if not oid:
                # For disabled questions in organizer forms, don't delete existing answers
                # unless the organizer explicitly submitted an empty value for an editable field
                orga = getattr(self, "orga", False)
                is_disabled = hasattr(q, "status") and q.status == "d"
                if orga and is_disabled:
                    # Keep existing value for disabled fields in organizer forms
                    pass
                else:
                    self.answers[q.id].delete()
            elif oid != self.answers[q.id].text:
                self.answers[q.id].text = oid
                self.answers[q.id].save()
        elif oid:  # Only create new answers if there's actually content
            self.answer_class.objects.create(**{"question": q, self.instance_key: instance.id, "text": oid})

    def save_reg_single(self, instance, oid, q):
        if not oid:
            return
        oid = int(oid)
        if q.id in self.singles:
            if oid == 0:
                self.singles[q.id].delete()
            elif oid != self.singles[q.id].option_id:
                self.singles[q.id].option_id = oid
                self.singles[q.id].save()
        elif oid != 0:
            self.choice_class.objects.create(**{"question": q, self.instance_key: instance.id, "option_id": oid})

    def save_reg_multiple(self, instance, oid, q):
        if not oid:
            return
        oid = set([int(o) for o in oid])
        if q.id in self.multiples:
            old = set([el.option_id for el in self.multiples[q.id]])
            for add in oid - old:
                self.choice_class.objects.create(**{"question": q, self.instance_key: instance.id, "option_id": add})
            rem = old - oid
            self.choice_class.objects.filter(
                **{"question": q, self.instance_key: instance.id, "option_id__in": rem}
            ).delete()
        else:
            for pkoid in oid:
                self.choice_class.objects.create(**{"question": q, self.instance_key: instance.id, "option_id": pkoid})


class MyCssForm(MyForm):
    """Form class for handling CSS customization.

    Manages CSS file upload, editing, and processing for styling
    customization with support for backgrounds, fonts, and color themes.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            return

        path = self.get_css_path(self.instance)
        if default_storage.exists(path):
            css = default_storage.open(path).read().decode("utf-8")
            if css_delimeter in css:
                css = css.split(css_delimeter)[0]
            self.initial[self.get_input_css()] = css

    def save(self, commit=True):
        self.instance.css_code = generate_id(32)
        instance = super(MyForm, self).save()
        self.save_css(instance)
        return instance

    def save_css(self, instance: Event | Association) -> None:
        """Save CSS content to file with automatic styling additions.

        Generates and saves CSS content by combining user-defined styles with
        automatic styling based on instance properties (background, font, colors).

        Args:
            instance: Model instance (either Event or Asssociation) containing styling configuration data.
                Expected to have attributes: background, background_red, font,
                slug, pri_rgb, sec_rgb, ter_rgb.

        Returns:
            None: Saves CSS file to storage, no return value.
        """
        # Get file path and base CSS content from form data
        path = self.get_css_path(instance)
        css = self.cleaned_data[self.get_input_css()]
        css += css_delimeter

        # Add background image styling if instance has background
        if instance.background:
            css += f"""body {{
                background-image: url('{instance.background_red.url}');
           }}"""

        # Add custom font face and header styling if font is specified
        if instance.font:
            css += f"""@font-face {{
                font-family: '{instance.slug}';
                src: url('{conf_settings.MEDIA_URL}/{instance.font}');
                font-display: swap;
           }}"""
            css += f"""h1, h2 {{
                font-family: {instance.slug};
           }}"""

        # Add CSS custom properties for color themes
        if instance.pri_rgb:
            css += f":root {{--pri-rgb: {hex_to_rgb(instance.pri_rgb)}; }}"
        if instance.sec_rgb:
            css += f":root {{--sec-rgb: {hex_to_rgb(instance.sec_rgb)}; }}"
        if instance.ter_rgb:
            css += f":root {{--ter-rgb: {hex_to_rgb(instance.ter_rgb)}; }}"

        # Save generated CSS content to storage
        default_storage.save(path, ContentFile(css))

    @staticmethod
    def get_css_path(instance):
        return ""

    @staticmethod
    def get_input_css():
        return ""


class BaseAccForm(forms.Form):
    """Base form class for accounting and payment processing.

    Handles payment method selection and fee configuration
    for association-specific accounting operations.
    """

    def __init__(self, *args, **kwargs):
        self.ctx = kwargs.pop("ctx")
        super().__init__(*args, **kwargs)
        self.methods = self.ctx["methods"]
        cho = []
        for s in self.methods:
            cho.append((s, self.methods[s]["name"]))
        self.fields["method"] = forms.ChoiceField(choices=cho)

        self.ctx["user_fees"] = get_assoc_config(self.ctx["a_id"], "payment_fees_user", False)
