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
from typing import Any, ClassVar

from django import forms
from django.core.exceptions import ValidationError
from django.forms import Textarea
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV3

from larpmanager.forms.base import MyForm
from larpmanager.models.larpmanager import LarpManagerTicket
from larpmanager.utils.common import get_recaptcha_secrets


def _get_captcha(form: forms.Form, request: HttpRequest) -> None:
    """Add reCAPTCHA field to form if secrets are configured."""
    # Get reCAPTCHA public and private keys from settings
    recaptcha_public_key, recaptcha_private_key = get_recaptcha_secrets(request)
    if not recaptcha_public_key or not recaptcha_private_key:
        return

    # Add reCAPTCHA v3 field to form
    form.fields["captcha"] = ReCaptchaField(
        widget=ReCaptchaV3,
        label="",
        public_key=recaptcha_public_key,
        private_key=recaptcha_private_key,
    )


class LarpManagerCheck(forms.Form):
    """Represents LarpManagerCheck model."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure CAPTCHA if needed."""
        # Extract request from kwargs for CAPTCHA configuration
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        _get_captcha(self, self.request)


class LarpManagerContact(LarpManagerCheck):
    """Represents LarpManagerContact model."""

    email = forms.EmailField(required=True, label="", widget=forms.EmailInput(attrs={"placeholder": "Email"}))

    content = forms.CharField(
        required=True,
        max_length=3000,
        label="",
        widget=Textarea(attrs={"rows": 10, "placeholder": "Content"}),
    )

    verification = forms.CharField(
        required=True,
        max_length=10,
        label="",
        widget=forms.TextInput(attrs={"placeholder": _("The name of our hobby, four letters")}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize delete association form."""
        super().__init__(*args, **kwargs)

    def clean_verification(self) -> str:
        """Validate that the verification field contains 'larp'."""
        verification = self.cleaned_data.get("verification", "")
        if verification.strip().lower() != "larp":
            raise ValidationError(_("Incorrect answer. Please enter the name of our hobby."))
        return verification


class LarpManagerTicketForm(MyForm):
    """Form for LarpManagerTicket."""

    class Meta:
        model = LarpManagerTicket
        fields = ("email", "content", "screenshot")
        widgets: ClassVar[dict] = {"content": Textarea(attrs={"rows": 5})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and setup captcha for unauthenticated users."""
        super().__init__(*args, **kwargs)

        # Add captcha field for unauthenticated users
        if not self.params["request"].user.is_authenticated:
            _get_captcha(self, self.params["request"])

        # Remove screenshot field if reason is provided
        if self.params.get("reason"):
            del self.fields["screenshot"]
