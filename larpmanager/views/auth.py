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

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetConfirmView
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django_registration import signals
from django_registration.backends.one_step.views import RegistrationView

from larpmanager.models.member import Membership, MembershipStatus, get_user_membership


class MyRegistrationView(RegistrationView):
    def register(self, form):
        new_user = form.save()
        new_user = authenticate(
            **{
                User.USERNAME_FIELD: new_user.get_username(),
                "password": form.cleaned_data["password1"],
            }
        )
        login(self.request, new_user)
        signals.user_registered.send(sender=self.__class__, user=new_user, request=self.request)
        messages.success(self.request, _("Registration completed successfully!"))

        if self.request.assoc["id"] > 1:
            mb = get_user_membership(self.request.user.member, self.request.assoc["id"])
            mb.status = MembershipStatus.JOINED
            mb.save()

        return new_user

    def get_success_url(self, user=None):
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}):
            return next_url
        return self.success_url or reverse("home")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs


class MyPasswordResetConfirmView(PasswordResetConfirmView):
    def form_valid(self, form):
        res = super().form_valid(form)

        for mb in (
            Membership.objects.filter(member_id=form.user.member.id)
            .exclude(password_reset__exact="")
            .exclude(password_reset__isnull=True)
        ):
            mb.password_reset = None
            mb.save()

        return res
