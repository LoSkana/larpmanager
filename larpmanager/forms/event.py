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

from larpmanager.cache.character import get_character_fields
from larpmanager.forms.base import MyCssForm, MyForm
from larpmanager.forms.config import ConfigForm, ConfigType
from larpmanager.forms.feature import FeatureForm
from larpmanager.forms.utils import (
    AssocMemberS2WidgetMulti,
    CampaignS2Widget,
    DatePickerInput,
    DateTimePickerInput,
    EventS2Widget,
    SlugInput,
    TemplateS2Widget,
    prepare_permissions_role,
    remove_choice,
    save_permissions_role,
)
from larpmanager.models.access import EventPermission, EventRole
from larpmanager.models.event import Event, EventButton, EventConfig, EventText, EventTextType, ProgressStep, Run
from larpmanager.models.form import QuestionType, QuestionVisibility
from larpmanager.models.utils import generate_id
from larpmanager.utils.common import copy_class


class EventCharactersPdfForm(ConfigForm):
    class Meta:
        model = Event
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def set_configs(self):
        self.add_configs(
            "page_css", ConfigType.TEXTAREA, "CSS", "CSS", _("Insert the css code to customize the pdf printing")
        )

        self.add_configs(
            "header_content", ConfigType.TEXTAREA, _("Header"), _("Header"), _("Insert the html code for the header")
        )

        self.add_configs(
            "footer_content", ConfigType.TEXTAREA, _("Footer"), _("Footer"), _("Insert the html code for the footer")
        )


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

        widgets = {"slug": SlugInput, "parent": CampaignS2Widget}

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

        self.init_campaign(dl)

        if "waiting" not in self.params["features"]:
            dl.append("max_waiting")

        if "filler" not in self.params["features"]:
            dl.append("max_filler")

        for m in dl:
            self.delete_field(m)

    def init_campaign(self, dl):
        if "campaign" not in self.params["features"]:
            dl.append("parent")
        else:
            self.fields["parent"].widget.set_assoc(self.params["a_id"])
            if self.instance and self.instance.pk:
                self.fields["parent"].widget.set_exclude(self.instance.pk)

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


class OrgaFeatureForm(FeatureForm):
    page_title = _("Event features")

    page_info = _(
        "This page allows you to select the features activated for this event, and all its runs. Click on a feature to show its description."
    )

    load_js = "feature_checkbox"

    class Meta:
        model = Event
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_features(False)
        self.prevent_canc = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._save_features(instance)
        return instance


class OrgaConfigForm(ConfigForm):
    page_title = _("Event Configuration")

    page_info = _("This page allows you to edit the configuration of the activated features.")

    section_replace = True

    load_js = "config-search"

    class Meta:
        model = Event
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def set_configs(self):
        section = _("Email notifications")
        label = _("Disable assignment")
        help_text = _("If checked: Does not send communication to the player when the character is assigned")
        self.add_configs("mail_character", ConfigType.BOOL, section, label, help_text)

        section = _("Visualisation")
        label = _("Limitations")
        help_text = _("If checked: Show summary page with number of tickets/options used")
        self.add_configs("show_limitations", ConfigType.BOOL, section, label, help_text)

        self.set_config_reg_form()

        self.set_config_gallery()

        self.set_config_structure()

        self.set_config_writing()

        self.set_config_character()

        self.set_config_char_form()

        self.set_config_custom()

        self.set_config_accounting()

        self.set_config_casting()

        self.set_config_registration()

    def set_config_gallery(self):
        section = _("Gallery")

        label = _("Request login")
        help_text = _("If checked, the gallery will not be displayed to those not logged in to the system")
        self.add_configs("gallery_hide_login", ConfigType.BOOL, section, label, help_text)

        label = _("Request registration")
        help_text = _(
            "If checked, the subscribers' gallery will not be displayed to those who are not subscribed to the run"
        )
        self.add_configs("gallery_hide_signup", ConfigType.BOOL, section, label, help_text)

        if "character" in self.params["features"]:
            label = _("Hide unassigned characters")
            help_text = _("If checked, does not show characters in the gallery who have not been assigned a player")
            self.add_configs("gallery_hide_uncasted_characters", ConfigType.BOOL, section, label, help_text)

            label = _("Hide players without a character")
            help_text = _("If checked, does not show players in the gallery who have not been assigned a character")
            self.add_configs("gallery_hide_uncasted_players", ConfigType.BOOL, section, label, help_text)

    def set_config_reg_form(self):
        section = _("Registration form")

        label = _("Hide not available")
        help_text = _(
            "If checked, options no longer available in the registration form are hidden, "
            "instead of being displayed disabled"
        )
        self.add_configs("registration_hide_unavailable", ConfigType.BOOL, section, label, help_text)

        label = _("Faction selection")
        help_text = _(
            "If checked, allows a registration form question to be visible only if the player is "
            "assigned to certain factions."
        )
        self.add_configs("registration_reg_que_faction", ConfigType.BOOL, section, label, help_text)

        label = _("Ticket selection")
        help_text = _(
            "If checked, allows a registration form question to be visible based on the selected registration ticket."
        )
        self.add_configs("registration_reg_que_tickets", ConfigType.BOOL, section, label, help_text)

        label = _("Age selection")
        help_text = _("If checked, allows a registration form question to be visible based on the player's age.")
        self.add_configs("registration_reg_que_age", ConfigType.BOOL, section, label, help_text)

    def set_config_char_form(self):
        section = _("Character form")

        label = _("Hide not available")
        help_text = _(
            "If checked, options no longer available in the form are hidden, instead of being displayed disabled"
        )
        self.add_configs("character_form_hide_unavailable", ConfigType.BOOL, section, label, help_text)

        label = _("Maximum available")
        help_text = _("If checked, an option can be chosen a maximum number of times.")
        self.add_configs("character_form_wri_que_max", ConfigType.BOOL, section, label, help_text)

        label = _("Ticket selection")
        help_text = _("If checked, allows a option to be visible only to players with selected ticket.")
        self.add_configs("character_form_wri_que_tickets", ConfigType.BOOL, section, label, help_text)

        label = _("Prerequisites")
        help_text = _("If checked, allows a option to be visible only if other options are selected.")
        self.add_configs("character_form_wri_que_dependents", ConfigType.BOOL, section, label, help_text)

    def set_config_structure(self):
        if "pre_register" in self.params["features"]:
            section = _("Pre-registration")
            label = _("Active")
            help_text = _("If checked, makes pre-registration for this event available")
            self.add_configs("pre_register_active", ConfigType.BOOL, section, label, help_text)

        if "custom_mail" in self.params["features"]:
            section = _("Customised mail server")
            help_text = ""

            label = _("Use TLD")
            self.add_configs("mail_server_use_tls", ConfigType.BOOL, section, label, help_text)

            label = _("Host Address")
            self.add_configs("mail_server_host", ConfigType.CHAR, section, label, help_text)

            label = _("Port")
            self.add_configs("mail_server_port", ConfigType.INT, section, label, help_text)

            label = _("Username of account")
            self.add_configs("mail_server_host_user", ConfigType.CHAR, section, label, help_text)

            label = _("Password of account")
            self.add_configs("mail_server_host_password", ConfigType.CHAR, section, label, help_text)

        if "cover" in self.params["features"]:
            section = _("Character cover")
            label = _("Desalt thumbnail")
            help_text = _("If checked, shows the original image in the cover, not the thumbnail version")
            self.add_configs("cover_orig", ConfigType.BOOL, section, label, help_text)

    def set_config_writing(self):
        if "character" in self.params["features"]:
            section = _("Writing")

            label = _("Title")
            help_text = _("Enables field 'title', a short (2-3 words) text added to the character's name")
            self.add_configs("writing_title", ConfigType.BOOL, section, label, help_text)

            label = _("Cover")
            help_text = _(
                "Enables field 'cover', to shown a specific image in the gallery - until assigned to a player"
            )
            self.add_configs("writing_cover", ConfigType.BOOL, section, label, help_text)

            label = _("Hide")
            help_text = _("Enables field 'hide', to be able to hide writing element from players")
            self.add_configs("writing_hide?", ConfigType.BOOL, section, label, help_text)

            label = _("Assigned")
            help_text = _(
                "Enables field 'assigned', to track which staff member is responsible for each writing element"
            )
            self.add_configs("writing_assigned", ConfigType.BOOL, section, label, help_text)

            label = _("Replacing names")
            help_text = _("If checked, character names will be automatically replaced by a reference")
            self.add_configs("writing_substitute", ConfigType.BOOL, section, label, help_text)

            label = _("Paste as text")
            help_text = _("If checked, automatically removes formatting when pasting text into the WYSIWYG editor")
            self.add_configs("writing_paste_text", ConfigType.BOOL, section, label, help_text)

            label = _("Safe editing")
            help_text = _(
                "If checked, prevents multiple users from editing the same item at the same time to avoid conflicts"
            )
            self.add_configs("writing_working_ticket", ConfigType.BOOL, section, label, help_text)

    def set_config_character(self):
        if "campaign" in self.params["features"]:
            section = _("Campaign")
            label = _("Independent factions")
            help_text = _("If checked, do not use the parent event's factions")
            self.add_configs("campaign_faction_indep", ConfigType.BOOL, section, label, help_text)

        if "px" in self.params["features"]:
            section = _("Experience points")
            label = _("Player selection")
            help_text = _(
                "If checked, players may add abilities themselves, by selecting from those that "
                "are visible, and whose pre-requisites they meet."
            )
            self.add_configs("px_user", ConfigType.BOOL, section, label, help_text)

            label = _("Initial experience points")
            help_text = _("Initial value of experience points for all characters")
            self.add_configs("px_start", ConfigType.INT, section, label, help_text)

        if "user_character" in self.params["features"]:
            section = _("Player editor")

            label = _("Maximum number")
            help_text = _("Maximum number of characters the player can create")
            self.add_configs("user_character_max", ConfigType.INT, section, label, help_text)

            label = _("Approval")
            help_text = _("If checked, activates a staff-managed approval process for characters")
            self.add_configs("user_character_approval", ConfigType.BOOL, section, label, help_text)

            label = _("Relationships")
            help_text = _("If checked, enables players to write their own list of character relationships")
            self.add_configs("user_character_player_relationships", ConfigType.BOOL, section, label, help_text)

    def set_config_custom(self):
        if "custom_character" in self.params["features"]:
            section = _("Character customisation")

            label = _("Name")
            help_text = _("If checked, it allows players to customise the names of their characters")
            self.add_configs("custom_character_name", ConfigType.BOOL, section, label, help_text)

            label = _("Profile")
            help_text = _("If checked, allows players to customise their characters' profile picture")
            self.add_configs("custom_character_profile", ConfigType.BOOL, section, label, help_text)

            label = _("Pronoun")
            help_text = _("If checked, it allows players to customise their characters' pronouns")
            self.add_configs("custom_character_pronoun", ConfigType.BOOL, section, label, help_text)

            label = _("Song")
            help_text = _("If checked, it allows players to indicate the song of their characters")
            self.add_configs("custom_character_song", ConfigType.BOOL, section, label, help_text)

            label = _("Private")
            help_text = _(
                "If checked, it allows players to enter private information on their characters, "
                "visible only to them and the staff."
            )
            self.add_configs("custom_character_private", ConfigType.BOOL, section, label, help_text)

            label = _("Public")
            help_text = _(
                "If checked, it allows players to enter public information on their characters, visible to all"
            )
            self.add_configs("custom_character_public", ConfigType.BOOL, section, label, help_text)

    def set_config_casting(self):
        if "casting" in self.params["features"]:
            section = _("Casting")

            label = _("Assignments")
            help_text = _("Number of characters to be assigned (default 1)")
            self.add_configs("casting_characters", ConfigType.INT, section, label, help_text)

            label = _("Mirror")
            help_text = _("Enables to set a character as a 'mirror' for another, to hide it's true nature")
            self.add_configs("casting_mirror", ConfigType.BOOL, section, label, help_text)

            label = _("Minimum preferences")
            help_text = _("Minimum number of preferences")
            self.add_configs("casting_min", ConfigType.INT, section, label, help_text)

            label = _("Maximum preferences")
            help_text = _("Maximum number of preferences")
            self.add_configs("casting_max", ConfigType.INT, section, label, help_text)

            label = _("Additional Preferences")
            help_text = _("Additional preferences, for random assignment when no solution is found (default 0)")
            self.add_configs("casting_add", ConfigType.INT, section, label, help_text)

            label = _("Field for exclusions")
            help_text = _(
                "If checked, it adds a field in which the player can indicate which elements they "
                "wish to avoid altogether"
            )
            self.add_configs("casting_avoid", ConfigType.BOOL, section, label, help_text)

            label = _("Show statistics")
            help_text = _("If checked, players will be able to view for each character the preference statistics")
            self.add_configs("casting_show_pref", ConfigType.BOOL, section, label, help_text)

            label = _("Show history")
            help_text = _("If checked, shows players the histories of preferences entered")
            self.add_configs("casting_history", ConfigType.BOOL, section, label, help_text)

    def set_config_accounting(self):
        if "payment" in self.params["features"]:
            section = _("Payments")

            label = _("Alert")
            help_text = _(
                "Given a payment deadline, indicates the number of days under which it notifies "
                "the player to proceed with the payment. Default 30."
            )
            self.add_configs("payment_alert", ConfigType.INT, section, label, help_text)

            label = _("Causal")
            help_text = _(
                "If present, it indicates the reason for the payment that the player must put on the payments they make."
            )
            help_text += (
                " "
                + _("You can use the following fields, they will be filled in automatically:")
                + "{player_name}, {question_name}"
            )
            self.add_configs("payment_custom_reason", ConfigType.CHAR, section, label, help_text)

        if "token_credit" in self.params["features"]:
            section = _("Tokens / Credits")
            label = _("Disable Tokens")
            help_text = _("If checked, no tokens will be used in the entries of this event")
            self.add_configs("token_credit_disable_t", ConfigType.BOOL, section, label, help_text)

            label = _("Disable credits")
            help_text = _("If checked, no credits will be used in the entries for this event")
            self.add_configs("token_credit_disable_c", ConfigType.BOOL, section, label, help_text)

        if "bring_friend" in self.params["features"]:
            section = _("Bring a friend")
            label = _("Forward discount")
            help_text = _("Value of the discount for the registered player who gives the code to a friend who signs up")
            self.add_configs("bring_friend_discount_to", ConfigType.INT, section, label, help_text)

            label = _("Discount back")
            help_text = _("Value of the discount for the friend who signs up using the code of a registered player")
            self.add_configs("bring_friend_discount_from", ConfigType.INT, section, label, help_text)

    def set_config_registration(self):
        section = _("Tickets")

        label = "Staff"
        help_text = _("If checked, allow ticket tier: Staff")
        self.add_configs("ticket_staff", ConfigType.BOOL, section, label, help_text)

        label = "NPC"
        help_text = _("If checked, allow ticket tier: NPC")
        self.add_configs("ticket_npc", ConfigType.BOOL, section, label, help_text)

        label = "Collaborator"
        help_text = _("If checked, allow ticket tier: Collaborator")
        self.add_configs("ticket_collaborator", ConfigType.BOOL, section, label, help_text)

        label = "Seller"
        help_text = _("If checked, allow ticket tier: Seller")
        self.add_configs("ticket_seller", ConfigType.BOOL, section, label, help_text)

        if "pay_what_you_want" in self.params["features"]:
            section = "Pay what you want"

            label = _("Name")
            help_text = _("Name of the free donation field")
            self.add_configs("pay_what_you_want_label", ConfigType.CHAR, section, label, help_text)

            label = _("Description")
            help_text = _("Description of free donation")
            self.add_configs("pay_what_you_want_descr", ConfigType.CHAR, section, label, help_text)

        if "reduced" in self.params["features"]:
            section = _("Patron / Reduced")
            label = "Ratio"
            help_text = _(
                "Indicates the ratio between reduced and patron tickets, multiplied by 10. "
                "Example: 10 -> 1 reduced ticket for 1 patron ticket. 20 -> 2 reduced tickets for "
                "1 patron ticket. 5 -> 1 reduced ticket for 2 patron tickets"
            )
            self.add_configs("reduced_ratio", ConfigType.INT, section, label, help_text)

        if "filler" in self.params["features"]:
            section = _("Ticket Filler")
            label = _("Free registration")
            help_text = _(
                "If checked, players may sign up as fillers at any time; otherwise, they may only "
                "do so if the stipulated number of characters has been reached"
            )
            self.add_configs("filler_always", ConfigType.BOOL, section, label, help_text)

        if "lottery" in self.params["features"]:
            section = _("Lottery")
            label = _("Number of extractions")
            help_text = _("Number of tickets to be drawn")
            self.add_configs("lottery_num_draws", ConfigType.INT, section, label, help_text)

            label = _("Conversion ticket")
            help_text = _("Name of the ticket into which to convert")
            self.add_configs("lottery_ticket", ConfigType.CHAR, section, label, help_text)


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
        widget=Textarea(attrs={"rows": 15}),
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
        ch = EventTextType.choices
        delete_choice = []

        if "event_tac" not in self.params["features"]:
            delete_choice.append(EventTextType.TOC)

        if not self.params["event"].get_config("user_character_approval", False):
            delete_choice.extend(
                [EventTextType.CHARACTER_PROPOSED, EventTextType.CHARACTER_APPROVED, EventTextType.CHARACTER_REVIEW]
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


class OrgaRunForm(ConfigForm):
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

        self.show_sections = True

    def set_configs(self):
        ls = []

        if "character" not in self.params["features"]:
            return ls

        shows = [
            (
                "char",
                _("Characters"),
                _("If checked, makes characters visible to all players"),
            )
        ]

        basics = QuestionType.get_basic_types()
        get_character_fields(self.params, False)
        for que_id, question in self.params["questions"].items():
            typ = question["typ"]
            if typ in basics:
                typ = f"{que_id}"
            elif typ not in ["teaser", "text"]:
                continue

            help_text = _("If checked, makes the field content visible to all players")
            if question["visibility"] == QuestionVisibility.PRIVATE:
                help_text = _("If checked, makes the field content visible to the assigned player")

            shows.append((typ, question["display"], help_text))

        addit_show = [
            (
                "faction",
                _("Factions"),
                _("If checked, makes factions visible, as the character assignments to factions"),
            ),
            (
                "speedlarp",
                _("Speedlarp"),
                _("If checked, makes visible the speedlarp"),
            ),
            (
                "prologue",
                _("Prologues"),
                _("If checked, makes prologues visible to the assigned character"),
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

        section = _("Visibility")
        for s in shows:
            self.add_configs(f"show_{s[0]}", ConfigType.BOOL, section, s[1], s[2])

        return ls


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


class ExeTemplateForm(FeatureForm):
    page_title = _("Event Template")

    page_info = _(
        "This page allows you to select the features of a template. Click on a feature to show its description."
    )

    load_js = "feature_checkbox"

    class Meta:
        model = Event
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_features(False)

    def save(self, commit=True):
        instance = super().save(commit=False)

        if not instance.template:
            instance.template = True

        if not instance.assoc_id:
            instance.assoc_id = self.params["a_id"]

        if not instance.pk:
            instance.save()

        self._save_features(instance)

        return instance


class ExeTemplateRolesForm(OrgaEventRoleForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].required = False
