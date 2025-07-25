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
from django.forms import Textarea
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV3

from larpmanager.utils.common import get_recaptcha_secrets


class LarpManagerCheck(forms.Form):
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        public, private = get_recaptcha_secrets(self.request)
        self.fields["captcha"] = ReCaptchaField(
            widget=ReCaptchaV3,
            label="", 
            public_key=public, 
            private_key=private
        )


class LarpManagerContact(LarpManagerCheck):
    email = forms.EmailField(required=True, label="", widget=forms.TextInput(attrs={"placeholder": "Email"}))
    content = forms.CharField(
        required=True,
        max_length=3000,
        label="",
        widget=Textarea(attrs={"rows": 10, "placeholder": "Content"}),
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class LarpManagerTicket(LarpManagerContact):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
