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

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from larpmanager.forms.accounting import (
    AnyInvoiceSubmitForm,
    CollectionForm,
    DonateForm,
    ExeOutflowForm,
    ExePaymentSettingsForm,
    OrgaCreditForm,
    OrgaDiscountForm,
    OrgaExpenseForm,
    OrgaPaymentForm,
    OrgaPersonalExpenseForm,
    OrgaTokenForm,
    PaymentForm,
    RefundRequestForm,
    WireInvoiceSubmitForm,
)
from larpmanager.tests.unit.base import BaseTestCase


class TestOrgaPersonalExpenseForm(BaseTestCase):
    def test_init_without_balance_feature(self):
        params = {
            "features": [],  # No ita_balance feature
            "run": self.run(),
        }
        form = OrgaPersonalExpenseForm(ctx=params)

        # Should not have balance field
        assert "balance" not in form.fields

    def test_init_with_balance_feature(self):
        params = {"features": ["ita_balance"], "run": self.run()}
        form = OrgaPersonalExpenseForm(ctx=params)

        # Should have balance field
        assert "balance" in form.fields

    def test_valid_form_data(self):
        run = self.run()
        params = {"features": ["ita_balance"], "run": run, "a_id": run.event.assoc.id}

        # Create uploaded file for testing
        test_file = SimpleUploadedFile("test_invoice.pdf", b"test content", content_type="application/pdf")

        form_data = {
            "value": "100.50",
            "descr": "Test expense description",
            "exp": "a",  # SCENOGR
            "balance": "1",  # MATER
        }

        form = OrgaPersonalExpenseForm(data=form_data, files={"invoice": test_file}, ctx=params)

        assert form.is_valid()


class TestOrgaExpenseForm(BaseTestCase):
    def test_init_sets_member_widget_run(self):
        params = {"features": ["ita_balance"], "run": self.run(), "event": self.event()}

        with patch.object(OrgaExpenseForm, "delete_field") as mock_delete:
            form = OrgaExpenseForm(ctx=params)

            # Check that member widget has run set
            assert hasattr(form.fields["member"].widget, "set_run")

    def test_init_without_balance_feature(self):
        params = {
            "features": [],  # No ita_balance
            "run": self.run(),
            "event": self.event(),
        }

        with patch.object(OrgaExpenseForm, "delete_field") as mock_delete:
            form = OrgaExpenseForm(ctx=params)
            mock_delete.assert_called_with("balance")

    def test_init_expense_disable_orga(self):
        # Mock event.assoc.get_config to return True for expense_disable_orga
        event = self.event()
        event.assoc.get_config = Mock(return_value=True)

        params = {"features": ["ita_balance"], "run": self.run(), "event": event}

        with patch.object(OrgaExpenseForm, "delete_field") as mock_delete:
            form = OrgaExpenseForm(ctx=params)
            mock_delete.assert_called_with("is_approved")


class TestOrgaTokenForm(BaseTestCase):
    def test_init_sets_token_data(self):
        params = {"token_name": "Game Tokens", "run": self.run()}

        form = OrgaTokenForm(ctx=params)

        assert form.page_title == "Game Tokens"
        assert form.initial["oth"] == "t"  # TOKEN choice
        assert "Game Tokens" in form.page_info


class TestOrgaCreditForm(BaseTestCase):
    def test_init_sets_credit_data(self):
        params = {"credit_name": "Event Credits", "run": self.run()}

        form = OrgaCreditForm(ctx=params)

        assert form.page_title == "Event Credits"
        assert form.initial["oth"] == "c"  # CREDIT choice


class TestOrgaPaymentForm(BaseTestCase):
    def test_init_sets_event_widget(self):
        params = {"run": self.run(), "event": self.event()}

        form = OrgaPaymentForm(ctx=params)

        # Check that reg field is required and widget has event set
        assert form.fields["reg"].required is True


class TestExeOutflowForm(BaseTestCase):
    def test_init_sets_default_payment_date(self):
        params = {"features": ["ita_balance"], "a_id": self.association().id}

        form = ExeOutflowForm(ctx=params)

        # Should have today's date as initial payment_date
        assert "payment_date" in form.initial
        assert form.fields["invoice"].required is True

    def test_init_without_balance_feature(self):
        params = {
            "features": [],  # No ita_balance
            "a_id": self.association().id,
        }

        with patch.object(ExeOutflowForm, "delete_field") as mock_delete:
            form = ExeOutflowForm(ctx=params)
            mock_delete.assert_called_with("balance")


class TestDonateForm(BaseTestCase):
    def test_form_fields(self):
        ctx = {
            "methods": {"test": {"name": "Test Method"}},
            "association": self.association()
        }
        form = DonateForm(ctx=ctx)

        # Should have amount and descr fields
        assert "amount" in form.fields
        assert "descr" in form.fields

        # Amount should have proper validation
        amount_field = form.fields["amount"]
        assert amount_field.min_value == 0.01
        assert amount_field.max_value == 1000
        assert amount_field.decimal_places == 2

    def test_valid_data(self):
        form_data = {"amount": "50.00", "descr": "Donation for a good cause", "method": "test"}
        ctx = {
            "methods": {"test": {"name": "Test Method"}},
            "association": self.association()
        }
        form = DonateForm(data=form_data, ctx=ctx)
        assert form.is_valid()

    def test_invalid_amount_too_low(self):
        form_data = {"amount": "0.00", "descr": "Invalid donation", "method": "test"}
        ctx = {
            "methods": {"test": {"name": "Test Method"}},
            "association": self.association()
        }
        form = DonateForm(data=form_data, ctx=ctx)
        assert not form.is_valid()
        assert "amount" in form.errors

    def test_invalid_amount_too_high(self):
        form_data = {"amount": "1001.00", "descr": "Too much donation", "method": "test"}
        ctx = {
            "methods": {"test": {"name": "Test Method"}},
            "association": self.association()
        }
        form = DonateForm(data=form_data, ctx=ctx)
        assert not form.is_valid()
        assert "amount" in form.errors


class TestCollectionForm(BaseTestCase):
    def test_form_fields(self):
        ctx = {
            "methods": {"test": {"name": "Test Method"}},
            "association": self.association()
        }
        form = CollectionForm(ctx=ctx)

        assert "amount" in form.fields

        amount_field = form.fields["amount"]
        assert amount_field.min_value == 0.01
        assert amount_field.max_value == 1000

    def test_valid_data(self):
        form_data = {"amount": "25.00", "method": "test"}
        ctx = {
            "methods": {"test": {"name": "Test Method"}},
            "association": self.association()
        }
        form = CollectionForm(data=form_data, ctx=ctx)
        assert form.is_valid()


class TestPaymentForm(BaseTestCase):
    def test_init_with_registration(self):
        # Mock registration values
        registration = self.registration()
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("30.00")

        ctx = {
            "quota": Decimal("70.00"),
            "methods": {"test": {"name": "Test Method"}},
            "association": registration.run.event.assoc
        }

        form = PaymentForm(reg=registration, ctx=ctx)

        # Check amount field configuration
        amount_field = form.fields["amount"]
        assert amount_field.min_value == 0.01
        assert amount_field.max_value == 70.00  # tot_iscr - tot_payed
        assert amount_field.initial == Decimal("70.00")  # quota

    def test_valid_payment_amount(self):
        registration = self.registration()
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("30.00")

        ctx = {
            "quota": Decimal("70.00"),
            "methods": {"test": {"name": "Test Method"}},
            "association": registration.run.event.assoc
        }

        form_data = {"amount": "50.00", "method": "test"}

        form = PaymentForm(data=form_data, reg=registration, ctx=ctx)
        assert form.is_valid()

    def test_invalid_payment_amount_too_high(self):
        registration = self.registration()
        registration.tot_iscr = Decimal("100.00")
        registration.tot_payed = Decimal("30.00")

        ctx = {
            "quota": Decimal("70.00"),
            "methods": {"test": {"name": "Test Method"}},
            "association": registration.run.event.assoc
        }

        form_data = {
            "amount": "80.00",  # More than max allowed
            "method": "test"
        }

        form = PaymentForm(data=form_data, reg=registration, ctx=ctx)
        assert not form.is_valid()
        assert "amount" in form.errors


class TestOrgaDiscountForm(BaseTestCase):
    def test_init_creates_runs_choices(self):
        run = self.run()
        params = {"run": run}

        # Mock Run.objects.filter to return the run
        with patch("larpmanager.forms.accounting.Run.objects.filter") as mock_filter:
            mock_filter.return_value = [run]
            run.__str__ = lambda: "Test Run"

            form = OrgaDiscountForm(ctx=params)

            # Should have runs field with choices
            assert "runs" in form.fields
            runs_field = form.fields["runs"]
            assert len(runs_field.choices) == 1

    def test_init_with_existing_instance(self):
        run = self.run()
        params = {"run": run}

        # Create a mock discount since it's not in the base class
        discount = Mock()
        discount.runs.all = Mock(return_value=[run])

        with patch("larpmanager.forms.accounting.Run.objects.filter") as mock_filter:
            mock_filter.return_value = [run]

            form = OrgaDiscountForm(instance=discount, ctx=params)

            # Should set initial runs
            assert form.initial["runs"] == [run.id]


class TestWireInvoiceSubmitForm(BaseTestCase):
    def test_form_fields(self):
        form = WireInvoiceSubmitForm()

        assert "cod" in form.fields
        assert "invoice" in form.fields

        # Check that cod field is hidden
        assert form.fields["cod"].widget.__class__.__name__ == "HiddenInput"

    def test_valid_file_upload(self):
        test_file = SimpleUploadedFile("test_invoice.pdf", b"test content", content_type="application/pdf")

        form_data = {"cod": "TEST123"}

        form = WireInvoiceSubmitForm(data=form_data, files={"invoice": test_file})

        assert form.is_valid()

    def test_set_initial(self):
        form = WireInvoiceSubmitForm()
        form.set_initial("cod", "TEST456")

        assert form.fields["cod"].initial == "TEST456"


class TestAnyInvoiceSubmitForm(BaseTestCase):
    def test_form_fields(self):
        form = AnyInvoiceSubmitForm()

        assert "cod" in form.fields
        assert "text" in form.fields

    def test_valid_data(self):
        form_data = {"cod": "TEST123", "text": "Payment reference information"}

        form = AnyInvoiceSubmitForm(data=form_data)
        assert form.is_valid()


class TestRefundRequestForm(BaseTestCase):
    def test_init_sets_max_value(self):
        # Mock member.membership.credit
        member = self.member()
        mock_membership = Mock()
        mock_membership.credit = Decimal("150.00")
        member.membership = mock_membership

        form = RefundRequestForm(member=member)

        # Check that value field has correct max_value
        value_field = form.fields["value"]
        assert value_field.max_value == Decimal("150.00")

    def test_valid_refund_request(self):
        member = self.member()
        mock_membership = Mock()
        mock_membership.credit = Decimal("150.00")
        member.membership = mock_membership

        form_data = {"details": "IBAN: IT60 X054 2811 1010 0000 0123 456", "value": "100.00"}

        form = RefundRequestForm(data=form_data, member=member)
        assert form.is_valid()

    def test_invalid_refund_amount(self):
        member = self.member()
        mock_membership = Mock()
        mock_membership.credit = Decimal("150.00")
        member.membership = mock_membership

        form_data = {
            "details": "IBAN: IT60 X054 2811 1010 0000 0123 456",
            "value": "200.00",  # More than available credit
        }

        form = RefundRequestForm(data=form_data, member=member)
        assert not form.is_valid()
        assert "value" in form.errors


class TestExePaymentSettingsForm(BaseTestCase):
    def test_init_creates_payment_details_fields(self):
        # Mock payment methods
        mock_method1 = Mock()
        mock_method1.slug = "wire"
        mock_method1.name = "Wire Transfer"
        mock_method1.instructions = "Wire transfer instructions"

        mock_method2 = Mock()
        mock_method2.slug = "paypal"
        mock_method2.name = "PayPal"
        mock_method2.instructions = "PayPal instructions"

        with patch("larpmanager.forms.accounting.PaymentMethod.objects.order_by") as mock_order:
            mock_order.return_value = [mock_method1, mock_method2]

            with patch.object(ExePaymentSettingsForm, "get_payment_details_fields") as mock_get_fields:
                mock_get_fields.return_value = {
                    "wire": ["wire_descr", "wire_fee", "wire_iban"],
                    "paypal": ["paypal_descr", "paypal_fee", "paypal_email"],
                }

                with patch("larpmanager.forms.accounting.get_payment_details") as mock_get_details:
                    mock_get_details.return_value = {}

                    form = ExePaymentSettingsForm(instance=self.association())

                    # Should create fields for payment details
                    assert "wire_descr" in form.fields
                    assert "wire_fee" in form.fields
                    assert "wire_iban" in form.fields
                    assert "paypal_descr" in form.fields
                    assert "paypal_fee" in form.fields
                    assert "paypal_email" in form.fields

    def test_mask_string_method(self):
        # Test the static mask_string method

        # Short string should not be masked
        short_string = "short"
        assert ExePaymentSettingsForm.mask_string(short_string) == "short"

        # Long string should be masked
        long_string = "this_is_a_very_long_string_that_should_be_masked"
        masked = ExePaymentSettingsForm.mask_string(long_string)
        assert masked.startswith("thi")
        assert masked.endswith("ked")
        assert "*" in masked

    def test_clean_validates_fee_fields(self):
        form = ExePaymentSettingsForm(instance=self.association())
        form.fee_fields = {"test_fee"}

        # Test valid fee
        cleaned_data = {"test_fee": "2.5"}
        form.cleaned_data = cleaned_data
        result = form.clean()
        assert result["test_fee"] == "2.5"

        # Test fee with percentage sign
        cleaned_data = {"test_fee": "2.5%"}
        form.cleaned_data = cleaned_data
        result = form.clean()
        assert result["test_fee"] == "2.5"

        # Test invalid fee
        cleaned_data = {"test_fee": "invalid"}
        form.cleaned_data = cleaned_data
        with patch.object(form, "add_error") as mock_add_error:
            form.clean()
            mock_add_error.assert_called()

    def test_save_updates_payment_details(self):
        with patch("larpmanager.forms.accounting.get_payment_details") as mock_get:
            mock_get.return_value = {}
            with patch("larpmanager.forms.accounting.save_payment_details") as mock_save:
                with patch.object(ExePaymentSettingsForm, "get_payment_details_fields") as mock_fields:
                    mock_fields.return_value = {"test": ["test_field"]}

                    association = self.association()
                    form = ExePaymentSettingsForm(instance=association)
                    form.cleaned_data = {"test_field": "new_value"}

                    with patch("django.forms.ModelForm.save") as mock_super_save:
                        mock_super_save.return_value = association

                        result = form.save()

                        mock_save.assert_called_once()
                        assert result == association