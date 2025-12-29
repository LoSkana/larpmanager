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
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse

import pandas as pd
from django.utils import timezone
from playwright.sync_api import expect

logger = logging.getLogger(__name__)

password = "banana"
orga_user = "orga@test.it"
test_user = "user@test.it"


def logout(page: Any) -> None:
    page.locator("a#menu-open").click()
    page.get_by_role("link", name="Logout").click()


def login_orga(page: Any, live_server: Any) -> None:
    login(page, live_server, orga_user)


def login_user(page: Any, live_server: Any) -> None:
    login(page, live_server, test_user)


def login(page: Any, live_server: Any, name: Any) -> None:
    go_to(page, live_server, "/login")

    page.locator("#id_username").fill(name)
    page.locator("#id_password").fill(password)
    page.get_by_role("button", name="Submit").click()
    expect(page.locator("#banner")).not_to_contain_text("Login")


def handle_error(page: Any, e: Any, test_name: Any) -> NoReturn:
    logger.error("Error on %s: %s\n", test_name, page.url)
    logger.error(e)

    uid = timezone.now().strftime("%Y%m%d_%H%M%S")
    page.screenshot(path=f"test_screenshots/{test_name}_{uid}.png")

    raise e


def print_text(page: Any) -> None:
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

    logger.debug(visible_text)


def go_to(page: Any, live_server: Any, path: Any) -> None:
    go_to_check(page, f"{live_server}/{path}")


def go_to_check(page: Any, path: Any) -> None:
    page.goto(path)
    page.wait_for_load_state("load")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_load_state("networkidle")
    ooops_check(page)


def submit(page: Any) -> None:
    page.get_by_role("button", name="Submit").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_load_state("load")
    ooops_check(page)


def ooops_check(page: Any) -> None:
    banner = page.locator("#banner")
    if banner.count() > 0:
        expect(banner).not_to_contain_text("Oops!")
        expect(banner).not_to_contain_text("404")


def check_download(page: Any, link: str) -> None:
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
            lower_name = str(Path(download.suggested_filename or download_path).name.lower())
            if lower_name.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(content))
                assert not df.empty, f"Empty csv {lower_name}"
                return

            return

        except Exception as err:
            logger.warning("Download attempt %s/%s failed: %s", current_try + 1, max_tries, err)
            current_try += 1
            if current_try >= max_tries:
                raise


def fill_tinymce(page: Any, iframe_id: Any, text: Any, show: Any = True, timeout: Any = 10000) -> None:
    page.wait_for_load_state("load")
    page.wait_for_load_state("domcontentloaded")

    if show:
        show_link_selector = f'a.my_toggle[tog="f_{iframe_id}"]'
        page.wait_for_selector(show_link_selector, timeout=timeout)
        show_link = page.locator(show_link_selector)
        show_link.wait_for(state="attached", timeout=timeout)
        show_link.scroll_into_view_if_needed()
        show_link.click()

    # Wait for TinyMCE to initialize the editor instance
    page.wait_for_function(
        """(id) => window.tinymce && tinymce.get(id) && tinymce.get(id).initialized === true""",
        arg=iframe_id,
        timeout=timeout,
    )

    # Set content via TinyMCE API and mark dirty/change
    page.evaluate(
        """([id, html]) => {
            const ed = tinymce.get(id);
            ed.setContent(html);
            ed.fire('change');
            ed.undoManager.add();
        }""",
        [iframe_id, text],
    )


def _checkboxes(page: Any, check: Any = True) -> None:
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

    submit_confirm(page)


def submit_confirm(page: Any) -> None:
    submit_btn = page.get_by_role("button", name="Confirm", exact=True)
    submit_btn.scroll_into_view_if_needed()
    expect(submit_btn).to_be_visible()
    submit_btn.click()


def add_links_to_visit(links_to_visit: Any, page: Any, visited_links: Any) -> None:
    new_links = page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")
    for link in new_links:
        if "logout" in link:
            continue
        if link.endswith(("#", "#menu", "#sidebar", "print", ".jpg")):
            continue
        if any(s in link for s in ["features", "pdf", "backup", "upload/template"]):
            continue
        parsed_url = urlparse(link)
        if parsed_url.hostname not in ("localhost", "127.0.0.1"):
            continue
        if link not in visited_links:
            links_to_visit.add(link)


def check_feature(page: Any, name: Any) -> None:
    block = page.locator(".feature_checkbox").filter(has=page.get_by_text(name, exact=True))
    block.get_by_role("checkbox").check()


def load_image(page: Any, element_id: Any) -> None:
    image_path = Path(__file__).parent / "image.jpg"
    upload(page, element_id, image_path)


def upload(page: Any, element_id: Any, image_path: Any) -> None:
    inp = page.locator(element_id)
    inp.scroll_into_view_if_needed()
    expect(inp).to_be_visible(timeout=60000)
    inp.set_input_files(str(image_path))


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace by removing newlines and collapsing multiple spaces."""

    # Replace newlines and tabs with spaces
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    # Collapse multiple spaces into single space
    text = re.sub(r"\s+", " ", text)
    # Strip leading/trailing whitespace
    return text.strip()


def expect_normalized_text(locator: Any, expected_text: str) -> None:
    """Assert that locator contains expected text after normalizing whitespace."""
    actual_text = locator.inner_text()
    normalized_actual = normalize_whitespace(actual_text)
    normalized_expected = normalize_whitespace(expected_text)

    assert normalized_expected in normalized_actual, (
        f"Expected text not found.\n"
        f"Expected (normalized): {normalized_expected}\n"
        f"Actual (normalized): {normalized_actual}"
    )
