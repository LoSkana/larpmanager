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

from datetime import datetime, timedelta

from django import forms
from django.forms.widgets import Widget
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms
from tinymce.widgets import TinyMCE

from larpmanager.models.access import EventRole
from larpmanager.models.base import FeatureModule
from larpmanager.models.event import (
    DevelopStatus,
    Event,
    Run,
)
from larpmanager.models.experience import AbilityPx
from larpmanager.models.form import (
    WritingOption,
)
from larpmanager.models.member import Member, Membership, MembershipStatus
from larpmanager.models.registration import (
    Registration,
    RegistrationTicket,
)
from larpmanager.models.writing import (
    Character,
    Faction,
    FactionType,
)

# defer script loaded by form

css_delimeter = "/*@#§*/"


def render_js(cls):
    return [format_html('<script defer src="{}"></script>', cls.absolute_path(path)) for path in cls._js]


forms.widgets.Media.render_js = render_js


# special widget


class ReadOnlyWidget(Widget):
    input_type = None
    template_name = "forms/widgets/read_only.html"


class DatePickerInput(forms.TextInput):
    input_type = "date_p"


class DateTimePickerInput(forms.TextInput):
    input_type = "datetime_p"


class TimePickerInput(forms.TextInput):
    input_type = "time_p"


class SlugInput(forms.TextInput):
    input_type = "slug"
    template_name = "forms/widgets/slug.html"


class RoleCheckboxWidget(forms.CheckboxSelectMultiple):
    def __init__(self, *args, **kwargs):
        self.feature_help = kwargs.pop("help_text", {})
        self.feature_map = kwargs.pop("feature_map", {})
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        output = []
        value = value or []

        know_more = _("click on the icon to open the tutorial")

        for i, (option_value, option_label) in enumerate(self.choices):
            checkbox_id = f"{attrs.get('id', name)}_{i}"
            checked = "checked" if option_value in value else ""
            checkbox_html = f'<input type="checkbox" name="{name}" value="{option_value}" id="{checkbox_id}" {checked}>'
            link_html = f'{option_label}<a href="#" feat="{self.feature_map.get(option_value, "")}"><i class="fas fa-question-circle"></i></a>'
            help_text = self.feature_help.get(option_value, "")
            output.append(f"""
                <div class="feature_checkbox lm_tooltip">
                    <span class="hide lm_tooltiptext">{help_text} ({know_more})</span>
                    {checkbox_html} {link_html}
                </div>
            """)

        return mark_safe("\n".join(output))


def prepare_permissions_role(form, typ):
    if form.instance and form.instance.number == 1:
        form.prevent_canc = True
        return
    form.modules = []
    init = []
    if form.instance.pk:
        init = list(form.instance.permissions.values_list("pk", flat=True))
    for module in FeatureModule.objects.order_by("order"):
        ch = []
        help_text = {}
        feature_map = {}
        for el in typ.objects.filter(feature__module=module).order_by("number"):
            if el.hidden:
                continue
            if not el.feature.placeholder and el.feature.slug not in form.params["features"]:
                continue
            ch.append((el.id, _(el.name)))
            help_text[el.id] = el.descr
            feature_map[el.id] = el.feature_id

        if not ch:
            continue

        label = _(module.name)
        if "interface_old" in form.params and not form.params["interface_old"]:
            if module.icon:
                label = f"<i class='fa-solid fa-{module.icon}'></i> {label}"

        valid_ids = {choice[0] for choice in ch}
        initial_values = [i for i in init if i in valid_ids]

        form.fields[module.name] = forms.MultipleChoiceField(
            required=False,
            choices=ch,
            widget=RoleCheckboxWidget(help_text=help_text, feature_map=feature_map),
            label=label,
            initial=initial_values,
        )
        form.modules.append(module.name)


def save_permissions_role(instance, form):
    instance.save()
    if form.instance and form.instance.number == 1:
        return

    sel = []
    for el in form.modules:
        sel.extend([int(e) for e in form.cleaned_data[el]])

    instance.permissions.clear()
    instance.permissions.add(*sel)

    instance.save()


class EventS2Widget(s2forms.ModelSelect2Widget):
    search_fields = [
        "name__icontains",
    ]

    def set_assoc(self, aid):
        self.aid = aid

    def set_exclude(self, excl):
        self.excl = excl

    def get_queryset(self):
        que = Event.objects.filter(assoc_id=self.aid, template=False)
        if hasattr(self, "excl"):
            que = que.exclude(pk=self.excl)
        return que


class CampaignS2Widget(s2forms.ModelSelect2Widget):
    search_fields = [
        "name__icontains",
    ]

    def label_from_instance(self, obj):
        return str(obj)

    def set_assoc(self, aid):
        self.aid = aid

    def set_exclude(self, excl):
        self.excl = excl

    def get_queryset(self):
        que = Event.objects.filter(parent_id__isnull=True, assoc_id=self.aid, template=False)
        if hasattr(self, "excl"):
            que = que.exclude(pk=self.excl)
        return que


class TemplateS2Widget(s2forms.ModelSelect2Widget):
    search_fields = [
        "name__icontains",
    ]

    def set_assoc(self, aid):
        self.aid = aid

    def get_queryset(self):
        return Event.objects.filter(assoc_id=self.aid, template=True)


class AssocMS2:
    search_fields = [
        "name__icontains",
        "surname__icontains",
        "nickname__icontains",
        "user__email__icontains",
    ]

    def set_assoc(self, aid):
        self.aid = aid

    def get_queryset(self):
        return get_members_queryset(self.aid)

    @staticmethod
    def label_from_instance(obj):
        return f"{obj.display_real()} - {obj.email}"


class AssocMemberS2WidgetMulti(AssocMS2, s2forms.ModelSelect2MultipleWidget):
    pass


class AssocMemberS2Widget(AssocMS2, s2forms.ModelSelect2Widget):
    pass


class RunMemberS2Widget(s2forms.ModelSelect2Widget):
    search_fields = [
        "name__icontains",
        "surname__icontains",
        "nickname__icontains",
        "user__email__icontains",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed = None

    def set_run(self, run):
        que = Registration.objects.filter(run=run, cancellation_date__isnull=True)
        self.allowed = set(que.values_list("member_id", flat=True))
        que = EventRole.objects.filter(event_id=run.event_id).prefetch_related("members")
        self.allowed.update(que.values_list("members__id", flat=True))
        # noinspection PyUnresolvedReferences
        self.attrs["required"] = "required"

    def get_queryset(self):
        return Member.objects.filter(pk__in=self.allowed)

    def label_from_instance(self, obj):
        # noinspection PyUnresolvedReferences
        return f"{obj.display_real()} - {obj.email}"


def get_assoc_people(assoc_id):
    ls = []
    que = Membership.objects.select_related("member").filter(assoc_id=assoc_id)
    que = que.exclude(status=MembershipStatus.EMPTY).exclude(status=MembershipStatus.REWOKED)
    for f in que:
        ls.append((f.member.id, f"{str(f.member)} - {f.member.email}"))
    return ls


def get_run_choices(self, past=False):
    cho = [("", "-----")]
    runs = Run.objects.filter(event__assoc_id=self.params["a_id"]).select_related("event").order_by("-end")
    if past:
        ref = datetime.now() - timedelta(days=30)
        runs = runs.filter(end__gte=ref.date(), development__in=[DevelopStatus.SHOW, DevelopStatus.DONE])
    for r in runs:
        cho.append((r.id, str(r)))

    if "run" not in self.fields:
        self.fields["run"] = forms.ChoiceField(label=_("Session"))

    self.fields["run"].choices = cho
    if "run" in self.params:
        self.initial["run"] = self.params["run"].id


class EventRegS2Widget(s2forms.ModelSelect2Widget):
    search_fields = [
        "search__icontains",
    ]

    def set_event(self, event):
        self.event = event

    def get_queryset(self):
        return Registration.objects.prefetch_related("run", "run__event").filter(run__event=self.event)

    def label_from_instance(self, obj):
        s = str(obj)
        # noinspection PyUnresolvedReferences
        if obj.cancellation_date:
            s += " - CANC"
        return s


class AssocRegS2Widget(s2forms.ModelSelect2Widget):
    search_fields = [
        "search__icontains",
    ]

    def set_assoc(self, assoc_id):
        self.assoc_id = assoc_id

    def get_queryset(self):
        return Registration.objects.prefetch_related("run", "run__event").filter(run__event__assoc_id=self.assoc_id)

    def label_from_instance(self, obj):
        s = str(obj)
        # noinspection PyUnresolvedReferences
        if obj.cancellation_date:
            s += " - CANC"
        return s


class RunS2Widget(s2forms.ModelSelect2Widget):
    search_fields = [
        "search__icontains",
    ]

    def set_assoc(self, aid):
        self.aid = aid

    def get_queryset(self):
        return Run.objects.filter(event__assoc_id=self.aid)


class EventCharacterS2:
    search_fields = [
        "number__icontains",
        "name__icontains",
        "teaser__icontains",
        "title__icontains",
    ]

    def set_event(self, event):
        self.event = event

    def get_queryset(self):
        return self.event.get_elements(Character)


class EventCharacterS2WidgetMulti(EventCharacterS2, s2forms.ModelSelect2MultipleWidget):
    pass


class EventCharacterS2Widget(EventCharacterS2, s2forms.ModelSelect2Widget):
    pass


class EventWritingOptionS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    search_fields = [
        "name__icontains",
        "description__icontains",
    ]

    def set_event(self, event):
        self.event = event

    def get_queryset(self):
        return self.event.get_elements(WritingOption)


class FactionS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    search_fields = [
        "number__icontains",
        "name__icontains",
        "teaser__icontains",
    ]

    def set_event(self, event):
        self.event = event

    def get_queryset(self):
        return self.event.get_elements(Faction)

    def label_from_instance(self, instance):
        code = {FactionType.PRIM: "P", FactionType.TRASV: "T", FactionType.SECRET: "S"}
        return f"{instance.name} ({code[instance.typ]})"


class AbilityS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    search_fields = [
        "name__icontains",
    ]

    def set_event(self, event):
        self.event = event

    def get_queryset(self):
        return self.event.get_elements(AbilityPx)


class TicketS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    search_fields = [
        "name__icontains",
    ]

    def set_event(self, event):
        self.event = event

    def get_queryset(self):
        return self.event.get_elements(RegistrationTicket)


class AllowedS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    search_fields = [
        "name__icontains",
        "surname__icontains",
        "nickname__icontains",
        "user__email__icontains",
    ]

    def set_event(self, event):
        self.event = event
        que = EventRole.objects.filter(event_id=event.id).prefetch_related("members")
        self.allowed = que.values_list("members__id", flat=True)

    def get_queryset(self):
        return Member.objects.filter(pk__in=self.allowed)


class InventoryS2Widget(s2forms.ModelSelect2Widget):
    search_fields = [
        "name__icontains",
    ]


def remove_choice(ch, typ):
    new = []
    for k, v in ch:
        if k == typ:
            continue
        new.append((k, v))
    return new


class RedirectForm(forms.Form):
    def __init__(self, *args, **kwargs):
        slugs = self.params = kwargs.pop("slugs")
        super().__init__(*args, **kwargs)
        cho = []
        counter = 0
        for el in slugs:
            cho.append((counter, el))
            counter += 1
        self.fields["slug"] = forms.ChoiceField(choices=cho, label="Element")


def get_members_queryset(aid):
    allwd = [MembershipStatus.ACCEPTED, MembershipStatus.SUBMITTED, MembershipStatus.JOINED]
    qs = Member.objects.prefetch_related("memberships")
    qs = qs.filter(memberships__assoc_id=aid, memberships__status__in=allwd)
    return qs


class WritingTinyMCE(TinyMCE):
    def __init__(self):
        super().__init__(attrs={"rows": 20, "content_style": ".char-marker { background: yellow !important; }"})
