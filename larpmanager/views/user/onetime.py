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

import os

from django.http import Http404, StreamingHttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from larpmanager.models.miscellanea import OneTimeAccessToken


def file_iterator(file_object, chunk_size=8192):
    """
    Generator to stream file in chunks.

    Args:
        file_object: File object to stream
        chunk_size: Size of each chunk in bytes

    Yields:
        bytes: Chunks of file data
    """
    try:
        file_object.seek(0)
        while True:
            chunk = file_object.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        file_object.close()


@never_cache
@require_http_methods(["GET"])
def onetime_access(request, token):
    """
    Public view to access one-time content via token.
    Security features:
    - No caching headers
    - No indexing headers
    - Token can only be used once
    - Streaming instead of direct download
    - Logs access information
    """
    try:
        access_token = OneTimeAccessToken.objects.select_related("content").get(token=token)
    except OneTimeAccessToken.DoesNotExist:
        return render(
            request,
            "larpmanager/event/onetime/error.html",
            {
                "error_title": _("Invalid Token"),
                "error_message": _("This access link is invalid or has expired."),
            },
            status=404,
        )

    # Check if content is active
    if not access_token.content.active:
        return render(
            request,
            "larpmanager/event/onetime/error.html",
            {
                "error_title": _("Content Unavailable"),
                "error_message": _("This content is currently not available."),
            },
            status=404,
        )

    # Check if token has already been used
    if access_token.used:
        return render(
            request,
            "larpmanager/event/onetime/already_used.html",
            {
                "token": access_token,
                "used_at": access_token.used_at,
                "user_agent": access_token.user_agent,
            },
        )

    # Mark token as used and log access information
    member = request.user.member if request.user.is_authenticated and hasattr(request.user, "member") else None
    access_token.mark_as_used(request=request, member=member)

    # Render video player page
    content = access_token.content
    return render(
        request,
        "larpmanager/event/onetime/player.html",
        {
            "content": content,
            "token": token,
        },
    )


@never_cache
@require_http_methods(["GET"])
def onetime_stream(request, token):
    """
    Stream the media file for a one-time content.
    This endpoint is called by the video player to actually stream the file.
    """
    try:
        access_token = OneTimeAccessToken.objects.select_related("content").get(token=token)
    except OneTimeAccessToken.DoesNotExist:
        raise Http404(_("Invalid token"))

    # Verify token is used and content is active
    if not access_token.used:
        raise Http404(_("Token not initialized"))

    if not access_token.content.active:
        raise Http404(_("Content unavailable"))

    content = access_token.content

    # Open the file
    try:
        file = content.file.open("rb")
    except Exception:
        raise Http404(_("File not found"))

    # Get file size
    file_size = content.file.size

    # Handle range requests for seeking in video
    range_header = request.META.get("HTTP_RANGE", "").strip()
    range_match = None
    if range_header:
        import re

        range_match = re.search(r"bytes=(\d+)-(\d*)", range_header)

    if range_match:
        # Partial content request
        first_byte = int(range_match.group(1))
        last_byte = int(range_match.group(2)) if range_match.group(2) else file_size - 1

        file.seek(first_byte)
        length = last_byte - first_byte + 1

        response = StreamingHttpResponse(
            file_iterator(file, chunk_size=8192 * 16),
            status=206,
            content_type=content.content_type or "application/octet-stream",
        )
        response["Content-Length"] = str(length)
        response["Content-Range"] = f"bytes {first_byte}-{last_byte}/{file_size}"
    else:
        # Full file request
        response = StreamingHttpResponse(
            file_iterator(file, chunk_size=8192 * 16),
            content_type=content.content_type or "application/octet-stream",
        )
        response["Content-Length"] = str(file_size)

    # Security headers
    response["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["Accept-Ranges"] = "bytes"

    # Set filename for download (optional)
    filename = os.path.basename(content.file.name)
    response["Content-Disposition"] = f'inline; filename="{filename}"'

    return response
