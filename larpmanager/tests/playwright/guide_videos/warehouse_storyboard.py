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

"""Guide video: store props in numbered boxes on shelves, assign them to event areas and load them."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.core.files import File
from PIL import Image, ImageDraw
from playwright.sync_api import expect

from larpmanager.models.association import Association
from larpmanager.models.event import Event, Run
from larpmanager.models.miscellanea import (
    WarehouseArea,
    WarehouseContainer,
    WarehouseItem,
    WarehouseItemAssignment,
    WarehouseTag,
)
from larpmanager.tests.playwright.guide_videos.helpers import (
    CONFIRM,
    feature_checkbox,
    open_menu,
    open_new,
    save_modal,
)
from larpmanager.tests.utils import login_orga

if TYPE_CHECKING:
    from typing import Any

    from larpmanager.tests.playwright.guide_videos.director import Director

pytestmark = pytest.mark.e2e

TITLE = "Inventory"
PACE = 0.8

ORGANIZATION = "Ravenhold Larp"
EVENT = "The Siege of Ravenhold"
PHOTO_DIR = Path(".guide_videos/warehouse_photos")

# Boxes created on camera, then the rest of the shelves, by box number
FIRST_BOX = ("Box 12", "Shelf A, height 3", "Lighting and candles")
SECOND_BOX = ("Box 21", "Shelf B, height 2", "Flags and banners")
OTHER_BOXES = (
    ("Box 15", "Shelf A, height 1", "Cooking gear"),
    ("Box 34", "Shelf C, height 4", "Tableware"),
)
TAGS = ("Lighting", "Decor", "Kitchen")

# Item created on camera: name, description, box, tag, quantity owned
LANTERN = ("Iron lantern", "Oil lantern with hanging hook", "Box 12", "Lighting", "10")
# Items already in the warehouse: name, description, box, tag, quantity owned
OTHER_ITEMS = (
    ("Tavern banner", "Red banner with the raven crest", "Box 21", "Decor", 2),
    ("Copper cauldron", "Large pot for the camp fire", "Box 15", "Kitchen", 1),
    ("Pewter mugs", "Tin mugs for the tavern", "Box 34", "Kitchen", 24),
    ("Beeswax candles", "Long-burning table candles", "Box 12", "Lighting", 30),
)
# Props already assigned to the camp, with their quantity
CAMP_ITEMS = (("Copper cauldron", 1), ("Beeswax candles", 10), ("Iron lantern", 4))
# Props assigned to the tavern on camera, with their quantity
TAVERN_ITEMS = (("Pewter mugs", "20"), ("Tavern banner", "1"))
LANTERN_AVAILABLE = "6"
TAVERN = ("Tavern", "Main hall", "Where players eat and trade")
CAMP = ("Camp", "Meadow by the river", "Outdoor camp of the rebels")
LANTERN_NOTE = "One on each table"


def prepare_data() -> None:
    """Rename test labels and add the tags of the warehouse."""
    association = Association.objects.get()
    association.name = ORGANIZATION
    association.save()
    event = Event.objects.get(slug="test")
    event.name = EVENT
    event.save()
    for run in Run.objects.filter(event=event):
        run.save()
    for name in TAGS:
        WarehouseTag.objects.create(name=name, association=association)


def _draw(name: str) -> Image.Image:
    """Draw a simple illustration of a prop on a warm background."""
    image = Image.new("RGB", (600, 600), "#e9dcc3")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 470, 600, 600), fill="#b99b6b")
    if name == "Iron lantern":
        draw.arc((230, 60, 370, 200), 180, 360, fill="#3b3b3b", width=14)
        draw.polygon([(200, 130), (400, 130), (370, 170), (230, 170)], fill="#3b3b3b")
        draw.rectangle((240, 170, 360, 400), fill="#ffd36b", outline="#3b3b3b", width=14)
        draw.ellipse((270, 230, 330, 330), fill="#ff9f1c")
        draw.line((300, 170, 300, 400), fill="#3b3b3b", width=8)
        draw.rectangle((210, 400, 390, 450), fill="#3b3b3b")
    elif name == "Tavern banner":
        draw.line((150, 60, 150, 500), fill="#5a3b1e", width=16)
        draw.polygon([(160, 80), (460, 80), (460, 400), (310, 340), (160, 400)], fill="#a4161a")
        draw.ellipse((250, 140, 370, 260), fill="#1b1b1b")
        draw.polygon([(300, 170), (350, 200), (300, 230), (270, 200)], fill="#e9dcc3")
    elif name == "Copper cauldron":
        draw.line((170, 440, 140, 520), fill="#3b3b3b", width=14)
        draw.line((430, 440, 460, 520), fill="#3b3b3b", width=14)
        draw.arc((160, 120, 440, 300), 180, 360, fill="#3b3b3b", width=10)
        draw.ellipse((120, 200, 480, 480), fill="#b87333", outline="#7a4a1f", width=10)
        draw.ellipse((150, 190, 450, 260), fill="#7a4a1f")
    elif name == "Pewter mugs":
        for left in (90, 330):
            draw.rectangle((left, 220, left + 170, 450), fill="#9ea3a8", outline="#5d6166", width=10)
            draw.arc((left + 140, 260, left + 230, 380), 270, 90, fill="#5d6166", width=16)
            draw.ellipse((left, 200, left + 170, 240), fill="#c9cdd1", outline="#5d6166", width=8)
    else:
        for index, left in enumerate((150, 260, 370)):
            top = 200 + index % 2 * 60
            draw.rectangle((left, top, left + 70, 460), fill="#fff3c4", outline="#c9a227", width=6)
            draw.line((left + 35, top, left + 35, top - 25), fill="#3b3b3b", width=5)
            draw.ellipse((left + 15, top - 85, left + 55, top - 25), fill="#ff9f1c")
    return image


def demo_photo(name: str) -> Path:
    """Return the photo of a prop, drawing it once."""
    path = PHOTO_DIR / f"{name.lower().replace(' ', '_')}.jpg"
    if not path.exists():
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        _draw(name).save(path, quality=90)
    return path


def add_boxes() -> None:
    """Add the other boxes of the shelves."""
    association = Association.objects.get()
    for name, position, description in OTHER_BOXES:
        WarehouseContainer.objects.create(
            name=name, position=position, description=description, association=association
        )


def add_items() -> None:
    """Add the other props of the warehouse, each with its photo."""
    association = Association.objects.get()
    for name, description, box, tag, quantity in OTHER_ITEMS:
        item = WarehouseItem.objects.create(
            name=name,
            description=description,
            quantity=quantity,
            container=WarehouseContainer.objects.get(name=box),
            association=association,
        )
        item.tags.add(WarehouseTag.objects.get(name=tag))
        with demo_photo(name).open("rb") as photo:
            item.photo.save(f"{name}.jpg", File(photo))


def add_camp() -> None:
    """Add the second area of the event, with its props."""
    event = Event.objects.get(slug="test")
    name, position, description = CAMP
    camp = WarehouseArea.objects.create(name=name, position=position, description=description, event=event)
    for item, quantity in CAMP_ITEMS:
        WarehouseItemAssignment.objects.create(
            item=WarehouseItem.objects.get(name=item), area=camp, event=event, quantity=quantity
        )


def pick(director: Director, modal: Any, field: str, search: str, option: str) -> None:
    """Search and choose an option of a select2 field, single or multiple."""
    if "multiple" in field:
        director.type(modal.locator(f"{field} .select2-search__field"), search)
    else:
        director.click(modal.locator(field))
        director.type(modal.locator(".select2-dropdown .select2-search__field"), search)
    director.click(modal.locator(".select2-results__option", has_text=option).first)


def is_assignment_save(response: Any) -> bool:
    """Tell whether a response is the autosave of an item assignment."""
    return response.request.method == "POST" and "assignment" in response.url


def manifest_row(page: Any, item: str, area: str = TAVERN[0]) -> Any:
    """Return the row of an item in an area of the manifest."""
    return page.locator("#inv_manifest tbody tr", has_text=item).filter(has_text=area)


def test_warehouse_video(director: Director) -> None:
    """Record the organizer storing props and loading them for an event."""
    page = director.page
    prepare_data()
    login_orga(page, director.base_url)
    director.goto("/manage/features/")
    director.start()

    director.step("Step 1: turn on the warehouse")
    director.say("In the organization features, turn on Warehouse")
    director.check(feature_checkbox(page, "Warehouse"))
    director.say("The warehouse is shared by every event of the organization")
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)
    director.say("Turn on quantities to count how many of each prop you own")
    open_menu(director, "Configuration")
    director.click(page.locator("#main_form").get_by_role("link", name="Warehouse", exact=True))
    director.check(page.locator("#id_warehouse_quantity"))
    director.confirm(page.get_by_role("button", name=CONFIRM), settle=1.0)

    director.step("Step 2: number your boxes")
    director.say("Each container is a box: write its number on it")
    open_menu(director, "Containers")
    modal = open_new(director)
    name, position, description = FIRST_BOX
    director.type(modal.locator("#id_name"), name)
    director.say("Note where it sits: which shelf, at which height")
    director.type(modal.locator("#id_position"), position)
    director.fill(modal.locator("#id_description"), description)
    save_modal(director, modal)
    director.say("Add a container for every box on your shelves")
    modal = open_new(director)
    name, position, description = SECOND_BOX
    director.fill(modal.locator("#id_name"), name)
    director.fill(modal.locator("#id_position"), position)
    director.fill(modal.locator("#id_description"), description)
    save_modal(director, modal)
    with director.off_camera():
        add_boxes()
        page.reload()
    containers = page.locator("#inv_containers tbody")
    expect(containers).to_contain_text("Box 34")
    director.spotlight(containers, 2.5)

    director.step("Step 3: add items with a photo")
    director.say("Now list the props stored in each box")
    open_menu(director, "Items")
    modal = open_new(director)
    name, description, box, tag, quantity = LANTERN
    director.type(modal.locator("#id_name"), name)
    director.fill(modal.locator("#id_description"), description)
    director.say("Quantity is how many you own in total")
    director.type(modal.locator("#id_quantity"), quantity)
    director.say("Choose the box it is stored in")
    pick(director, modal, "#select2-id_container-container", box[-2:], box)
    director.say("Tags group similar props, such as all the lighting")
    pick(director, modal, ".select2-selection--multiple", tag[:4], tag)
    director.say("A photo helps whoever packs or unpacks the box")
    director.upload(modal.locator("#id_photo"), demo_photo(name))
    save_modal(director, modal)
    with director.off_camera():
        add_items()
        page.reload()
    lantern = page.locator("tr", has_text=LANTERN[0])
    expect(lantern.locator("img.inv_photo")).to_be_visible()
    director.spotlight(lantern, 2.5)

    director.step("Step 4: create the event areas")
    director.say("Areas are the places of the event where props are set up")
    director.click(page.locator("#topbar").get_by_role("link", name=EVENT, exact=True), settle=0.8)
    open_menu(director, "Area")
    modal = open_new(director)
    name, position, description = TAVERN
    director.type(modal.locator("#id_name"), name)
    director.type(modal.locator("#id_position"), position)
    director.fill(modal.locator("#id_description"), description)
    save_modal(director, modal)
    with director.off_camera():
        add_camp()
        page.reload()
    expect(page.locator("#one")).to_contain_text(CAMP[0])
    director.hold(1.0)

    director.step("Step 5: assign the props to each area")
    director.say("Open the item assignments of the tavern")
    tavern = page.locator("tr", has_text=TAVERN[0])
    director.click(tavern.get_by_role("link", name="Item assignments"), settle=1.0)
    lantern = page.locator("tr", has_text=LANTERN[0])
    available = lantern.locator("td").nth(7)
    expect(available).to_have_text(LANTERN_AVAILABLE)
    director.say("Available leaves out what other areas already took")
    director.spotlight(available, 2.5)
    director.say("Type how many the tavern needs, with a note for the crew")
    with page.expect_response(is_assignment_save):
        director.type(lantern.locator("td.quantity input"), LANTERN_AVAILABLE)
    with page.expect_response(is_assignment_save):
        director.type(lantern.locator("textarea"), LANTERN_NOTE)
    for item, quantity in TAVERN_ITEMS:
        with page.expect_response(is_assignment_save):
            director.type(page.locator("tr", has_text=item).locator("td.quantity input"), quantity)
    director.hold(1.5)

    director.step("Step 6: load the boxes from the manifest")
    director.say("The manifest lists every prop of the event, with how many to bring")
    open_menu(director, "Manifest")
    container_header = page.locator(".dt-scroll-head th").filter(has_text="Container").locator(".dtcc-button_order")
    director.spotlight(manifest_row(page, LANTERN[0]).locator("td", has_text=FIRST_BOX[0]), 2.5)
    director.say("Each line tells which box to pull, and from which shelf")
    director.hold(2.0)
    quantity = manifest_row(page, LANTERN[0]).locator("td").nth(6)
    expect(quantity).to_have_text(LANTERN_AVAILABLE)
    director.say("...and how many to take out of it")
    director.spotlight(quantity, 2.0)
    director.say("Sort by container to walk the shelves box by box")
    director.click(container_header)
    expect(page.locator("#inv_manifest tbody tr").first).to_contain_text("Box 12")
    expect(page.locator("#inv_manifest tbody tr").last).to_contain_text("Box 34")
    director.hold(1.5)
    director.say("Mark each prop as loaded when it goes on the van")
    for item, area in (("Beeswax candles", CAMP[0]), (LANTERN[0], TAVERN[0]), (LANTERN[0], CAMP[0])):
        loaded = manifest_row(page, item, area).locator("td.ajax-toggle[tp='load']")
        director.click(loaded)
        expect(loaded.locator("span.value")).to_be_visible()
    director.hold(1.0)

    director.step("Step 7: check what is set up on site")
    director.say("On site, mark each prop as deployed in its area")
    deployed = manifest_row(page, LANTERN[0]).locator("td.ajax-toggle[tp='depl']")
    director.click(deployed)
    expect(deployed.locator("span.value")).to_be_visible()
    assignment = WarehouseItemAssignment.objects.get(item__name=LANTERN[0], area__name=TAVERN[0])
    assert assignment.loaded
    assert assignment.deployed
    assert assignment.notes == LANTERN_NOTE
    assert assignment.quantity == int(LANTERN_AVAILABLE)
    director.say("Loaded and deployed: nothing gets left behind")
    director.spotlight(manifest_row(page, LANTERN[0]), 3.5)

    director.stop()
