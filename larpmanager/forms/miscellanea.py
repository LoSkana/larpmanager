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
from typing import Any

from django import forms
from django.forms import Textarea
from django.utils.translation import gettext_lazy as _
from tinymce.widgets import TinyMCE

from larpmanager.cache.config import get_association_config
from larpmanager.forms.base import MyForm
from larpmanager.forms.member import MEMBERSHIP_CHOICES
from larpmanager.forms.utils import (
    AssociationMemberS2Widget,
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
    OneTimeAccessToken,
    OneTimeContent,
    Problem,
    ShuttleService,
    UrlShortner,
    Util,
    WarehouseItem,
    WorkshopModule,
    WorkshopOption,
    WorkshopQuestion,
)
from larpmanager.models.registration import RegistrationTicket, TicketTier
from larpmanager.models.utils import generate_id
from larpmanager.models.writing import Faction, FactionType
from larpmanager.utils.validators import FileTypeValidator

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

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize the form with show_link configuration.

        Initializes the parent form class and configures specific fields to be
        displayed as clickable links in the form interface.

        Args:
            *args: Variable length argument list passed to parent class.
            **kwargs: Arbitrary keyword arguments passed to parent class.

        Returns:
            None: This method doesn't return a value.
        """
        # Initialize parent class with all provided arguments
        super().__init__(*args, **kwargs)

        # Configure fields that should display as links in the form
        # These fields will be rendered as clickable links rather than standard form inputs
        self.show_link = ["id_reply_to", "id_raw"]


class UtilForm(MyForm):
    class Meta:
        model = Util
        fields = ("name", "util", "cod", "event")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and set unique code if not provided."""
        super().__init__(*args, **kwargs)
        # Set unique code if not present in initial data
        if "cod" not in self.initial or not self.initial["cod"]:
            self.initial["cod"] = unique_util_cod()


class HelpQuestionForm(MyForm):
    class Meta:
        model = HelpQuestion
        fields = ("text", "attachment", "run")

        widgets = {
            "text": Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with run choices and optional run parameter."""
        super().__init__(*args, **kwargs)
        get_run_choices(self, True)

        # Set initial run value from params if provided
        if "run" in self.params:
            self.initial["run"] = self.params["run"]


class OrgaHelpQuestionForm(MyForm):
    page_info = _("Manage participant questions")

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and populate module choices from event workshops."""
        super().__init__(*args, **kwargs)
        # Filter workshop modules by event and populate dropdown choices
        self.fields["module"].choices = [
            (m.id, m.name) for m in WorkshopModule.objects.filter(event=self.params["event"])
        ]


class WorkshopOptionForm(MyForm):
    class Meta:
        model = WorkshopOption
        exclude = ("number",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and populate question choices from event's workshop questions."""
        super().__init__(*args, **kwargs)
        # Filter workshop questions by event and populate choices
        self.fields["question"].choices = [
            (m.id, m.name) for m in WorkshopQuestion.objects.filter(module__event=self.params["event"])
        ]


class OrgaAlbumForm(MyForm):
    page_info = _("Manage albums")

    page_title = _("Album")

    class Meta:
        model = Album
        fields = "__all__"
        exclude = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with filtered parent album choices for the current run."""
        super().__init__(*args, **kwargs)
        # Build choices: unassigned option + existing albums excluding self
        self.fields["parent"].choices = [("", _("--- NOT ASSIGNED ---"))] + [
            (m.id, m.name) for m in Album.objects.filter(run=self.params["run"]).exclude(pk=self.instance.id)
        ]


class OrgaProblemForm(MyForm):
    page_info = _("Manage reported problems")

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
    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        """Initialize form with dynamic fields for each element in the provided list.

        Args:
            *args: Variable positional arguments passed to parent class.
            **kwargs: Variable keyword arguments. Must contain 'list' key with iterable of objects.
        """
        self.list = kwargs.pop("list")
        super().__init__(*args, **kwargs)

        # Create dynamic fields for each element: one for experience points and one for info
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
    page_info = _("Manage URL shorteners")

    page_title = _("Shorten URL")

    class Meta:
        model = UrlShortner
        exclude = ("number",)


def _delete_optionals_warehouse(warehouse_form):
    """Remove optional warehouse fields not enabled in association configuration.

    Args:
        warehouse_form: Form instance to modify by removing disabled optional fields

    Side effects:
        Deletes form fields for warehouse options not enabled in config
    """
    for optional_field_name in WarehouseItem.get_optional_fields():
        if not get_association_config(
            warehouse_form.params["association_id"], f"warehouse_{optional_field_name}", False
        ):
            warehouse_form.delete_field(optional_field_name)


class ExeCompetenceForm(MyForm):
    page_info = _("Manage competencies")

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize casting form with payment, membership, ticket, and faction options.

        Sets up form fields based on enabled features and initializes choices
        for payments, memberships, tickets, and factions.

        Args:
            *args: Variable length argument list passed to parent form.
            **kwargs: Arbitrary keyword arguments. Expects 'context' with event context.
        """
        # Extract context parameters if provided
        if "context" in kwargs:
            self.params = kwargs.pop("context")
        super().__init__(*args, **kwargs)

        # Set default payment types (ticket, card, paypal)
        self.fields["pays"].initial = ("t", "c", "p")

        # Configure membership field based on feature availability
        if "membership" in self.params["features"]:
            self.fields["memberships"].initial = ("s", "a", "p")
        else:
            del self.fields["memberships"]

        # Fetch available tickets excluding waiting list, staff, and NPC tiers
        ticks = (
            RegistrationTicket.objects.filter(event=self.params["event"])
            .exclude(tier__in=[TicketTier.WAITING, TicketTier.STAFF, TicketTier.NPC])
            .values_list("id", "name")
        )

        # Create ticket selection field with all available tickets
        self.fields["tickets"] = forms.MultipleChoiceField(
            choices=ticks, widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"})
        )
        self.fields["tickets"].initial = [str(el[0]) for el in ticks]

        # Configure faction field if faction feature is enabled
        if "faction" in self.params["features"]:
            factions = (
                self.params["event"]
                .get_elements(Faction)
                .filter(typ=FactionType.PRIM)
                .order_by("number")
                .values_list("id", "name")
            )

            # Create faction selection field with primary factions
            self.fields["factions"] = forms.MultipleChoiceField(
                choices=factions, widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"})
            )
            self.fields["factions"].initial = [str(el[0]) for el in factions]

    def get_data(self) -> dict[str, list]:
        """Get form data, either cleaned or initial values.

        Retrieves form data from cleaned_data if available (after validation),
        otherwise falls back to initial field values converted to lists.

        Returns:
            dict[str, list]: Form data with field names as keys and values as lists.
                Keys are field names, values are lists containing field data.
        """
        # Return cleaned data if form has been validated
        if hasattr(self, "cleaned_data"):
            return self.cleaned_data

        # Build dictionary from initial field values
        field_data = {}
        for field_name in self.fields:
            # Convert initial values to list format for consistency
            field_data[field_name] = list(self.fields[field_name].initial)

        return field_data


class ShuttleServiceForm(MyForm):
    class Meta:
        model = ShuttleService
        exclude = ("member", "working", "notes", "status")

        widgets = {
            "date": DatePickerInput,
            "time": TimePickerInput,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with default time value if not provided."""
        super().__init__(*args, **kwargs)
        # ~ if 'date' not in self.initial or not self.initial['date']:
        # ~ self.initial['date'] = datetime.now().date().isoformat()
        # ~ else:
        # ~ self.initial['date'] = self.instance.date.isoformat()

        # Set default time to current time if not already set
        if "time" not in self.initial or not self.initial["time"]:
            self.initial["time"] = datetime.now().time()


class ShuttleServiceEditForm(ShuttleServiceForm):
    class Meta:
        model = ShuttleService
        fields = "__all__"

        widgets = {
            "date": DatePickerInput,
            "time": TimePickerInput,
            "working": AssociationMemberS2Widget,
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with default working member from request user."""
        super().__init__(*args, **kwargs)

        # Set default working member to current user if not already set
        if "working" not in self.initial or not self.initial["working"]:
            self.initial["working"] = self.params["member"]

        # Configure widget with association context
        self.fields["working"].widget.set_association_id(self.params["association_id"])


class OrgaCopyForm(forms.Form):
    def __init__(self, *args, **kwargs):
        """Initialize organizer copy form with source event choices.

        Args:
            *args: Variable length argument list passed to parent form
            **kwargs: Arbitrary keyword arguments passed to parent form
        """
        self.params = kwargs.pop("context")
        super().__init__(*args, **kwargs)

        self.fields["parent"] = forms.ChoiceField(
            required=True,
            choices=[
                (el.id, el.name)
                for el in Event.objects.filter(association_id=self.params["association_id"], template=False)
            ],
            help_text="The event from which you will copy the elements",
        )
        self.fields["parent"].widget = EventS2Widget()
        self.fields["parent"].widget.set_association_id(self.params["association_id"])
        self.fields["parent"].widget.set_exclude(self.params["event"].id)

        cho = [
            ("event", "Event"),
            ("config", "Configuration"),
            ("appearance", "Appearance"),
            ("text", "Texts"),
            ("navigation", "Navigation"),
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

        self.fields["target"] = forms.MultipleChoiceField(
            required=True,
            choices=cho,
            help_text="The type of elements you want to copy",
            widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"}),
        )


def unique_util_cod() -> str:
    """Generate a unique utility code for new Util instances.

    Attempts to generate a unique 16-character code by checking against existing
    Util objects in the database. Will retry up to 5 times before raising an error.

    Returns:
        str: A unique 16-character alphanumeric code that doesn't exist in the database.

    Raises:
        ValueError: If unable to generate a unique code after 5 attempts.
    """
    # Attempt to generate a unique code up to 5 times
    max_attempts = 5
    for _attempt_number in range(max_attempts):
        # Generate a new 16-character code
        generated_code = generate_id(16)

        # Check if this code already exists in the database
        if not Util.objects.filter(cod=generated_code).exists():
            return generated_code

    # If all attempts failed, raise an error
    raise ValueError("Too many attempts to generate the code")


class OneTimeContentForm(MyForm):
    page_info = _("Manage content that should be accessed only one time with a specific token")

    page_title = _("One-time content")

    class Meta:
        model = OneTimeContent
        fields = ("name", "description", "file", "active", "event")

        widgets = {
            "description": Textarea(attrs={"rows": 3}),
        }


class OneTimeAccessTokenForm(MyForm):
    page_info = _("Manage tokens to access the one-time content")

    page_title = _("One-time token")

    class Meta:
        model = OneTimeAccessToken
        fields = ("note", "content")

        widgets = {
            "note": Textarea(attrs={"rows": 2}),
        }
