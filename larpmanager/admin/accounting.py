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

"""Django admin configuration for accounting and payment models.

This module provides admin interfaces for managing accounting items, invoices,
discounts, and financial records within the LarpManager application.
"""

from typing import ClassVar

from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin

from larpmanager.admin.base import AssociationFilter, DefModelAdmin, MemberFilter, RegistrationFilter, RunFilter
from larpmanager.models.accounting import (
    AccountingItem,
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
from larpmanager.models.event import Run


class InvoiceFilter(AutocompleteFilter):
    """Filter for payment invoices in admin list views."""

    title = "PaymentInvoice"
    field_name = "inv"


class AccountingItemAdmin(DefModelAdmin):
    """Base admin configuration for accounting item models."""

    exclude = ("search",)
    list_display = ("id", "member", "value")
    autocomplete_fields: ClassVar[list] = ["member", "inv", "association"]
    search_fields: ClassVar[tuple] = ("id", "search")

    @admin.display(ordering="registration__run", description="Run")
    def get_run(self, instance: AccountingItem) -> Run:
        """Get run from instance for admin display."""
        return instance.registration.run


@admin.register(AccountingItemTransaction)
class AccountingItemTransactionAdmin(AccountingItemAdmin):
    """Admin interface for payment transaction accounting items."""

    list_display = ("id", "inv", "member", "value")
    autocomplete_fields: ClassVar[list] = ["member", "inv", "association", "registration"]
    list_filter = (MemberFilter, AssociationFilter, RegistrationFilter)


@admin.register(AccountingItemDiscount)
class AccountingItemDiscountAdmin(AccountingItemAdmin):
    """Admin interface for discount accounting items."""

    list_display = ("id", "disc", "run", "member", "value")
    autocomplete_fields: ClassVar[list] = ["member", "inv", "association", "run", "disc"]
    list_filter = (MemberFilter, AssociationFilter, RunFilter)


@admin.register(AccountingItemDonation)
class AccountingItemDonationAdmin(AccountingItemAdmin):
    """Admin interface for donation accounting items."""

    list_display = ("id", "member", "value", "descr")
    list_filter = (MemberFilter, AssociationFilter)
    autocomplete_fields: ClassVar[list] = ["member", "inv", "association"]


@admin.register(AccountingItemCollection)
class AccountingItemCollectionAdmin(AccountingItemAdmin):
    """Admin interface for collection accounting items."""

    list_display = ("id", "member", "value")
    list_filter = (MemberFilter, AssociationFilter)
    autocomplete_fields: ClassVar[list] = ["member", "inv", "association"]


@admin.register(AccountingItemExpense)
class AccountingItemExpenseAdmin(AccountingItemAdmin):
    """Admin interface for expense accounting items."""

    list_display = ("id", "run", "short_descr", "member", "value", "balance")
    autocomplete_fields = ("run", "member", "inv", "association")
    list_filter = (RunFilter, MemberFilter, AssociationFilter)
    search_fields: ClassVar[tuple] = ("id", "search", "descr")


@admin.register(AccountingItemOutflow)
class AccountingItemOutflowAdmin(AccountingItemAdmin):
    """Admin interface for outflow accounting items."""

    list_display = ("id", "run", "short_descr", "value", "payment_date", "balance")
    autocomplete_fields = ("run", "member", "inv", "association")
    list_filter = (RunFilter, AssociationFilter)
    search_fields: ClassVar[tuple] = ("id", "search", "descr")


@admin.register(AccountingItemInflow)
class AccountingItemInflowAdmin(AccountingItemAdmin):
    """Admin interface for inflow accounting items."""

    list_display = ("id", "run", "short_descr", "value", "payment_date")
    autocomplete_fields: ClassVar[list] = ["member", "inv", "association", "run"]
    list_filter = (RunFilter, AssociationFilter)
    search_fields: ClassVar[tuple] = ("id", "search", "descr")


@admin.register(AccountingItemPayment)
class AccountingItemPaymentAdmin(AccountingItemAdmin):
    """Admin interface for payment accounting items linked to registrations."""

    list_display = ("id", "registration", "member", "value")
    autocomplete_fields: ClassVar[list] = ["member", "inv", "association", "registration"]
    list_filter = (MemberFilter, AssociationFilter, RegistrationFilter, "pay")


@admin.register(AccountingItemMembership)
class AccountingItemMembershipAdmin(AccountingItemAdmin):
    """Admin interface for membership fee accounting items."""

    list_display = ("id", "year", "member", "value")
    list_filter = (MemberFilter, AssociationFilter)
    autocomplete_fields: ClassVar[list] = ["member", "inv", "association"]


@admin.register(AccountingItemOther)
class AccountingItemOtherAdmin(AccountingItemAdmin):
    """Admin interface for miscellaneous accounting items."""

    list_display = ("id", "run", "member", "short_descr", "value", "oth")
    autocomplete_fields = ("run", "member", "inv", "association")
    list_filter = (RunFilter, MemberFilter, AssociationFilter)


@admin.register(PaymentInvoice)
class PaymentInvoiceAdmin(DefModelAdmin):
    """Admin interface for payment invoices and transaction records."""

    exclude = ("search",)
    search_fields: ClassVar[tuple] = ("id", "search", "cod", "causal", "uuid")
    list_display = ("id", "key", "causal", "typ", "method", "status", "mc_gross", "mc_fee", "uuid")
    autocomplete_fields = ("member", "method", "association", "registration")
    list_filter = ("status", "method", "typ", AssociationFilter, MemberFilter)


@admin.register(ElectronicInvoice)
class ElectronicInvoiceAdmin(DefModelAdmin):
    """Admin interface for electronic invoices."""

    list_display = ("id", "inv", "association", "uuid")
    search_fields: ClassVar[tuple] = ("id", "uuid")
    autocomplete_fields = ("inv", "association")
    list_filter = (AssociationFilter, InvoiceFilter)


@admin.register(Discount)
class DiscountAdmin(DefModelAdmin):
    """Admin interface for discount codes and vouchers."""

    list_display = ("name", "value", "max_redeem", "cod", "typ", "show_event", "uuid")
    autocomplete_fields: ClassVar[list] = ["event", "runs", "runs"]
    search_fields: ClassVar[list] = ["id", "name", "uuid"]


@admin.register(RecordAccounting)
class RecordAccountingAdmin(DefModelAdmin):
    """Admin interface for accounting records and financial summaries."""

    list_display = ("run", "association", "global_sum", "bank_sum")
    list_filter = (RunFilter, AssociationFilter)
    autocomplete_fields: ClassVar[list] = ["run", "association"]


@admin.register(RefundRequest)
class RefundRequestAdmin(DefModelAdmin):
    """Admin interface for member refund requests."""

    list_display = ("member", "value", "status", "details", "uuid")
    search_fields: ClassVar[tuple] = ("id", "uuid")
    list_filter = (MemberFilter,)
    autocomplete_fields = ("member", "association")


@admin.register(Collection)
class CollectionAdmin(DefModelAdmin):
    """Admin interface for payment collections."""

    list_display = ("id", "member", "organizer", "total", "uuid")
    autocomplete_fields: ClassVar[list] = ["member", "run", "organizer", "association"]
    search_fields: ClassVar[list] = ["id", "name", "uuid"]
