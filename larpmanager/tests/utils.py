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

import io
import os
import zipfile
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
from playwright.sync_api import expect

password = "banana"
orga_user = "orga@test.it"
test_user = "user@test.it"


def logout(page):
    page.locator("a#menu-open").click()
    page.get_by_role("link", name="Logout").click()


def login_orga(page, live_server):
    login(page, live_server, orga_user)


def login_user(page, live_server):
    login(page, live_server, test_user)


def login(page, live_server, name):
    go_to(page, live_server, "/login")

    page.locator("#id_username").fill(name)
    page.locator("#id_password").fill(password)
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#banner")).not_to_contain_text("Login")


def handle_error(page, e, test_name):
    print(f"Error on {test_name}: {page.url}\n")
    print(e)

    uid = datetime.now().strftime("%Y%m%d_%H%M%S")
    page.screenshot(path=f"test_screenshots/{test_name}_{uid}.png")

    raise e


def print_text(page):
    visible_text = page.evaluate("""
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


def go_to(page, live_server, path):
    go_to_check(page, f"{live_server}/{path}")


def go_to_check(page, path):
    page.goto(path)
    ooops_check(page)


def submit(page):
    page.get_by_role("button", name="Submit").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_load_state("load")
    ooops_check(page)


def ooops_check(page):
    banner = page.locator("#banner")
    if banner.count() > 0:
        expect(banner).not_to_contain_text("Oops!")
        expect(banner).not_to_contain_text("404")


def check_download(page, link: str) -> None:
    max_tries = 3
    current_try = 0

    while current_try < max_tries:
        try:
            with page.expect_download(timeout=100_000) as download_info:
                page.click(f"text={link}")
            download = download_info.value
            download_path = download.path()
            assert download_path is not None, "Download failed"

            with open(download_path, "rb") as f:
                content = f.read()

            file_size = os.path.getsize(download_path)
            assert file_size > 0, "File empty"

            # handle zip: extract CSVs, read with pandas
            if zipfile.is_zipfile(io.BytesIO(content)) or zipfile.is_zipfile(download_path):
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    csv_members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
                    assert csv_members, "ZIP contains no CSV files"
                    for member in csv_members:
                        with zf.open(member) as f:
                            df = pd.read_csv(f)
                            assert not df.empty, f"Empty csv {member}"
                return

            # if plain CSV, read with pandas
            lower_name = str(os.path.basename(download.suggested_filename or download_path).lower())
            if lower_name.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(content))
                assert not df.empty, f"Empty csv {lower_name}"
                return

            return

        except Exception as err:
            print(err)
            current_try += 1
            if current_try >= max_tries:
                raise


def fill_tinymce(page, iframe_id, text):
    page.wait_for_timeout(2000)
    locator = page.locator(f'a.my_toggle[tog="f_{iframe_id}"]')
    if locator.count() > 0:
        locator.click()
    page.wait_for_timeout(2000)
    frame_locator = page.frame_locator(f"iframe#{iframe_id}_ifr")
    editor = frame_locator.locator("body#tinymce")
    editor.wait_for(state="visible")
    editor.fill(text)
    page.wait_for_timeout(2000)


def _checkboxes(page, check=True):
    checkboxes = page.locator('input[type="checkbox"]')
    count = checkboxes.count()
    for i in range(count):
        checkbox = checkboxes.nth(i)
        if checkbox.is_visible() and checkbox.is_enabled():
            if check:
                if not checkbox.is_checked():
                    checkbox.check()
            elif checkbox.is_checked():
                checkbox.uncheck()
    page.locator('input[type="submit"][value="Confirm"]').click(force=True)


def add_links_to_visit(links_to_visit, page, visited_links):
    new_links = page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")
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
