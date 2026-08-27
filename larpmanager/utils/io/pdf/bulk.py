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

import io
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings as conf_settings
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from larpmanager.cache.character import get_event_cache_all
from larpmanager.cache.media import get_run_gallery_filepath, get_run_profiles_filepath
from larpmanager.cache.writing import get_writing_element_fields
from larpmanager.models.form import QuestionApplicable
from larpmanager.models.writing import Character, Faction, Handout, get_event_elements
from larpmanager.utils.core.base import get_event_context
from larpmanager.utils.core.common import get_element, get_handout
from larpmanager.utils.core.exceptions import NotFoundError
from larpmanager.utils.io.pdf.engine import reprint
from larpmanager.utils.io.pdf.sheets import (
    print_character,
    print_character_friendly,
    print_faction,
    print_gallery,
    print_handout,
    print_profiles,
)
from larpmanager.utils.io.pdf.tasks import get_fake_request
from larpmanager.utils.larpmanager.tasks import background_auto
from larpmanager.utils.services.character import get_char_check

if TYPE_CHECKING:
    from larpmanager.models.event import Run


def print_bulk(context: dict, request: HttpRequest) -> HttpResponse:
    """Generate and return a ZIP file containing multiple PDFs based on user selection.

    This function creates an in-memory ZIP archive containing selected PDF files for
    an event run. Users can select from gallery, profiles, character sheets, faction
    sheets, and handouts via POST parameters. Each selected item is generated (if needed)
    and added to the ZIP file.

    The function delegates to specialized helper functions for each PDF type, each of
    which handles generation, caching, and error reporting independently.

    Args:
        context: Context dictionary containing:
            - 'run': The Run model instance
            - 'event': The Event model instance
            - Other data required by individual PDF generators
        request: HTTP request object with POST data indicating which PDFs to include.
            Expected POST parameters: 'gallery', 'profiles', 'character_{id}',
            'faction_{id}', 'handout_{id}'

    Returns:
        HttpResponse: ZIP file download response with timestamped filename in format:
            {run_slug}_pdfs_{YYYYMMDD_HHMMSS}.zip

    Side Effects:
        - Generates PDF files in the media directory as needed
        - Displays warning messages to user for any failed PDF generations

    """
    # Create in-memory zip file buffer for PDF collection
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # Process each PDF type via specialized helper functions
        _bulk_gallery(context, request, zip_file)
        _bulk_profiles(context, request, zip_file)
        _bulk_characters(context, request, zip_file)
        _bulk_factions(context, request, zip_file)
        _handle_handouts(context, request, zip_file)

    # Prepare ZIP file for download
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")

    # Generate timestamped filename for download
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    response["Content-Disposition"] = f'attachment; filename="{context["run"].get_slug()}_pdfs_{timestamp}.zip"'

    return response


def get_friendly_bundle_filepath(run: Run) -> Path:
    """Return the filesystem path for the pre-built printable bundle ZIP."""
    return Path(conf_settings.MEDIA_ROOT) / "bundles" / f"{run.media_token}_printable.zip"


@background_auto(queue="pdf", skip_duplicates=True)
def build_friendly_bundle_bkg(association_slug: str, event_slug: str) -> None:
    """Build printable character sheet ZIP bundle in the background and save to disk."""
    request = get_fake_request(association_slug)
    if request is None:
        return
    context = get_event_context(request, event_slug, check_visibility=False)
    run = context["run"]

    zip_path = get_friendly_bundle_filepath(run)
    zip_path.parent.mkdir(mode=0o770, parents=True, exist_ok=True)
    zip_path_tmp = zip_path.with_suffix(".tmp")

    try:
        with zipfile.ZipFile(zip_path_tmp, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for character in get_event_elements(context["event"].id, Character, context=context):
                try:
                    get_char_check(request, context, character.uuid, bypass_access_checks=True)
                    filepath = context["character"].get_sheet_friendly_filepath(run)

                    if not Path(filepath).exists():
                        print_character_friendly(context, force=True)

                    if Path(filepath).exists():
                        zip_file.write(filepath, f"character_{character.number}_{character.name}.pdf")
                except (Http404, NotFoundError):
                    pass
                except Exception:  # noqa: BLE001, S110
                    pass
        zip_path_tmp.rename(zip_path)
    except Exception:
        zip_path_tmp.unlink(missing_ok=True)
        raise


def print_all_friendly(context: dict, request: HttpRequest) -> HttpResponse:
    """Generate a ZIP file containing printable character sheet PDFs for all characters.

    Args:
        context: Context dictionary containing event and run data
        request: HTTP request object used for character access checks and warnings

    Returns:
        HttpResponse: ZIP file download response with timestamped filename

    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for character in get_event_elements(context["event"].id, Character, context=context):
            try:
                get_char_check(request, context, character.uuid, deny_public=True)
                filepath = context["character"].get_sheet_friendly_filepath(context["run"])

                if not Path(filepath).exists() or reprint(filepath):
                    print_character_friendly(context, force=True)

                if Path(filepath).exists():
                    zip_file.write(filepath, f"character_{character.number}_{character.name}.pdf")
            except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error
                messages.warning(request, _("Failed to add character") + f" #{character.number}: {e}")

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    response["Content-Disposition"] = f'attachment; filename="{context["run"].get_slug()}_printable_{timestamp}.zip"'
    return response


def _handle_handouts(context: dict, request: HttpRequest, zip_file: zipfile.ZipFile) -> None:
    """Process and add handout PDFs to bulk ZIP file based on user selection.

    Iterates through all handouts for the event, generating PDFs for those selected
    in the POST request, and adding them to the ZIP archive with descriptive filenames.

    Args:
        context: Context dictionary with 'event' and 'run' data
        request: HTTP request with POST parameters like 'handout_{id}'
        zip_file: Open ZipFile object to write PDFs into

    Side Effects:
        - Generates handout PDF files if needed
        - Adds PDFs to zip_file
        - Displays warning messages for failed generations

    """
    # Iterate through all handouts in the event
    for handout in get_event_elements(context["event"].id, Handout, context=context):
        # Check if this handout was selected by user
        if request.POST.get(f"handout_{handout.id}"):
            try:
                # Load handout data into context
                get_handout(context, handout.number)
                filepath = context["handout"].get_filepath()

                # Generate PDF if it doesn't exist or is outdated
                if not Path(filepath).exists() or reprint(filepath):
                    print_handout(context, force=True)

                # Add to ZIP if generation succeeded
                if Path(filepath).exists():
                    zip_file.write(filepath, f"handout_{handout.number}_{handout.name}.pdf")
            except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error (Http404, NotFoundError, OSError, etc.)
                # Notify user of failure but continue processing other handouts
                messages.warning(request, _("Failed to add handout") + f" #{handout.number}: {e}")


def _bulk_factions(context: dict, request: HttpRequest, zip_file: zipfile.ZipFile) -> None:
    """Process and add faction sheet PDFs to bulk ZIP file based on user selection.

    Iterates through all factions for the event, generating faction sheets for those
    selected in the POST request, and adding them to the ZIP archive.

    Args:
        context: Context dictionary with 'event', 'run', and cache data
        request: HTTP request with POST parameters like 'faction_{id}'
        zip_file: Open ZipFile object to write PDFs into

    Side Effects:
        - Loads event cache and faction field data into context
        - Generates faction PDF files if needed
        - Adds PDFs to zip_file
        - Displays warning messages for failed generations

    """
    # Iterate through all factions in the event
    for faction in get_event_elements(context["event"].id, Faction, context=context):
        # Check if this faction was selected by user
        if request.POST.get(f"faction_{faction.id}"):
            try:
                # Load faction data into context
                get_element(context, faction.number, "faction", Faction)
                get_event_cache_all(context)

                # Verify faction exists in cache
                if faction.number in context["factions"]:
                    context["sheet_faction"] = context["factions"][faction.number]
                else:
                    # Skip if faction not found in cache
                    continue

                # Load custom faction fields for the sheet
                context["fact"] = get_writing_element_fields(
                    context,
                    "faction",
                    QuestionApplicable.FACTION,
                    context["faction"].id,
                    only_visible=True,
                )

                filepath = context["faction"].get_sheet_filepath(context["run"])

                # Generate PDF if it doesn't exist or is outdated
                if not Path(filepath).exists() or reprint(filepath):
                    print_faction(context, force=True)

                # Add to ZIP if generation succeeded
                if Path(filepath).exists():
                    zip_file.write(filepath, f"faction_{faction.number}_{faction.name}.pdf")
            except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error (Http404, NotFoundError, OSError, etc.)
                # Notify user of failure but continue processing other factions
                messages.warning(request, _("Failed to add faction") + f" #{faction.number}: {e}")


def _bulk_characters(context: dict, request: HttpRequest, zip_file: zipfile.ZipFile) -> None:
    """Process and add character sheet PDFs to bulk ZIP file based on user selection.

    Iterates through all characters for the event, generating character sheets for
    those selected in the POST request, and adding them to the ZIP archive.

    Args:
        context: Context dictionary with 'event' and 'run' data
        request: HTTP request with POST parameters like 'character_{id}'
        zip_file: Open ZipFile object to write PDFs into

    Side Effects:
        - Loads character data into context
        - Generates character PDF files if needed
        - Adds PDFs to zip_file
        - Displays warning messages for failed generations

    """
    # Iterate through all characters in the event
    for character in get_event_elements(context["event"].id, Character, context=context):
        # Check if this character was selected by user
        if request.POST.get(f"character_{character.id}"):
            try:
                # Load and validate character data
                get_char_check(request, context, character.uuid, deny_public=True)
                filepath = context["character"].get_sheet_filepath(context["run"])

                # Generate PDF if it doesn't exist or is outdated
                if not Path(filepath).exists() or reprint(filepath):
                    print_character(context, force=True)

                # Add to ZIP if generation succeeded
                if Path(filepath).exists():
                    zip_file.write(filepath, f"character_{character.number}_{character.name}.pdf")
            except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error (Http404, NotFoundError, OSError, etc.)
                # Notify user of failure but continue processing other characters
                messages.warning(request, _("Failed to add character") + f" #{character.number}: {e}")


def _bulk_profiles(context: dict, request: HttpRequest, zip_file: zipfile.ZipFile) -> None:
    """Add profiles PDF to bulk ZIP file if selected by user.

    Generates a profiles PDF containing information for all characters in the run
    if the 'profiles' POST parameter is present.

    Args:
        context: Context dictionary with 'run' data
        request: HTTP request with 'profiles' POST parameter
        zip_file: Open ZipFile object to write PDF into

    Side Effects:
        - Generates profiles PDF file if needed
        - Adds PDF to zip_file
        - Displays warning message if generation fails

    """
    # Check if profiles PDF was requested
    if request.POST.get("profiles"):
        try:
            filepath = get_run_profiles_filepath(context["run"].id)

            # Generate PDF if it doesn't exist or is outdated
            if not Path(filepath).exists() or reprint(filepath):
                print_profiles(context, force=True)

            # Add to ZIP if generation succeeded
            if Path(filepath).exists():
                zip_file.write(filepath, "profiles.pdf")
        except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error (Http404, NotFoundError, OSError, etc.)
            # Notify user of failure
            messages.warning(request, _("Failed to add profiles") + f": {e}")


def _bulk_gallery(context: dict, request: HttpRequest, zip_file: zipfile.ZipFile) -> None:
    """Add gallery PDF to bulk ZIP file if selected by user.

    Generates a gallery PDF containing character portraits if the 'gallery'
    POST parameter is present.

    Args:
        context: Context dictionary with 'run' data
        request: HTTP request with 'gallery' POST parameter
        zip_file: Open ZipFile object to write PDF into

    Side Effects:
        - Generates gallery PDF file if needed
        - Adds PDF to zip_file
        - Displays warning message if generation fails

    """
    # Check if gallery PDF was requested
    if request.POST.get("gallery"):
        try:
            filepath = get_run_gallery_filepath(context["run"].id)

            # Generate PDF if it doesn't exist or is outdated
            if not Path(filepath).exists() or reprint(filepath):
                print_gallery(context, force=True)

            # Add to ZIP if generation succeeded
            if Path(filepath).exists():
                zip_file.write(filepath, "gallery.pdf")
        except Exception as e:  # noqa: BLE001 - Batch operation must continue on any error (Http404, NotFoundError, OSError, etc.)
            # Notify user of failure
            messages.warning(request, _("Failed to add gallery") + f": {e}")
