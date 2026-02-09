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

import logging
from typing import TYPE_CHECKING, Any

from django import forms
from django.conf import settings as conf_settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms

from larpmanager.cache.config import get_association_config
from larpmanager.forms.utils import ReadOnlyWidget, WritingTinyMCE, css_delimeter
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.form import (
    BaseQuestionType,
    QuestionStatus,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
    WritingQuestionType,
    get_writing_max_length,
)
from larpmanager.models.registration import RegistrationTicket
from larpmanager.models.utils import generate_id, get_attr, strip_tags
from larpmanager.templatetags.show_tags import hex_to_rgb

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from larpmanager.models.base import BaseModel

logger = logging.getLogger(__name__)


class FormMixin:
    """Mixin for common form operations."""

    def configure_field_event(self, field_name: str, event: Event) -> None:
        """Configure a form field's widget and queryset for a specific event."""
        field = self.fields[field_name]
        field.widget.set_event(event)
        field.queryset = field.widget.get_queryset()

    def configure_field_association(self, field_name: str, association_id: int) -> None:
        """Configure a form field's widget and queryset for a specific association."""
        field = self.fields[field_name]
        field.widget.set_association_id(association_id)
        field.queryset = field.widget.get_queryset()

    def configure_field_run(self, field_name: str, run: Run) -> None:
        """Configure a form field's widget and queryset for a specific run."""
        field = self.fields[field_name]
        field.widget.set_run(run)
        field.queryset = field.widget.get_queryset()

    def delete_field(self, field_key: str) -> None:
        """Remove a field from the form if it exists."""
        if field_key in self.fields:
            del self.fields[field_key]


class BaseForm(FormMixin, forms.Form):
    """Base for all non-models form."""


class BaseModelForm(FormMixin, forms.ModelForm):
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
                - context: Context data dictionary
                - run: Run instance for form context
                - request: HTTP request object

        Note:
            Automatically removes 'deleted' and 'temp' fields if present.
            Sets up character widget with event context when available.
            Configures automatic fields as hidden or removes them based on instance state.

        """
        # Initialize parent class and extract context parameters
        super().__init__()
        if "context" in kwargs:
            self.params = kwargs.pop("context")
        else:
            self.params = {}

        # Extract run and request parameters if provided
        for k in ["run", "request"]:
            if k in kwargs:
                self.params[k] = kwargs.pop(k)

        # Call parent ModelForm initialization with remaining arguments
        super(forms.ModelForm, self).__init__(*args, **kwargs)

        # Set to use uuid
        for field in self.fields.values():
            # Check if field is a ModelChoiceField / ModelMultipleChoiceField
            if isinstance(field, forms.ModelChoiceField):
                # Skip if it's a Select2 widget
                if isinstance(field.widget, (s2forms.ModelSelect2Widget, s2forms.ModelSelect2MultipleWidget)):
                    continue

                field.to_field_name = "uuid"

        # Remove system fields that shouldn't be user-editable
        for m in ["deleted", "temp"]:
            self.delete_field(m)

        # Configure characters field widget with event context
        if "characters" in self.fields:
            self.configure_field_event("characters", self.params.get("event"))

        # Handle automatic fields based on instance state
        self.handle_automatic()

        # Initialize tracking dictionaries for form state management
        self.mandatory = []
        self.answers = {}
        self.singles = {}
        self.multiples = {}
        self.unavail = {}
        self.max_lengths = {}

    def handle_automatic(self) -> None:
        """Handle automatic fields, that should be automatically populated."""
        for s in self.get_automatic_field():
            if s in self.fields:
                if self.instance.pk:
                    # Remove automatic fields for existing instances
                    self.delete_field(s)
                else:
                    # Hide automatic fields for new instances
                    self.fields[s].widget = forms.HiddenInput()
                    self.fields[s].required = False

    def get_automatic_field(self) -> Any:
        """Get list of fields that should be automatically populated."""
        automatic_fields = ["event", "association"]
        if hasattr(self, "auto_run"):
            automatic_fields.extend(["run"])
        return automatic_fields

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
        available_runs = Run.objects.filter(event=self.params.get("event"))

        # If campaign switch is active, expand to include related events
        if get_association_config(
            self.params.get("event").association_id, "campaign_switch", default_value=False, context=self.params
        ):
            # Start with current event ID
            related_event_ids = {self.params.get("event").id}

            # Add child events
            child_event_ids = Event.objects.filter(parent_id=self.params.get("event").id).values_list("pk", flat=True)
            related_event_ids.update(child_event_ids)

            # Add parent and sibling events if current event has a parent
            if self.params.get("event").parent_id:
                related_event_ids.add(self.params.get("event").parent_id)
                sibling_event_ids = Event.objects.filter(parent_id=self.params["event"].parent_id).values_list(
                    "pk",
                    flat=True,
                )
                related_event_ids.update(sibling_event_ids)

            # Filter runs by all related event IDs
            available_runs = Run.objects.filter(event_id__in=related_event_ids)

        # Optimize query and order by end date
        available_runs = available_runs.select_related("event").order_by("end")

        # Handle field visibility based on number of available runs
        if len(available_runs) <= 1:
            # For both existing and new instances, remove field entirely
            self.delete_field("run")
            # Store the run value for clean_run()
            self._auto_run_value = self.params["run"]
        else:
            # Multiple runs available
            self.fields["run"] = forms.ChoiceField(
                choices=[(run.uuid, str(run)) for run in available_runs],
                required=self.fields["run"].required,
                label=self.fields["run"].label,
                help_text=self.fields["run"].help_text,
            )
            # Set initial value from existing instance or current run parameter
            if self.instance.pk and hasattr(self.instance, "run") and self.instance.run:
                self.initial["run"] = self.instance.run.uuid
            else:
                self.initial["run"] = self.params["run"].uuid
            # noinspection PyUnresolvedReferences
            del self.auto_run

    def clean_run(self) -> Run:
        """Return the appropriate Run instance based on form configuration."""
        # Use params if auto_run is set, otherwise use cleaned form data
        if hasattr(self, "auto_run"):
            return self.params["run"]

        # Get the value from cleaned_data
        run_value = self.cleaned_data["run"]

        if not run_value:
            return None

        # If it's already a Run instance, return it
        if not isinstance(run_value, Run):
            # Otherwise, it's a UUID (from ChoiceField), convert to Run instance
            try:
                run_value = Run.objects.select_related("event").get(uuid=run_value)
            except ObjectDoesNotExist as err:
                msg = _("Select a valid choice. That choice is not one of the available choices.")
                raise ValidationError(msg) from err

        # Validate run belongs to current association
        if "event" in self.params and run_value.event.association_id != self.params["event"].association_id:
            msg = _("Selected event does not belong to this organization")
            raise ValidationError(msg)

        return run_value

    def clean_event(self) -> Event:
        """Return the appropriate event based on form configuration.

        Returns event directly if choose_event exists, otherwise returns parent event
        based on element type.
        """
        # Return selected event if form has choose_event field
        if hasattr(self, "choose_event"):
            return self.cleaned_data["event"]

        # Get parent event based on element type from params
        typ = self.params["elementTyp"]
        return self.params["event"].get_class_parent(typ)

    def clean_association(self) -> Association:
        """Return association from params."""
        return Association.objects.get(pk=self.params["association_id"])

    def clean_name(self) -> str:
        """Validate that the name is unique within the event."""
        return self._validate_unique_event("name")

    def clean_display(self) -> str:
        """Validate display field uniqueness within event."""
        return self._validate_unique_event("display")

    def _validate_unique_event(self, field_name: str) -> Any:
        """Validate field uniqueness within event scope.

        This method ensures that a field value is unique within the context of a specific
        event or association, preventing duplicate entries that could cause conflicts.

        Args:
            field_name: Name of the field to validate for uniqueness

        Returns:
            any: The validated field value if unique

        Raises:
            ValidationError: If the value is not unique within the event scope

        """
        # Get the field value and event context parameters
        field_value = self.cleaned_data.get(field_name)
        event = self.params.get("event")
        element_type = self.params.get("elementTyp")

        if event and element_type:
            # Determine the appropriate event ID based on the element type
            parent_event_id = event.get_class_parent(element_type).id

            # Build the base queryset for uniqueness checking
            model = self._meta.model
            if model == Event:
                # For Event model, filter by association ID
                queryset = model.objects.filter(**{field_name: field_value}, association_id=event.association_id)
            else:
                # For other models, filter by event ID
                queryset = model.objects.filter(**{field_name: field_value}, event_id=parent_event_id)

            # Apply additional filters if question context exists and model has question field
            question = self.params.get("question")
            if question and hasattr(model, "question"):
                queryset = queryset.filter(question_id=question.id)

            # Filter by applicability if the check method exists
            if hasattr(self, "check_applicable"):
                queryset = queryset.filter(applicable=self.check_applicable)

            # Exclude current instance from uniqueness check during updates
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            # Raise validation error if duplicate exists
            if queryset.exists():
                raise ValidationError(field_name.capitalize() + " " + _("already used"))

        return field_value

    def save(self, commit: bool = True) -> BaseModel:  # noqa: FBT001, FBT002
        """Save form instance with custom field handling."""
        # Handle auto run
        if hasattr(self, "_auto_run_value"):
            self.instance.run = self._auto_run_value

        # Call parent save method to get the instance
        instance = super(forms.ModelForm, self).save(commit=commit)

        # Process each field in the form
        for field in self.fields:
            # Skip custom fields if they exist
            if hasattr(self, "custom_field") and field in self.custom_field:
                continue

            # Handle multi-select widgets specially
            if isinstance(self.fields[field].widget, s2forms.ModelSelect2MultipleWidget):
                self._save_multi(field, instance)

        return instance

    def _save_multi(self, field: str, instance: Any) -> None:
        """Save many-to-many field relationships for a model instance.

        Compares the initial values with cleaned form data to determine
        which relationships to add or remove, then updates the instance
        accordingly.

        Args:
            field: The field name for the many-to-many relationship
            instance: The model instance to update

        """
        # Get the initial set of related object primary keys
        if field in self.initial:
            old = set()
            for el in self.initial[field]:
                if hasattr(el, "pk"):
                    old.add(el.pk)
                else:
                    old.add(str(el))
        else:
            old = set()

        # Get the new set of primary keys from cleaned form data
        new = set(self.cleaned_data[field].values_list("pk", flat=True))

        # Get the attribute manager for the many-to-many field
        attr = get_attr(instance, field)

        # Remove relationships that are no longer selected
        for ch in old - new:
            attr.remove(ch)

        # Add new relationships that were selected
        for ch in new - old:
            attr.add(ch)


class BaseModelFormRun(BaseModelForm):
    """Form class for run-specific operations.

    Extends MyForm with automatic run handling functionality.
    Sets auto_run to True by default for run-related forms.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with auto_run flag enabled."""
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

    def validator(selected_values: list) -> None:
        """Validate that selected values do not exceed maximum allowed choices."""
        # Check if the number of selected values exceeds the maximum allowed
        if len(selected_values) > max_choices:
            # Raise validation error with localized message
            raise ValidationError(_("You have exceeded the maximum number of selectable options"))

    return validator


def max_length_validator(maximum_allowed_length: int) -> callable:
    """Create a validator that limits text length after stripping HTML tags.

    This validator removes HTML tags from the input text before checking length,
    ensuring that HTML markup doesn't count toward the character limit.

    Args:
        maximum_allowed_length: Maximum allowed text length after HTML stripping.

    Returns:
        A validator function that raises ValidationError if text exceeds maximum_allowed_length.

    Raises:
        ValidationError: When stripped text length exceeds the maximum allowed.

    """

    def validator(html_value: str) -> None:
        """Validate that plain text length does not exceed maximum_allowed_length."""
        # Strip HTML tags from the input value to get plain text
        plain_text = strip_tags(html_value)

        # Check if the plain text exceeds the maximum allowed length
        if len(plain_text) > maximum_allowed_length:
            raise ValidationError(_("You have exceeded the maximum text length"))

    return validator


def get_question_key(question: BaseModel) -> str:
    """Gets the key of a form custom question."""
    return f"que_{question.uuid}"


class BaseRegistrationForm(BaseModelFormRun):
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
    instance_key = "registration_id"

    class Meta:
        abstract = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with link tracking and section structures."""
        super().__init__(*args, **kwargs)
        # Track visible links for form navigation
        self.show_link = []
        # Store form sections organized by category
        self.sections = {}

    def _init_registration_question(self, instance: Any | None, event: Event) -> None:
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
            for answer in self.answer_class.objects.filter(**{self.instance_key: instance.id}):
                self.answers[answer.question_id] = answer

            # Populate choice dictionaries with existing single/multiple choice answers
            for choice_answer in self.choice_class.objects.filter(**{self.instance_key: instance.id}).select_related(
                "question",
            ):
                # Handle single choice questions - store the selected choice
                if choice_answer.question.typ == BaseQuestionType.SINGLE:
                    self.singles[choice_answer.question_id] = choice_answer
                # Handle multiple choice questions - store as a set of selected choices
                elif choice_answer.question.typ == BaseQuestionType.MULTIPLE:
                    if choice_answer.question_id not in self.multiples:
                        self.multiples[choice_answer.question_id] = set()
                    self.multiples[choice_answer.question_id].add(choice_answer)

        # Initialize choices dictionary for all available options
        self.choices = {}

        # Load all available choice options for this event's questions
        for question_option in self.get_options_query(event):
            # Group options by question ID for easy lookup during form rendering
            if question_option.question_id not in self.choices:
                self.choices[question_option.question_id] = []
            self.choices[question_option.question_id].append(question_option)

        # Finalize question initialization with event context
        self._init_questions(event)

    def _init_questions(self, event: Event) -> None:
        """Initialize questions for the given event."""
        self.questions = self.question_class.get_instance_questions(event, self.params["features"])

    def get_options_query(self, event: Event) -> QuerySet:
        """Return ordered options for questions in the given event."""
        return self.option_class.objects.filter(question__event=event).order_by("order")

    def get_choice_options(
        self,
        all_options: dict,
        question: RegistrationQuestion,
        chosen_options: list | None = None,
        registration_count: dict | None = None,
    ) -> tuple[list[tuple], str]:
        """Build form choice options for a question with availability and ticket validation.

        Processes available options for a registration question, applying availability
        constraints and ticket validation rules to generate valid form choices.

        Args:
            all_options: Dictionary mapping question IDs to their available option lists
            question: Question instance to retrieve and process options for
            chosen_options: Previously selected options for validation checks
            registration_count:  Registration count data used for availability verification

        Returns:
            tuple[list[tuple], str]: A tuple containing:
                - List of (option_id, display_name) tuples for form choices
                - Combined help text string with question description and option details

        """
        choices = []
        help_text = question.description

        # Early return if no options available for this question
        if question.id not in all_options:
            return choices, help_text

        available_options = all_options[question.id]

        # Process each available option for the question
        for option in available_options:
            # Generate display text with pricing information
            option_display_name = option.get_form_text(currency_symbol=self.params.get("currency_symbol", ""))

            # Check availability constraints if registration counts provided
            if registration_count and option.max_available > 0:
                option_display_name, is_valid = self.check_option(
                    chosen_options, option_display_name, option, registration_count
                )
                if not is_valid:
                    continue

            # Validate ticket compatibility if ticket mapping exists
            if registration_count and hasattr(option, "tickets_map"):
                valid_ticket_ids = [ticket_id for ticket_id in option.tickets_map if ticket_id is not None]
                registration = self.params.get("registration")
                if valid_ticket_ids and registration and registration.ticket_id not in valid_ticket_ids:
                    continue

            # Add valid option to choices and append description to help text
            choices.append((str(option.uuid), option_display_name))
            if option.description:
                help_text += f'<p id="hp_{option.uuid!s}"><b>{option.name}</b> {option.description}</p>'

        return choices, help_text

    def check_option(
        self,
        previously_chosen_options: list,
        display_name: str,
        option: RegistrationOption,
        registration_count_by_option: dict,
    ) -> tuple[str, bool]:
        """Check option availability and update display name with availability info.

        Verifies if an option is available for selection based on current registrations
        and maximum capacity. Updates the display name to show availability count.

        Args:
            previously_chosen_options: List of previously chosen options for the current registration
            display_name: Display name for the option to be potentially modified
            option: Option instance to check for availability
            registration_count_by_option: Dictionary containing registration count data by option key

        Returns:
            tuple[str, bool]: A tuple containing:
                - updated_name: Display name with availability info appended
                - is_valid: Boolean indicating if the option is valid/available

        """
        # Check if this option was already chosen by the user
        option_already_chosen = False
        is_valid = True

        if previously_chosen_options:
            for choice in previously_chosen_options:
                if choice.option_id == option.id:
                    option_already_chosen = True

        # If option wasn't previously chosen, check availability
        if not option_already_chosen:
            # Get the registration count key for this option
            option_key = self.get_option_key_count(option)
            remaining_availability = option.max_available

            # Calculate remaining availability based on current registrations
            if option_key in registration_count_by_option:
                remaining_availability -= registration_count_by_option[option_key]

            # Handle unavailable options or add availability info to name
            if remaining_availability <= 0:
                # Track unavailable options by question ID
                if option.question.uuid not in self.unavail:
                    self.unavail[option.question.uuid] = []
                self.unavail[option.question.uuid].append(str(option.uuid))
            else:
                # Append availability count to the display name
                display_name += " - (" + _("Available") + f" {remaining_availability})"

        return display_name, is_valid

    def _validate_multiple_choice(self, form_data: dict, question: BaseModel, field_key: str) -> None:
        """Validate multiple choice question selections.

        Args:
            form_data: Form data dictionary
            question: Question to validate
            field_key: Form field key for this question
        """
        for sel in form_data[field_key]:
            # Skip empty selections
            if not sel:
                continue

            # Check if selected option is unavailable
            if question.uuid in self.unavail and sel in self.unavail[question.uuid]:
                self.add_error(field_key, _("Option no longer available"))

    def _validate_single_choice(self, form_data: dict, question: BaseModel, field_key: str) -> None:
        """Validate single choice question selection.

        Args:
            form_data: Form data dictionary
            question: Question to validate
            field_key: Form field key for this question
        """
        # Skip empty selections
        if not form_data[field_key]:
            return

        # Check if selected option is unavailable
        if question.uuid in self.unavail and form_data[field_key] in self.unavail[question.uuid]:
            self.add_error(field_key, _("Option no longer available"))

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
            for question in self.questions:
                key = get_question_key(question)

                # Skip if this question's data is not in the form submission
                if key not in form_data:
                    continue

                # Handle multiple choice questions
                if question.typ == BaseQuestionType.MULTIPLE:
                    self._validate_multiple_choice(form_data, question, key)

                # Handle single choice questions
                elif question.typ == BaseQuestionType.SINGLE:
                    self._validate_single_choice(form_data, question, key)

        return form_data

    def clean_ticket(self) -> RegistrationTicket:
        """Get ticket and validate it belongs to the current run's event."""
        ticket_value = self.cleaned_data.get("ticket")
        try:
            return RegistrationTicket.objects.get(uuid=ticket_value, event_id=self.params["run"].event_id)
        except ObjectDoesNotExist as err:
            msg = _("Invalid ticket selection")
            raise ValidationError(msg) from err

    def get_option_key_count(self, option: BaseModel) -> str:
        """Generate counting key for option availability tracking.

        This method creates a unique identifier string used to track the usage
        count of a specific option in the system's availability monitoring.

        Args:
            option: The option instance for which to generate the tracking key.

        Returns:
            str: A formatted key string in the format "option_{id}" used for
            tracking option usage counts.

        """
        # Generate unique key using option ID for tracking purposes
        return f"option_{option.id}"

    def init_orga_fields(self, registration_section: str | None = None) -> list[str]:
        """Initialize form fields for organizer view with registration questions.

        This method processes registration questions for an event and creates
        corresponding form fields that organizers can use to manage registrations.
        It filters questions based on availability and permissions.

        Args:
            registration_section: Optional registration section name to override the
                        question's default section assignment.

        Returns:
            List of initialized field keys that were successfully created.

        """
        # Get the event from the current run context
        event = self.params["run"].event
        self._init_registration_question(self.instance, event)

        # Initialize container for field keys that will be created
        field_keys = []

        # Process each registration question for field creation
        for question in self.questions:
            # Skip questions that don't meet visibility/permission criteria
            if question.skip(self.instance, self.params["features"], self.params, is_organizer=True):
                continue

            # Create form field for this question (organizer context)
            field_key = self._init_field(question, registration_counts=None, is_organizer=True)
            if not field_key:
                continue

            # Add the field key to our collection
            field_keys.append(field_key)

            # Determine section name for field grouping
            section_name = registration_section
            if hasattr(question, "section") and question.section:
                section_name = question.section.name

            # Assign field to section if section name is available
            if section_name:
                self.sections["id_" + field_key] = section_name

        return field_keys

    def check_editable(self, registration_question: RegistrationQuestion) -> bool:  # noqa: ARG002
        """Always allow editing."""
        return True

    def _init_field(
        self,
        question: RegistrationQuestion,
        registration_counts: dict[str, Any] | None = None,
        *,
        is_organizer: bool = True,
    ) -> str | None:
        """Initialize form field for a writing question.

        Creates and configures a form field based on the writing question type and settings.
        Handles different question statuses, validation requirements, and organizer vs user contexts.

        Args:
            question: WritingQuestion instance to create field for
            registration_counts: Registration count data for field initialization, defaults to None
            is_organizer: Whether this is an organizer form, defaults to True

        Returns:
            Form field key string if field was created, None if question was skipped
            (computed questions or non-editable questions for users)

        """
        # Skip computed questions entirely - they don't need form fields
        if question.typ == WritingQuestionType.COMPUTED:
            return None

        # Generate unique field key based on question UUID
        field_key = get_question_key(question)

        # Set default field states for organizer context
        is_field_active = True
        is_required = False

        # Apply user-specific field logic when not in organizer mode
        if not is_organizer:
            # Check if question is editable for current user context
            if not self.check_editable(question):
                return None

            # Hide questions marked as hidden from users
            if question.status == QuestionStatus.HIDDEN:
                return None

            # Disable fields for disabled questions or creation-only questions
            if question.status == QuestionStatus.DISABLED:
                is_field_active = False
            else:
                # Set field as required based on question status
                is_required = question.status == QuestionStatus.MANDATORY

        # Initialize field type and apply type-specific configuration
        field_key = self.init_type(
            field_key,
            question,
            registration_counts,
            is_organizer=is_organizer,
            is_required=is_required,
            is_field_active=is_field_active,
        )
        if not field_key:
            return field_key

        # Apply user-specific field state (disabled/enabled)
        if not is_organizer:
            self.fields[field_key].disabled = not is_field_active

        # Configure max length validation for applicable question types
        if question.max_length and question.typ in get_writing_max_length():
            self.max_lengths[f"id_{field_key}"] = (question.max_length, question.typ)

        # Mark mandatory fields with visual indicator and track for validation
        if question.status == QuestionStatus.MANDATORY:
            self.fields[field_key].label += " (*)"
            self.has_mandatory = True
            self.mandatory.append("id_" + field_key)

        # Set basic type flag for template rendering logic
        question.basic_typ = question.typ in BaseQuestionType.get_basic_types()

        return field_key

    def init_type(
        self,
        field_key: str,
        question: RegistrationQuestion,
        registration_counts: dict,
        *,
        is_organizer: bool,
        is_required: bool,
        is_field_active: bool = True,
    ) -> str:
        """Initialize form field based on question type.

        Creates and configures the appropriate form field type based on the question's
        type attribute. Handles multiple choice, single choice, text input, paragraph,
        editor, and special question types.

        Args:
            field_key: Field key identifier used to reference the form field
            is_organizer: Organization context flag indicating organizational scope
            question: Question object containing type and configuration information
            registration_counts: Dictionary containing registration count data for choices
            is_required: Whether the field should be marked as required
            is_field_active: Whether the field can be changed by the user

        Returns:
            The field key identifier, potentially modified for special question types

        Note:
            For special question types, the key may be replaced with a new identifier
            generated by the init_special method.

        """
        # Handle multiple choice questions (checkboxes, multi-select)
        if question.typ == BaseQuestionType.MULTIPLE:
            self.init_multiple(
                field_key, question, registration_counts, is_organizer=is_organizer, is_required=is_required
            )

        # Handle single choice questions (radio buttons, dropdowns)
        elif question.typ == BaseQuestionType.SINGLE:
            self.init_single(
                field_key, question, registration_counts, is_organizer=is_organizer, is_required=is_required
            )

        # Handle simple text input fields
        elif question.typ == BaseQuestionType.TEXT:
            self.init_text(field_key, question, is_required=is_required, is_field_active=is_field_active)

        # Handle multi-line text areas
        elif question.typ == BaseQuestionType.PARAGRAPH:
            self.init_paragraph(field_key, question, is_required=is_required, is_field_active=is_field_active)

        # Handle rich text editor fields
        elif question.typ == BaseQuestionType.EDITOR:
            self.init_editor(field_key, question, is_required=is_required, is_field_active=is_field_active)

        # Handle special question types (custom implementations)
        else:
            field_key = self.init_special(question, is_required=is_required)

        # Assign the key attribute to the created field for reference
        if field_key:
            self.fields[field_key].key = field_key

        return field_key

    def init_special(self, question: RegistrationQuestion, *, is_required: bool) -> str | None:
        """Initialize special form field configurations.

        Configures special form fields based on the question type, mapping certain
        question types to their corresponding field names and applying question
        properties like label, help text, and validation rules.

        Args:
            question: Question object containing type, name, description, and
                     validation configuration data
            is_required: Whether the field should be marked as required

        Returns:
            The field key if successfully initialized, None if the field
            doesn't exist in the form

        """
        # Get the field key, either directly from question type or mapped
        field_key = question.typ
        question_type_to_field_mapping = {
            "faction": "factions_list",
            "additional_tickets": "additionals",
            "pay_what_you_want": "pay_what",
            "reg_quotas": "quotas",
            "reg_surcharges": "surcharge",
        }

        # Use mapped key if available, otherwise use original type
        if field_key in question_type_to_field_mapping:
            field_key = question_type_to_field_mapping[field_key]

        # Early return if field doesn't exist in form
        if field_key not in self.fields:
            return None

        # Configure basic field properties from question data
        self.fields[field_key].label = question.name
        self.fields[field_key].help_text = question.description
        self.reorder_field(field_key)
        self.fields[field_key].required = is_required

        # Apply length validation for text-based fields
        if field_key in ["name", "teaser", "text"]:
            self.fields[field_key].validators = (
                [max_length_validator(question.max_length)] if question.max_length else []
            )

        return field_key

    def init_editor(
        self, field_key: str, question: RegistrationQuestion, *, is_required: bool, is_field_active: bool = True
    ) -> None:
        """Initialize a TinyMCE editor field for a form question.

        Args:
            field_key: The field key/name to use in the form
            question: Question object containing field configuration
            is_required: Whether the field is required
            is_field_active: Whether the field should be editable (if False, shows as read-only HTML)

        """
        # Set up validators based on question configuration
        length_validators = [max_length_validator(question.max_length)] if question.max_length else []

        # Choose widget based on whether field is active
        widget = WritingTinyMCE() if is_field_active else ReadOnlyWidget()

        # Create the CharField with widget
        self.fields[field_key] = forms.CharField(
            required=is_required,
            widget=widget,
            label=question.name,
            help_text=question.description,
            validators=length_validators,
        )

        # Set initial value if answer exists
        if question.id in self.answers:
            self.initial[field_key] = self.answers[question.id].text

        # Add field to show_link list for frontend handling only if active
        if is_field_active:
            self.show_link.append(f"id_{field_key}")

    def init_paragraph(
        self, field_key: str, question_config: RegistrationQuestion, *, is_required: bool, is_field_active: bool = True
    ) -> None:
        """Initialize a paragraph text field for the form.

        Args:
            field_key: Form field key
            question_config: Question object with configuration
            is_required: Whether field is required
            is_field_active: Whether the field should be editable (if False, shows as read-only HTML)

        """
        # Configure validators based on question settings
        length_validators = [max_length_validator(question_config.max_length)] if question_config.max_length else []

        # Choose widget based on whether field is active
        widget = forms.Textarea(attrs={"rows": 4}) if is_field_active else ReadOnlyWidget()

        # Create textarea field with question properties
        self.fields[field_key] = forms.CharField(
            required=is_required,
            widget=widget,
            label=question_config.name,
            help_text=question_config.description,
            validators=length_validators,
        )

        # Set initial value if answer exists
        if question_config.id in self.answers:
            self.initial[field_key] = self.answers[question_config.id].text

    def init_text(
        self, field_key: str, form_question: RegistrationQuestion, *, is_required: bool, is_field_active: bool = True
    ) -> None:
        """Initialize a text field with validators and initial values.

        Args:
            field_key: The field key/name to use in the form
            form_question: Question object containing field configuration
            is_required: Whether the field is required
            is_field_active: Whether the field should be editable (if False, shows as read-only text)
        """
        # Create validators based on max_length constraint
        field_validators = [max_length_validator(form_question.max_length)] if form_question.max_length else []

        # Choose widget based on whether field is active
        widget = forms.TextInput() if is_field_active else ReadOnlyWidget()

        # Create the form field with proper configuration
        self.fields[field_key] = forms.CharField(
            required=is_required,
            widget=widget,
            label=form_question.name,
            help_text=form_question.description,
            validators=field_validators,
        )

        # Set initial value if answer exists
        if form_question.id in self.answers:
            self.initial[field_key] = self.answers[form_question.id].text

    def init_single(
        self,
        field_key: str,
        question: RegistrationQuestion,
        registration_counts: dict,
        *,
        is_organizer: bool,
        is_required: bool,
    ) -> None:
        """Initialize single choice form field.

        Args:
            field_key: Form field key for the choice field
            is_organizer: Whether this is an organizational form context
            question: Question object containing choices configuration and metadata
            registration_counts: Registration counts dictionary for quota tracking
            is_required: Whether the field is required for form validation

        Side Effects:
            - Creates and adds a single choice field to self.fields
            - Sets initial value in self.initial if a previous selection exists

        """
        if is_organizer:
            # Get choice options for organizational context
            (available_choices, help_text) = self.get_choice_options(self.choices, question)

            # Add default "Not selected" option if no previous selection exists
            if question.id not in self.singles:
                available_choices.insert(0, (0, "--- " + _("Not selected")))
        else:
            # Prepare list of previously chosen options for user context
            previously_chosen_options = []
            if question.id in self.singles:
                previously_chosen_options.append(self.singles[question.id])

            # Get choice options with quota tracking for user registration
            (available_choices, help_text) = self.get_choice_options(
                self.choices,
                question,
                previously_chosen_options,
                registration_counts,
            )

        # Create the choice field with determined options and configuration
        self.fields[field_key] = forms.ChoiceField(
            required=is_required,
            choices=available_choices,
            label=question.name,
            help_text=help_text,
        )

        # Set initial value from previous selection if it exists and is still valid
        if question.id in self.singles and self.singles[question.id].option:
            option_uuid_str = str(self.singles[question.id].option.uuid)
            # Only set initial value if the option is still available in the current context
            if any(choice[0] == option_uuid_str for choice in available_choices):
                self.initial[field_key] = option_uuid_str

    def init_multiple(
        self,
        field_key: str,
        question: RegistrationQuestion,
        registration_counts: dict,
        *,
        is_organizer: bool,
        is_required: bool,
    ) -> None:
        """Set up multiple choice form field handling.

        Creates a multiple choice field with checkboxes for form questions that allow
        multiple selections. Handles both organizational and regular forms with
        different choice option processing.

        Args:
            field_key: Form field identifier used as the field name
            question: Question object containing choices configuration and metadata
            registration_counts: Dictionary mapping registration types to their current counts
                       for quota tracking purposes
            is_organizer: True if this is an organizational form, False for regular forms
            is_required: True if the field must be filled, False if optional

        Side Effects:
            - Creates a MultipleChoiceField in self.fields[field_key]
            - Sets initial values in self.initial[field_key] if previous selections exist
            - Applies max_selections_validator if question has max_length limit

        """
        # Process choice options differently for organizational vs regular forms
        if is_organizer:
            (available_choices, help_text) = self.get_choice_options(self.choices, question)
        else:
            previously_selected_choices = []
            # Retrieve previously selected choices if they exist
            if question.id in self.multiples:
                previously_selected_choices = self.multiples[question.id]
            (available_choices, help_text) = self.get_choice_options(
                self.choices,
                question,
                previously_selected_choices,
                registration_counts,
            )

        # Add validator for maximum selection limit if specified
        field_validators = [max_selections_validator(question.max_length)] if question.max_length else []

        # Create the multiple choice field with checkbox widget
        self.fields[field_key] = forms.MultipleChoiceField(
            required=is_required,
            choices=available_choices,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"}),
            label=question.name,
            help_text=help_text,
            validators=field_validators,
        )

        # Set initial values from previously selected options that are still available
        if question.id in self.multiples:
            available_choice_uuids = {choice[0] for choice in available_choices}
            initial_option_uuids = [
                str(selected_choice.option.uuid)
                for selected_choice in self.multiples[question.id]
                if selected_choice.option and str(selected_choice.option.uuid) in available_choice_uuids
            ]
            self.initial[field_key] = initial_option_uuids

    def reorder_field(self, field_name: str) -> None:
        """Move field to end of fields dictionary."""
        # Remove field from current position and re-add at the end
        field = self.fields.pop(field_name)
        self.fields[field_name] = field

    def save_registration_questions(self, instance: Any, *, is_organizer: Any = True) -> None:
        """Save registration question answers to database.

        Args:
            instance: Registration instance to save answers for
            is_organizer (bool): Whether to save organizational questions

        """
        for question in self.questions:
            if question.skip(instance, self.params["features"], self.params, is_organizer=is_organizer):
                continue

            key = get_question_key(question)
            if key not in self.cleaned_data:
                continue
            oid = self.cleaned_data[key]

            if question.typ == BaseQuestionType.MULTIPLE:
                self.save_registration_multiple(instance, oid, question)
            elif question.typ == BaseQuestionType.SINGLE:
                self.save_registration_single(instance, oid, question)
            elif question.typ in [BaseQuestionType.TEXT, BaseQuestionType.PARAGRAPH, BaseQuestionType.EDITOR]:
                self.save_registration_text(instance, oid, question)

    def save_registration_text(
        self,
        instance: Any,
        value: str | None,
        question: Any,
    ) -> None:
        """Save or update a text answer for a registration question.

        Args:
            instance: The registration/application instance to attach the answer to.
            value: The new text value to save, or None to delete the answer.
            question: The question object being answered.

        Notes:
            - Preserves disabled field values in organizer forms.
            - Only creates new answers when content is provided.

        """
        # Check if an answer already exists for this question
        if question.id in self.answers:
            if not value:
                # For disabled questions in organizer forms, don't delete existing answers
                # unless the organizer explicitly submitted an empty value for an editable field
                orga = getattr(self, "orga", False)
                is_disabled = hasattr(question, "status") and question.status == "d"

                # Keep existing value for disabled fields in organizer forms
                if orga and is_disabled:
                    pass
                else:
                    self.answers[question.id].delete()
            elif value != self.answers[question.id].text:
                # Update existing answer if the value has changed
                self.answers[question.id].text = value
                self.answers[question.id].save()
        elif value:
            # Only create new answers if there's actually content
            self.answer_class.objects.create(**{"question": question, self.instance_key: instance.id, "text": value})

    def save_registration_single(self, instance: Any, option_uuid: str | None, question: Any) -> None:
        """Save or update a single-choice question response.

        Args:
            instance: The parent instance (registration/application)
            option_uuid: The option UUID as string (or None)
            question: The question object

        """
        # Skip if no option UUID provided
        if not option_uuid:
            return

        # Look up option by UUID
        try:
            option = question.options.get(uuid=option_uuid)
        except ObjectDoesNotExist:
            # Option not found or invalid UUID
            return

        # Update existing choice: delete if requested, otherwise update option
        if question.id in self.singles:
            if self.singles[question.id].option_id != option.id:
                self.singles[question.id].option_id = option.id
                self.singles[question.id].save()
        # Create new choice
        else:
            self.choice_class.objects.create(
                **{"question": question, self.instance_key: instance.id, "option_id": option.id}
            )

    def save_registration_multiple(
        self,
        instance: Any,
        option_uuids: list[str] | None,
        question: Any,
    ) -> None:
        """Save multiple-choice registration answers by syncing selected options.

        Creates new choices for added options and deletes removed ones.
        """
        if not option_uuids:
            return

        # Convert option UUIDs to option IDs by looking them up
        uuid_to_id = {str(opt.uuid): opt.id for opt in question.options.all()}
        selected_option_ids = {uuid_to_id[uuid_str] for uuid_str in option_uuids if uuid_str in uuid_to_id}

        # If question already has existing choices, sync the differences
        if question.id in self.multiples:
            old = {el.option_id for el in self.multiples[question.id]}

            # Create new choices for added options
            for add in selected_option_ids - old:
                self.choice_class.objects.create(
                    **{"question": question, self.instance_key: instance.id, "option_id": add}
                )

            # Delete choices for removed options
            rem = old - selected_option_ids
            self.choice_class.objects.filter(
                **{"question": question, self.instance_key: instance.id, "option_id__in": rem},
            ).delete()
        else:
            # Create all choices from scratch if none exist
            for pkoid in selected_option_ids:
                self.choice_class.objects.create(
                    **{"question": question, self.instance_key: instance.id, "option_id": pkoid}
                )

    def clean_pay_what(self) -> Any:
        """Ensure pay_what has a valid integer value, defaulting to 0 if None or empty."""
        data = self.cleaned_data.get("pay_what")
        # Convert None or empty string to 0 to prevent NULL constraint violations
        return data if data is not None else 0


class BaseModelCssForm(BaseModelForm):
    """Form class for handling CSS customization.

    Manages CSS file upload, editing, and processing for styling
    customization with support for backgrounds, fonts, and color themes.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and load existing CSS from storage if instance exists."""
        super().__init__(*args, **kwargs)

        # Skip CSS loading for new instances
        if not self.instance.pk:
            return

        # Load and parse existing CSS file
        path = self.get_css_path(self.instance)
        if default_storage.exists(path):
            try:
                css = default_storage.open(path).read().decode("utf-8")
                # Extract CSS content before delimiter if present
                if css_delimeter in css:
                    css = css.split(css_delimeter)[0]
                self.initial[self.get_input_css()] = css
            except (OSError, UnicodeDecodeError, PermissionError):
                logger.exception("Failed to load CSS file")
                # Continue without loading CSS - form will work with empty CSS

    def save(self, commit: bool = True) -> Any:  # noqa: FBT001, FBT002, ARG002
        """Save form instance with generated CSS code and custom CSS file.

        Args:
            commit: Whether to save the instance to the database.

        Returns:
            The saved model instance.

        """
        # Generate unique CSS identifier
        self.instance.css_code = generate_id(32)

        # Save instance and write CSS file
        instance = super(BaseModelForm, self).save()
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
    def get_css_path(association_skin: Association | Event) -> str:  # noqa: ARG004
        """Returns empty string (CSS path logic not implemented)."""
        return ""

    @staticmethod
    def get_input_css() -> str:
        """Return CSS class string for input styling."""
        return ""


class BaseAccForm(BaseForm):
    """Base form class for accounting and payment processing.

    Handles payment method selection and fee configuration
    for association-specific accounting operations.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with payment methods from context.

        Args:
            *args: Variable positional arguments passed to parent class.
            **kwargs: Variable keyword arguments including required 'context' key.

        """
        self.context = kwargs.pop("context")
        super().__init__(*args, **kwargs)

        # Build choices list from available payment methods
        self.methods = self.context["methods"]
        cho = [(s, self.methods[s]["name"]) for s in self.methods]
        self.fields["method"] = forms.ChoiceField(choices=cho)

        # Load payment fees configuration for the association
        self.context["user_fees"] = get_association_config(
            self.context["association_id"],
            "payment_fees_user",
            default_value=False,
            context=self.context,
        )
