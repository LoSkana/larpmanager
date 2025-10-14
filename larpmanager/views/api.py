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
from django.http import JsonResponse
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
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def log_api_access(api_key, request, response_status, events_count=0):
    """Log API access using the existing Log model."""
    try:
        # Use a system member or create a placeholder for API access
        member, created = Member.objects.get_or_create(
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

        Log.objects.create(member=member, eid=api_key.id, cls="PublisherAPI", dct=json.dumps(log_data), dl=False)

        # Update API key usage
        api_key.last_used = timezone.now()
        api_key.usage_count += 1
        api_key.save()

    except Exception:
        # Don't let logging errors break the API
        pass


def validate_api_key(request):
    """Validate API key."""
    api_key_value = request.GET.get("api_key")
    if not api_key_value:
        return None, JsonResponse({"error": "API key required"}, status=401)

    try:
        api_key = PublisherApiKey.objects.get(key=api_key_value, active=True)
    except ObjectDoesNotExist:
        return None, JsonResponse({"error": "Invalid API key"}, status=401)

    return api_key, None


@require_GET
def published_events(request):
    """API endpoint to get upcoming runs from associations with publisher feature enabled."""
    # This endpoint should only work on the primary domain (assoc.id == 0)
    if not settings.DEBUG and hasattr(request, "assoc") and request.assoc.get("id", 0) != 0:
        return JsonResponse({"error": "This endpoint is only available on the primary domain"}, status=403)

    # Validate API key
    api_key, error_response = validate_api_key(request)
    if error_response:
        return error_response

    try:
        # Get associations with publisher feature enabled
        publisher_associations = Association.objects.filter(
            features__slug="publisher", deleted__isnull=True
        ).select_related("skin")

        # Get upcoming runs from these associations
        now = timezone.now()
        runs = (
            Run.objects.filter(event__assoc__in=publisher_associations, start__gte=now)
            .select_related("event", "event__assoc", "event__assoc__skin")
            .order_by("start")
        )

        # Build response data
        events_data = []
        for run in runs:
            event = run.event
            assoc = run.event.assoc

            run_status = _get_registration_status_code(run)

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

            mapping = {
                "where": "location",
                "authors": "authors",
                "description": "description",
                "genre": "genre",
                "website": "website",
            }

            for orig, dest in mapping.items():
                if not hasattr(event, orig):
                    continue
                value = getattr(event, orig, "")
                if not value:
                    continue
                event_data[dest] = value

            # Add optional profile image if available
            if event.cover:
                event_data["cover"] = request.build_absolute_uri(event.cover_thumb.url)

            events_data.append(event_data)

        response_data = {"runs": events_data, "count": len(events_data), "generated_at": timezone.now().isoformat()}

        # Log successful access
        log_api_access(api_key, request, 200, len(events_data))

        return JsonResponse(response_data)

    except Exception as e:
        notify_admins("error api publisher", "", e)

        # Log error access
        if "api_key" in locals():
            log_api_access(api_key, request, 500)

        if settings.DEBUG:
            return JsonResponse({"error": str(e)}, status=500)
        else:
            return JsonResponse({"error": "Internal server error"}, status=500)
