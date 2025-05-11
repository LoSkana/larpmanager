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
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Max
from django.utils.translation import gettext_lazy as _
from django_select2 import forms as s2forms
from tinymce.widgets import TinyMCE

from larpmanager.cache.registration import get_reg_counts
from larpmanager.forms.base import BaseRegistrationForm, MyForm
from larpmanager.forms.utils import (
    AssocMemberS2Widget,
    EventCharacterOptionS2WidgetMulti,
    EventCharacterS2WidgetMulti,
    TicketS2WidgetMulti,
)
from larpmanager.forms.writing import WritingForm
from larpmanager.models.casting import AssignmentTrait
from larpmanager.models.event import Run, RunText
from larpmanager.models.experience import AbilityPx, DeliveryPx
from larpmanager.models.form import CharacterAnswer, CharacterChoice, CharacterOption, CharacterQuestion, QuestionType
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character, CharacterStatus, Faction, PlotCharacterRel


class CharacterCocreationForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__()
        text = kwargs.pop("text")
        super().__init__(*args, **kwargs)
        k = "co_creation_answer"
        self.fields[k] = forms.CharField(
            widget=TinyMCE(attrs={"cols": 80, "rows": 10}),
            label="Risposte",
            help_text=_("Freely answer the co-creation questions"),
            required=False,
        )
        self.initial[k] = text


class BaseCharacterForm(BaseRegistrationForm):
    gift = False
    answer_class = CharacterAnswer
    choice_class = CharacterChoice
    option_class = CharacterOption
    question_class = CharacterQuestion
    instance_key = "character"

    def get_options_query(self, event):
        query = super().get_options_query(event)
        return query.annotate(tickets_map=ArrayAgg("tickets"))

    def get_option_key_count(self, option):
        key = f"option_char_{option.id}"
        return key

    class Meta:
        abstract = True


class CharacterForm(WritingForm, BaseCharacterForm):
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
            "preview",
            "text",
            "props",
            "mirror",
            "hide",
            "cover",
            "player",
            "event",
            "status",
        ]

        widgets = {
            "teaser": TinyMCE(attrs={"cols": 80, "rows": 10}),
            "text": TinyMCE(attrs={"cols": 80, "rows": 20}),
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
                )

    def _init_character(self):
        self._init_factions()

        # custom fields
        if "character_form" in self.params["features"]:
            self._init_custom_fields()
            return

        self.delete_field("characters")

        self.fields["teaser"].help_text = _("Presentation text, visible to other players")

        self.fields["text"].help_text = _(
            "Private text, visible only to you and the organizers. You can use it for write background or a journal."
        )

        # STANDARD FIELDS
        st_fields = ["title", "mirror", "hide"]
        for s in st_fields:
            if s in self.fields and s not in self.params["features"]:
                del self.fields[s]

        # ORGA FIELDS
        if not self.orga:
            for s in [
                "progress",
                "assigned",
                "props",
                "mirror",
                "hide",
                "cover",
                "characters",
                "status",
                "player",
            ]:
                if s in self.fields:
                    del self.fields[s]

    def _init_factions(self):
        if "faction" not in self.params["features"]:
            return

        queryset = self.params["run"].event.get_elements(Faction).filter(selectable=True)

        if queryset.count() == 0:
            return

        self.fields["factions_list"] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
        )

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
                if el.typ == Faction.PRIM:
                    prim += 1

            if prim > 1:
                raise ValidationError({"factions_list": _("Select one primary faction")})

        return cleaned_data

    def save(self, commit=True):
        instance = super().save()
        if hasattr(self, "questions"):
            self.save_reg_questions(instance, orga=self.orga)
        return instance


class OrgaCharacterForm(CharacterForm):
    page_info = _("This page allows you to add or edit a character.")

    page_title = _("Character")

    load_templates = "char"

    load_js = "characters-choices"

    orga = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            return

        self._init_cocreation()

        self._init_px()

        self._init_plots()

        self._init_questbuilder()

    def _init_character(self):
        self._init_factions()

        # custom fields
        if "character_form" in self.params["features"]:
            self._init_custom_fields()
        else:
            # STANDARD FIELDS
            st_fields = [
                "title",
                "mirror",
                "hide",
                "progress",
                "assigned",
                "props",
                "cover",
            ]
            for s in st_fields:
                if s in self.fields and s not in self.params["features"]:
                    del self.fields[s]

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

    def _init_questbuilder(self):
        if "questbuilder" not in self.params["features"]:
            return

        tot_runs = Run.objects.filter(event=self.params["run"].event).aggregate(Max("number"))["number__max"]
        if tot_runs != 1:
            return

        # check if in this run it has been assigned
        try:
            rcr = RegistrationCharacterRel.objects.get(reg__run=self.params["run"], character=self.instance.pk)
        except ObjectDoesNotExist:
            return

        reg = rcr.reg

        # get other traits
        que = (
            AssignmentTrait.objects.filter(run=self.params["run"], member=reg.member)
            .select_related("trait")
            .order_by("trait_id")
        )

        for at in que:
            if self.details["id_concept"]:
                self.details["id_concept"] += '</div><div class="plot">'

            self.details["id_concept"] += f"<h4>{at.trait.quest.name} - {at.trait.name}</h4>"
            if at.trait.quest.concept:
                self.details["id_concept"] += "<hr />" + at.trait.quest.concept
            if at.trait.quest.text:
                self.details["id_concept"] += "<hr />" + at.trait.quest.text
            if at.trait.concept:
                self.details["id_concept"] += "<hr />" + at.trait.concept
            if at.trait.text:
                self.details["id_concept"] += "<hr />" + at.trait.text

    def _init_plots(self):
        if "plot" not in self.params["features"]:
            return

        pcr = {}
        for el in PlotCharacterRel.objects.filter(character=self.instance):
            pcr[el.plot_id] = el.text

        que = self.instance.plots.order_by("number").values_list("id", "number", "name", "text")
        for pl in que:
            plot = f"#{pl[1]} {pl[2]}"
            field = f"pl_{pl[0]}"
            self.fields[field] = forms.CharField(
                widget=TinyMCE(attrs={"cols": 80, "rows": 10}),
                label=plot,
                help_text=_("This text will be added to the sheet, in the plot paragraph %(name)s") % {"name": plot},
                required=False,
            )
            if pl[0] in pcr:
                self.initial[field] = pcr[pl[0]]

            self.details[f"id_{field}"] = pl[3]
            self.show_link.append(f"id_{field}")

    def _save_plot(self):
        if "plot" not in self.params["features"]:
            return

        for pr in self.instance.get_plot_characters():
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
            queryset=queryset,
            widget=s2forms.ModelSelect2MultipleWidget(search_fields=["name__icontains"]),
            required=False,
        )

        if not self.instance.pk:
            return

        # FACTIONS SHOW TEXT
        fact_tx = ""
        self.initial["factions_list"] = []
        for fc in self.instance.factions_list.order_by("number").values_list("id", "number", "name", "text"):
            self.initial["factions_list"].append(fc[0])
            if fact_tx:
                fact_tx += '</div><div class="plot">'
            fact_tx += f"<h4>{fc[2]}</h4>"
            if fc[3]:
                fact_tx += "<hr />" + fc[3]
        self.show_link.append("id_factions_list")

    def _init_cocreation(self):
        if "co_creation" not in self.params["features"]:
            return

        (el, creat) = RunText.objects.get_or_create(
            run=self.params["run"], eid=self.instance.number, typ=RunText.COCREATION
        )

        k = "co_creation_question"
        self.fields[k] = forms.CharField(
            widget=TinyMCE(attrs={"cols": 80, "rows": 10}),
            label=_("Co-creation questions"),
            help_text=_("Questions for the co-creation section, editable only by authors"),
            required=False,
        )
        if el.first:
            self.initial[k] = el.first
        self.show_link.append(f"id_{k}")

        k = "co_creation_answer"
        self.fields[k] = forms.CharField(
            widget=TinyMCE(attrs={"cols": 80, "rows": 10}),
            label=_("Co-creation answers"),
            help_text=_("Answers for the co-creation section, editable by both players and authors"),
            required=False,
        )
        if el.second:
            self.initial[k] = el.second
        self.show_link.append(f"id_{k}")

    def _save_cocreation(self):
        if "co_creation" not in self.params["features"]:
            return

        (el, creat) = RunText.objects.get_or_create(
            run=self.params["run"],
            eid=self.instance.number,
            typ=RunText.COCREATION,
        )
        if "co_creation_question" in self.cleaned_data:
            el.first = self.cleaned_data["co_creation_question"]
        if "co_creation_answer" in self.cleaned_data:
            el.second = self.cleaned_data["co_creation_answer"]
        el.save()

    def save(self, commit=True):
        instance = super().save()

        if instance.pk:
            self._save_plot()
            self._save_px(instance)
            self._save_cocreation()

        return instance


class OrgaCharacterQuestionForm(MyForm):
    page_info = _("This page allows you to add or modify a character form question.")

    page_title = _("Character Question")

    class Meta:
        model = CharacterQuestion
        exclude = ["order"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "cols": 40}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add type of character question to the available types
        already = list(
            CharacterQuestion.objects.filter(event=self.params["event"]).values_list("typ", flat=True).distinct()
        )
        if self.instance.pk and self.instance.typ:
            already.remove(self.instance.typ)

            basic_type = self.instance.typ in {
                QuestionType.SINGLE,
                QuestionType.MULTIPLE,
                QuestionType.TEXT,
                QuestionType.PARAGRAPH,
            }
            def_type = self.instance.typ in {QuestionType.NAME}
            type_feature = self.instance.typ in self.params["features"]
            self.prevent_canc = not basic_type and def_type or type_feature

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

        if "user_character" not in self.params["features"]:
            self.delete_field("max_length")
            self.delete_field("status")

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

    def clean_editable(self):
        return ",".join(self.cleaned_data["editable"])


class OrgaCharacterOptionForm(MyForm):
    page_info = _("This page allows you to add or modify an option in a character form question.")

    page_title = _("Character option")

    class Meta:
        model = CharacterOption
        exclude = ["order"]
        widgets = {
            "dependents": EventCharacterOptionS2WidgetMulti,
            "question": forms.HiddenInput(),
            "tickets": TicketS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["tickets"].widget.set_event(self.params["event"])

        if "question_id" in self.params:
            self.initial["question"] = self.params["question_id"]

        for s in ["dependents"]:
            self.fields[s].widget.set_event(self.params["event"])
