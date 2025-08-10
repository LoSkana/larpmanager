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
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.feature import get_event_features, reset_event_features
from larpmanager.cache.role import has_event_permission
from larpmanager.forms.base import MyCssForm, MyForm
from larpmanager.forms.config import ConfigForm, ConfigType
from larpmanager.forms.feature import FeatureForm, QuickSetupForm
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
from larpmanager.models.event import (
    DevelopStatus,
    Event,
    EventButton,
    EventConfig,
    EventText,
    EventTextType,
    ProgressStep,
    Run,
)
from larpmanager.models.form import QuestionType, _get_writing_elements, _get_writing_mapping
from larpmanager.models.member import Member
from larpmanager.models.utils import generate_id
from larpmanager.utils.common import copy_class
from larpmanager.views.orga.registration import _get_registration_fields


class EventCharactersPdfForm(ConfigForm):
    class Meta:
        model = Event
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def set_configs(self):
        self.set_section("pdf", "PDF")
        self.add_configs("page_css", ConfigType.TEXTAREA, "CSS", _("Insert the css code to customize the pdf printing"))
        self.add_configs("header_content", ConfigType.TEXTAREA, _("Header"), _("Insert the html code for the header"))

        self.add_configs("footer_content", ConfigType.TEXTAREA, _("Footer"), _("Insert the html code for the footer"))


class OrgaEventForm(MyForm):
    page_title = _("Event")

    page_info = _("This page allows you to change general event settings")

    load_templates = ["event"]

    class Meta:
        model = Event
        fields = (
            "name",
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
        self.fields["parent"].widget.set_assoc(self.params["a_id"])
        if self.instance and self.instance.pk:
            self.fields["parent"].widget.set_exclude(self.instance.pk)

        if "campaign" not in self.params["features"] or not self.fields["parent"].widget.get_queryset().count():
            dl.append("parent")
            return

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
        "This page allows you to select the features activated for this event, and all its runs (click on a feature to show its description)"
    )

    class Meta:
        model = Event
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_features(False)

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._save_features(instance)
        reset_event_features(instance.id)
        return instance


class OrgaConfigForm(ConfigForm):
    page_title = _("Event Configuration")

    page_info = _("This page allows you to edit the configuration of the activated features")

    section_replace = True

    load_js = ["config-search"]

    class Meta:
        model = Event
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def set_configs(self):
        self.set_section("email", _("Email notifications"))
        label = _("Disable assignment")
        help_text = _("If checked: Does not send communication to the participant when the character is assigned")
        self.add_configs("mail_character", ConfigType.BOOL, label, help_text)

        self.set_section("visualisation", _("Visualisation"))

        label = _("Show shortcuts")
        help_text = _("If checked: when first accessing the manage page, automatically show shortcuts on mobile")
        self.add_configs("show_shortcuts_mobile", ConfigType.BOOL, label, help_text)

        label = _("Export")
        help_text = _("If checked: allow to export characters and registration in a easily readable page")
        self.add_configs("show_export", ConfigType.BOOL, label, help_text)

        label = _("Limitations")
        help_text = _("If checked: Show summary page with number of tickets/options used")
        self.add_configs("show_limitations", ConfigType.BOOL, label, help_text)

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
        self.set_section("gallery", _("Gallery"))

        label = _("Request login")
        help_text = _("If checked, the gallery will not be displayed to those not logged in to the system")
        self.add_configs("gallery_hide_login", ConfigType.BOOL, label, help_text)

        label = _("Request registration")
        help_text = _(
            "If checked, the subscribers' gallery will not be displayed to those who are not registered to the event"
        )
        self.add_configs("gallery_hide_signup", ConfigType.BOOL, label, help_text)

        if "character" in self.params["features"]:
            label = _("Hide unassigned characters")
            help_text = _(
                "If checked, does not show characters in the gallery who have not been assigned a participant"
            )
            self.add_configs("gallery_hide_uncasted_characters", ConfigType.BOOL, label, help_text)

            label = _("Hide participants without a character")
            help_text = _(
                "If checked, does not show participants in the gallery who have not been assigned a character"
            )
            self.add_configs("gallery_hide_uncasted_players", ConfigType.BOOL, label, help_text)

    def set_config_reg_form(self):
        self.set_section("reg_form", _("Registration form"))

        label = _("Unique code")
        help_text = _("If checked, adds to all registrations an unique code to reference them")
        self.add_configs("registration_unique_code", ConfigType.BOOL, label, help_text)

        label = _("Allowed")
        help_text = _(
            "If checked, enables to set for each registration question the list of staff members allowed to see it's answers from the participants"
        )
        self.add_configs("registration_reg_que_allowed", ConfigType.BOOL, label, help_text)

        label = _("Hide not available")
        help_text = _(
            "If checked, options no longer available in the registration form are hidden, "
            "instead of being displayed disabled"
        )
        self.add_configs("registration_hide_unavailable", ConfigType.BOOL, label, help_text)

        label = _("Faction selection")
        help_text = _(
            "If checked, allows a registration form question to be visible only if the participant is "
            "assigned to certain factions."
        )
        self.add_configs("registration_reg_que_faction", ConfigType.BOOL, label, help_text)

        label = _("Ticket selection")
        help_text = _(
            "If checked, allows a registration form question to be visible based on the selected registration ticket."
        )
        self.add_configs("registration_reg_que_tickets", ConfigType.BOOL, label, help_text)

        label = _("Age selection")
        help_text = _("If checked, allows a registration form question to be visible based on the participant's age")
        self.add_configs("registration_reg_que_age", ConfigType.BOOL, label, help_text)

    def set_config_char_form(self):
        if "character" in self.params["features"]:
            self.set_section("char_form", _("Character form"))

            label = _("Hide not available")
            help_text = _(
                "If checked, options no longer available in the form are hidden, instead of being displayed disabled"
            )
            self.add_configs("character_form_hide_unavailable", ConfigType.BOOL, label, help_text)

            label = _("Maximum available")
            help_text = _("If checked, an option can be chosen a maximum number of times")
            self.add_configs("character_form_wri_que_max", ConfigType.BOOL, label, help_text)

            label = _("Ticket selection")
            help_text = _("If checked, allows a option to be visible only to participants with selected ticket")
            self.add_configs("character_form_wri_que_tickets", ConfigType.BOOL, label, help_text)

            label = _("Prerequisites")
            help_text = _("If checked, allows a option to be visible only if other options are selected")
            self.add_configs("character_form_wri_que_dependents", ConfigType.BOOL, label, help_text)

    def set_config_structure(self):
        if "pre_register" in self.params["features"]:
            self.set_section("pre_reg", _("Pre-registration"))
            label = _("Active")
            help_text = _("If checked, makes pre-registration for this event available")
            self.add_configs("pre_register_active", ConfigType.BOOL, label, help_text)

        if "custom_mail" in self.params["features"]:
            self.set_section("custom_mail_server", _("Customised mail server"))
            help_text = ""

            label = _("Use TLD")
            self.add_configs("mail_server_use_tls", ConfigType.BOOL, label, help_text)

            label = _("Host Address")
            self.add_configs("mail_server_host", ConfigType.CHAR, label, help_text)

            label = _("Port")
            self.add_configs("mail_server_port", ConfigType.INT, label, help_text)

            label = _("Username of account")
            self.add_configs("mail_server_host_user", ConfigType.CHAR, label, help_text)

            label = _("Password of account")
            self.add_configs("mail_server_host_password", ConfigType.CHAR, label, help_text)

        if "cover" in self.params["features"]:
            self.set_section("cover", _("Character cover"))
            label = _("Desalt thumbnail")
            help_text = _("If checked, shows the original image in the cover, not the thumbnail version")
            self.add_configs("cover_orig", ConfigType.BOOL, label, help_text)

    def set_config_writing(self):
        if "character" in self.params["features"]:
            self.set_section("writing", _("Writing"))

            label = _("Title")
            help_text = _("Enables field 'title', a short (2-3 words) text added to the character's name")
            self.add_configs("writing_title", ConfigType.BOOL, label, help_text)

            label = _("Cover")
            help_text = _(
                "Enables field 'cover', to shown a specific image in the gallery - until assigned to a participant"
            )
            self.add_configs("writing_cover", ConfigType.BOOL, label, help_text)

            label = _("Hide")
            help_text = _("Enables field 'hide', to be able to hide writing element from participants")
            self.add_configs("writing_hide?", ConfigType.BOOL, label, help_text)

            label = _("Assigned")
            help_text = _(
                "Enables field 'assigned', to track which staff member is responsible for each writing element"
            )
            self.add_configs("writing_assigned", ConfigType.BOOL, label, help_text)

            label = _("Field visibility")
            help_text = _(
                "Normally all character fields (public or private) are shown; with this configuration you can select which ones to display at any given time"
            )
            self.add_configs("writing_field_visibility", ConfigType.BOOL, label, help_text)

            label = _("Disable character finder")
            help_text = (
                _("Disable the system that finds the character number when a special reference symbol is written")
                + " (#, @, ^)"
            )
            self.add_configs("writing_disable_char_finder", ConfigType.BOOL, label, help_text)

            label = _("Replacing names")
            help_text = _("If checked, character names will be automatically replaced by a reference")
            self.add_configs("writing_substitute", ConfigType.BOOL, label, help_text)

            label = _("Paste as text")
            help_text = _("If checked, automatically removes formatting when pasting text into the WYSIWYG editor")
            self.add_configs("writing_paste_text", ConfigType.BOOL, label, help_text)

            label = _("Disable Auto save")
            help_text = _("If checked, automatic saving during editing will be disable for writing elements")
            self.add_configs("writing_disable_auto", ConfigType.BOOL, label, help_text)

            label = _("External access")
            help_text = _(
                "If checked, generates secret urls to share the full character sheet with a not signed up user"
            )
            self.add_configs("writing_external_access", ConfigType.BOOL, label, help_text)

    def set_config_character(self):
        if "campaign" in self.params["features"]:
            self.set_section("campaign", _("Campaign"))
            label = _("Independent factions")
            help_text = _("If checked, do not use the parent event's factions")
            self.add_configs("campaign_faction_indep", ConfigType.BOOL, label, help_text)

        if "px" in self.params["features"]:
            self.set_section("px", _("Experience points"))

            label = _("Player selection")
            help_text = _(
                "If checked, participants may add abilities themselves, by selecting from those that "
                "are visible, and whose pre-requisites they meet."
            )
            self.add_configs("px_user", ConfigType.BOOL, label, help_text)

            label = _("Undo period")
            help_text = _(
                "Time window (in hours) during which the user can revoke a chosen skill and recover spent XP (default is 0)"
            )
            self.add_configs("px_undo", ConfigType.INT, label, help_text)

            label = _("Initial experience points")
            help_text = _("Initial value of experience points for all characters")
            self.add_configs("px_start", ConfigType.INT, label, help_text)

        if "user_character" in self.params["features"]:
            self.set_section("user_character", _("Player editor"))

            label = _("Maximum number")
            help_text = _("Maximum number of characters the player can create")
            self.add_configs("user_character_max", ConfigType.INT, label, help_text)

            label = _("Approval")
            help_text = _("If checked, activates a staff-managed approval process for characters")
            self.add_configs("user_character_approval", ConfigType.BOOL, label, help_text)

            label = _("Relationships")
            help_text = _("If checked, enables participants to write their own list of character relationships")
            self.add_configs("user_character_player_relationships", ConfigType.BOOL, label, help_text)

    def set_config_custom(self):
        if "custom_character" in self.params["features"]:
            self.set_section("custom_character", _("Character customisation"))

            label = _("Name")
            help_text = _("If checked, it allows participants to customise the names of their characters")
            self.add_configs("custom_character_name", ConfigType.BOOL, label, help_text)

            label = _("Profile")
            help_text = _("If checked, allows participants to customise their characters' profile picture")
            self.add_configs("custom_character_profile", ConfigType.BOOL, label, help_text)

            label = _("Pronoun")
            help_text = _("If checked, it allows participants to customise their characters' pronouns")
            self.add_configs("custom_character_pronoun", ConfigType.BOOL, label, help_text)

            label = _("Song")
            help_text = _("If checked, it allows participants to indicate the song of their characters")
            self.add_configs("custom_character_song", ConfigType.BOOL, label, help_text)

            label = _("Private")
            help_text = _(
                "If checked, it allows participants to enter private information on their characters, "
                "visible only to them and the staff"
            )
            self.add_configs("custom_character_private", ConfigType.BOOL, label, help_text)

            label = _("Public")
            help_text = _(
                "If checked, it allows participants to enter public information on their characters, visible to all"
            )
            self.add_configs("custom_character_public", ConfigType.BOOL, label, help_text)

    def set_config_casting(self):
        if "casting" in self.params["features"]:
            self.set_section("casting", _("Casting"))

            label = _("Minimum preferences")
            help_text = _("Minimum number of preferences")
            self.add_configs("casting_min", ConfigType.INT, label, help_text)

            label = _("Maximum preferences")
            help_text = _("Maximum number of preferences")
            self.add_configs("casting_max", ConfigType.INT, label, help_text)

            label = _("Additional Preferences")
            help_text = _("Additional preferences, for random assignment when no solution is found (default 0)")
            self.add_configs("casting_add", ConfigType.INT, label, help_text)

            label = _("Field for exclusions")
            help_text = _(
                "If checked, it adds a field in which the participant can indicate which elements they "
                "wish to avoid altogether"
            )
            self.add_configs("casting_avoid", ConfigType.BOOL, label, help_text)

            label = _("Assignments")
            help_text = _("Number of characters to be assigned (default 1)")
            self.add_configs("casting_characters", ConfigType.INT, label, help_text)

            label = _("Mirror")
            help_text = _("Enables to set a character as a 'mirror' for another, to hide it's true nature")
            self.add_configs("casting_mirror", ConfigType.BOOL, label, help_text)

            label = _("Show statistics")
            help_text = _("If checked, participants will be able to view for each character the preference statistics")
            self.add_configs("casting_show_pref", ConfigType.BOOL, label, help_text)

            label = _("Show history")
            help_text = _("If checked, shows participants the histories of preferences entered")
            self.add_configs("casting_history", ConfigType.BOOL, label, help_text)

    def set_config_accounting(self):
        if "payment" in self.params["features"]:
            self.set_section("payment", _("Payments"))

            label = _("Alert")
            help_text = _(
                "Given a payment deadline, indicates the number of days under which it notifies "
                "the participant to proceed with the payment. Default 30."
            )
            self.add_configs("payment_alert", ConfigType.INT, label, help_text)

            label = _("Causal")
            help_text = _(
                "If present, it indicates the reason for the payment that the participant must put on the payments they make."
            )
            help_text += (
                " "
                + _("You can use the following fields, they will be filled in automatically")
                + ":"
                + "{player_name}, {question_name}"
            )
            self.add_configs("payment_custom_reason", ConfigType.CHAR, label, help_text)

        if "token_credit" in self.params["features"]:
            self.set_section("token_credit", _("Tokens / Credits"))
            label = _("Disable Tokens")
            help_text = _("If checked, no tokens will be used in the entries of this event")
            self.add_configs("token_credit_disable_t", ConfigType.BOOL, label, help_text)

            label = _("Disable credits")
            help_text = _("If checked, no credits will be used in the entries for this event")
            self.add_configs("token_credit_disable_c", ConfigType.BOOL, label, help_text)

        if "bring_friend" in self.params["features"]:
            self.set_section("bring_friend", _("Bring a friend"))
            label = _("Forward discount")
            help_text = _(
                "Value of the discount for the registered participant who gives the code to a friend who signs up"
            )
            self.add_configs("bring_friend_discount_to", ConfigType.INT, label, help_text)

            label = _("Discount back")
            help_text = _(
                "Value of the discount for the friend who signs up using the code of a registered participant"
            )
            self.add_configs("bring_friend_discount_from", ConfigType.INT, label, help_text)

    def set_config_registration(self):
        self.set_section("tickets", _("Tickets"))

        label = "Staff"
        help_text = _("If checked, allow ticket tier: Staff")
        self.add_configs("ticket_staff", ConfigType.BOOL, label, help_text)

        label = "NPC"
        help_text = _("If checked, allow ticket tier: NPC")
        self.add_configs("ticket_npc", ConfigType.BOOL, label, help_text)

        label = "Collaborator"
        help_text = _("If checked, allow ticket tier: Collaborator")
        self.add_configs("ticket_collaborator", ConfigType.BOOL, label, help_text)

        label = "Seller"
        help_text = _("If checked, allow ticket tier: Seller")
        self.add_configs("ticket_seller", ConfigType.BOOL, label, help_text)

        if "pay_what_you_want" in self.params["features"]:
            self.set_section("pay_what_you_want", "Pay what you want")

            label = _("Name")
            help_text = _("Name of the free donation field")
            self.add_configs("pay_what_you_want_label", ConfigType.CHAR, label, help_text)

            label = _("Description")
            help_text = _("Description of free donation")
            self.add_configs("pay_what_you_want_descr", ConfigType.CHAR, label, help_text)

        if "reduced" in self.params["features"]:
            self.set_section("reduced", _("Patron / Reduced"))
            label = "Ratio"
            help_text = _(
                "Indicates the ratio between reduced and patron tickets, multiplied by 10. "
                "Example: 10 -> 1 reduced ticket for 1 patron ticket. 20 -> 2 reduced tickets for "
                "1 patron ticket. 5 -> 1 reduced ticket for 2 patron tickets"
            )
            self.add_configs("reduced_ratio", ConfigType.INT, label, help_text)

        if "filler" in self.params["features"]:
            self.set_section("filler", _("Ticket Filler"))
            label = _("Free registration")
            help_text = _(
                "If checked, participants may sign up as fillers at any time; otherwise, they may only "
                "do so if the stipulated number of characters has been reached"
            )
            self.add_configs("filler_always", ConfigType.BOOL, label, help_text)

        if "lottery" in self.params["features"]:
            self.set_section("lottery", _("Lottery"))
            label = _("Number of extractions")
            help_text = _("Number of tickets to be drawn")
            self.add_configs("lottery_num_draws", ConfigType.INT, label, help_text)

            label = _("Conversion ticket")
            help_text = _("Name of the ticket into which to convert")
            self.add_configs("lottery_ticket", ConfigType.CHAR, label, help_text)


class OrgaAppearanceForm(MyCssForm):
    page_title = _("Event Appearance")

    page_info = _("This page allows you to change the appearance and presentation of the event")

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
        help_text=_("These CSS commands will be carried over to all pages in your Association space"),
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

    page_info = _("This page allows you to edit event-specific texts")

    class Meta:
        abstract = True
        model = EventText
        exclude = ("number",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ch = EventTextType.choices
        delete_choice = []

        if "character" not in self.params["features"]:
            delete_choice.append(EventTextType.INTRO)

        if not self.params["event"].get_config("user_character_approval", False):
            delete_choice.extend(
                [EventTextType.CHARACTER_PROPOSED, EventTextType.CHARACTER_APPROVED, EventTextType.CHARACTER_REVIEW]
            )

        for tp in delete_choice:
            ch = remove_choice(ch, tp)
        self.fields["typ"].choices = ch

        help_texts = {
            EventTextType.INTRO: _("Text show at the start of all character sheets"),
            EventTextType.TOC: _("Terms and conditions of signup, shown in a page linked in the registration form"),
            EventTextType.REGISTER: _("Added to the registration page, before the form"),
            EventTextType.SEARCH: _("Added at the top of the search page of characters"),
            EventTextType.SIGNUP: _("Added at the bottom of mail confirming signup to participants"),
            EventTextType.ASSIGNMENT: _("Added at the bottom of mail notifying participants of character assignment"),
            EventTextType.CHARACTER_PROPOSED: _(
                "Content of mail notifying participants of their character in proposed status"
            ),
            EventTextType.CHARACTER_APPROVED: _(
                "Content of mail notifying participants of their character in approved status"
            ),
            EventTextType.CHARACTER_REVIEW: _(
                "Content of mail notifying participants of their character in review status"
            ),
        }
        help_text = []
        for choice_typ, text in help_texts.items():
            if choice_typ in delete_choice:
                continue
            help_text.append(f"<b>{choice_typ.label}</b>: {text}")
        self.fields["typ"].help_text = " - ".join(help_text)

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

    page_info = _("This page allows you to change the access roles for the event")

    load_templates = ["share"]

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

    page_info = _("This page allows you to edit the event navigation buttons")

    class Meta:
        model = EventButton
        exclude = ("number",)


class OrgaRunForm(ConfigForm):
    page_title = _("Session")

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

        self.main_class = ""

        if "exe" not in self.params:
            self.prevent_canc = True

        dl = []

        if not self.instance.pk or not self.instance.event:
            event_field = forms.ChoiceField(
                required=True,
                choices=[(el.id, el.name) for el in Event.objects.filter(assoc_id=self.params["a_id"], template=False)],
            )
            self.fields = {"event": event_field} | self.fields
            self.fields["event"].widget = EventS2Widget()
            self.fields["event"].widget.set_assoc(self.params["a_id"])
            self.fields["event"].help_text = _("Select the event of this new session")
            self.choose_event = True
            self.page_info = _("This page allows you to add a new session of an existing event")
        else:
            self.page_info = _("This page allows you to change the date settings of this event")

        # do not show cancelled or done options for development if date are not set
        if not self.instance.pk or not self.instance.start or not self.instance.end:
            self.fields["development"].choices = [
                (choice.value, choice.label)
                for choice in DevelopStatus
                if choice not in [DevelopStatus.CANC, DevelopStatus.DONE]
            ]
        status_text = {
            DevelopStatus.START: _("Not visible to users"),
            DevelopStatus.SHOW: _("Visible in the homepage"),
            DevelopStatus.DONE: _("Concluded and archived"),
            DevelopStatus.CANC: _("Not active anymore"),
        }
        self.fields["development"].help_text = ", ".join(
            f"<b>{label}</b>: {status_text[DevelopStatus(value)]}"
            for value, label in self.fields["development"].choices
        )

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

        if not self.params["event"].get_config("writing_field_visibility", False):
            return

        help_text = _(
            "Selected fields will be displayed as follows: public fields visible to all participants, "
            "private fields visible only to assigned participants"
        )

        shows = _get_writing_elements()

        basics = QuestionType.get_basic_types()
        self.set_section("visibility", _("Visibility"))
        for s in shows:
            if "writing_fields" not in self.params or s[0] not in self.params["writing_fields"]:
                continue
            if s[0] == "plot":
                continue
            fields = self.params["writing_fields"][s[0]]["questions"]
            extra = []
            for _id, field in fields.items():
                typ = field["typ"]
                if typ in basics:
                    typ = str(field["id"])

                extra.append((typ, field["name"]))

            self.add_configs(f"show_{s[0]}", ConfigType.MULTI_BOOL, s[1], help_text, extra=extra)

        shows = []

        addit_show = {
            "plot": _("Plots"),
            "relationships": _("Relationships"),
            "speedlarp": _("Speedlarp"),
            "prologue": _("Prologues"),
            "workshop": _("Workshop"),
            "print_pdf": _("PDF"),
        }

        extra = []
        for key, display in addit_show.items():
            if self.instance.pk and key in self.params["features"]:
                extra.append((key, display))
        if extra:
            help_text = _("Selected elements will be shown to participants")
            self.add_configs("show_addit", ConfigType.MULTI_BOOL, _("Elements"), help_text, extra=extra)

        self.set_section("visibility", _("Visibility"))
        for s in shows:
            self.add_configs(f"show_{s[0]}", ConfigType.BOOL, s[1], s[2])

        return ls

    def clean(self):
        cleaned_data = super().clean()
        if "end" not in cleaned_data or not cleaned_data["end"]:
            raise ValidationError({"end": _("You need to define the end date!")})

        if "start" not in cleaned_data or not cleaned_data["start"]:
            raise ValidationError({"start": _("You need to define the start date!")})

        if cleaned_data["end"] < cleaned_data["start"]:
            raise ValidationError({"end": _("End date cannot be before start date!")})

        return cleaned_data


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
        "This page allows you to select the features of a template (click on a feature to show its description)"
    )

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


class OrgaQuickSetupForm(QuickSetupForm):
    page_title = _("Quick Setup")

    page_info = _("This page allows you to perform a quick setup of the most important settings for your new event")

    class Meta:
        model = Event
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setup = {
            "registration_open": (
                True,
                _("Registration opening date"),
                _("Do you want to open registrations at a specific date and time instead of immediately"),
            ),
            "registration_secret": (
                True,
                _("Early registration link"),
                _("Do you want to enable a secret registration link to allow early sign-ups"),
            ),
            "player_cancellation": (
                True,
                _("Signup cancellation"),
                _("Do you want to allow users to cancel their registrations on their own"),
            ),
            "reg_installments": (
                True,
                _("Payment installments"),
                _("Do you want to split the registration fee into fixed payment installments"),
            ),
            "reg_quotas": (
                True,
                _("Payment quotas"),
                _("Do you want to split the registration fee into dynamic payment quotas"),
            ),
            "pay_what_you_want": (
                True,
                _("Voluntary donation"),
                _("Do you want to allow users to add a voluntary donation to their registration fee"),
            ),
        }
        if self.instance.assoc.skin_id == 1:
            self.setup.update(
                {
                    "character": (
                        True,
                        _("Characters"),
                        _("Do you want to manage characters assigned to registered participants"),
                    ),
                    "casting": (
                        True,
                        _("Casting algorithm"),
                        _("Do you want to assign characters using a casting algorithm"),
                    ),
                    "user_character": (
                        True,
                        _("Player editor"),
                        _("Do you want to allow participants to create their own characters"),
                    ),
                }
            )

        self.init_fields(get_event_features(self.instance.pk))


class OrgaPreferencesForm(ConfigForm):
    page_title = _("Personal preferences")

    page_info = _("This page allows you to set your personal preferences on the interface")

    class Meta:
        model = Member
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True
        self.show_sections = True

    def set_configs(self):
        basics = QuestionType.get_basic_types()
        event_id = self.params["event"].id

        self.set_section("open", "Default fields")

        help_text = _("Select which fields should open automatically when the list is displayed")

        self._add_reg_configs(event_id, help_text)

        # Add writings fields
        shows = _get_writing_elements()
        for s in shows:
            self.add_writing_configs(basics, event_id, help_text, s)

    def _add_reg_configs(self, event_id, help_text):
        if not has_event_permission(
            self.params, self.params["request"], self.params["event"].slug, "orga_registrations"
        ):
            return

        # Add registration fields
        extra = []
        feature_fields = [
            ("", "#load_accounting", _("Accounting")),
            ("", "email", _("Email")),
            ("", "date", _("Chronology")),
            ("unique_code", "special_cod", _("Unique code")),
            ("additional_tickets", "additionals", _("Additional")),
            ("gift", "gift", _("Gift")),
            ("membership", "membership", _("Member")),
            ("faction", "factions", _("Factions")),
            ("custom_character", "custom", _("Customisations")),
            ("reg_surcharges", "sur", _("Surcharge")),
            ("discount", "disc", _("Discounts")),
        ]
        self.add_feature_extra(extra, feature_fields)
        fields = _get_registration_fields(self.params, self.params["request"].user.member)
        max_length = 20
        if fields:
            extra.extend(
                [
                    (
                        f".lq_{field_id}",
                        field.name if len(field.name) <= max_length else field.name[: max_length - 5] + " [...]",
                    )
                    for field_id, field in fields.items()
                ]
            )
        self.add_configs(
            f"open_registration_{event_id}", ConfigType.MULTI_BOOL, _("Registrations"), help_text, extra=extra
        )

    def add_writing_configs(self, basics, event_id, help_text, s):
        mapping = _get_writing_mapping()
        if mapping.get(s[0]) not in self.params["features"]:
            return

        if "writing_fields" not in self.params or s[0] not in self.params["writing_fields"]:
            return

        if not has_event_permission(self.params, self.params["request"], self.params["event"].slug, f"orga_{s[0]}s"):
            return

        fields = self.params["writing_fields"][s[0]]["questions"]
        extra = []

        for _id, field in fields.items():
            if field["typ"] == "name":
                continue

            if field["typ"] in basics:
                tog = f".lq_{field['id']}"
            else:
                tog = f"q_{field['id']}"

            extra.append((tog, field["name"]))

        if s[0] == "character":
            if self.params["event"].get_config("user_character_max", 0):
                extra.append(("player", _("Player")))
            if self.params["event"].get_config("user_character_approval", False):
                extra.append(("status", _("Status")))
            feature_fields = [
                ("px", "px", _("XP")),
                ("plot", "plots", _("Plots")),
                ("relationships", "relationships", _("Relationships")),
                ("speedlarp", "speedlarp", _("speedlarp")),
            ]
            self.add_feature_extra(extra, feature_fields)
        elif s[0] in ["faction", "plot"]:
            extra.append(("characters", _("Characters")))
        elif s[0] in ["quest", "trait"]:
            extra.append(("traits", _("Traits")))

        extra.append(("stats", "Stats"))

        self.add_configs(f"open_{s[0]}_{event_id}", ConfigType.MULTI_BOOL, s[1], help_text, extra=extra)

    def add_feature_extra(self, extra, feature_fields):
        for field in feature_fields:
            if field[0] and field[0] not in self.params["features"]:
                continue
            extra.append((field[1], field[2]))
