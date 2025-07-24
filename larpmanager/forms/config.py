from abc import abstractmethod
from enum import IntEnum

from django import forms
from django.forms import Textarea
from django.utils.safestring import mark_safe
from tinymce.widgets import TinyMCE

from larpmanager.cache.config import save_all_element_configs
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
    def render(self, name, value, attrs=None, renderer=None):
        output = []
        value = value or []

        for i, (option_value, option_label) in enumerate(self.choices):
            checkbox_id = f"{attrs.get('id', name)}_{i}"
            checked = "checked" if str(option_value) in value else ""
            checkbox_html = f'<input type="checkbox" name="{name}" value="{option_value}" id="{checkbox_id}" {checked}>'
            link_html = f"{option_label}"
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

    def set_section(self, slug, name):
        self._section = name
        if self.params.get("jump_section", "") == slug:
            self.jump_section = name

    def add_configs(self, key, config_type, label, help_text, extra=None):
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

    def save(self, commit=True):
        instance = super().save(commit=commit)

        config_values = {}
        for el in self.config_fields:
            self._get_custom_field(el, config_values)
        save_all_element_configs(instance, config_values)

        instance.save()

        return instance

    def _get_custom_field(self, el, res):
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
    def _get_form_field(field_type: ConfigType, label, help_text, extra=None):
        field_map = {
            ConfigType.CHAR: lambda: forms.CharField(label=label, help_text=help_text, required=False),
            ConfigType.BOOL: lambda: forms.BooleanField(
                label=label,
                help_text=help_text,
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "checkbox_single"}),
            ),
            ConfigType.HTML: lambda: forms.CharField(
                label=label, widget=TinyMCE(), help_text=help_text, required=False
            ),
            ConfigType.INT: lambda: forms.IntegerField(label=label, help_text=help_text, required=False),
            ConfigType.TEXTAREA: lambda: forms.CharField(
                label=label,
                widget=Textarea(attrs={"rows": 5}),
                help_text=help_text,
                required=False,
            ),
            ConfigType.MEMBERS: lambda: forms.ModelMultipleChoiceField(
                label=label,
                queryset=get_members_queryset(extra),
                widget=AssocMemberS2WidgetMulti,
                required=False,
                help_text=help_text,
            ),
            ConfigType.MULTI_BOOL: lambda: forms.MultipleChoiceField(
                label=label,
                choices=extra,
                widget=MultiCheckboxWidget,
                required=False,
                help_text=help_text,
            ),
        }

        factory = field_map.get(ConfigType(field_type))
        return factory() if factory else None

    def _add_custom_field(self, config, res):
        key = config["key"]
        init = str(res[key]) if key in res else None

        if not hasattr(self, "custom_field"):
            self.custom_field = []
        self.custom_field.append(key)

        field_type = config["type"]

        extra = config["extra"] if field_type in [ConfigType.MEMBERS, ConfigType.MULTI_BOOL] else None
        self.fields[key] = self._get_form_field(field_type, config["label"], config["help_text"], extra)

        if field_type == ConfigType.MEMBERS:
            self.fields[key].widget.set_assoc(config["extra"])
            if init:
                init = [s.strip() for s in init.split(",")]

        if not hasattr(self, "sections"):
            self.sections = {}
        self.sections["id_" + key] = config["section"]

        if init:
            if field_type == ConfigType.BOOL:
                init = init == "True"
            self.initial[key] = init

    def _get_all_element_configs(self):
        res = {}
        if self.instance.pk:
            for config in self.instance.configs.all():
                res[config.name] = config.value
        return res
