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

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    @staticmethod
    def update_member(user, sociallogin):
        data = sociallogin.account.extra_data
        # print(data)
        if "given_name" in data and len(user.member.name) == 0:
            user.member.name = data["given_name"]
        if "family_name" in data and len(user.member.surname) == 0:
            user.member.surname = data["family_name"]
        user.member.save()

        # if user exists, connect the account to the existing account and login

    def pre_social_login(self, request, sociallogin):
        user = sociallogin.user

        if user.id:
            return
        if not user.email:
            return

        try:
            user = User.objects.get(email=user.email)
            sociallogin.connect(request, user)
            self.update_member(user, sociallogin)
        except ObjectDoesNotExist:
            pass

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        self.update_member(user, sociallogin)


def is_lm_admin(request):
    if not hasattr(request.user, "member"):
        return False
    if request.user.is_superuser:
        return True
    # TODO CHECK ADMIN GROUP
    return False


def check_lm_admin(request):
    if not is_lm_admin(request):
        raise Http404("Not lm admin")
    return {"a_id": request.assoc["id"], "lm_admin": 1}
