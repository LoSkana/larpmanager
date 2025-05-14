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
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms

from larpmanager.models.access import EventRole
from larpmanager.models.base import FeatureModule, PaymentMethod
from larpmanager.models.event import (
    Event,
    Run,
)
from larpmanager.models.experience import AbilityPx
from larpmanager.models.form import (
    WritingOption,
)
from larpmanager.models.member import Member, Membership
from larpmanager.models.registration import (
    Registration,
    RegistrationTicket,
)
from larpmanager.models.writing import (
    Character,
    Faction,
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


def prepare_permissions_role(form, typ):
    if form.instance and form.instance.number == 1:
        return
    form.modules = []
    init = []
    if form.instance.pk:
        init = list(form.instance.permissions.values_list("pk", flat=True))
    for module in FeatureModule.objects.order_by("order"):
        ch = []
        for el in typ.objects.filter(feature__module=module).order_by("number"):
            if not el.feature.placeholder and el.feature.slug not in form.params["features"]:
                continue
            ch.append((el.id, _(el.name)))
        if not ch:
            continue
        form.fields[module.name] = forms.MultipleChoiceField(
            required=False,
            choices=ch,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"}),
            label=_(module.name),
        )
        form.modules.append(module.name)
        form.initial[module.name] = init


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


class EventMS2:
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


class EventS2WidgetMulti(s2forms.ModelSelect2MultipleWidget, EventMS2):
    pass


class EventS2Widget(s2forms.ModelSelect2Widget, EventMS2):
    pass


class CampaignMS2:
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


class CampaignS2WidgetMulti(s2forms.ModelSelect2MultipleWidget, CampaignMS2):
    pass


class CampaignS2Widget(s2forms.ModelSelect2Widget, CampaignMS2):
    pass


class TemplateMS2:
    search_fields = [
        "name__icontains",
    ]

    def set_assoc(self, aid):
        self.aid = aid

    def get_queryset(self):
        return Event.objects.filter(assoc_id=self.aid, template=True)


class TemplateS2WidgetMulti(s2forms.ModelSelect2MultipleWidget, TemplateMS2):
    pass


class TemplateS2Widget(s2forms.ModelSelect2Widget, TemplateMS2):
    pass


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


class AssocMemberS2WidgetMulti(s2forms.ModelSelect2MultipleWidget, AssocMS2):
    pass


class AssocMemberS2Widget(s2forms.ModelSelect2Widget, AssocMS2):
    pass


class RegisteredMS2:
    search_fields = [
        "name__icontains",
        "surname__icontains",
        "nickname__icontains",
        "user__email__icontains",
    ]

    def __init__(self):
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

    @staticmethod
    def label_from_instance(obj):
        return f"{obj.display_real()} - {obj.email}"


class RunMemberS2WidgetMulti(s2forms.ModelSelect2MultipleWidget, RegisteredMS2):
    pass


class RunMemberS2Widget(s2forms.ModelSelect2Widget, RegisteredMS2):
    pass


def get_assoc_people(assoc_id):
    ls = []
    que = Membership.objects.select_related("member").filter(assoc_id=assoc_id)
    que = que.exclude(status=Membership.EMPTY).exclude(status=Membership.REWOKED)
    for f in que:
        ls.append((f.member.id, f"{str(f.member)} - {f.member.email}"))
    return ls


def get_run_choices(self, past=False):
    cho = [("", "-----")]
    runs = Run.objects.filter(event__assoc_id=self.params["a_id"]).select_related("event").order_by("-end")
    if past:
        ref = datetime.now() - timedelta(days=30)
        runs = runs.filter(end__gte=ref.date(), development__in=[Run.SHOW, Run.DONE])
    for r in runs:
        cho.append((r.id, str(r)))

    if "run" not in self.fields:
        self.fields["run"] = forms.ChoiceField(label=_("Run"))

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


class EventCharacterS2WidgetMulti(s2forms.ModelSelect2MultipleWidget, EventCharacterS2):
    pass


class EventCharacterS2Widget(s2forms.ModelSelect2Widget, EventCharacterS2):
    pass


class EventWritingOptionS2:
    search_fields = [
        "display__icontains",
        "details__icontains",
    ]

    def set_event(self, event):
        self.event = event

    def get_queryset(self):
        return self.event.get_elements(WritingOption)


class EventWritingOptionS2WidgetMulti(s2forms.ModelSelect2MultipleWidget, EventWritingOptionS2):
    pass


class EventWritingOptionS2Widget(s2forms.ModelSelect2Widget, EventWritingOptionS2):
    pass


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


class PaymentsS2WidgetMulti(s2forms.ModelSelect2MultipleWidget):
    search_fields = [
        "name__icontains",
    ]

    def get_queryset(self):
        return PaymentMethod.objects.all()


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
    allwd = [Membership.ACCEPTED, Membership.SUBMITTED, Membership.JOINED]
    qs = Member.objects.prefetch_related("memberships")
    qs = qs.filter(memberships__assoc_id=aid, memberships__status__in=allwd)
    return qs
