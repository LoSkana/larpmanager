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

import json

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from larpmanager.models.association import Association
from larpmanager.models.base import PublisherApiKey
from larpmanager.models.event import Run
from larpmanager.models.member import Log, Member
from larpmanager.utils.tasks import notify_admins
from larpmanager.views.manage import _get_registration_status_code


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for_header = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for_header:
        client_ip = x_forwarded_for_header.split(",")[0]
    else:
        client_ip = request.META.get("REMOTE_ADDR")
    return client_ip


def log_api_access(api_key, request, response_status, events_count=0):
    """Log API access using the existing Log model."""
    try:
        # Use a system member or create a placeholder for API access
        system_member, created = Member.objects.get_or_create(
            username="api_system", defaults={"email": "api@larpmanager.com", "first_name": "API", "last_name": "System"}
        )

        log_data = {
            "api_key_id": api_key.id,
            "api_key_name": api_key.name,
            "ip_address": get_client_ip(request),
            "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            "referer": request.META.get("HTTP_REFERER", ""),
            "response_status": response_status,
            "events_count": events_count,
            "timestamp": timezone.now().isoformat(),
        }

        Log.objects.create(member=system_member, eid=api_key.id, cls="PublisherAPI", dct=json.dumps(log_data), dl=False)

        # Update API key usage
        api_key.last_used = timezone.now()
        api_key.usage_count += 1
        api_key.save()

    except Exception:
        # Don't let logging errors break the API
        pass


def validate_api_key(request: HttpRequest) -> tuple[PublisherApiKey | None, JsonResponse | None]:
    """Validate API key from request parameters.

    Args:
        request: HTTP request object containing GET parameters

    Returns:
        tuple: A tuple containing:
            - PublisherApiKey object if valid, None if invalid
            - JsonResponse with error if validation fails, None if successful

    Raises:
        None: All exceptions are handled internally and returned as error responses
    """
    # Extract API key from GET parameters
    api_key_value = request.GET.get("api_key")
    if not api_key_value:
        return None, JsonResponse({"error": "API key required"}, status=401)

    # Attempt to retrieve and validate the API key from database
    try:
        api_key = PublisherApiKey.objects.get(key=api_key_value, active=True)
    except ObjectDoesNotExist:
        # Return error response for invalid or inactive API keys
        return None, JsonResponse({"error": "Invalid API key"}, status=401)

    # Return valid API key object with no error
    return api_key, None


@require_GET
def published_events(request: HttpRequest) -> JsonResponse:
    """API endpoint to get upcoming runs from associations with publisher feature enabled.

    This endpoint returns a list of upcoming LARP events from associations that have
    the publisher feature enabled. It validates API keys and restricts access to the
    primary domain in production.

    Args:
        request: HTTP request object containing API key and association context

    Returns:
        JsonResponse: JSON response containing runs data with the following structure:
            - runs: List of event dictionaries with id, name, dates, association info
            - count: Total number of runs returned
            - generated_at: ISO timestamp of response generation

    Raises:
        JsonResponse: Returns error responses for invalid API keys, domain restrictions,
                     or internal server errors (status codes: 403, 401, 500)
    """
    # Restrict access to primary domain only in production environments
    if not settings.DEBUG and hasattr(request, "assoc") and request.assoc.get("id", 0) != 0:
        return JsonResponse({"error": "This endpoint is only available on the primary domain"}, status=403)

    # Validate the provided API key and return early if invalid
    api_key, error_response = validate_api_key(request)
    if error_response:
        return error_response

    try:
        # Query associations that have publisher feature enabled and are not deleted
        publisher_associations = Association.objects.filter(
            features__slug="publisher", deleted__isnull=True
        ).select_related("skin")

        # Get all upcoming runs from publisher associations, ordered by start date
        now = timezone.now()
        runs = (
            Run.objects.filter(event__assoc__in=publisher_associations, start__gte=now)
            .select_related("event", "event__assoc", "event__assoc__skin")
            .order_by("start")
        )

        # Initialize response data structure
        events_data = []

        # Process each run to build the response data
        for run in runs:
            event = run.event
            assoc = run.event.assoc

            # Get registration status information for this run
            run_status = _get_registration_status_code(run)

            # Build base event data structure with required fields
            event_data = {
                "id": run.id,
                "name": str(run),
                "date_start": run.start.isoformat() if run.start else None,
                "date_end": run.end.isoformat() if run.end else None,
                "association": assoc.name,
                "signup_url": f"https://{assoc.slug}.{assoc.skin.domain}/{run.get_slug()}/register/",
                "status": run_status[0],
                "additional": run_status[1],
            }

            # Map optional event attributes to response fields
            mapping = {
                "where": "location",
                "authors": "authors",
                "description": "description",
                "genre": "genre",
                "website": "website",
            }

            # Add optional fields if they exist and have values
            for orig, dest in mapping.items():
                if not hasattr(event, orig):
                    continue
                value = getattr(event, orig, "")
                if not value:
                    continue
                event_data[dest] = value

            # Add cover image URL if available
            if event.cover:
                event_data["cover"] = request.build_absolute_uri(event.cover_thumb.url)

            events_data.append(event_data)

        # Build final response with metadata
        response_data = {"runs": events_data, "count": len(events_data), "generated_at": timezone.now().isoformat()}

        # Log successful API access for monitoring
        log_api_access(api_key, request, 200, len(events_data))

        return JsonResponse(response_data)

    except Exception as e:
        # Notify administrators of API errors
        notify_admins("error api publisher", "", e)

        # Log error access if api_key was successfully retrieved
        if "api_key" in locals():
            log_api_access(api_key, request, 500)

        # Return appropriate error response based on debug mode
        if settings.DEBUG:
            return JsonResponse({"error": str(e)}, status=500)
        else:
            return JsonResponse({"error": "Internal server error"}, status=500)
