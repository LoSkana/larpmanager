from django import forms
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.base import MyForm
from larpmanager.models.base import FeatureModule


class FeatureCheckboxWidget(forms.CheckboxSelectMultiple):
    def render(self, name, value, attrs=None, renderer=None):
        output = []
        value = value or []

        for i, (option_value, option_label) in enumerate(self.choices):
            checkbox_id = f"{attrs.get('id', name)}_{i}"
            checked = "checked" if str(option_value) in value else ""
            checkbox_html = f'<input type="checkbox" name="{name}" value="{option_value}" id="{checkbox_id}" {checked}>'
            link_html = f'<a href="#" feat="{option_value}">{option_label}</a>'
            output.append(f'<div class="feature_checkbox">{checkbox_html} {link_html}</div>')

        return mark_safe("\n".join(output))


class FeatureForm(MyForm):
    def _init_features(self, overall):
        init_features = None
        if self.instance.pk:
            init_features = [str(v) for v in self.instance.features.values_list("pk", flat=True)]

        for module in FeatureModule.objects.exclude(order=0).order_by("order"):
            choices = [
                (str(feat.id), _(feat.name))
                for feat in module.features.filter(overall=overall, placeholder=False).order_by("order")
            ]
            if not choices:
                continue
            self.fields[f"mod_{module.id}"] = forms.MultipleChoiceField(
                choices=choices,
                widget=FeatureCheckboxWidget(),
                label=_(module.name),
                required=False,
            )
            if init_features:
                self.initial[f"mod_{module.id}"] = init_features

    def _save_features(self, instance):
        instance.features.clear()
        features_id = []
        for module_id in FeatureModule.objects.values_list("pk", flat=True):
            key = f"mod_{module_id}"
            if key not in self.cleaned_data:
                continue
            features_id.extend([int(v) for v in self.cleaned_data[key]])
        instance.features.set(features_id)
        instance.save()
