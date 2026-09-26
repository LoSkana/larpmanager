"""Tutorial screenshots: casting, quests, deadlines, users, membership, accounting, mails (tutorials 230-999)."""

import base64
from datetime import UTC, date, datetime

import pytest
from django.contrib.auth.models import User
from lm_shots import (
    ORGA,
    OUT_DIR,
    PLAYER,
    Shooter,
    activate,
    banner,
    content,
    menu,
    open_select,
    qr_video,
    refresh,
    row,
    section,
    seed_base,
    seed_characters,
    seed_factions,
    seed_registrations,
    set_config,
)

from larpmanager.models.accounting import (
    AccountingItemExpense,
    AccountingItemInflow,
    AccountingItemOther,
    AccountingItemOutflow,
    AccountingItemPayment,
    Collection,
    RefundRequest,
)
from larpmanager.models.casting import Casting, CastingAvoid, Quest, QuestType, Trait
from larpmanager.models.event import Run
from larpmanager.models.form import RegistrationAnswer, RegistrationChoice, RegistrationOption, RegistrationQuestion
from larpmanager.models.member import Member, Membership
from larpmanager.models.miscellanea import HelpQuestion
from larpmanager.models.registration import CheckIn, Registration

pytestmark = pytest.mark.e2e

UNASSIGNED = "giulia.serra@example.com"


@pytest.fixture(autouse=True)
def _real_editor(settings) -> None:
    settings.TINYMCE_DISABLED = False


def _world(sh: Shooter, *features: str, assign: bool = True) -> tuple[dict, list, list]:
    base = seed_base()
    activate(sh, "character", *features)
    characters = seed_characters(base["event"])
    seed_factions(base["event"], characters)
    registrations = seed_registrations(base["run"], base["members"], characters, assign=assign)
    return base, characters, registrations


def test_casting(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 230, "casting")
    base, characters, registrations = _world(sh, "faction", "casting", assign=False)
    event, run = base["event"], base["run"]
    set_config(event, "casting_min", "3")
    set_config(event, "casting_max", "4")
    set_config(event, "casting_avoid", "True")
    set_config(event, "casting_show_pref", "True")
    for reg_idx, registration in enumerate(registrations):
        for rank in range(3):
            character = characters[(reg_idx + rank) % len(characters)]
            Casting.objects.create(
                run=run, member=registration.member, element=str(character.uuid), pref=rank + 1, typ=0
            )
    CastingAvoid.objects.create(run=run, member=registrations[1].member, typ=0, text="Characters in love stories")
    refresh()

    page = sh.goto(sh.page(ORGA), "test/manage/config/casting/")
    rows = section(page, "Casting")[1].locator("tr").filter(visible=True)
    sh.shot(1, [section(page, "Casting")[0], rows.nth(4)], "Casting configuration")
    sh.shot(2, [rows.nth(5), rows.last], "Casting priorities and visibility")

    page = sh.goto(sh.page(UNASSIGNED), "test/casting/")
    sh.shot(3, [banner(page), content(page)], "Character preferences for participants", max_height=700)
    sh.shot(10, [page.locator(".casting-avoid"), page.locator("#avoid")], "Elements to avoid")

    page = sh.goto(sh.page(PLAYER), f"test/character/{characters[0].uuid}/")
    sh.shot(4, [banner(page), content(page)], "Preference statistics on a character", max_height=560)

    page = sh.goto(sh.page(ORGA), "test/manage/casting/")
    sh.shot(5, [banner(page), content(page).locator("table").filter(visible=True).first], "Casting filters")
    sh.shot(6, content(page).locator(".dt-container").first, "Participant preferences")
    start = (
        page.get_by_role("button", name="Start algorithm").or_(page.get_by_role("link", name="Start algorithm")).first
    )
    sh.shot(8, start.locator("xpath=ancestor::*[self::div or self::tr][1]"), "Start the algorithm")
    start.click()
    page.locator("#go").wait_for(state="visible", timeout=60_000)
    sh.shot(9, [page.locator("#go"), page.locator("#go").locator("xpath=ancestor::div[1]")], "Proposed assignment")
    sh.close()


def test_quests(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 240, "quests")
    base, characters, registrations = _world(sh, "questbuilder", "casting")
    event, run = base["event"], base["run"]

    page = sh.goto(sh.page(ORGA), "test/manage/quest_types/new/?frame=1")
    sh.shot(1, page.locator("form table").first, "New quest type")

    quest_type = QuestType.objects.create(event=event, number=1, name="Past Occupations")
    quest = Quest.objects.create(
        event=event,
        number=1,
        name="Heist",
        typ=quest_type,
        teaser="<p>Do you remember that heist? It'll be an easy job, they said.</p>",
    )
    traits = []
    for number, (name, teaser) in enumerate(
        [
            ("Mind", "You were the mind..."),
            ("Muscle", "You were the muscle..."),
            ("Face", "You were the face..."),
            ("Driver", "You were the driver..."),
            ("Lookout", "You were the lookout..."),
        ],
        1,
    ):
        traits.append(
            Trait.objects.create(event=event, number=number, name=name, quest=quest, teaser=f"<p>{teaser}</p>")
        )
    refresh()

    page = sh.goto(sh.page(ORGA), "test/manage/quests/new/?frame=1")
    sh.shot(2, page.locator("form table").first, "New quest", max_height=620)
    page = sh.goto(sh.page(ORGA), "test/manage/traits/new/?frame=1")
    sh.shot(3, page.locator("form table").first, "New trait", max_height=620)

    page = sh.goto(sh.page(PLAYER), "test/quests/")
    sh.shot(4, [banner(page), content(page)], "Quests for participants")
    page = sh.goto(sh.page(PLAYER), f"test/quest/{quest.uuid}/")
    sh.shot(5, [banner(page), content(page)], "Quest with its traits")

    page = sh.goto(sh.page(PLAYER), f"test/casting/{quest_type.uuid}/")
    sh.shot(6, [banner(page), content(page)], "Trait preferences", max_height=640)

    for reg_idx, registration in enumerate(registrations):
        for rank in range(3):
            trait = traits[(reg_idx + rank) % len(traits)]
            Casting.objects.create(
                run=run, member=registration.member, element=str(trait.uuid), pref=rank + 1, typ=quest_type.number
            )
    refresh()
    page = sh.goto(sh.page(ORGA), f"test/manage/casting/{quest_type.uuid}/")
    sh.shot(7, content(page).locator(".dt-container").first, "Trait preferences for the organizers")

    page = sh.goto(sh.page(ORGA), f"test/manage/registrations/{registrations[0].uuid}/edit/?frame=1")
    section(page, "Character")
    select = page.locator("select").filter(has=page.locator("option", has_text="Mind")).first
    open_select(select)
    sh.shot(8, select.locator("xpath=ancestor::tr[1]"), "Assign a trait from the registration")
    sh.close()


def test_deadlines(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 250, "deadlines")
    _base, _characters, registrations = _world(sh, "deadlines", "remind", "membership", "payment")
    Membership.objects.filter(member__user__username=UNASSIGNED).update(status="e")
    # One payment a few days late, one beyond the default 30 days tolerance
    Registration.objects.filter(pk=registrations[0].pk).update(quota=80, deadline=-5)
    Registration.objects.filter(pk=registrations[1].pk).update(quota=120, deadline=-45)
    refresh()

    page = sh.goto(sh.page(ORGA), "manage/config/deadlines/")
    sh.shot(1, section(page, "Deadline"), "Deadline configuration")
    page = sh.goto(sh.page(ORGA), "test/manage/deadlines/")
    sh.shot(2, [banner(page), content(page)], "Missed deadlines of the event")
    page = sh.goto(sh.page(ORGA), "manage/config/remind/")
    sh.shot(3, section(page, "Reminder"), "Reminder configuration")
    page = sh.goto(sh.page(ORGA), "manage/texts/new/?frame=1")
    open_select(page.locator("#id_typ"))
    sh.shot(4, [row(page, "id_text"), row(page, "id_typ")], "Reminder text types")
    sh.close()


def test_users(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 260, "users")
    base, characters, registrations = _world(sh, "help", "safety", "diet", "chat", "newsletter", "delegated_members")
    Member.objects.filter(pk=registrations[0].member.pk).update(safety="Asthma, carries an inhaler", diet="Vegetarian")
    Member.objects.filter(pk=registrations[1].member.pk).update(diet="Gluten free")
    refresh()

    page = sh.goto(sh.page(PLAYER), "help/")
    sh.shot(2, [banner(page), content(page).locator("form").first], "Help request form")
    HelpQuestion.objects.create(
        member=registrations[0].member,
        run=base["run"],
        text="Can I arrive on Saturday morning?",
        association=base["association"],
    )
    refresh()
    page = sh.goto(sh.page(PLAYER), "help/")
    sh.shot(
        3,
        page.locator("h2, h3", has_text="Comunications")
        .or_(page.locator("h2, h3", has_text="Communications"))
        .first.locator("xpath=.."),
        "Previous help requests",
    )
    page = sh.goto(sh.page(ORGA), "manage/questions/")
    sh.shot(4, [banner(page), content(page)], "Help requests to answer")

    page = sh.goto(sh.page(ORGA), "test/manage/safety/")
    sh.shot(5, [banner(page), content(page)], "Safety information")
    page = sh.goto(sh.page(ORGA), "test/manage/diet/")
    sh.shot(6, [banner(page), content(page)], "Diet information")
    page = sh.goto(sh.page(PLAYER), f"public/{registrations[1].member.uuid}/")
    sh.shot(7, [banner(page), content(page)], "Public profile with the chat link", max_height=420)
    page = sh.goto(sh.page(ORGA), "manage/newsletter/")
    sh.shot(8, [banner(page), content(page)], "Newsletter lists")

    delegated_user = User.objects.create(username="tommaso.ricci.delegated", email="")
    Member.objects.filter(user=delegated_user).update(name="Tommaso", surname="Ricci", parent=registrations[0].member)
    refresh()
    page = sh.goto(sh.page(PLAYER), "delegated/")
    sh.shot(10, [banner(page), content(page)], "Delegated accounts")
    sh.close()


def test_membership(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 270, "membership")
    base, characters, registrations = _world(sh, "membership", "deadlines")
    Membership.objects.filter(member=registrations[4].member).update(status="s")
    Membership.objects.filter(member__user__username=PLAYER).update(status="j")
    refresh()

    page = sh.goto(sh.page(ORGA), "manage/config/membership/")
    sh.shot(1, section(page, "Members"), "Membership configuration")
    page = sh.goto(sh.page(ORGA), "manage/texts/new/?frame=1")
    select = page.locator("#id_typ")
    select.evaluate("el => { for (const o of el.options) { o.selected = o.text.trim() === 'Membership'; } }")
    open_select(select)
    sh.shot(2, [row(page, "id_text"), row(page, "id_typ")], "Membership request template")

    page = sh.goto(sh.page(PLAYER), "membership/")
    sh.shot(3, [banner(page), content(page)], "Membership request for participants")

    page = sh.goto(sh.page(ORGA), "manage/membership/")
    sh.shot(5, [banner(page), content(page)], "Membership requests to review", max_height=520)
    page = sh.goto(sh.page(ORGA), f"manage/membership/{registrations[4].member.uuid}/")
    sh.shot(6, [banner(page), content(page)], "Review a membership request", max_height=520)

    page = sh.goto(sh.page(ORGA), "test/manage/registrations/")
    page.locator("a", has_text="member").first.click()
    page.wait_for_timeout(500)
    sh.shot(8, page.locator(".dt-container").first, "Membership status in the registrations")
    page = sh.goto(sh.page(ORGA), "manage/deadlines/")
    sh.shot(9, [banner(page), content(page)], "Membership deadlines")
    sh.close()


def test_accounting(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 300, "accounting")
    feats = (
        "payment",
        "donate",
        "expense",
        "collection",
        "refund",
        "credits",
        "tokens",
        "inflow",
        "outflow",
        "vat",
        "verification",
        "organization_tax",
    )
    base, characters, registrations = _world(sh, *feats)
    assoc, run = base["association"], base["run"]
    set_config(assoc, "vat_ticket", "22")
    set_config(assoc, "organization_tax_perc", "10")
    for registration in registrations:
        AccountingItemPayment.objects.create(
            member=registration.member, association=assoc, registration=registration, value=120
        )
    AccountingItemExpense.objects.create(
        member=base["members"][ORGA],
        association=assoc,
        run=run,
        value=86,
        descr="Candles and lanterns",
        exp="a",
        invoice="invoice/x.pdf",
    )
    AccountingItemInflow.objects.create(
        association=assoc, run=run, value=300, descr="Sponsorship from the local tavern", payment_date=date(2027, 5, 10)
    )
    AccountingItemOutflow.objects.create(
        association=assoc, run=run, value=450, descr="Venue rental", payment_date=date(2027, 5, 20), exp="h"
    )
    AccountingItemOther.objects.create(
        member=registrations[0].member, association=assoc, run=run, value=30, oth="c", descr="Staff bonus"
    )
    RefundRequest.objects.create(
        member=registrations[1].member, association=assoc, value=40, details="IBAN IT60X0542811101000000123456"
    )
    Collection.objects.create(
        name="Gift for Lysa",
        organizer=registrations[0].member,
        member=registrations[3].member,
        run=run,
        association=assoc,
    )
    refresh()

    page = sh.goto(sh.page(PLAYER), "accounting/")
    sh.shot(2, [banner(page), content(page)], "Personal accounting", max_height=700)
    for num, title in [(5, "Donation"), (8, "Collection"), (10, "Credits")]:
        heading = page.locator("h2, h3", has_text=title).first
        sh.shot(
            num, [heading, heading.locator("xpath=following-sibling::*[1]")], f"{title} section of the accounting page"
        )

    page = sh.goto(sh.page(ORGA), "manage/accounting/")
    sh.shot(3, [banner(page), content(page)], "Organization accounting", max_height=700)
    page = sh.goto(sh.page(ORGA), "test/manage/accounting/")
    sh.shot(4, [banner(page), content(page)], "Event accounting", max_height=700)
    sh.shot(18, [banner(page), content(page)], "Event accounting with the organizational fee", max_height=360)

    page = sh.goto(sh.page(ORGA), "test/manage/upload_expenses/new/?frame=1")
    sh.shot(6, page.locator("form table").first, "Upload an expense")
    page = sh.goto(sh.page(ORGA), "manage/expenses/")
    sh.shot(7, [banner(page), content(page)], "Expenses to review")

    collection = Collection.objects.get(name="Gift for Lysa")
    page = sh.goto(sh.page(PLAYER), f"accounting/collection/{collection.contribute_code}/")
    sh.shot(9, [banner(page), content(page)], "Collection page")

    page = sh.goto(sh.page(ORGA), "manage/refunds/")
    sh.shot(11, [banner(page), content(page)], "Refund requests")
    page = sh.goto(sh.page(ORGA), "manage/inflows/new/?frame=1")
    sh.shot(12, page.locator("form table").first, "New inflow")
    page = sh.goto(sh.page(ORGA), "manage/outflows/new/?frame=1")
    sh.shot(13, page.locator("form table").first, "New outflow")
    page = sh.goto(sh.page(ORGA), "manage/config/vat/")
    sh.shot(14, section(page, "VAT"), "VAT configuration")
    page = sh.goto(sh.page(ORGA), "manage/payments/")
    sh.shot(15, [banner(page), content(page)], "Payments with VAT", max_height=520)
    page = sh.goto(sh.page(ORGA), "manage/verification/")
    sh.shot(16, [banner(page), content(page)], "Payment verification", max_height=600)
    page = sh.goto(sh.page(ORGA), "manage/config/organization_tax/")
    sh.shot(17, section(page, "Organizational fee"), "Organizational fee configuration")
    sh.close()


def test_manage_mails(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 999, "manage-mails")
    _world(sh, "custom_mail")
    page = sh.goto(sh.page(ORGA), "manage/config/email/")
    sh.shot(1, section(page, "Email notifications"), "Email notifications")
    page = sh.goto(sh.page(ORGA), "manage/config/custom_mail_server/")
    sh.shot(2, section(page, "Customised mail server"), "Organization mail server")
    page = sh.goto(sh.page(ORGA), "test/manage/config/custom_mail_server/")
    sh.shot(3, section(page, "Customised mail server"), "Event mail server")
    sh.close()


def test_checkin(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 400, "checkin")
    base, characters, registrations = _world(sh, "checkin", "experience")
    orga = base["members"][ORGA]
    for registration, hour in ((registrations[1], 9), (registrations[2], 10)):
        CheckIn.objects.update_or_create(
            registration=registration,
            defaults={"checked_in_at": datetime(2027, 6, 18, hour, 15, tzinfo=UTC), "checked_in_by": orga},
        )
    refresh()

    page = sh.goto(sh.page(PLAYER), "test/")
    qr = page.locator(".checkin-qr")
    sh.shot(2, [qr.locator("xpath=.."), qr], "Check-in QR code on the event page")

    # Scan the player's real QR code through a fake camera
    qr_png = OUT_DIR / "_qr.png"
    src = qr.locator("img").get_attribute("src")
    if src.startswith("data:"):
        qr_png.write_bytes(base64.b64decode(src.split(",", 1)[1]))
    else:
        qr_png.write_bytes(page.request.get(f"{sh.base_url}{src}").body())
    scanner = Shooter(browser_type, live_server, 400, "checkin", camera=qr_video(qr_png, OUT_DIR / "_qr.y4m"))
    scan_page = scanner.goto(scanner.page(ORGA), "test/manage/checkin/")
    scan_page.locator("#checkin_table tbody tr").first.wait_for()
    scan_page.locator("#checkin_scan_btn").click()
    scan_page.locator("#checkin_scan_result").filter(has_text="Elena Ricci").wait_for(timeout=30_000)
    scanner.shot(4, scan_page.locator("#checkin_scan_popup"), "QR code scanner after a scan")
    scanner.close()
    qr_png.unlink()
    (OUT_DIR / "_qr.y4m").unlink()

    page = sh.goto(sh.page(ORGA), "test/manage/checkin/")
    page.locator("#checkin_table tbody tr").first.wait_for()
    sh.shot(3, [banner(page), page.locator("#checkin")], "Check-in page")

    page.locator(".checkin-signin-btn").first.click()
    page.locator("#checkin_signin_popup").wait_for(state="visible")
    sh.shot(5, page.locator("#checkin_signin_popup"), "Manual check-in confirmation")
    page.locator("#checkin_signin_cancel").click()

    page.context.set_offline(True)
    page.evaluate("() => window.dispatchEvent(new Event('offline'))")
    page.locator(".checkin-signin-btn").first.click()
    page.locator("#checkin_signin_confirm").click()
    page.wait_for_timeout(800)
    sh.shot(6, page.locator("#checkin_status"), "Offline mode with pending check-ins")
    page.context.set_offline(False)

    page = sh.goto(sh.page(ORGA), "test/manage/experience/awards/")
    page.locator("details.button-dropdown").first.evaluate("el => el.open = true")
    sh.shot(
        7,
        [banner(page), page.locator("details.button-dropdown ul").first],
        "Load characters from checked-in participants",
    )
    sh.close()


def test_debrief(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 410, "debrief")
    base, characters, registrations = _world(sh, "debrief", "deadlines", "experience")
    event, run = base["event"], base["run"]
    rating = RegistrationQuestion.objects.create(
        event=event,
        applicable="b",
        typ="l",
        name="Overall rating",
        description="From 1 (poor) to 5 (unforgettable)",
        status="o",
        max_length=5,
        order=1,
    )
    moment = RegistrationQuestion.objects.create(
        event=event,
        applicable="b",
        typ="p",
        name="Best moment",
        description="What did you enjoy most?",
        status="o",
        order=2,
    )
    again = RegistrationQuestion.objects.create(
        event=event,
        applicable="b",
        typ="s",
        name="Next edition",
        description="Would you play the next edition?",
        status="o",
        order=3,
    )
    options = {
        name: RegistrationOption.objects.create(event=event, question=again, name=name, order=order)
        for order, name in enumerate(["Yes", "Maybe", "No"])
    }
    feedback = [
        ("5", "The coronation scene, when the crown was finally found.", "Yes"),
        ("4", "Plotting with the Ashen Guild in the tavern.", "Yes"),
        ("4", "The night market and all the trading.", "Maybe"),
    ]
    for registration, (score, text, choice) in zip(registrations[1:], feedback):
        RegistrationAnswer.objects.create(question=rating, registration=registration, text=score)
        RegistrationAnswer.objects.create(question=moment, registration=registration, text=text)
        RegistrationChoice.objects.create(question=again, option=options[choice], registration=registration)
    refresh()

    page = sh.goto(sh.page(ORGA), "test/manage/form/debrief/")
    sh.shot(1, [banner(page), content(page).locator(".dt-container").first], "Debrief questions in the form page")

    page = sh.goto(sh.page(PLAYER), "test/debrief/")
    sh.shot(2, menu(page, "Debrief"), "Debrief entry in the event menu", pad=4)
    sh.shot(3, [banner(page), content(page).locator("form").first], "Debrief form for participants")

    page = sh.goto(sh.page(ORGA), "test/manage/debrief/")
    sh.shot(4, [banner(page), content(page).locator(".dt-container").first], "Debrief answers")
    chart = content(page).locator("canvas").first
    sh.shot(
        5, [content(page).locator("h2, h3", has_text="Overall rating").last, chart], "Distribution of a rating question"
    )

    # Deadlines only report the debrief once the session is over
    Run.objects.filter(pk=run.pk).update(start=date(2026, 6, 18), end=date(2026, 6, 20))
    refresh()
    page = sh.goto(sh.page(ORGA), "test/manage/deadlines/")
    row = page.locator("tr", has_text="Debrief not yet compiled").first
    sh.shot(6, [page.locator("#deadlines thead, table thead").first, row], "Participants who did not fill the debrief")

    page = sh.goto(sh.page(ORGA), "test/manage/experience/awards/")
    page.locator("details.button-dropdown").first.evaluate("el => el.open = true")
    sh.shot(
        7,
        [banner(page), page.locator("details.button-dropdown ul").first],
        "Load characters of participants who filled the debrief",
    )
    sh.close()
