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
import os
from datetime import datetime
from urllib.parse import urlparse

from playwright.async_api import expect

password = "banana"
orga_user = "orga@test.it"
test_user = "user@test.it"


async def page_start(p, show=False):
    browser = await p.chromium.launch(headless=not show)
    context = await browser.new_context(record_video_dir="test_videos")
    page = await context.new_page()

    page.set_default_timeout(60000)

    page.on("dialog", lambda dialog: dialog.accept())

    async def on_response(response):
        error_code = 500
        if response.status == error_code:
            raise Exception(f"500 on {response.url}")

    page.on("response", on_response)

    return browser, context, page


async def logout(page, live_server):
    await page.locator("a#menu-open").click()
    await page.get_by_role("link", name="Logout").click()


async def login_orga(pg, ls):
    await login(pg, ls, orga_user)


async def login_user(pg, lv):
    await login(pg, lv, test_user)


async def login(pg, live_server, name):
    await go_to(pg, live_server, "/login")

    await pg.locator("#id_username").fill(name)
    await pg.locator("#id_password").fill(password)
    await pg.get_by_role("button", name="Submit").click()
    await expect(pg.locator("#banner")).not_to_contain_text("Login")


async def handle_error(page, e, test_name):
    print(f"Error on {test_name}: {page.url}\n")
    print(e)

    uid = datetime.now().strftime("%Y%m%d_%H%M%S")
    await page.screenshot(path=f"test_screenshots/{test_name}_{uid}.png")
    try:
        video_path = await page.video.path()
        os.rename(video_path, f"test_videos/{test_name}_{uid}.webm")
    except Exception as ve:
        print(f"[!] Errore video: {ve}")

    # print("Captured Visible Page Text:\n")
    # print(print_text(page))
    raise e


async def print_text(page):
    visible_text = await page.evaluate("""
        () => {
            function getVisibleText(element) {
                return [...element.querySelectorAll('*')]
                    .filter(el => el.offsetParent !== null) // Filter only visible elements
                    .map(el => el.innerText.trim()) // Extract text
                    .filter(text => text.length > 0) // Remove empty strings
                    .join('\\n'); // Join with new lines
            }
            return getVisibleText(document.body);
        }
    """)

    print(visible_text)


async def go_to(page, live_server, path):
    await go_to_check(page, f"{live_server.url}/{path}")


async def go_to_check(page, path):
    dialog_triggered = False

    def on_dialog(dialog):
        nonlocal dialog_triggered
        dialog_triggered = True
        dialog.dismiss()

    page.on("dialog", on_dialog)

    await page.goto(path)
    await ooops_check(page)

    assert not dialog_triggered, "Unexpected JavaScript dialog was triggered"


async def submit(page):
    await page.get_by_role("button", name="Submit").click()
    await page.wait_for_load_state("networkidle")
    await page.wait_for_load_state("load")
    await ooops_check(page)


async def ooops_check(page):
    banner = page.locator("#banner")
    if await banner.count() > 0:
        await expect(banner).not_to_contain_text("Oops!")
        await expect(banner).not_to_contain_text("404")


async def check_download(page, link):
    max_tries = 3
    current_try = 0
    while current_try < max_tries:
        try:
            async with page.expect_download(timeout=100000) as download_info:
                await page.get_by_role("link", name=link).click()
            download = await download_info.value
            download_path = await download.path()
            assert download_path is not None, "Download failed"

            with open(download_path, "rb") as f:
                content = f.read()
                print(content[:100])

            file_size = os.path.getsize(download_path)
            assert file_size > 0, "File empty"

            return
        except Exception:
            current_try += 1


async def fill_tinymce(page, iframe_id: str, text: str):
    frame_locator = page.frame_locator(f"iframe#{iframe_id}")
    editor = frame_locator.locator("body#tinymce")
    await editor.wait_for(state="visible")
    await editor.fill(text)


async def _checkboxes(page, check=True):
    checkboxes = page.locator('input[type="checkbox"]')
    count = await checkboxes.count()
    for i in range(count):
        checkbox = checkboxes.nth(i)
        if await checkbox.is_visible() and await checkbox.is_enabled():
            if check:
                if not await checkbox.is_checked():
                    await checkbox.check()
            elif await checkbox.is_checked():
                await checkbox.uncheck()
    await page.locator('input[type="submit"][value="Confirm"]').click(force=True)


async def add_links_to_visit(links_to_visit, page, visited_links):
    new_links = await page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")
    for link in new_links:
        if "logout" in link:
            continue
        if link.endswith(("#", "#menu", "#sidebar", "print")):
            continue
        if any(s in link for s in ["features", "pdf", "backup", "upload/template"]):
            continue
        parsed_url = urlparse(link)
        if parsed_url.hostname not in ("localhost", "127.0.0.1"):
            continue
        if link not in visited_links:
            links_to_visit.add(link)
