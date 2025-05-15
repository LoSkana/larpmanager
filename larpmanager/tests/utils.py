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
import time
from datetime import datetime

import pytest
from django.utils.translation import activate
from playwright.sync_api import expect

password = "banana"
orga_user = "orga@test.it"
test_user = "user@test.it"


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    result = outcome.get_result()
    setattr(item, f"rep_{result.when}", result)


@pytest.fixture(scope="function", autouse=True)
def handle_video_and_screenshot(request, page):
    yield  # Run the test

    test_name = request.node.name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    video_path = None
    try:
        video_path = page.video.path()
    except Exception:
        pass  # Ignore if video is unavailable

    if request.node.rep_call.failed:
        # Test failed → save screenshot and video
        os.makedirs("test_screenshots", exist_ok=True)
        os.makedirs("test_videos", exist_ok=True)

        screenshot_file = f"test_screenshots/{test_name}_{timestamp}.png"
        page.screenshot(path=screenshot_file)

        if video_path and os.path.exists(video_path):
            try:
                new_video_path = f"test_videos/{test_name}_{timestamp}.webm"
                os.rename(video_path, new_video_path)
            except Exception as e:
                print(f"[!] Failed to save video: {e}")
    # Test passed → delete the video
    elif video_path and os.path.exists(video_path):
        try:
            os.remove(video_path)
        except Exception as e:
            print(f"[!] Failed to delete video: {e}")


def page_start(p, show=False):
    browser = p.chromium.launch(headless=not show)
    context = browser.new_context(record_video_dir="test_videos")
    page = context.new_page()

    page.set_default_timeout(60000)

    page.on("dialog", lambda dialog: dialog.accept())

    def on_response(response):
        error_code = 500
        if response.status == error_code:
            raise Exception(f"500 on {response.url}")

    page.on("response", on_response)

    activate("en")
    return browser, context, page


def logout(page, live_server):
    page.locator("a#menu-open").click()
    page.get_by_role("link", name="Logout").click()


def login_orga(pg, ls):
    login(pg, ls, orga_user)


def login_user(pg, lv):
    login(pg, lv, test_user)


def login(pg, live_server, name):
    go_to(pg, live_server, "/login")

    pg.locator("#id_username").fill(name)
    pg.locator("#id_password").fill(password)
    pg.get_by_role("button", name="Submit").click()
    expect(pg.locator("#banner")).not_to_contain_text("Login")


def handle_error(page, e, test_name):
    print(f"Error on {test_name}: {page.url}\n")
    print(e)
    raise (e)


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
    go_to_check(page, f"{live_server.url}/{path}")


def go_to_check(page, path):
    page.goto(path)
    ooops_check(page)


def submit(page):
    page.get_by_role("button", name="Submit").click()
    page.wait_for_load_state("networkidle")
    ooops_check(page)


def ooops_check(page):
    banner = page.locator("#banner")
    if banner.count() > 0:
        expect(banner).not_to_contain_text("Oops!")
        expect(banner).not_to_contain_text("404")


def check_download(page, link):
    max_tries = 3
    current_try = 0
    while current_try < max_tries:
        try:
            with page.expect_download(timeout=100000) as download_info:
                page.get_by_role("link", name=link).click()
            download_path = download_info.value.path()
            assert download_path is not None, "Download failed"

            with open(download_path, "rb") as f:
                content = f.read()
                print(content[:100])

            file_size = os.path.getsize(download_path)
            assert file_size > 0, "File empty"

            return
        except Exception:
            current_try += 1


def fill_tinymce(iframe_locator, value):
    iframe_locator.wait_for(state="visible")

    frame = iframe_locator.content_frame

    timeout = time.time() + 30
    while frame is None:
        if time.time() > timeout:
            raise TimeoutError("Iframe not available")
        time.sleep(0.1)
        frame = iframe_locator.content_frame

    rich_text = frame.locator('[aria-label="Rich Text Area"]')
    rich_text.wait_for(state="visible")
    rich_text.fill(value)


def _checkboxes(page, check=True):
    checkboxes = page.locator('input[type="checkbox"]')
    count = checkboxes.count()
    for i in range(count):
        checkbox = checkboxes.nth(i)
        if check:
            if not checkbox.is_checked():
                checkbox.check()
        elif checkbox.is_checked():
            checkbox.uncheck()
    page.get_by_role("button", name="Confirm").click()
