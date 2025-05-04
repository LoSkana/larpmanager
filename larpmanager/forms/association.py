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

from larpmanager.forms.base import MyCssForm, MyForm
from larpmanager.forms.utils import (
    AssocMemberS2WidgetMulti,
    ConfigType,
    SlugInput,
    prepare_permissions_role,
    remove_choice,
    save_permissions_role,
)
from larpmanager.models.access import AssocPermission, AssocRole
from larpmanager.models.association import Association, AssocText


class ExeAssociationForm(MyForm):
    page_title = _("Settings")

    page_info = _("This page allows you to change the main settings of your Organization.")

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
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.prevent_canc = True

        for m in ["slug"]:
            del self.fields[m]


class ExeAssocTextForm(MyForm):
    page_title = _("Texts")

    page_info = _("This page allows you to edit organization-specific text.")

    class Meta:
        abstract = True
        model = AssocText
        exclude = ("number",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ch = AssocText.TYPE_CHOICES
        ch = remove_choice(ch, AssocText.PRIVACY)
        if "assoc_tac" not in self.params["features"]:
            ch = remove_choice(ch, AssocText.TOC)
        if "legal_notice" not in self.params["features"]:
            ch = remove_choice(ch, AssocText.LEGAL)
        if "membership" not in self.params["features"]:
            ch = remove_choice(ch, AssocText.MEMBERSHIP)
            ch = remove_choice(ch, AssocText.STATUTE)
        if "receipts" not in self.params["features"]:
            ch = remove_choice(ch, AssocText.RECEIPT)
        self.fields["typ"].choices = ch

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

    page_info = _("This page allows you to edit the roles of the association.")

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
        "management system for your Organization."
    )

    class Meta:
        model = Association
        fields = ("background", "font", "pri_rgb", "sec_rgb", "ter_rgb")

    assoc_css = forms.CharField(
        widget=Textarea(attrs={"cols": 80, "rows": 15}),
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


class ExeConfigForm(MyForm):
    page_title = _("Configuration")

    page_info = _("This page allows you to edit the configuration of the activated features.")

    section_replace = True

    load_js = "config-search"

    istr = []

    class Meta:
        model = Association
        fields = ()

    def get_config_fields(self):
        ls = []

        # ## CALENDAR
        section = _("Calendar")

        label = _("Show event links")
        help_text = _("If checked: shows a link to the event in the navigation bar.")
        ls.append(("calendar", "show_event", ConfigType.BOOL, section, label, help_text))

        label = _("Past events")
        help_text = _("If checked: shows a link in the calendar to past events.")
        ls.append(("calendar", "past_events", ConfigType.BOOL, section, label, help_text))

        label = _("Website")
        help_text = _("If checked: shows the website for each event")
        ls.append(("calendar", "website", ConfigType.BOOL, section, label, help_text))

        label = _("Description")
        help_text = _("If checked: shows the description for each event")
        ls.append(("calendar", "description", ConfigType.BOOL, section, label, help_text))

        label = _("Where")
        help_text = _("If checked: shows the position for each event")
        ls.append(("calendar", "where", ConfigType.BOOL, section, label, help_text))

        label = _("Authors")
        help_text = _("If checked: shows the list of authors for each event")
        ls.append(("calendar", "authors", ConfigType.BOOL, section, label, help_text))

        label = pgettext("event", "Genre")
        help_text = pgettext("event", "If checked: shows the genre for each event")
        ls.append(("calendar", "genre", ConfigType.BOOL, section, label, help_text))

        label = _("Tagline")
        help_text = _("If checked: shows the tagline for each event")
        ls.append(("calendar", "tagline", ConfigType.BOOL, section, label, help_text))

        # ## INTERFACE

        section = _("Interface")
        label = _("Quick links organisation")
        help_text = _("If checked: In the event management panel, it also shows the association management links")
        ls.append(("interface", "admin_links", ConfigType.BOOL, section, label, help_text))

        # ## MAIL
        section = _("Email notifications")

        label = _("Carbon copy")
        help_text = _("If checked: Sends the main mail a copy of all mails sent to players")
        ls.append(("mail", "cc", ConfigType.BOOL, section, label, help_text))

        label = _("New signup")
        help_text = _("If checked: Send an email notification to the organisers for new signups")
        ls.append(("mail", "signup_new", ConfigType.BOOL, section, label, help_text))

        label = _("Signup update")
        help_text = _("If checked: Send an email notification to the organisers for updated signups")
        ls.append(("mail", "signup_update", ConfigType.BOOL, section, label, help_text))

        label = _("Signup cancellation")
        help_text = _("If checked: Send a notification email to the organisers for cancellation of registration")
        ls.append(("mail", "signup_del", ConfigType.BOOL, section, label, help_text))

        label = _("Payments received")
        help_text = _("If checked: Send an email to the organisers for each payment received")
        ls.append(("mail", "payment", ConfigType.BOOL, section, label, help_text))

        self.get_config_members(ls)

        self.get_config_accounting(ls)

        self.get_config_einvoice(ls)

        self.get_config_others(ls)

        return ls

    def get_config_others(self, ls):
        if "custom_mail" in self.params["features"]:
            section = _("Customised mail server")
            help_text = ""

            label = _("Use TLD")
            ls.append(("mail_server", "use_tls", ConfigType.BOOL, section, label, help_text))

            label = _("Host Address")
            ls.append(("mail_server", "host", ConfigType.CHAR, section, label, help_text))

            label = _("Port")
            ls.append(("mail_server", "port", ConfigType.INT, section, label, help_text))

            label = _("Username of account")
            ls.append(("mail_server", "host_user", ConfigType.CHAR, section, label, help_text))

            label = _("Password of account")
            ls.append(("mail_server", "host_password", ConfigType.CHAR, section, label, help_text))

        if "centauri" in self.params["features"]:
            section = _("Centarui")

            label = _("Probability")
            help_text = _("Probability of showing the special page (out of thousands)")
            ls.append(("centauri", "prob", ConfigType.INT, section, label, help_text))

            label = _("Badge")
            help_text = _("Name of badge to be awarded")
            ls.append(("centauri", "badge", ConfigType.CHAR, section, label, help_text))

            label = _("Description")
            help_text = _("Description to be shown on the special page")
            ls.append(("centauri", "descr", ConfigType.CHAR, section, label, help_text))

            label = _("Page")
            help_text = _("Contents of the special page")
            ls.append(("centauri", "content", ConfigType.HTML, section, label, help_text))

    def get_config_members(self, ls):
        if "deadlines" in self.params["features"]:
            section = _("Deadline")

            label = _("Tolerance")
            help_text = _(
                "Number of days past the deadline beyond which registrations are marked to be cancelled (default 30 days)"
            )
            ls.append(("deadline", "tolerance", ConfigType.INT, section, label, help_text))

            label = _("Frequency")
            help_text = _("Sets how often reminder emails are sent, in days (if not set, no emails are sent)")
            ls.append(("deadline", "days", ConfigType.INT, section, label, help_text))

        if "membership" in self.params["features"]:
            section = _("Members")

            label = _("Age")
            help_text = _("Minimum age of members")
            ls.append(("membership", "age", ConfigType.INT, section, label, help_text))

            label = _("Annual fee")
            help_text = _("Annual fee required of members, starting from the beginning of the membership year")
            ls.append(("membership", "fee", ConfigType.INT, section, label, help_text))

            label = _("Start day")
            help_text = _("Day of the year from which the membership year begins, in DD-MM format")
            ls.append(("membership", "day", ConfigType.CHAR, section, label, help_text))

            label = _("Months free quota")
            help_text = _(
                "Number of months, starting from the beginning of the membership year, for which "
                "to make free membership fee payment"
            )
            ls.append(("membership", "grazing", ConfigType.INT, section, label, help_text))

            label = _("Tax code check")
            help_text = _("Apply a check on the tax code of players")
            ls.append(("membership", "cf", ConfigType.BOOL, section, label, help_text))

        if "vote" in self.params["features"]:
            section = _("Voting")

            label = _("Active")
            help_text = _("If checked: members can vote.")
            ls.append(("vote", "open", ConfigType.BOOL, section, label, help_text))

            label = _("Candidates")
            help_text = _("Candidates at the polls")
            ls.append(("vote", "candidates", ConfigType.MEMBERS, section, label, help_text, self.instance.id))

            label = _("Minimum votes")
            help_text = _("Minimum number of votes")
            ls.append(("vote", "min", ConfigType.INT, section, label, help_text))

            label = _("Maximum votes")
            help_text = _("Maximum number of votes")
            ls.append(("vote", "max", ConfigType.INT, section, label, help_text))

        if "remind" in self.params["features"]:
            section = _("Reminder")

            label = _("Frequency")
            help_text = _("Sets how often reminder emails are sent, in days (default: 5)")
            ls.append(("remind", "days", ConfigType.INT, section, label, help_text))

            label = _("Text")
            help_text = _("Enter the text with which to remind the payment deadline.")
            ls.append(("remind", "text", ConfigType.HTML, section, label, help_text))

            label = _("Holidays")
            help_text = _("If checked: the system will send reminds the days on which holidays fall")
            ls.append(("remind", "holidays", ConfigType.BOOL, section, label, help_text))

    def get_config_accounting(self, ls):
        if "payment" in self.params["features"]:
            section = _("Payments")

            label = _("Disable amount change")
            help_text = _(
                "If checked: Hides the possibility for the player to change the payment amount for his entries"
            )
            ls.append(("payment", "hide_amount", ConfigType.BOOL, section, label, help_text))

            label = _("Unique code")
            help_text = _("If checked: Adds a unique code to each payment, which helps in being able to recognize it")
            ls.append(("payment", "special_code", ConfigType.BOOL, section, label, help_text))

        if "vat" in self.params["features"]:
            section = _("VAT")

            label = _("Ticket")
            help_text = _("Percentage of VAT to be calculated on the ticket cost alone")
            ls.append(("vat", "ticket", ConfigType.INT, section, label, help_text))

            label = _("Options")
            help_text = _("Percentage of VAT to be calculated on the sum of the costs of the registration options")
            ls.append(("vat", "options", ConfigType.INT, section, label, help_text))

        if "token_credit" in self.params["features"]:
            section = _("Tokens / Credits")
            label = _("Token name")
            help_text = _("Name to be displayed for tokens")
            ls.append(("token_credit", "token_name", ConfigType.CHAR, section, label, help_text))

            label = _("Name credits")
            help_text = _("Name to be displayed for credits")
            ls.append(("token_credit", "credit_name", ConfigType.CHAR, section, label, help_text))

        if "treasurer" in self.params["features"]:
            section = _("Treasury")
            label = _("Appointees")
            help_text = _("Treasury appointees")
            ls.append(("treasurer", "appointees", ConfigType.MEMBERS, section, label, help_text, self.instance.id))

        if "organization_tax" in self.params["features"]:
            section = _("Organisation fee")
            label = _("Percentage")
            help_text = _(
                "Percentage of takings calculated as a fee for association infrastructure (in "
                "whole numbers from 0 to 100)"
            )
            ls.append(("organization_tax", "perc", ConfigType.INT, section, label, help_text))

        if "payment_fees" in self.params["features"]:
            section = _("Payment fees")

            label = _("Charging the player")
            help_text = _("If checked: the system will add payment fees to the ticket, making the player pay for them.")
            ls.append(("payment_fees", "user", ConfigType.BOOL, section, label, help_text))

    def get_config_einvoice(self, ls):
        if "e-invoice" not in self.params["features"]:
            return

        section = _("Electronic invoice")

        label = _("Name")
        help_text = ""
        ls.append(("einvoice", "denominazione", ConfigType.CHAR, section, label, help_text))

        label = _("Fiscal code")
        help_text = ""
        ls.append(("einvoice", "idcodice", ConfigType.CHAR, section, label, help_text))

        label = _("VAT No.")
        help_text = ""
        ls.append(("einvoice", "partitaiva", ConfigType.CHAR, section, label, help_text))

        label = _("Tax regime")
        help_text = "RF19: forfettario, RF01: ordinario, RF05: agevolato, RF07: commerciale"
        ls.append(("einvoice", "regimefiscale", ConfigType.CHAR, section, label, help_text))

        label = _("VAT rate")
        help_text = _("If absent, indicate 0")
        ls.append(("einvoice", "aliquotaiva", ConfigType.CHAR, section, label, help_text))

        label = _("Nature")
        help_text = _("Indicate only if rate 0")
        ls.append(("einvoice", "natura", ConfigType.CHAR, section, label, help_text))

        label = _("Address")
        help_text = ""
        ls.append(("einvoice", "indirizzo", ConfigType.CHAR, section, label, help_text))

        label = _("House number")
        help_text = ""
        ls.append(("einvoice", "numerocivico", ConfigType.CHAR, section, label, help_text))

        label = _("Cap")
        help_text = ""
        ls.append(("einvoice", "cap", ConfigType.CHAR, section, label, help_text))

        label = _("Municipality")
        help_text = ""
        ls.append(("einvoice", "comune", ConfigType.CHAR, section, label, help_text))

        label = _("Province")
        help_text = _("Code two capital letters")
        ls.append(("einvoice", "provincia", ConfigType.CHAR, section, label, help_text))

        label = _("Nation")
        help_text = _("Code two capital letters")
        ls.append(("einvoice", "nazione", ConfigType.CHAR, section, label, help_text))

        label = _("Recipient Code")
        help_text = _("Intermediary channel code")
        ls.append(("einvoice", "codicedestinatario", ConfigType.CHAR, section, label, help_text))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # print(self.instance)

        self.prevent_canc = True

        self.prepare_configs()

        # print(self.initial)

    def save(self, commit=True):
        instance = super().save(commit=commit)

        self.save_configs(instance)

        return instance


class FirstAssociationForm(MyForm):
    class Meta:
        model = Association
        fields = ("name", "profile", "slug", "main_mail")  # 'main_language',

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
