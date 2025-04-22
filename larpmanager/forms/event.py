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
from django.conf import settings as conf_settings
from django.core.exceptions import ValidationError
from django.forms import Textarea
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.base import MyForm, MyCssForm
from larpmanager.forms.utils import (
    add_custom_field,
    get_custom_field,
    SlugInput,
    remove_choice,
    AssocMemberS2WidgetMulti,
    prepare_permissions_role,
    save_permissions_role,
    DatePickerInput,
    DateTimePickerInput,
    EventS2Widget,
    TemplateS2Widget,
)
from larpmanager.models.access import EventRole, EventPermission
from larpmanager.models.base import FeatureModule
from larpmanager.models.event import Event, EventText, EventButton, Run, ProgressStep, EventConfig
from larpmanager.models.utils import get_all_element_configs, save_all_element_configs
from larpmanager.utils.common import copy_class
from larpmanager.models.utils import generate_id


class EventCharactersPdfForm(forms.ModelForm):
    istr = [
        (
            "page",
            "css",
            5,
            "CSS",
            "CSS",
            _("Insert the css code to customize the pdf printing"),
        ),
        (
            "header",
            "content",
            5,
            _("Header"),
            _("Header"),
            _("Insert the html code for the header"),
        ),
        (
            "footer",
            "content",
            5,
            _("Footer"),
            _("Footer"),
            _("Insert the html code for the footer"),
        ),
    ]

    class Meta:
        model = Event
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # print(self.instance)

        self.prevent_canc = True

        res = get_all_element_configs(self.instance)
        for el in self.istr:
            add_custom_field(el, res, self)

    def save(self, commit=True):
        instance = super().save(commit=commit)

        # PDF INSTRUCTIONS
        pdf_instructions = {}
        for el in self.istr:
            get_custom_field(el, pdf_instructions, self)
        save_all_element_configs(self.instance, pdf_instructions)

        return instance


class OrgaEventForm(MyForm):
    page_title = _("Event Settings")

    page_info = _("This page allows you to change general event settings.")

    load_templates = "event"

    class Meta:
        model = Event
        fields = (
            "name",
            "lang",
            "slug",
            "tagline",
            "where",
            "authors",
            "description_short",
            "description",
            "genre",
            "visible",
            "max_pg",
            "max_waiting",
            "max_filler",
            "website",
            "register_link",
            "parent",
            "assoc",
        )

        widgets = {"slug": SlugInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "exe" not in self.params:
            self.prevent_canc = True

        if self.instance.pk:
            self.delete_field("slug")
        else:
            self.fields["slug"].required = True

        dl = []

        if "multi_lang" not in self.params["features"]:
            dl.append("lang")
        else:
            self.fields["lang"].required = True
            self.fields["lang"].choices = conf_settings.LANGUAGES
            if not self.instance.lang:
                self.initial["lang"] = translation.get_language()

        for s in ["visible", "website", "tagline", "where", "authors", "description", "genre", "register_link"]:
            if s not in self.params["features"]:
                dl.append(s)

        if "campaign" not in self.params["features"]:
            dl.append("parent")
        else:
            ch = [("", "--- EMPTY ---")]
            query = Event.objects.filter(parent_id__isnull=True, assoc_id=self.params["a_id"], template=False)
            if self.instance and self.instance.pk:
                query = query.exclude(pk=self.instance.pk)
            ch.extend([(e.id, e.name) for e in query])
            self.fields["parent"].choices = ch

        if "waiting" not in self.params["features"]:
            dl.append("max_waiting")

        if "filler" not in self.params["features"]:
            dl.append("max_filler")

        for m in dl:
            self.delete_field(m)

    def clean_slug(self):
        data = self.cleaned_data["slug"]
        # print(data)
        # check if already used
        lst = Event.objects.filter(slug=data)
        if self.instance is not None and self.instance.pk is not None:
            lst.exclude(pk=self.instance.pk)
        if lst.count() > 0:
            raise ValidationError("Slug already used!")

        if data and hasattr(conf_settings, "STATIC_PREFIXES"):
            if data in conf_settings.STATIC_PREFIXES:
                raise ValidationError("Reserved word, please choose another!")

        return data


class OrgaConfigForm(MyForm):
    page_title = _("Event Configuration")

    page_info = _("This page allows you to edit the configuration of the activated features.")

    section_replace = True

    load_js = "config-search"

    class Meta:
        model = Event
        fields = ()

    def get_feature_configurations(self):
        ls = []

        section = _("Email notifications")
        label = _("Disable assignment")
        help = _("If checked: Does not send communication to the player when the character is assigned")
        ls.append(("mail", "character", 2, section, label, help))

        section = _("Visualisation")
        label = _("Limitations")
        help = _("If checked: Show summary page with number of tickets/options used")
        ls.append(("show", "limitations", 2, section, label, help))

        if "characters" in self.params["features"]:
            section = _("Writing")
            label = _("Replacing names")
            help = _("If checked, PG names will be automatically replaced by a reference")
            ls.append(("writing", "substitute", 2, section, label, help))

        section = _("Registration form")
        label = _("Hide not available")
        help = _(
            "If checked, options no longer available in the registration form are hidden, "
            "instead of being displayed disabled"
        )
        ls.append(("registration", "hide_unavailable", 2, section, label, help))

        section = _("Gallery")
        label = _("Request login")
        help = _("If checked, the gallery will not be displayed to those not logged in to the system")
        ls.append(("gallery", "hide_login", 2, section, label, help))
        label = _("Request registration")
        help = _(
            "If checked, the subscribers' gallery will not be displayed to those who are not subscribed to the run"
        )
        ls.append(("gallery", "hide_signup", 2, section, label, help))

        if "characters" in self.params["features"]:
            label = _("Hide unassigned characters")
            help = _("If checked, does not show characters in the gallery who have not been assigned a player")
            ls.append(("gallery", "hide_uncasted_characters", 2, section, label, help))

            label = _("Hide players without a character")
            help = _("If checked, does not show players in the gallery who have not been assigned a character")
            ls.append(("gallery", "hide_uncasted_players", 2, section, label, help))

        if "campaign" in self.params["features"]:
            section = _("Campaign")
            label = _("Independent factions")
            help = _("If checked, do not use the parent event's factions")
            ls.append(("campaign", "faction_indep", 2, section, label, help))

        if "pre_register" in self.params["features"]:
            section = _("Pre-registration")
            label = _("Active")
            help = _("If checked, makes pre-registration for this event available")
            ls.append(("pre_register", "active", 2, section, label, help))

        if "payment" in self.params["features"]:
            section = _("Payments")

            label = _("Alert")
            help = _(
                "Given a payment deadline, indicates the number of days under which it notifies "
                "the player to proceed with the payment. Default 30."
            )
            ls.append(("payment", "alert", 4, section, label, help))

            label = _("Causal")
            help = _(
                "If present, it indicates the reason for the payment that the player must put on the payments he makes."
            )
            help += " " + _("You can use the following fields, they will be filled in automatically:") + "{player_name}"
            ls.append(("payment", "custom_reason", 1, section, label, help))

        if "custom_mail" in self.params["features"]:
            section = _("Customised mail server")
            help = ""

            label = _("Use TLD")
            ls.append(("mail_server", "use_tls", 2, section, label, help))

            label = _("Host Address")
            ls.append(("mail_server", "host", 1, section, label, help))

            label = _("Port")
            ls.append(("mail_server", "port", 4, section, label, help))

            label = _("Username of account")
            ls.append(("mail_server", "host_user", 1, section, label, help))

            label = _("Password of account")
            ls.append(("mail_server", "host_password", 1, section, label, help))

        if "user_character" in self.params["features"]:
            section = _("Player editor")

            label = _("Maximum number")
            help = _("Maximum number of characters the player can create")
            ls.append(("user_character", "max", 4, section, label, help))

            label = _("Approval")
            help = _("If checked, activates a staff-managed approval process for characters")
            ls.append(("user_character", "approval", 2, section, label, help))

        if "custom_character" in self.params["features"]:
            section = _("Character customisation")

            label = _("Name")
            help = _("If checked, it allows players to customise the names of their characters")
            ls.append(("custom_character", "name", 2, section, label, help))

            label = _("Profile Photos")
            help = _("If checked, allows players to customise their characters' profile picture")
            ls.append(("custom_character", "profile", 2, section, label, help))

            label = _("Pronoun")
            help = _("If checked, it allows players to customise their characters' pronouns")
            ls.append(("custom_character", "pronoun", 2, section, label, help))

            label = _("Song")
            help = _("If checked, it allows players to indicate the song of their characters")
            ls.append(("custom_character", "song", 2, section, label, help))

            label = _("Private")
            help = _(
                "If checked, it allows players to enter private information on their characters, "
                "visible only to them and the staff."
            )
            ls.append(("custom_character", "private", 2, section, label, help))

            label = _("Public")
            help = _("If checked, it allows players to enter public information on their characters, visible to all")
            ls.append(("custom_character", "public", 2, section, label, help))

        if "cover" in self.params["features"]:
            section = _("Character cover")
            label = _("Desalt thumbnail")
            help = _("If checked, shows the original image in the cover, not the thumbnail version")
            ls.append(("cover", "orig", 2, section, label, help))

        if "token_credit" in self.params["features"]:
            section = _("Tokens / Credits")
            label = _("Disable Tokens")
            help = _("If checked, no tokens will be used in the entries of this event")
            ls.append(("token_credit", "disable_t", 2, section, label, help))

            label = _("Disable credits")
            help = _("If checked, no credits will be used in the entries for this event")
            ls.append(("token_credit", "disable_c", 2, section, label, help))

        if "bring_friend" in self.params["features"]:
            section = _("Bring a friend")
            label = _("Forward discount")
            help = _("Value of the discount for the registered player who gives the code to a friend who signs up")
            ls.append(("bring_friend", "discount_to", 4, section, label, help))

            label = _("Discount back")
            help = _("Value of the discount for the friend who signs up using the code of a registered player")
            ls.append(("bring_friend", "discount_from", 4, section, label, help))

        if "lottery" in self.params["features"]:
            section = _("Lottery")
            label = _("Number of extractions")
            help = _("Number of tickets to be drawn")
            ls.append(("lottery", "num_draws", 4, section, label, help))

            label = _("Conversion ticket")
            help = _("Name of the ticket into which to convert")
            ls.append(("lottery", "ticket", 1, section, label, help))

        if "casting" in self.params["features"]:
            section = _("Casting")

            label = _("Assignments")
            help = _("Number of characters to be assigned (default 1)")
            ls.append(("casting", "characters", 4, section, label, help))

            label = _("Minimum preferences")
            help = _("Minimum number of preferences")
            ls.append(("casting", "min", 4, section, label, help))

            label = _("Maximum preferences")
            help = _("Maximum number of preferences")
            ls.append(("casting", "max", 4, section, label, help))

            label = _("Additional Preferences")
            help = _("Additional preferences, for random assignment when no solution is found (default 0)")
            ls.append(("casting", "add", 4, section, label, help))

            label = _("Field for exclusions")
            help = _(
                "If checked, it adds a field in which the player can indicate which elements they "
                "wish to avoid altogether"
            )
            ls.append(("casting", "avoid", 2, section, label, help))

            label = _("Show statistics")
            help = _("If checked, players will be able to view for each character the preference statistics")
            ls.append(("casting", "show_pref", 2, section, label, help))

            label = _("Show history")
            help = _("If checked, shows players the histories of preferences entered")
            ls.append(("casting", "history", 2, section, label, help))

        if "pay_what_you_want" in self.params["features"]:
            section = "Pay what you want"

            label = _("Name")
            help = _("Name of the free donation field")
            ls.append(("pay_what_you_want", "label", 1, section, label, help))

            label = _("Description")
            help = _("Description of free donation")
            ls.append(("pay_what_you_want", "descr", 1, section, label, help))

        if "reduced" in self.params["features"]:
            section = _("Patron / Reduced")
            label = "Ratio"
            help = _(
                "Indicates the ratio between reduced and patron tickets, multiplied by 10. "
                "Example: 10 -> 1 reduced ticket for 1 patron ticket. 20 -> 2 reduced tickets for "
                "1 patron ticket. 5 -> 1 reduced ticket for 2 patron tickets"
            )
            ls.append(("reduced", "ratio", 4, section, label, help))

        if "filler" in self.params["features"]:
            section = _("Ticket Filler")
            label = _("Free registration")
            help = _(
                "If checked, players may sign up as fillers at any time; otherwise, they may only "
                "do so if the stipulated number of characters has been reached"
            )
            ls.append(("filler", "always", 2, section, label, help))

        if "px" in self.params["features"]:
            section = _("Experience points")
            label = _("Player selection")
            help = _(
                "If checked, players may add abilities themselves, by selecting from those that "
                "are visible, and whose pre-requisites they meet."
            )
            ls.append(("px", "user", 2, section, label, help))

            label = _("Initial experience points")
            help = _("Initial value of experience points for all characters")
            ls.append(("px", "start", 4, section, label, help))

        return ls

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.prevent_canc = True

        ev = self.instance

        res = get_all_element_configs(ev)

        for el in self.get_feature_configurations():
            add_custom_field(el, res, self)

    def save(self, commit=True):
        instance = super().save(commit=commit)

        ev = self.instance

        feature_conf = {}
        for el in self.get_feature_configurations():
            get_custom_field(el, feature_conf, self)

        save_all_element_configs(ev, feature_conf)

        return instance


class OrgaAppearanceForm(MyCssForm):
    page_title = _("Event Appearance")

    page_info = _("This page allows you to change the appearance and presentation of the event.")

    class Meta:
        model = Event
        fields = (
            "cover",
            "carousel_img",
            "carousel_text",
            "background",
            "font",
            "pri_rgb",
            "sec_rgb",
            "ter_rgb",
        )

    event_css = forms.CharField(
        widget=Textarea(attrs={"cols": 80, "rows": 15}),
        required=False,
        help_text=_("These CSS commands will be carried over to all pages in your Association space."),
    )

    def __init__(self, *args: object, **kwargs: object):
        super().__init__(*args, **kwargs)

        self.prevent_canc = True

        self.show_link = ["id_event_css"]

        dl = []
        if "carousel" not in self.params["features"]:
            dl.append("carousel_text")
            dl.append("carousel_img")
        else:
            self.show_link.append("id_carousel_text")

        for m in dl:
            del self.fields[m]

    def save(self, commit=True):
        self.instance.css_code = generate_id(32)
        instance = super().save()
        self.save_css(instance)
        return instance

    @staticmethod
    def get_input_css():
        return "event_css"

    @staticmethod
    def get_css_path(instance):
        return f"css/{instance.assoc.slug}_{instance.slug}_{instance.css_code}.css"


class OrgaEventTextForm(MyForm):
    page_title = _("Texts")

    page_info = _("This page allows you to edit event-specific texts.")

    class Meta:
        abstract = True
        model = EventText
        exclude = ("number",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ch = EventText.TYPE_CHOICES
        delete_choice = []
        if "event_tac" not in self.params["features"]:
            delete_choice.append(EventText.TOC)
        if not self.params["event"].get_config("user_character_approval", False):
            delete_choice.extend(
                [EventText.CHARACTER_PROPOSED, EventText.CHARACTER_APPROVED, EventText.CHARACTER_REVIEW]
            )

        for tp in delete_choice:
            ch = remove_choice(ch, tp)
        self.fields["typ"].choices = ch

    def clean(self):
        cleaned_data = super().clean()

        default = cleaned_data.get("default")
        typ = cleaned_data.get("typ")
        language = cleaned_data.get("language")

        if default:
            # check if there is already a default with that type
            res = EventText.objects.filter(event_id=self.params["event"].id, default=True, typ=typ)
            if res.count() > 0 and res.first().pk != self.instance.pk:
                self.add_error("default", "There is already a language set as default!")

        # check if there is already a language with that type
        res = EventText.objects.filter(event_id=self.params["event"].id, language=language, typ=typ)
        if res.count() > 0 and res.first().pk != self.instance.pk:
            self.add_error("language", "There is already a language of this type!")

        return cleaned_data


class OrgaEventRoleForm(MyForm):
    page_title = _("Roles")

    page_info = _("This page allows you to change the access roles for the event.")

    class Meta:
        model = EventRole
        fields = ("name", "members", "event")
        widgets = {"members": AssocMemberS2WidgetMulti}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].widget.set_assoc(self.params["a_id"])
        prepare_permissions_role(self, EventPermission)

    def save(self, commit=True):
        instance = super().save()
        save_permissions_role(instance, self)
        return instance


class OrgaEventButtonForm(MyForm):
    page_title = _("Navigation")

    page_info = _("This page allows you to edit the event navigation buttons.")

    class Meta:
        model = EventButton
        exclude = ("number",)


class OrgaRunForm(MyForm):
    page_title = _("Run Settings")

    page_info = _("This page allows you to change the general settings of this run.")

    class Meta:
        model = Run
        exclude = ("balance", "number", "plan", "paid")

        widgets = {
            "start": DatePickerInput,
            "end": DatePickerInput,
            "registration_open": DateTimePickerInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "exe" not in self.params:
            self.prevent_canc = True

        dl = []

        if not self.instance.pk or not self.instance.event:
            self.fields["event"] = forms.ChoiceField(
                required=True,
                choices=[(el.id, el.name) for el in Event.objects.filter(assoc_id=self.params["a_id"], template=False)],
            )
            self.fields["event"].widget = EventS2Widget()
            self.fields["event"].widget.set_assoc(self.params["a_id"])
            self.choose_event = True

        for s in ["registration_open", "registration_secret"]:
            if not self.instance.pk or not self.instance.event or s not in self.params["features"]:
                dl.append(s)

        for s in dl:
            del self.fields[s]

        # add visibility options
        res = get_all_element_configs(self.instance)
        for el in self.get_feature_configurations():
            add_custom_field(el, res, self)

        self.show_sections = True

    def get_feature_configurations(self):
        ls = []

        if "characters" not in self.params["features"]:
            return ls

        shows = [
            (
                "char",
                _("Characters"),
                _(
                    "If checked, makes characters visible with basic information such as name, title, "
                    "motto to all players"
                ),
            ),
            (
                "teaser",
                _("Presentations"),
                _("If checked, make the presentations (public information) visible to all players"),
            ),
            (
                "text",
                _("Texts"),
                _(
                    "If checked, makes texts (private information) visible only to the "
                    "player to whom the item is assigned"
                ),
            ),
        ]

        addit_show = [
            (
                "preview",
                _("Preview"),
                _("If checked, makes visible the preview, reserved only to the player to whom the item is assigned"),
            ),
            (
                "faction",
                _("Factions"),
                _("If checked, makes factions visible, as th character assignments to factions"),
            ),
            (
                "speedlarp",
                _("Speedlarp"),
                _("If checked, makes visible the speedlarp in which the character participates assigned"),
            ),
            (
                "prologue",
                _("Prologues"),
                _("If checked, makes prologues of the assigned character visible"),
            ),
            ("questbuilder", _("Questbuilder"), _("If checked, makes quests and traits visible")),
            (
                "workshop",
                _("Workshop"),
                _("If checked, makes workshops visible for players to fill in"),
            ),
            (
                "print_pdf",
                _("PDF"),
                _("If checked, makes visible the PDF version of the character sheets"),
            ),
            (
                "co_creation",
                _("Co-creation"),
                _("If checked, makes co-creation questions and answers visible"),
            ),
        ]

        for f in addit_show:
            if self.instance.pk and f[0] in self.params["features"]:
                shows.append(f)

        for s in shows:
            ls.append(("show", s[0], 2, _("Visibility"), s[1], s[2]))

        return ls

    def save(self, commit=True):
        instance = super().save(commit=commit)

        feature_conf = {}
        for el in self.get_feature_configurations():
            get_custom_field(el, feature_conf, self)
        # print(feature_conf)
        save_all_element_configs(instance, feature_conf)

        return instance


class OrgaProgressStepForm(MyForm):
    page_title = _("Progression")

    class Meta:
        model = ProgressStep
        exclude = ("number", "order")


class ExeEventForm(OrgaEventForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "template" in self.params["features"] and not self.instance.pk:
            self.fields["template_event"] = forms.ChoiceField(
                required=False,
                choices=[(el.id, el.name) for el in Event.objects.filter(assoc_id=self.params["a_id"], template=True)],
                label=_("Template"),
                help_text=_(
                    "You can indicate a template event from which functionality and configurations will be copied"
                ),
            )
            self.fields["template_event"].widget = TemplateS2Widget()
            self.fields["template_event"].widget.set_assoc(self.params["a_id"])

    def save(self, commit=True):
        instance = super().save(commit=False)

        if "template" in self.params["features"] and not self.instance.pk:
            if "template_event" in self.cleaned_data and self.cleaned_data["template_event"]:
                event_id = self.cleaned_data["template_event"]
                event = Event.objects.get(pk=event_id)
                instance.save()
                instance.features.set(event.features.all())
                copy_class(instance.id, event_id, EventConfig)
                copy_class(instance.id, event_id, EventRole)

        instance.save()

        return instance


class ExeTemplateForm(MyForm):
    page_title = _("Event Template")

    page_info = _("This page allows you to edit an event template.")

    class Meta:
        model = Event
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        init_features = None
        if self.instance.pk:
            init_features = [str(v) for v in self.instance.features.values_list("pk", flat=True)]

        for module in FeatureModule.objects.exclude(order=0).order_by("order"):
            choices = [
                (str(feat.id), _(feat.name))
                for feat in module.features.filter(overall=False, placeholder=False).order_by("order")
            ]
            if not choices:
                continue
            self.fields[f"mod_{module.id}"] = forms.MultipleChoiceField(
                choices=choices,
                widget=forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"}),
                label=_(module.name),
                required=False,
            )
            if init_features:
                self.initial[f"mod_{module.id}"] = init_features

    def save(self, commit=True):
        instance = super().save(commit=False)

        if not instance.template:
            instance.template = True

        if not instance.assoc_id:
            instance.assoc_id = self.params["a_id"]

        if not instance.pk:
            instance.save()

        instance.features.clear()
        features_id = []
        for module_id in FeatureModule.objects.values_list("pk", flat=True):
            key = f"mod_{module_id}"
            if key not in self.cleaned_data:
                continue
            features_id.extend([int(v) for v in self.cleaned_data[key]])
        instance.features.set(features_id)

        instance.save()

        return instance


class ExeTemplateRolesForm(OrgaEventRoleForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].required = False
