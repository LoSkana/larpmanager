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
from django.core.exceptions import ValidationError
from django.forms import Textarea
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext

from larpmanager.cache.feature import get_assoc_features, reset_assoc_features
from larpmanager.forms.base import MyCssForm, MyForm
from larpmanager.forms.config import ConfigForm, ConfigType
from larpmanager.forms.feature import FeatureForm, QuickSetupForm
from larpmanager.forms.utils import (
    AssocMemberS2WidgetMulti,
    SlugInput,
    prepare_permissions_role,
    remove_choice,
    save_permissions_role,
)
from larpmanager.models.access import AssocPermission, AssocRole
from larpmanager.models.association import Association, AssocText, AssocTextType


class ExeAssociationForm(MyForm):
    page_title = _("Settings")

    page_info = _("This page allows you to change the main settings of your Organization")

    class Meta:
        model = Association
        exclude = (
            "features",
            "background",
            "font",
            "pri_rgb",
            "sec_rgb",
            "ter_rgb",
            "payment_methods",
            "promoter",
            "gdpr_contract",
            "optional_fields",
            "mandatory_fields",
            "review_done",
            "images_shared",
            "plan",
            "skin",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.prevent_canc = True

        for m in ["slug"]:
            del self.fields[m]


class ExeAssocTextForm(MyForm):
    page_title = _("Texts")

    page_info = _("This page allows you to edit organization-specific text")

    class Meta:
        abstract = True
        model = AssocText
        exclude = ("number",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ch = AssocTextType.choices
        delete_choice = [AssocTextType.PRIVACY]

        if "legal_notice" not in self.params["features"]:
            delete_choice.append(AssocTextType.LEGAL)

        if "receipts" not in self.params["features"]:
            delete_choice.append(AssocTextType.RECEIPT)

        if "membership" not in self.params["features"]:
            delete_choice.extend([AssocTextType.MEMBERSHIP, AssocTextType.STATUTE])

        if "remind" not in self.params["features"]:
            delete_choice.extend(
                [
                    AssocTextType.REMINDER_MEMBERSHIP,
                    AssocTextType.REMINDER_MEMBERSHIP_FEE,
                    AssocTextType.REMINDER_PAY,
                    AssocTextType.REMINDER_PROFILE,
                ]
            )
        elif "membership" not in self.params["features"]:
            delete_choice.extend([AssocTextType.REMINDER_MEMBERSHIP, AssocTextType.REMINDER_MEMBERSHIP_FEE])
        else:
            delete_choice.extend([AssocTextType.REMINDER_PROFILE])

        for tp in delete_choice:
            ch = remove_choice(ch, tp)

        self.fields["typ"].choices = ch

        help_texts = {
            AssocTextType.PROFILE: _("Added at the top of the user profile page"),
            AssocTextType.HOME: _("Added at the top of the main calendar page"),
            AssocTextType.SIGNUP: _("Added at the bottom of all mails confirming signup to participants"),
            AssocTextType.MEMBERSHIP: _("Content of the membership request filled with user data"),
            AssocTextType.STATUTE: _("Added to the membership page as the paragraph for statute info"),
            AssocTextType.LEGAL: _("Content of legal notice page linked at the bottom of all pages"),
            AssocTextType.FOOTER: _("Added to the bottom of all pages"),
            AssocTextType.TOC: _("Terms and conditions of signup, shown in a page linked in the registration form"),
            AssocTextType.RECEIPT: _("Content of the receipt created for each payment and sent to participants"),
            AssocTextType.SIGNATURE: _("Added to the bottom of all mails sent"),
            AssocTextType.PRIVACY: _("Content of privacy page linked at the bottom of all pages"),
            AssocTextType.REMINDER_MEMBERSHIP: _(
                "Content of mail reminding participants to fill their membership request"
            ),
            AssocTextType.REMINDER_MEMBERSHIP_FEE: _(
                "Content of mail reminding participants to pay the membership fee"
            ),
            AssocTextType.REMINDER_PAY: _("Content of mail reminding participants to pay their signup fee"),
            AssocTextType.REMINDER_PROFILE: _("Content of mail reminding participants to fill their profile"),
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
            res = AssocText.objects.filter(assoc_id=self.params["request"].assoc["id"], default=True, typ=typ)
            if res.count() > 0 and res.first().pk != self.instance.pk:
                self.add_error("default", "There is already a language set as default!")

        # check if there is already a language with that type
        res = AssocText.objects.filter(assoc_id=self.params["a_id"], language=language, typ=typ)
        if res.count() > 0:
            first = res.first()
            if first.pk != self.instance.pk:
                self.add_error("language", "There is already a language of this type!")

        return cleaned_data


class ExeAssocRoleForm(MyForm):
    page_title = _("Roles")

    page_info = _("This page allows you to edit the roles of the association")

    load_templates = ["share"]

    class Meta:
        model = AssocRole
        fields = ("name", "members", "assoc")
        widgets = {"members": AssocMemberS2WidgetMulti}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].widget.set_assoc(self.params["a_id"])
        prepare_permissions_role(self, AssocPermission)

    def save(self, commit=True):
        instance = super().save(commit=commit)
        save_permissions_role(instance, self)
        return instance


class ExeAppearanceForm(MyCssForm):
    page_title = _("Appearance")

    page_info = _(
        "This page allows you to change the appearance settings and presentation of the "
        "management system for your Organization"
    )

    class Meta:
        model = Association
        fields = ("background", "font", "pri_rgb", "sec_rgb", "ter_rgb")

    assoc_css = forms.CharField(
        widget=Textarea(attrs={"rows": 15}),
        required=False,
        help_text=_(
            "Freely insert CSS commands, they will be reported in all pages  in the space of "
            "your Organization. In this way you can customize freely the appearance."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True
        self.show_link = ["id_assoc_css"]

    @staticmethod
    def get_css_path(instance):
        p = f"css/{instance.slug}_{instance.css_code}.css"
        return p

    @staticmethod
    def get_input_css():
        return "assoc_css"


class ExeFeatureForm(FeatureForm):
    page_title = _("Features")

    page_info = _(
        "This page allows you to select the features activated for the organization, and all its events (click on a feature to show its description)"
    )

    class Meta:
        model = Association
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_features(True)

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._save_features(instance)
        reset_assoc_features(instance.id)
        return instance


class ExeConfigForm(ConfigForm):
    page_title = _("Configuration")

    page_info = _("This page allows you to edit the configuration of the activated features")

    section_replace = True

    load_js = ["config-search"]

    istr = []

    class Meta:
        model = Association
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def set_configs(self):
        # CALENDAR
        self.set_section("interface", _("Interface"))

        label = _("Old interface")
        help_text = _("If checked: uses old interface")
        self.add_configs("interface_old", ConfigType.BOOL, label, help_text)

        # CALENDAR
        self.set_section("calendar", _("Calendar"))

        label = _("Past events")
        help_text = _("If checked: shows a link in the calendar to past events")
        self.add_configs("calendar_past_events", ConfigType.BOOL, label, help_text)

        label = _("Website")
        help_text = _("If checked: shows the website for each event")
        self.add_configs("calendar_website", ConfigType.BOOL, label, help_text)

        label = _("Description")
        help_text = _("If checked: shows the description for each event")
        self.add_configs("calendar_description", ConfigType.BOOL, label, help_text)

        label = _("Where")
        help_text = _("If checked: shows the position for each event")
        self.add_configs("calendar_where", ConfigType.BOOL, label, help_text)

        label = _("Authors")
        help_text = _("If checked: shows the list of authors for each event")
        self.add_configs("calendar_authors", ConfigType.BOOL, label, help_text)

        label = pgettext("event", "Genre")
        help_text = pgettext("event", "If checked: shows the genre for each event")
        self.add_configs("calendar_genre", ConfigType.BOOL, label, help_text)

        label = _("Tagline")
        help_text = _("If checked: shows the tagline for each event")
        self.add_configs("calendar_tagline", ConfigType.BOOL, label, help_text)

        # MAIL
        self.set_section("email", _("Email notifications"))

        if self.instance.main_mail:
            label = _("Carbon copy")
            help_text = _("If checked: Sends the main mail a copy of all mails sent to participants")
            self.add_configs("mail_cc", ConfigType.BOOL, label, help_text)

        label = _("New signup")
        help_text = _("If checked: Send an email notification to the organisers for new signups")
        self.add_configs("mail_signup_new", ConfigType.BOOL, label, help_text)

        label = _("Signup update")
        help_text = _("If checked: Send an email notification to the organisers for updated signups")
        self.add_configs("mail_signup_update", ConfigType.BOOL, label, help_text)

        label = _("Signup cancellation")
        help_text = _("If checked: Send a notification email to the organisers for cancellation of registration")
        self.add_configs("mail_signup_del", ConfigType.BOOL, label, help_text)

        label = _("Payments received")
        help_text = _("If checked: Send an email to the organisers for each payment received")
        self.add_configs("mail_payment", ConfigType.BOOL, label, help_text)

        self.set_config_members()
        self.set_config_accounting()
        self.set_config_einvoice()
        self.set_config_others()

    def set_config_others(self):
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

        if "centauri" in self.params["features"]:
            self.set_section("centauri", _("Easter egg"))

            label = _("Probability")
            help_text = _("Probability of showing the special page (out of thousands)")
            self.add_configs("centauri_prob", ConfigType.INT, label, help_text)

            label = _("Badge")
            help_text = _("Name of badge to be awarded")
            self.add_configs("centauri_badge", ConfigType.CHAR, label, help_text)

            label = _("Description")
            help_text = _("Description to be shown on the special page")
            self.add_configs("centauri_descr", ConfigType.CHAR, label, help_text)

            label = _("Page")
            help_text = _("Contents of the special page")
            self.add_configs("centauri_content", ConfigType.HTML, label, help_text)

        if "campaign" in self.params["features"]:
            self.set_section("campaign", _("Campaign"))

            label = _("Move registration event")
            help_text = _("Allow to switch registration between events")
            self.add_configs("campaign_switch", ConfigType.BOOL, label, help_text)

    def set_config_members(self):
        # USERS
        self.set_section("users", _("Users"))

        label = _("Event history")
        help_text = _("If checked: in the public page of an user shows a list of all events attended")
        self.add_configs("player_larp_history", ConfigType.BOOL, label, help_text)

        if "deadlines" in self.params["features"]:
            self.set_section("deadlines", _("Deadline"))

            label = _("Tolerance")
            help_text = _(
                "Number of days past the deadline beyond which registrations are marked to be cancelled (default 30 days)"
            )
            self.add_configs("deadline_tolerance", ConfigType.INT, label, help_text)

            label = _("Frequency")
            help_text = _("Sets how often reminder emails are sent, in days (if not set, no emails are sent)")
            self.add_configs("deadline_days", ConfigType.INT, label, help_text)

        if "membership" in self.params["features"]:
            self.set_section("membership", _("Members"))

            label = _("Age")
            help_text = _("Minimum age of members (leave empty for no limit)")
            self.add_configs("membership_age", ConfigType.INT, label, help_text)

            label = _("Annual fee")
            help_text = _("Annual fee required of members, starting from the beginning of the membership year")
            self.add_configs("membership_fee", ConfigType.INT, label, help_text)

            label = _("Start day")
            help_text = _("Day of the year from which the membership year begins, in DD-MM format")
            self.add_configs("membership_day", ConfigType.CHAR, label, help_text)

            label = _("Months free quota")
            help_text = _(
                "Number of months, starting from the beginning of the membership year, for which "
                "to make free membership fee payment"
            )
            self.add_configs("membership_grazing", ConfigType.INT, label, help_text)

        if "vote" in self.params["features"]:
            self.set_section("vote", _("Voting"))

            label = _("Active")
            help_text = _("If checked: members can vote")
            self.add_configs("vote_open", ConfigType.BOOL, label, help_text)

            label = _("Candidates")
            help_text = _("Candidates at the polls")
            self.add_configs("vote_candidates", ConfigType.MEMBERS, label, help_text, self.instance.id)

            label = _("Minimum votes")
            help_text = _("Minimum number of votes")
            self.add_configs("vote_min", ConfigType.INT, label, help_text)

            label = _("Maximum votes")
            help_text = _("Maximum number of votes")
            self.add_configs("vote_max", ConfigType.INT, label, help_text)

        if "remind" in self.params["features"]:
            self.set_section("remind", _("Reminder"))

            label = _("Frequency")
            help_text = _("Sets how often reminder emails are sent, in days (default: 5)")
            self.add_configs("remind_days", ConfigType.INT, label, help_text)

            label = _("Holidays")
            help_text = _("If checked: the system will send reminds the days on which holidays fall")
            self.add_configs("remind_holidays", ConfigType.BOOL, label, help_text)

    def set_config_accounting(self):
        if "payment" in self.params["features"]:
            self.set_section("payment", _("Payments"))

            label = _("Charge transaction fees to participant")
            help_text = _(
                "If enabled, the system will automatically add payment gateway fees to the ticket price, so the participant covers them instead of the organization"
            )
            self.add_configs("payment_fees_user", ConfigType.BOOL, label, help_text)

            label = _("Disable amount change")
            help_text = _(
                "If checked: Hides the possibility for the participant to change the payment amount for his entries"
            )
            self.add_configs("payment_hide_amount", ConfigType.BOOL, label, help_text)

            label = _("Unique code")
            help_text = _("If checked: Adds a unique code to each payment, which helps in being able to recognize it")
            self.add_configs("payment_special_code", ConfigType.BOOL, label, help_text)

        if "vat" in self.params["features"]:
            self.set_section("vat", _("VAT"))

            label = _("Ticket")
            help_text = _("Percentage of VAT to be calculated on the ticket cost alone")
            self.add_configs("vat_ticket", ConfigType.INT, label, help_text)

            label = _("Options")
            help_text = _("Percentage of VAT to be calculated on the sum of the costs of the registration options")
            self.add_configs("vat_options", ConfigType.INT, label, help_text)

        if "token_credit" in self.params["features"]:
            self.set_section("token_credit", _("Tokens / Credits"))
            label = _("Token name")
            help_text = _("Name to be displayed for tokens")
            self.add_configs("token_credit_token_name", ConfigType.CHAR, label, help_text)

            label = _("Name credits")
            help_text = _("Name to be displayed for credits")
            self.add_configs("token_credit_credit_name", ConfigType.CHAR, label, help_text)

        if "treasurer" in self.params["features"]:
            self.set_section("treasurer", _("Treasury"))
            label = _("Appointees")
            help_text = _("Treasury appointees")
            self.add_configs("treasurer_appointees", ConfigType.MEMBERS, label, help_text, self.instance.id)

        if "organization_tax" in self.params["features"]:
            self.set_section("organization_tax", _("Organisation fee"))
            label = _("Percentage")
            help_text = _(
                "Percentage of takings calculated as a fee for association infrastructure (in "
                "whole numbers from 0 to 100)"
            )
            self.add_configs("organization_tax_perc", ConfigType.INT, label, help_text)

    def set_config_einvoice(self):
        if "e-invoice" not in self.params["features"]:
            return

        self.set_section("einvoice", _("Electronic invoice"))

        label = _("Name")
        help_text = ""
        self.add_configs("einvoice_denominazione", ConfigType.CHAR, label, help_text)

        label = _("Fiscal code")
        help_text = ""
        self.add_configs("einvoice_idcodice", ConfigType.CHAR, label, help_text)

        label = _("VAT No")
        help_text = ""
        self.add_configs("einvoice_partitaiva", ConfigType.CHAR, label, help_text)

        label = _("Tax regime")
        help_text = "RF19: forfettario, RF01: ordinario, RF05: agevolato, RF07: commerciale"
        self.add_configs("einvoice_regimefiscale", ConfigType.CHAR, label, help_text)

        label = _("VAT rate")
        help_text = _("If absent, indicate 0")
        self.add_configs("einvoice_aliquotaiva", ConfigType.CHAR, label, help_text)

        label = _("Nature")
        help_text = _("Indicate only if rate 0")
        self.add_configs("einvoice_natura", ConfigType.CHAR, label, help_text)

        label = _("Address")
        help_text = ""
        self.add_configs("einvoice_indirizzo", ConfigType.CHAR, label, help_text)

        label = _("House number")
        help_text = ""
        self.add_configs("einvoice_numerocivico", ConfigType.CHAR, label, help_text)

        label = _("Cap")
        help_text = ""
        self.add_configs("einvoice_cap", ConfigType.CHAR, label, help_text)

        label = _("Municipality")
        help_text = ""
        self.add_configs("einvoice_comune", ConfigType.CHAR, label, help_text)

        label = _("Province")
        help_text = _("Code two capital letters")
        self.add_configs("einvoice_provincia", ConfigType.CHAR, label, help_text)

        label = _("Nation")
        help_text = _("Code two capital letters")
        self.add_configs("einvoice_nazione", ConfigType.CHAR, label, help_text)

        label = _("Recipient Code")
        help_text = _("Intermediary channel code")
        self.add_configs("einvoice_codicedestinatario", ConfigType.CHAR, label, help_text)


class FirstAssociationForm(MyForm):
    class Meta:
        model = Association
        fields = ("name", "profile", "slug")
        widgets = {
            "slug": SlugInput,
        }

    def clean_slug(self):
        data = self.cleaned_data["slug"]
        # print(data)
        # check if already used
        lst = Association.objects.filter(slug=data)
        if self.instance is not None and self.instance.pk is not None:
            lst.exclude(pk=self.instance.pk)
        if lst.count() > 0:
            raise ValidationError("Slug already used!")

        return data


class ExeQuickSetupForm(QuickSetupForm):
    page_title = _("Quick Setup")

    page_info = _(
        "This page allows you to perform a quick setup of the most important settings for your new organization"
    )

    class Meta:
        model = Association
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setup = {
            "payment": (True, _("Payments"), _("Do you want to accept payments processed through the system")),
            "payment_fees_user": (
                False,
                _("Transaction fees"),
                _(
                    "Do you want to add payment gateway fees to the ticket price, so that the user pays them instead of the organization"
                ),
            ),
            "membership": (True, _("Membership"), _("Do you want users to join events only after an approval process")),
            "deadlines": (
                True,
                _("Deadlines"),
                _("Do you want a dashboard to track and manage deadlines missed by registered users"),
            ),
            "remind": (
                True,
                _("Reminders"),
                _("Do you want to enable an automatic email reminder system for registered users who miss a deadline"),
            ),
            "help": (True, _("Help"), _("Do you want to manage user help requests directly through the platform")),
            "donate": (True, _("Donations"), _("Do you want to allow users to make voluntary donations")),
        }
        if self.instance.skin_id == 1:
            self.setup.update(
                {
                    "campaign": (
                        True,
                        _("Campaign"),
                        _("Do you want to manage campaigns, a series of events that share the same characters"),
                    ),
                }
            )

        self.init_fields(get_assoc_features(self.instance.pk))
