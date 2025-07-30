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

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from larpmanager.forms.event import EventCharactersPdfForm
from larpmanager.models.event import Run
from larpmanager.models.writing import (
    Character,
)
from larpmanager.utils.character import get_char_check, get_character_relationships, get_character_sheet
from larpmanager.utils.event import check_event_permission
from larpmanager.utils.pdf import (
    add_pdf_instructions,
    print_character,
    print_character_bkg,
    print_character_friendly,
    print_character_rel,
    print_gallery,
    print_profiles,
)


@login_required
def orga_characters_pdf(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    if request.method == "POST":
        form = EventCharactersPdfForm(request.POST, request.FILES, instance=ctx["event"])
        if form.is_valid():
            form.save()
            messages.success(request, _("Updated") + "!")
            return redirect(request.path_info)
    else:
        form = EventCharactersPdfForm(instance=ctx["event"])
    ctx["list"] = ctx["event"].get_elements(Character).order_by("number")
    ctx["form"] = form
    return render(request, "larpmanager/orga/characters/pdf.html", ctx)


@login_required
def orga_pdf_regenerate(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    chs = ctx["event"].get_elements(Character)
    for run in Run.objects.filter(event=ctx["event"], end__gte=datetime.now()):
        for ch in chs:
            print_character_bkg(ctx["event"].assoc.slug, ctx["event"].slug, run.number, ch.number)
    messages.success(request, _("Regeneration pdf started") + "!")
    return redirect("orga_characters_pdf", s=ctx["event"].slug, n=ctx["run"].number)


@login_required
def orga_characters_sheet_pdf(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    get_char_check(request, ctx, num, True)
    return print_character(ctx, True)


@login_required
def orga_characters_sheet_test(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    get_char_check(request, ctx, num, True)
    ctx["pdf"] = True
    get_character_sheet(ctx)
    add_pdf_instructions(ctx)
    return render(request, "pdf/sheets/auxiliary.html", ctx)


@login_required
def orga_characters_friendly_pdf(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    get_char_check(request, ctx, num, True)
    return print_character_friendly(ctx, True)


@login_required
def orga_characters_friendly_test(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    get_char_check(request, ctx, num, True)
    get_character_sheet(ctx)
    return render(request, "pdf/sheets/friendly.html", ctx)


@login_required
def orga_characters_relationships_pdf(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    get_char_check(request, ctx, num, False, True)
    return print_character_rel(ctx, True)


@login_required
def orga_characters_relationships_test(request, s, n, num):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    get_char_check(request, ctx, num, True)
    get_character_sheet(ctx)
    get_character_relationships(ctx)
    return render(request, "pdf/sheets/relationships.html", ctx)


@login_required
def orga_gallery_pdf(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    return print_gallery(ctx, True)


@login_required
def orga_gallery_test(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    return render(request, "pdf/sheets/gallery.html", ctx)


@login_required
def orga_profiles_pdf(request, s, n):
    ctx = check_event_permission(request, s, n, "orga_characters_pdf")
    return print_profiles(ctx, True)
