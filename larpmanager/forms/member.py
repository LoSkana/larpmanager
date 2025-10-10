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
import os
import re
from collections import OrderedDict
from datetime import datetime

import pycountry
from dateutil.relativedelta import relativedelta
from django import forms
from django.conf import settings as conf_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Max
from django.forms import Textarea
from django.template import loader
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV3
from django_registration.forms import RegistrationFormUniqueEmail

from larpmanager.cache.config import get_assoc_config
from larpmanager.cache.feature import get_assoc_features
from larpmanager.forms.base import BaseAccForm, MyForm
from larpmanager.forms.utils import AssocMemberS2Widget, AssocMemberS2WidgetMulti, DatePickerInput, get_members_queryset
from larpmanager.models.accounting import AccountingItemMembership
from larpmanager.models.association import Association, MemberFieldType
from larpmanager.models.base import FeatureNationality
from larpmanager.models.member import (
    Badge,
    Member,
    Membership,
    MembershipStatus,
    NewsletterChoices,
    VolunteerRegistry,
    get_user_membership,
)
from larpmanager.utils.common import get_recaptcha_secrets
from larpmanager.utils.tasks import my_send_mail
from larpmanager.utils.validators import FileTypeValidator

logger = logging.getLogger(__name__)


class MyAuthForm(AuthenticationForm):
    """Custom authentication form with styled fields."""

    class Meta:
        model = User
        fields = ["username", "password"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget = forms.TextInput(
            attrs={"class": "form-control", "placeholder": "email", "maxlength": 70},
        )
        self.fields["username"].label = False
        self.fields["password"].widget = forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "password", "maxlength": 70},
        )
        self.fields["password"].label = False


class MyRegistrationFormUniqueEmail(RegistrationFormUniqueEmail):
    """Custom registration form with unique email validation and GDPR compliance."""

    # noinspection PyUnresolvedReferences, PyProtectedMember
    def __init__(self, *args, **kwargs):
        """Initialize RegistrationFormUniqueEmail with custom field configuration.

        Args:
            *args: Variable length argument list passed to parent
            **kwargs: Arbitrary keyword arguments, including 'request'
        """
        self.request = kwargs.pop("request", None)
        super(RegistrationFormUniqueEmail, self).__init__(*args, **kwargs)
        self.fields["username"].widget = forms.HiddenInput()

        self.fields["lang"] = forms.ChoiceField(
            required=True,
            choices=conf_settings.LANGUAGES,
            label=Member._meta.get_field("language").verbose_name,
            help_text=Member._meta.get_field("language").help_text,
            initial=translation.get_language(),
        )

        self.fields["email"].widget.attrs["maxlength"] = 70

        self.fields["password1"].widget.attrs["maxlength"] = 70

        self.fields["name"] = forms.CharField(
            required=True,
            label=Member._meta.get_field("name").verbose_name,
            help_text=Member._meta.get_field("name").help_text,
        )

        self.fields["surname"] = forms.CharField(
            required=True,
            label=Member._meta.get_field("surname").verbose_name,
            help_text=Member._meta.get_field("surname").help_text,
        )

        self.fields["newsletter"] = forms.ChoiceField(
            required=True,
            choices=NewsletterChoices.choices,
            label=Member._meta.get_field("newsletter").verbose_name,
            help_text=Member._meta.get_field("newsletter").help_text,
            initial=NewsletterChoices.ALL,
        )

        self.fields["share"] = forms.BooleanField(
            required=True,
            label=_("Authorisation"),
            help_text=_(
                "Do you consent to the sharing of your personal data in accordance with the GDPR and our Privacy Policy"
            )
            + "?",
        )

        if not conf_settings.DEBUG and not os.getenv("PYTEST_CURRENT_TEST"):
            public, private = get_recaptcha_secrets(self.request)
            if public and private:
                self.fields["captcha"] = ReCaptchaField(
                    widget=ReCaptchaV3, label="Captcha", public_key=public, private_key=private
                )

        # place language as first
        new_order = ["lang"] + [key for key in self.fields if key != "lang"]
        self.fields = OrderedDict((key, self.fields[key]) for key in new_order)

    def clean_username(self):
        data = self.cleaned_data["username"].strip()
        logger.debug(f"Validating username/email: {data}")
        # check if already used in user or email
        if User.objects.filter(email__iexact=data).exists():
            raise ValidationError("Email already used! It seems you already have an account!")
        return data

    def save(self, commit=True):
        """Save user and associated member profile.

        Args:
            commit: Whether to save to database

        Returns:
            User: Created user instance
        """
        user = super(RegistrationFormUniqueEmail, self).save()

        user.member.newsletter = self.cleaned_data["newsletter"]
        user.member.language = self.cleaned_data["lang"]
        user.member.name = self.cleaned_data["name"]
        user.member.surname = self.cleaned_data["surname"]
        user.member.save()

        return user


class MyPasswordResetConfirmForm(SetPasswordForm):
    """Custom password reset confirmation form with field limits."""

    def __init__(self, *args, **kwargs):
        """Initialize form with password field constraints.

        Args:
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments
        """
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs["maxlength"] = 70


class MyPasswordResetForm(PasswordResetForm):
    """Custom password reset form with association-specific handling."""

    def __init__(self, *args, **kwargs):
        """Initialize form with email field constraints.

        Args:
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments
        """
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs["maxlength"] = 70

    def get_users(self, email):
        # noinspection PyProtectedMember
        active_users = get_user_model()._default_manager.filter(email__iexact=email, is_active=True)
        return (u for u in active_users)

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        """
        Sends a django.core.mail.EmailMultiAlternatives to `to_email`.
        """
        subject = loader.render_to_string(subject_template_name, context)
        # Email subject *must not* contain newlines
        subject = "".join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)

        assoc_slug = context["domain"].replace("larpmanager.com", "").strip(".").strip()
        assoc = None
        if assoc_slug:
            try:
                assoc = Association.objects.get(slug=assoc_slug)
                user = context["user"]
                mb = get_user_membership(user.member, assoc.id)
                mb.password_reset = f"{context['uid']}#{context['token']}"
                mb.save()
            except ObjectDoesNotExist:
                # Invalid association slug - continue with None assoc
                pass

        logger.debug(f"Password reset context: domain={context.get('domain')}, uid={context.get('uid')}")

        my_send_mail(subject, body, to_email, assoc)

    # ~ email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
    # ~ if html_email_template_name is not None:
    # ~ html_email = loader.render_to_string(html_email_template_name, context)
    # ~ email_message.attach_alternative(html_email, 'text/html')

    # ~ email_message.send()


class AvatarForm(forms.Form):
    """Form for uploading user avatar images."""

    image = forms.ImageField(label="Select an image")


class LanguageForm(forms.Form):
    """Form for selecting user interface language."""

    language = forms.ChoiceField(
        choices=conf_settings.LANGUAGES,
        label=_("Select Language"),
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        current_lang = kwargs.pop("current_language")
        super().__init__(*args, **kwargs)
        self.fields["language"].initial = current_lang


# noinspection PyUnresolvedReferences
COUNTRY_CHOICES = sorted([(country.alpha_2, country.name) for country in pycountry.countries], key=lambda x: x[1])

# noinspection PyUnresolvedReferences
FULL_PROVINCE_CHOICES = sorted(
    [(province.code, province.name, province.country_code) for province in pycountry.subdivisions], key=lambda x: x[1]
)

PROVINCE_CHOICES = [("", "----")] + [(province[0], province[1]) for province in FULL_PROVINCE_CHOICES]

country_subdivisions_map = {}
for province in FULL_PROVINCE_CHOICES:
    if province[2] == "IT":
        if re.match(r"^IT-\d{2}", province[0]):
            continue
    if province[2] not in country_subdivisions_map:
        country_subdivisions_map[province[2]] = []
    country_subdivisions_map[province[2]].append([province[0], province[1]])


MEMBERSHIP_CHOICES = (
    ("e", _("Absent")),
    ("j", _("Nothing")),
    ("s", _("Submitted")),
    ("a", _("Accepted")),
    ("p", _("Quota")),
)


class ResidenceWidget(forms.MultiWidget):
    template_name = "forms/widgets/residence_widget.html"

    def __init__(self, attrs=None):
        attr_common = {"class": "form-control"}
        widgets = [
            forms.Select(choices=COUNTRY_CHOICES),
            forms.Select(choices=PROVINCE_CHOICES),
            forms.TextInput(attrs={**attr_common, "placeholder": _("Municipality")}),
            forms.TextInput(attrs={**attr_common, "placeholder": _("Postal code")}),
            forms.TextInput(attrs={**attr_common, "placeholder": _("Street")}),
            forms.TextInput(attrs={**attr_common, "placeholder": _("House number")}),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return value.split("|")
        return [None] * 6


def validate_no_pipe(value):
    if "|" in value:
        raise forms.ValidationError(_("Character not allowed") + ": |")


class ResidenceField(forms.MultiValueField):
    def __init__(self, *args, **kwargs):
        fields = [
            forms.ChoiceField(choices=COUNTRY_CHOICES),
            forms.ChoiceField(choices=PROVINCE_CHOICES, required=False),
            forms.CharField(validators=[validate_no_pipe]),
            forms.CharField(max_length=7, validators=[validate_no_pipe]),
            forms.CharField(max_length=30, validators=[validate_no_pipe]),
            forms.CharField(max_length=10, validators=[validate_no_pipe]),
        ]
        widget = ResidenceWidget(attrs=None)
        super().__init__(*args, fields=fields, widget=widget, **kwargs)

    def compress(self, values):
        if not values:
            return ""
        values = [v if v is not None else "" for v in values]
        return "|".join(values)

    def clean(self, value):
        if not value:
            value = self.compress([None] * len(self.fields))
            return value

        try:
            cleaned_data = []
            for i, field in enumerate(self.fields):
                if i == 1 and (value[i] in (None, "")):
                    cleaned_data.append("")
                else:
                    cleaned_data.append(field.clean(value[i]))
            return self.compress(cleaned_data)
        except forms.ValidationError as err:
            raise err


class BaseProfileForm(MyForm):
    def _get_cached_assoc(self, request):
        """Get cached association object to avoid redundant database queries."""
        assoc_id = request.assoc["id"]
        if hasattr(request, "_cached_assoc") and request._cached_assoc.id == assoc_id:
            return request._cached_assoc

        assoc = Association.objects.get(pk=assoc_id)
        request._cached_assoc = assoc
        return assoc

    def _get_cached_features(self, request, assoc_id=None):
        """Get cached association features to avoid redundant function calls."""
        if hasattr(request, "_cached_features"):
            return request._cached_features

        if assoc_id is None:
            assoc_id = request.assoc["id"]

        features = get_assoc_features(assoc_id)
        request._cached_features = features
        return features

    def _get_cached_membership(self, instance, assoc_id):
        """Get cached membership object to avoid redundant queries."""
        if hasattr(instance, "_cached_membership"):
            return instance._cached_membership

        membership = get_user_membership(instance, assoc_id)
        instance._cached_membership = membership
        return membership

    def __init__(self, *args, **kwargs):
        """Initialize base profile form with field filtering based on association settings.

        Args:
            *args: Positional arguments passed to parent
            **kwargs: Keyword arguments passed to parent
        """
        super().__init__(*args, **kwargs)

        # Cache frequently accessed request data
        request = self.params["request"]
        self.allowed = request.assoc["members_fields"]

        # Use cached association data
        assoc = self._get_cached_assoc(request)

        # Pre-split and cache field sets
        self.mandatory = set(assoc.mandatory_fields.split(","))
        self.optional = set(assoc.optional_fields.split(","))

        # Field filtering
        always_allowed = {"name", "surname", "language"}
        fields_to_delete = [f for f in self.fields if f not in self.allowed and f not in always_allowed]

        # Batch delete fields
        for f in fields_to_delete:
            del self.fields[f]

        # Handle residence address field if needed
        if "residence_address" in self.allowed:
            self.fields["residence_address"] = ResidenceField(label=_("Residence address"))
            self.fields["residence_address"].required = "residence_address" in self.mandatory

            if self.instance.pk and self.instance.residence_address:
                residence_data = self.instance.residence_address
                self.initial["residence_address"] = residence_data

                # Safe split with error handling
                try:
                    aux = residence_data.split("|")
                    self.initial_nation = aux[0] if len(aux) > 0 else ""
                    self.initial_province = aux[1] if len(aux) > 1 else ""
                except (IndexError, AttributeError):
                    self.initial_nation = ""
                    self.initial_province = ""

            # Only assign if needed (avoid unnecessary memory allocation)
            self.country_subdivisions_map = country_subdivisions_map


class ProfileForm(BaseProfileForm):
    class Meta:
        model = Member
        fields = (
            "name",
            "surname",
            "legal_name",
            "nickname",
            "pronoun",
            "gender",
            "social_contact",
            "first_aid",
            "diet",
            "safety",
            "newsletter",
            "presentation",
            "birth_date",
            "birth_place",
            "nationality",
            "document_type",
            "document",
            "document_issued",
            "document_expiration",
            "fiscal_code",
            "phone_contact",
        )

        widgets = {
            "diet": Textarea(attrs={"rows": 5}),
            "safety": Textarea(attrs={"rows": 5}),
            "presentation": Textarea(attrs={"rows": 5}),
            "birth_date": DatePickerInput,
            "document_issued": DatePickerInput,
            "document_expiration": DatePickerInput,
        }

    def __init__(self, *args, **kwargs):
        """Initialize member form with dynamic field validation and configuration.

        Sets mandatory fields, handles voting candidates, and adds required
        data sharing consent field based on membership status.

        Args:
            *args: Variable positional arguments
            **kwargs: Variable keyword arguments including request context
        """
        super().__init__(*args, **kwargs)

        # Cache request data
        request = self.params["request"]
        assoc_id = request.assoc["id"]

        # Batch process mandatory field updates
        mandatory_asterisk = " (*)"
        fields_to_update = {}

        # Process mandatory fields
        for field_name in self.fields:
            if field_name in self.mandatory:
                field = self.fields[field_name]
                field.required = True
                fields_to_update[field_name] = _(field.label) + mandatory_asterisk

        # Process always-required fields
        for field_name in ["name", "surname"]:
            if field_name in self.fields:
                field = self.fields[field_name]
                fields_to_update[field_name] = _(field.label) + mandatory_asterisk

        # Apply all label updates at once
        for field_name, new_label in fields_to_update.items():
            self.fields[field_name].label = new_label

        # Handle presentation field for voting candidates
        if "presentation" in self.fields:
            vote_cands = get_assoc_config(self.params["request"].assoc["id"], "vote_candidates", "").split(",")
            if not self.instance.pk or str(self.instance.pk) not in vote_cands:
                self.delete_field("presentation")

        # Set default values
        initial_defaults = {}
        if "phone_contact" not in self.initial:
            initial_defaults["phone_contact"] = "+XX"
        if "birth_date" not in self.initial:
            initial_defaults["birth_date"] = "00/00/0000"

        # Apply initial values in batch
        self.initial.update(initial_defaults)

        # Membership checking
        share = False
        if self.instance.pk:
            membership = self._get_cached_membership(self.instance, assoc_id)
            share = membership.compiled

        # Add consent field only if needed
        if not share:
            self.fields["share"] = forms.BooleanField(
                required=True,
                label=_("Authorisation"),
                help_text=_(
                    "Do you consent to the sharing of your personal data in accordance with the GDPR and our Privacy Policy"
                )
                + "?",
            )

    def clean_birth_date(self):
        """
        Optimized birth date validation with cached association data.
        """
        data = self.cleaned_data["birth_date"]
        logger.debug(f"Validating birth date: {data}")

        # Use cached association
        request = self.params["request"]
        assoc_id = self.params["request"].assoc["id"]

        # Use cached features
        features = self._get_cached_features(request, assoc_id)

        if "membership" in features:
            min_age = get_assoc_config(assoc_id, "membership_age", "")
            if min_age:
                try:
                    min_age = int(min_age)
                    logger.debug(f"Checking minimum age {min_age} against birth date {data}")
                    age_diff = relativedelta(datetime.now(), data).years
                    if age_diff < min_age:
                        raise ValidationError(_("Minimum age: %(number)d") % {"number": min_age})
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid membership_age config: {min_age}, error: {e}")

        return data

    def clean(self):
        cleaned_data = super().clean()

        if "profile" in self.allowed and "profile" in self.mandatory:
            if not self.instance.profile:
                self.add_error(None, _("Please upload your profile photo") + "!")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if "residence_address" in self.cleaned_data:
            instance.residence_address = self.cleaned_data["residence_address"]
        if commit:
            instance.save()
        return instance


class MembershipRequestForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = ("request", "document")

    request = forms.FileField(
        label=_("Request signed"),
        help_text=_("Upload the scan of your signed application (image or pdf document)"),
        validators=[FileTypeValidator(allowed_types=["image/*", "application/pdf"])],
    )

    document = forms.FileField(
        label=_("Photo of an ID"),
        help_text=_("Upload a photo of the identity document that you listed in the request (image or pdf)"),
        validators=[FileTypeValidator(allowed_types=["image/*", "application/pdf"])],
    )


class MembershipConfirmForm(forms.Form):
    confirm_1 = forms.BooleanField(required=True, initial=False)
    confirm_2 = forms.BooleanField(required=True, initial=False)
    confirm_3 = forms.BooleanField(required=True, initial=False)
    confirm_4 = forms.BooleanField(required=True, initial=False)


class MembershipResponseForm(forms.Form):
    is_approved = forms.BooleanField(required=False, initial=True)
    response = forms.CharField(
        required=False,
        max_length=1000,
        help_text=_(
            "Optional text to be included in the email sent to the participant to notify them of the approval decision"
        ),
    )


class ExeVolunteerRegistryForm(MyForm):
    page_title = _("Volounteer data")

    page_info = _("This page allows you to add or edit a volunteer entry")

    class Meta:
        model = VolunteerRegistry
        exclude = []

        widgets = {
            "member": AssocMemberS2Widget,
            "start": DatePickerInput,
            "end": DatePickerInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_assoc(self.params["a_id"])

    def clean_member(self):
        member = self.cleaned_data["member"]

        # check if already used
        lst = VolunteerRegistry.objects.filter(member=member, assoc_id=self.params["a_id"])
        if lst.count() > 1:
            raise ValidationError("Volunteer entry already existing!")

        return member


class MembershipForm(BaseAccForm):
    amount = forms.DecimalField(min_value=0.01, max_value=1000, decimal_places=2)


class ExeMemberForm(BaseProfileForm):
    page_info = _("This page allows you to edit a member's profile")

    class Meta:
        model = Member
        fields = "__all__"
        widgets = {
            "birth_date": DatePickerInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "profile" in self.fields:
            self.fields["profile"].required = False


class ExeMembershipForm(MyForm):
    page_info = _("This page allows you to change a member's membership status")

    load_templates = ["membership"]

    class Meta:
        model = Membership
        fields = (
            "compiled",
            "credit",
            "tokens",
            "status",
            "request",
            "document",
            "card_number",
            "date",
            "newsletter",
        )


class ExeMembershipFeeForm(forms.Form):
    page_info = _("This page allows you to upload the invoce of payment of a membership fee")

    page_title = _("Upload membership fee")

    member = forms.ModelChoiceField(
        label=_("Member"),
        queryset=Member.objects.none(),
        required=False,
        widget=AssocMemberS2Widget,
    )

    invoice = forms.FileField(
        validators=[FileTypeValidator(allowed_types=["image/*", "application/pdf"])],
        label=_("Invoice"),
    )

    def __init__(self, *args, **kwargs):
        self.params = kwargs.pop("ctx", None)
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_assoc(self.params["a_id"])
        self.fields["member"].queryset = get_members_queryset(self.params["a_id"])

        assoc = Association.objects.get(pk=self.params["a_id"])
        choices = [(method.id, method.name) for method in assoc.payment_methods.all()]
        self.fields["method"] = forms.ChoiceField(
            required=True,
            choices=choices,
            label=_("Method"),
        )

    def clean_member(self):
        member = self.cleaned_data["member"]
        year = datetime.today().year

        if AccountingItemMembership.objects.filter(member=member, year=year).exists():
            self.add_error("member", _("Membership fee already existing for this user and for this year"))

        return member


class ExeMembershipDocumentForm(forms.Form):
    page_info = (
        _("This page allows you to upload a new membership documents")
        + " - "
        + _("Please note that the user must have confirmed it's consent to share their data with your organization")
    )

    page_title = _("Upload membership document")

    member = forms.ModelChoiceField(
        label=_("Member"),
        queryset=Member.objects.none(),
        required=False,
        widget=AssocMemberS2Widget,
    )

    request = forms.FileField(
        validators=[FileTypeValidator(allowed_types=["image/*", "application/pdf"])],
        label=_("Membership request"),
    )

    document = forms.FileField(
        validators=[FileTypeValidator(allowed_types=["image/*", "application/pdf"])],
        label=_("ID document photo"),
        required=False,
    )

    card_number = forms.IntegerField(label=_("Membership ID number"))

    date = forms.DateField(widget=DatePickerInput(), label=_("Date of membership approval"))

    def __init__(self, *args, **kwargs):
        self.params = kwargs.pop("ctx", None)
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_assoc(self.params["a_id"])
        self.fields["member"].queryset = get_members_queryset(self.params["a_id"])

        number = Membership.objects.filter(assoc_id=self.params["a_id"]).aggregate(Max("card_number"))[
            "card_number__max"
        ]
        if not number:
            number = 1
        else:
            number += 1
        self.initial["card_number"] = number

    def clean_member(self):
        member = self.cleaned_data["member"]
        membership = Membership.objects.get(member=member, assoc_id=self.params["a_id"])
        if membership.status not in [MembershipStatus.EMPTY, MembershipStatus.JOINED, MembershipStatus.UPLOADED]:
            self.add_error("member", _("User is already a member"))

        return member

    def clean_card_number(self):
        card_number = self.cleaned_data["card_number"]

        if Membership.objects.filter(assoc_id=self.params["a_id"], card_number=card_number).exists():
            self.add_error("card_number", _("There is already a member with this number"))

        return card_number


class ExeBadgeForm(MyForm):
    page_info = _("This page allows you to add or edit a badge, or assign it  to users")

    page_title = _("Badge")

    class Meta:
        model = Badge
        exclude = ("number",)

        widgets = {
            "members": AssocMemberS2WidgetMulti,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].widget.set_assoc(self.params["a_id"])


class ExeProfileForm(MyForm):
    page_title = _("Profile")

    page_info = _("This page allows you to set up the fields that participants can fill in in their user profile")

    class Meta:
        model = Association
        fields = ()

    def __init__(self, *args, **kwargs):
        """Initialize member field configuration form.

        Args:
            *args: Positional arguments passed to parent
            **kwargs: Keyword arguments passed to parent
        """
        super().__init__(*args, **kwargs)
        self.prevent_canc = True

        mandatory = set(self.instance.mandatory_fields.split(","))
        optional = set(self.instance.optional_fields.split(","))

        # MEMBERS INFO
        fields = self.get_members_fields()
        for slug, name, help_text in fields:
            if slug in mandatory:
                init = MemberFieldType.MANDATORY
            elif slug in optional:
                init = MemberFieldType.OPTIONAL
            else:
                init = MemberFieldType.ABSENT

            self.fields[slug] = forms.ChoiceField(
                required=True,
                choices=MemberFieldType.choices,
                label=name,
                help_text=help_text,
            )

            self.initial[slug] = init

        if self.instance.nationality != FeatureNationality.ITALY:
            self.delete_field("fiscal_code")

    @staticmethod
    def get_members_fields():
        """
        Get available member fields for form configuration.

        Returns:
            list: List of tuples containing field information (name, verbose_name, help_text)
        """
        skip = [
            "id",
            "deleted",
            "created",
            "updated",
            "user",
            "search",
            "name",
            "email",
            "surname",
            "deleted_by_cascade",
            "language",
            "newsletter",
            "parent",
            "legal_gender",
        ]
        choices = []
        # noinspection PyUnresolvedReferences,PyProtectedMember
        for f in Member._meta.get_fields():
            if not str(f).startswith("larpmanager.Member."):
                continue
            if f.name in skip:
                continue

            choices.append((f.name, f.verbose_name, f.help_text))
        return choices

    def save(self, commit=True):
        """Save form data and update member field configurations.

        Args:
            commit: Whether to save the instance to database

        Returns:
            The saved form instance
        """
        instance = super().save(commit=commit)

        mandatory = []
        optional = []

        fields = self.get_members_fields()
        for slug, _verbose_name, _help_text in fields:
            if slug not in self.cleaned_data:
                continue
            value = self.cleaned_data[slug]
            if value == MemberFieldType.MANDATORY:
                mandatory.append(slug)
            elif value == MemberFieldType.OPTIONAL:
                optional.append(slug)

        instance.mandatory_fields = ",".join(mandatory)
        instance.optional_fields = ",".join(optional)

        instance.save()

        return instance
