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
"""Media filesystem paths for events, runs and characters.

Paths are derived from cached scalar fields (slug, number, media_token) rather
than the full Event/Run objects, so callers that only need a path don't have
to load (or join through) those rows.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings as conf_settings

from larpmanager.cache.basic import get_event_basic_cache, get_run_basic_cache


def get_event_media_filepath(event_id: int) -> str:
    """Get the media directory path for an event's PDFs, creating it if needed."""
    slug = get_event_basic_cache(event_id)["slug"]
    pdf_directory_path = str(Path(conf_settings.MEDIA_ROOT) / f"pdf/{slug}/")
    Path(pdf_directory_path).mkdir(mode=0o770, parents=True, exist_ok=True)
    return pdf_directory_path


def get_run_media_filepath(run_id: int) -> str:
    """Get the media directory path for a run's PDFs, creating it if needed."""
    info = get_run_basic_cache(run_id)
    run_media_path = str(Path(get_event_media_filepath(info["event_id"])) / f"{info['number']}-{info['media_token']}/")
    Path(run_media_path).mkdir(mode=0o770, parents=True, exist_ok=True)
    return run_media_path


def get_run_gallery_filepath(run_id: int) -> str:
    """Get the file path for a run's gallery PDF."""
    return get_run_media_filepath(run_id) + "gallery.pdf"


def get_run_profiles_filepath(run_id: int) -> str:
    """Get the file path for a run's profiles PDF."""
    return get_run_media_filepath(run_id) + "profiles.pdf"


def get_character_filepath(run_id: int) -> str:
    """Get the directory path for storing character files for a given run."""
    directory_path = str(Path(get_run_media_filepath(run_id)) / "characters/")
    Path(directory_path).mkdir(mode=0o770, parents=True, exist_ok=True)
    return directory_path


def get_character_media_filepath(run_id: int, character_number: int, media_token: str, descr: str) -> str:
    """Get the path to a character's PDF file for a given run."""
    character_directory = get_character_filepath(run_id)
    return str(Path(character_directory) / f"{character_number}-{media_token}-{descr}.pdf")


def get_faction_filepath(run_id: int) -> str:
    """Get the directory path for storing faction PDF files for a given run."""
    directory_path = str(Path(get_run_media_filepath(run_id)) / "factions/")
    Path(directory_path).mkdir(mode=0o770, parents=True, exist_ok=True)
    return directory_path


def get_faction_media_filepath(run_id: int, faction_number: int, media_token: str) -> str:
    """Get the complete file path for a faction's PDF sheet."""
    return str(Path(get_faction_filepath(run_id)) / f"{faction_number}-{media_token}.pdf")


def get_handout_media_filepath(event_id: int, handout_number: int, media_token: str) -> str:
    """Get the file path for a handout's PDF within the event's media directory."""
    handouts_directory = str(Path(get_event_media_filepath(event_id)) / "handouts")
    Path(handouts_directory).mkdir(mode=0o770, parents=True, exist_ok=True)
    return str(Path(handouts_directory) / f"{handout_number}-{media_token}.pdf")
