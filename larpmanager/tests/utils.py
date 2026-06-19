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
    page.locator("a#menu-open").first.click()
    page.get_by_role("link", name="Logout").click()


def login_orga(page: Any, live_server: Any) -> None:
    login(page, live_server, orga_user)


def login_user(page: Any, live_server: Any) -> None:
    login(page, live_server, test_user)


def login(page: Any, live_server: Any, name: Any) -> None:
    go_to(page, live_server, "/login")

    page.locator("#id_username").fill(name)
    page.locator("#id_password").fill(password)
    submit_confirm(page)
    expect(page.locator("#banner")).not_to_contain_text("Login")


def handle_error(page: Any, e: Any, test_name: Any) -> NoReturn:
    logger.error("Error on %s: %s\n", test_name, page.url)
    logger.error(e)

    # uid = timezone.now().strftime("%Y%m%d_%H%M%S")
    # page.screenshot(path=f"test_screenshots/{test_name}_{uid}.png")

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
    go_to_check(page, f"{live_server}/{path.lstrip('/')}")

def _wait_lm_ready(page: Any, timeout: int = 3000) -> None:
    page.wait_for_load_state("networkidle", timeout=timeout)
    page.wait_for_load_state("load", timeout=timeout)
    page.wait_for_load_state("domcontentloaded", timeout=timeout)

    try:
        page.wait_for_function("() => window._lmReady === true", timeout=timeout)
    except Exception:
        pass

    ooops_check(page)


def go_to_check(page: Any, path: Any) -> None:
    page.goto(path)
    _wait_lm_ready(page)

def get_request(page: Any, live_server: Any, path: Any) -> dict:
    api_context = page.request
    response = api_context.get(f"{live_server}/{path}")
    assert response.ok
    return response.json()

def submit(page: Any) -> None:
    submit_confirm(page)
    page.wait_for_load_state("load")
    page.wait_for_load_state("domcontentloaded")
    ooops_check(page)


def ooops_check(page: Any) -> None:
    banner = page.locator("#banner")
    if banner.count() > 0:
        try:
            expect(banner).not_to_contain_text("Oops!")
            expect(banner).not_to_contain_text("404")
        except AssertionError:
            raise Exception(f"Error on {page.url}: {banner.inner_text()}")


def check_download(page: Any, link: str, locator: Any = None) -> None:
    max_tries = 3
    current_try = 0

    while current_try < max_tries:
        try:
            with page.expect_download(timeout=100_000) as download_info:
                if locator is not None:
                    locator.click()
                else:
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


def check_pdf_zip_download(page: Any, link: str, locator: Any = None) -> None:
    """Download a ZIP and verify it contains at least one PDF file."""
    max_tries = 3
    current_try = 0
    while current_try < max_tries:
        try:
            with page.expect_download(timeout=100_000) as download_info:
                if locator is not None:
                    locator.click()
                else:
                    page.click(f"text={link}")
            download = download_info.value
            download_path = download.path()
            assert download_path is not None, "Download failed"
            with open(download_path, "rb") as f:
                content = f.read()
            assert zipfile.is_zipfile(io.BytesIO(content)), "Downloaded file is not a ZIP"
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                pdf_members = [m for m in zf.namelist() if m.lower().endswith(".pdf")]
                assert pdf_members, "ZIP contains no PDF files"
            return
        except Exception as err:
            logger.warning("PDF zip download attempt %s/%s failed: %s", current_try + 1, max_tries, err)
            current_try += 1
            if current_try >= max_tries:
                raise


def fill_tinymce(page, iframe_id, text, show = True) -> None:
    """In test setting tinymce is not rendered, just fill the textarea."""

    if show:
        show_link_selector = f'a.my_toggle[tog="f_{iframe_id}"]'
        show_link = page.locator(show_link_selector)
        show_link.wait_for(state="visible")
        show_link.click()

    input_element = page.locator(f'#{iframe_id}')
    input_element.fill(f"<p>{text}</p>", force=True)


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


def submit_confirm(page: Any, container_id: str = None) -> None:
    scope = page
    if container_id:
        scope = page.locator(f"#{container_id}")

    # Ensure any blocking loading screen is gone before searching for elements
    overlay = page.locator("#overlay")
    if overlay.is_visible():
        expect(overlay).to_be_hidden(timeout=5000)

    # Use a generic locator with a regex filter covering both text and role fallbacks
    submit_btn = scope.locator("button, input[type='submit'], a").filter(
        has_text=re.compile(r"^\s*(Confirm|Submit|Conferma|Execute)\s*$", re.IGNORECASE)
    ).first

    submit_btn.scroll_into_view_if_needed()
    expect(submit_btn).to_be_visible()

    # Click normally to ensure actionability, fallback to forced action if styling dictates
    try:
        submit_btn.click(timeout=2000)
    except Exception:
        submit_btn.click(force=True)

    _wait_lm_ready(page, timeout=8000)

def wait_for_inline_edit(page: Any) -> Any:
    page.wait_for_selector("#excel-edit.visible", timeout=10000)
    return page.locator("#excel-edit")


def submit_inline_edit(page: Any) -> None:
    submit_btn = page.get_by_role(
        "button",
        name=re.compile(r"^(Confirm|Submit|Conferma)$", re.IGNORECASE)
    )
    submit_btn.scroll_into_view_if_needed()
    expect(submit_btn).to_be_visible()
    count_before = page.evaluate("() => window._datatablesRefreshCount || 0")
    submit_btn.click(force=True)
    page.wait_for_function(
        f"() => (window._datatablesRefreshCount || 0) > {count_before}",
        timeout=10000,
    )


def save_modal(page: any, frame: Any) -> None:
    submit_btn = frame.get_by_role(
        "button",
        name=re.compile(r"^(Confirm|Submit|Conferma)$", re.IGNORECASE)
    )
    submit_btn.scroll_into_view_if_needed()
    expect(submit_btn).to_be_visible()
    url_before = page.url
    count_before = page.evaluate("() => window._datatablesRefreshCount || 0")
    submit_btn.click(force=True)
    page.wait_for_function(
        f"() => (window._datatablesRefreshCount || 0) > {count_before} || window.location.href !== {repr(url_before)}",
        timeout=10000,
    )


def add_links_to_visit(links_to_visit: Any, page: Any, visited_links: Any) -> None:
    new_links = page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")
    for link in new_links:
        if "logout" in link:
            continue
        if link.endswith(("#", "#menu", "#sidebar", "print", ".jpg")):
            continue
        if any(s in link for s in ["features", "pdf", "backup"]):
            continue
        if re.search(r"/manage/upload/[\w-]+/template/", link):
            continue
        parsed_url = urlparse(link)
        if parsed_url.hostname not in ("localhost", "127.0.0.1"):
            continue
        if link not in visited_links and link not in links_to_visit:
            links_to_visit.append(link)


def check_feature(page: Any, name: Any) -> None:
    block = page.locator(".feature_checkbox").filter(has=page.get_by_text(name, exact=True))
    block.get_by_role("checkbox").check()


def load_image(page: Any, element_id: Any) -> None:
    image_path = Path(__file__).parent / "image.jpg"
    upload(page, element_id, image_path)


def load_image_hidden(page: Any, element_id: str) -> None:
    """Set files on a hidden file input (e.g. inside an avatar dropzone widget)."""
    image_path = Path(__file__).parent / "image.jpg"
    sel = element_id.lstrip("#")
    page.evaluate(f"document.getElementById('{sel}').style.display = 'block'")
    inp = page.locator(element_id)
    inp.set_input_files(str(image_path))


def upload(page: Any, element_id: Any, image_path: Any) -> None:
    inp = page.locator(element_id)
    inp.scroll_into_view_if_needed()
    expect(inp).to_be_visible(timeout=60000)
    inp.set_input_files(str(image_path))


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace by removing newlines and collapsing multiple spaces."""

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line_lower = line.lower()
        # Filter out JavaScript code patterns
        js_patterns = [
            "addeventlistener",
            "preventdefault",
            "window.location",
            ".split(",
            ".href",
            "let ",
            "const ",
            "var ",
        ]
        if line_lower.startswith("document.") or any(pattern in line_lower for pattern in js_patterns):
            continue
        lines.append(line)

    text = " ".join(" ".join(lines).split())

    # Remove pipes separator
    text = text.replace("|", "")
    # Replace newlines and tabs with spaces
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    # Collapse multiple spaces into single space
    text = re.sub(r"\s+", " ", text)
    # Strip leading/trailing whitespace
    return text.strip().lower()

def expect_normalized(page, locator, expected: str, timeout=10000):
    locator.wait_for(state="visible", timeout=timeout)

    page.wait_for_load_state("load")
    page.wait_for_load_state("domcontentloaded")

    raw_parts = []

    # main text element
    raw_parts.append(locator.inner_text() or "")

    # field values
    try:
        field_values = locator.evaluate(
            """(el) => Array.from(el.querySelectorAll('input, textarea, select'))
                .map(f => f.tagName === 'SELECT'
                    ? Array.from(f.selectedOptions).map(o => o.text).join(' ')
                    : f.value)
                .join(' ')"""
        )
        raw_parts.append(field_values or "")
    except:
        pass

    # iframe discendenti (same-origin)
    iframes = locator.locator("iframe")
    count = iframes.count()

    for i in range(count):
        frame_locator = iframes.nth(i).frame_locator(":scope")
        try:
            raw_parts.append(frame_locator.locator("body").inner_text())
        except:
            pass  # iframe non accessibile / cross-origin

    raw = "\n".join(raw_parts)

    actual = normalize_whitespace(raw)
    exp = normalize_whitespace(expected)

    if exp not in actual:
        raise AssertionError(
            "Text mismatch\n\n"
            f"EXPECTED:\n{exp}\n\n"
            f"ACTUAL:\n{actual}"
        )

def just_wait(page, big=False):
    if not hasattr(page, 'wait_for_timeout'):
        return
    wait = 2000 if big else 500
    page.wait_for_timeout(wait)
    page.wait_for_load_state("load")
    page.wait_for_load_state("domcontentloaded")


def wait_accounting_load(page: Any) -> None:
    """Wait until the accounting AJAX call in registrations.html has completed."""
    page.locator("#load_accounting.select").wait_for()


def wait_question_load(page: Any, key: str) -> None:
    """Wait until a specific question column AJAX call in load.js has completed.

    key: the q_uuid / key attribute value on the .load_que link that was clicked.
    """
    page.wait_for_function(f"typeof window.done !== 'undefined' && ('{key}' in window.done)")


def click_and_wait_question(page: Any, name: str) -> None:
    """Click a question column link and wait if it triggers AJAX."""
    load_que = page.locator("a.load_que", has_text=name)
    if load_que.count() > 0:
        key = load_que.get_attribute("key")
        load_que.click()
        wait_question_load(page, key)
    else:
        toggle = page.locator("a.table_toggle", has_text=name)
        tog = toggle.get_attribute("tog")
        page.evaluate("window._tableToggleDone = null")
        toggle.click()
        try:
            page.wait_for_function(f"window._tableToggleDone === '{tog}'", timeout=3000)
        except Exception:
            pass  # column toggle is synchronous; proceed if signal missed


def fill_date(locator, selector, value):
    """Fill a date_p input by setting value via JS, bypassing the datetimepicker popup."""
    locator.locator(selector).evaluate(
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('change', {bubbles: true})); }",
        value,
    )


class FrameLocatorWithPage:
    """Wraps a FrameLocator with the real Page so helpers can call keyboard/wait methods."""

    def __init__(self, frame_locator, page, iframe_locator=None):
        object.__setattr__(self, '_frame', frame_locator)
        object.__setattr__(self, '_real_page', page)
        object.__setattr__(self, '_iframe_locator', iframe_locator)

    def _get_frame(self):
        """Return the actual Frame object for JS evaluation in this iframe's context."""
        if self._iframe_locator is not None:
            return self._iframe_locator.element_handle().content_frame()
        return self._real_page

    def wait_for_function(self, *args, **kwargs):
        return self._get_frame().wait_for_function(*args, **kwargs)

    def evaluate(self, *args, **kwargs):
        return self._get_frame().evaluate(*args, **kwargs)

    def __getattr__(self, name):
        try:
            return getattr(self._frame, name)
        except AttributeError:
            return getattr(self._real_page, name)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)


class InlineOptionRow:
    """Compatibility wrapper for the inline options editor.

    Exposes the same selector API (#id_name, #id_price, ...) that tests used
    with the old modal-iframe flow, mapping it onto one row of the inline
    editor. Fields living in the expandable details row are reached by
    expanding it on demand.
    """

    PRIMARY_FIELDS = {
        "#id_name": "input[name=name]",
        "#id_price": "input[name=price]",
        "#id_max_available": "input[name=max_available]",
    }
    DETAILS_FIELDS = {
        "#id_description": "textarea[name=description]",
    }

    def __init__(self, page, row):
        self.page = page
        self.row = row
        self.details = row.locator("xpath=following-sibling::tr[1]")

    def _ensure_details(self):
        if "hide" in (self.details.get_attribute("class") or ""):
            self.row.locator(".io-toggle-details").click()
            self.page.wait_for_timeout(200)

    def locator(self, selector):
        if selector in self.PRIMARY_FIELDS:
            return self.row.locator(self.PRIMARY_FIELDS[selector])
        # The select2 dropdown is portaled to the page body
        if "select2-results" in selector or "select2-dropdown" in selector:
            return self.page.locator(selector)
        self._ensure_details()
        if selector in self.DETAILS_FIELDS:
            return self.details.locator(self.DETAILS_FIELDS[selector])
        return self.details.locator(selector)

    def get_by_role(self, role, *args, **kwargs):
        # The select2 dropdown is portaled to the page body
        if role == "option":
            return self.page.get_by_role(role, *args, **kwargs)
        self._ensure_details()
        return self.details.get_by_role(role, *args, **kwargs)

    def searchbox(self, field):
        """Return the select2 search field of an M2M column (requirements / tickets)."""
        self._ensure_details()
        container = self.details.locator(
            f"select[name={field}] ~ .select2"
        )
        return container.get_by_role("searchbox")


def new_option(page):
    count_before = page.locator("#inline-options-body tr.inline-option").count()
    page.locator("#inline-options .add-inline-option").click()
    page.locator("#inline-options-body tr.inline-option").nth(count_before).wait_for(state="visible")
    row = page.locator("#inline-options-body tr.inline-option").last
    return InlineOptionRow(page, row)

def get_option(page, uuid):
    """Return the inline editor row for an existing option."""
    row = page.locator(f'#inline-options-body tr.inline-option[data-uuid="{uuid}"]')
    return InlineOptionRow(page, row)

def submit_option(page, option):
    # The inline editor autosaves: blur the fields and wait for the row
    # to receive its uuid (i.e. for the server to confirm the save)
    page.keyboard.press("Tab")
    expect(option.row).to_have_attribute("data-uuid", re.compile(".+"), timeout=10000)


def get_modal_iframe(page):
    iframe_locator = page.locator("#lm-modal iframe")
    iframe_locator.wait_for(state="visible")
    frame_handle = iframe_locator.element_handle()
    if frame_handle:
        frame = frame_handle.content_frame()
        if frame:
            frame.wait_for_load_state("domcontentloaded")
    return FrameLocatorWithPage(iframe_locator.content_frame, page, iframe_locator)


def sidebar(page, link):
    icon_link("#sidebar", page, link)

def icon_link(container, page, link):
    pattern = re.compile(re.escape(link) + "$", re.IGNORECASE)
    page.locator(container).get_by_role("link", name=pattern).click()
    _wait_lm_ready(page)

def nav(page, link):
    icon_link(".nav", page, link)
