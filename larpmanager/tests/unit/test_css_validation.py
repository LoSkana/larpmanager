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
"""Tests for PDF stylesheet validation."""

from __future__ import annotations

import pytest
from django import forms

from larpmanager.forms.utils import validate_css

# Test CSS
PAGE_CSS = """@page {
    size: A4;
    background: url('#0tmbrrhg05jl2uqjn#');
@frame content_frame { margin: 2cm; }
}

h1, h2, h3 {
    font-family: 'Cinzel', 'Trajan Pro', 'Georgia', serif;
    color: #c82323;
    text-transform: uppercase;
    text-align: center;
    letter-spacing: 2px;
    margin-bottom: 10px;
    border-bottom: 1px solid #4a0d0d;
    padding-bottom: 5px;
}

body {
    font-family: 'Georgia', 'Times New Roman', serif;
    color: #d4c3a3;
    font-size: 11pt;
    line-height: 1.5;
}

a, a:link, a:visited {
    color: #8b0000;
    text-decoration: none;
    font-weight: bold;
}

h1 {
    font-size: 22pt;
    color: #e62e2e;
}

h2 {
    font-size: 16pt;
    color: #d4a359;
}
"""


class TestValidateCssAccepts:
    """Stylesheets that organizers legitimately configure must pass validation."""

    def test_event_page_css(self) -> None:
        """A full event stylesheet with @page, @frame and a utility-code background is valid."""
        validate_css(PAGE_CSS)

    @pytest.mark.parametrize(
        "css",
        [
            "",
            "h1 { color: red; }",
            "@page { size: A4; margin: 2cm; }",
            "@page { @frame content_frame { margin: 2cm; } }",
            'h1 { content: "}"; color: red; }',
            "h1 { color: red; } /* } */",
            r'h1 { content: "\"}"; }',
            "h1 { color: red;",
        ],
    )
    def test_valid_css(self, css: str) -> None:
        """Braces inside strings and comments, and unclosed blocks, are not stray closers."""
        validate_css(css)


class TestValidateCssRejects:
    """Stray closing braces make xhtml2pdf's parser loop forever, so they must be refused."""

    @pytest.mark.timeout(30)
    @pytest.mark.parametrize(
        "css",
        [
            "}",
            "h1{color:red}}}",
            "h1 { color: ; font-size: }}}",
            "@page { size: A4; } }",
            'h1 { content: "{"; } }',
        ],
    )
    def test_stray_closing_brace(self, css: str) -> None:
        """Validation raises instead of hanging the worker."""
        with pytest.raises(forms.ValidationError):
            validate_css(css)
