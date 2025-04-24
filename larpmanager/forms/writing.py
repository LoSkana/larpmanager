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

import traceback

from django import forms
from django.db.models import Max
from django.forms import CharField
from django.utils.translation import gettext_lazy as _
from tinymce.widgets import TinyMCE

from larpmanager.forms.base import MyForm
from larpmanager.forms.utils import EventCharacterS2Widget, EventCharacterS2WidgetMulti
from larpmanager.models.access import get_event_staffers
from larpmanager.models.casting import AssignmentTrait, Quest, QuestType, Trait
from larpmanager.models.event import ProgressStep, Run
from larpmanager.models.miscellanea import PlayerRelationship
from larpmanager.models.registration import Registration
from larpmanager.models.writing import (
    Faction,
    Handout,
    HandoutTemplate,
    Plot,
    PlotCharacterRel,
    Prologue,
    PrologueType,
    Relationship,
    SpeedLarp,
)
from larpmanager.utils.common import FileTypeValidator


class WritingForm(MyForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for s in ["props", "cover", "concept"]:
            if s in self.fields and s not in self.params["features"]:
                del self.fields[s]

        if "assigned" in self.params["features"]:
            choices = [(m.id, m.show_nick()) for m in get_event_staffers(self.params["run"].event)]
            self.fields["assigned"].choices = [("", _("--- NOT ASSIGNED ---"))] + choices
        else:
            self.delete_field("assigned")

        if "progress" in self.params["features"]:
            self.fields["progress"].choices = [
                (el.id, str(el)) for el in ProgressStep.objects.filter(event=self.params["run"].event).order_by("order")
            ]
        else:
            self.delete_field("progress")

        # prepare translate text
        if "translate" in self.params["features"]:
            self.translate = {}
            for k in self.fields:
                if not isinstance(self.fields[k], CharField):
                    continue
                if k not in self.initial or not self.initial[k]:
                    continue
                self.translate[f"id_{k}"] = self.initial[k]

        self.show_link = ["id_concept", "id_teaser", "id_text"]

        if "preview" in self.params["features"]:
            self.show_link.append("id_preview")
        elif "preview" in self.fields:
            self.delete_field("preview")


class PlayerRelationshipForm(MyForm):
    page_title = _("Character Relationship")

    class Meta:
        model = PlayerRelationship
        exclude = ["reg"]
        widgets = {
            "target": EventCharacterS2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["target"].widget.set_event(self.params["run"].event)

    def clean(self):
        cleaned_data = super().clean()

        if self.cleaned_data["target"].id == self.params["char"]["id"]:
            self.add_error("target", _("You cannot create a relationship towards yourself!"))

        try:
            rel = PlayerRelationship.objects.get(reg=self.params["run"].reg, target=self.cleaned_data["target"])
            if rel.id != self.instance.id:
                self.add_error("target", _("Already existing relationship!"))
        except Exception:
            pass

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        if not instance.pk:
            instance.reg = self.params["run"].reg

        instance.save()

        return instance


class OrgaRelationshipForm(MyForm):
    page_info = _("This page allows you to add or edit a relationship between characters.")

    page_title = _("Character Relationship")

    class Meta:
        model = Relationship
        fields = "__all__"
        widgets = {"source": EventCharacterS2Widget, "target": EventCharacterS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].widget.set_event(self.params["event"])
        self.fields["target"].widget.set_event(self.params["event"])

    def clean(self):
        cleaned_data = super().clean()

        if self.cleaned_data["source"] == self.cleaned_data["target"]:
            self.add_error("source", _("You cannot add a relationship from character to self!"))

        try:
            rel = Relationship.objects.get(source_id=self.cleaned_data["source"], target_id=self.cleaned_data["target"])
            if rel.id != self.instance.id:
                self.add_error("source", _("Already existing relationship!"))
        except Exception:
            pass

        return cleaned_data


class UploadElementsForm(forms.Form):
    elem = forms.FileField(
        validators=[
            FileTypeValidator(
                allowed_types=[
                    "application/csv",
                    "text/csv",
                    "text/plain",
                    "application/zip",
                    "text/html",
                ]
            )
        ]
    )


class PlotForm(WritingForm):
    load_templates = "plot"
    load_js = "characters-choices"

    page_title = _("Plot")

    class Meta:
        model = Plot

        exclude = ("number", "teaser", "temp", "hide")

        widgets = {
            "characters": EventCharacterS2WidgetMulti,
            "concept": TinyMCE(attrs={"cols": 80, "rows": 10}),
            "text": TinyMCE(attrs={"cols": 80, "rows": 20}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # PLOT CHARACTERS REL
        if self.instance.pk:
            for ch in (
                self.instance.get_plot_characters()
                .order_by("character__number")
                .values_list("character__id", "character__number", "character__name", "text")
            ):
                char = f"#{ch[1]} {ch[2]}"
                field = f"ch_{ch[0]}"
                self.fields[field] = forms.CharField(
                    widget=TinyMCE(attrs={"cols": 80, "rows": 10}),
                    label=char,
                    help_text=_("This text will be added to the sheet of {name}".format(name=char)),
                    required=False,
                )

                self.initial[field] = ch[3]

                self.show_link.append("id_" + field)

        # print(self.show_link)

    def get_init_multi_character(self):
        que = PlotCharacterRel.objects.filter(plot__id=self.instance.pk)
        return que.values_list("character_id", flat=True)

    @staticmethod
    def save_multi_characters(instance, old, new):
        for ch in old - new:
            PlotCharacterRel.objects.filter(character_id=ch, plot_id=instance.pk).delete()
        for ch in new - old:
            PlotCharacterRel.objects.create(character_id=ch, plot_id=instance.pk)

    def save(self, commit=True):
        instance = super().save()

        if instance.pk:
            for pr in self.instance.get_plot_characters():
                field = f"ch_{pr.character_id}"
                if field not in self.cleaned_data:
                    continue
                if self.cleaned_data[field] == pr.text:
                    continue
                pr.text = self.cleaned_data[field]
                pr.save()

        return instance


class FactionForm(WritingForm):
    load_templates = "faction"
    load_js = "characters-choices"

    page_title = _("Faction")

    class Meta:
        model = Faction

        exclude = ("number", "temp", "hide", "order")

        widgets = {
            "characters": EventCharacterS2WidgetMulti,
            "concept": TinyMCE(attrs={"cols": 80, "rows": 10}),
            "teaser": TinyMCE(attrs={"cols": 80, "rows": 1}),
            "text": TinyMCE(attrs={"cols": 80, "rows": 20}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "user_character" not in self.params["features"]:
            self.delete_field("selectable")


class QuestTypeForm(WritingForm):
    page_title = _("Quest type")

    class Meta:
        model = QuestType
        fields = ["progress", "name", "assigned", "concept", "teaser", "preview", "props", "event"]

        widgets = {
            "teaser": TinyMCE(attrs={"cols": 80, "rows": 1}),
            "text": TinyMCE(attrs={"cols": 80, "rows": 20}),
        }


class QuestForm(WritingForm):
    page_title = _("Quest")

    class Meta:
        model = Quest
        fields = [
            "progress",
            "typ",
            "name",
            "assigned",
            "concept",
            "teaser",
            "preview",
            "text",
            "props",
            "hide",
            "open_show",
            "event",
        ]

        widgets = {
            "concept": TinyMCE(attrs={"cols": 80, "rows": 10}),
            "teaser": TinyMCE(attrs={"cols": 80, "rows": 1}),
            "text": TinyMCE(attrs={"cols": 80, "rows": 20}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        que = self.params["run"].event.get_elements(QuestType)
        self.fields["typ"].choices = [(m.id, m.name) for m in que]

        # ~ #if not 'questbuilder_open' in self.params['features']:
        # ~ del self.fields['open_show']

        self.details = {}

        if not self.instance.pk:
            return

        # TRAITS CHARACTERS REL
        if Run.objects.filter(event=self.params["run"].event).aggregate(Max("number"))["number__max"] > 1:
            # do this only if this the only run of this event
            return

            # get traits
        txts = []
        for trait in self.instance.traits.all():
            char_name = "<" + _("NOT ASSIGNED") + ">"
            try:
                at = AssignmentTrait.objects.get(run=self.params["run"], trait=trait)
                reg = Registration.objects.get(run=self.params["run"], member=at.member)
                chars = []
                for rcr in reg.rcrs.all():
                    chars.append(f"#{rcr.character.number}")
                char_name = ", ".join(chars)
            except Exception:
                print(traceback.format_exc())
                pass

            txts.append(f"{trait.name} - {char_name}")
        self.details["id_concept"] = "<h4>" + _("Traits") + "</h4><hr />" + ", ".join(txts)


class TraitForm(WritingForm):
    page_title = _("Trait")

    load_templates = "trait"

    class Meta:
        model = Trait
        fields = [
            "progress",
            "quest",
            "name",
            "assigned",
            "concept",
            "teaser",
            "preview",
            "text",
            "role",
            "props",
            "gender",
            "keywords",
            "safety",
            "hide",
            "event",
        ]

        widgets = {
            "concept": TinyMCE(attrs={"cols": 80, "rows": 10}),
            "teaser": TinyMCE(attrs={"cols": 80, "rows": 1}),
            "text": TinyMCE(attrs={"cols": 80, "rows": 20}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        que = self.params["run"].event.get_elements(Quest)
        self.fields["quest"].choices = [(m.id, m.name) for m in que]


class HandoutForm(WritingForm):
    page_title = _("Handout")

    class Meta:
        model = Handout
        fields = ["progress", "template", "name", "assigned", "concept", "text", "event"]

        widgets = {
            "text": TinyMCE(attrs={"cols": 80, "rows": 20}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        que = self.params["run"].event.get_elements(HandoutTemplate)
        self.fields["template"].choices = [(m.id, m.name) for m in que]


class HandoutTemplateForm(MyForm):
    load_templates = "handout-template"

    class Meta:
        model = HandoutTemplate
        exclude = ("number", "event")

        widgets = {"template": forms.FileInput(attrs={"accept": "application/vnd.oasis.opendocument.text"})}


class PrologueTypeForm(MyForm):
    class Meta:
        model = PrologueType
        fields = ["name"]


class PrologueForm(WritingForm):
    page_title = _("Prologue")

    load_js = "characters-choices"

    class Meta:
        model = Prologue

        exclude = ("teaser", "temp", "hide")

        widgets = {
            "characters": EventCharacterS2WidgetMulti,
            "concept": TinyMCE(attrs={"cols": 80, "rows": 10}),
            "text": TinyMCE(attrs={"cols": 80, "rows": 20}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        que = self.params["run"].event.get_elements(PrologueType)
        self.fields["typ"].choices = [(m.id, m.name) for m in que]


class SpeedLarpForm(WritingForm):
    page_title = _("Speed larp")

    load_js = "characters-choices"

    class Meta:
        model = SpeedLarp
        exclude = ("teaser", "temp", "hide")

        widgets = {
            "characters": EventCharacterS2WidgetMulti,
            "concept": TinyMCE(attrs={"cols": 80, "rows": 10}),
            "text": TinyMCE(attrs={"cols": 80, "rows": 20}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
