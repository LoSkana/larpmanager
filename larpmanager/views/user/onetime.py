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
import re
from collections.abc import Generator
from typing import BinaryIO, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from larpmanager.models.miscellanea import OneTimeAccessToken


def file_iterator(
    file_object: BinaryIO, chunk_size: int = 8192, start_pos: Optional[int] = None, max_length: Optional[int] = None
) -> Generator[bytes, None, None]:
    """Generator to stream file in chunks with optional range support.

    Efficiently reads a file in chunks, optionally starting from a specific
    position and limiting the total bytes read. The file is automatically
    closed when iteration completes or an exception occurs.

    Args:
        file_object: Binary file object to stream from
        chunk_size: Size of each chunk in bytes. Defaults to 8192
        start_pos: Starting position in bytes. If None, uses current position
        max_length: Maximum bytes to read. If None, reads until EOF

    Yields:
        bytes: Sequential chunks of file data

    Raises:
        OSError: If file operations (seek/read) fail
        ValueError: If chunk_size <= 0 or start_pos/max_length < 0
    """
    try:
        # Seek to starting position if specified
        if start_pos is not None:
            file_object.seek(start_pos)

        bytes_read = 0

        # Main reading loop - continue until EOF or max_length reached
        while True:
            # Calculate appropriate chunk size for this iteration
            if max_length is not None:
                remaining = max_length - bytes_read
                if remaining <= 0:
                    break
                current_chunk_size = min(chunk_size, remaining)
            else:
                current_chunk_size = chunk_size

            # Read the next chunk from file
            chunk = file_object.read(current_chunk_size)
            if not chunk:  # EOF reached
                break

            # Track total bytes read and yield the chunk
            bytes_read += len(chunk)
            yield chunk

    finally:
        # Ensure file is always closed, even on exceptions
        file_object.close()


@never_cache
@require_http_methods(["GET", "POST"])
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
    except ObjectDoesNotExist:
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

    # Handle POST request (user confirmed access)
    if request.method == "POST":
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

    # Handle GET request - show confirmation page
    content = access_token.content
    return render(
        request,
        "larpmanager/event/onetime/confirm.html",
        {
            "content": content,
            "token": token,
        },
    )


@never_cache
@require_http_methods(["GET"])
def onetime_stream(request: HttpRequest, token: str) -> StreamingHttpResponse:
    """
    Stream the media file for a one-time content with range request support.

    This endpoint is called by video players to stream protected content files.
    Supports HTTP range requests for video seeking and handles security headers
    to prevent caching and unauthorized access.

    Args:
        request: The HTTP request object containing headers and metadata
        token: The one-time access token string for content authentication

    Returns:
        StreamingHttpResponse: HTTP response with file content stream

    Raises:
        Http404: If token is invalid, not initialized, content inactive, or file not found
    """
    content, file = _onetime_prepare(token)

    # Get total file size for response headers
    file_size = content.file.size

    # Parse HTTP Range header for partial content requests (video seeking)
    range_header = request.META.get("HTTP_RANGE", "").strip()
    range_match: Optional[re.Match] = None
    if range_header:
        range_match = re.search(r"bytes=(\d+)-(\d*)", range_header)

    # Determine the correct content type for MP4 videos
    content_type = content.content_type
    if not content_type and content.file.name:
        filename_lower = content.file.name.lower()
        if filename_lower.endswith(".mp4"):
            content_type = "video/mp4"
        elif filename_lower.endswith(".webm"):
            content_type = "video/webm"
        elif filename_lower.endswith(".mp3"):
            content_type = "audio/mpeg"
        elif filename_lower.endswith(".ogg"):
            content_type = "audio/ogg"
        else:
            content_type = "application/octet-stream"

    # Handle partial content request (HTTP 206) for range requests
    if range_match:
        first_byte = int(range_match.group(1))
        last_byte = int(range_match.group(2)) if range_match.group(2) else file_size - 1

        # Validate range
        if first_byte >= file_size or last_byte >= file_size or first_byte > last_byte:
            file.close()
            response = StreamingHttpResponse(status=416)  # Range Not Satisfiable
            response["Content-Range"] = f"bytes */{file_size}"
            return response

        length = last_byte - first_byte + 1

        # Create partial content response with appropriate headers
        response = StreamingHttpResponse(
            file_iterator(file, chunk_size=8192 * 16, start_pos=first_byte, max_length=length),
            status=206,
            content_type=content_type,
        )
        response["Content-Length"] = str(length)
        response["Content-Range"] = f"bytes {first_byte}-{last_byte}/{file_size}"
    else:
        # Handle full file request (HTTP 200)
        response = StreamingHttpResponse(
            file_iterator(file, chunk_size=8192 * 16, start_pos=0),
            content_type=content_type,
        )
        response["Content-Length"] = str(file_size)

    # Apply headers optimized for video streaming
    response["Cache-Control"] = "private"  # Allow browser caching for better streaming
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["Accept-Ranges"] = "bytes"

    # Add CORS headers for video streaming
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET"
    response["Access-Control-Allow-Headers"] = "Range"

    # Ensure proper content-encoding for video
    response["X-Content-Type-Options"] = "nosniff"

    # Set content disposition header with original filename
    filename = os.path.basename(content.file.name)
    response["Content-Disposition"] = f'inline; filename="{filename}"'

    return response


def _onetime_prepare(token):
    max_time_use = 3600  # 3600 seconds = 1 hour
    # Validate and retrieve the access token with related content
    try:
        access_token = OneTimeAccessToken.objects.select_related("content").get(token=token)
    except ObjectDoesNotExist as err:
        raise Http404(_("Invalid token")) from err
    # Verify token has been properly initialized
    if not access_token.used:
        raise Http404(_("Token not initialized"))
    # Verify token was used within the last hour
    if access_token.used_at:
        time_since_used = timezone.now() - access_token.used_at
        if time_since_used.total_seconds() > max_time_use:
            raise Http404(_("Token expired"))
    # Ensure the content is still active and available
    if not access_token.content.active:
        raise Http404(_("Content unavailable"))
    content = access_token.content
    # Open the file in binary read mode for streaming
    try:
        file = content.file.open("rb")
    except Exception as err:
        raise Http404(_("File not found")) from err
    return content, file
