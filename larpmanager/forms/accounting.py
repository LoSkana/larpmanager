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

from django import forms
from django.utils.translation import gettext_lazy as _

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
    PaymentInvoice,
    RefundRequest,
)
from larpmanager.models.association import Association
from larpmanager.models.base import PaymentMethod
from larpmanager.models.event import Run
from larpmanager.models.utils import get_payment_details, save_payment_details
from larpmanager.utils.common import FileTypeValidator


class OrgaPersonalExpenseForm(MyFormRun):
    page_info = _("This page allows you to add or edit an expense item of a contributor")

    page_title = _("Expenses")

    class Meta:
        model = AccountingItemExpense
        exclude = ("member", "is_approved", "inv", "hide")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "ita_balance" not in self.params["features"]:
            self.delete_field("balance")


class OrgaExpenseForm(MyFormRun):
    page_title = _("Expenses collaborators")

    page_info = _("This page allows you to add or edit the expense of a contributor")

    class Meta:
        model = AccountingItemExpense
        exclude = ("inv", "hide")
        widgets = {"member": RunMemberS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_run(self.params["run"])

        if "ita_balance" not in self.params["features"]:
            self.delete_field("balance")


class OrgaTokenForm(MyFormRun):
    class Meta:
        model = AccountingItemOther
        exclude = ("inv", "hide", "reg", "cancellation", "ref_addit")
        widgets = {"member": RunMemberS2Widget, "oth": forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page_info = _("This page allows you to add or edit an assignment of") + f" {self.params['token_name']}"
        self.page_title = self.params["token_name"]
        self.initial["oth"] = AccountingItemOther.TOKEN
        self.fields["member"].widget.set_run(self.params["run"])


class OrgaCreditForm(MyFormRun):
    page_info = _("This page allows you to add or edit a credits assignment")

    class Meta:
        model = AccountingItemOther
        exclude = ("inv", "hide", "reg", "cancellation", "ref_addit")
        widgets = {"member": RunMemberS2Widget, "oth": forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page_title = self.params["credit_name"]
        self.initial["oth"] = AccountingItemOther.CREDIT
        self.fields["member"].widget.set_run(self.params["run"])


class OrgaPaymentForm(MyFormRun):
    page_title = _("Payments")

    page_info = _("This page allows you to add or edit a payment item")

    class Meta:
        model = AccountingItemPayment
        exclude = ("inv", "hide", "member", "vat")
        widgets = {"reg": EventRegS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reg"].widget.set_event(self.params["event"])
        self.fields["reg"].required = True


class ExeOutflowForm(MyForm):
    page_title = _("Outflows")

    page_info = _("This page allows you to add or edit an expense item incurred")

    class Meta:
        model = AccountingItemOutflow
        exclude = ("member", "inv", "hide")

        widgets = {"payment_date": DatePickerInput, "run": RunS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, "auto_run"):
            self.fields["run"].widget.set_assoc(self.params["a_id"])
        if "payment_date" not in self.initial or not self.initial["payment_date"]:
            self.initial["payment_date"] = datetime.now().date().isoformat()
            # ~ else:
            # ~ self.initial['payment_date'] = self.instance.payment_date.isoformat()

        self.fields["invoice"].required = True

        if "ita_balance" not in self.params["features"]:
            self.delete_field("balance")


class OrgaOutflowForm(ExeOutflowForm):
    def __init__(self, *args, **kwargs):
        self.auto_run = True
        super().__init__(*args, **kwargs)


class ExeInflowForm(MyForm):
    page_title = _("Inflows")

    page_info = _("This page allows you to add or edit an event revenue other than the players' registration fee")

    class Meta:
        model = AccountingItemInflow
        exclude = ("member", "inv", "hide")

        widgets = {"payment_date": DatePickerInput, "run": RunS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, "auto_run"):
            self.fields["run"].widget.set_assoc(self.params["a_id"])
        if "payment_date" not in self.initial or not self.initial["payment_date"]:
            self.initial["payment_date"] = datetime.now().date().isoformat()

        self.fields["invoice"].required = True


class OrgaInflowForm(ExeInflowForm):
    def __init__(self, *args, **kwargs):
        self.auto_run = True
        super().__init__(*args, **kwargs)


class ExeDonationForm(MyForm):
    page_title = _("Donations")

    class Meta:
        model = AccountingItemDonation
        exclude = ("inv", "hide")
        widgets = {"member": AssocMemberS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_assoc(self.params["a_id"])


class ExePaymentForm(MyForm):
    page_title = _("Payments")

    page_info = _("This page allows you to add or edit a payment item")

    class Meta:
        model = AccountingItemPayment
        exclude = ("inv", "hide", "member")
        widgets = {"reg": AssocRegS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reg"].widget.set_assoc(self.params["a_id"])
        if "vat" not in self.params["features"]:
            del self.fields["vat"]


class ExeInvoiceForm(MyForm):
    page_title = _("Invoices")

    page_info = _("This page allows you to add or edit an invoice")

    class Meta:
        model = PaymentInvoice
        exclude = ("hide", "reg", "key", "idx", "txn_id")
        widgets = {"member": AssocMemberS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_assoc(self.params["a_id"])


class ExeCreditForm(MyForm):
    page_info = _("This page allows you to add or edit a credits assignment")

    class Meta:
        model = AccountingItemOther
        exclude = ("inv", "hide", "reg", "cancellation", "ref_addit")
        widgets = {"member": AssocMemberS2Widget, "run": RunS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page_title = _("Assignment") + f" {self.params['credit_name']}"
        get_run_choices(self)
        self.fields["member"].widget.set_assoc(self.params["a_id"])
        self.fields["run"].widget.set_assoc(self.params["a_id"])
        self.fields["oth"].widget = forms.HiddenInput()
        self.initial["oth"] = AccountingItemOther.CREDIT


class ExeTokenForm(MyForm):
    class Meta:
        model = AccountingItemOther
        exclude = ("inv", "hide", "reg", "cancellation", "ref_addit")
        widgets = {"member": AssocMemberS2Widget, "run": RunS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page_title = _("Assignment") + f" {self.params['token_name']}"
        self.page_info = _("This page allows you to add or edit an assignment of") + f" {self.params['token_name']}"
        get_run_choices(self)
        self.fields["member"].widget.set_assoc(self.params["a_id"])
        self.fields["run"].widget.set_assoc(self.params["a_id"])
        self.fields["oth"].widget = forms.HiddenInput()
        self.initial["oth"] = AccountingItemOther.TOKEN


class ExeExpenseForm(MyForm):
    page_title = _("Expenses")

    page_info = _("This page allows you to add or edit an expense item of a contributor")

    class Meta:
        model = AccountingItemExpense
        exclude = ("inv", "hide")
        widgets = {"member": AssocMemberS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        get_run_choices(self)
        self.fields["member"].widget.set_assoc(self.params["a_id"])

        if "ita_balance" not in self.params["features"]:
            self.delete_field("balance")


class DonateForm(MembershipForm):
    amount = forms.DecimalField(min_value=0.01, max_value=1000, decimal_places=2)
    descr = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 2}))


class CollectionForm(BaseAccForm):
    amount = forms.DecimalField(min_value=0.01, max_value=1000, decimal_places=2)


class PaymentForm(BaseAccForm):
    amount = forms.DecimalField()

    def __init__(self, *args, **kwargs):
        self.reg = kwargs.pop("reg")
        super().__init__(*args, **kwargs)
        self.fields["amount"] = forms.DecimalField(
            min_value=0.01,
            max_value=self.reg.tot_iscr - self.reg.tot_payed,
            decimal_places=2,
            initial=self.ctx["quota"],
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_assoc(self.params["a_id"])


class OrgaDiscountForm(MyForm):
    page_info = _("This page allows you to add or edit a discount")

    page_title = _("Discount")

    class Meta:
        model = Discount
        fields = "__all__"
        exclude = ("number",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(m.id, str(m)) for m in Run.objects.filter(event=self.params["run"].event)]

        widget = forms.CheckboxSelectMultiple(attrs={"class": "my-checkbox-class"})
        self.fields["runs"] = forms.MultipleChoiceField(
            choices=choices,
            widget=widget,
            required=False,
            help_text=_("Indicates the runs for which the discount is available"),
        )

        if self.instance and self.instance.pk:
            self.initial["runs"] = [r.id for r in self.instance.runs.all()]


class InvoiceSubmitForm(forms.Form):
    cod = forms.CharField(widget=forms.HiddenInput())

    class Meta:
        abstract = True

    def set_initial(self, k, v):
        self.fields[k].initial = v


class WireInvoiceSubmitForm(InvoiceSubmitForm):
    # noinspection PyUnresolvedReferences, PyProtectedMember
    invoice = forms.FileField(
        validators=[FileTypeValidator(allowed_types=["image/*", "application/pdf"])],
        label=PaymentInvoice._meta.get_field("invoice").verbose_name,
    )


class AnyInvoiceSubmitForm(InvoiceSubmitForm):
    text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5, "cols": 20}),
        label=_("Info"),
        help_text=_("Enter any useful information for the organizers to verify the payment"),
    )


class RefundRequestForm(MyForm):
    class Meta:
        model = RefundRequest
        fields = ("details", "value")

    def __init__(self, *args, **kwargs):
        self.member = kwargs.pop("member")
        super().__init__(*args, **kwargs)
        self.fields["value"] = forms.DecimalField(max_value=self.member.membership.credit, decimal_places=2)


class ExeRefundRequestForm(MyForm):
    page_title = _("Request refund")

    class Meta:
        model = RefundRequest
        exclude = ("status",)
        widgets = {"member": AssocMemberS2Widget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].widget.set_assoc(self.params["a_id"])


class ExePaymentSettingsForm(MyForm):
    page_title = _("Payment Methods")

    page_info = _("This page allows you to set up your payment methods")

    load_js = ["payment-details"]

    class Meta:
        model = Association
        fields = ("payment_methods",)

        widgets = {
            "payment_methods": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.prevent_canc = True

        self.fields["payment_methods"].queryset = self.fields["payment_methods"].queryset.order_by("id")

        self.methods = PaymentMethod.objects.order_by("id")
        self.section_descriptions = {}
        for el in self.methods:
            self.section_descriptions[el.name] = el.instructions

        self.all_methods = self.methods

        self.sections = {}
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

        res = get_payment_details(self.instance)
        for el in res:
            if el.startswith("old"):
                continue
            data_string = res[el]
            if not el.endswith(("_descr", "_fee")):
                data_string = self.mask_string(data_string)
            self.initial[el] = data_string

    def save(self, commit=True):
        instance = super().save(commit=commit)

        res = get_payment_details(self.instance)
        for _slug, lst in self.get_payment_details_fields().items():
            for el in lst:
                if el in self.cleaned_data:
                    input_value = self.cleaned_data[el]

                    if el in res:
                        orig_value = res[el]
                    else:
                        orig_value = ""

                    if el.endswith(("_descr", "_fee")):
                        data_string = orig_value
                    else:
                        data_string = self.mask_string(orig_value)

                    if input_value != data_string:
                        if input_value not in [None, ""] or orig_value not in [None, ""]:
                            res[el] = input_value
                            now = datetime.now()
                            old_key = f"old-{el}-{now.strftime('%Y%m%d%H%M%S')}"
                            res[old_key] = orig_value

        save_payment_details(self.instance, res)

        return instance

    def get_payment_details_fields(self):
        res = {}
        # noinspection PyUnresolvedReferences
        for el in self.methods:
            ls = [el.slug + "_descr", el.slug + "_fee"]
            if not el.slug:
                continue
            fields = el.fields.replace(" ", "")
            for field in fields.split(","):
                if field:
                    ls.append(el.slug + "_" + field)
            res[el.slug] = ls
        return res

    @staticmethod
    def mask_string(data_string):
        min_length = 6
        if len(data_string) > min_length:
            first_three = data_string[:3]
            last_three = data_string[-3:]
            middle_length = len(data_string) - min_length
            masked_middle = "*" * middle_length
            return first_three + masked_middle + last_three
        else:
            return data_string
