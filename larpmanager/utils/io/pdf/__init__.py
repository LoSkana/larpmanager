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

from larpmanager.utils.io.pdf.bulk import (
    build_friendly_bundle_bkg,
    get_friendly_bundle_filepath,
    print_all_friendly,
    print_bulk,
)
from larpmanager.utils.io.pdf.cleanup import (
    cleanup_character_pdfs_on_save,
    cleanup_faction_pdfs_on_save,
    cleanup_handout_pdfs_after_save,
    cleanup_handout_template_pdfs_after_save,
    cleanup_pdfs_on_trait_assignment,
    cleanup_relationship_pdfs_after_save,
    deactivate_castings_and_remove_pdfs,
    delete_character_pdf_files,
    get_trait_character,
)
from larpmanager.utils.io.pdf.engine import (
    add_pdf_instructions,
    fix_filename,
    has_pdf_customization,
    link_callback,
    reprint,
    return_pdf,
    xhtml_pdf,
)
from larpmanager.utils.io.pdf.receipts import generate_payment_receipt
from larpmanager.utils.io.pdf.sheets import (
    _get_character_pdf_data,
    get_membership_request,
    print_character,
    print_character_friendly,
    print_faction,
    print_gallery,
    print_handout,
    print_profiles,
    print_volunteer_registry,
)
from larpmanager.utils.io.pdf.tasks import (
    get_fake_request,
    print_character_bkg,
    print_character_go,
    print_handout_bkg,
    print_handout_go,
    print_run_bkg,
)

__all__ = [
    "_get_character_pdf_data",
    "add_pdf_instructions",
    "build_friendly_bundle_bkg",
    "cleanup_character_pdfs_on_save",
    "cleanup_faction_pdfs_on_save",
    "cleanup_handout_pdfs_after_save",
    "cleanup_handout_template_pdfs_after_save",
    "cleanup_pdfs_on_trait_assignment",
    "cleanup_relationship_pdfs_after_save",
    "deactivate_castings_and_remove_pdfs",
    "delete_character_pdf_files",
    "fix_filename",
    "generate_payment_receipt",
    "get_fake_request",
    "get_friendly_bundle_filepath",
    "get_membership_request",
    "get_trait_character",
    "has_pdf_customization",
    "link_callback",
    "print_all_friendly",
    "print_bulk",
    "print_character",
    "print_character_bkg",
    "print_character_friendly",
    "print_character_go",
    "print_faction",
    "print_gallery",
    "print_handout",
    "print_handout_bkg",
    "print_handout_go",
    "print_profiles",
    "print_run_bkg",
    "print_volunteer_registry",
    "reprint",
    "return_pdf",
    "xhtml_pdf",
]
