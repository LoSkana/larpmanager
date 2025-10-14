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

    def __init__(self, *args, **kwargs):
        """Initialize form with optional context parameters.

        Args:
            *args: Positional arguments passed to parent ModelForm
            **kwargs: Keyword arguments, may include 'ctx' for context data
        """
        super().__init__()
        if "ctx" in kwargs:
            self.params = kwargs.pop("ctx")
        else:
            self.params = {}

        for k in ["run", "request"]:
            if k in kwargs:
                self.params[k] = kwargs.pop(k)

        super(forms.ModelForm, self).__init__(*args, **kwargs)

        for m in ["deleted", "temp"]:
            if m in self.fields:
                del self.fields[m]

        if "characters" in self.fields:
            self.fields["characters"].widget.set_event(self.params["event"])

        for s in self.get_automatic_field():
            if s in self.fields:
                if self.instance.pk:
                    del self.fields[s]
                else:
                    self.fields[s].widget = forms.HiddenInput()
                    self.fields[s].required = False

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

    def allow_run_choice(self):
        """Configure run selection field based on available runs.

        Sets up the run choice field, considering campaign switches and
        hiding the field if only one run is available.
        """
        runs = Run.objects.filter(event=self.params["event"])

        # if campaign switch is active, show as runs all of the events sharing the campaign
        if get_assoc_config(self.params["event"].assoc_id, "campaign_switch", False):
            event_ids = {self.params["event"].id}
            child = Event.objects.filter(parent_id=self.params["event"].id).values_list("pk", flat=True)
            event_ids.update(child)
            if self.params["event"].parent_id:
                event_ids.add(self.params["event"].parent_id)
                siblings = Event.objects.filter(parent_id=self.params["event"].parent_id).values_list("pk", flat=True)
                event_ids.update(siblings)

            runs = Run.objects.filter(event_id__in=event_ids)

        runs = runs.select_related("event").order_by("end")

        self.initial["run"] = self.params["run"].id
        if len(runs) <= 1:
            if self.instance.pk:
                self.delete_field("run")
            else:
                self.fields["run"].widget = forms.HiddenInput()
        else:
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

    def _validate_unique_event(self, field_name):
        """
        Validate field uniqueness within event scope.

        Args:
            field_name: Name of the field to validate for uniqueness

        Returns:
            value: Validated field value

        Raises:
            ValidationError: If value is not unique within the event
        """
        value = self.cleaned_data.get(field_name)
        event = self.params.get("event")
        typ = self.params.get("elementTyp")
        if event and typ:
            event_id = event.get_class_parent(typ).id

            model = self._meta.model
            if model == Event:
                qs = model.objects.filter(**{field_name: value}, assoc_id=event.assoc_id)
            else:
                qs = model.objects.filter(**{field_name: value}, event_id=event_id)
            question = self.cleaned_data.get("question")
            if question:
                qs = qs.filter(question_id=question.id)
            if hasattr(self, "check_applicable"):
                qs = qs.filter(applicable=self.check_applicable)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(field_name.capitalize() + " " + _("already used"))
        return value

    def save(self, commit=True):
        instance = super(forms.ModelForm, self).save(commit=commit)

        self.full_clean()

        for s in self.fields:
            if hasattr(self, "custom_field"):
                if s in self.custom_field:
                    continue
            if isinstance(self.fields[s].widget, s2forms.ModelSelect2MultipleWidget):
                self._save_multi(s, instance)

        return instance

    def _save_multi(self, s, instance):
        if s in self.initial:
            old = set()
            for el in self.initial[s]:
                if hasattr(el, "pk"):
                    old.add(el.pk)
                else:
                    old.add(int(el))
        else:
            old = set()
        new = set(self.cleaned_data[s].values_list("pk", flat=True))
        attr = get_attr(instance, s)
        for ch in old - new:
            attr.remove(ch)
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


def max_selections_validator(max_choices):
    """Create a validator that limits the number of selectable options.

    Args:
        max_choices (int): Maximum number of options that can be selected

    Returns:
        function: Validator function that raises ValidationError if exceeded
    """

    def validator(value):
        if len(value) > max_choices:
            raise ValidationError(_("You have exceeded the maximum number of selectable options"))

    return validator


def max_length_validator(max_length):
    """Create a validator that limits text length after stripping HTML tags.

    Args:
        max_length (int): Maximum allowed text length

    Returns:
        function: Validator function that raises ValidationError if exceeded
    """

    def validator(value):
        if len(strip_tags(value)) > max_length:
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

    def _init_reg_question(self, instance, event):
        """Initialize registration questions and answers from existing instance.

        Args:
            instance: Registration instance to load data from
            event: Event object for question context
        """
        if instance and instance.pk:
            for el in self.answer_class.objects.filter(**{self.instance_key: instance.id}):
                self.answers[el.question_id] = el

            for el in self.choice_class.objects.filter(**{self.instance_key: instance.id}).select_related("question"):
                if el.question.typ == BaseQuestionType.SINGLE:
                    self.singles[el.question_id] = el
                elif el.question.typ == BaseQuestionType.MULTIPLE:
                    if el.question_id not in self.multiples:
                        self.multiples[el.question_id] = set()
                    self.multiples[el.question_id].add(el)

        self.choices = {}

        for r in self.get_options_query(event):
            if r.question_id not in self.choices:
                self.choices[r.question_id] = []
            self.choices[r.question_id].append(r)

        self._init_questions(event)

    def _init_questions(self, event):
        self.questions = self.question_class.get_instance_questions(event, self.params["features"])

    def get_options_query(self, event):
        return self.option_class.objects.filter(question__event=event).order_by("order")

    def get_choice_options(self, all_options, question, chosen=None, reg_count=None):
        """
        Build form choice options for a question with availability and ticket validation.

        Args:
            all_options: Dictionary of all available options by question ID
            question: Question instance to get options for
            chosen: Previously chosen options (optional)
            reg_count: Registration count data for availability checking (optional)

        Returns:
            tuple: (choices list, help_text string)
        """
        choices = []
        help_text = question.description
        run = self.params["run"]

        if question.id not in all_options:
            return choices, help_text

        options = all_options[question.id]

        for option in options:
            name = option.get_form_text(run, cs=self.params["currency_symbol"])
            if reg_count and option.max_available > 0:
                name, valid = self.check_option(chosen, name, option, reg_count, run)
                if not valid:
                    continue

            if reg_count and hasattr(option, "tickets_map"):
                tickets_id = [i for i in option.tickets_map if i is not None]
                if tickets_id and run.reg.ticket_id not in tickets_id:
                    continue

            # no problem, go ahead
            choices.append((option.id, name))
            if option.description:
                help_text += f'<p id="hp_{option.id}"><b>{option.name}</b> {option.description}</p>'

        return choices, help_text

    def check_option(self, chosen, name, option, reg_count, run):
        """
        Check option availability and update display name with availability info.

        Args:
            chosen: Previously chosen options list
            name: Display name for the option
            option: Option instance to check
            reg_count: Registration count data
            run: Run instance

        Returns:
            tuple: (updated_name, is_valid) with availability information
        """
        found = False
        valid = True
        if chosen:
            for choice in chosen:
                if choice.option_id == option.id:
                    found = True

        if not found:
            key = self.get_option_key_count(option)
            avail = option.max_available
            if key in reg_count:
                avail -= reg_count[key]
            if avail <= 0:
                if option.question_id not in self.unavail:
                    self.unavail[option.question_id] = []
                self.unavail[option.question_id].append(option.id)
            else:
                name += " - (" + _("Available") + f" {avail})"

        return name, valid

    def clean(self):
        """Validate form data and check registration constraints.

        Returns:
            dict: Cleaned form data

        Raises:
            ValidationError: If validation rules are violated
        """
        form_data = super().clean()

        if hasattr(self, "questions"):
            for q in self.questions:
                k = "q" + str(q.id)
                if k not in form_data:
                    continue
                if q.typ == BaseQuestionType.MULTIPLE:
                    for sel in form_data[k]:
                        if not sel:
                            continue
                        if q.id in self.unavail and int(sel) in self.unavail[q.id]:
                            self.add_error(k, _("Option no longer available"))
                elif q.typ == BaseQuestionType.SINGLE:
                    if not form_data[k]:
                        continue
                    if q.id in self.unavail and int(form_data[k]) in self.unavail[q.id]:
                        self.add_error(k, _("Option no longer available"))

        return form_data

    def get_option_key_count(self, option):
        """
        Generate counting key for option availability tracking.

        Args:
            option: Option instance to generate key for

        Returns:
            str: Key string for tracking option usage
        """
        key = f"option_{option.id}"
        return key

    def init_orga_fields(self, reg_section=None):
        """
        Initialize form fields for organizer view with registration questions.

        Args:
            reg_section: Optional registration section name override

        Returns:
            list: List of initialized field keys
        """
        event = self.params["run"].event
        self._init_reg_question(self.instance, event)

        # start loop on questions
        keys = []
        for question in self.questions:
            if question.skip(self.instance, self.params["features"], self.params, True):
                continue

            k = self._init_field(question, reg_counts=None, orga=True)
            if not k:
                continue

            keys.append(k)

            sec_name = reg_section
            if hasattr(question, "section") and question.section:
                sec_name = question.section.name

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

    def init_type(self, key, orga, question, reg_counts, required):
        """Initialize form field based on question type.

        Args:
            key: Field key identifier
            orga: Organization context flag
            question: Question object with type information
            reg_counts: Registration count data
            required: Whether field is required

        Returns:
            Field key identifier
        """
        if question.typ == BaseQuestionType.MULTIPLE:
            self.init_multiple(key, orga, question, reg_counts, required)

        elif question.typ == BaseQuestionType.SINGLE:
            self.init_single(key, orga, question, reg_counts, required)

        elif question.typ == BaseQuestionType.TEXT:
            self.init_text(key, question, required)

        elif question.typ == BaseQuestionType.PARAGRAPH:
            self.init_paragraph(key, question, required)

        elif question.typ == BaseQuestionType.EDITOR:
            self.init_editor(key, question, required)

        else:
            key = self.init_special(question, required)

        if key:
            self.fields[key].key = key

        return key

    def init_special(self, question, required):
        """Initialize special form field configurations.

        Args:
            question: Question object with type and configuration data
            required: Whether the field should be required

        Returns:
            str or None: The field key if successfully initialized, None otherwise
        """
        key = question.typ
        mapping = {
            "faction": "factions_list",
            "additional_tickets": "additionals",
            "pay_what_you_want": "pay_what",
            "reg_quotas": "quotas",
            "reg_surcharges": "surcharge",
        }
        if key in mapping:
            key = mapping[key]
        if key not in self.fields:
            return None

        self.fields[key].label = question.name
        self.fields[key].help_text = question.description
        self.reorder_field(key)
        self.fields[key].required = required
        if key in ["name", "teaser", "text"]:
            self.fields[key].validators = [max_length_validator(question.max_length)] if question.max_length else []

        return key

    def init_editor(self, key, question, required):
        validators = [max_length_validator(question.max_length)] if question.max_length else []
        self.fields[key] = forms.CharField(
            required=required,
            widget=WritingTinyMCE(),
            label=question.name,
            help_text=question.description,
            validators=validators,
        )
        if question.id in self.answers:
            self.initial[key] = self.answers[question.id].text

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

    def init_single(self, key, orga, question, reg_counts, required):
        """Initialize single choice form field.

        Args:
            key: Form field key
            orga: Whether this is an organizational form
            question: Question object with choices configuration
            reg_counts: Registration counts for quota tracking
            required: Whether field is required

        Side effects:
            Creates single choice field and sets initial value if available
        """
        if orga:
            (choices, help_text) = self.get_choice_options(self.choices, question)
            if question.id not in self.singles:
                choices.insert(0, (0, "--- " + _("Not selected")))
        else:
            chosen = []
            if question.id in self.singles:
                chosen.append(self.singles[question.id])
            (choices, help_text) = self.get_choice_options(self.choices, question, chosen, reg_counts)
        self.fields[key] = forms.ChoiceField(
            required=required,
            choices=choices,
            label=question.name,
            help_text=help_text,
        )
        if question.id in self.singles:
            self.initial[key] = self.singles[question.id].option_id

    def init_multiple(self, key, orga, question, reg_counts, required):
        """Set up multiple choice form field handling.

        Args:
            key: Form field key
            orga: Whether this is an organizational form
            question: Question object with choices configuration
            reg_counts: Registration counts for quota tracking
            required: Whether field is required

        Side effects:
            Creates multiple choice field with checkboxes and sets initial values
        """
        if orga:
            (choices, help_text) = self.get_choice_options(self.choices, question)
        else:
            chosen = []
            if question.id in self.multiples:
                chosen = self.multiples[question.id]
            (choices, help_text) = self.get_choice_options(self.choices, question, chosen, reg_counts)
        validators = [max_selections_validator(question.max_length)] if question.max_length else []
        self.fields[key] = forms.MultipleChoiceField(
            required=required,
            choices=choices,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"}),
            label=question.name,
            help_text=help_text,
            validators=validators,
        )
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

    def save_css(self, instance):
        """Save CSS content to file with automatic styling additions.

        Args:
            instance: Model instance to save CSS for
        """
        path = self.get_css_path(instance)
        css = self.cleaned_data[self.get_input_css()]
        css += css_delimeter
        if instance.background:
            css += f"""body {{
                background-image: url('{instance.background_red.url}');
           }}"""
        if instance.font:
            css += f"""@font-face {{
                font-family: '{instance.slug}';
                src: url('{conf_settings.MEDIA_URL}/{instance.font}');
                font-display: swap;
           }}"""
            css += f"""h1, h2 {{
                font-family: {instance.slug};
           }}"""
        if instance.pri_rgb:
            css += f":root {{--pri-rgb: {hex_to_rgb(instance.pri_rgb)}; }}"
        if instance.sec_rgb:
            css += f":root {{--sec-rgb: {hex_to_rgb(instance.sec_rgb)}; }}"
        if instance.ter_rgb:
            css += f":root {{--ter-rgb: {hex_to_rgb(instance.ter_rgb)}; }}"
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
