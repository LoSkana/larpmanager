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

import logging
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.forms import Textarea
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext

from larpmanager.cache.feature import get_association_features, reset_association_features
from larpmanager.forms.base import MyCssForm, MyForm
from larpmanager.forms.config import ConfigForm, ConfigType
from larpmanager.forms.feature import FeatureForm, QuickSetupForm
from larpmanager.forms.utils import (
    AssociationMemberS2WidgetMulti,
    SlugInput,
    prepare_permissions_role,
    remove_choice,
    save_permissions_role,
)
from larpmanager.models.access import AssociationPermission, AssociationRole
from larpmanager.models.association import Association, AssociationText, AssociationTextType, AssociationTranslation
from larpmanager.models.member import Member

logger = logging.getLogger(__name__)


class ExeAssociationForm(MyForm):
    """Form for editing main association settings.

    Allows executives to modify core association properties
    while protecting critical fields like slug and features.
    """

    page_title = _("Settings")

    page_info = _("Manage main organization settings")

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
            "demo",
        )

    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        """Initialize the form instance with custom field modifications.

        Args:
            *args: Variable length argument list passed to parent class.
            **kwargs: Arbitrary keyword arguments passed to parent class.
        """
        # Initialize parent class with all provided arguments
        super().__init__(*args, **kwargs)

        # Set flag to prevent cancellation operations
        self.prevent_canc = True

        # Remove specified fields from the form's field collection
        for field_name in ["slug"]:
            del self.fields[field_name]


class ExeAssociationTextForm(MyForm):
    """Form for managing association text content.

    Handles custom text snippets used throughout the
    association's interface and communications.
    """

    page_title = _("Texts")

    page_info = _("Manage organization-specific texts")

    class Meta:
        abstract = True
        model = AssociationText
        exclude = ("number",)

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize AssociationTextForm with feature-based field configuration.

        Configures text type choices based on activated features, removing
        options for disabled features like membership, reminders, and legal notices.
        Adds detailed help text for each text type explaining its usage context.

        Args:
            *args: Positional arguments passed to parent form class
            **kwargs: Keyword arguments including 'params' dict with features list

        Side effects:
            - Modifies typ field choices based on enabled features
            - Adds comprehensive help text to typ field
        """
        super().__init__(*args, **kwargs)
        ch = AssociationTextType.choices
        delete_choice = [AssociationTextType.PRIVACY]

        if "legal_notice" not in self.params["features"]:
            delete_choice.append(AssociationTextType.LEGAL)

        if "receipts" not in self.params["features"]:
            delete_choice.append(AssociationTextType.RECEIPT)

        if "membership" not in self.params["features"]:
            delete_choice.extend([AssociationTextType.MEMBERSHIP, AssociationTextType.STATUTE])

        if "remind" not in self.params["features"]:
            delete_choice.extend(
                [
                    AssociationTextType.REMINDER_MEMBERSHIP,
                    AssociationTextType.REMINDER_MEMBERSHIP_FEE,
                    AssociationTextType.REMINDER_PAY,
                    AssociationTextType.REMINDER_PROFILE,
                ]
            )
        elif "membership" not in self.params["features"]:
            delete_choice.extend([AssociationTextType.REMINDER_MEMBERSHIP, AssociationTextType.REMINDER_MEMBERSHIP_FEE])
        else:
            delete_choice.extend([AssociationTextType.REMINDER_PROFILE])

        for tp in delete_choice:
            ch = remove_choice(ch, tp)

        self.fields["typ"].choices = ch

        help_texts = {
            AssociationTextType.PROFILE: _("Added at the top of the user profile page"),
            AssociationTextType.HOME: _("Added at the top of the main calendar page"),
            AssociationTextType.SIGNUP: _("Added at the bottom of all mails confirming signup to participants"),
            AssociationTextType.MEMBERSHIP: _("Content of the membership request filled with user data"),
            AssociationTextType.STATUTE: _("Added to the membership page as the paragraph for statute info"),
            AssociationTextType.LEGAL: _("Content of legal notice page linked at the bottom of all pages"),
            AssociationTextType.FOOTER: _("Added to the bottom of all pages"),
            AssociationTextType.TOC: _(
                "Terms and conditions of signup, shown in a page linked in the registration form"
            ),
            AssociationTextType.RECEIPT: _("Content of the receipt created for each payment and sent to participants"),
            AssociationTextType.SIGNATURE: _("Added to the bottom of all mails sent"),
            AssociationTextType.PRIVACY: _("Content of privacy page linked at the bottom of all pages"),
            AssociationTextType.REMINDER_MEMBERSHIP: _(
                "Content of mail reminding participants to fill their membership request"
            ),
            AssociationTextType.REMINDER_MEMBERSHIP_FEE: _(
                "Content of mail reminding participants to pay the membership fee"
            ),
            AssociationTextType.REMINDER_PAY: _("Content of mail reminding participants to pay their signup fee"),
            AssociationTextType.REMINDER_PROFILE: _("Content of mail reminding participants to fill their profile"),
        }
        help_text = []
        for choice_typ, text in help_texts.items():
            if choice_typ in delete_choice:
                continue
            help_text.append(f"<b>{choice_typ.label}</b>: {text}")
        self.fields["typ"].help_text = " - ".join(help_text)

    def clean(self) -> dict:
        """Validate association text form to prevent duplicates and enforce default rules.

        Validates that:
        - Only one default text exists per type within an association
        - Only one text exists per language-type combination within an association

        Returns:
            dict: The cleaned form data after validation

        Raises:
            ValidationError: If a duplicate default text or language-type combination
                           already exists for this association
        """
        cleaned_data = super().clean()

        # Extract form fields for validation
        default = cleaned_data.get("default")
        typ = cleaned_data.get("typ")
        language = cleaned_data.get("language")

        # Check for duplicate default text of the same type
        if default:
            res = AssociationText.objects.filter(association_id=self.params["association_id"], default=True, typ=typ)
            # Ensure we're not comparing against the current instance
            if res.count() > 0 and res.first().pk != self.instance.pk:
                self.add_error("default", "There is already a language set as default!")

        # Check for duplicate language-type combination
        res = AssociationText.objects.filter(association_id=self.params["association_id"], language=language, typ=typ)
        if res.count() > 0:
            first = res.first()
            # Ensure we're not comparing against the current instance
            if first.pk != self.instance.pk:
                self.add_error("language", "There is already a language of this type!")

        return cleaned_data


class ExeAssociationTranslationForm(MyForm):
    """Django form for creating and editing association-specific translation overrides.

    This form provides the interface for organization administrators to create custom
    translations that override the default Django i18n strings. It allows specifying:
    - The original text (msgid) to override
    - The custom translation (msgstr)
    - The target language
    - Optional context for disambiguation
    - Active/inactive status

    The form is used in the executive (exe) dashboard for managing organization-wide
    translation customizations. The number field is excluded as it's auto-managed.
    """

    page_title = _("Translations")

    page_info = _("Manage organization-specific translation overrides for customizing terminology and text")

    class Meta:
        abstract = True
        model = AssociationTranslation
        exclude = ("number",)


class ExeAssociationRoleForm(MyForm):
    """Form for managing association roles and permissions.

    Allows configuration of role-based access control
    including member assignment and permission management.
    """

    page_title = _("Roles")

    page_info = _("Manage association roles")

    load_templates = ["share"]

    class Meta:
        model = AssociationRole
        fields = ("name", "members", "association")
        widgets = {"members": AssociationMemberS2WidgetMulti}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure member widget with association context."""
        super().__init__(*args, **kwargs)
        # Configure member widget with association context
        self.fields["members"].widget.set_association_id(self.params["association_id"])
        # Prepare role-based permissions for association
        prepare_permissions_role(self, AssociationPermission)

    def save(self, commit: bool = True) -> Any:
        """Save form instance and update related role permissions."""
        instance = super().save(commit=commit)
        save_permissions_role(instance, self)
        return instance


class ExeAppearanceForm(MyCssForm):
    page_title = _("Appearance")

    page_info = _("Manage appearance settings and presentation of the organization")

    class Meta:
        model = Association
        fields = ("background", "font", "pri_rgb", "sec_rgb", "ter_rgb")

    association_css = forms.CharField(
        widget=Textarea(attrs={"rows": 15}),
        required=False,
        help_text=_(
            "Freely insert CSS commands, they will be reported in all pages  in the space of "
            "your Organization. In this way you can customize freely the appearance."
        ),
    )

    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        """Initialize form with cancel prevention and CSS link visibility."""
        super().__init__(*args, **kwargs)
        self.prevent_canc = True
        self.show_link = ["id_association_css"]

    @staticmethod
    def get_css_path(instance) -> str:
        """Return CSS file path for instance."""
        css_file_path = f"css/{instance.slug}_{instance.css_code}.css"
        return css_file_path

    @staticmethod
    def get_input_css():
        return "association_css"


class ExeFeatureForm(FeatureForm):
    page_title = _("Features")

    page_info = _(
        "Manage features activated for the organization and all its events (click on a feature to show its description)"
    )

    load_js = ["feature-search"]

    class Meta:
        model = Association
        fields = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the form and its features configuration."""
        super().__init__(*args, **kwargs)
        self._init_features(True)

    def save(self, commit: bool = True) -> Association:
        """Save form and reset association features cache."""
        # Save form without committing to database yet
        instance = super().save(commit=False)

        # Update related features and reset cache
        self._save_features(instance)
        reset_association_features(instance.id)

        return instance


class ExeConfigForm(ConfigForm):
    page_title = _("Configuration")

    page_info = _("Manage configuration of activated features")

    section_replace = True

    load_js = ["config-search"]

    istr = []

    class Meta:
        model = Association
        fields = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Initialize parent class and prevent cancellation
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

    def set_configs(self) -> None:
        """Set up interface configuration options for association settings.

        Manages UI preferences, theme settings, and display options for the
        association's interface customization. Configures calendar display options,
        email notification preferences, and delegates to other configuration methods.
        """
        # CALENDAR SECTION - Configure calendar display options
        self.set_section("calendar", _("Calendar"))

        # Configure visibility of past events link in calendar
        past_events_label = _("Past events")
        past_events_help_text = _("If checked: shows a link in the calendar to past events")
        self.add_configs("calendar_past_events", ConfigType.BOOL, past_events_label, past_events_help_text)

        # Configure website link display for each event
        website_label = _("Website")
        website_help_text = _("If checked: shows the website for each event")
        self.add_configs("calendar_website", ConfigType.BOOL, website_label, website_help_text)

        # Configure event location display toggle
        location_label = _("Where")
        location_help_text = _("If checked: shows the position for each event")
        self.add_configs("calendar_where", ConfigType.BOOL, location_label, location_help_text)

        # Configure authors list visibility for events
        authors_label = _("Authors")
        authors_help_text = _("If checked: shows the list of authors for each event")
        self.add_configs("calendar_authors", ConfigType.BOOL, authors_label, authors_help_text)

        # Configure event genre display setting
        genre_label = pgettext("event", "Genre")
        genre_help_text = pgettext("event", "If checked: shows the genre for each event")
        self.add_configs("calendar_genre", ConfigType.BOOL, genre_label, genre_help_text)

        # Configure event tagline visibility toggle
        tagline_label = _("Tagline")
        tagline_help_text = _("If checked: shows the tagline for each event")
        self.add_configs("calendar_tagline", ConfigType.BOOL, tagline_label, tagline_help_text)

        # EMAIL SECTION - Configure notification preferences
        self.set_section("email", _("Email notifications"))

        # Configure carbon copy setting (only if main_mail exists)
        if self.instance.main_mail:
            carbon_copy_label = _("Carbon copy")
            carbon_copy_help_text = _("If checked: Sends the main mail a copy of all mails sent to participants")
            self.add_configs("mail_cc", ConfigType.BOOL, carbon_copy_label, carbon_copy_help_text)

        # Configure new signup notification toggle
        new_signup_label = _("New signup")
        new_signup_help_text = _("If checked: Send an email notification to the organisers for new signups")
        self.add_configs("mail_signup_new", ConfigType.BOOL, new_signup_label, new_signup_help_text)

        # Configure signup update notification setting
        signup_update_label = _("Signup update")
        signup_update_help_text = _("If checked: Send an email notification to the organisers for updated signups")
        self.add_configs("mail_signup_update", ConfigType.BOOL, signup_update_label, signup_update_help_text)

        # Configure signup cancellation notification option
        signup_cancellation_label = _("Signup cancellation")
        signup_cancellation_help_text = _(
            "If checked: Send a notification email to the organisers for cancellation of registration"
        )
        self.add_configs("mail_signup_del", ConfigType.BOOL, signup_cancellation_label, signup_cancellation_help_text)

        # Configure payment notification toggle
        payment_received_label = _("Payments received")
        payment_received_help_text = _("If checked: Send an email to the organisers for each payment received")
        self.add_configs("mail_payment", ConfigType.BOOL, payment_received_label, payment_received_help_text)

        # Delegate to specialized configuration methods for other settings
        self.set_config_members()
        self.set_config_accounting()
        self.set_config_einvoice()
        self.set_config_others()

    def set_config_others(self) -> None:
        """Configure miscellaneous association settings.

        Sets up configuration sections for various optional features including:
        - Custom mail server settings (SMTP configuration)
        - Pre-registration preferences
        - Easter egg features (centauri)
        - Campaign-specific settings
        - Warehouse management options

        The method checks for available features in self.params["features"] and
        creates appropriate configuration sections and fields for each enabled feature.
        """
        # Configure custom mail server settings if feature is enabled
        if "custom_mail" in self.params["features"]:
            self.set_section("custom_mail_server", _("Customised mail server"))
            empty_help_text = ""

            # SMTP connection settings
            use_tls_label = _("Use TLD")
            self.add_configs("mail_server_use_tls", ConfigType.BOOL, use_tls_label, empty_help_text)

            host_address_label = _("Host Address")
            self.add_configs("mail_server_host", ConfigType.CHAR, host_address_label, empty_help_text)

            port_label = _("Port")
            self.add_configs("mail_server_port", ConfigType.INT, port_label, empty_help_text)

            # Authentication credentials
            username_label = _("Username of account")
            self.add_configs("mail_server_host_user", ConfigType.CHAR, username_label, empty_help_text)

            password_label = _("Password of account")
            self.add_configs("mail_server_host_password", ConfigType.CHAR, password_label, empty_help_text)

        # Configure pre-registration preferences
        if "pre_register" in self.params["features"]:
            self.set_section("pre_reg", _("Pre-registration"))
            preferences_label = _("Enable preferences")
            preferences_help_text = _("If checked, participants give a preference value when adding pre-registrations")
            self.add_configs("pre_reg_preferences", ConfigType.BOOL, preferences_label, preferences_help_text)

        # Configure easter egg feature (centauri)
        if "centauri" in self.params["features"]:
            self.set_section("centauri", _("Easter egg"))

            # Probability and badge settings
            probability_label = _("Probability")
            probability_help_text = _("Probability of showing the special page (out of thousands)")
            self.add_configs("centauri_prob", ConfigType.INT, probability_label, probability_help_text)

            badge_label = _("Badge")
            badge_help_text = _("Name of badge to be awarded")
            self.add_configs("centauri_badge", ConfigType.CHAR, badge_label, badge_help_text)

            # Content configuration
            description_label = _("Description")
            description_help_text = _("Description to be shown on the special page")
            self.add_configs("centauri_descr", ConfigType.CHAR, description_label, description_help_text)

            page_label = _("Page")
            page_help_text = _("Contents of the special page")
            self.add_configs("centauri_content", ConfigType.HTML, page_label, page_help_text)

        # Configure campaign-specific settings
        if "campaign" in self.params["features"]:
            self.set_section("campaign", _("Campaign"))

            move_registration_label = _("Move registration event")
            move_registration_help_text = _("Allow to switch registration between events")
            self.add_configs("campaign_switch", ConfigType.BOOL, move_registration_label, move_registration_help_text)

        # Configure warehouse management options
        if "warehouse" in self.params["features"]:
            self.set_section("warehouse", _("Warehouse"))

            quantity_label = _("Quantity")
            quantity_help_text = _("If checked: Add a field to track items quantity")
            self.add_configs("warehouse_quantity", ConfigType.BOOL, quantity_label, quantity_help_text)

    def set_config_members(self) -> None:
        """Configure member-related form fields and sections in association settings.

        Sets up various user management options like event history visibility,
        membership fees, deadlines, voting, and reminder features for the association
        configuration form based on enabled features.

        Side effects:
            Modifies form fields in-place by adding configuration sections and fields
            for users, deadlines, membership, voting, and reminders
        """
        # Configure user profile and history display settings
        self.set_section("users", _("Users"))

        field_label = _("Event history")
        field_help_text = _("If checked: in the public page of an user shows a list of all events attended")
        self.add_configs("player_larp_history", ConfigType.BOOL, field_label, field_help_text)

        # Configure deadline management if feature is enabled
        if "deadlines" in self.params["features"]:
            self.set_section("deadlines", _("Deadline"))

            # Tolerance period before automatic cancellation
            field_label = _("Tolerance")
            field_help_text = _(
                "Number of days past the deadline beyond which registrations are marked to be cancelled (default 30 days)"
            )
            self.add_configs("deadline_tolerance", ConfigType.INT, field_label, field_help_text)

            # Reminder email frequency
            field_label = _("Frequency")
            field_help_text = _("Sets how often reminder emails are sent, in days (if not set, no emails are sent)")
            self.add_configs("deadline_days", ConfigType.INT, field_label, field_help_text)

        # Configure membership fee and requirements if feature is enabled
        if "membership" in self.params["features"]:
            self.set_section("membership", _("Members"))

            # Minimum age requirement for membership
            field_label = _("Age")
            field_help_text = _("Minimum age of members (leave empty for no limit)")
            self.add_configs("membership_age", ConfigType.INT, field_label, field_help_text)

            # Annual membership fee amount
            field_label = _("Annual fee")
            field_help_text = _("Annual fee required of members, starting from the beginning of the membership year")
            self.add_configs("membership_fee", ConfigType.INT, field_label, field_help_text)

            # Membership year start date configuration
            field_label = _("Start day")
            field_help_text = _("Day of the year from which the membership year begins, in DD-MM format")
            self.add_configs("membership_day", ConfigType.CHAR, field_label, field_help_text)

            # Grace period for membership fee payment
            field_label = _("Months free quota")
            field_help_text = _(
                "Number of months, starting from the beginning of the membership year, for which "
                "to make free membership fee payment"
            )
            self.add_configs("membership_grazing", ConfigType.INT, field_label, field_help_text)

        # Configure voting system if feature is enabled
        if "vote" in self.params["features"]:
            self.set_section("vote", _("Voting"))

            # Toggle voting availability
            field_label = _("Active")
            field_help_text = _("If checked: members can vote")
            self.add_configs("vote_open", ConfigType.BOOL, field_label, field_help_text)

            # List of candidates for election
            field_label = _("Candidates")
            field_help_text = _("Candidates at the polls")
            self.add_configs("vote_candidates", ConfigType.MEMBERS, field_label, field_help_text, self.instance.id)

            # Voting constraints: minimum and maximum votes per member
            field_label = _("Minimum votes")
            field_help_text = _("Minimum number of votes")
            self.add_configs("vote_min", ConfigType.INT, field_label, field_help_text)

            field_label = _("Maximum votes")
            field_help_text = _("Maximum number of votes")
            self.add_configs("vote_max", ConfigType.INT, field_label, field_help_text)

        # Configure reminder email system if feature is enabled
        if "remind" in self.params["features"]:
            self.set_section("remind", _("Reminder"))

            # Frequency of automated reminder emails
            field_label = _("Frequency")
            field_help_text = _("Sets how often reminder emails are sent, in days (default: 5)")
            self.add_configs("remind_days", ConfigType.INT, field_label, field_help_text)

            # Holiday scheduling for reminder emails
            field_label = _("Holidays")
            field_help_text = _("If checked: the system will send reminds the days on which holidays fall")
            self.add_configs("remind_holidays", ConfigType.BOOL, field_label, field_help_text)

    def set_config_accounting(self) -> None:
        """Configure accounting-related form fields for association settings.

        Sets up payment options, transaction fee settings, and financial
        feature configurations for the association based on enabled features.

        This method conditionally adds form sections and configuration fields
        for various accounting features including payments, VAT, tokens/credits,
        treasury management, organization fees, and expenses.
        """
        # Configure payment gateway settings and fee options
        if "payment" in self.params["features"]:
            self.set_section("payment", _("Payments"))

            # Payment fee configuration - who pays gateway fees
            label_charge_fees_to_participant = _("Charge transaction fees to participant")
            help_text_charge_fees_to_participant = _(
                "If enabled, the system will automatically add payment gateway fees to the ticket price, so the participant covers them instead of the organization"
            )
            self.add_configs(
                "payment_fees_user",
                ConfigType.BOOL,
                label_charge_fees_to_participant,
                help_text_charge_fees_to_participant,
            )

            # Payment amount modification controls
            label_disable_amount_change = _("Disable amount change")
            help_text_disable_amount_change = _(
                "If checked: Hides the possibility for the participant to change the payment amount for his entries"
            )
            self.add_configs(
                "payment_hide_amount", ConfigType.BOOL, label_disable_amount_change, help_text_disable_amount_change
            )

            # Unique payment identification system
            label_unique_payment_code = _("Unique code")
            help_text_unique_payment_code = _(
                "If checked: Adds a unique code to each payment, which helps in being able to recognize it"
            )
            self.add_configs(
                "payment_special_code", ConfigType.BOOL, label_unique_payment_code, help_text_unique_payment_code
            )

            # Manual payment receipt requirement
            label_require_payment_receipt = _("Require receipt for manual payments")
            help_text_require_payment_receipt = _(
                "If checked: Participants must provide a receipt/invoice for manual payments"
            )
            self.add_configs(
                "payment_require_receipt",
                ConfigType.BOOL,
                label_require_payment_receipt,
                help_text_require_payment_receipt,
            )

        # Configure VAT calculation settings for different cost components
        if "vat" in self.params["features"]:
            self.set_section("vat", _("VAT"))

            # VAT percentage for base ticket cost
            label_vat_on_ticket = _("Ticket")
            help_text_vat_on_ticket = _("Percentage of VAT to be calculated on the ticket cost alone")
            self.add_configs("vat_ticket", ConfigType.INT, label_vat_on_ticket, help_text_vat_on_ticket)

            # VAT percentage for additional registration options
            label_vat_on_options = _("Options")
            help_text_vat_on_options = _(
                "Percentage of VAT to be calculated on the sum of the costs of the registration options"
            )
            self.add_configs("vat_options", ConfigType.INT, label_vat_on_options, help_text_vat_on_options)

        # Configure token/credit system naming and display
        if "token_credit" in self.params["features"]:
            self.set_section("token_credit", _("Tokens / Credits"))

            # Customizable token display name
            label_token_display_name = _("Token name")
            help_text_token_display_name = _("Name to be displayed for tokens")
            self.add_configs(
                "token_credit_token_name", ConfigType.CHAR, label_token_display_name, help_text_token_display_name
            )

            # Customizable credit display name
            label_credit_display_name = _("Name credits")
            help_text_credit_display_name = _("Name to be displayed for credits")
            self.add_configs(
                "token_credit_credit_name", ConfigType.CHAR, label_credit_display_name, help_text_credit_display_name
            )

        # Configure treasury management and appointee selection
        if "treasurer" in self.params["features"]:
            self.set_section("treasurer", _("Treasury"))
            label_treasury_appointees = _("Appointees")
            help_text_treasury_appointees = _("Treasury appointees")
            self.add_configs(
                "treasurer_appointees",
                ConfigType.MEMBERS,
                label_treasury_appointees,
                help_text_treasury_appointees,
                self.instance.id,
            )

        # Configure organization infrastructure fee calculation
        if "organization_tax" in self.params["features"]:
            self.set_section("organization_tax", _("Organisation fee"))
            label_organization_fee_percentage = _("Percentage")
            help_text_organization_fee_percentage = _(
                "Percentage of takings calculated as a fee for association infrastructure (in "
                "whole numbers from 0 to 100)"
            )
            self.add_configs(
                "organization_tax_perc",
                ConfigType.INT,
                label_organization_fee_percentage,
                help_text_organization_fee_percentage,
            )

        # Configure expense approval workflow settings
        if "expense" in self.params["features"]:
            self.set_section("expense", _("Expenses"))
            label_disable_event_approval = _("Disable event approval")
            help_text_disable_event_approval = _(
                "If checked, approval of expenses can be performed only from the organization panel"
            )
            self.add_configs(
                "expense_disable_orga", ConfigType.BOOL, label_disable_event_approval, help_text_disable_event_approval
            )

    def set_config_einvoice(self) -> None:
        """Configure electronic invoice settings for associations.

        Sets up Italian e-invoice system parameters and business information
        for electronic billing compliance. Only processes if 'e-invoice'
        feature is enabled in params.

        Returns:
            None
        """
        if "e-invoice" not in self.params["features"]:
            return

        self.set_section("einvoice", _("Electronic invoice"))

        # Basic company information fields
        field_label = _("Name")
        field_help_text = ""
        self.add_configs("einvoice_denominazione", ConfigType.CHAR, field_label, field_help_text)

        field_label = _("Fiscal code")
        field_help_text = ""
        self.add_configs("einvoice_idcodice", ConfigType.CHAR, field_label, field_help_text)

        field_label = _("VAT No")
        field_help_text = ""
        self.add_configs("einvoice_partitaiva", ConfigType.CHAR, field_label, field_help_text)

        # Tax regime and VAT configuration
        field_label = _("Tax regime")
        field_help_text = "RF19: forfettario, RF01: ordinario, RF05: agevolato, RF07: commerciale"
        self.add_configs("einvoice_regimefiscale", ConfigType.CHAR, field_label, field_help_text)

        field_label = _("VAT rate")
        field_help_text = _("If absent, indicate 0")
        self.add_configs("einvoice_aliquotaiva", ConfigType.CHAR, field_label, field_help_text)

        field_label = _("Nature")
        field_help_text = _("Indicate only if rate 0")
        self.add_configs("einvoice_natura", ConfigType.CHAR, field_label, field_help_text)

        # Company address information
        field_label = _("Address")
        field_help_text = ""
        self.add_configs("einvoice_indirizzo", ConfigType.CHAR, field_label, field_help_text)

        field_label = _("House number")
        field_help_text = ""
        self.add_configs("einvoice_numerocivico", ConfigType.CHAR, field_label, field_help_text)

        field_label = _("Cap")
        field_help_text = ""
        self.add_configs("einvoice_cap", ConfigType.CHAR, field_label, field_help_text)

        # Geographic location fields
        field_label = _("Municipality")
        field_help_text = ""
        self.add_configs("einvoice_comune", ConfigType.CHAR, field_label, field_help_text)

        field_label = _("Province")
        field_help_text = _("Code two capital letters")
        self.add_configs("einvoice_provincia", ConfigType.CHAR, field_label, field_help_text)

        field_label = _("Nation")
        field_help_text = _("Code two capital letters")
        self.add_configs("einvoice_nazione", ConfigType.CHAR, field_label, field_help_text)

        # Electronic invoice routing configuration
        field_label = _("Recipient Code")
        field_help_text = _("Intermediary channel code")
        self.add_configs("einvoice_codicedestinatario", ConfigType.CHAR, field_label, field_help_text)


class FirstAssociationForm(MyForm):
    """Form for creating a new association during initial setup.

    Simplified form for first-time association creation
    with essential fields only.
    """

    class Meta:
        model = Association
        fields = ("name", "profile", "slug")
        widgets = {
            "slug": SlugInput,
        }

    def clean_slug(self) -> str:
        """Validate that the slug is unique across all associations.

        Returns:
            str: The validated slug value.

        Raises:
            ValidationError: If the slug is already in use by another association.
        """
        data: str = self.cleaned_data["slug"]
        logger.debug(f"Validating association slug: {data}")

        # Check if slug is already used by other associations
        lst = Association.objects.filter(slug=data)

        # Exclude current instance from validation if editing existing association
        if self.instance is not None and self.instance.pk is not None:
            lst = lst.exclude(pk=self.instance.pk)

        # Raise validation error if slug already exists
        if lst.count() > 0:
            raise ValidationError("Slug already used!")

        return data


class ExeQuickSetupForm(QuickSetupForm):
    page_title = _("Quick Setup")

    page_info = _("Manage quick setup of the most important settings for your new organization")

    class Meta:
        model = Association
        fields = []

    def __init__(self, *args, **kwargs):
        """Initialize association setup form with feature configuration options.

        Sets up available features and configuration options based on
        association settings and skin preferences.

        Args:
            *args: Variable positional arguments
            **kwargs: Variable keyword arguments
        """
        super().__init__(*args, **kwargs)
        self.setup = {}

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

        self.setup.update(
            {
                "publisher": (
                    True,
                    _("Publisher"),
                    _("Do you want to make your upcoming events visible to external sites through a public API"),
                ),
                "payment": (True, _("Payments"), _("Do you want to accept payments processed through the system")),
                "payment_fees_user": (
                    False,
                    _("Transaction fees"),
                    _(
                        "Do you want to add payment gateway fees to the ticket price, so that the user pays them instead of the organization"
                    ),
                ),
                "membership": (
                    True,
                    _("Membership"),
                    _("Do you want users to join events only after an approval process"),
                ),
                "deadlines": (
                    True,
                    _("Deadlines"),
                    _("Do you want a dashboard to track and manage deadlines missed by registered users"),
                ),
                "remind": (
                    True,
                    _("Reminders"),
                    _(
                        "Do you want to enable an automatic email reminder system for registered users who miss a deadline"
                    ),
                ),
                "help": (True, _("Help"), _("Do you want to manage user help requests directly through the platform")),
                "donate": (True, _("Donations"), _("Do you want to allow users to make voluntary donations")),
            }
        )

        self.init_fields(get_association_features(self.instance.pk))


class ExePreferencesForm(ConfigForm):
    page_title = _("Personal preferences")

    page_info = _("Manage your personal interface preferences")

    class Meta:
        model = Member
        fields = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with default settings."""
        super().__init__(*args, **kwargs)

        # Configure form behavior flags
        self.prevent_canc = True
        self.show_sections = True

    def set_configs(self) -> None:
        """Add interface configuration options to the form."""
        # Define interface configuration section
        self.set_section("interface", _("Interface"))

        # Add sidebar collapse toggle option
        sidebar_collapse_label = _("Collapse sidebar")
        sidebar_collapse_help_text = _("If checked: collpase sidebars links, and expand on mouse hover")
        self.add_configs(
            "interface_collapse_sidebar", ConfigType.BOOL, sidebar_collapse_label, sidebar_collapse_help_text
        )
