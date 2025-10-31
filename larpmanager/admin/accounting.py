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

from larpmanager.admin.base import AssociationFilter, DefModelAdmin, MemberFilter, RegistrationFilter, RunFilter
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
    autocomplete_fields = ["member", "inv", "association"]
    search_fields = ("search",)

    @admin.display(ordering="reg__run", description="Run")
    def get_run(self, registration):
        return registration.reg.run


@admin.register(AccountingItemTransaction)
class AccountingItemTransactionAdmin(AccountingItemAdmin):
    list_display = ("id", "inv", "member", "value", "created", "updated")
    autocomplete_fields = ["member", "inv", "association", "reg"]
    list_filter = (MemberFilter, AssociationFilter, RegistrationFilter)


@admin.register(AccountingItemDiscount)
class AccountingItemDiscountAdmin(AccountingItemAdmin):
    list_display = ("id", "disc", "run", "member", "value", "created", "updated")
    autocomplete_fields = ["member", "inv", "association", "run", "disc"]
    list_filter = (MemberFilter, AssociationFilter, RunFilter)


@admin.register(AccountingItemDonation)
class AccountingItemDonationAdmin(AccountingItemAdmin):
    list_display = ("id", "member", "value", "descr", "created", "updated")
    list_filter = (MemberFilter, AssociationFilter)
    autocomplete_fields = ["member", "inv", "association"]


@admin.register(AccountingItemCollection)
class AccountingItemCollectionAdmin(AccountingItemAdmin):
    list_display = ("id", "member", "value", "created", "updated")
    list_filter = (MemberFilter, AssociationFilter)
    autocomplete_fields = ["member", "inv", "association"]


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
    autocomplete_fields = ("run", "member", "inv", "association")
    list_filter = (RunFilter, MemberFilter, AssociationFilter)
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
    autocomplete_fields = ("run", "member", "inv", "association")
    list_filter = (RunFilter, AssociationFilter)
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
    autocomplete_fields = ["member", "inv", "association", "run"]
    list_filter = (RunFilter, AssociationFilter)
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
    autocomplete_fields = ["member", "inv", "association", "reg"]
    list_filter = (MemberFilter, AssociationFilter, RegistrationFilter, "pay", "created")


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
    list_filter = (MemberFilter, AssociationFilter)
    autocomplete_fields = ["member", "inv", "association"]


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
    autocomplete_fields = ("run", "member", "inv", "association")
    list_filter = (RunFilter, MemberFilter, AssociationFilter)


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
    autocomplete_fields = ("member", "method", "association", "reg")
    list_filter = ("status", "method", "typ", AssociationFilter, MemberFilter)


@admin.register(ElectronicInvoice)
class ElectronicInvoiceAdmin(DefModelAdmin):
    autocomplete_fields = ("inv", "association")
    list_filter = (AssociationFilter, InvoiceFilter)


@admin.register(Discount)
class DiscountAdmin(DefModelAdmin):
    list_display = ("name", "value", "max_redeem", "cod", "typ", "show_event")
    # filter_horizontal = ['runs']
    autocomplete_fields = ["event", "runs", "runs"]
    search_fields = ["name"]


@admin.register(RecordAccounting)
class RecordAccountingAdmin(DefModelAdmin):
    list_display = ("run", "association", "global_sum", "bank_sum")
    list_filter = (RunFilter, AssociationFilter)
    autocomplete_fields = ["run", "association"]


@admin.register(RefundRequest)
class RefundRequestAdmin(DefModelAdmin):
    list_display = ("member", "value", "status", "details")
    list_filter = (MemberFilter,)
    autocomplete_fields = ("member", "association")


@admin.register(Collection)
class CollectionAdmin(DefModelAdmin):
    list_display = ("id", "member", "organizer", "total")
    autocomplete_fields = ["member", "run", "organizer", "association"]
    search_fields = ["name"]
