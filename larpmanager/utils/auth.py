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
from django.db.models import Max
from django.http import Http404

from larpmanager.models.access import EventPermission


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account adapter for LarpManager.

    Handles automatic user linking and profile updates from social login data.
    """

    @staticmethod
    def update_member(user, sociallogin):
        """Update member profile from social login data.

        Args:
            user: Django User instance
            sociallogin: Social login instance with extra data

        Side effects:
            Updates member's name and surname if they are empty
        """
        data = sociallogin.account.extra_data
        # print(data)
        if "given_name" in data and len(user.member.name) == 0:
            user.member.name = data["given_name"]
        if "family_name" in data and len(user.member.surname) == 0:
            user.member.surname = data["family_name"]
        user.member.save()

        # if user exists, connect the account to the existing account and login

    def pre_social_login(self, request, sociallogin):
        """Handle social login before user creation.

        Links social account to existing user if email matches.

        Args:
            request: Django HTTP request
            sociallogin: Social login instance

        Side effects:
            Connects social account to existing user and updates profile
        """
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
        """Save new user from social login.

        Args:
            request: Django HTTP request
            sociallogin: Social login instance
            form: Optional form data

        Returns:
            User: Created user instance

        Side effects:
            Updates member profile from social login data
        """
        user = super().save_user(request, sociallogin, form)
        self.update_member(user, sociallogin)


def is_lm_admin(request):
    """Check if user is a LarpManager administrator.

    Args:
        request: Django HTTP request with authenticated user

    Returns:
        bool: True if user is superuser or LM admin
    """
    if not hasattr(request.user, "member"):
        return False
    if request.user.is_superuser:
        return True
    # TODO CHECK ADMIN GROUP
    return False


def check_lm_admin(request):
    """Verify user is LM admin and return admin context.

    Args:
        request: Django HTTP request

    Returns:
        dict: Admin context with association ID and admin flag

    Raises:
        Http404: If user is not a LM administrator
    """
    if not is_lm_admin(request):
        raise Http404("Not lm admin")
    return {"a_id": request.assoc["id"], "lm_admin": 1}


def get_allowed_managed():
    """Get list of allowed management permission keys.

    Returns:
        list: List of permission strings for management access
    """
    allowed = [
        "exe_events",
        "orga_event",
        "exe_accounting",
        "orga_cancellations",
        "orga_registration_form",
        "orga_registration_tickets",
        "orga_registrations",
        "orga_accounting",
        "orga_sensitive",
        "orga_preferences",
        "exe_preferences",
    ]
    return allowed


def assign_event_permission_number(event_permission):
    """Assign number to event permission if not set.

    Args:
        event_permission: EventPermission instance to assign number to
    """
    if not event_permission.number:
        n = EventPermission.objects.filter(feature__module=event_permission.feature.module).aggregate(Max("number"))[
            "number__max"
        ]
        if not n:
            n = 1
        event_permission.number = n + 10
