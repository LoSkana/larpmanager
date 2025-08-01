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

import re

from django import forms
from django.core.exceptions import ValidationError
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms

from larpmanager.cache.registration import get_reg_counts
from larpmanager.forms.base import MyForm
from larpmanager.forms.utils import (
    AssocMemberS2Widget,
    EventCharacterS2WidgetMulti,
    EventWritingOptionS2WidgetMulti,
    FactionS2WidgetMulti,
    TicketS2WidgetMulti,
    WritingTinyMCE,
)
from larpmanager.forms.writing import BaseWritingForm, WritingForm
from larpmanager.models.experience import AbilityPx, DeliveryPx
from larpmanager.models.form import (
    QuestionApplicable,
    QuestionStatus,
    QuestionType,
    QuestionVisibility,
    WritingOption,
    WritingQuestion,
)
from larpmanager.models.writing import (
    Character,
    CharacterStatus,
    Faction,
    FactionType,
    PlotCharacterRel,
    Relationship,
    TextVersion,
)
from larpmanager.utils.edit import save_version


class CharacterForm(WritingForm, BaseWritingForm):
    orga = False

    page_title = _("Character")

    class Meta:
        model = Character
        fields = [
            "progress",
            "name",
            "assigned",
            "title",
            "teaser",
            "text",
            "mirror",
            "hide",
            "cover",
            "player",
            "event",
            "status",
            "access_token",
        ]

        widgets = {
            "teaser": WritingTinyMCE(),
            "text": WritingTinyMCE(),
            "player": AssocMemberS2Widget,
            "characters": EventCharacterS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.details = {}

        self._init_character()

    def check_editable(self, question):
        if not self.params["event"].get_config("user_character_approval", False):
            return True

        statuses = question.get_editable()

        if not statuses:
            return True

        return self.instance.status in question.get_editable()

    def _init_custom_fields(self):
        event = self.params["event"]
        if event.parent:
            event = event.parent
        fields_default = {"event"}
        fields_custom = set()
        self._init_reg_question(self.instance, event)
        reg_counts = get_reg_counts(self.params["run"])
        for question in self.questions:
            key = self._init_field(question, reg_counts=reg_counts, orga=self.orga)
            if len(question.typ) == 1:
                fields_custom.add(key)
            else:
                fields_default.add(key)

        if self.orga:
            for key in ["player", "status"]:
                fields_default.add(key)
                self.reorder_field(key)
            if event.get_config("writing_external_access", False):
                fields_default.add("access_token")
                self.reorder_field("access_token")

        all_fields = set(self.fields.keys()) - fields_default
        for lbl in all_fields - fields_custom:
            del self.fields[lbl]

        if not self.orga and event.get_config("user_character_approval", False):
            if not self.instance.pk or self.instance.status in [CharacterStatus.CREATION, CharacterStatus.REVIEW]:
                self.fields["propose"] = forms.BooleanField(
                    required=False,
                    label=_("Complete"),
                    help_text=_(
                        "Click here to confirm that you have completed the character and are ready to "
                        "propose it to the staff. Be careful: some fields may no longer be editable. "
                        "Leave the field blank to save your changes and to be able to continue them in "
                        "the future."
                    ),
                    widget=forms.CheckboxInput(attrs={"class": "checkbox_single"}),
                )

    def _init_character(self):
        self._init_factions()

        self._init_custom_fields()

    def _init_factions(self):
        if "faction" not in self.params["features"]:
            return

        queryset = self.params["run"].event.get_elements(Faction).filter(selectable=True)

        self.fields["factions_list"] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
            label=_("Factions"),
        )

        self.show_available_factions = _("Show available factions")

        self.initial["factions_list"] = []
        if not self.instance.pk:
            return

        for fc in self.instance.factions_list.order_by("number").values_list("id", "number", "name", "text"):
            self.initial["factions_list"].append(fc[0])

    def _save_multi(self, s, instance):
        if s != "factions_list":
            return super()._save_multi(s, instance)

        new = set(self.cleaned_data["factions_list"].values_list("pk", flat=True))
        old = set(instance.factions_list.order_by("number").values_list("id", flat=True))

        for ch in old - new:
            instance.factions_list.remove(ch)
        for ch in new - old:
            instance.factions_list.add(ch)

    def clean(self):
        cleaned_data = super().clean()

        if "factions_list" in self.cleaned_data:
            # check only one primary
            prim = 0
            for el in self.cleaned_data["factions_list"]:
                if el.typ == FactionType.PRIM:
                    prim += 1

            if prim > 1:
                raise ValidationError({"factions_list": _("Select only one primary faction")})

        return cleaned_data


class OrgaCharacterForm(CharacterForm):
    page_info = _("This page allows you to add or edit a character")

    page_title = _("Character")

    load_templates = ["char"]

    load_js = ["characters-choices", "characters-relationships", "factions-choices"]

    load_form = ["characters-relationships"]

    orga = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            return

        self._init_px()

        self._init_plots()

    def _init_character(self):
        self._init_factions()

        self._init_custom_fields()

        if "user_character" in self.params["features"]:
            self.fields["player"].widget.set_assoc(aid=self.params["a_id"])
        else:
            self.delete_field("player")

        if not self.params["event"].get_config("user_character_approval", False):
            self.delete_field("status")

        if "mirror" in self.fields:
            que = self.params["run"].event.get_elements(Character).all()
            choices = [(m.id, m.name) for m in que]
            self.fields["mirror"].choices = [("", _("--- NOT ASSIGNED ---"))] + choices

        self._init_special_fields()

    def _init_plots(self):
        if "plot" not in self.params["features"]:
            return

        pcr = {}
        for el in PlotCharacterRel.objects.filter(character=self.instance):
            pcr[el.plot_id] = el.text

        self.add_char_finder = []
        self.field_link = {}
        que = self.instance.plots.order_by("number").values_list("id", "number", "name", "text")
        for pl in que:
            plot = f"#{pl[1]} {pl[2]}"
            field = f"pl_{pl[0]}"
            id_field = f"id_{field}"
            self.fields[field] = forms.CharField(
                widget=WritingTinyMCE(),
                label=plot,
                help_text=_("This text will be added to the sheet, in the plot paragraph %(name)s") % {"name": plot},
                required=False,
            )
            if pl[0] in pcr:
                self.initial[field] = pcr[pl[0]]

            if pl[3]:
                self.details[id_field] = pl[3]
            self.show_link.append(id_field)
            self.add_char_finder.append(id_field)

            reverse_args = [self.params["event"].slug, self.params["run"].number, pl[0]]
            self.field_link[id_field] = reverse("orga_plots_edit", args=reverse_args)

    def _save_plot(self, instance):
        if "plot" not in self.params["features"]:
            return

        for pr in instance.get_plot_characters():
            field = f"pl_{pr.plot_id}"
            if field not in self.cleaned_data:
                continue
            if self.cleaned_data[field] == pr.text:
                continue
            pr.text = self.cleaned_data[field]
            pr.save()

    def _init_px(self):
        if "px" not in self.params["features"]:
            return

        self.fields["px_ability_list"] = forms.ModelMultipleChoiceField(
            label=_("Abilities"),
            queryset=self.params["run"].event.get_elements(AbilityPx),
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
        )

        self.initial["px_ability_list"] = [str(s) for s in self.instance.px_ability_list.values_list("pk", flat=True)]
        self.show_link.append("id_px_ability_list")

        self.fields["px_delivery_list"] = forms.ModelMultipleChoiceField(
            label=_("Delivery"),
            queryset=self.params["run"].event.get_elements(DeliveryPx),
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
        )

        self.initial["px_delivery_list"] = [str(s) for s in self.instance.px_delivery_list.values_list("pk", flat=True)]
        self.show_link.append("id_px_delivery_list")

    def _save_px(self, instance):
        if "px" not in self.params["features"]:
            return

        if "abilities" in self.cleaned_data:
            instance.px_ability_list.set(self.cleaned_data["abilities"])
        if "deliveries" in self.cleaned_data:
            instance.px_delivery_list.set(self.cleaned_data["deliveries"])

    def _init_factions(self):
        if "faction" not in self.params["features"]:
            return

        queryset = self.params["run"].event.get_elements(Faction)

        self.fields["factions_list"] = forms.ModelMultipleChoiceField(
            queryset=queryset, widget=FactionS2WidgetMulti(), required=False, label=_("Factions")
        )
        self.fields["factions_list"].widget.set_event(self.params["event"])

        self.show_available_factions = _("Show available factions")

        if not self.instance.pk:
            return

        # Initial factions values
        self.initial["factions_list"] = []
        for fc in self.instance.factions_list.order_by("number").values_list("id", "number", "name", "text"):
            self.initial["factions_list"].append(fc[0])

    def _save_relationships(self, instance):
        if "relationships" not in self.params["features"]:
            return

        chars_ids = [char["id"] for char in self.params["chars"].values()]

        rel_data = {k: v for k, v in self.data.items() if k.startswith("rel")}
        for key, value in rel_data.items():
            match = re.match(r"rel_(\d+)_(\w+)", key)
            if not match:
                continue
            ch_id = int(match.group(1))
            rel_type = match.group(2)

            # check ch_id is in chars of the event
            if ch_id not in chars_ids:
                raise Http404(f"char {ch_id} not recognized")

            # if value is empty
            if not value:
                # if wasn't present, do nothing
                if ch_id not in self.params["relationships"] or rel_type not in self.params["relationships"][ch_id]:
                    continue
                # else delete
                else:
                    rel = self._get_rel(ch_id, instance, rel_type)
                    save_version(rel, TextVersion.RELATIONSHIP, self.params["member"], True)
                    rel.delete()
                    continue

            # if the value is present, and is the same as before, do nothing
            if ch_id in self.params["relationships"] and rel_type in self.params["relationships"][ch_id]:
                if value == self.params["relationships"][ch_id][rel_type]:
                    continue

            rel = self._get_rel(ch_id, instance, rel_type)
            rel.text = value
            rel.save()

    def _get_rel(self, ch_id, instance, rel_type):
        if rel_type == "direct":
            (rel, cr) = Relationship.objects.get_or_create(source_id=instance.pk, target_id=ch_id)
        else:
            (rel, cr) = Relationship.objects.get_or_create(target_id=instance.pk, source_id=ch_id)
        return rel

    def save(self, commit=True):
        instance = super().save()

        if instance.pk:
            self._save_plot(instance)
            self._save_px(instance)
            self._save_relationships(instance)

        return instance


class OrgaWritingQuestionForm(MyForm):
    page_info = _("This page allows you to add or modify a form question for a writing element")

    page_title = _("Writing Question")

    class Meta:
        model = WritingQuestion
        exclude = ["order"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "cols": 40}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._init_type()

        if (
            "user_character" not in self.params["features"]
            or self.params["writing_typ"] != QuestionApplicable.CHARACTER
        ):
            self.delete_field("status")
        else:
            visible_choices = {v for v, _ in self.fields["status"].choices}

            help_texts = {
                QuestionStatus.OPTIONAL: "The question is shown, and can be filled by the player",
                QuestionStatus.MANDATORY: "The question needs to be filled by the player",
                QuestionStatus.DISABLED: "The question is shown, but cannot be changed by the player",
                QuestionStatus.HIDDEN: "The question is not shown to the player",
            }

            self.fields["status"].help_text = ", ".join(
                f"<b>{choice.label}</b>: {text}"
                for choice, text in help_texts.items()
                if choice.value in visible_choices
            )

        if "print_pdf" not in self.params["features"] or self.params["writing_typ"] == QuestionApplicable.PLOT:
            self.delete_field("printable")

        self._init_editable()

        self._init_applicable()

        # remove visibility from plot
        if self.params["writing_typ"] == QuestionApplicable.PLOT:
            self.delete_field("visibility")
        else:
            # set only private and public visibility if different from character
            if self.params["writing_typ"] != QuestionApplicable.CHARACTER:
                self.fields["visibility"].choices = [
                    (choice.value, choice.label)
                    for choice in QuestionVisibility
                    if choice != QuestionVisibility.SEARCHABLE
                ]

            visible_choices = {v for v, _ in self.fields["visibility"].choices}

            help_texts = {
                QuestionVisibility.SEARCHABLE: "Characters can be filtered according to this question",
                QuestionVisibility.PUBLIC: "The answer to this question is publicly visible",
                QuestionVisibility.PRIVATE: "The answer to this question is only visible to the player",
                QuestionVisibility.HIDDEN: "The answer is hidden to all players",
            }

            self.fields["visibility"].help_text = ", ".join(
                f"<b>{choice.label}</b>: {text}"
                for choice, text in help_texts.items()
                if choice.value in visible_choices
            )

        self.check_applicable = self.params["writing_typ"]

    def _init_type(self):
        # Add type of character question to the available types
        que = self.params["event"].get_elements(WritingQuestion)
        que = que.filter(applicable=self.params["writing_typ"])
        already = list(que.values_list("typ", flat=True).distinct())
        if self.instance.pk and self.instance.typ:
            already.remove(self.instance.typ)

            # basic_type = self.instance.typ in QuestionType.get_basic_types()
            def_type = self.instance.typ in {QuestionType.NAME, QuestionType.TEASER, QuestionType.TEXT}
            # type_feature = self.instance.typ in self.params["features"]
            self.prevent_canc = def_type
        choices = []
        for choice in QuestionType.choices:
            if len(choice[0]) > 1:
                # check it is not already present
                if choice[0] in already:
                    continue
                # check the feature is active
                if choice[0] not in ["name", "teaser", "text"]:
                    if choice[0] not in self.params["features"]:
                        continue
            choices.append(choice)
        self.fields["typ"].choices = choices

    def _init_editable(self):
        if not self.params["event"].get_config("user_character_approval", False):
            self.delete_field("editable")
        else:
            self.fields["editable"] = forms.MultipleChoiceField(
                choices=CharacterStatus.choices,
                widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"}),
                required=False,
            )
            if self.instance and self.instance.pk:
                self.initial["editable"] = self.instance.get_editable()

    def _init_applicable(self):
        if self.instance.pk:
            del self.fields["applicable"]
            return

        self.fields["applicable"].widget = forms.HiddenInput()
        self.initial["applicable"] = self.params["writing_typ"]

    def clean_editable(self):
        return ",".join(self.cleaned_data["editable"])


class OrgaWritingOptionForm(MyForm):
    page_info = _("This page allows you to add or modify an option in a form question for a writing element")

    page_title = _("Writing option")

    class Meta:
        model = WritingOption
        exclude = ["order"]
        widgets = {
            "dependents": EventWritingOptionS2WidgetMulti,
            "question": forms.HiddenInput(),
            "tickets": TicketS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "question_id" in self.params:
            self.initial["question"] = self.params["question_id"]

        if "wri_que_max" not in self.params["features"]:
            self.delete_field("max_available")

        if "wri_que_tickets" not in self.params["features"]:
            self.delete_field("tickets")
        else:
            self.fields["tickets"].widget.set_event(self.params["event"])

        if "wri_que_dependents" not in self.params["features"]:
            self.delete_field("dependents")
        else:
            self.fields["dependents"].widget.set_event(self.params["event"])
