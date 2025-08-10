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

from django.contrib.auth.decorators import login_required
from django.http import Http404

from larpmanager.utils.character import get_char_check
from larpmanager.utils.event import get_event_run
from larpmanager.utils.pdf import (
    print_character,
    print_character_friendly,
    print_character_rel,
    print_gallery,
    print_profiles,
)


def check_print_pdf(ctx):
    if "show_addit" not in ctx or "print_pdf" not in ctx["show_addit"]:
        raise Http404("not ready")


@login_required
def character_pdf_sheet(request, s, n, num):
    ctx = get_event_run(request, s, n, signup=True)

    check_print_pdf(ctx)
    get_char_check(request, ctx, num, True)
    return print_character(ctx)


@login_required
def character_pdf_sheet_friendly(request, s, n, num):
    ctx = get_event_run(request, s, n, signup=True)
    check_print_pdf(ctx)
    get_char_check(request, ctx, num, True)
    return print_character_friendly(ctx)


@login_required
def character_pdf_relationships(request, s, n, num):
    ctx = get_event_run(request, s, n, signup=True)
    check_print_pdf(ctx)
    get_char_check(request, ctx, num, True)
    return print_character_rel(ctx)


@login_required
def portraits(request, s, n):
    ctx = get_event_run(request, s, n, signup=True)
    return print_gallery(ctx)


@login_required
def profiles(request, s, n):
    ctx = get_event_run(request, s, n, signup=True)
    return print_profiles(ctx)
