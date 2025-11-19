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

import secrets
import uuid
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from larpmanager.cache.config import save_single_config
from larpmanager.forms.member import MyAuthForm
from larpmanager.utils.base import get_context
from larpmanager.utils.common import welcome_user
from larpmanager.utils.miscellanea import check_centauri
from larpmanager.utils.tutorial_query import query_index
from larpmanager.views.larpmanager import lm_home
from larpmanager.views.user.event import calendar

if TYPE_CHECKING:
    from django.forms import Form


class MyLoginView(LoginView):
    """View for MyLogin."""

    template_name = "registration/login.html"
    authentication_form = MyAuthForm

    def form_valid(self, authentication_form: Form) -> HttpResponse:
        """Handle valid login form submission.

        Processes a successfully validated authentication form by welcoming the user
        and delegating to the parent class for standard login handling.

        Args:
            authentication_form (AuthenticationForm): Valid authentication form containing user credentials
                and authentication state.

        Returns:
            HttpResponse: HTTP response after successful login processing, typically
                a redirect to the next page or default landing page.

        Note:
            This method is called only after form validation has passed. The welcome_user
            function handles user greeting logic and session setup.

        """
        # Welcome the authenticated user and set up session state
        welcome_user(self.request, authentication_form.get_user())

        # Delegate to parent class for standard login flow completion
        return super().form_valid(authentication_form)


def home(request: HttpRequest, lang: str | None = None) -> HttpResponse:
    """Handle home page routing based on association.

    Routes users to appropriate home page view depending on their association ID.
    For association ID 0, shows the main landing page. Otherwise, checks for
    Centauri-specific handling or displays the calendar view.

    Args:
        request: HTTP request object containing user and association data
        lang: Optional language code for localization, defaults to None

    Returns:
        HttpResponse: Rendered home page, calendar view, or Centauri-specific response

    Note:
        Association ID 0 is reserved for the main/default organization.

    """
    # Check if this is the default/main association (ID 0)
    if request.association["id"] == 0:
        return lm_home(request)

    # For other associations, check Centauri handling or fallback to calendar
    context = get_context(request)
    return check_centauri(request, context) or calendar(request, context, lang)


def error_404(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Handle 404 errors with custom template.

    Renders a custom 404 error page when a requested resource is not found.
    The exception details are passed to the template context for debugging
    purposes in development environments.

    Args:
        request (HttpRequest): The HTTP request object that triggered the 404 error.
        exception (Exception): The exception instance that caused the 404 error,
                              typically a Http404 exception.

    Returns:
        HttpResponse: A rendered HTTP response containing the 404 error page
                     with the exception context.

    """
    # Render the custom 404 template with exception context
    # The 'exe' variable provides exception details to the template
    return render(request, "404.html", {"exe": exception})


def error_500(request: HttpRequest) -> Any:
    """Handle 500 errors with custom template.

    Args:
        request: HTTP request object

    Returns:
        HttpResponse: Rendered 500 error page

    """
    return render(request, "500.html")


def after_login(request: HttpRequest, subdomain: str, path: str = "") -> HttpResponse:
    """Handle post-login redirect based on subdomain.

    Creates a temporary session token and redirects the authenticated user to the
    specified subdomain with the token for secure cross-subdomain authentication.

    Args:
        request: HTTP request object containing user authentication data
        subdomain: Target subdomain to redirect to (e.g., 'app', 'admin')
        path: Optional path to append to the redirect URL. Defaults to empty string.

    Returns:
        HttpResponse: Redirect response to the target subdomain URL with session token,
                     or redirect to login page if user is not authenticated

    Note:
        The session token expires after 60 seconds for security purposes.

    """
    # Check if user is authenticated, redirect to login if not
    user = request.user
    if not user.is_authenticated:
        return redirect("/login/")

    # Generate secure random token for cross-subdomain authentication
    token = secrets.token_urlsafe(32)

    # Store token in cache with user ID and short timeout for security
    # Session token has short 60 second timeout for security
    cache.set(f"session_token:{token}", user.id, timeout=60)

    # Build redirect URL with subdomain and token
    base_domain = get_base_domain(request)
    return redirect(f"https://{subdomain}.{base_domain}/{path}?token={token}")


def get_base_domain(request: HttpRequest) -> str:
    """Extract the base domain from the request host.

    Args:
        request: Django HTTP request object.

    Returns:
        Base domain (e.g., 'example.com' from 'subdomain.example.com').

    """
    host = request.get_host()
    host_parts = host.split(".")

    # Use last 2 parts for base domain (domain.tld)
    minimum_parts_for_base_domain = 2
    if len(host_parts) >= minimum_parts_for_base_domain:
        return ".".join(host_parts[-2:])
    return host


@require_POST
def tutorial_query(request: HttpRequest) -> HttpResponse:
    """Delegate to query_index for tutorial queries."""
    return query_index(request)


@login_required
@csrf_exempt
def upload_media(request: HttpRequest) -> JsonResponse:
    """Handle media file uploads for TinyMCE editor.

    Security measures:
    - Requires authentication
    - Validates file extension against whitelist
    - Enforces file size limit
    - Generates unique filenames to prevent overwriting

    Args:
        request: HTTP request containing file upload data

    Returns:
        JSON response with file location or error message

    """
    if request.method != "POST" or not request.FILES.get("file"):
        return JsonResponse({"error": "Invalid request"}, status=400)

    file = request.FILES["file"]

    # Validate file size
    if file.size > settings.MAX_UPLOAD_SIZE:
        max_size_mb = settings.MAX_UPLOAD_SIZE / (1024 * 1024)
        return JsonResponse({"error": f"File size exceeds maximum allowed size of {max_size_mb}MB"}, status=400)

    # Extract and validate file extension
    file_ext = file.name[file.name.rfind(".") :].lower() if "." in file.name else ""

    if not file_ext or file_ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(settings.ALLOWED_UPLOAD_EXTENSIONS))
        return JsonResponse({"error": f"File type not allowed. Allowed types: {allowed}"}, status=400)

    # Generate timestamp and unique filename
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    filename = f"{timestamp}_{uuid.uuid4().hex}{file_ext}"

    # Save file to association-specific directory
    path = default_storage.save(f"tinymce_uploads/{request.association['id']}/{filename}", file)

    return JsonResponse({"location": default_storage.url(path)})


@require_POST
def set_member_config(request: HttpRequest) -> JsonResponse:
    """Update member configuration settings via AJAX.

    This function handles AJAX requests to update member-specific configuration
    settings. It validates the request, processes boolean values, and saves the
    configuration using the save_single_config utility.

    Args:
        request (HttpRequest): HTTP request containing 'name' and 'value' parameters
            in POST data. Expected to have authenticated user.

    Returns:
        JsonResponse: JSON response with 'res' status and optional 'msg' field.
            Returns 'ko' status with error message on validation failure or
            processing error.

    Note:
        - Requires authenticated user
        - Converts string 'true'/'false' to boolean values
        - All parameter values are converted to lowercase for consistency

    """
    # Check user authentication status
    if not request.user.is_authenticated:
        return JsonResponse({"res": "ko", "msg": "not authenticated"})

    # Extract and validate configuration name parameter
    config_name = request.POST.get("name", "").lower()
    if not config_name:
        return JsonResponse({"res": "ko", "msg": "empty name"})

    # Extract and validate configuration value parameter
    value = request.POST.get("value", "").lower()
    if not value:
        return JsonResponse({"res": "ko", "msg": "empty value"})

    # Convert string boolean values to actual boolean types
    if value == "true":
        value = True
    elif value == "false":
        value = False

    # Save the configuration and return response
    save_single_config(request.user.member, config_name, value)
    return JsonResponse({"res": "ko"})
