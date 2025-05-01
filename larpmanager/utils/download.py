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

import csv

from bs4 import BeautifulSoup
from django.http import HttpResponse

from larpmanager.cache.character import get_event_cache_all, get_event_cache_fields
from larpmanager.models.form import CharacterQuestion, get_ordered_registration_questions
from larpmanager.utils.common import check_field


def writing_download(request, ctx, typ, nm):
    response, writer = get_writer(ctx, nm)

    query = typ.objects.all()
    # fields = typ._meta.get_fields()

    get_event_cache_all(ctx)

    res = None
    if nm == "character" and "character_form" in ctx["features"]:
        res = {"chars": {}}
        get_event_cache_fields(ctx, res, only_visible=False)

    if check_field(typ, "event"):
        query = query.filter(event=ctx["event"])
    elif check_field(typ, "run"):
        query = query.filter(run=ctx["run"])

    if check_field(typ, "number"):
        query = query.order_by("number")

    first = True
    key = []
    for el in query:
        val = []
        for k, v in el.show_complete().items():
            if k in [
                "id",
                "show",
                "owner_id",
                "owner",
                "player",
                "player_full",
                "player_id",
                "first_aid",
                "player_prof",
                "profile",
                "cover",
                "thumb",
            ]:
                continue

            if k.startswith("custom_"):
                continue

            if k in ["title", "motto", "role", "special", "gender", "keywords", "safety", "preview"]:
                if k not in ctx["features"]:
                    continue

            if k == "factions":
                if "faction" not in ctx["features"]:
                    continue

                aux = [ctx["factions"][int(el)]["name"] for el in v]
                v = ", ".join(aux)

            soup = BeautifulSoup(str(v), features="lxml")
            val.append(soup.get_text("\n").replace("\n", " "))
            if first:
                key.append(k)

        # Add character question and answers
        if res:
            for idq, question in ctx["questions"].items():
                if first:
                    key.append(question["display"])

                v = ""
                if el.number in res["chars"]:
                    if idq in res["chars"][el.number]["fields"]:
                        v = res["chars"][el.number]["fields"][idq]
                        if not isinstance(v, str):
                            v = ", ".join([ctx["options"][ido]["display"] for ido in v])
                val.append(str(v))

        if first:
            writer.writerow(key)
            first = False

        writer.writerow(val)

    return response


def get_writer(ctx, nm):
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="{}-{}.csv"'.format(ctx["event"], nm)},
    )
    writer = csv.writer(response, delimiter="\t")
    return response, writer


def orga_registration_form_download(request, ctx):
    response, writer = get_writer(ctx, "Registration form")
    writer.writerow(["typ", "display", "description", "status", "options"])

    que = get_ordered_registration_questions(ctx)
    for el in que:
        options = el.options.all()
        row = [el.typ, el.display, el.description, el.status, len(options)]
        for opt in options:
            row.extend([opt.display, opt.details, opt.price, opt.max_available])
        writer.writerow(row)

    return response


def orga_character_form_download(request, ctx):
    response, writer = get_writer(ctx, "Registration form")
    writer.writerow(["typ", "display", "description", "status", "visibility", "options"])

    que = ctx["event"].get_elements(CharacterQuestion).order_by("order").prefetch_related("options")
    for el in que:
        options = el.options.order_by("order")
        row = [el.typ, el.display, el.description, el.status, el.visibility, len(options)]
        for opt in options:
            dependents = ",".join(opt.dependents.values_list("display", flat=True))
            tickets = ",".join(opt.tickets.values_list("name", flat=True))
            row.extend([opt.display, opt.details, opt.max_available, dependents, tickets])
        writer.writerow(row)

    return response
