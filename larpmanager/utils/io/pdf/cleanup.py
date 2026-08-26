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

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from larpmanager.cache.media import (
    get_character_media_filepath,
    get_handout_media_filepath,
    get_run_gallery_filepath,
    get_run_profiles_filepath,
)
from larpmanager.cache.run import get_event_run_ids
from larpmanager.models.casting import AssignmentTrait, Casting, Trait
from larpmanager.models.registration import RegistrationCharacterRel

if TYPE_CHECKING:
    from larpmanager.models.event import Run
    from larpmanager.models.writing import Character


def cleanup_handout_pdfs_after_save(instance: object) -> None:
    """Handle handout post-save PDF cleanup."""
    safe_remove(get_handout_media_filepath(instance.event_id, instance.number, instance.media_token))


def cleanup_handout_template_pdfs_after_save(instance: object) -> None:
    """Handle handout template post-save PDF cleanup."""
    for el in instance.handouts.all():
        safe_remove(get_handout_media_filepath(instance.event_id, el.number, el.media_token))


def safe_remove(file_path: str) -> None:
    """Remove a file, ignoring if it doesn't exist."""
    with contextlib.suppress(FileNotFoundError):
        Path(file_path).unlink()


def remove_run_pdf(event_id: int) -> None:
    """Remove PDF files for all runs associated with the event."""
    for run_id in get_event_run_ids(event_id):
        # Remove profiles and gallery PDFs for each run
        safe_remove(get_run_profiles_filepath(run_id))
        safe_remove(get_run_gallery_filepath(run_id))


def delete_character_pdf_files(
    instance: object, single_run_id: int | None = None, run_ids: list[int] | None = None
) -> None:
    """Delete PDF files for a character across specified runs.

    Args:
        instance: Character instance whose PDF files should be deleted
        single_run_id: Optional specific run id to delete files for
        run_ids: Optional run ids, defaults to all event runs

    """
    if run_ids is None:
        run_ids = get_event_run_ids(instance.event_id)

    for run_id in run_ids:
        if single_run_id and run_id != single_run_id:
            continue
        safe_remove(get_character_media_filepath(run_id, instance.number, instance.media_token, "full"))
        safe_remove(get_character_media_filepath(run_id, instance.number, instance.media_token, "light"))
        safe_remove(get_character_media_filepath(run_id, instance.number, instance.media_token, "rels"))


def cleanup_character_pdfs_on_save(instance: object) -> None:
    """Handle character post-save PDF cleanup."""
    remove_run_pdf(instance.event_id)
    delete_character_pdf_files(instance)


def cleanup_relationship_pdfs_after_save(instance: object) -> None:
    """Handle player relationship post-save PDF cleanup."""
    for el in instance.registration.rcrs.all():
        delete_character_pdf_files(el.character, instance.registration.run_id)


def cleanup_faction_pdfs_on_save(instance: object) -> None:
    """Handle faction post-save PDF cleanup."""
    run_ids = get_event_run_ids(instance.event_id)
    for char in instance.characters.all():
        delete_character_pdf_files(char, run_ids=run_ids)


def deactivate_castings_and_remove_pdfs(trait_instance: Any) -> None:
    """Deactivate castings and remove PDF files for a trait instance."""
    # Deactivate all matching castings for this member, run, and type
    for casting in Casting.objects.filter(member=trait_instance.member, run=trait_instance.run, typ=trait_instance.typ):
        casting.active = False
        casting.save()

    # Get character associated with this trait and remove PDF files
    character = get_trait_character(trait_instance.run, trait_instance.trait.number)
    if character:
        delete_character_pdf_files(character, trait_instance.run_id)


def cleanup_pdfs_on_trait_assignment(assignment_trait_instance: Any) -> None:
    """Handle assignment trait post-save PDF cleanup."""
    if not assignment_trait_instance.member:
        return

    deactivate_castings_and_remove_pdfs(assignment_trait_instance)


def clean_tag(tag: Any) -> Any:
    """Clean XML tag by removing namespace prefix."""
    closing_brace_index = tag.find("}")
    if closing_brace_index >= 0:
        tag = tag[closing_brace_index + 1 :]
    return tag


def replace_data(template_path: Any, character_data: Any) -> None:
    """Replace character data placeholders in template file.

    Args:
        template_path: Path to template file
        character_data: Character data dictionary with replacement values

    """
    with Path(template_path).open() as template_file:
        file_content = template_file.read()

    for placeholder_key in ["number", "name", "title"]:
        if placeholder_key not in character_data:
            continue
        file_content = file_content.replace(f"#{placeholder_key}#", str(character_data[placeholder_key]))

    # Write the file out again
    with Path(template_path).open("w") as template_file:
        template_file.write(file_content)


def get_trait_character(run: Run, number: int) -> Character | None:
    """Get the character assigned to a trait number in a specific run.

    Args:
        run: The Run instance to search in.
        number: The trait number to look for.

    Returns:
        The Character assigned to the trait, or None if not found.

    """
    try:
        # Find the trait by event and number
        trait = Trait.objects.get(event_id=run.event_id, number=number)

        # Get the member assigned to this trait in the run
        member = AssignmentTrait.objects.get(run=run, trait=trait).member

        # Find the character registered for this member in the run
        registration_character_rels = RegistrationCharacterRel.objects.filter(
            registration__run=run,
            registration__member=member,
        ).select_related("character")

        if not registration_character_rels.exists():
            return None
        return registration_character_rels.first().character
    except ObjectDoesNotExist:
        return None
