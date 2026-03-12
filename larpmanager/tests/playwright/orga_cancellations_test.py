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

"""Test: Organizer cancellation list and refund workflow.

Verifies that cancelled registrations with real token/credit payments appear in
the cancellations list and that the refund form correctly processes token-only
and mixed token+credit refunds, checking the resulting accounting entries.

Important ordering: tokens/credits must be added AFTER the member registers,
because RunMemberS2Widget only shows members with active registrations.
The post_save signal on AccountingItemOther triggers auto-apply of tokens/credits
to incomplete registrations, creating AccountingItemPayment records automatically.

Accounting page check: the "Delivered" section (hidden by default) lists all
AccountingItemOther(oth=TOKEN/CREDIT) items; clicking the toggle reveals it.
The refund entry has descr="Refund" so we filter by that text and verify value.

Refund math (70% return rate):
  - user@test.it: 17 tokens + 19 credits paid = 36 total
    typ_t → ceil(36*0.7)=26 tokens returned
  - orga@test.it: 10 tokens + 8 credits paid = 18 total
    typ_c → rest=ceil(18*0.7)=13; token=min(13,10)=10; credit=13-10=3
"""

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import (
    expect_normalized,
    go_to,
    just_wait,
    login_orga,
    login_user,
    submit_confirm,
)

pytestmark = pytest.mark.e2e

# Token/credit amounts per scenario
USER_TOKENS = 17
USER_CREDITS = 19
ORGA_TOKENS = 10
ORGA_CREDITS = 8

# Expected refund amounts at 70% return
USER_TOKEN_REFUND = 26  # ceil((17+19)*0.7)=26, typ_t: all in tokens
ORGA_TOKEN_REFUND = 10  # min(13, 10)
ORGA_CREDIT_REFUND = 3  # ceil(18*0.7)=13 - 10 tokens = 3 credits


def test_orga_cancellations(pw_page: Any) -> None:
    """Test cancellation list and token/credit refund workflows with real payments."""
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    setup(live_server, page)

    refund_with_tokens(live_server, page)

    refund_with_credits(live_server, page)


def setup(live_server: Any, page: Any) -> None:
    """Enable tokens/credits features and set ticket price to 100."""
    go_to(page, live_server, "/manage/features/tokens/on")
    go_to(page, live_server, "/manage/features/credits/on")

    go_to(page, live_server, "/test/manage/tickets")
    page.wait_for_selector("table.go_datatable")
    page.wait_for_selector(".fa-edit", timeout=10000)
    page.locator(".fa-edit").click(force=True)
    page.locator("#id_price").fill("100.00")
    submit_confirm(page)


def _add_event_tokens(live_server: Any, page: Any, member_search: str, member_option: str, value: int) -> None:
    """Add event-level token accounting item; member must already be registered."""
    go_to(page, live_server, "/test/manage/tokens")
    page.get_by_role("link", name="New").click()
    page.locator("#select2-id_member-container").click()
    page.get_by_role("searchbox").fill(member_search)
    page.get_by_role("option", name=member_option).click()
    page.locator("#id_value").fill(str(value))
    page.locator("#id_descr").fill("test")
    submit_confirm(page)


def _add_event_credits(live_server: Any, page: Any, member_search: str, member_option: str, value: int) -> None:
    """Add event-level credit accounting item; member must already be registered."""
    go_to(page, live_server, "/test/manage/credits")
    page.get_by_role("link", name="New").click()
    page.get_by_text("---------").click()
    page.get_by_role("searchbox").fill(member_search)
    page.get_by_role("option", name=member_option).click()
    page.locator("#id_value").fill(str(value))
    page.locator("#id_descr").fill("test")
    submit_confirm(page)


def _cancel_first_active_registration(live_server: Any, page: Any) -> None:
    """Cancel the first active registration shown in the organizer panel."""
    go_to(page, live_server, "/test/manage/registrations")
    just_wait(page)
    page.locator("a:has(i.fas.fa-trash)").first.click(force=True)
    just_wait(page)


def refund_with_tokens(live_server: Any, page: Any) -> None:
    """Register as user@test.it, add tokens+credits, cancel, refund 70% as tokens only."""
    # Register as user
    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Login as orga and assign tokens/credits for user@test.it.
    login_orga(page, live_server)
    _add_event_tokens(live_server, page, "user", "User Test - user@test.it", USER_TOKENS)
    _add_event_credits(live_server, page, "user", "User Test - user@test.it", USER_CREDITS)

    # Cancel user's registration
    _cancel_first_active_registration(live_server, page)

    # Go to cancellations list
    go_to(page, live_server, "/test/manage/cancellations/")
    just_wait(page)
    expect(page.locator("#cancellations")).to_be_visible()

    approve_link = page.get_by_role("link", name="Approve reimbursement")
    expect(approve_link).to_be_visible()
    approve_link.click()
    page.wait_for_load_state("load")

    # Refund form: payment cells show actual paid amounts from tokens / credits
    expect_normalized(page, page.locator("#pay_token"), str(USER_TOKENS))
    expect_normalized(page, page.locator("#pay_credit"), str(USER_CREDITS))

    # Select "Only tokens" type and 70% — JS computes inp_token=26, inp_credit=0
    expect(page.locator("#typ_t")).to_be_visible()
    page.locator("#typ_t").click()
    page.locator("#p_7").click()
    just_wait(page)

    # Verify JS computed the correct token refund amount
    expect_normalized(page, page.locator("#ref_token"), str(USER_TOKEN_REFUND))

    submit_confirm(page)

    # Back on cancellations: shows "Refunded", no more approve link
    just_wait(page)
    expect(page.locator("#cancellations")).to_contain_text("Refunded")
    expect(page.get_by_role("link", name="Approve reimbursement")).not_to_be_visible()

    # Verify token refund accounting entry created for user
    go_to(page, live_server, "/test/manage/tokens")
    just_wait(page)
    refund_row = page.get_by_role("row", name=re.compile(r"User Test.*Refund"))
    expect(refund_row).to_be_visible()
    expect(refund_row).to_contain_text(str(USER_TOKEN_REFUND))

    # Check user personal accounting
    login_user(page, live_server)
    go_to(page, live_server, "/accounting/tokens/")
    page.get_by_role("link", name="Delivered").click()
    just_wait(page)
    refund_row = page.get_by_role("row").filter(has_text="Refund")
    expect_normalized(page, refund_row, str(USER_TOKEN_REFUND))
    go_to(page, live_server, "/accounting/")
    expect_normalized(page, page.locator("#one"), "Total: " + str(USER_TOKEN_REFUND))
    login_orga(page, live_server)


def refund_with_credits(live_server: Any, page: Any) -> None:
    """Register orga as participant, add tokens+credits, cancel, refund 70% as mixed.

    Expected: rest=ceil(18*0.7)=13; token=min(13,10)=10; credit=13-10=3
    """
    # Orga registers for the event as a participant
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Add tokens and credits for orga@test.it (now registered, visible in dropdown)
    _add_event_tokens(live_server, page, "org", "Admin Test - orga@test.it", ORGA_TOKENS)
    _add_event_credits(live_server, page, "org", "Admin Test - orga@test.it", ORGA_CREDITS)

    # Cancel orga's registration
    _cancel_first_active_registration(live_server, page)

    # Cancellations list: user row shows "Refunded", orga row has the approve link
    go_to(page, live_server, "/test/manage/cancellations/")
    just_wait(page)

    approve_link = page.get_by_role("link", name="Approve reimbursement")
    expect(approve_link).to_be_visible()
    approve_link.click()
    page.wait_for_load_state("load")

    # Refund form: payment cells reflect orga's actual payments
    expect_normalized(page, page.locator("#pay_token"), str(ORGA_TOKENS))
    expect_normalized(page, page.locator("#pay_credit"), str(ORGA_CREDITS))

    # Select "tokens + credits" type and 70% — JS computes inp_token=10, inp_credit=3
    expect(page.locator("#typ_c")).to_be_visible()
    page.locator("#typ_c").click()
    page.locator("#p_7").click()
    just_wait(page)

    # Verify JS computed the correct split
    expect_normalized(page, page.locator("#ref_token"), str(ORGA_TOKEN_REFUND))
    expect_normalized(page, page.locator("#ref_credit"), str(ORGA_CREDIT_REFUND))

    submit_confirm(page)

    # Back on cancellations: both registrations now show "Refunded"
    just_wait(page)
    refunded_cells = page.locator("#cancellations td", has_text="Refunded")
    expect(refunded_cells).to_have_count(2)
    expect(page.get_by_role("link", name="Approve reimbursement")).not_to_be_visible()

    # Verify token refund accounting entry for orga@test.it
    go_to(page, live_server, "/test/manage/tokens")
    just_wait(page)
    token_refund_row = page.get_by_role("row", name=re.compile(r"Admin Test.*Refund"))
    expect(token_refund_row).to_be_visible()
    expect(token_refund_row).to_contain_text(str(ORGA_TOKEN_REFUND))

    # Verify credit refund accounting entry for orga@test.it
    go_to(page, live_server, "/test/manage/credits")
    just_wait(page)
    credit_refund_row = page.get_by_role("row", name=re.compile(r"Admin Test.*Refund"))
    expect(credit_refund_row).to_be_visible()
    expect(credit_refund_row).to_contain_text(str(ORGA_CREDIT_REFUND))

    # Check orga personal accounting: token refund row in Delivered section
    go_to(page, live_server, "/accounting/tokens/")
    page.get_by_role("link", name="Delivered").click()
    just_wait(page)
    token_refund_row = page.get_by_role("row").filter(has_text="Refund")
    expect_normalized(page, token_refund_row, str(ORGA_TOKEN_REFUND))

    # Check orga personal accounting: credit refund row in Delivered section
    go_to(page, live_server, "/accounting/credits/")
    page.get_by_role("link", name="Delivered").click()
    just_wait(page)
    credit_refund_row = page.get_by_role("row").filter(has_text="Refund")
    expect_normalized(page, credit_refund_row, str(ORGA_CREDIT_REFUND))
    go_to(page, live_server, "/accounting/")
    expect_normalized(page, "#one", "Total: " + str(ORGA_TOKEN_REFUND))
    expect_normalized(page, "#one", "Total: " + str(ORGA_CREDIT_REFUND))
