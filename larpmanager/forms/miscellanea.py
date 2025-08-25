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
from django.core.exceptions import ValidationError
from django.forms import Textarea
from django.utils.translation import gettext_lazy as _
from tinymce.widgets import TinyMCE

from larpmanager.forms.base import MyForm
from larpmanager.forms.member import MEMBERSHIP_CHOICES
from larpmanager.forms.utils import (
    AssocMemberS2Widget,
    DatePickerInput,
    EventS2Widget,
    InventoryAreaS2Widget,
    InventoryContainerS2Widget,
    InventoryItemS2Widget,
    InventoryItemS2WidgetMulti,
    InventoryTagS2WidgetMulti,
    TimePickerInput,
    get_run_choices,
)
from larpmanager.models.association import Association
from larpmanager.models.event import Event
from larpmanager.models.miscellanea import (
    Album,
    Competence,
    HelpQuestion,
    InventoryArea,
    InventoryAssignment,
    InventoryContainer,
    InventoryItem,
    InventoryMovement,
    InventoryTag,
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
from larpmanager.utils.miscellanea import get_inventory_optionals

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
    reply_to = forms.EmailField(help_text=_("Optional - email reply to"), required=False)
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
    page_info = _("This page allows you to answer a participant's question")

    page_title = _("Participant questions")

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
            (m.id, m.name) for m in WorkshopModule.objects.filter(event=self.params["event"])
        ]


class WorkshopOptionForm(MyForm):
    class Meta:
        model = WorkshopOption
        exclude = ("number",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["question"].choices = [
            (m.id, m.name) for m in WorkshopQuestion.objects.filter(module__event=self.params["event"])
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


def _delete_optionals_inventory(form):
    assoc = Association.objects.get(pk=form.params["a_id"])
    for field in InventoryItem.get_optional_fields():
        if not assoc.get_config(f"inventory_{field}", False):
            form.delete_field(field)


class ExeInventoryItemForm(MyForm):
    page_info = _("This page allows you to add or edit a new item of inventory")

    page_title = _("Inventory items")

    class Meta:
        model = InventoryItem
        exclude = []
        widgets = {
            "description": Textarea(attrs={"rows": 5}),
            "container": InventoryContainerS2Widget,
            "tags": InventoryTagS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["container"].widget.set_assoc(self.params["a_id"])
        self.fields["tags"].widget.set_assoc(self.params["a_id"])

        _delete_optionals_inventory(self)


class ExeInventoryContainerForm(MyForm):
    page_info = _("This page allows you to add or edit a new container of inventory")

    page_title = _("Inventory containers")

    class Meta:
        model = InventoryContainer
        exclude = []
        widgets = {"description": Textarea(attrs={"rows": 5})}


class ExeInventoryTagForm(MyForm):
    page_info = _("This page allows you to add or edit a new tag for inventory items")

    page_title = _("Inventory tags")

    class Meta:
        model = InventoryTag
        exclude = []
        widgets = {
            "description": Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["items"] = forms.ModelMultipleChoiceField(
            queryset=InventoryItem.objects.filter(assoc_id=self.params["a_id"]),
            label=_("Items"),
            widget=InventoryItemS2WidgetMulti,
            required=False,
        )
        if self.instance.pk:
            self.initial["items"] = self.instance.items.values_list("pk", flat=True)
        self.fields["items"].widget.set_assoc(self.params["a_id"])


class ExeInventoryMovementForm(MyForm):
    page_info = _("This page allows you to add or edit a new movement of item inventory, loans or repairs")

    page_title = _("Inventory movements")

    class Meta:
        model = InventoryMovement
        exclude = []
        widgets = {
            "notes": Textarea(attrs={"rows": 5}),
            "item": InventoryItemS2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].widget.set_assoc(self.params["a_id"])

        _delete_optionals_inventory(self)


class OrgaInventoryAreaForm(MyForm):
    page_info = _("This page allows you to add or edit a new event area")

    page_title = _("Event area")

    load_form = ["area-assignments"]

    load_js = ["area-assignments"]

    class Meta:
        model = InventoryArea
        exclude = []
        widgets = {"description": Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item_all = {}
        self.assigned = {}

        self.prepare()

        self.get_all_items()

        self.sort_items()

        self.separate_handling = []
        for item in self.item_all.values():
            self.item_fields(item)

    def item_fields(self, item):
        assigned_data = getattr(item, "assigned", {})

        # selected checkbox
        sel_field = f"sel_{item.id}"
        item.selected = bool(assigned_data)
        self.fields[sel_field] = forms.BooleanField(
            required=False,
            initial=item.selected,
        )
        self.separate_handling.append("id_" + sel_field)

        # quantity
        qty_field = f"qty_{item.id}"
        item.quantity_assigned = assigned_data.get("quantity", 0)
        self.fields[qty_field] = forms.IntegerField(
            required=False,
            initial=item.quantity_assigned,
            min_value=0,
            max_value=item.available,
        )
        self.separate_handling.append("id_" + qty_field)

        # notes
        notes_field = f"notes_{item.id}"
        self.fields[notes_field] = forms.CharField(
            required=False,
            initial=assigned_data.get("notes", ""),
            widget=forms.Textarea(attrs={"rows": 2, "cols": 10}),
        )
        self.separate_handling.append("id_" + notes_field)

    def prepare(self):
        ctx = {"a_id": self.params["request"].assoc["id"]}
        get_inventory_optionals(ctx, [4, 5])
        self.optionals = ctx["optionals"]
        self.no_header_cols = [4, 5]
        if "quantity" in self.optionals:
            self.no_header_cols = [6, 7]

    def get_all_items(self):
        for item in InventoryItem.objects.filter(assoc_id=self.params["a_id"]).prefetch_related("tags"):
            item.available = item.quantity
            self.item_all[item.id] = item

        for el in self.params["event"].get_elements(InventoryAssignment).filter(event=self.params["event"]):
            item = self.item_all[el.item_id]
            if el.area_id == self.instance.pk:
                item.assigned = {"quantity": el.quantity, "notes": el.notes}
            else:
                item.available -= el.quantity

    def sort_items(self):
        def _assigned_updated(it):
            if getattr(it, "assigned", None):
                return it.assigned.get("updated") or getattr(it, "updated", None) or datetime.min
            return datetime.min

        # items with assigned first; among them, most recently updated first; then by name, then id
        ordered_items = sorted(
            self.item_all.values(),
            key=lambda it: (
                bool(getattr(it, "assigned", None)),  # True first via reverse
                _assigned_updated(it),  # recent first via reverse
                getattr(it, "name", ""),  # alphabetical fallback
                it.id,  # stable tiebreaker
            ),
            reverse=True,
        )

        # rebuild dict preserving the sorted order
        self.item_all = {it.id: it for it in ordered_items}

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if not instance.pk:
            instance.save()

        to_del = []
        for item_id, _item in self.item_all.items():
            sel = self.cleaned_data.get(f"sel_{item_id}", False)

            if not sel:
                to_del.append(item_id)
                continue

            assignment, created = InventoryAssignment.objects.get_or_create(
                area=instance, item_id=item_id, event=instance.event
            )
            assignment.quantity = self.cleaned_data.get(f"qty_{item_id}", 0) or 0
            assignment.notes = self.cleaned_data.get(f"notes_{item_id}", "").strip()

            assignment.save()

        InventoryAssignment.objects.filter(area=instance, item_id__in=to_del, event=instance.event).delete()

        return instance


class OrgaInventoryAssignmentForm(MyForm):
    page_info = _("This page allows you to add or edit a new assignment of inventory item to event area")

    page_title = _("Inventory assignments")

    class Meta:
        model = InventoryAssignment
        exclude = []
        widgets = {
            "description": Textarea(attrs={"rows": 5}),
            "area": InventoryAreaS2Widget,
            "item": InventoryItemS2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["area"].widget.set_event(self.params["event"])
        self.fields["item"].widget.set_assoc(self.params["a_id"])

        _delete_optionals_inventory(self)

    def clean(self):
        cleaned = super().clean()
        area = cleaned.get("area")
        item = cleaned.get("item")
        if not area or not item:
            return cleaned

        qs = InventoryAssignment.objects.filter(
            area=area,
            item=item,
        )
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError({"area": _("An assignment for this item and area already exists")})

        return cleaned


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
