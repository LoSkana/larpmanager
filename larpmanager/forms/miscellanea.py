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

from datetime import datetime

from django import forms
from django.forms import Textarea
from django.utils.translation import gettext_lazy as _
from tinymce.widgets import TinyMCE

from larpmanager.forms.base import MyForm
from larpmanager.forms.member import MEMBERSHIP_CHOICES
from larpmanager.forms.utils import (
    AssocMemberS2Widget,
    DatePickerInput,
    EventS2Widget,
    TimePickerInput,
    get_run_choices,
)
from larpmanager.models.event import Event
from larpmanager.models.miscellanea import (
    Album,
    Competence,
    HelpQuestion,
    InventoryBox,
    Problem,
    ShuttleService,
    UrlShortner,
    Util,
    WorkshopModule,
    WorkshopOption,
    WorkshopQuestion,
)
from larpmanager.models.registration import RegistrationTicket, TicketTier
from larpmanager.models.utils import generate_id
from larpmanager.models.writing import Faction, FactionType
from larpmanager.utils.common import FileTypeValidator

PAY_CHOICES = (
    ("t", _("Over")),
    ("c", _("Complete")),
    ("p", _("Partial")),
    ("n", _("Nothing")),
)


class SendMailForm(forms.Form):
    players = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    subject = forms.CharField()
    body = forms.CharField(widget=TinyMCE(attrs={"rows": 30}))
    reply_to = forms.CharField(help_text=_("Optional - email reply to"), required=False)
    raw = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Optional - ram html code (substitute the text before)"),
        required=False,
    )

    def __init__(self, *args: object, **kwargs: object):
        super().__init__(*args, **kwargs)
        self.show_link = ["id_reply_to", "id_raw"]


class UtilForm(MyForm):
    class Meta:
        model = Util
        fields = ("name", "util", "cod", "event")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "cod" not in self.initial or not self.initial["cod"]:
            self.initial["cod"] = unique_util_cod()


class HelpQuestionForm(MyForm):
    class Meta:
        model = HelpQuestion
        fields = ("text", "attachment", "run")

        widgets = {
            "text": Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        get_run_choices(self, True)

        if "run" in self.params:
            self.initial["run"] = self.params["run"]


class OrgaHelpQuestionForm(MyForm):
    page_info = _("This page allows you to answer a player's question")

    page_title = _("Player Questions")

    class Meta:
        model = HelpQuestion
        fields = ("text", "attachment")

        widgets = {
            "text": Textarea(attrs={"rows": 5}),
        }


class WorkshopModuleForm(MyForm):
    class Meta:
        model = WorkshopModule
        exclude = ("members", "number")


class WorkshopQuestionForm(MyForm):
    class Meta:
        model = WorkshopQuestion
        exclude = ("number",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["module"].choices = [
            (m.id, m.display) for m in WorkshopModule.objects.filter(event=self.params["event"])
        ]


class WorkshopOptionForm(MyForm):
    class Meta:
        model = WorkshopOption
        exclude = ("number",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["question"].choices = [
            (m.id, m.display) for m in WorkshopQuestion.objects.filter(module__event=self.params["event"])
        ]


class OrgaAlbumForm(MyForm):
    page_info = _("This page allows you to add or edit an album")

    page_title = _("Album")

    class Meta:
        model = Album
        fields = "__all__"
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].choices = [("", _("--- NOT ASSIGNED ---"))] + [
            (m.id, m.name) for m in Album.objects.filter(run=self.params["run"]).exclude(pk=self.instance.id)
        ]


class OrgaProblemForm(MyForm):
    page_info = _("This page allows you to keep track of reported problems")

    page_title = _("Problems")

    class Meta:
        model = Problem
        exclude = ("number",)

        widgets = {
            "where": Textarea(attrs={"rows": 3}),
            "when": Textarea(attrs={"rows": 3}),
            "what": Textarea(attrs={"rows": 3}),
            "who": Textarea(attrs={"rows": 3}),
            "comments": Textarea(attrs={"rows": 3}),
        }


class UploadAlbumsForm(forms.Form):
    file = forms.FileField(validators=[FileTypeValidator(allowed_types=["application/zip"])])


class CompetencesForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.list = kwargs.pop("list")
        super().__init__(*args, **kwargs)
        for el in self.list:
            self.fields[f"{el.id}_exp"] = forms.IntegerField(required=False)
            self.fields[f"{el.id}_info"] = forms.CharField(required=False)

        # ~ class ContactForm(forms.Form):

    # ~ name = forms.CharField(max_length=100)
    # ~ email = forms.CharField(max_length=100)
    # ~ subject = forms.CharField(max_length=100)
    # ~ body = forms.CharField(widget=TinyMCE(attrs={'cols': 80, 'rows': 10}))
    # ~ captcha = ReCaptchaField()


class ExeUrlShortnerForm(MyForm):
    page_info = _("This page allows you to add or edit a url shortner")

    page_title = _("Shorten URL")

    class Meta:
        model = UrlShortner
        exclude = ("number",)


class ExeInventoryBoxForm(MyForm):
    page_info = _("This page allows you to add or edit a new item of inventory")

    page_title = _("Inventory")

    class Meta:
        model = InventoryBox
        exclude = ()

        widgets = {"description": Textarea(attrs={"rows": 5})}


class ExeCompetenceForm(MyForm):
    page_info = _("This page allows you to add or edit a competency")

    class Meta:
        model = Competence
        exclude = ("number", "members")

        widgets = {
            "descr": Textarea(attrs={"rows": 5}),
        }


class OrganizerCastingOptionsForm(forms.Form):
    pays = forms.MultipleChoiceField(
        choices=PAY_CHOICES, widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"})
    )
    memberships = forms.MultipleChoiceField(
        choices=MEMBERSHIP_CHOICES, widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"})
    )

    def __init__(self, *args, **kwargs):
        if "ctx" in kwargs:
            self.params = kwargs.pop("ctx")
        super().__init__(*args, **kwargs)
        self.fields["pays"].initial = ("t", "c", "p")

        if "membership" in self.params["features"]:
            self.fields["memberships"].initial = ("s", "a", "p")
        else:
            del self.fields["memberships"]

        ticks = (
            RegistrationTicket.objects.filter(event=self.params["event"])
            .exclude(tier__in=[TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC])
            .values_list("id", "name")
        )

        self.fields["tickets"] = forms.MultipleChoiceField(
            choices=ticks, widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"})
        )

        self.fields["tickets"].initial = [str(el[0]) for el in ticks]

        if "faction" in self.params["features"]:
            factions = (
                self.params["event"]
                .get_elements(Faction)
                .filter(typ=FactionType.PRIM)
                .order_by("number")
                .values_list("id", "name")
            )

            self.fields["factions"] = forms.MultipleChoiceField(
                choices=factions, widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"})
            )

            self.fields["factions"].initial = [str(el[0]) for el in factions]

    def get_data(self):
        if hasattr(self, "cleaned_data"):
            return self.cleaned_data
        dic = {}
        for key in self.fields:
            dic[key] = list(self.fields[key].initial)
        return dic


class ShuttleServiceForm(MyForm):
    class Meta:
        model = ShuttleService
        exclude = ("member", "working", "notes", "status")

        widgets = {
            "date": DatePickerInput,
            "time": TimePickerInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ~ if 'date' not in self.initial or not self.initial['date']:
        # ~ self.initial['date'] = datetime.now().date().isoformat()
        # ~ else:
        # ~ self.initial['date'] = self.instance.date.isoformat()

        if "time" not in self.initial or not self.initial["time"]:
            self.initial["time"] = datetime.now().time()


class ShuttleServiceEditForm(ShuttleServiceForm):
    class Meta:
        model = ShuttleService
        fields = "__all__"

        widgets = {
            "date": DatePickerInput,
            "time": TimePickerInput,
            "working": AssocMemberS2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "working" not in self.initial or not self.initial["working"]:
            self.initial["working"] = self.params["request"].user.member

        self.fields["working"].widget.set_assoc(self.params["a_id"])


class OrganizerCopyForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.params = kwargs.pop("ctx")
        super().__init__(*args, **kwargs)

        self.fields["parent"] = forms.ChoiceField(
            required=True,
            choices=[(el.id, el.name) for el in Event.objects.filter(assoc_id=self.params["a_id"], template=False)],
            help_text="The event from which you will copy the elements",
        )
        self.fields["parent"].widget = EventS2Widget()
        self.fields["parent"].widget.set_assoc(self.params["a_id"])
        self.fields["parent"].widget.set_exclude(self.params["event"].id)

        cho = [
            ("all", "All"),
            ("event", "Event"),
            ("config", "Configuration"),
            ("appearance", "Appearance"),
            ("text", "Texts"),
            ("role", "Roles"),
            ("features", "Features"),
            ("ticket", "Registration Tickets"),
            ("question", "Registration Questions and Options"),
            ("discount", "Discount"),
            ("quota", "Registration Quota"),
            ("installment", "Registration Installment"),
            ("surcharge", "Registration Surcharge"),
            ("character", "Characters"),
            ("faction", "Factions"),
            ("quest", "Quests and Traits"),
            ("prologue", "Prologues"),
            ("speedlarp", "SpeedLarps"),
            ("plot", "Plots"),
            ("handout", "Handout and templates"),
            ("workshop", "Workshops"),
        ]

        self.fields["target"] = forms.ChoiceField(
            required=True,
            choices=cho,
            help_text="The type of elements you want to copy",
        )


def unique_util_cod():
    for _idx in range(5):
        cod = generate_id(16)
        if not Util.objects.filter(cod=cod).exists():
            return cod
    raise ValueError("Too many attempts to generate the code")
