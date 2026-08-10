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

"""Tests for the rewriting of root-relative urls in email bodies."""

from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.utils.larpmanager.tasks import absolute_email_urls

BASE = "https://test.larpmanager.com"


class TestAbsoluteEmailUrls(BaseTestCase):
    """Test cases for absolute_email_urls"""

    def test_empty_body(self) -> None:
        """Empty bodies are returned untouched"""
        assert absolute_email_urls("", BASE) == ""
        assert absolute_email_urls(None, BASE) is None

    def test_href_and_src(self) -> None:
        """Root-relative href and src attributes are absolutized"""
        body = '<a href="/test/gallery/">go</a><img src="/media/a.png">'
        result = absolute_email_urls(body, BASE)
        assert f'href="{BASE}/test/gallery/"' in result
        assert f'src="{BASE}/media/a.png"' in result

    def test_poster_and_background(self) -> None:
        """Other single-value media attributes are absolutized too"""
        body = '<video poster="/media/p.jpg"></video><td background="/media/b.png"></td>'
        result = absolute_email_urls(body, BASE)
        assert f'poster="{BASE}/media/p.jpg"' in result
        assert f'background="{BASE}/media/b.png"' in result

    def test_absolute_and_protocol_relative_untouched(self) -> None:
        """Already absolute and protocol-relative urls are left alone"""
        body = '<a href="https://other.it/x">a</a><img src="//cdn.it/y.png">'
        assert absolute_email_urls(body, BASE) == body

    def test_anchor_and_mailto_untouched(self) -> None:
        """Non root-relative hrefs are left alone"""
        body = '<a href="#top">a</a><a href="mailto:a@b.it">b</a>'
        assert absolute_email_urls(body, BASE) == body

    def test_srcset_candidates(self) -> None:
        """Every root-relative candidate of a srcset is absolutized"""
        body = '<img srcset="/media/a.png 1x, /media/b.png 2x, https://cdn.it/c.png 3x">'
        result = absolute_email_urls(body, BASE)
        assert f"{BASE}/media/a.png 1x" in result
        assert f"{BASE}/media/b.png 2x" in result
        assert "https://cdn.it/c.png 3x" in result

    def test_srcset_with_data_uri_untouched(self) -> None:
        """A srcset holding a data uri cannot be split, so it is left alone"""
        body = '<img srcset="data:image/png;base64,iVBOR/w0K 1x">'
        assert absolute_email_urls(body, BASE) == body

    def test_inline_style_url(self) -> None:
        """Css url() references inside inline styles are absolutized"""
        body = "<div style=\"background-image: url('/media/bg.png')\"></div>"
        result = absolute_email_urls(body, BASE)
        assert f"url('{BASE}/media/bg.png')" in result

    def test_style_block_url(self) -> None:
        """Css url() references inside style blocks are absolutized"""
        body = "<style>.a { background: url(/media/bg.png); }</style>"
        result = absolute_email_urls(body, BASE)
        assert f"url({BASE}/media/bg.png)" in result

    def test_plain_text_url_untouched(self) -> None:
        """Text outside tags is never rewritten, even when it looks like css"""
        body = "<p>write url(/media/bg.png) to point at the image</p>"
        assert absolute_email_urls(body, BASE) == body

    def test_script_untouched(self) -> None:
        """Script contents are not tags, so they are left alone"""
        body = '<script>var css = "url(/media/bg.png)";</script>'
        assert absolute_email_urls(body, BASE) == body

    def test_greater_than_inside_attribute(self) -> None:
        """A ">" inside a quoted value does not end the tag: later attributes still rewritten"""
        body = '<img alt="a > b" src="/media/a.png">'
        result = absolute_email_urls(body, BASE)
        assert f'src="{BASE}/media/a.png"' in result
        assert 'alt="a > b"' in result

    def test_multiple_attributes_in_one_tag(self) -> None:
        """All url attributes of the same tag are rewritten"""
        body = '<a href="/one/" style="background: url(/media/bg.png)"><img src="/two.png"></a>'
        result = absolute_email_urls(body, BASE)
        assert f'href="{BASE}/one/"' in result
        assert f"url({BASE}/media/bg.png)" in result
        assert f'src="{BASE}/two.png"' in result
