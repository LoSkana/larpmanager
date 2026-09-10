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

"""Test: Member status flags pseudo-feature.

Verifies activation via config toggle, flag definition CRUD, the members-flags
summary datatable with its edit modal, and the read-only flags popup shown in
orga_registrations, orga_payments and exe_payments.
"""

from decimal import Decimal
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.models.accounting import PaymentInvoice, PaymentStatus, PaymentType
from larpmanager.models.base import PaymentMethod
from larpmanager.models.member import Member
from larpmanager.models.registration import Registration
from larpmanager.tests.utils import go_to, login_orga, orga_user, submit_confirm, submit_register

pytestmark = pytest.mark.e2e


def test_exe_member_flags(pw_page: Any) -> None:
    page, live_server, _ = pw_page

    login_orga(page, live_server)

    enable_feature(page, live_server)

    create_flag_defs(page, live_server)

    register_member(page, live_server)

    check_summary_initial(page, live_server)

    edit_flag_and_save(page, live_server)

    check_summary_updated(page, live_server)

    check_registration_popup(page, live_server)

    check_payments_flags(page, live_server)


def enable_feature(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/manage/config/member_flags_active/on")
    expect(page.locator("#id_member_flags_active")).to_be_checked()


def create_flag_defs(page: Any, live_server: Any) -> None:
    # Permanent flag
    go_to(page, live_server, "/manage/member_flags/new/")
    page.locator("#id_name").fill("Tesserato")
    page.locator("#id_descr").fill("Membership card issued")
    submit_confirm(page)

    # Annual flag
    go_to(page, live_server, "/manage/member_flags/new/")
    page.locator("#id_name").fill("Quota pagata")
    page.locator("#id_descr").fill("Yearly membership fee paid")
    page.locator("#id_annual").check()
    submit_confirm(page)

    go_to(page, live_server, "/manage/member_flags/")
    expect(page.locator("#member_flags")).to_contain_text("Tesserato")
    expect(page.locator("#member_flags")).to_contain_text("Quota pagata")


def register_member(page: Any, live_server: Any) -> None:
    # Register the logged-in organizer for the test event, so their own
    # membership status becomes eligible (>= joined) and a registration
    # exists to check the read-only flags popup on later.
    go_to(page, live_server, "/test/register")
    submit_register(page)


def check_summary_initial(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/manage/members_flags/")
    row = page.locator("#members_flags tbody tr").first
    expect(row).to_be_visible()
    expect(row.locator("i.fa-check")).to_have_count(0)


def edit_flag_and_save(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/manage/members_flags/")
    page.locator("#members_flags tbody tr").first.locator(".edit_member_flags").click()

    modal = page.locator("#lm-modal-content")
    expect(modal.locator("#member_flags_form")).to_be_visible()

    row = modal.locator("#member_flags_form tr", has_text="Tesserato")
    row.locator("input[type=checkbox]").check()

    modal.locator("#member_flags_form button[type=submit]").click()
    page.wait_for_load_state("networkidle")


def check_summary_updated(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/manage/members_flags/")
    row = page.locator("#members_flags tbody tr").first
    expect(row.locator("i.fa-check")).to_have_count(1)


def check_registration_popup(page: Any, live_server: Any) -> None:
    go_to(page, live_server, "/test/manage/registrations/")
    page.locator("a.post_popup_member").first.click()

    modal = page.locator("#lm-modal-content")
    expect(modal).to_contain_text("Flags")
    expect(modal).to_contain_text("Tesserato")
    expect(modal.locator("table i.fa-check")).to_have_count(1)


def check_payments_flags(page: Any, live_server: Any) -> None:
    # Create a pending (submitted) payment invoice for the registered organizer,
    # so a row with the flags eye icon shows up in both orga_payments and
    # exe_payments "Payments pending approval" tables.
    go_to(page, live_server, "/manage/features/payment/on")

    member = Member.objects.get(email=orga_user)
    registration = Registration.objects.get(member=member, run__event__slug="test")
    method, _created = PaymentMethod.objects.get_or_create(
        slug="test-flags-method",
        defaults={"name": "Test method", "fields": ""},
    )
    PaymentInvoice.objects.create(
        member=member,
        association_id=registration.run.event.association_id,
        method=method,
        typ=PaymentType.REGISTRATION,
        status=PaymentStatus.SUBMITTED,
        mc_gross=Decimal("10.00"),
        causal="Test flags payment",
        cod="FLAGTEST1",
        registration=registration,
    )

    go_to(page, live_server, "/test/manage/payments/")
    page.locator(".member_flags_eye").first.click()
    modal = page.locator("#lm-modal-content")
    expect(modal).to_contain_text("Flags")
    expect(modal).to_contain_text("Tesserato")
    expect(modal.locator("table i.fa-check")).to_have_count(1)

    go_to(page, live_server, "/manage/payments/")
    page.locator(".member_flags_eye").first.click()
    modal = page.locator("#lm-modal-content")
    expect(modal).to_contain_text("Flags")
    expect(modal).to_contain_text("Tesserato")
    expect(modal.locator("table i.fa-check")).to_have_count(1)
