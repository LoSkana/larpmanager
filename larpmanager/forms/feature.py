from django import forms
from django.db.models import Q
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.config import save_single_config
from larpmanager.forms.base import MyForm
from larpmanager.models.base import Feature, FeatureModule


class FeatureCheckboxWidget(forms.CheckboxSelectMultiple):
    def __init__(self, *args, **kwargs):
        self.feature_help = kwargs.pop("help_text", {})
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        output = []
        value = value or []

        know_more = _("click on the icon to open the tutorial")

        for i, (option_value, option_label) in enumerate(self.choices):
            checkbox_id = f"{attrs.get('id', name)}_{i}"
            checked = "checked" if str(option_value) in value else ""
            checkbox_html = f'<input type="checkbox" name="{name}" value="{option_value}" id="{checkbox_id}" {checked}>'
            link_html = f'{option_label}<a href="#" feat="{option_value}"><i class="fas fa-question-circle"></i></a>'
            help_text = self.feature_help.get(option_value, "")
            output.append(f"""
                <div class="feature_checkbox lm_tooltip">
                    <span class="hide lm_tooltiptext">{help_text} ({know_more})</span>
                    {checkbox_html} {link_html}
                </div>
            """)

        return mark_safe("\n".join(output))


class FeatureForm(MyForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def _init_features(self, overall):
        init_features = None
        if self.instance.pk:
            init_features = [str(v) for v in self.instance.features.values_list("pk", flat=True)]

        modules = FeatureModule.objects.exclude(order=0).order_by("order")
        if overall:
            modules = modules.filter(Q(nationality__isnull=True) | Q(nationality=self.instance.nationality))
        for module in modules:
            features = module.features.filter(overall=overall, placeholder=False, hidden=False).order_by("order")
            choices = [(str(f.id), _(f.name)) for f in features]
            help_text = {str(f.id): _(f.descr) for f in features}
            if not choices:
                continue
            label = _(module.name)
            if "interface_old" in self.params and not self.params["interface_old"]:
                if module.icon:
                    label = f"<i class='fa-solid fa-{module.icon}'></i> {label}"
            self.fields[f"mod_{module.id}"] = forms.MultipleChoiceField(
                choices=choices,
                widget=FeatureCheckboxWidget(help_text=help_text),
                label=label,
                required=False,
            )
            if init_features:
                self.initial[f"mod_{module.id}"] = init_features

    def _save_features(self, instance):
        old_features = set(instance.features.values_list("id", flat=True))
        instance.features.clear()

        features_id = []
        for module_id in FeatureModule.objects.values_list("pk", flat=True):
            key = f"mod_{module_id}"
            if key not in self.cleaned_data:
                continue
            features_id.extend([int(v) for v in self.cleaned_data[key]])

        instance.features.set(features_id)
        instance.save()

        new_features = set(features_id)
        self.added_features = new_features - old_features


class QuickSetupForm(MyForm):
    setup = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def init_fields(self, features):
        # for each value in self.setup, init a field
        for key, element in self.setup.items():
            (is_feature, label, help_text) = element
            self.fields[key] = forms.BooleanField(required=False, label=label, help_text=help_text + "?")
            if is_feature:
                init = key in features
            else:
                init = self.instance.get_config(key, False)
            self.initial[key] = init

    def save(self, commit=True):
        instance = super().save(commit=commit)

        features = {}
        for key, element in self.setup.items():
            (is_feature, _label, _help_text) = element
            checked = self.cleaned_data[key]
            if is_feature:
                features[key] = checked
            else:
                save_single_config(self.instance, key, checked)

        features_ids_map = dict(Feature.objects.filter(slug__in=features.keys()).values_list("slug", "id"))
        for slug, checked in features.items():
            feature_id = features_ids_map[slug]
            if checked:
                self.instance.features.add(feature_id)
            else:
                self.instance.features.remove(feature_id)

        instance.save()

        return instance
