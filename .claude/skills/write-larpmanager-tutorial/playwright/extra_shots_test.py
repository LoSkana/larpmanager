"""Tutorial screenshots: guilds, matchmaker, user flags, notification digest."""

import pytest
from lm_shots import (
    ORGA,
    PLAYER,
    Shooter,
    activate,
    banner,
    content,
    menu,
    refresh,
    section,
    seed_base,
    seed_characters,
    seed_factions,
    seed_registrations,
    set_config,
)

from larpmanager.models.form import RegistrationAnswer, RegistrationQuestion
from larpmanager.models.member import MemberFlagDef
from larpmanager.models.writing import Guild, GuildMembership
from larpmanager.utils.users.member_flags import set_member_flags

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _real_editor(settings) -> None:
    settings.TINYMCE_DISABLED = False


def _world(sh: Shooter, *features: str) -> tuple[dict, list, list]:
    base = seed_base()
    activate(sh, "character", *features)
    characters = seed_characters(base["event"])
    seed_factions(base["event"], characters)
    registrations = seed_registrations(base["run"], base["members"], characters)
    return base, characters, registrations


def test_guilds(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 217, "guilds")
    base, characters, registrations = _world(sh, "guild")
    event = base["event"]
    set_config(event, "guild_max_number", "5")
    set_config(event, "guild_max_members", "6")

    page = sh.goto(sh.page(ORGA), "test/manage/config/guild/")
    sh.shot(1, section(page, "Guilds"), "Guilds configuration")

    guild = Guild.objects.create(
        event=event,
        number=1,
        name="The Lantern Keepers",
        teaser="<p>Night watchers of the old city walls.</p>",
        color="#c47a2c",
    )
    GuildMembership.objects.create(guild=guild, character=characters[0], role="a", status="a")
    GuildMembership.objects.create(guild=guild, character=characters[1], role="m", status="a")
    GuildMembership.objects.create(guild=guild, character=characters[2], role="m", status="i")
    refresh()

    page = sh.goto(sh.page(PLAYER), "test/guilds/")
    sh.shot(2, menu(page, "Guilds"), "Guilds entry in the event menu", pad=4)
    sh.shot(3, [banner(page), content(page)], "Guild list for participants")

    page = sh.goto(sh.page(PLAYER), "test/guilds/new/")
    sh.shot(4, [banner(page), content(page).locator("form").first], "Create a guild", max_height=640)

    page = sh.goto(sh.page(PLAYER), f"test/guilds/{guild.uuid}/")
    sh.shot(5, [banner(page), content(page)], "Guild page for its admin")

    invited = "sofia.conti@example.com"
    page = sh.goto(sh.page(invited), "test/guilds/invites/")
    sh.shot(6, [banner(page), content(page)], "Pending guild invites")

    page = sh.goto(sh.page(PLAYER), "test/gallery/")
    heading = page.locator("h1.title", has_text="The Lantern Keepers")
    sh.shot(7, [heading, heading.locator("xpath=following-sibling::div[1]")], "Guild in the character gallery")

    page = sh.goto(sh.page(ORGA), "test/manage/guilds/")
    sh.shot(8, [banner(page), content(page).locator(".dt-container").first], "Guilds for the organizers")
    sh.close()


def test_matchmaker(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 225, "matchmaker")
    base, characters, registrations = _world(sh, "faction", "matchmaker")
    event = base["event"]
    wish = RegistrationQuestion.objects.create(
        event=event,
        applicable="m",
        typ="p",
        name="Ideal role",
        description="What kind of character would you like to play?",
        status="o",
        order=1,
    )
    # Activating the matchmaker creates the faction preference question
    factions = RegistrationQuestion.objects.get(event=event, applicable="m", typ="faction_preference")
    intrigue = RegistrationQuestion.objects.create(
        event=event,
        applicable="m",
        typ="l",
        name="Intrigue",
        description="From 1 (none) to 5 (all the scheming)",
        status="o",
        max_length=5,
        order=3,
    )
    faction_uuids = {f.name: str(f.uuid) for f in characters[0].factions_list.model.objects.filter(event=event)}
    answers = [
        ("A noble torn between loyalty and love.", ["House Vane", "Ashen Guild"], "5"),
        ("Someone with secrets, working in the shadows.", ["Ashen Guild", "House Vane"], "4"),
        ("A healer who keeps everyone together.", ["House Vane", "Ashen Guild"], "2"),
    ]
    for registration, (text, order, score) in zip(registrations[1:], answers):
        RegistrationAnswer.objects.create(question=wish, registration=registration, text=text)
        RegistrationAnswer.objects.create(
            question=factions, registration=registration, text=",".join(faction_uuids[name] for name in order)
        )
        RegistrationAnswer.objects.create(question=intrigue, registration=registration, text=score)
    refresh()

    page = sh.goto(sh.page(ORGA), "test/manage/form/matchmaker/")
    sh.shot(1, [banner(page), content(page).locator(".dt-container").first], "Matchmaker questions in the form page")

    page = sh.goto(sh.page(PLAYER), "test/matchmaker/")
    sh.shot(2, menu(page, "Matchmaker"), "Matchmaker entry in the event menu", pad=4)
    sh.shot(3, [banner(page), content(page).locator("form").first], "Matchmaker form for participants")

    page = sh.goto(sh.page(ORGA), "test/manage/matchmaker/")
    sh.shot(4, [banner(page), content(page).locator(".dt-container").first], "Matchmaker answers")
    chart = content(page).locator("canvas").first
    sh.shot(5, [content(page).locator("h2, h3", has_text="Intrigue").last, chart], "Distribution of a rating question")
    sh.close()


def test_user_flags(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 265, "user-flags")
    base, characters, registrations = _world(sh, "payment")
    association = base["association"]

    page = sh.goto(sh.page(ORGA), "manage/config/users/")
    sh.shot(1, section(page, "Users", "id_player_larp_history", "id_member_flags_active"), "User flags configuration")

    set_config(association, "member_flags_active", "True")
    flags = [
        MemberFlagDef.objects.create(
            association=association, name="Code of conduct", descr="Signed the code of conduct", order=1
        ),
        MemberFlagDef.objects.create(association=association, name="First aid", descr="Qualified first aider", order=2),
        MemberFlagDef.objects.create(
            association=association, name="Volunteer", descr="Helped the staff this year", annual=True, order=3
        ),
    ]
    for registration, values in zip(registrations, [(1, 1, 0), (1, 0, 1), (1, 0, 0), (0, 1, 0), (1, 0, 0)]):
        set_member_flags(registration.member, flags, {f.id: bool(v) for f, v in zip(flags, values)})
    refresh()

    page = sh.goto(sh.page(ORGA), "manage/member_flags/new/?frame=1")
    sh.shot(2, page.locator("form table").first, "New user flag")
    page = sh.goto(sh.page(ORGA), "manage/member_flags/")
    sh.shot(3, [banner(page), content(page).locator(".dt-container").first], "Flag types")

    page = sh.goto(sh.page(ORGA), "manage/members_flags/")
    sh.shot(4, [banner(page), content(page).locator(".dt-container").first], "User flags of each user")
    page.locator(".edit_member_flags").first.click()
    page.wait_for_timeout(1500)
    popup = page.locator("dialog[open], .popup:visible, #popup:visible").first
    sh.shot(5, popup, "Edit the flags of a user")

    page = sh.goto(sh.page(ORGA), "test/manage/registrations/")
    page.locator("i.fa-eye").first.click()
    page.wait_for_timeout(1500)
    popup = page.locator("dialog[open], .popup:visible, #popup:visible").first
    sh.shot(6, popup, "User flags in the registration details")
    sh.close()


def test_digest(browser_type, live_server) -> None:
    sh = Shooter(browser_type, live_server, 999, "manage-mails")
    seed_base()
    page = sh.goto(sh.page(ORGA), "manage/preferences/")
    sh.shot(4, section(page, "Interface"), "Personal notifications digest")
    sh.close()
