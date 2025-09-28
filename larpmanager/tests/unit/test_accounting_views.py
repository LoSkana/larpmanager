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

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.http import Http404, JsonResponse
from django.test import Client, RequestFactory

from larpmanager.models.accounting import (
    CollectionStatus,
    PaymentInvoice,
    PaymentStatus,
    PaymentType,
)
from larpmanager.models.base import PaymentMethod
from larpmanager.tests.unit.base import BaseTestCase
from larpmanager.views.exe import accounting as exe_accounting

# Import views to test
from larpmanager.views.orga import accounting as orga_accounting
from larpmanager.views.user import accounting as user_accounting


class TestOrgaAccountingViews(BaseTestCase):
    """Test organizer accounting views"""

    def setup_method(self):
        self.factory = RequestFactory()
        self.client = Client()

    def test_orga_discounts(self):
        user_with_permissions = self.user_with_permissions()
        event = self.event()
        run = self.run()
        request = self.factory.get("/test/manage/discounts/")
        request.user = user_with_permissions
        request.assoc = {"id": event.assoc_id}

        with patch("larpmanager.views.orga.accounting.check_event_permission") as mock_check:
            mock_check.return_value = {"event": event, "run": run}
            with patch("larpmanager.views.orga.accounting.render") as mock_render:
                orga_accounting.orga_discounts(request, "test-slug")
                mock_check.assert_called_once()
                mock_render.assert_called_once()

    def test_orga_discounts_edit(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/test/manage/discounts/1/edit/")
        request.user = user_with_permissions

        with patch("larpmanager.views.orga.accounting.orga_edit") as mock_edit:
            mock_edit.return_value = Mock()
            orga_accounting.orga_discounts_edit(request, "test-slug", 1)
            mock_edit.assert_called_once()

    def test_orga_expenses_my(self):
        user_with_permissions = self.user_with_permissions()
        event = self.event()
        run = self.run()
        request = self.factory.get("/test/manage/expenses_my/")
        request.user = user_with_permissions
        request.user.member = Mock()

        with patch("larpmanager.views.orga.accounting.check_event_permission") as mock_check:
            mock_check.return_value = {"event": event, "run": run}
            with patch("larpmanager.views.orga.accounting.render") as mock_render:
                orga_accounting.orga_expenses_my(request, "test-slug")
                mock_check.assert_called_once()
                mock_render.assert_called_once()

    def test_orga_expenses_my_new_get(self):
        user_with_permissions = self.user_with_permissions()
        event = self.event()
        run = self.run()
        request = self.factory.get("/test/manage/expenses_my/new/")
        request.user = user_with_permissions
        request.user.member = Mock()
        request.assoc = {"id": 1}

        with patch("larpmanager.views.orga.accounting.check_event_permission") as mock_check:
            mock_check.return_value = {"event": event, "run": run}
            with patch("larpmanager.views.orga.accounting.OrgaPersonalExpenseForm") as mock_form:
                with patch("larpmanager.views.orga.accounting.render") as mock_render:
                    orga_accounting.orga_expenses_my_new(request, "test-slug")
                    mock_check.assert_called_once()
                    mock_form.assert_called_once()
                    mock_render.assert_called_once()

    def test_orga_expenses_my_new_post_valid(self):
        user_with_permissions = self.user_with_permissions()
        event = self.event()
        run = self.run()
        request = self.factory.post("/test/manage/expenses_my/new/", {"descr": "Test expense"})
        request.user = user_with_permissions
        request.user.member = Mock()
        request.assoc = {"id": 1}

        mock_expense = Mock()
        mock_form = Mock()
        mock_form.is_valid.return_value = True
        mock_form.save.return_value = mock_expense

        with patch("larpmanager.views.orga.accounting.check_event_permission") as mock_check:
            mock_check.return_value = {"event": event, "run": run}
            with patch("larpmanager.views.orga.accounting.OrgaPersonalExpenseForm", return_value=mock_form):
                with patch("larpmanager.views.orga.accounting.messages"):
                    with patch("larpmanager.views.orga.accounting.redirect") as mock_redirect:
                        orga_accounting.orga_expenses_my_new(request, "test-slug")
                        mock_expense.save.assert_called_once()
                        mock_redirect.assert_called_once()

    def test_orga_invoices(self):
        user_with_permissions = self.user_with_permissions()
        event = self.event()
        run = self.run()
        request = self.factory.get("/test/manage/invoices/")
        request.user = user_with_permissions

        with patch("larpmanager.views.orga.accounting.check_event_permission") as mock_check:
            mock_check.return_value = {"event": event, "run": run}
            with patch("larpmanager.views.orga.accounting.render") as mock_render:
                orga_accounting.orga_invoices(request, "test-slug")
                mock_check.assert_called_once()
                mock_render.assert_called_once()

    def test_orga_invoices_confirm(self):
        user_with_permissions = self.user_with_permissions()
        event = self.event()
        run = self.run()
        payment_invoice = self.payment_invoice()
        request = self.factory.get("/test/manage/invoices/1/confirm/")
        request.user = user_with_permissions
        payment_invoice.status = PaymentStatus.SUBMITTED

        with patch("larpmanager.views.orga.accounting.check_event_permission") as mock_check:
            mock_check.return_value = {"event": event, "run": run}
            with patch("larpmanager.views.orga.accounting.backend_get") as mock_get:
                mock_get.return_value = None
                mock_context = {"el": payment_invoice, "run": run}
                mock_check.return_value.update(mock_context)
                with patch("larpmanager.views.orga.accounting.messages"):
                    with patch("larpmanager.views.orga.accounting.redirect") as mock_redirect:
                        orga_accounting.orga_invoices_confirm(request, "test-slug", 1)
                        assert payment_invoice.status == PaymentStatus.CONFIRMED
                        mock_redirect.assert_called_once()

    def test_orga_invoices_confirm_wrong_run(self):
        user_with_permissions = self.user_with_permissions()
        event = self.event()
        run = self.run()
        payment_invoice = self.payment_invoice()
        request = self.factory.get("/test/manage/invoices/1/confirm/")
        request.user = user_with_permissions

        # Create different run
        other_run = Mock()
        other_run.id = 999
        payment_invoice.reg = Mock()
        payment_invoice.reg.run = other_run

        with patch("larpmanager.views.orga.accounting.check_event_permission") as mock_check:
            mock_check.return_value = {"event": event, "run": run}
            with patch("larpmanager.views.orga.accounting.backend_get") as mock_get:
                mock_context = {"el": payment_invoice, "run": run}
                mock_check.return_value.update(mock_context)

                with pytest.raises(Http404):
                    orga_accounting.orga_invoices_confirm(request, "test-slug", 1)

    def test_orga_accounting(self):
        user_with_permissions = self.user_with_permissions()
        event = self.event()
        run = self.run()
        request = self.factory.get("/test/manage/accounting/")
        request.user = user_with_permissions

        with patch("larpmanager.views.orga.accounting.check_event_permission") as mock_check:
            mock_check.return_value = {"event": event, "run": run}
            with patch("larpmanager.views.orga.accounting.get_run_accounting") as mock_get_run:
                mock_get_run.return_value = {"revenue": 100}
                with patch("larpmanager.views.orga.accounting.render") as mock_render:
                    orga_accounting.orga_accounting(request, "test-slug")
                    mock_check.assert_called_once()
                    mock_get_run.assert_called_once()
                    mock_render.assert_called_once()

    def test_assign_payment_fee(self):
        # Create mock context
        ctx = {"list": []}

        # Create mock payment items
        payment1 = Mock()
        payment1.inv_id = 1
        payment1.value = Decimal("100")

        payment2 = Mock()
        payment2.inv_id = 2
        payment2.value = Decimal("50")

        payment3 = Mock()
        payment3.inv_id = None
        payment3.value = Decimal("25")

        ctx["list"] = [payment1, payment2, payment3]

        # Create mock transaction
        transaction = Mock()
        transaction.inv_id = 1
        transaction.value = Decimal("5")

        with patch("larpmanager.views.orga.accounting.AccountingItemTransaction") as mock_transaction:
            mock_transaction.objects.filter.return_value = [transaction]

            orga_accounting.assign_payment_fee(ctx)

            # Check that net values are calculated correctly
            assert payment1.net == Decimal("95")  # 100 - 5
            assert payment1.trans == Decimal("5")
            assert payment2.net == Decimal("50")  # No transaction fee
            assert payment3.net == Decimal("25")  # No inv_id

    def test_orga_expenses_approve(self):
        user_with_permissions = self.user_with_permissions()
        event = self.event()
        run = self.run()
        request = self.factory.get("/test/manage/expenses/1/approve/")
        request.user = user_with_permissions

        mock_expense = Mock()
        mock_expense.run.event = event
        mock_expense.is_approved = False

        with patch("larpmanager.views.orga.accounting.check_event_permission") as mock_check:
            mock_check.return_value = {"event": event, "run": run}
            with patch("larpmanager.views.orga.accounting.AccountingItemExpense") as mock_model:
                mock_model.objects.get.return_value = mock_expense
                with patch("larpmanager.views.orga.accounting.messages"):
                    with patch("larpmanager.views.orga.accounting.redirect") as mock_redirect:
                        orga_accounting.orga_expenses_approve(request, "test-slug", 1)
                        assert mock_expense.is_approved is True
                        mock_expense.save.assert_called_once()
                        mock_redirect.assert_called_once()

    def test_orga_expenses_approve_disabled(self):
        user_with_permissions = self.user_with_permissions()
        event = self.event()
        run = self.run()
        request = self.factory.get("/test/manage/expenses/1/approve/")
        request.user = user_with_permissions

        # Mock association config to disable expense approval
        event.assoc.get_config = Mock(return_value=True)

        with patch("larpmanager.views.orga.accounting.check_event_permission") as mock_check:
            mock_check.return_value = {"event": event, "run": run}

            with pytest.raises(Http404):
                orga_accounting.orga_expenses_approve(request, "test-slug", 1)


class TestExeAccountingViews(BaseTestCase):
    """Test executive accounting views"""

    def setup_method(self):
        self.factory = RequestFactory()

    def test_exe_outflows(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/manage/outflows/")
        request.user = user_with_permissions

        with patch("larpmanager.views.exe.accounting.check_assoc_permission") as mock_check:
            mock_check.return_value = {"a_id": 1}
            with patch("larpmanager.views.exe.accounting.exe_paginate") as mock_paginate:
                with patch("larpmanager.views.exe.accounting.render") as mock_render:
                    exe_accounting.exe_outflows(request)
                    mock_check.assert_called_once()
                    mock_paginate.assert_called_once()
                    mock_render.assert_called_once()

    def test_exe_outflows_edit(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/manage/outflows/1/edit/")
        request.user = user_with_permissions

        with patch("larpmanager.views.exe.accounting.exe_edit") as mock_edit:
            exe_accounting.exe_outflows_edit(request, 1)
            mock_edit.assert_called_once()

    def test_exe_year_accounting_valid_year(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.post("/manage/year_accounting/", {"year": "2025"})
        request.user = user_with_permissions

        with patch("larpmanager.views.exe.accounting.check_assoc_permission") as mock_check:
            mock_check.return_value = {"a_id": 1}
            with patch("larpmanager.views.exe.accounting.assoc_accounting_data") as mock_data:
                response = exe_accounting.exe_year_accounting(request)
                assert isinstance(response, JsonResponse)
                mock_check.assert_called_once()
                mock_data.assert_called_once_with({"a_id": 1}, 2025)

    def test_exe_year_accounting_invalid_year(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.post("/manage/year_accounting/", {"year": "invalid"})
        request.user = user_with_permissions

        with patch("larpmanager.views.exe.accounting.check_assoc_permission") as mock_check:
            mock_check.return_value = {"a_id": 1}
            response = exe_accounting.exe_year_accounting(request)
            assert isinstance(response, JsonResponse)
            assert response.status_code == 400

    def test_exe_run_accounting(self):
        user_with_permissions = self.user_with_permissions()
        run = self.run()
        request = self.factory.get(f"/manage/run/{run.id}/accounting/")
        request.user = user_with_permissions

        with patch("larpmanager.views.exe.accounting.check_assoc_permission") as mock_check:
            mock_check.return_value = {"a_id": run.event.assoc_id}
            with patch("larpmanager.views.exe.accounting.Run") as mock_run_model:
                mock_run_model.objects.get.return_value = run
                with patch("larpmanager.views.exe.accounting.get_run_accounting") as mock_get_run:
                    mock_get_run.return_value = {"revenue": 100}
                    with patch("larpmanager.views.exe.accounting.render") as mock_render:
                        exe_accounting.exe_run_accounting(request, run.id)
                        mock_check.assert_called_once()
                        mock_get_run.assert_called_once()
                        mock_render.assert_called_once()

    def test_exe_run_accounting_wrong_assoc(self):
        user_with_permissions = self.user_with_permissions()
        run = self.run()
        request = self.factory.get(f"/manage/run/{run.id}/accounting/")
        request.user = user_with_permissions

        with patch("larpmanager.views.exe.accounting.check_assoc_permission") as mock_check:
            mock_check.return_value = {"a_id": 999}  # Different association
            with patch("larpmanager.views.exe.accounting.Run") as mock_run_model:
                mock_run_model.objects.get.return_value = run

                with pytest.raises(Http404):
                    exe_accounting.exe_run_accounting(request, run.id)

    def test_exe_balance(self):
        user_with_permissions = self.user_with_permissions()
        association = self.association()
        request = self.factory.get("/manage/balance/")
        request.user = user_with_permissions

        with patch("larpmanager.views.exe.accounting.check_assoc_permission") as mock_check:
            mock_check.return_value = {"a_id": association.id}
            with patch("larpmanager.views.exe.accounting.check_year") as mock_check_year:
                mock_check_year.return_value = 2025
                with patch("larpmanager.views.exe.accounting.get_sum") as mock_get_sum:
                    mock_get_sum.return_value = Decimal("100")
                    with patch("larpmanager.views.exe.accounting.render") as mock_render:
                        exe_accounting.exe_balance(request)
                        mock_check.assert_called_once()
                        mock_check_year.assert_called_once()
                        mock_render.assert_called_once()

    def test_check_year_with_post(self):
        association = self.association()
        request = self.factory.post("/test/", {"year": "2024"})
        ctx = {"a_id": association.id}

        with patch("larpmanager.views.exe.accounting.Association") as mock_assoc:
            mock_assoc.objects.get.return_value = association
            association.created = datetime(2020, 1, 1)

            result = exe_accounting.check_year(request, ctx)
            assert result == 2024
            assert ctx["year"] == 2024

    def test_check_year_invalid_year(self):
        association = self.association()
        request = self.factory.post("/test/", {"year": "invalid"})
        ctx = {"a_id": association.id}

        with patch("larpmanager.views.exe.accounting.Association") as mock_assoc:
            mock_assoc.objects.get.return_value = association
            association.created = datetime(2020, 1, 1)

            with patch("larpmanager.views.exe.accounting.datetime") as mock_datetime:
                mock_datetime.today.return_value.year = 2025

                result = exe_accounting.check_year(request, ctx)
                assert result == 2025  # Should default to current year

    def test_exe_verification_manual(self):
        user_with_permissions = self.user_with_permissions()
        payment_invoice = self.payment_invoice()
        request = self.factory.get(f"/manage/verification/{payment_invoice.id}/manual/")
        request.user = user_with_permissions
        payment_invoice.verified = False

        with patch("larpmanager.views.exe.accounting.check_assoc_permission") as mock_check:
            mock_check.return_value = {"a_id": payment_invoice.assoc_id}
            with patch("larpmanager.views.exe.accounting.PaymentInvoice") as mock_model:
                mock_model.objects.get.return_value = payment_invoice
                with patch("larpmanager.views.exe.accounting.messages"):
                    with patch("larpmanager.views.exe.accounting.redirect") as mock_redirect:
                        exe_accounting.exe_verification_manual(request, payment_invoice.id)
                        assert payment_invoice.verified is True
                        payment_invoice.save.assert_called_once()
                        mock_redirect.assert_called_once()

    def test_exe_verification_manual_wrong_assoc(self):
        user_with_permissions = self.user_with_permissions()
        payment_invoice = self.payment_invoice()
        request = self.factory.get(f"/manage/verification/{payment_invoice.id}/manual/")
        request.user = user_with_permissions

        with patch("larpmanager.views.exe.accounting.check_assoc_permission") as mock_check:
            mock_check.return_value = {"a_id": 999}  # Different association
            with patch("larpmanager.views.exe.accounting.PaymentInvoice") as mock_model:
                mock_model.objects.get.return_value = payment_invoice

                with pytest.raises(Http404):
                    exe_accounting.exe_verification_manual(request, payment_invoice.id)

    def test_exe_verification_manual_already_verified(self):
        user_with_permissions = self.user_with_permissions()
        payment_invoice = self.payment_invoice()
        request = self.factory.get(f"/manage/verification/{payment_invoice.id}/manual/")
        request.user = user_with_permissions
        payment_invoice.verified = True

        with patch("larpmanager.views.exe.accounting.check_assoc_permission") as mock_check:
            mock_check.return_value = {"a_id": payment_invoice.assoc_id}
            with patch("larpmanager.views.exe.accounting.PaymentInvoice") as mock_model:
                mock_model.objects.get.return_value = payment_invoice
                with patch("larpmanager.views.exe.accounting.messages"):
                    with patch("larpmanager.views.exe.accounting.redirect") as mock_redirect:
                        exe_accounting.exe_verification_manual(request, payment_invoice.id)
                        mock_redirect.assert_called_once()


class TestUserAccountingViews(BaseTestCase):
    """Test user accounting views"""

    def setup_method(self):
        self.factory = RequestFactory()

    def test_accounting(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/accounting/")
        request.user = user_with_permissions
        request.assoc = {"id": 1, "features": []}

        with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
            mock_ctx.return_value = {"a_id": 1, "member": user_with_permissions}
            with patch("larpmanager.views.user.accounting.info_accounting") as mock_info:
                with patch("larpmanager.views.user.accounting.get_assoc_text") as mock_text:
                    mock_text.return_value = "Terms and conditions"
                    with patch("larpmanager.views.user.accounting.render") as mock_render:
                        user_accounting.accounting(request)
                        mock_ctx.assert_called_once()
                        mock_info.assert_called_once()
                        mock_render.assert_called_once()

    def test_accounting_redirect_no_assoc(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/accounting/")
        request.user = user_with_permissions

        with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
            mock_ctx.return_value = {"a_id": 0}
            with patch("larpmanager.views.user.accounting.redirect") as mock_redirect:
                user_accounting.accounting(request)
                mock_redirect.assert_called_once_with("home")

    def test_accounting_tokens(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/accounting/tokens/")
        request.user = user_with_permissions

        with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
            mock_ctx.return_value = {"member": user_with_permissions, "a_id": 1}
            with patch("larpmanager.views.user.accounting.AccountingItemOther") as mock_other:
                with patch("larpmanager.views.user.accounting.AccountingItemPayment") as mock_payment:
                    with patch("larpmanager.views.user.accounting.render") as mock_render:
                        user_accounting.accounting_tokens(request)
                        mock_ctx.assert_called_once()
                        mock_render.assert_called_once()

    def test_accounting_credits(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/accounting/credits/")
        request.user = user_with_permissions

        with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
            mock_ctx.return_value = {"member": user_with_permissions, "a_id": 1}
            with patch("larpmanager.views.user.accounting.AccountingItemExpense") as mock_expense:
                with patch("larpmanager.views.user.accounting.AccountingItemOther") as mock_other:
                    with patch("larpmanager.views.user.accounting.AccountingItemPayment") as mock_payment:
                        with patch("larpmanager.views.user.accounting.render") as mock_render:
                            user_accounting.accounting_credits(request)
                            mock_ctx.assert_called_once()
                            mock_render.assert_called_once()

    def test_acc_refund_get(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/accounting/refund/")
        request.user = user_with_permissions
        request.user.member = Mock()

        with patch("larpmanager.views.user.accounting.check_assoc_feature") as mock_check:
            with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
                mock_ctx.return_value = {"member": user_with_permissions, "a_id": 1}
                with patch("larpmanager.views.user.accounting.get_user_membership") as mock_membership:
                    with patch("larpmanager.views.user.accounting.RefundRequestForm") as mock_form:
                        with patch("larpmanager.views.user.accounting.render") as mock_render:
                            user_accounting.acc_refund(request)
                            mock_check.assert_called_once_with(request, "refund")
                            mock_ctx.assert_called_once()
                            mock_form.assert_called_once()
                            mock_render.assert_called_once()

    def test_acc_refund_post_valid(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.post("/accounting/refund/", {"details": "Bank details", "value": "50.00"})
        request.user = user_with_permissions
        request.user.member = Mock()

        mock_refund = Mock()
        mock_form = Mock()
        mock_form.is_valid.return_value = True
        mock_form.save.return_value = mock_refund

        with patch("larpmanager.views.user.accounting.check_assoc_feature") as mock_check:
            with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
                mock_ctx.return_value = {"member": user_with_permissions, "a_id": 1}
                with patch("larpmanager.views.user.accounting.get_user_membership") as mock_membership:
                    with patch("larpmanager.views.user.accounting.RefundRequestForm", return_value=mock_form):
                        with patch("larpmanager.views.user.accounting.notify_refund_request") as mock_notify:
                            with patch("larpmanager.views.user.accounting.transaction"):
                                with patch("larpmanager.views.user.accounting.messages"):
                                    with patch("larpmanager.views.user.accounting.redirect") as mock_redirect:
                                        user_accounting.acc_refund(request)
                                        mock_refund.save.assert_called_once()
                                        mock_notify.assert_called_once_with(mock_refund)
                                        mock_redirect.assert_called_once_with("accounting")

    def test_acc_collection_redeem(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/accounting/collection/ABC123/redeem/")
        request.user = user_with_permissions
        request.assoc = {"id": 1}

        mock_collection = Mock()
        mock_collection.status = CollectionStatus.DONE

        with patch("larpmanager.views.user.accounting.get_collection_redeem") as mock_get:
            mock_get.return_value = mock_collection
            with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
                mock_ctx.return_value = {"member": user_with_permissions, "a_id": 1}
                with patch("larpmanager.views.user.accounting.AccountingItemCollection") as mock_items:
                    with patch("larpmanager.views.user.accounting.render") as mock_render:
                        user_accounting.acc_collection_redeem(request, "ABC123")
                        mock_get.assert_called_once()
                        mock_ctx.assert_called_once()
                        mock_render.assert_called_once()

    def test_acc_collection_redeem_post(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.post("/accounting/collection/ABC123/redeem/")
        request.user = user_with_permissions
        request.assoc = {"id": 1}

        mock_collection = Mock()
        mock_collection.status = CollectionStatus.DONE

        with patch("larpmanager.views.user.accounting.get_collection_redeem") as mock_get:
            mock_get.return_value = mock_collection
            with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
                mock_ctx.return_value = {"member": user_with_permissions, "a_id": 1}
                with patch("larpmanager.views.user.accounting.transaction"):
                    with patch("larpmanager.views.user.accounting.messages"):
                        with patch("larpmanager.views.user.accounting.redirect") as mock_redirect:
                            user_accounting.acc_collection_redeem(request, "ABC123")
                            assert mock_collection.member == user_with_permissions
                            assert mock_collection.status == CollectionStatus.PAYED
                            mock_collection.save.assert_called_once()
                            mock_redirect.assert_called_once_with("home")

    def test_acc_collection_redeem_wrong_status(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/accounting/collection/ABC123/redeem/")
        request.user = user_with_permissions
        request.assoc = {"id": 1}

        mock_collection = Mock()
        mock_collection.status = CollectionStatus.OPEN  # Wrong status

        with patch("larpmanager.views.user.accounting.get_collection_redeem") as mock_get:
            mock_get.return_value = mock_collection
            with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
                mock_ctx.return_value = {"member": user_with_permissions, "a_id": 1}

                with pytest.raises(Http404):
                    user_accounting.acc_collection_redeem(request, "ABC123")

    def test_acc_payed(self):
        user_with_permissions = self.user_with_permissions()
        payment_invoice = self.payment_invoice()
        request = self.factory.get(f"/accounting/payed/{payment_invoice.id}/")
        request.user = user_with_permissions
        request.user.member = Mock()
        request.assoc = {"id": payment_invoice.assoc_id}

        with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
            mock_ctx.return_value = {"member": user_with_permissions, "a_id": payment_invoice.assoc_id}
            with patch("larpmanager.views.user.accounting.satispay_check") as mock_satispay:
                with patch("larpmanager.views.user.accounting.acc_profile_check") as mock_profile:
                    mock_profile.return_value = Mock()
                    with patch("larpmanager.views.user.accounting.PaymentInvoice") as mock_model:
                        mock_model.objects.get.return_value = payment_invoice
                        user_accounting.acc_payed(request, payment_invoice.id)
                        mock_ctx.assert_called_once()
                        mock_satispay.assert_called_once()
                        mock_profile.assert_called_once()

    def test_acc_payed_no_invoice(self):
        user_with_permissions = self.user_with_permissions()
        request = self.factory.get("/accounting/payed/")
        request.user = user_with_permissions
        request.user.member = Mock()
        request.assoc = {"id": 1}

        with patch("larpmanager.views.user.accounting.def_user_ctx") as mock_ctx:
            mock_ctx.return_value = {"member": user_with_permissions, "a_id": 1}
            with patch("larpmanager.views.user.accounting.satispay_check") as mock_satispay:
                with patch("larpmanager.views.user.accounting.acc_profile_check") as mock_profile:
                    mock_profile.return_value = Mock()
                    user_accounting.acc_payed(request, 0)
                    mock_ctx.assert_called_once()
                    mock_satispay.assert_called_once()
                    mock_profile.assert_called_once_with(request, "You have completed the payment!", None)


    # Helper methods for creating specific test objects when needed
    def user_with_permissions(self):
        """Create a mock user with permissions"""
        user = Mock()
        user.is_authenticated = True
        user.member = Mock()
        return user

    def payment_method(self):
        """Create a payment method for testing"""
        return PaymentMethod.objects.create(name="Test Method", slug="test", fields="field1,field2")

    def payment_invoice(self):
        """Create a payment invoice for testing"""
        association = self.association()
        payment_method = self.payment_method()
        invoice = PaymentInvoice.objects.create(
            member_id=1,
            assoc=association,
            method=payment_method,
            typ=PaymentType.REGISTRATION,
            status=PaymentStatus.CREATED,
            mc_gross=Decimal("100.00"),
            mc_fee=Decimal("5.00"),
            causal="Test payment",
            cod="TEST123",
            txn_id="TXN456",
        )
        # Mock the save method since we're using mock objects
        invoice.save = Mock()
        return invoice
