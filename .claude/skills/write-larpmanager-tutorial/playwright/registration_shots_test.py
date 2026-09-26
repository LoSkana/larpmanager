"""Tutorial screenshots: registrations, tickets, registration form and accounting, payments (tutorials 90-150)."""

from datetime import date

import pytest
from lm_shots import (
    NEWCOMER,
    ORGA,
    PLAYER,
    Shooter,
    activate,
    banner,
    content,
    open_select,
    refresh,
    row,
    row_label,
    section,
    seed_base,
    seed_characters,
    seed_questions,
    seed_quotas,
    seed_registrations,
    seed_section,
    seed_tickets,
    set_config,
)

from larpmanager.models.event import Run
from larpmanager.models.registration import Registration

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _real_editor(settings) -> None:
    settings.TINYMCE_DISABLED = False


def test_registrations(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 90, "registrations")
    activate(sh, "character", "pre_register", "registration_secret")
    characters = seed_characters(base["event"])
    registrations = seed_registrations(base["run"], base["members"], characters)

    page = sh.goto(sh.page(ORGA), "test/manage/registrations/")
    sh.shot(1, [banner(page), page.locator(".dt-container").first], "Registrations list")

    page = sh.goto(sh.page(ORGA), f"test/manage/registrations/{registrations[0].uuid}/edit/?frame=1")
    section(page, "Character")
    sh.shot(2, [row(page, "id_member"), row(page, "id_characters_new")], "Registration with its character")

    Registration.objects.filter(pk=registrations[-1].pk).update(cancellation_date=date(2027, 5, 2))
    refresh()
    page = sh.goto(sh.page(ORGA), "test/manage/cancellations/")
    sh.shot(3, [banner(page), content(page)], "Cancelled registrations")

    page = sh.goto(sh.page(ORGA), "test/manage/event/?frame=1")
    sh.shot(5, row(page, "id_form2-registration_status"), "Registration status options")

    Run.objects.filter(pk=base["run"].pk).update(registration_status="c", registration_secret="ember2027")
    refresh()
    page = sh.goto(sh.page(ORGA), "test/manage/")
    card = page.locator(".grid-item").filter(has=page.locator("h2", has_text="Registrations")).first
    sh.shot(7, card, "Secret registration link in the dashboard")
    sh.close()


def test_manage_ticket(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 100, "manage-ticket")
    activate(sh, "reduced", "filler", "waiting", "lottery")
    set_config(base["event"], "ticket_staff", "True")
    set_config(base["event"], "ticket_npc", "True")
    seed_tickets(base["event"])

    page = sh.goto(sh.page(ORGA), "test/manage/tickets/new/?frame=1")
    sh.shot(1, page.locator("form table").first, "New ticket form", max_height=700)
    open_select(page.locator("#id_tier"))
    sh.shot(3, row(page, "id_tier"), "Ticket tiers")

    page = sh.goto(sh.page(ORGA), "test/manage/config/tickets/")
    sh.shot(2, section(page, "Tickets"), "Tickets configuration")

    page = sh.goto(sh.page(NEWCOMER), "test/register/")
    sh.shot(4, row_label(page, "Ticket"), "Ticket selection for participants")

    page = sh.goto(sh.page(ORGA), "test/manage/config/reduced/")
    sh.shot(6, section(page, "Patron / Reduced"), "Patron and reduced configuration")
    page = sh.goto(sh.page(ORGA), "test/manage/config/lottery/")
    sh.shot(12, section(page, "Lottery"), "Lottery configuration")
    sh.close()


def test_registration_form(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 110, "registration-form")
    activate(sh, "reg_que_sections")
    seed_tickets(base["event"])
    registration_section = seed_section(base["event"])
    questions = seed_questions(base["event"], registration_section)

    page = sh.goto(sh.page(ORGA), "test/manage/form/registration/new/?frame=1")
    sh.shot(1, [row(page, "id_typ"), row(page, "id_status")], "New registration question")

    page = sh.goto(sh.page(NEWCOMER), "test/register/")
    sh.shot(2, row_label(page, questions["t"].name), "Single-line text question")
    sh.shot(3, row_label(page, questions["p"].name), "Multi-line text question")
    editor = row_label(page, questions["e"].name)
    editor.locator("a.my_toggle").first.click()
    sh.shot(4, editor, "Advanced text editor question")
    sh.shot(5, row_label(page, questions["l"].name), "Likert scale question")
    logistics = section(page, "Logistics")
    sh.shot(10, logistics, "Registration form section")
    sh.shot(7, [row_label(page, questions["s"].name), row_label(page, questions["m"].name)], "Choice questions")

    page = sh.goto(sh.page(ORGA), f"test/manage/form/registration/{questions['s'].uuid}/edit/?frame=1")
    sh.shot(
        6, page.locator(".inline-options-table, table:has(.fa-grip-vertical)").first, "Options of a choice question"
    )

    page = sh.goto(sh.page(ORGA), "test/manage/sections/new/?frame=1")
    sh.shot(8, page.locator("form table").first, "New section")

    page = sh.goto(sh.page(ORGA), "test/manage/config/registrations/")
    sh.shot(11, section(page, "Registrations"), "Registrations configuration")

    set_config(base["event"], "registration_approval_process", "True")
    page = sh.goto(sh.page(NEWCOMER), "test/register/request/")
    sh.shot(12, [banner(page), content(page)], "Signup request")
    page.locator("input[type=checkbox]").first.check()
    page.get_by_role("button", name="Confirm").click()

    page = sh.goto(sh.page(ORGA), "test/manage/registrations/requests/")
    sh.shot(13, [banner(page), content(page)], "Signup requests to review")
    sh.close()


def test_registration_accounting(browser_type, live_server) -> None:
    base = seed_base()
    sh = Shooter(browser_type, live_server, 130, "registration-accounting")
    activate(sh, "payment", "reg_installments", "reg_quotas", "reg_surcharges", "discount", "gift")
    seed_tickets(base["event"])

    page = sh.goto(sh.page(ORGA), "test/manage/installments/new/?frame=1")
    sh.shot(2, page.locator("form table").first, "New fixed instalment")
    page = sh.goto(sh.page(ORGA), "test/manage/quotas/new/?frame=1")
    sh.shot(3, page.locator("form table").first, "New dynamic rate")
    seed_quotas(base["event"])
    page = sh.goto(sh.page(ORGA), "test/manage/quotas/")
    sh.shot(4, content(page), "Dynamic rates list")
    page = sh.goto(sh.page(ORGA), "test/manage/surcharges/new/?frame=1")
    sh.shot(5, page.locator("form table").first, "New surcharge")
    page = sh.goto(sh.page(ORGA), "test/manage/discounts/new/?frame=1")
    sh.shot(6, page.locator("form table").first, "New discount", max_height=700)

    page = sh.goto(sh.page(NEWCOMER), "test/register/")
    sh.shot(7, section(page, "Discounts"), "Discount code field")

    page = sh.goto(sh.page(PLAYER), "test/gift/")
    sh.shot(9, [banner(page), content(page)], "Gift page")
    sh.close()


def test_payments(browser_type, live_server) -> None:
    seed_base()
    sh = Shooter(browser_type, live_server, 150, "payments")
    activate(sh, "payment")

    page = sh.goto(sh.page(ORGA), "manage/methods/")
    sh.shot(1, [banner(page), content(page)], "Payment methods", max_height=420)
    page.locator("label", has_text="Wire").first.click()
    wire = section(page, "wire")
    inputs = wire[1].locator("input[type=text], input:not([type])")
    for idx, value in enumerate(["Bank transfer", "", "Test Organization", "IT60X0542811101000000123456", "BPMOIT22XXX"]):
        if value and idx < inputs.count():
            inputs.nth(idx).fill(value)
    sh.shot(2, wire, "Wire transfer settings")

    page = sh.goto(sh.page(ORGA), "manage/config/payment/")
    sh.shot(3, section(page, "Payments"), "Organization payment configuration")
    page = sh.goto(sh.page(ORGA), "test/manage/config/payment/")
    sh.shot(4, section(page, "Payments"), "Event payment configuration")
    sh.close()
