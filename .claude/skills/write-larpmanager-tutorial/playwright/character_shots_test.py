"""Tutorial screenshots: characters, character sheet, creation, inventory, experience, ensemble (tutorials 170-215)."""

import pytest
from lm_shots import (
    ORGA,
    PLAYER,
    Shooter,
    activate,
    banner,
    content,
    menu,
    open_select,
    refresh,
    row,
    row_label,
    section,
    seed_base,
    seed_characters,
    seed_factions,
    seed_registrations,
    set_config,
)

from larpmanager.models.experience import AbilityExp, AbilityTypeExp, DeliveryExp, SystemExp
from larpmanager.models.form import WritingOption, WritingQuestion
from larpmanager.models.inventory import Inventory, InventoryTransfer, InventoryType, PoolBalance, PoolLabel, PoolType
from larpmanager.models.registration import RegistrationCharacterRel
from larpmanager.models.writing import Character, Relationship

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _real_editor(settings) -> None:
    settings.TINYMCE_DISABLED = False


def _world(sh: Shooter, *features: str) -> tuple[dict, list[Character]]:
    base = seed_base()
    activate(sh, "character", *features)
    characters = seed_characters(base["event"])
    seed_factions(base["event"], characters)
    seed_registrations(base["run"], base["members"], characters)
    return base, characters


def test_characters(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 170, "characters")
    base, characters = _world(sh, "faction", "relationships", "custom_character", "print_pdf")

    page = sh.goto(sh.page(ORGA), "test/manage/characters/new/?frame=1")
    sh.shot(1, [row(page, "id_name"), row(page, "id_text")], "New character form")

    page = sh.goto(sh.page(ORGA), "test/manage/config/writing/")
    sh.shot(2, section(page, "Characters"), "Characters configuration", max_height=520)

    set_config(base["event"], "writing_field_visibility", "True")
    page = sh.goto(sh.page(ORGA), "test/manage/event/?frame=1")
    sh.shot(3, row_label(page, "Characters"), "Character fields visible to players")
    set_config(base["event"], "writing_field_visibility", "")

    Character.objects.filter(pk=characters[1].pk).update(text="<p>Mira owes her position at court to #1.</p>")
    refresh()
    page = sh.goto(sh.page(ORGA), f"test/manage/characters/{characters[1].uuid}/edit/?frame=1")
    text_row = row(page, "id_text")
    text_row.locator("a.my_toggle").first.click()
    sh.shot(4, text_row, "Character reference in a text")

    Relationship.objects.get_or_create(
        source=characters[0], target=characters[1], defaults={"text": "<p>My most trusted advisor.</p>"}
    )
    refresh()
    page = sh.goto(sh.page(ORGA), f"test/manage/characters/{characters[0].uuid}/edit/?frame=1")
    heading = page.locator("h2", has_text="Relationships")
    sh.shot(9, [heading, page.locator("#form_relationships")], "Character relationships")

    page = sh.goto(sh.page(ORGA), "test/manage/config/custom_character/")
    sh.shot(11, section(page, "Character customisation"), "Character customisation configuration")

    set_config(base["event"], "custom_character_name", "True")
    page = sh.goto(sh.page(PLAYER), f"test/character/{characters[0].uuid}/")
    sh.shot(12, menu(page, "Aldric Vane", "Customize"), "Customize entry in the character menu")

    page = sh.goto(sh.page(ORGA), "test/manage/pdf/")
    sh.shot(13, [banner(page), content(page)], "PDF generation", max_height=600)

    page = sh.goto(sh.page(ORGA), "test/manage/check/")
    sh.shot(15, [banner(page), content(page)], "Consistency check", max_height=600)
    sh.close()


def test_character_form(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 190, "character-form")
    base, characters = _world(sh, "user_character", "progress")
    set_config(base["event"], "writing_title", "True")
    set_config(base["event"], "writing_assigned", "True")

    page = sh.goto(sh.page(ORGA), "test/manage/writing/character/form/new/?frame=1")
    sh.shot(1, page.locator("form table").first, "New character field", max_height=700)
    sh.shot(2, row(page, "id_status"), "Field status for character creation")

    question = WritingQuestion.objects.create(
        event=base["event"],
        typ="s",
        name="Origin",
        description="Where the character comes from",
        status="o",
        visibility="c",
        order=20,
        applicable="c",
    )
    for order, name in enumerate(["Emberfall", "Border villages", "Overseas"]):
        WritingOption.objects.create(event=base["event"], question=question, name=name, order=order)
    refresh()
    page = sh.goto(sh.page(ORGA), f"test/manage/writing/character/form/{question.uuid}/edit/?frame=1")
    sh.shot(3, page.locator(".inline-options-table").first, "Options of a character field")

    page = sh.goto(sh.page(ORGA), "test/manage/config/char_form/")
    sh.shot(4, section(page, "Character sheet"), "Character sheet configuration")

    Character.objects.filter(pk=characters[0].pk).update(title="the Heir")
    refresh()
    page = sh.goto(sh.page(PLAYER), "test/gallery/")
    sh.shot(6, page.locator(".gallery .el").first, "Character title in the gallery")

    page = sh.goto(sh.page(ORGA), "test/manage/characters/")
    sh.shot(10, page.locator(".orga-buttons").first, "Progress and assignment views")
    sh.close()


def test_character_creation(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 200, "character-creation")
    base, characters = _world(sh, "user_character", "player_relationships")
    set_config(base["event"], "user_character_max", "1")

    page = sh.goto(sh.page(ORGA), "test/manage/config/user_character/")
    sh.shot(1, section(page, "Character creation"), "Character creation configuration")

    newcomer = "giulia.serra@example.com"
    page = sh.goto(sh.page(newcomer), "test/")
    sh.shot(2, page.locator(".reg-banner").first, "Prompt to create a character")

    set_config(base["event"], "user_character_approval", "True")
    registration = base["run"].registrations.get(member__user__username=newcomer)
    created = Character.objects.create(
        event=base["event"],
        number=20,
        name="Wren Ashby",
        teaser="<p>A wandering bard.</p>",
        player=registration.member,
        status="c",
    )
    RegistrationCharacterRel.objects.create(registration=registration, character=created)
    refresh()
    page = sh.goto(sh.page(newcomer), f"test/character/{created.uuid}/")
    sh.shot(3, menu(page, "Wren Ashby", "Edit"), "Character entries in the menu")
    sh.shot(5, page.locator(".reg-banner").first, "Prompt to propose the character")

    page = sh.goto(sh.page(ORGA), "test/manage/writing/character/form/new/?frame=1")
    sh.shot(6, row(page, "id_editable"), "Stages in which a field is editable")

    page = sh.goto(sh.page(PLAYER), f"test/character/{characters[0].uuid}/relationships/new/")
    sh.shot(8, menu(page, "Aldric Vane", "Relationships"), "Relationships entry in the character menu")
    sh.shot(9, [banner(page), content(page)], "New relationship form")
    sh.close()


def test_character_inventory(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 202, "character-inventory")
    base, characters = _world(sh, "inventory")
    event = base["event"]
    coins = PoolType.objects.create(event=event, number=1, name="Silver coins")
    herbs = PoolType.objects.create(event=event, number=2, name="Healing herbs")
    label = PoolLabel.objects.create(event=event, number=1, name="Goods")
    label.pool_types.set([coins, herbs])
    inv_type = InventoryType.objects.create(event=event, number=1, name="Personal")
    inv_type.labels.set([label])
    inventory = Inventory.objects.create(event=event, number=1, name="Aldric's purse", inventory_type=inv_type)
    inventory.owners.set([characters[0]])
    for number, (pool, amount) in enumerate([(coins, 12), (herbs, 3)], start=1):
        PoolBalance.objects.update_or_create(
            inventory=inventory, pool_type=pool, defaults={"event": event, "number": number, "amount": amount}
        )
    orga = base["members"][ORGA]
    InventoryTransfer.objects.create(
        target_inventory=inventory, pool_type=coins, amount=15, actor=orga, reason="Starting purse"
    )
    InventoryTransfer.objects.create(
        source_inventory=inventory, pool_type=coins, amount=3, actor=orga, reason="Paid the ferryman"
    )
    refresh()

    page = sh.goto(sh.page(ORGA), f"test/manage/ci/inventory/{inventory.uuid}/view/")
    sh.shot(1, [banner(page), page.locator("table.mob").filter(visible=True).first], "Inventory balances and transfers")
    sh.shot(2, page.locator("#transfer_log"), "Transfer log")
    sh.close()


def test_xp(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 205, "xp")
    base, characters = _world(sh, "experience")
    event = base["event"]
    set_config(event, "exp_user", "True")
    set_config(event, "exp_undo", "24")
    set_config(event, "exp_start", "10")
    set_config(event, "exp_rules", "True")
    set_config(event, "exp_modifiers", "True")
    system = SystemExp.objects.filter(event=event).first() or SystemExp.objects.create(
        event=event, number=1, name="Default"
    )
    combat = AbilityTypeExp.objects.create(event=event, number=1, name="Combat")
    for number, (name, cost, descr) in enumerate(
        [("Sword mastery", 2, "Fight with a blade."), ("Shield wall", 3, "Block a volley.")], 1
    ):
        AbilityExp.objects.create(
            event=event,
            number=number,
            name=name,
            typ=combat,
            system=system,
            cost=cost,
            visible=True,
            descr=f"<p>{descr}</p>",
        )
    DeliveryExp.objects.create(event=event, number=1, name="First session", amount=5, system=system)
    refresh()

    page = sh.goto(sh.page(ORGA), "test/manage/experience/abilities/new/?frame=1")
    sh.shot(1, page.locator("form table").first, "New ability")
    page = sh.goto(sh.page(ORGA), "test/manage/experience/awards/new/?frame=1")
    sh.shot(2, page.locator("form table").first, "New award")
    page = sh.goto(sh.page(ORGA), "test/manage/experience/awards/")
    page.locator("details.button-dropdown").first.evaluate("el => el.open = true")
    page.wait_for_timeout(300)
    sh.shot(3, [banner(page), page.locator("details.button-dropdown ul").first], "Load characters into an award")
    page = sh.goto(sh.page(ORGA), "test/manage/config/experience/")
    sh.shot(4, section(page, "Experience points"), "Experience points configuration")

    page = sh.goto(sh.page(PLAYER), f"test/character/{characters[0].uuid}/abilities/")
    sh.shot(5, menu(page, "Aldric Vane", "Abilities"), "Abilities entry in the character menu")
    sh.shot(6, [banner(page), content(page)], "Obtain a new ability", max_height=700)
    page.get_by_text("Sword mastery", exact=True).first.click()
    page.get_by_role("button", name="Submit").or_(page.locator("input[type=submit]")).first.click()
    sh.goto(page, f"test/character/{characters[0].uuid}/abilities/")
    sh.shot(
        7,
        [page.locator("h1", has_text="Experience points"), page.locator("table.abilities")],
        "Owned abilities with undo",
    )

    page = sh.goto(sh.page(ORGA), "test/manage/writing/character/form/new/?frame=1")
    open_select(page.locator("#id_typ"))
    sh.shot(9, row(page, "id_typ"), "Computed field type")
    page = sh.goto(sh.page(ORGA), "test/manage/experience/rules/new/?frame=1")
    sh.shot(10, page.locator("form table").first, "New rule")
    page = sh.goto(sh.page(ORGA), "test/manage/experience/modifiers/new/?frame=1")
    sh.shot(11, page.locator("form table").first, "New modifier")
    sh.close()


def test_ensemble(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 215, "ensemble")
    _world(sh, "ensemble")
    page = sh.goto(sh.page(PLAYER), "test/")
    sh.shot(3, menu(page, "Gallery", "Search", "Ensemble"), "Ensemble entry in the event menu")
    sh.close()


def test_pdf_generation(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 180, "pdf-generation")
    base, characters = _world(sh, "print_pdf", "faction")
    Character.objects.filter(pk=characters[0].pk).update(
        text="<h2>Background</h2><p>You grew up in the halls of House Vane, trained to rule.</p>"
        "<h2>Secrets</h2><p>You know who took the crown, and you have not told anyone.</p>"
    )
    refresh()

    page = sh.goto(sh.page(ORGA), "test/manage/pdf/")
    sh.shot(1, [banner(page), page.locator("#sheet_pdf .mob").first], "PDF downloads and test generation")
    form = page.locator("#sheet_pdf form .form_container")
    sh.shot(2, form, "PDF options", max_height=900)

    event = base["event"]
    for name, value in {
        "pdf_header": "True",
        "pdf_footer": "True",
        "pdf_color_title": "#7a3b12",
        "pdf_color_bold": "#7a3b12",
        "pdf_color_link": "#7a3b12",
        "pdf_color_border": "#c9a36b",
        "page_css": "h2 { border-bottom: 1px solid #c9a36b; padding-bottom: 2pt; }",
    }.items():
        set_config(event, name, value)
    # The test sheet is plain HTML, without the readiness flags of the app pages
    page = sh.page(ORGA)
    page.goto(f"{sh.base_url}/test/manage/characters/{characters[0].uuid}/pdf/sheet/test/")
    page.wait_for_load_state("load")
    sh.shot(3, page.locator("body"), "Complete sheet with header, footer and colors", max_height=760)
    sh.close()
