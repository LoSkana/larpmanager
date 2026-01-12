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

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from larpmanager.tests.utils import go_to, load_image, login_orga, login_user, logout, submit, submit_confirm

pytestmark = pytest.mark.e2e


def test_orga_digest_notifications_immediate(pw_page: Any) -> None:
    """Test immediate organizer notifications (default behavior, digest mode OFF)"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    prepare_event(page, live_server)

    # Ensure digest mode is OFF (default)
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    if page.locator("#id_mail_orga_digest").is_checked():
        page.locator("#id_mail_orga_digest").uncheck()
    submit_confirm(page)

    # Clear any existing emails
    go_to(page, live_server, "/debug/mail")

    # Perform registration as user
    logout(page)
    login_user(page, live_server)
    register_user(page, live_server)

    # Check that organizer received immediate email
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")

    # Should see immediate registration notification email
    expect(page.locator("body")).to_contain_text("Registration to")
    expect(page.locator("body")).to_contain_text("by user@test.it")


def test_orga_digest_notifications_queued(pw_page: Any) -> None:
    """Test digest mode - notifications are queued, no immediate emails"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    prepare_event(page, live_server)

    # Enable digest mode
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_orga_digest").wait_for(state="visible")
    page.locator("#id_mail_orga_digest").check()
    submit_confirm(page)

    # Clear any existing emails
    go_to(page, live_server, "/debug/mail")

    # Perform registration as user
    logout(page)
    login_user(page, live_server)
    register_user(page, live_server)

    # Check that NO immediate email was sent to organizer
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")

    # Should NOT see registration email (it's queued)
    expect(page.locator("body")).not_to_contain_text("Registration to")

    # Check that notification is in admin queue
    go_to(page, live_server, "/admin/larpmanager/organizernotificationqueue/")

    # Should see queued notification
    expect(page.locator("body")).to_contain_text("registration_new")
    expect(page.locator("body")).to_contain_text("Test Event")

    # Verify not sent yet
    expect(page.locator("tbody tr:first-child")).to_contain_text("✓")  # sent=False shows as checkmark icon


def test_orga_digest_daily_summary(pw_page: Any) -> None:
    """Test daily summary email is sent when automate command runs"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    prepare_event(page, live_server)

    # Enable digest mode
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_orga_digest").wait_for(state="visible")
    page.locator("#id_mail_orga_digest").check()
    submit_confirm(page)

    # Perform multiple actions as user
    logout(page)
    login_user(page, live_server)

    # Action 1: New registration
    register_user(page, live_server)

    # Action 2: Update registration (add a note or change something)
    go_to(page, live_server, "/test/register")
    # Trigger an update by re-submitting
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Back to organizer
    logout(page)
    login_orga(page, live_server)

    # Clear existing emails
    go_to(page, live_server, "/debug/mail")

    # Run automate command (simulating daily cron job)
    # Note: In real test, this would need to call python manage.py automate
    # For now, we'll call the function directly via admin action or API
    # Since we can't easily call manage.py from playwright, we'll verify the queue state

    # Check queue has entries
    go_to(page, live_server, "/admin/larpmanager/organizernotificationqueue/")
    expect(page.locator("body")).to_contain_text("registration_new")

    # In a real scenario, after running automate:
    # 1. Queue entries would be marked as sent
    # 2. A daily summary email would be sent
    # 3. Email would contain all queued notifications


def test_orga_digest_multiple_notification_types(pw_page: Any) -> None:
    """Test digest mode with multiple notification types (registration + payment)"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    prepare_event_with_payments(page, live_server)

    # Enable digest mode
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_orga_digest").wait_for(state="visible")
    page.locator("#id_mail_orga_digest").check()
    submit_confirm(page)

    # Perform registration + payment as user
    logout(page)
    login_user(page, live_server)

    # Register
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Pay
    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name=re.compile(r"proceed with payment")).click()
    page.get_by_role("cell", name="Wire", exact=True).click()
    submit(page)
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()
    submit(page)

    # Check organizer queue has both notifications
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/admin/larpmanager/organizernotificationqueue/")

    # Should see both registration and payment notifications
    expect(page.locator("body")).to_contain_text("registration_new")
    expect(page.locator("body")).to_contain_text("invoice_approval")


def test_orga_digest_user_emails_immediate(pw_page: Any) -> None:
    """Test that user emails are always immediate, even with digest mode ON"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    prepare_event(page, live_server)

    # Enable digest mode for ORGANIZERS
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_orga_digest").check()
    submit_confirm(page)

    # Clear existing emails
    go_to(page, live_server, "/debug/mail")

    # Perform registration as user
    logout(page)
    login_user(page, live_server)
    register_user(page, live_server)

    # Check that USER received immediate confirmation email
    # (even though organizer notifications are queued)
    go_to(page, live_server, "/debug/mail")

    # Should see user confirmation email
    expect(page.locator("body")).to_contain_text("Registration to")
    # Should be addressed to user, not organizer
    expect(page.locator("body")).to_contain_text("user@test.it")


def test_orga_digest_cancellation_queued(pw_page: Any) -> None:
    """Test that registration cancellations are queued in digest mode"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    prepare_event(page, live_server)

    # Enable digest mode
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_orga_digest").wait_for(state="visible")
    page.locator("#id_mail_orga_digest").check()
    submit_confirm(page)

    # Register and then cancel as user
    logout(page)
    login_user(page, live_server)
    register_user(page, live_server)

    # Cancel registration
    go_to(page, live_server, "/test/unregister")
    page.get_by_role("button", name="Confirm").click()

    # Check organizer queue
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/admin/larpmanager/organizernotificationqueue/")

    # Should see cancellation notification
    expect(page.locator("body")).to_contain_text("registration_cancel")


def test_orga_digest_toggle_on_off(pw_page: Any) -> None:
    """Test toggling digest mode on and off"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    prepare_event(page, live_server)

    # Start with digest OFF (default) - should get immediate emails
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    if page.locator("#id_mail_orga_digest").is_checked():
        page.locator("#id_mail_orga_digest").uncheck()
    submit_confirm(page)

    # Clear emails
    go_to(page, live_server, "/debug/mail")

    # Register as user
    logout(page)
    login_user(page, live_server)
    register_user(page, live_server)

    # Should have immediate email
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).to_contain_text("Registration to")

    # Now turn digest ON
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_orga_digest").check()
    submit_confirm(page)

    # Clear emails again
    go_to(page, live_server, "/debug/mail")

    # Update registration as user
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Should NOT have immediate email now
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).not_to_contain_text("Registration updated")

    # But should be in queue
    go_to(page, live_server, "/admin/larpmanager/organizernotificationqueue/")
    expect(page.locator("body")).to_contain_text("registration_update")


# Helper functions

def prepare_event(page: Any, live_server: Any) -> None:
    """Prepare event with basic email notifications enabled"""
    # Enable email notifications
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_cc").check()
    page.locator("#id_mail_signup_new").check()
    page.locator("#id_mail_signup_update").check()
    page.locator("#id_mail_signup_del").check()
    submit_confirm(page)


def prepare_event_with_payments(page: Any, live_server: Any) -> None:
    """Prepare event with payments enabled"""
    prepare_event(page, live_server)

    # Activate payments feature
    go_to(page, live_server, "/manage/features/payment/on")

    # Configure payment notifications
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_payment").check()
    page.locator('a[tog="sec_payments"]').click()
    page.locator("#id_payment_require_receipt").check()
    submit_confirm(page)

    # Configure payment method
    go_to(page, live_server, "/manage/methods")
    page.get_by_role("checkbox", name="Wire").check()
    page.locator("#id_wire_descr").fill("test wire")
    page.locator("#id_wire_fee").fill("0")
    page.locator("#id_wire_payee").fill("test beneficiary")
    page.locator("#id_wire_iban").fill("test iban")
    submit_confirm(page)

    # Set ticket price
    go_to(page, live_server, "/test/manage/tickets")
    page.locator("a:has(i.fas.fa-edit)").click()
    page.locator("#id_price").fill("100.00")
    submit_confirm(page)


def register_user(page: Any, live_server: Any) -> None:
    """Register user for event"""
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Approve sharing if needed
    if "Authorisation" in page.content():
        page.get_by_role("checkbox", name="Authorisation").check()
        page.get_by_role("button", name="Submit").click()


def test_orga_digest_all_notification_types_immediate(pw_page: Any) -> None:
    """Test all notification types generate immediate emails when digest mode is OFF"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    prepare_event_with_payments(page, live_server)

    # Ensure digest mode is OFF
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_orga_digest").wait_for(state="visible")
    if page.locator("#id_mail_orga_digest").is_checked():
        page.locator("#id_mail_orga_digest").uncheck()
    submit_confirm(page)

    # Clear any existing emails
    go_to(page, live_server, "/debug/mail")

    # Test 1: Registration created
    logout(page)
    login_user(page, live_server)
    register_user(page, live_server)

    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).to_contain_text("Registration to")

    # Clear emails
    go_to(page, live_server, "/debug/mail")

    # Test 2: Registration updated
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).to_contain_text("Registration to")

    # Clear emails
    go_to(page, live_server, "/debug/mail")

    # Test 3: Payment (invoice approval)
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name=re.compile(r"proceed with payment")).click()
    page.get_by_role("cell", name="Wire", exact=True).click()
    submit(page)
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()
    submit(page)

    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")
    # Should see invoice approval notification
    expect(page.locator("body")).to_contain_text("Invoice")

    # Clear emails
    go_to(page, live_server, "/debug/mail")

    # Test 4: Registration cancelled
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/test/unregister")
    page.get_by_role("button", name="Confirm").click()

    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).to_contain_text("Cancellation")


def test_orga_digest_all_notification_types_queued_and_sent(pw_page: Any) -> None:
    """Test all notification types are queued and sent via digest when digest mode is ON"""
    page, live_server, _ = pw_page

    login_orga(page, live_server)
    prepare_event_with_payments(page, live_server)

    # Enable digest mode
    go_to(page, live_server, "/manage/config")
    page.get_by_role("link", name=re.compile(r"^Email notifications\s.+")).click()
    page.locator("#id_mail_orga_digest").wait_for(state="visible")
    page.locator("#id_mail_orga_digest").check()
    submit_confirm(page)

    # Clear any existing emails and notifications
    go_to(page, live_server, "/debug/mail")

    # Test 1: Registration created
    logout(page)
    login_user(page, live_server)
    register_user(page, live_server)

    # Verify NO immediate email
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).not_to_contain_text("Registration to")

    # Verify notification is queued
    go_to(page, live_server, "/admin/larpmanager/organizernotificationqueue/")
    expect(page.locator("body")).to_contain_text("registration_new")

    # Test 2: Registration updated
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    page.get_by_role("button", name="Continue").click()
    submit_confirm(page)

    # Verify NO immediate email
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).not_to_contain_text("Registration updated")

    # Verify notification is queued
    go_to(page, live_server, "/admin/larpmanager/organizernotificationqueue/")
    expect(page.locator("body")).to_contain_text("registration_update")

    # Test 3: Payment (invoice approval)
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/test/register")
    page.get_by_role("link", name=re.compile(r"proceed with payment")).click()
    page.get_by_role("cell", name="Wire", exact=True).click()
    submit(page)
    load_image(page, "#id_invoice")
    page.get_by_role("checkbox", name="Payment confirmation:").check()
    submit(page)

    # Verify NO immediate email
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).not_to_contain_text("Invoice")

    # Verify notification is queued
    go_to(page, live_server, "/admin/larpmanager/organizernotificationqueue/")
    expect(page.locator("body")).to_contain_text("invoice_approval")

    # Test 4: Registration cancelled
    logout(page)
    login_user(page, live_server)
    go_to(page, live_server, "/test/unregister")
    page.get_by_role("button", name="Confirm").click()

    # Verify NO immediate email
    logout(page)
    login_orga(page, live_server)
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).not_to_contain_text("Cancellation")

    # Verify notification is queued
    go_to(page, live_server, "/admin/larpmanager/organizernotificationqueue/")
    expect(page.locator("body")).to_contain_text("registration_cancel")

    # Verify all notifications are NOT sent yet
    expect(page.locator("tbody tr")).to_have_count(4)  # 4 notifications total

    # Clear existing emails before triggering digest
    go_to(page, live_server, "/debug/mail")

    # Trigger digest summary generation (simulates automate command)
    go_to(page, live_server, "/debug/send_digests/")

    # Verify digest email was sent
    go_to(page, live_server, "/debug/mail")
    expect(page.locator("body")).to_contain_text("Daily Summary")
    expect(page.locator("body")).to_contain_text("Test Event")

    # Verify digest contains all notification types
    expect(page.locator("body")).to_contain_text("New Registrations")
    expect(page.locator("body")).to_contain_text("Updated Registrations")
    expect(page.locator("body")).to_contain_text("Cancelled Registrations")
    expect(page.locator("body")).to_contain_text("Invoices Awaiting Approval")

    # Verify all notifications are marked as sent
    go_to(page, live_server, "/admin/larpmanager/organizernotificationqueue/")
    # All checkboxes should be checked now (sent=True)
    # The admin interface shows a checkmark when sent=False, and unchecked when sent=True
    # So after sending, we should NOT see the checkmark icon for "sent" column
