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

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from larpmanager.accounting.base import get_payment_details
from larpmanager.cache.config import get_assoc_config
from larpmanager.forms.base import BaseAccForm, MyForm, MyFormRun
from larpmanager.forms.member import MembershipForm
from larpmanager.forms.utils import (
    AssocMemberS2Widget,
    AssocRegS2Widget,
    DatePickerInput,
    EventRegS2Widget,
    RunMemberS2Widget,
    RunS2Widget,
    get_run_choices,
)
from larpmanager.models.accounting import (
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemInflow,
    AccountingItemOther,
    AccountingItemOutflow,
    AccountingItemPayment,
    Collection,
    Discount,
    OtherChoices,
    PaymentInvoice,
    RefundRequest,
)
from larpmanager.models.association import Association
from larpmanager.models.base import PaymentMethod
from larpmanager.models.event import Run
from larpmanager.models.member import Member
from larpmanager.models.utils import save_payment_details
from larpmanager.utils.validators import FileTypeValidator


class OrgaPersonalExpenseForm(MyFormRun):
    """Form for contributors to add/edit their personal expenses.

    Allows expense tracking with optional balance integration
    based on enabled features.
    """

    page_info = _("Manage expense items for contributors")

    page_title = _("Expenses")

    class Meta:
        model = AccountingItemExpense
        exclude = ("member", "is_approved", "inv", "hide")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and conditionally remove balance field based on feature flag.

        Args:
            *args: Variable length argument list passed to parent constructor.
            **kwargs: Arbitrary keyword arguments passed to parent constructor.
        """
        # Initialize parent form with all provided arguments
        super().__init__(*args, **kwargs)

        # Remove balance field if Italian balance feature is not enabled
        if "ita_balance" not in self.params["features"]:
            self.delete_field("balance")


class OrgaExpenseForm(MyFormRun):
    """Form for organizers to manage contributor expenses.

    Full expense management including approval workflow
    and member assignment capabilities.
    """

    page_title = _("Expenses collaborators")

    page_info = _("Manage expenses for contributors")

    class Meta:
        model = AccountingItemExpense
        exclude = ("inv", "hide")
        widgets = {"member": RunMemberS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure fields based on run features and association config."""
        super().__init__(*args, **kwargs)

        # Configure member widget with run context
        self.fields["member"].widget.set_run(self.params["run"])

        # Remove balance field if Italian balance feature is disabled
        if "ita_balance" not in self.params["features"]:
            self.delete_field("balance")

        # Remove approval field if organization has disabled expense approval
        if get_assoc_config(self.params["event"].assoc_id, "expense_disable_orga", False):
            self.delete_field("is_approved")


class OrgaTokenForm(MyFormRun):
    """Form for managing token accounting items.

    Handles token-based payments and transactions
    within the event accounting system.
    """

    class Meta:
        model = AccountingItemOther
        exclude = ("inv", "hide", "reg", "cancellation", "ref_addit")
        widgets = {"member": RunMemberS2Widget, "oth": forms.HiddenInput()}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with token-specific page information and field configuration."""
        super().__init__(*args, **kwargs)

        # Set page metadata with token name
        self.page_info = _("Manage") + f" {self.params['token_name']} " + _("assignments")
        self.page_title = self.params["token_name"]

        # Configure initial form values and widget
        self.initial["oth"] = OtherChoices.TOKEN
        self.fields["member"].widget.set_run(self.params["run"])


class OrgaCreditForm(MyFormRun):
    page_info = _("Manage credit assignments")

    class Meta:
        model = AccountingItemOther
        exclude = ("inv", "hide", "reg", "cancellation", "ref_addit")
        widgets = {"member": RunMemberS2Widget, "oth": forms.HiddenInput()}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize credit form with page title and run-specific member field."""
        super().__init__(*args, **kwargs)
        # Set page title from credit name parameter
        self.page_title = self.params["credit_name"]
        # Configure form for credit transaction type
        self.initial["oth"] = OtherChoices.CREDIT
        self.fields["member"].widget.set_run(self.params["run"])


class OrgaPaymentForm(MyFormRun):
    """Form for managing payment accounting records.

    Handles payment processing, validation, and
    integration with accounting workflows.
    """

    page_title = _("Payments")

    page_info = _("Manage payment items")

    class Meta:
        model = AccountingItemPayment
        exclude = ("inv", "hide", "member", "vat_ticket", "vat_options")
        widgets = {"reg": EventRegS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure registration field for the event."""
        super().__init__(*args, **kwargs)
        # Configure registration widget with event context and make field required
        self.fields["reg"].widget.set_event(self.params["event"])
        self.fields["reg"].required = True


class ExeOutflowForm(MyForm):
    page_title = _("Outflows")

    page_info = _("Manage expense items incurred")

    class Meta:
        model = AccountingItemOutflow
        exclude = ("member", "inv", "hide")

        widgets = {"payment_date": DatePickerInput, "run": RunS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with association-specific run widget, default payment date, and conditional fields."""
        super().__init__(*args, **kwargs)

        # Configure run widget with association context if not auto-populated
        if not hasattr(self, "auto_run"):
            self.fields["run"].widget.set_assoc(self.params["a_id"])

        # Set default payment date to today if not already provided
        if "payment_date" not in self.initial or not self.initial["payment_date"]:
            self.initial["payment_date"] = datetime.now().date().isoformat()
            # ~ else:
            # ~ self.initial['payment_date'] = self.instance.payment_date.isoformat()

        # Mark invoice field as required
        self.fields["invoice"].required = True

        # Remove balance field if Italian balance feature is disabled
        if "ita_balance" not in self.params["features"]:
            self.delete_field("balance")


class OrgaOutflowForm(ExeOutflowForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the form with auto_run enabled by default."""
        self.auto_run = True
        super().__init__(*args, **kwargs)


class ExeInflowForm(MyForm):
    page_title = _("Inflows")

    page_info = _("Manage event revenue other than participants' registration fees")

    class Meta:
        model = AccountingItemInflow
        exclude = ("member", "inv", "hide")

        widgets = {"payment_date": DatePickerInput, "run": RunS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with auto-populated run and payment date fields."""
        super().__init__(*args, **kwargs)

        # Set association for run field if not auto-run mode
        if not hasattr(self, "auto_run"):
            self.fields["run"].widget.set_assoc(self.params["a_id"])

        # Set default payment date to today if not provided
        if "payment_date" not in self.initial or not self.initial["payment_date"]:
            self.initial["payment_date"] = datetime.now().date().isoformat()

        # Invoice field is always required
        self.fields["invoice"].required = True


class OrgaInflowForm(ExeInflowForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with automatic run flag enabled."""
        self.auto_run = True
        super().__init__(*args, **kwargs)


class ExeDonationForm(MyForm):
    page_title = _("Donations")

    class Meta:
        model = AccountingItemDonation
        exclude = ("inv", "hide")
        widgets = {"member": AssocMemberS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and set association for member field widget."""
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_assoc(self.params["a_id"])


class ExePaymentForm(MyForm):
    page_title = _("Payments")

    page_info = _("Manage payment items")

    class Meta:
        model = AccountingItemPayment
        exclude = ("inv", "hide", "member", "vat_ticket", "vat_options")
        widgets = {"reg": AssocRegS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with association-specific field configuration."""
        super().__init__(*args, **kwargs)

        # Configure registration field widget with association context
        self.fields["reg"].widget.set_assoc(self.params["a_id"])

        # Remove VAT field if feature is not enabled
        if "vat" not in self.params["features"]:
            del self.fields["vat"]


class ExeInvoiceForm(MyForm):
    page_title = _("Invoices")

    page_info = _("Manage invoices")

    class Meta:
        model = PaymentInvoice
        exclude = ("hide", "reg", "key", "idx", "txn_id")
        widgets = {"member": AssocMemberS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure member widget with association."""
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_assoc(self.params["a_id"])


class ExeCreditForm(MyForm):
    page_info = _("Manage credit assignments")

    class Meta:
        model = AccountingItemOther
        exclude = ("inv", "hide", "reg", "cancellation", "ref_addit")
        widgets = {"member": AssocMemberS2Widget, "run": RunS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with credit assignment configuration."""
        super().__init__(*args, **kwargs)

        # Set page title with credit name
        self.page_title = _("Assignment") + f" {self.params['credit_name']}"

        # Configure run choices and association widgets
        get_run_choices(self)
        self.fields["member"].widget.set_assoc(self.params["a_id"])
        self.fields["run"].widget.set_assoc(self.params["a_id"])

        # Set other field as hidden with credit value
        self.fields["oth"].widget = forms.HiddenInput()
        self.initial["oth"] = OtherChoices.CREDIT


class ExeTokenForm(MyForm):
    class Meta:
        model = AccountingItemOther
        exclude = ("inv", "hide", "reg", "cancellation", "ref_addit")
        widgets = {"member": AssocMemberS2Widget, "run": RunS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with page title, info, and field configurations."""
        super().__init__(*args, **kwargs)

        # Set page title and info with token name
        self.page_title = _("Assignment") + f" {self.params['token_name']}"
        self.page_info = _("Manage") + f" {self.params['token_name']} " + _("assignments")

        # Configure run choices and association filtering
        get_run_choices(self)
        self.fields["member"].widget.set_assoc(self.params["a_id"])
        self.fields["run"].widget.set_assoc(self.params["a_id"])

        # Hide 'oth' field and set default value
        self.fields["oth"].widget = forms.HiddenInput()
        self.initial["oth"] = OtherChoices.TOKEN


class ExeExpenseForm(MyForm):
    page_title = _("Expenses")

    page_info = _("Manage expense items for contributors")

    class Meta:
        model = AccountingItemExpense
        exclude = ("inv", "hide")
        widgets = {"member": AssocMemberS2Widget, "run": RunS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with run choices and association-specific widget configuration."""
        super().__init__(*args, **kwargs)

        # Configure run choices and set association context for widgets
        get_run_choices(self)
        self.fields["member"].widget.set_assoc(self.params["a_id"])
        self.fields["run"].widget.set_assoc(self.params["a_id"])

        # Remove balance field if feature not enabled
        if "ita_balance" not in self.params["features"]:
            self.delete_field("balance")


class DonateForm(MembershipForm):
    amount = forms.DecimalField(min_value=0.01, max_value=1000, decimal_places=2)
    descr = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 2}))


class CollectionForm(BaseAccForm):
    amount = forms.DecimalField(min_value=0.01, max_value=1000, decimal_places=2)


class PaymentForm(BaseAccForm):
    amount = forms.DecimalField()

    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        """Initialize form with registration-specific amount field."""
        # Extract registration instance from kwargs
        self.reg = kwargs.pop("reg")
        super().__init__(*args, **kwargs)

        # Configure amount field with dynamic validation based on registration balance
        self.fields["amount"] = forms.DecimalField(
            min_value=0.01,
            max_value=self.reg.tot_iscr - self.reg.tot_payed,
            decimal_places=2,
            initial=self.context["quota"],
        )


class CollectionNewForm(MyForm):
    class Meta:
        model = Collection
        fields = ("name",)
        widgets = {"cod": forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class ExeCollectionForm(CollectionNewForm):
    page_title = _("Collections")

    class Meta:
        model = Collection
        fields = ("name", "member", "status", "contribute_code", "redeem_code")
        widgets = {"member": AssocMemberS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure member field widget with association."""
        super().__init__(*args, **kwargs)
        # Set association for member widget filtering
        self.fields["member"].widget.set_assoc(self.params["a_id"])


class OrgaDiscountForm(MyForm):
    page_info = _("Manage discounts")

    page_title = _("Discount")

    class Meta:
        model = Discount
        fields = "__all__"
        exclude = ("number",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form with dynamically generated run selection field.

        Creates a multiple choice field with checkboxes for all runs in the same event
        as the provided run parameter. Pre-selects runs associated with the instance.
        """
        super().__init__(*args, **kwargs)

        # Build choices from all runs in the same event
        choices = [(m.id, str(m)) for m in Run.objects.filter(event=self.params["run"].event)]

        # Create multiple choice field with checkbox widgets
        widget = forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"})
        self.fields["runs"] = forms.MultipleChoiceField(
            choices=choices,
            widget=widget,
            required=False,
            help_text=_("Indicates the sessions for which the discount is available"),
        )

        # Pre-populate field with existing runs if editing an instance
        if self.instance and self.instance.pk:
            self.initial["runs"] = [r.id for r in self.instance.runs.all()]


class InvoiceSubmitForm(forms.Form):
    cod = forms.CharField(widget=forms.HiddenInput())

    class Meta:
        abstract = True

    def set_initial(self, field_name, initial_value):
        self.fields[field_name].initial = initial_value


class WireInvoiceSubmitForm(InvoiceSubmitForm):
    # noinspection PyUnresolvedReferences, PyProtectedMember
    invoice = forms.FileField(
        validators=[
            FileTypeValidator(
                allowed_types=[
                    "image/jpeg",
                    "image/jpg",
                    "image/png",
                    "image/gif",
                    "image/bmp",
                    "image/tiff",
                    "image/webp",
                    "application/pdf",
                ]
            )
        ],
        label=PaymentInvoice._meta.get_field("invoice").verbose_name,
        help_text=_("Upload a PDF file or image (JPG, PNG, etc.)"),
    )

    payment_confirmed = forms.BooleanField(
        required=True,
        label=_("Payment confirmation"),
        help_text=_("I confirm that I have made the payment"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form, optionally removing invoice field based on receipt requirement."""
        require_receipt = kwargs.pop("require_receipt", True)
        super().__init__(*args, **kwargs)

        # Remove invoice field when receipt is not required
        if not require_receipt:
            if "invoice" in self.fields:
                del self.fields["invoice"]


class AnyInvoiceSubmitForm(InvoiceSubmitForm):
    text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5, "cols": 20}),
        label=_("Info"),
        help_text=_("Enter any useful information for the organizers to verify the payment"),
    )

    payment_confirmed = forms.BooleanField(
        required=True,
        label=_("Payment confirmation"),
        help_text=_("I confirm that I have made the payment"),
    )


class RefundRequestForm(MyForm):
    class Meta:
        model = RefundRequest
        fields = ("details", "value")

    def __init__(self, member: Member, *args: Any, **kwargs: Any) -> None:
        """Initialize form with member-specific credit validation.

        Args:
            member: Member instance to extract credit limit from
            *args: Variable length argument list passed to parent
            **kwargs: Arbitrary keyword arguments passed to parent
        """
        # Extract member from kwargs and initialize parent form
        self.member = kwargs.pop("member")
        super().__init__(*args, **kwargs)

        # Set value field with max value constraint from member's credit
        self.fields["value"] = forms.DecimalField(max_value=self.member.membership.credit, decimal_places=2)


class ExeRefundRequestForm(MyForm):
    page_title = _("Request refund")

    class Meta:
        model = RefundRequest
        exclude = ("status", "hide")
        widgets = {"member": AssocMemberS2Widget}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize form and configure member widget with association."""
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_assoc(self.params["a_id"])


class ExePaymentSettingsForm(MyForm):
    page_title = _("Payment Methods")

    page_info = _("Manage payment methods")

    load_js = ["payment-details"]

    class Meta:
        model = Association
        fields = ("payment_methods",)

        widgets = {
            "payment_methods": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        """Initialize PaymentMethodForm with dynamic payment method configuration.

        Args:
            *args: Variable length argument list passed to parent
            **kwargs: Arbitrary keyword arguments passed to parent
        """
        super().__init__(*args, **kwargs)

        self.prevent_canc = True

        self.fields["payment_methods"].queryset = self.fields["payment_methods"].queryset.order_by("id")

        self.methods = PaymentMethod.objects.order_by("id")
        self.section_descriptions = {}
        for el in self.methods:
            self.section_descriptions[el.name] = el.instructions

        self.all_methods = self.methods

        self.sections = {}
        self.fee_fields = set()
        self.payment_details = self.get_payment_details_fields()
        for method in self.methods:
            for el in self.payment_details[method.slug]:
                self.fields[el] = forms.CharField()
                self.fields[el].required = False
                self.sections["id_" + el] = method.name
                label = el.replace(f"{method.slug}_", "")

                help_dict = {
                    "descr": _("Description of this payment method to be displayed to the user"),
                    "fee": _(
                        "Percentage to be retained by the payment system - enter the value as a number, without the percentage symbol"
                    ),
                }
                if label in help_dict:
                    self.fields[el].help_text = help_dict[label]

                repl_dict = {
                    "descr": _("Description"),
                    "fee": _("Fee"),
                    "payee": _("Beneficiary"),
                }
                if label in repl_dict:
                    label = repl_dict[label]
                self.fields[el].label = label

                if el.endswith("_fee"):
                    self.fee_fields.add(el)

        res = get_payment_details(self.instance)
        for el in res:
            if el.startswith("old"):
                continue
            data_string = res[el]
            if not el.endswith(("_descr", "_fee")):
                data_string = self.mask_string(data_string)
            self.initial[el] = data_string

    def save(self, commit: bool = True) -> PaymentInvoice:
        """Save payment form with details masking and change tracking.

        This method saves the payment form instance, processes payment details
        by masking sensitive information, tracks changes with timestamps,
        and maintains a history of modifications.

        Args:
            commit: Whether to commit changes to database. Defaults to True.

        Returns:
            Payment instance with updated details and change history.

        Note:
            Changes are tracked by storing old values with timestamped keys.
            Description and fee fields are not masked for readability.
        """
        instance = super().save(commit=commit)

        # Get current payment details from the instance
        res = get_payment_details(self.instance)

        # Iterate through payment detail fields by category
        for _slug, lst in self.get_payment_details_fields().items():
            for el in lst:
                # Process only fields present in cleaned form data
                if el in self.cleaned_data:
                    # Extract input value from cleaned form data
                    input_value = self.cleaned_data[el]

                    # Get original value or default to empty string
                    if el in res:
                        orig_value = res[el]
                    else:
                        orig_value = ""

                    # Apply masking based on field type
                    # Description and fee fields remain unmasked for clarity
                    if el.endswith(("_descr", "_fee")):
                        data_string = orig_value
                    else:
                        data_string = self.mask_string(orig_value)

                    # Track changes only when values actually differ
                    if input_value != data_string:
                        # Ensure we don't track trivial empty-to-empty changes
                        if input_value not in [None, ""] or orig_value not in [None, ""]:
                            # Update with new value
                            res[el] = input_value

                            # Create timestamped backup of old value
                            now = datetime.now()
                            old_key = f"old-{el}-{now.strftime('%Y%m%d%H%M%S')}"
                            res[old_key] = orig_value

        # Persist updated payment details to storage
        save_payment_details(self.instance, res)

        return instance

    def get_payment_details_fields(self) -> dict[str, list[str]]:
        """Get payment method fields mapping.

        Returns a dictionary mapping payment method slugs to their required field names.
        Each payment method includes description and fee fields, plus any custom fields
        defined in the method's fields configuration.

        Returns:
            dict[str, list[str]]: Mapping of payment method slugs to field name lists.
                Each list contains field names in format: {slug}_{field_type}.
        """
        payment_method_fields: dict[str, list[str]] = {}

        # noinspection PyUnresolvedReferences
        for payment_method in self.methods:
            # Skip methods without slug identifier
            if not payment_method.slug:
                continue

            # Initialize with standard payment method fields (description and fee)
            field_names: list[str] = [payment_method.slug + "_descr", payment_method.slug + "_fee"]

            # Parse custom fields from comma-separated string
            normalized_fields = payment_method.fields.replace(" ", "")
            for custom_field in normalized_fields.split(","):
                # Add custom field if non-empty, prefixed with payment method slug
                if custom_field:
                    field_names.append(payment_method.slug + "_" + custom_field)

            # Store field list for this payment method
            payment_method_fields[payment_method.slug] = field_names

        return payment_method_fields

    @staticmethod
    def mask_string(input_string: str) -> str:
        """Masks the middle portion of a string, preserving first and last 3 characters."""
        minimum_maskable_length = 6
        # Only mask strings longer than minimum length
        if len(input_string) > minimum_maskable_length:
            first_three_chars = input_string[:3]
            last_three_chars = input_string[-3:]
            middle_section_length = len(input_string) - minimum_maskable_length
            masked_middle_section = "*" * middle_section_length
            return first_three_chars + masked_middle_section + last_three_chars
        else:
            return input_string

    def clean(self) -> dict[str, any]:
        """Validate and normalize fee field values.

        Processes form fields identified as fee fields, converting string values
        to normalized decimal representations. Validates that values are numeric
        and non-negative.

        Returns:
            dict[str, any]: Cleaned form data with normalized fee values as strings.
                           Fee fields are converted to normalized decimal strings,
                           other fields remain unchanged.

        Raises:
            ValidationError: Added to form errors when fee values are invalid
                           (non-numeric or negative).
        """
        # Get initial cleaned data from parent class
        cleaned = super().clean()

        # Process each fee field for validation and normalization
        for name in self.fee_fields:
            val = cleaned.get(name)

            # Skip empty or None values
            if val in (None, ""):
                continue

            # Normalize string representation by removing common formatting
            s = str(val).strip().replace("%", "").replace(",", ".")

            # Attempt to convert to Decimal for validation
            try:
                d = Decimal(s)
            except InvalidOperation:
                self.add_error(name, _("Enter a valid numeric value"))
                continue

            # Validate that the value is non-negative
            if d < 0:
                self.add_error(name, _("Value must be greater than or equal to 0"))
                continue

            # Store normalized decimal string representation
            cleaned[name] = str(d.normalize())

        return cleaned
