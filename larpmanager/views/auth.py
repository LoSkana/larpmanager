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
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetConfirmView
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django_registration import signals
from django_registration.backends.one_step.views import RegistrationView

from larpmanager.models.member import Member, Membership, MembershipStatus, get_user_membership

if TYPE_CHECKING:
    from django.forms import Form
    from django.http import HttpResponse


class MyRegistrationView(RegistrationView):
    """View for MyRegistration."""

    def register(self, form: Form) -> User:
        """Register a new user and set up membership if needed.

        Creates a new user account from the provided form data, authenticates
        and logs in the user, sends registration signals, and sets up membership
        status for non-default associations.

        Args:
            form: Registration form with validated user data containing username,
                password, and other required registration fields.

        Returns:
            User: The newly created and authenticated user instance.

        Raises:
            AuthenticationError: If user authentication fails after creation.

        """
        # Create new user from validated form data
        new_user = form.save()

        # Authenticate the newly created user with provided credentials
        new_user = authenticate(
            **{
                User.USERNAME_FIELD: new_user.get_username(),
                "password": form.cleaned_data["password1"],
            },
        )

        # Log in the authenticated user and send registration signal
        login(self.request, new_user)
        signals.user_registered.send(sender=self.__class__, user=new_user, request=self.request)
        messages.success(self.request, _("Registration completed successfully!"))

        # Set membership status to JOINED for non-default associations
        if self.request.association["id"] > 1:
            user_membership = get_user_membership(self.request.user.member, self.request.association["id"])
            user_membership.status = MembershipStatus.JOINED
            user_membership.save()

        return new_user

    def get_success_url(self, user: Member | None = None) -> str:  # noqa: ARG002
        """Get URL to redirect to after successful registration.

        Determines the appropriate redirect URL after a user successfully completes
        registration. Prioritizes 'next' parameter from POST/GET data if it's safe,
        otherwise falls back to the configured success_url or home page.

        Args:
            user: User instance, typically a Member model instance. Optional parameter
                that may be used for user-specific redirect logic.

        Returns:
            A valid URL string for redirection. Will be either the 'next' parameter
            (if safe), the instance's success_url attribute, or the 'home' URL as fallback.

        Note:
            The 'next' URL is validated for security using Django's
            url_has_allowed_host_and_scheme to prevent open redirect vulnerabilities.

        """
        # Check for 'next' parameter in POST data first, then GET data
        next_url = self.request.POST.get("next") or self.request.GET.get("next")

        # Validate the next_url for security to prevent open redirect attacks
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}):
            return next_url

        # Fall back to success_url attribute or default home page
        return self.success_url or reverse("home")

    def get_form_kwargs(self) -> Any:
        """Get keyword arguments for form initialization.

        Returns:
            dict: Form kwargs including request object

        """
        form_kwargs = super().get_form_kwargs()
        form_kwargs["request"] = self.request
        return form_kwargs


class MyPasswordResetConfirmView(PasswordResetConfirmView):
    """View for MyPasswordResetConfirm."""

    def form_valid(self, form: Form) -> HttpResponse:
        """Handle valid password reset form submission.

        Processes a valid password reset confirmation form by calling the parent
        implementation and then clearing any pending password reset tokens for
        all memberships associated with the user.

        Args:
            form: Valid password reset confirmation form containing the user
                and new password information.

        Returns:
            HttpResponse: Response after processing form, typically a redirect
            to the login page or success page.

        """
        # Call parent form_valid to handle the actual password reset
        response = super().form_valid(form)

        # Find all memberships for this user that have pending password reset tokens
        for membership in (
            Membership.objects.filter(member_id=form.user.member.id)
            .exclude(password_reset__exact="")
            .exclude(password_reset__isnull=True)
        ):
            # Clear the password reset token since password has been successfully reset
            membership.password_reset = None
            membership.save()

        return response
