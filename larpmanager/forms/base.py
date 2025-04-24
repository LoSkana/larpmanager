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

from django import forms
from django.conf import settings as conf_settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms

from larpmanager.forms.utils import add_custom_field, css_delimeter, get_custom_field
from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.form import (
    QuestionStatus,
    QuestionType,
    RegistrationAnswer,
    RegistrationChoice,
    RegistrationOption,
    RegistrationQuestion,
)
from larpmanager.models.utils import generate_id, get_all_element_configs, get_attr, save_all_element_configs
from larpmanager.templatetags.show_tags import hex_to_rgb


class MyForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__()
        if "ctx" in kwargs:
            self.params = kwargs.pop("ctx")
        else:
            self.params = {}

        for k in ["run", "request"]:
            if k in kwargs:
                self.params[k] = kwargs.pop(k)

        if not hasattr(self, "auto_run"):
            self.auto_run = False

        super(forms.ModelForm, self).__init__(*args, **kwargs)
        # fix_help_text(self)

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

    def get_automatic_field(self):
        s = ["event", "assoc"]
        if self.auto_run:
            s.extend(["run"])
        return s

    def allow_run_choice(self):
        runs = Run.objects.filter(event=self.params["event"])
        runs = runs.select_related("event").order_by("end")
        self.initial["run"] = self.params["run"].id
        if len(runs) <= 1:
            if self.instance.pk:
                self.delete_field("run")
            else:
                self.fields["run"].widget = forms.HiddenInput()
        else:
            self.fields["run"].choices = [(r.id, str(r)) for r in runs]
            self.auto_run = False

    def clean_run(self):
        if self.auto_run:
            return self.params["run"]
        return self.cleaned_data["run"]

    def clean_event(self):
        if hasattr(self, "choose_event"):
            event_id = self.cleaned_data["event"]
            return Event.objects.get(pk=event_id)
        typ = self.params["elementTyp"]
        return self.params["event"].get_class_parent(typ)

    def clean_assoc(self):
        return Association.objects.get(pk=self.params["a_id"])

    def save(self, commit=True):
        instance = super(forms.ModelForm, self).save(commit=commit)

        self.full_clean()

        for s in self.fields:
            if hasattr(self, "custom_field"):
                if s in self.custom_field:
                    continue
            if isinstance(self.fields[s].widget, s2forms.ModelSelect2MultipleWidget):
                self.save_multi(s, instance)

        return instance

    def save_multi(self, s, instance):
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

    def save_configs(self, instance):
        config_values = {}
        for el in self.get_config_fields():
            get_custom_field(el, config_values, self)
        save_all_element_configs(instance, config_values)

    def prepare_configs(self):
        res = get_all_element_configs(self.instance)
        for el in self.get_config_fields():
            add_custom_field(el, res, self)

    def get_config_fields(self):
        return []


class MyFormRun(MyForm):
    def __init__(self, *args, **kwargs):
        self.auto_run = True
        super().__init__(*args, **kwargs)


def max_selections_validator(max_choices):
    def validator(value):
        if len(value) > max_choices:
            raise ValidationError(_("You have exceeded the maximum number of selectable options"))

    return validator


class BaseRegistrationForm(MyFormRun):
    gift = False
    answer_class = RegistrationAnswer
    choice_class = RegistrationChoice
    option_class = RegistrationOption
    question_class = RegistrationQuestion
    instance_key = "reg"

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.choices = {}
        self.max_lengths = {}
        self.unavail = []
        self.multiples = {}
        self.singles = {}
        self.answers = {}
        self.questions = []
        self.has_mandatory = False
        self.sections = {}

    def init_reg_question(self, instance, event):
        if instance and instance.pk:
            for el in self.answer_class.objects.filter(**{self.instance_key: instance}):
                self.answers[el.question_id] = el

            for el in self.choice_class.objects.filter(**{self.instance_key: instance}).select_related("question"):
                if el.question.typ == QuestionType.SINGLE:
                    self.singles[el.question_id] = el
                elif el.question.typ == QuestionType.MULTIPLE:
                    if el.question_id not in self.multiples:
                        self.multiples[el.question_id] = set()
                    self.multiples[el.question_id].add(el)

        for r in self.get_options_query(event):
            if r.question_id not in self.choices:
                self.choices[r.question_id] = []
            self.choices[r.question_id].append(r)

        self.questions = self.question_class.get_instance_questions(event, self.params["features"])

    def get_options_query(self, event):
        return self.option_class.objects.filter(question__event=event).order_by("order")

    def get_choice_options(self, all_options, question, chosen=None, reg_count=None):
        choices = []
        help_text = question.description
        run = self.params["run"]

        if question.id not in all_options:
            return choices, help_text

        options = all_options[question.id]

        for option in options:
            help_text = self.add_choice_option(choices, chosen, help_text, option, reg_count, run)

        return choices, help_text

    def add_choice_option(self, choices, chosen, help_text, option, reg_count, run):
        name = option.get_form_text(run, cs=self.params["currency_symbol"])
        if reg_count and option.max_available > 0:
            found = False
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
                    self.unavail.append(option.id)
                else:
                    name += " - (" + _("Available") + f" {avail})"

            if hasattr(option, "tickets_map"):
                tickets_id = [i for i in option.tickets_map if i is not None]
                if tickets_id and run.reg.ticket_id not in tickets_id:
                    return

        # no problem, go ahead
        choices.append((option.id, name))
        if option.details:
            help_text += f'<p id="hp_{option.id}"><b>{option.display}</b> {option.details}</p>'
        return help_text

    def clean(self):
        form_data = super().clean()

        if hasattr(self, "questions"):
            for q in self.questions:
                k = "q" + str(q.id)
                if k not in form_data:
                    continue
                if q.typ == QuestionType.MULTIPLE:
                    for sel in form_data[k]:
                        if not sel:
                            continue
                        if int(sel) in self.unavail:
                            self.add_error(k, _("Option no longer available"))
                elif q.typ == QuestionType.SINGLE:
                    if not form_data[k]:
                        continue
                    if int(form_data[k]) in self.unavail:
                        self.add_error(k, _("Option no longer available"))

        return form_data

    def get_option_key_count(self, option):
        key = f"option_{option.id}"
        return key

    def init_orga_fields(self, event, reg_section):
        self.init_reg_question(self.instance, event)
        # start loop on questions
        keys = []

        for question in self.questions:
            if question.skip(self.instance, self.params["features"], self.params, True):
                continue

            k = self.init_field(question, reg_counts=None, orga=True)
            keys.append(k)

            sec_name = reg_section
            if question.section:
                sec_name = question.section.name

            self.sections["id_" + k] = sec_name

        return keys

    def check_editable(self, question):
        return True

    def init_field(self, question, reg_counts=None, orga=True):
        key = "q" + str(question.id)

        active = True
        required = False

        if not orga:
            if not self.check_editable(question):
                # skip questions not editable
                return

            if question.status == QuestionStatus.HIDDEN:
                # do not show hidden questions
                return

            if question.status == QuestionStatus.DISABLED:
                # disable question, or if only creation and element is created
                active = False
            else:
                # make question mandatory
                required = question.status == QuestionStatus.MANDATORY

        if question.typ == QuestionType.MULTIPLE:
            self.init_multiple(key, orga, question, reg_counts, required)

        elif question.typ == QuestionType.SINGLE:
            self.init_single(key, orga, question, reg_counts, required)

        elif question.typ == QuestionType.TEXT:
            self.init_text(key, question, required)

        elif question.typ == QuestionType.PARAGRAPH:
            self.init_paragraph(key, question, required)

        else:
            key = self.init_custom(question, required)

        self.init_checks(active, key, orga, question)

        return key

    def init_checks(self, active, key, orga, question):
        if not orga:
            self.fields[key].disabled = not active
            if question.max_length:
                self.max_lengths[f"id_{key}"] = (question.max_length, question.typ)
        if question.status == QuestionStatus.MANDATORY:
            self.fields[key].label += " (*)"
            self.has_mandatory = True
            self.mandatory.append("id_" + key)

    def init_custom(self, question, required):
        key = question.typ
        mapping = {"faction": "factions_list"}
        if key in mapping:
            key = mapping[key]
        self.fields[key].label = question.display
        self.fields[key].help_text = question.description
        self.reorder_field(key)
        self.fields[key].required = required
        return key

    def init_paragraph(self, key, question, required):
        self.fields[key] = forms.CharField(
            required=required,
            max_length=question.max_length if question.max_length else 5000,
            widget=forms.Textarea,
            label=question.display,
            help_text=question.description,
        )
        if question.id in self.answers:
            self.initial[key] = self.answers[question.id].text

    def init_text(self, key, question, required):
        self.fields[key] = forms.CharField(
            required=required,
            max_length=question.max_length if question.max_length else 1000,
            label=question.display,
            help_text=question.description,
        )
        if question.id in self.answers:
            self.initial[key] = self.answers[question.id].text

    def init_single(self, key, orga, question, reg_counts, required):
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
            label=question.display,
            help_text=help_text,
        )
        if question.id in self.singles:
            self.initial[key] = self.singles[question.id].option_id

    def init_multiple(self, key, orga, question, reg_counts, required):
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
            label=question.display,
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
        for q in self.questions:
            if q.skip(instance, self.params["features"], self.params, orga):
                continue

            k = "q" + str(q.id)
            if k not in self.cleaned_data:
                continue
            oid = self.cleaned_data[k]

            if q.typ == QuestionType.MULTIPLE:
                self.save_multiple(instance, oid, q)
            elif q.typ == QuestionType.SINGLE:
                self.save_single(instance, oid, q)
            elif q.typ in [QuestionType.TEXT, QuestionType.PARAGRAPH]:
                self.save_reg_text(instance, oid, q)

    def save_multiple(self, instance, oid, q):
        if not oid:
            return
        oid = set([int(o) for o in oid])
        if q.id in self.multiples:
            old = set([el.option_id for el in self.multiples[q.id]])
            for add in oid - old:
                self.choice_class.objects.create(**{"question": q, self.instance_key: instance, "option_id": add})
            rem = old - oid
            self.choice_class.objects.filter(
                **{"question": q, self.instance_key: instance, "option_id__in": rem}
            ).delete()
        else:
            for pkoid in oid:
                self.choice_class.objects.create(**{"question": q, self.instance_key: instance, "option_id": pkoid})

    def save_single(self, instance, oid, q):
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
            self.choice_class.objects.create(**{"question": q, self.instance_key: instance, "option_id": oid})

    def save_reg_text(self, instance, oid, q):
        if q.id in self.answers:
            if not oid:
                self.answers[q.id].delete()
            elif oid != self.answers[q.id].text:
                self.answers[q.id].text = oid
                self.answers[q.id].save()
        else:
            self.answer_class.objects.create(**{"question": q, self.instance_key: instance, "text": oid})


class MyCssForm(MyForm):
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

    @staticmethod
    def get_css_path(element):
        return ""

    @staticmethod
    def get_input_css():
        return ""

    def save(self, commit=True):
        self.instance.css_code = generate_id(32)
        instance = super(MyForm, self).save()
        self.save_css(instance)
        return instance

    def save_css(self, instance):
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


class BaseAccForm(forms.Form):
    def __init__(self, *args, **kwargs):
        ctx = kwargs.pop("ctx")
        super().__init__(*args, **kwargs)
        self.methods = ctx["methods"]
        cho = []
        for s in self.methods:
            cho.append((s, self.methods[s]["name"]))
        self.fields["method"] = forms.ChoiceField(choices=cho)

        if "association" in ctx:
            self.assoc = ctx["association"]
        else:
            self.assoc = get_object_or_404(Association, pk=ctx["a_id"])
        ctx["user_fees"] = self.assoc.get_config("payment_fees_user", False)
