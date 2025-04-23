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
from django.utils.translation import gettext_lazy as _, pgettext

from larpmanager.forms.base import MyForm, MyCssForm
from larpmanager.forms.utils import (
    remove_choice,
    AssocMemberS2WidgetMulti,
    prepare_permissions_role,
    save_permissions_role,
    SlugInput,
)
from larpmanager.models.access import AssocRole, AssocPermission
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
        help = _("If checked: shows a link to the event in the navigation bar.")
        ls.append(("calendar", "show_event", 2, section, label, help))

        label = _("Past events")
        help = _("If checked: shows a link in the calendar to past events.")
        ls.append(("calendar", "past_events", 2, section, label, help))

        label = _("Website")
        help = _("If checked: shows the website for each event")
        ls.append(("calendar", "website", 2, section, label, help))

        label = _("Description")
        help = _("If checked: shows the description for each event")
        ls.append(("calendar", "description", 2, section, label, help))

        label = _("Where")
        help = _("If checked: shows the position for each event")
        ls.append(("calendar", "where", 2, section, label, help))

        label = _("Authors")
        help = _("If checked: shows the list of authors for each event")
        ls.append(("calendar", "authors", 2, section, label, help))

        label = pgettext("event", "Genre")
        help = pgettext("event", "If checked: shows the genre for each event")
        ls.append(("calendar", "genre", 2, section, label, help))

        label = _("Tagline")
        help = _("If checked: shows the tagline for each event")
        ls.append(("calendar", "tagline", 2, section, label, help))

        # ## INTERFACE

        section = _("Interface")
        label = _("Quick links organisation")
        help = _("If checked: In the event management panel, it also shows the association management links")
        ls.append(("interface", "admin_links", 2, section, label, help))

        # ## MAIL
        section = _("Email notifications")

        label = _("Carbon copy")
        help = _("If checked: Sends the main mail a copy of all mails sent to players")
        ls.append(("mail", "cc", 2, section, label, help))

        label = _("New signup")
        help = _("If checked: Send an email notification to the organisers for new signups")
        ls.append(("mail", "signup_new", 2, section, label, help))

        label = _("Signup update")
        help = _("If checked: Send an email notification to the organisers for updated signups")
        ls.append(("mail", "signup_update", 2, section, label, help))

        label = _("Signup cancellation")
        help = _("If checked: Send a notification email to the organisers for cancellation of registration")
        ls.append(("mail", "signup_del", 2, section, label, help))

        label = _("Payments received")
        help = _("If checked: Send an email to the organisers for each payment received")
        ls.append(("mail", "payment", 2, section, label, help))

        if "payment" in self.params["features"]:
            section = _("Payments")

            label = _("Disable amount change")
            help = _("If checked: Hides the possibility for the player to change the payment amount for his entries")
            ls.append(("payment", "hide_amount", 2, section, label, help))

            label = _("Unique code")
            help = _("If checked: Adds a unique code to each payment, which helps in being able to recognize it")
            ls.append(("payment", "special_code", 2, section, label, help))

        if "deadlines" in self.params["features"]:
            section = _("Deadline")

            label = _("Tolerance")
            help = _(
                "Number of days past the deadline beyond which registrations are marked to be cancelled (default 30 days)"
            )
            ls.append(("deadline", "tolerance", 4, section, label, help))

            label = _("Frequency")
            help = _("Sets how often reminder emails are sent, in days (default: 5)")
            ls.append(("deadline", "days", 4, section, label, help))

        if "vat" in self.params["features"]:
            section = _("VAT")

            label = _("Ticket")
            help = _("Percentage of VAT to be calculated on the ticket cost alone")
            ls.append(("vat", "ticket", 4, section, label, help))

            label = _("Options")
            help = _("Percentage of VAT to be calculated on the sum of the costs of the registration options")
            ls.append(("vat", "options", 4, section, label, help))

        if "token_credit" in self.params["features"]:
            section = _("Tokens / Credits")
            label = _("Token name")
            help = _("Name to be displayed for tokens")
            ls.append(("token_credit", "token_name", 1, section, label, help))

            label = _("Name credits")
            help = _("Name to be displayed for credits")
            ls.append(("token_credit", "credit_name", 1, section, label, help))

        if "membership" in self.params["features"]:
            section = _("Members")

            label = _("Age")
            help = _("Minimum age of members")
            ls.append(("membership", "age", 4, section, label, help))

            label = _("Annual fee")
            help = _("Annual fee required of members, starting from the beginning of the membership year")
            ls.append(("membership", "fee", 4, section, label, help))

            label = _("Start day")
            help = _("Day of the year from which the membership year begins, in DD-MM format")
            ls.append(("membership", "day", 1, section, label, help))

            label = _("Months free quota")
            help = _(
                "Number of months, starting from the beginning of the membership year, for which "
                "to make free membership fee payment"
            )
            ls.append(("membership", "grazing", 4, section, label, help))

            label = _("Tax code check")
            help = _("Apply a check on the tax code of players")
            ls.append(("membership", "cf", 2, section, label, help))

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

        if "vote" in self.params["features"]:
            section = _("Voting")

            label = _("Active")
            help = _("If checked: members can vote.")
            ls.append(("vote", "open", 2, section, label, help))

            label = _("Candidates")
            help = _("Candidates at the polls")
            ls.append(("vote", "candidates", 6, section, label, help, self.instance.id))

            label = _("Minimum votes")
            help = _("Minimum number of votes")
            ls.append(("vote", "min", 4, section, label, help))

            label = _("Maximum votes")
            help = _("Maximum number of votes")
            ls.append(("vote", "max", 4, section, label, help))

        if "treasurer" in self.params["features"]:
            section = _("Treasury")
            label = _("Appointees")
            help = _("Treasury appointees")
            ls.append(("treasurer", "appointees", 6, section, label, help, self.instance.id))

        if "remind" in self.params["features"]:
            section = _("Reminder")

            label = _("Frequency")
            help = _("Sets how often reminder emails are sent, in days (default: 5)")
            ls.append(("remind", "days", 4, section, label, help))

            label = _("Text")
            help = _("Enter the text with which to remind the payment deadline.")
            ls.append(("remind", "text", 3, section, label, help))

            label = _("Holidays")
            help = _("If checked: the system will send reminds the days on which holidays fall")
            ls.append(("remind", "holidays", 2, section, label, help))

        if "organization_tax" in self.params["features"]:
            section = _("Organisation fee")
            label = _("Percentage")
            help = _(
                "Percentage of takings calculated as a fee for association infrastructure (in "
                "whole numbers from 0 to 100)"
            )
            ls.append(("organization_tax", "perc", 4, section, label, help))

        if "centauri" in self.params["features"]:
            section = _("Centarui")

            label = _("Probability")
            help = _("Probability of showing the special page (out of thousands)")
            ls.append(("centauri", "prob", 4, section, label, help))

            label = _("Badge")
            help = _("Name of badge to be awarded")
            ls.append(("centauri", "badge", 1, section, label, help))

            label = _("Description")
            help = _("Description to be shown on the special page")
            ls.append(("centauri", "descr", 1, section, label, help))

            label = _("Page")
            help = _("Contents of the special page")
            ls.append(("centauri", "content", 3, section, label, help))

        if "payment_fees" in self.params["features"]:
            section = _("Payment fees")

            label = _("Charging the player")
            help = _("If checked: the system will add payment fees to the ticket, making the player pay for them.")
            ls.append(("payment_fees", "user", 2, section, label, help))

        if "e-invoice" in self.params["features"]:
            section = _("Electronic invoice")

            label = _("Name")
            help = ""
            ls.append(("einvoice", "denominazione", 1, section, label, help))

            label = _("Fiscal code")
            help = ""
            ls.append(("einvoice", "idcodice", 1, section, label, help))

            label = _("VAT No.")
            help = ""
            ls.append(("einvoice", "partitaiva", 1, section, label, help))

            label = _("Tax regime")
            help = "RF19: forfettario, RF01: ordinario, RF05: agevolato, RF07: commerciale"
            ls.append(("einvoice", "regimefiscale", 1, section, label, help))

            label = _("VAT rate")
            help = _("If absent, indicate 0")
            ls.append(("einvoice", "aliquotaiva", 1, section, label, help))

            label = _("Nature")
            help = _("Indicate only if rate 0")
            ls.append(("einvoice", "natura", 1, section, label, help))

            label = _("Address")
            help = ""
            ls.append(("einvoice", "indirizzo", 1, section, label, help))

            label = _("House number")
            help = ""
            ls.append(("einvoice", "numerocivico", 1, section, label, help))

            label = _("Cap")
            help = ""
            ls.append(("einvoice", "cap", 1, section, label, help))

            label = _("Municipality")
            help = ""
            ls.append(("einvoice", "comune", 1, section, label, help))

            label = _("Province")
            help = _("Code two capital letters")
            ls.append(("einvoice", "provincia", 1, section, label, help))

            label = _("Nation")
            help = _("Code two capital letters")
            ls.append(("einvoice", "nazione", 1, section, label, help))

            label = _("Recipient Code")
            help = _("Intermediary channel code")
            ls.append(("einvoice", "codicedestinatario", 1, section, label, help))

        return ls

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
