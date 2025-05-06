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

from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin

from larpmanager.admin.base import AssocFilter, DefModelAdmin, MemberFilter, RegistrationFilter, RunFilter
from larpmanager.models.accounting import (
    AccountingItemCollection,
    AccountingItemDiscount,
    AccountingItemDonation,
    AccountingItemExpense,
    AccountingItemInflow,
    AccountingItemMembership,
    AccountingItemOther,
    AccountingItemOutflow,
    AccountingItemPayment,
    AccountingItemTransaction,
    Collection,
    Discount,
    ElectronicInvoice,
    PaymentInvoice,
    RecordAccounting,
    RefundRequest,
)


class InvoiceFilter(AutocompleteFilter):
    title = "PaymentInvoice"
    field_name = "inv"


class AccountingItemAdmin(DefModelAdmin):
    exclude = ("search",)
    list_display = ("id", "member", "value")
    autocomplete_fields = ["member", "inv", "assoc"]
    search_fields = ("search",)

    @admin.display(ordering="reg__run", description="Run")
    def get_run(self, obj):
        return obj.reg.run


@admin.register(AccountingItemTransaction)
class AccountingItemTransactionAdmin(AccountingItemAdmin):
    list_display = ("id", "inv", "member", "value", "created", "updated")
    autocomplete_fields = ["member", "inv", "assoc", "reg"]
    list_filter = (MemberFilter, AssocFilter, RegistrationFilter)


@admin.register(AccountingItemDiscount)
class AccountingItemDiscountAdmin(AccountingItemAdmin):
    list_display = ("id", "disc", "run", "member", "value", "created", "updated")
    autocomplete_fields = ["member", "inv", "assoc", "run", "disc"]
    list_filter = (MemberFilter, AssocFilter, RunFilter)


@admin.register(AccountingItemDonation)
class AccountingItemDonationAdmin(AccountingItemAdmin):
    list_display = ("id", "member", "value", "descr", "created", "updated")
    list_filter = (MemberFilter, AssocFilter)
    autocomplete_fields = ["member", "inv", "assoc"]


@admin.register(AccountingItemCollection)
class AccountingItemCollectionAdmin(AccountingItemAdmin):
    list_display = ("id", "member", "value", "created", "updated")
    list_filter = (MemberFilter, AssocFilter)
    autocomplete_fields = ["member", "inv", "assoc"]


@admin.register(AccountingItemExpense)
class AccountingItemExpenseAdmin(AccountingItemAdmin):
    list_display = (
        "id",
        "run",
        "short_descr",
        "member",
        "value",
        "balance",
        "created",
        "updated",
    )
    autocomplete_fields = ("run", "member", "inv", "assoc")
    list_filter = (RunFilter, MemberFilter, AssocFilter)
    search_fields = ("search", "descr")


@admin.register(AccountingItemOutflow)
class AccountingItemOutflowAdmin(AccountingItemAdmin):
    list_display = (
        "id",
        "run",
        "short_descr",
        "value",
        "payment_date",
        "balance",
        "created",
        "updated",
    )
    autocomplete_fields = ("run", "member", "inv", "assoc")
    list_filter = (RunFilter, AssocFilter)
    search_fields = ("search", "descr")


@admin.register(AccountingItemInflow)
class AccountingItemInflowAdmin(AccountingItemAdmin):
    list_display = (
        "id",
        "run",
        "short_descr",
        "value",
        "payment_date",
        "created",
        "updated",
    )
    autocomplete_fields = ["member", "inv", "assoc", "run"]
    list_filter = (RunFilter, AssocFilter)
    search_fields = ("search", "descr")


@admin.register(AccountingItemPayment)
class AccountingItemPaymentAdmin(AccountingItemAdmin):
    list_display = (
        "id",
        "reg",
        "member",
        "value",
        "pay",
        "created",
        "updated",
        "inv",
    )
    autocomplete_fields = ["member", "inv", "assoc", "reg"]
    list_filter = (MemberFilter, AssocFilter, RegistrationFilter, "pay", "created")


@admin.register(AccountingItemMembership)
class AccountingItemMembershipAdmin(AccountingItemAdmin):
    list_display = (
        "id",
        "year",
        "member",
        "value",
        "created",
        "updated",
        "created",
        "updated",
    )
    list_filter = (MemberFilter, AssocFilter)
    autocomplete_fields = ["member", "inv", "assoc"]


@admin.register(AccountingItemOther)
class AccountingItemOtherAdmin(AccountingItemAdmin):
    list_display = (
        "id",
        "run",
        "member",
        "short_descr",
        "created",
        "value",
        "oth",
        "created",
        "updated",
    )
    autocomplete_fields = ("run", "member", "inv", "assoc")
    list_filter = (RunFilter, MemberFilter, AssocFilter)


@admin.register(PaymentInvoice)
class PaymentInvoiceAdmin(DefModelAdmin):
    exclude = ("search",)
    search_fields = ("search", "cod", "causal")
    list_display = (
        "id",
        "key",
        "causal",
        "typ",
        "method",
        "status",
        "mc_gross",
        "mc_fee",
        "created",
        "updated",
    )
    autocomplete_fields = ("member", "method", "assoc", "reg")
    list_filter = ("status", "method", "typ", AssocFilter, MemberFilter)


@admin.register(ElectronicInvoice)
class ElectronicInvoiceAdmin(DefModelAdmin):
    autocomplete_fields = ("inv", "assoc")
    list_filter = (AssocFilter, InvoiceFilter)


@admin.register(Discount)
class DiscountAdmin(DefModelAdmin):
    list_display = ("name", "value", "max_redeem", "cod", "typ", "show_event")
    # filter_horizontal = ['runs']
    autocomplete_fields = ["event", "runs", "runs"]
    search_fields = ["name"]


@admin.register(RecordAccounting)
class RecordAccountingAdmin(DefModelAdmin):
    list_display = ("run", "assoc", "global_sum", "bank_sum")
    list_filter = (RunFilter, AssocFilter)
    autocomplete_fields = ["run", "assoc"]


@admin.register(RefundRequest)
class RefundRequestAdmin(DefModelAdmin):
    list_display = ("member", "value", "status", "details")
    list_filter = (MemberFilter,)
    autocomplete_fields = ("member", "assoc")


@admin.register(Collection)
class CollectionAdmin(DefModelAdmin):
    list_display = ("id", "member", "organizer", "total")
    autocomplete_fields = ["member", "run", "organizer", "assoc"]
    search_fields = ["name"]
