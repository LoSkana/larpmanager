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

"""Paced browser actions for guide videos, with screen capture and a caption timeline."""

from __future__ import annotations

import json
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from playwright.sync_api import Locator, Page

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FRAME_RATE = 30

CURSOR_TRAVEL_SECONDS = 0.6
AFTER_CLICK_SECONDS = 0.5
TYPING_DELAY_MS = 55
FIRST_FRAME_TIMEOUT_SECONDS = 10
HIGHLIGHT_LEFT_MARGIN_PIXELS = 8
HIGHLIGHT_RIGHT_MARGIN_PIXELS = 24
DRAG_STEPS = 24
DRAG_STEP_MS = 50
DRAG_THRESHOLD_PIXELS = 8
CLICK_LEAD_SECONDS = 0.3
CAPTION_SAFE_AREA = 0.8
CUT_MARGIN_SECONDS = 0.4
CONFIRM_LEAD_SECONDS = 0.9
ROLE_CARD_SECONDS = 2.2
ROLE_SWITCH_HOLD_SECONDS = 2.0
ROLE_CARD_FADE_SECONDS = 0.4

ORGANIZER = "organizer"
PLAYER = "player"
ROLE_CARDS = {
    ORGANIZER: ("You are the organizer", "Set up events from the admin side", "#12303c"),
    PLAYER: ("Now you are a player", "See what participants do on the site", "#a85a00"),
}

# Drawn in the page because a headless-style capture has no system pointer
CURSOR_SCRIPT = """
(() => {
  if (window.top !== window) return;
  // Popovers share the top layer of modal dialogs, which no z-index can reach
  const float = (element) => {
    element.popover = 'manual';
    Object.assign(element.style, {
      margin: '0', padding: '0', border: '0', background: 'transparent', overflow: 'visible',
      right: 'auto', bottom: 'auto',
    });
    return element;
  };
  const show = (element) => {
    document.documentElement.appendChild(element);
    element.showPopover();
  };
  const build = () => {
    if (window.__guideCursor || !document.body) return;
    // Inside the scrolling wrapper: padding the body would shrink the visible page
    (document.getElementById('wrapper') || document.body).style.paddingBottom = '170px';
    const cursor = float(document.createElement('div'));
    cursor.innerHTML = '<svg width="32" height="32" viewBox="0 0 24 24">'
      + '<path d="M4 2 L4 20 L9 15.5 L12.5 22 L15.5 20.5 L12 14 L18.5 14 Z" '
      + 'fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(cursor.style, {
      position: 'fixed', left: '0', top: '0', width: '32px', height: '32px',
      zIndex: '2147483647', pointerEvents: 'none', willChange: 'transform',
      transition: 'transform 0ms linear',
    });
    show(cursor);
    let lastDialog = null;
    const raise = () => {
      const dialog = document.querySelector('dialog:modal');
      if (dialog === lastDialog) return;
      lastDialog = dialog;
      cursor.hidePopover();
      cursor.showPopover();
      getComputedStyle(cursor).transform;
    };
    let saved = {x: innerWidth / 2, y: innerHeight / 2};
    try { saved = JSON.parse(sessionStorage.getItem('guideCursor')) || saved; } catch (error) {}
    const api = {
      x: saved.x,
      y: saved.y,
      to(x, y, ms) {
        raise();
        this.x = x;
        this.y = y;
        cursor.style.transition = `transform ${ms}ms cubic-bezier(.45,.05,.25,1)`;
        cursor.style.transform = `translate(${x}px, ${y}px)`;
        try { sessionStorage.setItem('guideCursor', JSON.stringify({x, y})); } catch (error) {}
      },
      pulse() {
        const ring = float(document.createElement('div'));
        Object.assign(ring.style, {
          position: 'fixed', left: `${this.x - 22}px`, top: `${this.y - 22}px`,
          width: '44px', height: '44px', borderRadius: '50%',
          background: 'rgba(255, 180, 0, .55)', zIndex: '2147483646', pointerEvents: 'none',
        });
        show(ring);
        ring.animate(
          [{transform: 'scale(.3)', opacity: 1}, {transform: 'scale(1.5)', opacity: 0}],
          {duration: 600, easing: 'ease-out'},
        ).onfinish = () => ring.remove();
      },
      highlight(box, ms) {
        const frame = float(document.createElement('div'));
        Object.assign(frame.style, {
          position: 'fixed', left: `${box.x - 8}px`, top: `${box.y - 8}px`,
          width: `${box.width + 16}px`, height: `${box.height + 16}px`, boxSizing: 'border-box',
          border: '4px solid #ffb400', borderRadius: '10px',
          boxShadow: '0 0 22px 6px rgba(255, 180, 0, .75)',
          zIndex: '2147483646', pointerEvents: 'none',
        });
        show(frame);
        cursor.hidePopover();
        cursor.showPopover();
        frame.animate(
          [{opacity: 0, transform: 'scale(1.15)'}, {opacity: 1, transform: 'scale(1)'}],
          {duration: Math.min(ms, 250), easing: 'ease-out', fill: 'forwards'},
        );
        setTimeout(() => frame.remove(), ms);
      },
      card(title, subtitle, color) {
        const card = float(document.createElement('div'));
        card.id = 'guideRoleCard';
        card.innerHTML = '<div style="font-size:64px;font-weight:700"></div>'
          + '<div style="font-size:30px;margin-top:18px;opacity:.9"></div>';
        card.children[0].textContent = title;
        card.children[1].textContent = subtitle;
        Object.assign(card.style, {
          position: 'fixed', inset: '0', width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', background: color, color: '#fff',
          fontFamily: 'Lato, sans-serif', zIndex: '2147483647', pointerEvents: 'none',
        });
        show(card);
      },
      hideCard(ms) {
        const card = document.getElementById('guideRoleCard');
        card.animate([{opacity: 1}, {opacity: 0}], {duration: ms, fill: 'forwards'}).onfinish = () => card.remove();
      },
    };
    cursor.style.transform = `translate(${api.x}px, ${api.y}px)`;
    window.__guideCursor = api;
  };
  if (document.body) build();
  else document.addEventListener('DOMContentLoaded', build);
})();
"""


class Director:
    """Runs one storyboard: moves a visible cursor, records the screen, logs caption timings."""

    def __init__(self, page: Page, base_url: str, output_dir: Path, title: str, pace: float = 1.0) -> None:
        """Bind to a browser page and prepare the output directory; a lower pace means quicker actions."""
        self.page = page
        self.base_url = base_url
        self.output_dir = output_dir
        self.title = title
        self.pace = pace
        self.captions: list[dict[str, Any]] = []
        self.cuts: list[list[float]] = []
        self._recorder: subprocess.Popen | None = None
        self._started_at = 0.0
        self._open_caption: dict[str, Any] | None = None
        self._open_role: dict[str, Any] | None = None
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _wait(self, seconds: float) -> None:
        """Pause for a duration scaled by the storyboard pace."""
        time.sleep(seconds * self.pace)

    def _now(self) -> float:
        """Return seconds elapsed in the raw recording."""
        return time.monotonic() - self._started_at

    def start(self) -> None:
        """Start capturing the virtual display."""
        raw_path = self.output_dir / "raw.mkv"
        raw_path.unlink(missing_ok=True)
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "x11grab", "-draw_mouse", "0",
            "-framerate", str(FRAME_RATE),
            "-video_size", f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}",
            "-i", os.environ["DISPLAY"],
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "14", "-pix_fmt", "yuv420p",
            str(raw_path),
        ]  # fmt: skip
        self._recorder = subprocess.Popen(command, stdin=subprocess.PIPE)  # noqa: S603
        deadline = time.monotonic() + FIRST_FRAME_TIMEOUT_SECONDS
        while not raw_path.exists() or raw_path.stat().st_size == 0:
            if time.monotonic() > deadline or self._recorder.poll() is not None:
                msg = "Screen capture did not start"
                raise RuntimeError(msg)
            time.sleep(0.02)
        self._started_at = time.monotonic()

    def stop(self) -> None:
        """Stop capturing and write the timeline used by the compositor."""
        self._close_caption()
        self._close_role()
        duration = self._now()
        if self._recorder:
            self._recorder.communicate(input=b"q", timeout=30)
            self._recorder = None
        timeline ={"title": self.title, "duration": duration, "captions": self.captions, "cuts": self.cuts}
        (self.output_dir / "timeline.json").write_text(json.dumps(timeline, indent=2))

    def abort(self) -> None:
        """Stop a capture left running by a failed storyboard."""
        if self._recorder:
            self._recorder.terminate()
            self._recorder.wait(timeout=30)
            self._recorder = None

    def _close_caption(self) -> None:
        """Close the caption on screen, if any."""
        if self._open_caption:
            self._open_caption["end"] = self._now()
            self._open_caption = None

    def _close_role(self) -> None:
        """Close the role badge on screen, if any."""
        if self._open_role:
            self._open_role["end"] = self._now()
            self._open_role = None

    def play_as(self, role: str, prepare: Callable[[], None] | None = None) -> None:
        """Leave the last screen visible, switch role off camera, then announce it with a card and a corner badge."""
        title, subtitle, color = ROLE_CARDS[role]
        if self._open_role:
            self.hold(ROLE_SWITCH_HOLD_SECONDS)
        self._close_caption()
        self._close_role()
        with self.off_camera():
            if prepare:
                prepare()
            self.page.evaluate(
                "([title, subtitle, color]) => window.__guideCursor.card(title, subtitle, color)",
                [title, subtitle, color],
            )
        label = f"{role.capitalize()} view"
        self._open_role = {"start": self._now(), "end": None, "text": label, "kind": f"role_{role}"}
        self.captions.append(self._open_role)
        self._wait(ROLE_CARD_SECONDS)
        self.page.evaluate("(ms) => window.__guideCursor.hideCard(ms)", int(ROLE_CARD_FADE_SECONDS * 1000))
        time.sleep(ROLE_CARD_FADE_SECONDS + 0.2)

    def _open(self, text: str, kind: str) -> None:
        """Replace the caption on screen."""
        self._close_caption()
        self._open_caption = {"start": self._now(), "end": None, "text": text, "kind": kind}
        self.captions.append(self._open_caption)

    def step(self, text: str, seconds: float = 2.2) -> None:
        """Show a step heading, kept on screen alone for a moment."""
        self._open(text, "step")
        self._wait(seconds)
        self._close_caption()

    def say(self, text: str) -> None:
        """Show a caption, kept until the next one."""
        self._open(text, "caption")

    def hold(self, seconds: float) -> None:
        """Keep the current screen visible."""
        time.sleep(seconds)

    @contextmanager
    def off_camera(self) -> Generator[None, None, None]:
        """Remove the enclosed actions from the final video."""
        resumed = self._open_caption
        self._close_caption()
        cut_start = self._now()
        time.sleep(CUT_MARGIN_SECONDS)
        yield
        self._ready_page()
        time.sleep(CUT_MARGIN_SECONDS)
        self.cuts.append([cut_start, self._now()])
        if resumed:
            self._open(resumed["text"], resumed["kind"])

    def _ready_page(self) -> None:
        """Wait for the page to settle."""
        self.page.wait_for_load_state("load")

    def goto(self, path: str) -> None:
        """Open a path of the site."""
        self.page.goto(f"{self.base_url}/{path.lstrip('/')}")
        self._ready_page()

    def _point_at(self, target: Locator) -> None:
        """Glide the cursor over the target element."""
        target.scroll_into_view_if_needed()
        box = target.bounding_box()
        if not box:
            msg = f"Target has no visible box: {target}"
            raise RuntimeError(msg)
        if box["y"] + box["height"] > self.page.evaluate("() => innerHeight") * CAPTION_SAFE_AREA:
            target.evaluate("(element) => element.scrollIntoView({block: 'center'})")
            box = target.bounding_box()
        horizontal = box["x"] + min(box["width"] / 2, 60)
        vertical = box["y"] + box["height"] / 2
        self.page.evaluate(
            "([x, y, ms]) => window.__guideCursor && window.__guideCursor.to(x, y, ms)",
            [horizontal, vertical, int(CURSOR_TRAVEL_SECONDS * self.pace * 1000)],
        )
        self._wait(CURSOR_TRAVEL_SECONDS + 0.1)

    def _pulse(self) -> None:
        """Mark a click on screen."""
        self.page.evaluate("() => window.__guideCursor && window.__guideCursor.pulse()")

    def click(self, target: Locator, *, settle: float = AFTER_CLICK_SECONDS) -> None:
        """Move to the target and click it."""
        self._point_at(target)
        self._pulse()
        self._wait(CLICK_LEAD_SECONDS)
        target.click()
        self._ready_page()
        self._wait(settle)

    def confirm(self, target: Locator, *, settle: float = AFTER_CLICK_SECONDS) -> None:
        """Highlight a submit button and click it, before the page navigates away."""
        self._point_at(target)
        lead_ms = int((CONFIRM_LEAD_SECONDS + CLICK_LEAD_SECONDS) * self.pace * 1000)
        self.page.evaluate(
            "([box, ms]) => window.__guideCursor.highlight(box, ms)",
            [target.bounding_box(), lead_ms],
        )
        self._wait(CONFIRM_LEAD_SECONDS)
        self._pulse()
        self._wait(CLICK_LEAD_SECONDS)
        target.click()
        self._ready_page()
        self._wait(settle)

    def drag(self, source: Locator, target: Locator) -> None:
        """Drag a handle onto a target, with the cursor following the real mouse."""
        self._point_at(source)
        source_box = source.bounding_box()
        target_box = target.bounding_box()
        horizontal = source_box["x"] + source_box["width"] / 2
        start = source_box["y"] + source_box["height"] / 2
        end = target_box["y"] + target_box["height"] / 2
        self.page.mouse.move(horizontal, start)
        self._pulse()
        self.page.mouse.down()
        self._wait(CLICK_LEAD_SECONDS)
        self.page.mouse.move(horizontal, start + DRAG_THRESHOLD_PIXELS, steps=5)
        for step in range(1, DRAG_STEPS + 1):
            vertical = start + (end - start) * step / DRAG_STEPS
            self.page.mouse.move(horizontal, vertical)
            self.page.evaluate(
                "([x, y, ms]) => window.__guideCursor && window.__guideCursor.to(x, y, ms)",
                [horizontal, vertical, DRAG_STEP_MS],
            )
            self.page.wait_for_timeout(DRAG_STEP_MS)
        self.page.mouse.up()
        self._ready_page()
        self._wait(AFTER_CLICK_SECONDS)

    def spotlight(self, target: Locator, seconds: float) -> None:
        """Point at an element and highlight it, without clicking."""
        self._point_at(target)
        self.page.evaluate(
            "([box, ms]) => window.__guideCursor.highlight(box, ms)",
            [self._box_within_content(target), int(seconds * 1000)],
        )
        time.sleep(seconds)

    def _box_within_content(self, target: Locator) -> dict[str, float]:
        """Return the box of the target, kept clear of the sidebar and of the window edge."""
        box = target.bounding_box()
        content = self.page.locator("#page-wrapper").bounding_box()
        left = max(box["x"], content["x"] + HIGHLIGHT_LEFT_MARGIN_PIXELS)
        right = min(box["x"] + box["width"], content["x"] + content["width"] - HIGHLIGHT_RIGHT_MARGIN_PIXELS)
        return {**box, "x": left, "width": right - left}

    def check(self, target: Locator) -> None:
        """Move to a checkbox and tick it."""
        self._point_at(target)
        self._pulse()
        target.check()
        self._wait(AFTER_CLICK_SECONDS)

    def select(self, target: Locator, value: str) -> None:
        """Move to a native select and choose a value."""
        self._point_at(target)
        self._pulse()
        target.select_option(value)
        self._wait(AFTER_CLICK_SECONDS)

    def fill(self, target: Locator, text: str) -> None:
        """Fill a field at once, for details already shown earlier in the video."""
        target.fill(text)
        self._wait(0.15)

    def type(self, target: Locator, text: str) -> None:
        """Move to a field and type into it, one key at a time."""
        self._point_at(target)
        self._pulse()
        target.evaluate("(element) => element.setAttribute('autocomplete', 'off')")
        target.click()
        target.fill("")
        target.press_sequentially(text, delay=TYPING_DELAY_MS)
        self._wait(AFTER_CLICK_SECONDS)
